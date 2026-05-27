"""v0.4 Sprint 5 PR-T2.B — contract tests for the A-path router.

Pins both required entry-memo invariants:

  test_t2_a_class_routes_to_cascade
    classify_contradiction → A_invalidate dispatches through
    route_a_invalidate → cascade_remove_doc_from_sources

  test_correction_invalidates_wrong_source_only
    cascade removes only the bad doc's source from edges that
    reference it; other sources on the same edge stay.

Plus guards on the dispatcher's argument validation, B-path
NotImplementedError, ignore-no-op, and audit row shape.
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.lifecycle.contradiction_router import (  # noqa: E402
    dispatch_contradiction,
    route_a_invalidate,
    route_b_supersede,
)
from core.lifecycle.supersede_chain import (  # noqa: E402
    reconstruct_view_at,
)
from core.lifecycle.schema import T1_MUTATION_INVALIDATED  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "lifecycle"
NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def _load_fixture(tmp_path: Path) -> Path:
    target = tmp_path / "lifecycle"
    shutil.copytree(FIXTURE, target)
    return target


def _read_fm(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    parts = text.split("---\n", 2)
    if len(parts) < 2:
        return None
    try:
        return yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None


def _edge_world_changed_to_supersede() -> tuple[dict, dict]:
    """Build an edge + new_fact pair that classifies to B_supersede."""
    old = {
        "sources":       [{"doc_id": "doc_a", "weight": 0.7, "ts": "2026-04-01T00:00:00+00:00"}],
        "validity":      {"from": "2026-04-01T00:00:00+00:00", "to": "2026-05-01T00:00:00+00:00"},
        "status":        {"active": True, "superseded_by": None, "superseded_at": None},
        "mutation_type": "active",
    }
    new_fact = {
        "valid_from": "2026-07-01T00:00:00+00:00",
        "timestamp":  "2026-07-01T00:00:00+00:00",
        "weight":     0.7,
    }
    return old, new_fact


def _edge_corrected_invalidate(bad_doc_id: str) -> tuple[dict, dict]:
    """Build an edge + new_fact pair that classifies to A_invalidate."""
    old = {
        "sources": [
            {"doc_id": bad_doc_id, "weight": 0.7, "ts": "2026-04-01T00:00:00+00:00"},
        ],
        "validity":      {"from": "2026-04-01T00:00:00+00:00",
                          "to":   "2026-05-31T00:00:00+00:00"},
        "status":        {"active": True, "superseded_by": None, "superseded_at": None},
        "mutation_type": "active",
    }
    new_fact = {
        "valid_from": "2026-04-01T00:00:00+00:00",
        "timestamp":  "2026-03-01T00:00:00+00:00",   # before old.vf
        "weight":     0.95,
    }
    return old, new_fact


def _edge_duplicate_ignore() -> tuple[dict, dict]:
    """Pair that classifies to ignore."""
    old = {
        "sources":       [{"doc_id": "doc_a", "weight": 0.7, "ts": "2026-04-01T00:00:00+00:00"}],
        "validity":      {"from": "2026-04-01T00:00:00+00:00",
                          "to":   "2026-08-01T00:00:00+00:00"},
        "status":        {"active": True, "superseded_by": None, "superseded_at": None},
        "mutation_type": "active",
    }
    new_fact = {
        "valid_from": "2026-05-15T00:00:00+00:00",
        "timestamp":  "2026-05-15T00:00:00+00:00",
        "weight":     0.7,
    }
    return old, new_fact


# ─── Invariant 1 — A-path routes to cascade ───────────────────────


def test_t2_a_class_routes_to_cascade(tmp_path):
    """A_invalidate → cascade_remove_doc_from_sources runs against the
    fixture wiki + audit row emitted with mutation_type=invalidated."""
    wiki_root = _load_fixture(tmp_path)
    old, new_fact = _edge_corrected_invalidate("doc_cascade_target")

    captured: list[dict] = []
    result = dispatch_contradiction(
        old, new_fact,
        now=NOW,
        entity_root=wiki_root,
        bad_doc_id_for_a="doc_cascade_target",
        audit_emit=captured.append,
    )

    # A-path dispatched
    assert result["action"] == "invalidate"

    # Cascade ran — entity_b's lone-source relation was dropped
    assert result["counts"]["relations_dropped"] >= 1

    # Audit row emitted with the contract shape
    assert len(captured) == 1
    audit = captured[0]
    assert audit["endpoint"] == "lifecycle:invalidate"
    assert audit["mutation_type"] == T1_MUTATION_INVALIDATED
    assert audit["bad_doc_id"] == "doc_cascade_target"
    assert audit["entities_scanned"] >= 1
    assert audit["relations_dropped"] >= 1


# ─── Invariant 2 — wrong source only ─────────────────────────────


def test_correction_invalidates_wrong_source_only(tmp_path):
    """Cascade removes only the bad doc — entity_a's relations (which
    don't reference doc_cascade_target) stay intact post-cascade.
    Pins the 'other sources preserved' half of the entry memo
    invariant."""
    wiki_root = _load_fixture(tmp_path)
    pre_a = _read_fm(wiki_root / "entity_a.md")
    pre_v1 = next(r for r in pre_a["relations"] if r["id"] == "e_edge_a_v1")
    pre_v2 = next(r for r in pre_a["relations"] if r["id"] == "e_edge_a_v2")

    route_a_invalidate(
        "doc_cascade_target", wiki_root, audit_emit=lambda _: None,
    )

    # entity_a's chain pointers + sources are untouched
    post_a = _read_fm(wiki_root / "entity_a.md")
    post_v1 = next(r for r in post_a["relations"] if r["id"] == "e_edge_a_v1")
    post_v2 = next(r for r in post_a["relations"] if r["id"] == "e_edge_a_v2")
    assert post_v1["sources"] == pre_v1["sources"]
    assert post_v2["sources"] == pre_v2["sources"]
    assert post_v1["status"]["superseded_by"] == "e_edge_a_v2"


# ─── route_a_invalidate argument validation ──────────────────────


def test_route_a_invalidate_rejects_empty_doc_id(tmp_path):
    with pytest.raises(ValueError, match="bad_doc_id"):
        route_a_invalidate("", tmp_path)


def test_route_a_invalidate_rejects_missing_root():
    with pytest.raises(ValueError, match="entity_root"):
        route_a_invalidate("doc_x", "/nonexistent/path")


def test_route_a_invalidate_uses_default_audit_when_no_callback(tmp_path):
    """audit_emit=None routes through core.audit_bridge — should not
    raise (the bridge wraps writes defensively even when SQLite is
    missing/locked)."""
    wiki_root = _load_fixture(tmp_path)
    # Don't crash; cascade should still run.
    result = route_a_invalidate("doc_cascade_target", wiki_root)
    assert result["action"] == "invalidate"


# ─── dispatch_contradiction routing ──────────────────────────────


def test_dispatch_calls_classify(tmp_path):
    """ignore label returns no-op dict + does NOT call cascade."""
    old, new_fact = _edge_duplicate_ignore()
    result = dispatch_contradiction(old, new_fact, now=NOW)
    assert result == {"action": "ignore", "label": "ignore"}


def test_dispatch_routes_a_to_cascade(tmp_path):
    """A_invalidate dispatched → cascade ran (entity_b drop)."""
    wiki_root = _load_fixture(tmp_path)
    old, new_fact = _edge_corrected_invalidate("doc_cascade_target")

    captured: list[dict] = []
    result = dispatch_contradiction(
        old, new_fact, now=NOW,
        entity_root=wiki_root,
        bad_doc_id_for_a="doc_cascade_target",
        audit_emit=captured.append,
    )
    assert result["action"] == "invalidate"
    assert captured[0]["mutation_type"] == T1_MUTATION_INVALIDATED


def test_dispatch_a_requires_entity_root():
    old, new_fact = _edge_corrected_invalidate("doc_x")
    with pytest.raises(ValueError, match="entity_root"):
        dispatch_contradiction(old, new_fact, now=NOW,
                                bad_doc_id_for_a="doc_x")


def test_dispatch_a_requires_bad_doc_id(tmp_path):
    old, new_fact = _edge_corrected_invalidate("doc_x")
    with pytest.raises(ValueError, match="bad_doc_id_for_a"):
        dispatch_contradiction(old, new_fact, now=NOW,
                                entity_root=tmp_path)


def test_dispatch_routes_b_to_supersede():
    """B_supersede dispatch (PR-T2.C wiring) calls supersede_edge +
    emits the new+old ids in the audit row. Replaces the prior
    NotImplementedError pin from PR-T2.B."""
    old, new_fact = _edge_world_changed_to_supersede()
    captured: list[dict] = []
    result = dispatch_contradiction(
        old, new_fact, now=NOW, audit_emit=captured.append,
    )
    assert result["action"] == "supersede"
    assert result["new_edge"]["id"].startswith("e_edge_")
    assert result["old_edge"] is old   # mutated in place
    assert old["mutation_type"] == "superseded"
    assert old["status"]["superseded_by"] == result["new_edge"]["id"]
    # Audit row carries both ids per PR-T2.C contract
    assert captured[0]["mutation_type"] == "superseded"
    assert captured[0]["new_edge_id"] == result["new_edge"]["id"]


def test_dispatch_unknown_label_raises_runtime_error(monkeypatch):
    """Defensive — if classify_contradiction is extended with a new
    label that the dispatcher doesn't know about, raise loudly."""
    import core.lifecycle.contradiction_router as mod
    monkeypatch.setattr(
        mod, "classify_contradiction",
        lambda *_a, **_kw: "X_unknown_label",
    )
    with pytest.raises(RuntimeError, match="unknown contradiction label"):
        dispatch_contradiction({}, {}, now=NOW)


