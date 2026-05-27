"""v0.4 Sprint 5 PR-T7.B — release-gating invariants for the
CASCADE / EVENT separation.

Three invariants the entry memo §3 marked as "must hold before
v0.4.0 release":

  1. test_supersede_does_not_trigger_cascade — calling
     supersede_edge must NOT invoke cascade_remove_doc_from_sources
     (T7 EVENT is preservation; CASCADE is destruction; they don't
     compose into each other).
  2. test_cascade_preserves_supersede_chain — calling
     cascade_remove_doc_from_sources on a doc that is NOT a source
     of a supersede chain leaves the chain pointers
     (status.superseded_by) intact on unrelated edges.
  3. test_historical_replay_via_chain — reconstruct_view_at
     correctly retrieves historical edges from a chain after both
     CASCADE + supersede operations have run against the same wiki.

Unlike the PR-T7.A pure-function tests, these invariants run
against the curated fixture under ``tests/fixtures/lifecycle/`` —
the assertions read the actual frontmatter the wiki-write path
produces, so a regression in the production CASCADE/EVENT
separation surfaces here on every PR thereafter.
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.cascade import cascade_remove_doc_from_sources  # noqa: E402
from core.lifecycle.schema import (  # noqa: E402
    T1_MUTATION_ACTIVE,
    T1_MUTATION_SUPERSEDED,
)
from core.lifecycle.supersede_chain import (  # noqa: E402
    reconstruct_view_at,
    supersede_edge,
    walk_supersede_chain,
)


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "lifecycle"


def _load_fixture(tmp_path: Path) -> Path:
    """Copy the canonical fixture into ``tmp_path`` so tests can
    mutate freely without churning the committed files."""
    target = tmp_path / "lifecycle"
    shutil.copytree(FIXTURE, target)
    return target


def _read_fm(entity_path: Path) -> dict | None:
    """Read frontmatter dict; return None if the file has no
    frontmatter (e.g., README.md sitting alongside entity files)."""
    text = entity_path.read_text(encoding="utf-8")
    parts = text.split("---\n", 2)
    if len(parts) < 2:
        return None
    try:
        return yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None


def _write_fm(entity_path: Path, fm: dict) -> None:
    text = entity_path.read_text(encoding="utf-8")
    parts = text.split("---\n", 2)
    body_tail = "---\n" + parts[2] if len(parts) > 2 else ""
    new_text = (
        "---\n"
        + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True, default_flow_style=False)
        + body_tail
    )
    entity_path.write_text(new_text, encoding="utf-8")


def _all_edges_in_wiki(wiki_root: Path) -> dict:
    """Build the id→edge map the supersede-chain walker expects.

    Iterates every .md under ``wiki_root``, loads frontmatter,
    flattens all relations across all entities into one dict keyed
    by edge.id. Edges without an ``id`` field are skipped (they
    can't be referenced by chain links anyway).
    """
    out: dict[str, dict] = {}
    for path in wiki_root.rglob("*.md"):
        fm = _read_fm(path)
        if fm is None:
            continue
        for rel in fm.get("relations") or []:
            if isinstance(rel, dict) and rel.get("id"):
                out[rel["id"]] = rel
    return out


# ─── Invariant 1 ───────────────────────────────────────────────────


def test_supersede_does_not_trigger_cascade(tmp_path):
    """T7 EVENT must NOT call CASCADE under any path. We patch the
    production cascade entry point + count invocations; zero is
    the only acceptable answer when supersede_edge runs."""
    wiki_root = _load_fixture(tmp_path)

    # Load entity_a's v2 (active head). Will be superseded by a new fact.
    ent_a_path = wiki_root / "entity_a.md"
    fm = _read_fm(ent_a_path)
    old_active = next(r for r in fm["relations"] if r.get("id") == "e_edge_a_v2")

    new_fact = {
        "confidence": 0.97,
        "label":      "v3",
        "target":     "EntityC",
        "target_id":  "e_concept_c",
        "type":       "RELATED_TO",
        "sources":    [
            {
                "doc_id":      "doc_unrelated",
                "role":        "primary",
                "ts":          "2026-06-01T00:00:00+00:00",
                "weight":      0.97,
                "valid_from":  None,
                "valid_until": None,
            },
        ],
    }
    supersede_ts = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Patch the production cascade entry point + a couple of likely
    # underlying call sites (defensive — if someone routes cascade
    # through a different module in future, this still catches it).
    with patch(
        "core.cascade.cascade_remove_doc_from_sources",
    ) as cascade_mock, patch(
        "core.cascade._delete.cascade_remove_doc_from_sources",
    ) as cascade_delete_mock:
        new_edge, mutated_old = supersede_edge(
            old_active, new_fact, supersede_ts,
        )

    assert cascade_mock.call_count == 0, (
        "supersede_edge invoked core.cascade.cascade_remove_doc_from_sources — "
        "T7 EVENT and Layer 3 CASCADE must not compose"
    )
    assert cascade_delete_mock.call_count == 0, (
        "supersede_edge invoked core.cascade._delete.cascade_remove_doc_from_sources — "
        "same invariant via the underlying module"
    )
    # And the actual mutation surface is what PR-T7.A pinned
    assert mutated_old["status"]["superseded_by"] == new_edge["id"]
    assert mutated_old["mutation_type"] == T1_MUTATION_SUPERSEDED


# ─── Invariant 2 ───────────────────────────────────────────────────


def test_cascade_preserves_supersede_chain(tmp_path):
    """Calling cascade_remove_doc_from_sources on a doc that is NOT
    referenced by the supersede chain must leave the chain pointers
    intact on unrelated edges.

    Fixture setup:
      - entity_a has a 2-link chain (V1→V2). Both edges source from
        ``doc_unrelated``.
      - entity_b has one relation sourced from ``doc_cascade_target``.
      - CASCADE removes ``doc_cascade_target``.

    After CASCADE:
      - entity_b's relation is dropped (its only source is gone)
      - entity_a's chain pointers (status.superseded_by) are
        UNCHANGED on both V1 and V2
    """
    wiki_root = _load_fixture(tmp_path)

    # Confirm pre-state: entity_a chain links present + entity_b has
    # the cascade-target source.
    pre_a = _read_fm(wiki_root / "entity_a.md")
    pre_v1 = next(r for r in pre_a["relations"] if r["id"] == "e_edge_a_v1")
    pre_v2 = next(r for r in pre_a["relations"] if r["id"] == "e_edge_a_v2")
    assert pre_v1["status"]["superseded_by"] == "e_edge_a_v2"
    assert pre_v2["status"]["superseded_by"] is None

    pre_b = _read_fm(wiki_root / "entity_b.md")
    assert len(pre_b["relations"]) == 1
    assert pre_b["relations"][0]["sources"][0]["doc_id"] == "doc_cascade_target"

    # Run CASCADE — note the function walks the wiki root looking
    # for entity .md files. We point it at our fixture copy.
    counts = cascade_remove_doc_from_sources(
        "doc_cascade_target",
        wiki_root,
    )

    # entity_b's lone relation should be dropped.
    assert counts["relations_dropped"] >= 1

    # entity_a's chain links must be byte-identical to pre-CASCADE.
    post_a = _read_fm(wiki_root / "entity_a.md")
    post_v1 = next(r for r in post_a["relations"] if r["id"] == "e_edge_a_v1")
    post_v2 = next(r for r in post_a["relations"] if r["id"] == "e_edge_a_v2")

    assert post_v1["status"]["superseded_by"] == "e_edge_a_v2", (
        "CASCADE on unrelated doc broke V1.status.superseded_by — "
        "chain integrity invariant violated"
    )
    assert post_v1["status"]["active"] is False
    assert post_v1["mutation_type"] == T1_MUTATION_SUPERSEDED

    assert post_v2["status"]["active"] is True
    assert post_v2["mutation_type"] == T1_MUTATION_ACTIVE
    assert post_v2["status"]["superseded_by"] is None


# ─── Invariant 3 ───────────────────────────────────────────────────


def test_historical_replay_via_chain(tmp_path):
    """``reconstruct_view_at`` correctly retrieves the historical
    edge from a chain after both CASCADE + supersede operations
    have run against the same wiki.

    Steps:
      1. Load fixture
      2. Run CASCADE on the unrelated doc (proves the chain survives
         CASCADE — covered by invariant #2)
      3. Add a third link to the chain via supersede_edge (V2→V3)
      4. Reconstruct view at a time in the middle of V2's validity
         window → must return V2 (the historical link)
      5. Reconstruct view at "now" → must return V3 (the new active
         head)
    """
    wiki_root = _load_fixture(tmp_path)
    cascade_remove_doc_from_sources("doc_cascade_target", wiki_root)

    # Re-load post-CASCADE state for entity_a (chain should be intact)
    fm = _read_fm(wiki_root / "entity_a.md")
    v1 = next(r for r in fm["relations"] if r["id"] == "e_edge_a_v1")
    v2 = next(r for r in fm["relations"] if r["id"] == "e_edge_a_v2")

    # Add a V3 link superseding V2
    new_fact = {
        "confidence": 0.98,
        "label":      "v3",
        "target":     "EntityC",
        "target_id":  "e_concept_c",
        "type":       "RELATED_TO",
        "sources":    [
            {
                "doc_id":      "doc_unrelated",
                "role":        "primary",
                "ts":          "2026-06-01T00:00:00+00:00",
                "weight":      0.98,
                "valid_from":  None,
                "valid_until": None,
            },
        ],
    }
    supersede_ts = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    v3, mutated_v2 = supersede_edge(v2, new_fact, supersede_ts)

    # Tighten v2.validity.to so the replay can distinguish v2 ⇔ v3
    mutated_v2["validity"]["to"] = supersede_ts.isoformat()
    # And persist back so the lookup builder can find the new edge.
    fm["relations"].append(v3)
    _write_fm(wiki_root / "entity_a.md", fm)

    # Build the id→edge lookup from the post-mutation wiki.
    lookup = _all_edges_in_wiki(wiki_root).get

    # Replay #1 — mid-May (during V2's validity window, before V3)
    mid_may = datetime(2026, 5, 20, 0, 0, 0, tzinfo=timezone.utc)
    view = reconstruct_view_at(v1, lookup, mid_may)
    assert view is not None
    assert view["id"] == "e_edge_a_v2", (
        f"replay at {mid_may.isoformat()} returned "
        f"{view['id'] if view else None}, expected e_edge_a_v2 "
        f"(the historical link active during that window)"
    )

    # Replay #2 — after supersede_ts (V3 is now active)
    later = datetime(2026, 6, 2, 0, 0, 0, tzinfo=timezone.utc)
    view = reconstruct_view_at(v1, lookup, later)
    assert view is not None
    assert view["id"] == v3["id"], (
        f"replay at {later.isoformat()} returned "
        f"{view['id'] if view else None}, expected the new active "
        f"head {v3['id']}"
    )

    # Replay #3 — early April (before V1's validity window)
    early = datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc)
    view = reconstruct_view_at(v1, lookup, early)
    assert view is None, (
        f"replay at {early.isoformat()} returned {view!r}, expected "
        f"None (no chain link covers that time)"
    )

    # walk_supersede_chain sanity — full 3-link chain still walkable
    full_chain = walk_supersede_chain(v1, lookup)
    assert [e["id"] for e in full_chain] == [
        "e_edge_a_v1", "e_edge_a_v2", v3["id"],
    ]


# ─── Fixture sanity ────────────────────────────────────────────────


def test_fixture_loads_and_parses(tmp_path):
    """Sanity — the 3 fixture files load + parse + have the chain
    pointers the invariants above depend on. If this test fails,
    the fixture itself is broken and the other tests' verdicts
    can't be trusted."""
    wiki_root = _load_fixture(tmp_path)
    assert (wiki_root / "entity_a.md").exists()
    assert (wiki_root / "entity_b.md").exists()
    assert (wiki_root / "entity_c.md").exists()

    fm_a = _read_fm(wiki_root / "entity_a.md")
    assert len(fm_a["relations"]) == 2
    v1, v2 = fm_a["relations"]
    assert v1["id"] == "e_edge_a_v1"
    assert v1["status"]["superseded_by"] == "e_edge_a_v2"
    assert v2["id"] == "e_edge_a_v2"
    assert v2["status"]["active"] is True


def test_fixture_is_isolated_from_committed_files(tmp_path):
    """Mutating the loaded copy must NOT touch the committed fixture
    files. Pins the copy-out pattern so future tests don't
    accidentally write to the repo-resident fixture."""
    wiki_root = _load_fixture(tmp_path)
    committed_text = (FIXTURE / "entity_a.md").read_text(encoding="utf-8")

    # Trash the copy.
    (wiki_root / "entity_a.md").write_text("# overwritten\n", encoding="utf-8")

    # Committed file unchanged.
    assert (FIXTURE / "entity_a.md").read_text(encoding="utf-8") == committed_text
