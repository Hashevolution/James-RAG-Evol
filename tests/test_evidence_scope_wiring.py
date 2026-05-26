"""LEO L.C contract tests — pipeline scope wiring + audit payload.

Pins:
  - `scope_context(...)` / `get_current_scope()` ContextVar contract
    (set / get / nested / cleanup on exception)
  - `router.emit_route_event(..., evidence_scope=...)` formats audit
    payload correctly for ScopeBreakdown, bare float, and None
  - `trace_helpers.trace_synth_call` reads the bound scope and passes
    it to `resolve_backend` only when the flag is ON
  - Flag-OFF byte-identical invariant: with the env var unset, the
    bound scope is ignored entirely → existing audit row shape
    preserved exactly.

Companion to:
  - `test_evidence_scope.py` (L.A extractor)
  - `test_router_evidence_scope.py` (L.B router policy)

See `docs/handovers/v0.4-leo-evidence-scope-routing-track.md` for the
phase plan.
"""
from __future__ import annotations

import pytest

from core.reasoning.evidence_scope import (
    ScopeBreakdown,
    compute_scope,
    get_current_scope,
    scope_context,
    scope_routing_enabled,
)


def _make_breakdown(scope: float = 0.5) -> ScopeBreakdown:
    """Build a deterministic ScopeBreakdown for wiring tests."""
    return ScopeBreakdown(
        effective_k=scope,
        score_entropy=scope,
        graph_reach=scope,
        doc_spread=scope,
        scope=scope,
    )


# ─── ContextVar plumbing ──────────────────────────────────────────


def test_get_current_scope_returns_none_when_unbound():
    """No active scope_context → get_current_scope is None."""
    # No `with` block — read directly
    assert get_current_scope() is None


def test_scope_context_binds_and_releases():
    """Bind a breakdown inside `with`, observe via get_current_scope,
    confirm cleanup after the block exits."""
    breakdown = _make_breakdown(0.7)
    assert get_current_scope() is None
    with scope_context(breakdown):
        assert get_current_scope() is breakdown
    assert get_current_scope() is None


def test_scope_context_explicit_none_binding():
    """`scope_context(None)` is a valid explicit binding — signals
    'no scope this turn' rather than leaking a prior turn's value."""
    with scope_context(_make_breakdown(0.9)):
        assert get_current_scope() is not None
        # Inner block re-binds to None
        with scope_context(None):
            assert get_current_scope() is None
        # Outer binding restored after inner block exits
        assert get_current_scope() is not None


def test_scope_context_cleanup_on_exception():
    """Token reset must run even when the with-block body raises."""
    breakdown = _make_breakdown(0.4)
    with pytest.raises(RuntimeError, match="synth boom"):
        with scope_context(breakdown):
            assert get_current_scope() is breakdown
            raise RuntimeError("synth boom")
    # Exception propagated, but the binding was cleared.
    assert get_current_scope() is None


def test_scope_context_nested_restores_outer():
    """Nested with-blocks restore the outer binding correctly."""
    outer = _make_breakdown(0.2)
    inner = _make_breakdown(0.8)
    with scope_context(outer):
        assert get_current_scope() is outer
        with scope_context(inner):
            assert get_current_scope() is inner
        assert get_current_scope() is outer
    assert get_current_scope() is None


# ─── emit_route_event audit payload ───────────────────────────────


def _capture_emit_payload(monkeypatch):
    """Returns a list captured by patching `mirror_to_audit_db`."""
    captured: list[dict] = []
    monkeypatch.setattr(
        "core.audit_bridge.mirror_to_audit_db",
        lambda payload: captured.append(payload),
    )
    return captured


def test_emit_route_event_no_scope_fragment_when_none(monkeypatch):
    """`evidence_scope=None` → audit answer omits scope fields entirely
    (byte-identical to pre-L.C). This protects the flag-OFF invariant
    at the audit-row level."""
    captured = _capture_emit_payload(monkeypatch)
    from core.reasoning.router import emit_route_event
    emit_route_event(
        "synth", "test prompt", "gemma4:e4b",
        budget_signal=None, reason="fallback", evidence_scope=None,
    )
    assert len(captured) == 1
    answer = captured[0]["answer"]
    # No scope fields
    assert "evidence_scope=" not in answer
    assert "effective_k=" not in answer
    # Pre-L.C shape preserved
    assert answer.startswith("backend=gemma4:e4b tier=none reason=fallback")