# ─── Audit row contract ──────────────────────────────────────────


def test_audit_payload_carries_mutation_type_invalidated(tmp_path):
    """The replay primitive (reconstruct_view_at) skips edges with
    mutation_type=invalidated. The audit row carries the same label
    so a query of audit_log can correlate the cascade event to the
    filtered-out edge."""
    wiki_root = _load_fixture(tmp_path)
    captured: list[dict] = []
    route_a_invalidate(
        "doc_cascade_target", wiki_root, audit_emit=captured.append,
    )
    assert captured[0]["mutation_type"] == T1_MUTATION_INVALIDATED


def test_audit_payload_carries_cascade_counts(tmp_path):
    """Counts dict from cascade_remove_doc_from_sources is included
    in the audit row — operator can correlate audit timing to
    cascade scope without separate query."""
    wiki_root = _load_fixture(tmp_path)
    captured: list[dict] = []
    route_a_invalidate(
        "doc_cascade_target", wiki_root, audit_emit=captured.append,
    )
    audit = captured[0]
    for k in (
        "entities_scanned", "entities_touched",
        "relations_recomputed", "relations_dropped",
    ):
        assert k in audit, f"audit payload missing key: {k}"
        assert isinstance(audit[k], int)


# ─── PR-T2.C B-path tests ─────────────────────────────────────────


