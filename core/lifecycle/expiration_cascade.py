"""v0.4 Sprint 5 PR-T1.B — T1 expiration batch.

Walks every wiki entity's frontmatter and marks edges as
``mutation_type="expired"`` when **all** of their active sources
have reached ``valid_until``. Sources themselves are not mutated —
expiration is a *derived* property from ``valid_until`` ≤
``current_time`` rather than a stored flag, so a rollback /
re-import path stays trivial.

What this module is NOT
-----------------------

- **Not a delete.** Deletion is the CASCADE concern (Layer 3
  ``cascade_remove``). Per entry memo §3 invariant ``T7 EVENT vs
  CASCADE``, expiration is an EVENT — preserves history, only
  flips status so the consumer can filter.
- **Not a confidence recompute.** Downstream
  ``compute_confidence_from_sources`` extension (entry memo §348)
  will accept a ``current_time`` parameter so the v0.3 read path
  stays byte-identical. This module's only mutation surface is
  ``edge.status`` + ``edge.mutation_type``.
- **Not a supersede operation.** Supersede chains are PR-T7.A.
  This module never touches ``status.superseded_by`` —
  ``mutation_type="expired"`` is exclusive with
  ``"superseded"``.

What this module IS
-------------------

Two pure functions + one wiki-walker:

- ``is_source_expired(source, current_time)`` — derived predicate.
  ``True`` iff ``source["valid_until"]`` is a parseable ISO 8601
  timestamp ≤ ``current_time``. ``None`` (indefinite validity) is
  never expired. Malformed values return ``False`` defensively
  rather than raising — the migration script (PR-T1.A) already
  ran validators at write-time, so a malformed window here means
  externally-edited frontmatter that the cascade should not crash
  on.
- ``is_edge_immune(edge)`` — opt-out hook. ``edge["manual_immune"]``
  truthy ⇒ cascade skips this edge. Operator sets this on edges
  whose expiration should be a manual decision (e.g., curated
  reference relations). The flag is **edge-level only** — there
  is no source-level immunity (sources are immutable evidence;
  immunity is an operator policy on the relation that uses them).
- ``expiration_cascade(entity_root, current_time, dry_run=True)``
  — wiki walker. Loads each ``.md`` entity, iterates relations,
  checks each relation's sources, and when **every** non-already-
  expired source is expired (or there are no sources at all), marks
  the edge's ``mutation_type="expired"``, ``status.active=False``.
  Edges that are already inactive (superseded / invalidated /
  expired) are left untouched — idempotent.

Idempotency
-----------

Running the cascade twice on the same wiki + same ``current_time``
is a no-op the second time: every targeted edge already has
``status.active=False`` + ``mutation_type="expired"`` and the
"already inactive" guard skips it.

Atomic per-file write — same tempfile + ``os.replace`` pattern as
PR-T1.A migration script. Half-written frontmatter on crash is
not possible.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from core.lifecycle.schema import (
    T1_MUTATION_ACTIVE,
    T1_MUTATION_EXPIRED,
    T1_SOURCE_FIELD_VALID_UNTIL,
    T7_EDGE_FIELD_MUTATION_TYPE,
    T7_EDGE_FIELD_STATUS,
    apply_v04_edge_defaults,
    validate_edge_v04_fields,
)


# ─── Frontmatter split / serialize (shared shape with PR-T1.A) ────
#
# PR-T1.A migration script has its own ``_split_frontmatter`` /
# ``_serialize_frontmatter`` helpers. We duplicate the minimal
# surface here rather than depend on the migration script module so
# the cascade can live behind a tiny import cost (no operator
# entry-point coupling). If a third caller needs the same helpers,
# extract to ``core.lifecycle._frontmatter_io``.


_FRONTMATTER_FENCE = "---"


def _split_frontmatter(text: str) -> tuple[dict | None, str]:
    """Return (frontmatter_dict_or_None, body_tail_including_fence)."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != _FRONTMATTER_FENCE:
        return None, text
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == _FRONTMATTER_FENCE:
            end_idx = i
            break
    if end_idx is None:
        return None, text
    fm_text = "".join(lines[1:end_idx])
    body_tail = "".join(lines[end_idx:])
    try:
        fm = yaml.safe_load(fm_text)
        if not isinstance(fm, dict):
            return None, text
        return fm, body_tail
    except yaml.YAMLError:
        return None, text


