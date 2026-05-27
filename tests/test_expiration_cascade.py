"""v0.4 Sprint 5 PR-T1.B — contract tests for the T1 expiration cascade.

Four invariants required by the entry memo §"PR-T1.B Done when":

  1. test_source_expires_at_valid_until — derived predicate is
     correct at the boundary (≤ inclusive)
  2. test_relation_dropped_when_all_active_sources_expire — cascade
     marks the edge when every source has expired
  3. test_valid_until_null_means_indefinite — None valid_until ⇒
     never expired
  4. test_temporal_cascade_preserves_manual_immunity — operator's
     edge.manual_immune opt-out is respected

Plus a small ring of helpers (idempotency, atomic write, validator
guard) so the cascade can be safely re-run / re-deployed.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.lifecycle.expiration_cascade import (  # noqa: E402
    expiration_cascade,
    is_edge_immune,
    is_source_expired,
)
from core.lifecycle.schema import (  # noqa: E402
    T1_MUTATION_ACTIVE,
    T1_MUTATION_EXPIRED,
    T1_MUTATION_INVALIDATED,
    T1_MUTATION_SUPERSEDED,
)


# Reference "now" for these tests — a fixed UTC point. All
# valid_until values in fixtures are anchored relative to this.
NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def _src(valid_until=None, valid_from=None, **extras) -> dict:
    """Build a minimal v0.4 source dict for fixture composition."""
    out = {"doc_id": "doc_x", "role": "primary", "ts": "2026-05-01T00:00:00+00:00", "weight": 0.9, **extras}
    out["valid_from"] = valid_from
    out["valid_until"] = valid_until
    return out


def _edge(sources, **extras) -> dict:
    """Build a minimal v0.4 edge dict with the four T1+T7 fields
    pre-defaulted so the cascade's idempotency guard does not skip."""
    return {
        "confidence":    0.9,
        "label":         "관련",
        "target":        "Target",
        "target_id":     "e_concept_x",
        "type":          "RELATED_TO",
        "sources":       sources,
        "validity":      {"from": None, "to": None},
        "status":        {"active": True, "superseded_by": None, "superseded_at": None},
        "mutation_type": T1_MUTATION_ACTIVE,
        **extras,
    }


def _write_entity(path: Path, relations: list) -> None:
    """Write a minimal entity .md with the given relations list."""
    fm = {
        "entity_id":   "e_test_abc",
        "entity_type": "concept",
        "name":        "TestEntity",
        "relations":   relations,
    }
    text = (
        "---\n"
        + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True, default_flow_style=False)
        + "---\n"
        + "## body\n"
    )
    path.write_text(text, encoding="utf-8")


def _read_entity_relations(path: Path) -> list:
    text = path.read_text(encoding="utf-8")
    # crude split — sufficient for the test fixtures (no nested ---)
    parts = text.split("---\n", 2)
    fm = yaml.safe_load(parts[1])
    return fm["relations"]


# ─── #1 — derived predicate boundary ──────────────────────────────


def test_source_expires_at_valid_until():
    """Boundary inclusive — ``valid_until == current_time`` ⇒ expired."""
    earlier = (NOW - timedelta(days=1)).isoformat()
    exactly = NOW.isoformat()
    later   = (NOW + timedelta(days=1)).isoformat()

    assert is_source_expired(_src(valid_until=earlier), NOW) is True
    assert is_source_expired(_src(valid_until=exactly), NOW) is True
    assert is_source_expired(_src(valid_until=later),   NOW) is False


# ─── #2 — cascade marks edge when all sources expired ─────────────


def test_relation_dropped_when_all_active_sources_expire(tmp_path):
    """Wiki walker: one entity, one relation, two sources both
    expired → edge gets mutation_type=expired, status.active=False.
    File is rewritten."""
    expired = (NOW - timedelta(days=10)).isoformat()
    edge = _edge(
        sources=[
            _src(valid_until=expired, doc_id="doc_a"),
            _src(valid_until=expired, doc_id="doc_b"),
        ],
    )
    entity_path = tmp_path / "entity_a.md"
    _write_entity(entity_path, [edge])

    stats = expiration_cascade(tmp_path, current_time=NOW, dry_run=False)
    assert stats["files_mutated"] == 1
    assert stats["edges_expired"] == 1
    assert stats["errors"] == 0

    rels = _read_entity_relations(entity_path)
    assert len(rels) == 1
    new_edge = rels[0]
    assert new_edge["status"]["active"] is False
    assert new_edge["mutation_type"] == T1_MUTATION_EXPIRED