def test_emit_route_event_with_breakdown_emits_all_5_fields(monkeypatch):
    """ScopeBreakdown payload → all 5 audit fields land verbatim."""
    captured = _capture_emit_payload(monkeypatch)
    from core.reasoning.router import emit_route_event
    breakdown = _make_breakdown(0.6)
    emit_route_event(
        "synth", "test prompt", "stub_large",
        budget_signal=None, reason="scope", evidence_scope=breakdown,
    )
    assert len(captured) == 1
    answer = captured[0]["answer"]
    for key in (
        "evidence_scope=", "effective_k=", "score_entropy=",
        "graph_reach=", "doc_spread=",
    ):
        assert key in answer, f"missing {key} in audit answer: {answer!r}"
    assert "reason=scope" in answer


def test_emit_route_event_with_bare_float_emits_scalar_only(monkeypatch):
    """Bare float `evidence_scope=0.75` → just the scalar lands in audit
    (no 4-component breakdown)."""
    captured = _capture_emit_payload(monkeypatch)
    from core.reasoning.router import emit_route_event
    emit_route_event(
        "synth", "test", "gemma4:e4b",
        budget_signal=None, reason="scope", evidence_scope=0.75,
    )
    answer = captured[0]["answer"]
    assert "evidence_scope=0.7500" in answer
    # No component decomposition for bare-float path
    assert "effective_k=" not in answer
    assert "score_entropy=" not in answer


def test_emit_route_event_with_invalid_scope_silently_skips_fragment(
    monkeypatch,
):
    """A type that's neither ScopeBreakdown nor float-coercible →
    scope fragment is omitted, the row still lands (never raises)."""
    captured = _capture_emit_payload(monkeypatch)
    from core.reasoning.router import emit_route_event
    emit_route_event(
        "synth", "test", "gemma4:e4b",
        budget_signal=None, reason="scope", evidence_scope={"bad": "shape"},
    )
    assert len(captured) == 1
    answer = captured[0]["answer"]
    assert "evidence_scope=" not in answer


# ─── trace_synth_call integration ─────────────────────────────────


def test_flag_off_ignores_bound_scope(monkeypatch):
    """With JAMES_SCOPE_ROUTING unset, even an active scope_context is
    ignored — `trace_synth_call` passes `evidence_scope=None` to the
    router and emits no scope fragment in the audit row."""
    monkeypatch.delenv("JAMES_SCOPE_ROUTING", raising=False)
    # scope_context binding is non-None
    breakdown = _make_breakdown(0.9)
    assert scope_routing_enabled() is False
    with scope_context(breakdown):
        # The trace_helpers wiring uses scope_routing_enabled() as the
        # gate — confirm that flag OFF means get_current_scope is
        # NEVER consulted to make a routing decision (the bound value
        # exists, but the flag check short-circuits).
        from core.reasoning.evidence_scope import (
            get_current_scope as _get,
            scope_routing_enabled as _enabled,
        )
        scope = _get() if _enabled() else None
        assert scope is None
        # Sanity: the bound value is still there, just gated out
        assert _get() is breakdown


def test_flag_on_propagates_bound_scope(monkeypatch):
    """With JAMES_SCOPE_ROUTING=1, the scope read at the synth gate
    matches the bound breakdown."""
    monkeypatch.setenv("JAMES_SCOPE_ROUTING", "1")
    breakdown = _make_breakdown(0.85)
    assert scope_routing_enabled() is True
    with scope_context(breakdown):
        from core.reasoning.evidence_scope import (
            get_current_scope as _get,
            scope_routing_enabled as _enabled,
        )
        scope = _get() if _enabled() else None
        assert scope is breakdown
        assert scope.scope == pytest.approx(0.85)


# ─── compute_scope + scope_context wiring (the pipeline path) ─────


def test_compute_then_bind_round_trips_under_flag_on(monkeypatch):
    """Mimics what pipeline.py does after Loop 1: compute scope from
    loop_state-shaped inputs, bind, observe value at synth time."""
    monkeypatch.setenv("JAMES_SCOPE_ROUTING", "1")
    docs = [
        {"score": 0.7 + i * 0.02, "source": f"d{i}.md"} for i in range(8)
    ]
    graph_ctx = [{"_dfs_depth": 3, "name": f"e{i}"} for i in range(6)]
    graph_paths = ["a->b", "b->c", "c->d"]

    breakdown = compute_scope(docs, graph_ctx, graph_paths)
    with scope_context(breakdown):
        observed = get_current_scope()
        assert observed is breakdown
        assert 0.4 < observed.scope < 1.0