def _serialize_frontmatter(fm: dict, body_tail: str) -> str:
    """Same YAML defaults as PR-T1.A — preserve key order, allow
    unicode (Korean entity names), no flow style."""
    fm_text = yaml.safe_dump(
        fm,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    if not fm_text.endswith("\n"):
        fm_text += "\n"
    return f"{_FRONTMATTER_FENCE}\n{fm_text}{body_tail}"


# ─── Pure predicates ───────────────────────────────────────────────


def _parse_iso(value: Any) -> datetime | None:
    """Best-effort ISO 8601 parse. Returns ``None`` for malformed /
    non-string / ``None`` input — the cascade treats unparseable
    timestamps as "indefinite" rather than raising, so externally
    edited frontmatter can't halt the batch."""
    if value is None or not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    # ensure timezone-aware UTC for comparison against current_time
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def is_source_expired(source: dict, current_time: datetime) -> bool:
    """Derived predicate — source is expired iff its ``valid_until``
    is set and ≤ ``current_time``.

    Properties:
      - ``valid_until is None``    → never expired (indefinite)
      - ``valid_until > now``      → not yet expired
      - ``valid_until == now``     → expired (boundary inclusive —
                                     matches the "≤" in the entry
                                     memo §4 spec)
      - ``valid_until < now``      → expired
      - malformed ``valid_until``  → treated as ``None`` (defensive)

    ``current_time`` must be timezone-aware. Tests freeze the clock
    via ``monkeypatch.setattr("core.lifecycle.clock.now", ...)``.
    """
    if not isinstance(source, dict):
        return False
    vu = _parse_iso(source.get(T1_SOURCE_FIELD_VALID_UNTIL))
    if vu is None:
        return False
    return vu <= current_time


def is_edge_immune(edge: dict) -> bool:
    """Opt-out hook — ``edge["manual_immune"]`` truthy ⇒ cascade
    skips this edge.

    The flag is **edge-level only**. Sources are immutable evidence;
    operator immunity is a policy on the relation that uses them,
    not on the underlying evidence. Curated reference relations
    (e.g., legal references that should never auto-expire even when
    their source PDF gets a sunset date) set this.

    The flag is not part of the PR-0 schema validators by design —
    it's an operator escape hatch, not part of the canonical
    lifecycle vocabulary. Setting it does not invalidate the edge
    under ``validate_edge_v04_fields``.
    """
    if not isinstance(edge, dict):
        return False
    return bool(edge.get("manual_immune"))


def _is_edge_already_inactive(edge: dict) -> bool:
    """Idempotency guard — skip edges whose previous lifecycle state
    already says inactive. Covers all three EVENT types from the
    mutation_type enum: invalidated (CASCADE), superseded (T7),
    expired (this module's own previous run).
    """
    mt = edge.get(T7_EDGE_FIELD_MUTATION_TYPE)
    if mt and mt != T1_MUTATION_ACTIVE:
        return True
    status = edge.get(T7_EDGE_FIELD_STATUS)
    if isinstance(status, dict) and status.get("active") is False:
        return True
    return False


def _maybe_expire_edge(edge: dict, current_time: datetime) -> tuple[dict, bool]:
    """Decide expiration for one edge.

    Returns (mutated_edge, did_mutate). ``did_mutate=False`` covers:
      - edge already inactive (idempotency guard)
      - edge immune (operator opt-out)
      - edge has no sources → vacuously "all sources expired" but the
        entry memo's intent is "evidence-driven expiration"; no
        sources means we don't know, so leave alone
      - at least one source still active (not all expired)

    When the edge does expire, the mutation is minimal:
    ``status.active=False`` + ``mutation_type="expired"``. The
    ``superseded_by`` / ``superseded_at`` fields are deliberately
    left untouched — expiration is exclusive with supersede.
    """
    if _is_edge_already_inactive(edge):
        return edge, False
    if is_edge_immune(edge):
        return edge, False
    sources = edge.get("sources")
    if not isinstance(sources, list) or not sources:
        return edge, False

    # All non-malformed sources must be expired for the cascade to fire.
    saw_at_least_one_valid_source = False
    for src in sources:
        if not isinstance(src, dict):
            continue
        saw_at_least_one_valid_source = True
        if not is_source_expired(src, current_time):
            return edge, False
    if not saw_at_least_one_valid_source:
        return edge, False

    # Apply defaults first so we are operating on a fully-shaped edge,
    # then flip the two fields. apply_v04_edge_defaults is idempotent.
    new_edge = apply_v04_edge_defaults(edge)
    status = dict(new_edge.get(T7_EDGE_FIELD_STATUS) or {})
    status["active"] = False
    new_edge[T7_EDGE_FIELD_STATUS] = status
    new_edge[T7_EDGE_FIELD_MUTATION_TYPE] = T1_MUTATION_EXPIRED
    return new_edge, True


# ─── Wiki walker ───────────────────────────────────────────────────


def _process_entity_file(
    path: Path,
    current_time: datetime,
    dry_run: bool,
) -> dict:
    """Apply the cascade to one entity file. Returns stats dict.

    On ``dry_run=True``, no writes — the stats still report what
    would have been mutated so the operator can preview.
    """
    stats = {
        "scanned":           1,
        "had_no_relations":  0,
        "edges_expired":     0,
        "files_mutated":     0,
        "validation_failed": 0,
        "errors":            0,
    }
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"[EXPIRE] read fail {path}: {e}")
        stats["errors"] = 1
        return stats

    fm, body_tail = _split_frontmatter(text)
    if fm is None:
        return stats

    relations = fm.get("relations")
    if not isinstance(relations, list) or not relations:
        stats["had_no_relations"] = 1
        return stats

    new_relations = []
    file_changed = False
    for rel in relations:
        if not isinstance(rel, dict):
            new_relations.append(rel)
            continue
        new_rel, did_mutate = _maybe_expire_edge(rel, current_time)
        if did_mutate:
            stats["edges_expired"] += 1
            file_changed = True
            # Validate the mutated edge before accepting — defends
            # against a future schema change that the cascade hasn't
            # learned about yet.
            try:
                validate_edge_v04_fields(new_rel)
            except ValueError as e:
                print(f"[EXPIRE] validation fail {path}: {e}")
                stats["validation_failed"] = 1
                stats["errors"] = 1
                # Reject the mutation rather than write a malformed edge.
                new_rel = rel
                stats["edges_expired"] -= 1
                file_changed = (
                    stats["edges_expired"] > 0
                    or len([r for r in new_relations if r is not rel]) > 0
                )
        new_relations.append(new_rel)

    if not file_changed:
        return stats

    fm["relations"] = new_relations
    stats["files_mutated"] = 1
    if dry_run:
        return stats

    # Atomic per-file write (same pattern as PR-T1.A migration).
    new_text = _serialize_frontmatter(fm, body_tail)
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(new_text)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp_path, path)
    except Exception as e:
        print(f"[EXPIRE] write fail {path}: {e}")
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        stats["errors"] = 1
        stats["files_mutated"] = 0
    return stats


