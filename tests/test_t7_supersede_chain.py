"""v0.4 Sprint 5 PR-T7.A — contract tests for the supersede chain.

Three invariants required by the entry memo §"PR-T7.A":

  1. test_supersede_preserves_old_sources — no CASCADE side effect
     (sources stay on the old edge after supersede)
  2. test_supersede_chain_walks_to_active — walker follows the
     chain through all superseded links to the active head
  3. test_supersede_chain_acyclic — walker raises on a cycle
     instead of looping forever

Plus a small ring of reconstruct_view_at + cross-mutation-type
exclusivity + max-chain-length guard tests.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.lifecycle.schema import (  # noqa: E402
    T1_MUTATION_ACTIVE,
    T1_MUTATION_EXPIRED,
    T1_MUTATION_INVALIDATED,
    T1_MUTATION_SUPERSEDED,
)
from core.lifecycle.supersede_chain import (  # noqa: E402
    _ensure_edge_id,
    reconstruct_view_at,
    supersede_edge,
    walk_supersede_chain,
)


# Reference "now" — all supersede timestamps anchor here.
NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def _src(doc_id: str = "doc_x", weight: float = 0.9) -> dict:
    """Minimal v0.4 source dict."""
    return {
        "doc_id":      doc_id,
        "role":        "primary",
        "ts":          "2026-05-01T00:00:00+00:00",
        "weight":      weight,
        "valid_from":  None,
        "valid_until": None,
    }


def _edge(
    *,
    target: str = "Target",
    sources: list | None = None,
    mutation_type: str = T1_MUTATION_ACTIVE,
    status: dict | None = None,
    validity: dict | None = None,
    edge_id: str | None = None,
) -> dict:
    """Build a minimal v0.4-shaped edge dict."""
    out = {
        "confidence":    0.9,
        "label":         "관련",
        "target":        target,
        "target_id":     "e_concept_x",
        "type":          "RELATED_TO",
        "sources":       sources or [_src()],
        "validity":      validity or {"from": None, "to": None},
        "status":        status or {
            "active":          mutation_type == T1_MUTATION_ACTIVE,
            "superseded_by":   None,
            "superseded_at":   None,
        },
        "mutation_type": mutation_type,
    }
    if edge_id:
        out["id"] = edge_id
    return out


def _make_lookup(edges_by_id: dict[str, dict]):
    """Build the id→edge resolver the walker expects."""
    return lambda eid: edges_by_id.get(eid)


# ─── #1 — sources preserved on supersede ──────────────────────────


def test_supersede_preserves_old_sources():
    """Old edge keeps its sources after supersede. The whole point
    of T7 (vs Layer 3 CASCADE which removes sources) is preservation
    for replay."""
    old_sources = [_src("doc_a"), _src("doc_b")]
    old = _edge(sources=old_sources, target="OldTarget")
    new_fact = _edge(sources=[_src("doc_new")], target="NewTarget")

    new_edge, mutated_old = supersede_edge(old, new_fact, NOW)

    assert mutated_old["sources"] == old_sources, (
        "supersede must NOT touch sources on the old edge — that's "
        "CASCADE's job"
    )
    # Old edge mutation surface is exactly two fields + the chain link
    assert mutated_old["status"]["active"] is False
    assert mutated_old["status"]["superseded_by"] == new_edge["id"]
    assert mutated_old["status"]["superseded_at"] == NOW.isoformat()
    assert mutated_old["mutation_type"] == T1_MUTATION_SUPERSEDED


def test_supersede_returns_old_dict_by_reference():
    """Caller likely holds a list reference (frontmatter relations
    list) — old_edge must be mutated in place, not replaced."""
    old = _edge(target="OldTarget")
    list_holding_old = [old]
    new_fact = _edge(target="NewTarget")

    _, mutated_old = supersede_edge(old, new_fact, NOW)

    assert mutated_old is old, (
        "supersede must mutate old_edge in place so the caller's "
        "list reference picks up the change"
    )
    assert list_holding_old[0] is old
    assert list_holding_old[0]["mutation_type"] == T1_MUTATION_SUPERSEDED


def test_new_edge_gets_fresh_id_and_validity_from():
    """new_edge gets a synthetic id + validity.from=supersede_ts so
    the chain ordering is well-defined for replay."""
    old = _edge(target="OldTarget")
    new_fact = _edge(target="NewTarget")

    new_edge, _ = supersede_edge(old, new_fact, NOW)

    assert new_edge["id"].startswith("e_edge_")
    assert len(new_edge["id"]) >= len("e_edge_") + 8
    assert new_edge["validity"]["from"] == NOW.isoformat()


# ─── #2 — walker follows chain ────────────────────────────────────


def test_supersede_chain_walks_to_active():
    """Build a 3-link chain (head → mid → active), walk from each
    link, verify walker returns the correct ordered slice."""
    active = _edge(target="V3", edge_id="e_edge_v3")
    mid    = _edge(target="V2", edge_id="e_edge_v2")
    head   = _edge(target="V1", edge_id="e_edge_v1")

    # Wire chain: head → mid → active
    head["status"]["superseded_by"] = "e_edge_v2"
    head["status"]["superseded_at"] = NOW.isoformat()
    head["status"]["active"] = False
    head["mutation_type"] = T1_MUTATION_SUPERSEDED

    mid["status"]["superseded_by"] = "e_edge_v3"
    mid["status"]["superseded_at"] = (NOW + timedelta(days=1)).isoformat()
    mid["status"]["active"] = False
    mid["mutation_type"] = T1_MUTATION_SUPERSEDED

    lookup = _make_lookup({
        "e_edge_v1": head,
        "e_edge_v2": mid,
        "e_edge_v3": active,
    })

    # From head — walks the whole chain
    chain_from_head = walk_supersede_chain(head, lookup)
    assert [e["target"] for e in chain_from_head] == ["V1", "V2", "V3"]

    # From mid — walks forward only
    chain_from_mid = walk_supersede_chain(mid, lookup)
    assert [e["target"] for e in chain_from_mid] == ["V2", "V3"]

    # From the active head — single-element list
    chain_from_active = walk_supersede_chain(active, lookup)
    assert chain_from_active == [active]


def test_supersede_chain_handles_unsuperseded_edge():
    """Single-edge chain (no supersede) returns just the edge."""
    only = _edge(target="Only", edge_id="e_edge_only")
    lookup = _make_lookup({"e_edge_only": only})
    chain = walk_supersede_chain(only, lookup)
    assert chain == [only]


def test_supersede_chain_handles_dangling_pointer():
    """superseded_by points at an id the lookup can't resolve →
    walker returns what it has so far (caller's wiki snapshot may
    legitimately lack the next link if the next entity hasn't been
    loaded yet)."""
    head = _edge(target="V1", edge_id="e_edge_v1")
    head["status"]["superseded_by"] = "e_edge_v_missing"
    head["status"]["superseded_at"] = NOW.isoformat()
    head["status"]["active"] = False
    head["mutation_type"] = T1_MUTATION_SUPERSEDED

    lookup = _make_lookup({"e_edge_v1": head})  # missing target
    chain = walk_supersede_chain(head, lookup)
    assert chain == [head]


# ─── #3 — cycle detection ─────────────────────────────────────────


def test_supersede_chain_acyclic():
    """A cyclic chain (v1→v2→v1) must raise on walk. Cycles are an
    insertion bug that supersede_edge prevents, but the walker
    defends against externally-mutated chains too."""
    v1 = _edge(target="V1", edge_id="e_edge_v1")
    v2 = _edge(target="V2", edge_id="e_edge_v2")
    v1["status"]["superseded_by"] = "e_edge_v2"
    v1["status"]["superseded_at"] = NOW.isoformat()
    v1["status"]["active"] = False
    v1["mutation_type"] = T1_MUTATION_SUPERSEDED

    v2["status"]["superseded_by"] = "e_edge_v1"   # cycle!
    v2["status"]["superseded_at"] = NOW.isoformat()
    v2["status"]["active"] = False
    v2["mutation_type"] = T1_MUTATION_SUPERSEDED

    lookup = _make_lookup({"e_edge_v1": v1, "e_edge_v2": v2})

    with pytest.raises(ValueError, match="cycle"):
        walk_supersede_chain(v1, lookup)


def test_supersede_chain_max_length_cap():
    """Pathological linear chain longer than _MAX_CHAIN_LENGTH
    raises rather than spinning forever. We don't actually build
    1025 edges; we monkey-patch the cap on the module to a small
    number and verify the limit fires."""
    import core.lifecycle.supersede_chain as mod
    original = mod._MAX_CHAIN_LENGTH
    mod._MAX_CHAIN_LENGTH = 2
    try:
        v1 = _edge(target="V1", edge_id="e_edge_v1")
        v2 = _edge(target="V2", edge_id="e_edge_v2")
        v3 = _edge(target="V3", edge_id="e_edge_v3")
        v4 = _edge(target="V4", edge_id="e_edge_v4")
        for prev, nxt in [(v1, "e_edge_v2"), (v2, "e_edge_v3"), (v3, "e_edge_v4")]:
            prev["status"]["superseded_by"] = nxt
            prev["status"]["superseded_at"] = NOW.isoformat()
            prev["status"]["active"] = False
            prev["mutation_type"] = T1_MUTATION_SUPERSEDED

        lookup = _make_lookup({
            "e_edge_v1": v1, "e_edge_v2": v2,
            "e_edge_v3": v3, "e_edge_v4": v4,
        })
        with pytest.raises(ValueError, match="exceeded max length"):
            walk_supersede_chain(v1, lookup)
    finally:
        mod._MAX_CHAIN_LENGTH = original


# ─── reconstruct_view_at — replay primitive ───────────────────────


def test_reconstruct_view_at_returns_active_for_current_time():
    """3-link chain — replay at the current time picks the active head."""
    t0 = NOW - timedelta(days=10)
    t1 = NOW - timedelta(days=5)
    t2 = NOW
    head = _edge(
        target="V1", edge_id="e_edge_v1",
        validity={"from": t0.isoformat(), "to": t1.isoformat()},
        mutation_type=T1_MUTATION_SUPERSEDED,
        status={"active": False, "superseded_by": "e_edge_v2",
                "superseded_at": t1.isoformat()},
    )
    mid  = _edge(
        target="V2", edge_id="e_edge_v2",
        validity={"from": t1.isoformat(), "to": t2.isoformat()},
        mutation_type=T1_MUTATION_SUPERSEDED,
        status={"active": False, "superseded_by": "e_edge_v3",
                "superseded_at": t2.isoformat()},
    )
    active = _edge(
        target="V3", edge_id="e_edge_v3",
        validity={"from": t2.isoformat(), "to": None},
    )
    lookup = _make_lookup({
        "e_edge_v1": head, "e_edge_v2": mid, "e_edge_v3": active,
    })

    # At t > t2 → active head
    got = reconstruct_view_at(head, lookup, NOW + timedelta(days=1))
    assert got is active

    # At t between t1 and t2 → mid
    got = reconstruct_view_at(head, lookup, NOW - timedelta(days=3))
    assert got is mid

    # At t between t0 and t1 → head
    got = reconstruct_view_at(head, lookup, NOW - timedelta(days=7))
    assert got is head


def test_reconstruct_view_at_skips_invalidated():
    """An edge with mutation_type=invalidated is gone for replay —
    CASCADE deletions are not visible in reconstructed history.
    Supersede chain members are visible."""
    t0 = NOW - timedelta(days=10)
    t1 = NOW
    invalidated = _edge(
        target="V1", edge_id="e_edge_v1",
        validity={"from": t0.isoformat(), "to": None},
        mutation_type=T1_MUTATION_INVALIDATED,
        status={"active": False, "superseded_by": None,
                "superseded_at": None},
    )
    # Standalone edge — no chain — but reconstruct_view_at should
    # walk it (single-link chain) and find no match because the
    # only link is invalidated.
    lookup = _make_lookup({"e_edge_v1": invalidated})
    got = reconstruct_view_at(invalidated, lookup, t1)
    assert got is None


def test_reconstruct_view_at_returns_none_when_no_window_matches():
    """All chain links' validity windows are in the past — query at
    an even-earlier time returns None."""
    t_past = NOW - timedelta(days=100)
    only = _edge(
        target="Only", edge_id="e_edge_only",
        validity={"from": NOW.isoformat(), "to": None},
    )
    lookup = _make_lookup({"e_edge_only": only})
    got = reconstruct_view_at(only, lookup, t_past)
    assert got is None


# ─── Cross-mutation-type guards ──────────────────────────────────


def test_supersede_overwrites_expired_status():
    """An edge already marked expired (T1 EVENT) can still be
    superseded — supersede wins because supersede records WHY it's
    inactive (the chain link), expiration just records WHEN.

    This matches the entry memo §3 invariant: EVENT operations are
    composable, only CASCADE is destructive."""
    expired = _edge(target="V1", edge_id="e_edge_v1",
                    mutation_type=T1_MUTATION_EXPIRED,
                    status={"active": False, "superseded_by": None,
                            "superseded_at": None})
    new_fact = _edge(target="V2")

    new_edge, mutated_old = supersede_edge(expired, new_fact, NOW)

    assert mutated_old["mutation_type"] == T1_MUTATION_SUPERSEDED
    assert mutated_old["status"]["superseded_by"] == new_edge["id"]


def test_supersede_rejects_invalid_inputs():
    """Type guards on the three args."""
    with pytest.raises(ValueError, match="old_edge"):
        supersede_edge("not a dict", _edge(), NOW)
    with pytest.raises(ValueError, match="new_fact"):
        supersede_edge(_edge(), "not a dict", NOW)
    with pytest.raises(ValueError, match="supersede_ts"):
        supersede_edge(_edge(), _edge(), "not a datetime")


# ─── _ensure_edge_id helper ──────────────────────────────────────


def test_ensure_edge_id_assigns_when_missing():
    edge = {}
    eid = _ensure_edge_id(edge)
    assert eid.startswith("e_edge_")
    assert edge["id"] == eid


def test_ensure_edge_id_preserves_existing():
    edge = {"id": "e_edge_existing"}
    eid = _ensure_edge_id(edge)
    assert eid == "e_edge_existing"
    assert edge["id"] == "e_edge_existing"