def test_relation_NOT_dropped_when_one_source_still_active(tmp_path):
    """Companion to #2 — one expired + one still active ⇒ edge stays
    active. Pins the "all sources" half of the rule."""
    expired = (NOW - timedelta(days=10)).isoformat()
    future = (NOW + timedelta(days=10)).isoformat()
    edge = _edge(
        sources=[
            _src(valid_until=expired, doc_id="doc_a"),
            _src(valid_until=future,  doc_id="doc_b"),
        ],
    )
    entity_path = tmp_path / "entity_a.md"
    _write_entity(entity_path, [edge])

    stats = expiration_cascade(tmp_path, current_time=NOW, dry_run=False)
    assert stats["files_mutated"] == 0
    assert stats["edges_expired"] == 0

    rels = _read_entity_relations(entity_path)
    assert rels[0]["status"]["active"] is True
    assert rels[0]["mutation_type"] == T1_MUTATION_ACTIVE


# ─── #3 — None valid_until = indefinite ───────────────────────────


def test_valid_until_null_means_indefinite():
    """``None`` valid_until ⇒ never expired, even when current_time
    is far in the future."""
    assert is_source_expired(_src(valid_until=None), NOW) is False
    future = datetime(3000, 1, 1, tzinfo=timezone.utc)
    assert is_source_expired(_src(valid_until=None), future) is False


def test_indefinite_source_blocks_edge_expiration(tmp_path):
    """One expired + one indefinite ⇒ edge stays active (the
    indefinite source is "still alive" by definition)."""
    expired = (NOW - timedelta(days=10)).isoformat()
    edge = _edge(
        sources=[
            _src(valid_until=expired, doc_id="doc_a"),
            _src(valid_until=None,    doc_id="doc_b"),
        ],
    )
    entity_path = tmp_path / "entity_a.md"
    _write_entity(entity_path, [edge])

    stats = expiration_cascade(tmp_path, current_time=NOW, dry_run=False)
    assert stats["edges_expired"] == 0


# ─── #4 — manual immunity opt-out ─────────────────────────────────


def test_temporal_cascade_preserves_manual_immunity(tmp_path):
    """Edge with ``manual_immune: True`` is never expired by the
    cascade, even when all its sources are expired."""
    expired = (NOW - timedelta(days=10)).isoformat()
    edge = _edge(
        sources=[
            _src(valid_until=expired, doc_id="doc_a"),
            _src(valid_until=expired, doc_id="doc_b"),
        ],
        manual_immune=True,
    )
    entity_path = tmp_path / "entity_a.md"
    _write_entity(entity_path, [edge])

    stats = expiration_cascade(tmp_path, current_time=NOW, dry_run=False)
    assert stats["edges_expired"] == 0
    assert stats["files_mutated"] == 0

    rels = _read_entity_relations(entity_path)
    assert rels[0]["status"]["active"] is True
    assert rels[0]["mutation_type"] == T1_MUTATION_ACTIVE
    assert rels[0]["manual_immune"] is True

    # Direct predicate check too
    assert is_edge_immune(edge) is True
    assert is_edge_immune({"manual_immune": False}) is False
    assert is_edge_immune({}) is False


# ─── Idempotency + dry-run + already-inactive guard ───────────────


def test_dry_run_does_not_write(tmp_path):
    expired = (NOW - timedelta(days=10)).isoformat()
    edge = _edge(sources=[_src(valid_until=expired)])
    entity_path = tmp_path / "entity_a.md"
    _write_entity(entity_path, [edge])
    before = entity_path.read_text(encoding="utf-8")

    stats = expiration_cascade(tmp_path, current_time=NOW, dry_run=True)
    assert stats["edges_expired"] == 1
    assert stats["files_mutated"] == 1   # would-have count

    after = entity_path.read_text(encoding="utf-8")
    assert before == after, "dry_run=True must not modify disk"


def test_idempotent_second_apply_is_noop(tmp_path):
    """Run apply twice — second run sees the edge already inactive
    and skips it (mutation_type=expired and status.active=False)."""
    expired = (NOW - timedelta(days=10)).isoformat()
    edge = _edge(sources=[_src(valid_until=expired)])
    entity_path = tmp_path / "entity_a.md"
    _write_entity(entity_path, [edge])

    first = expiration_cascade(tmp_path, current_time=NOW, dry_run=False)
    assert first["edges_expired"] == 1

    second = expiration_cascade(tmp_path, current_time=NOW, dry_run=False)
    assert second["edges_expired"] == 0
    assert second["files_mutated"] == 0