def expiration_cascade(
    entity_root: Path | str,
    current_time: datetime | None = None,
    *,
    dry_run: bool = True,
) -> dict:
    """Walk every entity ``.md`` under ``entity_root`` and apply the
    T1 expiration cascade.

    Args:
        entity_root: wiki root (e.g. ``wiki``). Walks recursively;
            only files matching ``*.md`` are considered.
        current_time: timezone-aware UTC ``datetime``. ``None`` (the
            default) calls ``core.lifecycle.clock.now()`` — the
            production code path. Tests freeze time by passing an
            explicit value.
        dry_run: when ``True`` (default), no writes. Stats still
            count "would have mutated" so the operator can preview.

    Returns:
        Aggregate stats dict — ``scanned`` (files seen),
        ``had_no_relations`` (skipped, no work to do),
        ``edges_expired`` (per-file sum), ``files_mutated``,
        ``validation_failed`` (mutations rejected by the post-write
        validator), ``errors`` (read / write / parse failures).

    The wiki-tree filter is intentionally loose: any ``.md`` file
    under ``entity_root`` is candidate. Production wiki layout
    keeps entities under ``entity/prod/<type>/`` + ``entity/test/...``
    but this function does not encode that layout — the test fixture
    can flatten the tree without breaking anything.
    """
    if current_time is None:
        from core.lifecycle.clock import now
        current_time = now()

    root = Path(entity_root)
    if not root.exists():
        raise FileNotFoundError(f"entity root not found: {root}")

    agg = {
        "scanned":           0,
        "had_no_relations":  0,
        "edges_expired":     0,
        "files_mutated":     0,
        "validation_failed": 0,
        "errors":            0,
    }
    for entity_file in sorted(root.rglob("*.md")):
        # Skip snapshot dirs created by PR-T1.A migration. The
        # snapshot path is ``<wiki>.pre-v04-migration/...``; any
        # part containing that suffix is a snapshot we should not
        # double-process. Substring match (not equality) because
        # the parent name is the entire ``wiki.pre-v04-migration``
        # token.
        if any("pre-v04-migration" in p for p in entity_file.parts):
            continue
        s = _process_entity_file(entity_file, current_time, dry_run)
        for k in agg:
            agg[k] += s.get(k, 0)
    return agg


__all__ = [
    "is_source_expired",
    "is_edge_immune",
    "expiration_cascade",
]


if __name__ == "__main__":
    # Quick smoke test — operator typically uses
    # scripts/run_expiration_cascade.py instead.
    sys.exit(0)