def test_t2_b_class_routes_to_supersede():
    """B_supersede dispatch invokes supersede_edge — the entry memo
    invariant `test_t2_b_class_routes_to_supersede` from §3."""
    old, new_fact = _edge_world_changed_to_supersede()

    captured: list[dict] = []
    result = route_b_supersede(
        old, new_fact, NOW, audit_emit=captured.append,
    )

    assert result["action"] == "supersede"
    new_edge = result["new_edge"]
    mutated_old = result["old_edge"]
    # PR-T7.A contract: new_edge gets a fresh synthetic id
    assert new_edge["id"].startswith("e_edge_")
    # old mutated in place — caller's reference picks up the change
    assert mutated_old is old
    # The two T7 invariants on old_edge
    assert mutated_old["status"]["active"] is False
    assert mutated_old["status"]["superseded_by"] == new_edge["id"]
    assert mutated_old["mutation_type"] == "superseded"


def test_supersede_audit_payload_carries_old_and_new_ids():
    """Entry memo invariant — audit row must include both edge ids
    so the T7 replay primitive can correlate the chain when
    querying audit history."""
    old, new_fact = _edge_world_changed_to_supersede()
    old["id"] = "e_edge_pre_existing_old"   # exercise the "old has an id" path

    captured: list[dict] = []
    route_b_supersede(old, new_fact, NOW, audit_emit=captured.append)

    audit = captured[0]
    assert audit["endpoint"] == "lifecycle:supersede"
    assert audit["mutation_type"] == "superseded"
    assert audit["old_edge_id"] == "e_edge_pre_existing_old"
    assert audit["new_edge_id"].startswith("e_edge_")
    assert audit["superseded_by"] == audit["new_edge_id"]
    assert audit["superseded_at"] == NOW.isoformat()


def test_supersede_dispatch_uses_now_as_supersede_ts():
    """dispatch_contradiction passes now as supersede_ts → the new
    edge's validity.from matches now.isoformat()."""
    old, new_fact = _edge_world_changed_to_supersede()
    result = dispatch_contradiction(old, new_fact, now=NOW)
    assert result["new_edge"]["validity"]["from"] == NOW.isoformat()


def test_supersede_preserves_old_edge_sources():
    """PR-T2.C invariant cross-check — supersede path does not touch
    old edge's sources (CASCADE invariant from PR-T7.B preserved
    through the router layer)."""
    old, new_fact = _edge_world_changed_to_supersede()
    old_sources_before = list(old["sources"])
    route_b_supersede(old, new_fact, NOW, audit_emit=lambda _: None)
    assert old["sources"] == old_sources_before, (
        "supersede must NOT touch old edge's sources (CASCADE-free "
        "invariant); only status + mutation_type"
    )


def test_supersede_chain_replayable_after_dispatch():
    """End-to-end: dispatch a B_supersede contradiction, then
    reconstruct_view_at to confirm the new edge is reachable from
    the old via the chain. Pins that the router-emitted chain is
    walkable by the T7 replay primitive."""
    old, new_fact = _edge_world_changed_to_supersede()
    old["id"] = "e_edge_v1"

    result = dispatch_contradiction(old, new_fact, now=NOW)
    new_edge = result["new_edge"]

    # Build an in-memory id→edge lookup (caller would normally
    # populate this from wiki frontmatter).
    edges = {"e_edge_v1": old, new_edge["id"]: new_edge}
    lookup = edges.get

    # Replay at a time after the supersede → returns the new edge
    later = datetime(2026, 12, 31, tzinfo=timezone.utc)
    view = reconstruct_view_at(old, lookup, later)
    assert view is not None
    assert view["id"] == new_edge["id"]


def test_dispatch_b_emits_audit_through_callback():
    """audit_emit callback is invoked exactly once on the B path."""
    old, new_fact = _edge_world_changed_to_supersede()
    captured: list[dict] = []
    dispatch_contradiction(
        old, new_fact, now=NOW, audit_emit=captured.append,
    )
    assert len(captured) == 1
    assert captured[0]["endpoint"] == "lifecycle:supersede"