def test_already_superseded_edge_not_touched(tmp_path):
    """Edge with mutation_type=superseded (T7 EVENT) must not be
    re-flipped to expired even if all its sources are expired —
    expiration is exclusive with supersede."""
    expired = (NOW - timedelta(days=10)).isoformat()
    edge = _edge(
        sources=[_src(valid_until=expired)],
        status={"active": False, "superseded_by": "e_x", "superseded_at": "2026-05-15T00:00:00+00:00"},
        mutation_type=T1_MUTATION_SUPERSEDED,
    )
    entity_path = tmp_path / "entity_a.md"
    _write_entity(entity_path, [edge])

    stats = expiration_cascade(tmp_path, current_time=NOW, dry_run=False)
    assert stats["edges_expired"] == 0

    rels = _read_entity_relations(entity_path)
    assert rels[0]["mutation_type"] == T1_MUTATION_SUPERSEDED
    assert rels[0]["status"]["superseded_by"] == "e_x"


def test_already_invalidated_edge_not_touched(tmp_path):
    """Same guard for CASCADE-invalidated edges — preserves history."""
    expired = (NOW - timedelta(days=10)).isoformat()
    edge = _edge(
        sources=[_src(valid_until=expired)],
        status={"active": False, "superseded_by": None, "superseded_at": None},
        mutation_type=T1_MUTATION_INVALIDATED,
    )
    entity_path = tmp_path / "entity_a.md"
    _write_entity(entity_path, [edge])

    stats = expiration_cascade(tmp_path, current_time=NOW, dry_run=False)
    assert stats["edges_expired"] == 0


def test_clock_now_called_when_current_time_omitted(monkeypatch, tmp_path):
    """When current_time=None, expiration_cascade calls
    core.lifecycle.clock.now(). Monkeypatch verifies the wiring."""
    expired = (NOW - timedelta(days=10)).isoformat()
    edge = _edge(sources=[_src(valid_until=expired)])
    _write_entity(tmp_path / "entity_a.md", [edge])

    frozen = datetime(2027, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr("core.lifecycle.clock.now", lambda: frozen)
    stats = expiration_cascade(tmp_path, dry_run=False)
    assert stats["edges_expired"] == 1


# ─── Edge cases ────────────────────────────────────────────────────


def test_edge_with_no_sources_not_expired(tmp_path):
    """Edge with empty sources list — vacuously "all expired" but
    the intent is evidence-driven; no evidence ⇒ no expiration."""
    edge = _edge(sources=[])
    _write_entity(tmp_path / "entity_a.md", [edge])
    stats = expiration_cascade(tmp_path, current_time=NOW, dry_run=False)
    assert stats["edges_expired"] == 0


def test_malformed_valid_until_treated_as_indefinite():
    """Defensive — unparseable ISO string returns False from
    is_source_expired (so the batch doesn't halt)."""
    assert is_source_expired(_src(valid_until="not-a-date"), NOW) is False
    assert is_source_expired(_src(valid_until=12345), NOW) is False
    assert is_source_expired({}, NOW) is False
    assert is_source_expired("not a dict", NOW) is False


def test_entity_with_no_relations_skipped(tmp_path):
    """Entity files without a relations list count under
    had_no_relations and contribute zero work."""
    fm = {"entity_id": "e_x", "name": "X", "entity_type": "concept"}
    text = (
        "---\n"
        + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True, default_flow_style=False)
        + "---\n"
    )
    (tmp_path / "lone.md").write_text(text, encoding="utf-8")

    stats = expiration_cascade(tmp_path, current_time=NOW, dry_run=False)
    assert stats["scanned"] == 1
    assert stats["had_no_relations"] == 1
    assert stats["edges_expired"] == 0


def test_snapshot_dir_skipped(tmp_path):
    """``wiki.pre-v04-migration`` snapshot dir (created by PR-T1.A)
    must not be re-scanned — would double-apply / wreck the
    rollback path."""
    snap = tmp_path / "wiki.pre-v04-migration" / "entity"
    snap.mkdir(parents=True)
    expired = (NOW - timedelta(days=10)).isoformat()
    edge = _edge(sources=[_src(valid_until=expired)])
    _write_entity(snap / "ghost.md", [edge])

    stats = expiration_cascade(tmp_path, current_time=NOW, dry_run=False)
    assert stats["scanned"] == 0
    assert stats["edges_expired"] == 0


# ─── Missing root sanity ──────────────────────────────────────────


def test_missing_root_raises():
    with pytest.raises(FileNotFoundError):
        expiration_cascade("/nonexistent/wiki/path", current_time=NOW)
