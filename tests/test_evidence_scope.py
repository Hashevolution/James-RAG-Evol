"""L.A contract tests for `core/reasoning/evidence_scope.py`.

Pins the extractor's 4-component decomposition + the
`JAMES_SCOPE_ROUTING` flag's default-off invariant. L.C will extend
the test suite with engine-loop wiring tests; L.A only locks the
shape so subsequent PRs land without surprise behavior shifts.

See `docs/handovers/v0.4-leo-evidence-scope-routing-track.md` for the
full L.0 → L.D phase plan.
"""
from __future__ import annotations

import pytest

from core.reasoning.evidence_scope import (
    ScopeBreakdown,
    compute_scope,
    scope_routing_enabled,
)


# ─── Empty / safety-net behavior ──────────────────────────────────


def test_empty_inputs_zero_scope():
    """LEO open Q #3 mode-gate safety net.

    `chat` / `self_evolve` paths bypass retrieval entirely, so if the
    extractor is ever invoked with empty inputs (e.g. by accident at
    L.C wiring time), the scope must be 0.0 — routing falls back to
    the legacy / small backend rather than escalating.
    """
    breakdown = compute_scope(docs=[], graph_context=[], graph_paths=[])
    assert breakdown.scope == 0.0
    assert breakdown.effective_k == 0.0
    assert breakdown.score_entropy == 0.0
    assert breakdown.graph_reach == 0.0
    assert breakdown.doc_spread == 0.0


# ─── Narrow / wide signature pins ─────────────────────────────────


def test_narrow_single_doc_low_scope():
    """One high-score doc, no graph activity — verbatim retrieval shape.

    Mirrors the V3'.e substitution arm (single chunk has the answer).
    Expected scope is small: low effective_k (1/8), zero entropy
    (single doc), zero graph reach, low spread (1 source / 1 doc = 1
    in the formula but other components dominate downward).
    """
    docs = [{"score": 0.9, "source": "single_doc.md"}]
    breakdown = compute_scope(docs=docs, graph_context=[], graph_paths=[])
    assert breakdown.scope <= 0.25, f"narrow scope expected ≤ 0.25, got {breakdown.scope}"
    assert breakdown.effective_k == pytest.approx(1 / 8)
    assert breakdown.score_entropy == 0.0
    assert breakdown.graph_reach == 0.0


def test_wide_multidoc_graph_high_scope():
    """8 docs above threshold + deep graph traversal — synthesis-heavy shape.

    Mirrors a multi-document multi-hop query that needs a larger
    backend. Expected scope is large (all 4 components fire).
    """
    docs = [
        {"score": 0.6 + i * 0.01, "source": f"doc_{i}.md"} for i in range(8)
    ]
    graph_context = [
        {"_dfs_depth": d, "name": f"e{d}_{i}"}
        for d in range(1, 5)
        for i in range(3)
    ]
    graph_paths = [f"path_{i}" for i in range(8)]
    breakdown = compute_scope(
        docs=docs,
        graph_context=graph_context,
        graph_paths=graph_paths,
    )
    assert breakdown.scope >= 0.7, f"wide scope expected ≥ 0.7, got {breakdown.scope}"
    assert breakdown.effective_k == 1.0
    assert breakdown.graph_reach == 1.0
    assert breakdown.doc_spread == 1.0


# ─── Individual component shape pins ──────────────────────────────


def test_score_entropy_peak_vs_flat():
    """Single-peak distribution lower than flat distribution."""
    peak_docs = [{"score": 0.9, "source": "a.md"}] + [
        {"score": 0.01, "source": f"b{i}.md"} for i in range(4)
    ]
    flat_docs = [{"score": 0.5, "source": f"c{i}.md"} for i in range(5)]

    peak_breakdown = compute_scope(
        docs=peak_docs, graph_context=[], graph_paths=[]
    )
    flat_breakdown = compute_scope(
        docs=flat_docs, graph_context=[], graph_paths=[]
    )

    assert peak_breakdown.score_entropy < flat_breakdown.score_entropy
    assert flat_breakdown.score_entropy == pytest.approx(1.0, abs=1e-9)


def test_doc_spread_same_source_vs_distinct():
    """All docs from one source → spread small; distinct sources → 1.0."""
    same = [{"score": 0.5, "source": "shared.md"} for _ in range(5)]
    distinct = [
        {"score": 0.5, "source": f"unique_{i}.md"} for i in range(5)
    ]

    same_breakdown = compute_scope(
        docs=same, graph_context=[], graph_paths=[]
    )
    distinct_breakdown = compute_scope(
        docs=distinct, graph_context=[], graph_paths=[]
    )

    assert same_breakdown.doc_spread == pytest.approx(1 / 5)
    assert distinct_breakdown.doc_spread == pytest.approx(1.0)


# ─── F5 floor fix — k=0 special case (2026-05-27) ─────────────────


def test_k_zero_with_filler_docs_drops_entropy_spread_contributions():
    """When no doc is above the relevance threshold, the aggregate
    `scope` ignores `score_entropy` and `doc_spread` (they describe
    the distribution of irrelevant chroma filler — see compute_scope
    F5 docstring section). graph_reach still counts.

    Regression pin: F4 acceptance run observed a ~0.40 floor from
    chroma always-returning-top_k. The fix drops that floor to ~0
    when no graph activity either.
    """
    # 5 docs all below the 0.45 relevance threshold, from distinct
    # sources (mirrors what chroma returns when no chunk truly matches)
    filler_docs = [
        {"score": 0.2, "source": f"low_{i}.md"} for i in range(5)
    ]
    breakdown = compute_scope(
        docs=filler_docs, graph_context=[], graph_paths=[],
    )
    # Aggregate must collapse — narrow rule (≤0.30) now fires
    assert breakdown.scope == 0.0
    # Raw components preserved for observability
    assert breakdown.effective_k == 0.0
    assert breakdown.score_entropy > 0.9, (
        "raw score_entropy still measured (was meaningful pre-fix); "
        "only the aggregate dropped its contribution"
    )
    assert breakdown.doc_spread == pytest.approx(1.0)


def test_k_zero_with_filler_docs_and_graph_only_uses_graph():
    """k=0 + non-empty graph → scope reflects only the graph_reach
    contribution. Other 3 components measured but excluded from
    aggregate."""
    filler_docs = [
        {"score": 0.2, "source": f"low_{i}.md"} for i in range(5)
    ]
    # max graph_reach: depth 4 + 12+ entities + 8+ paths
    graph_context = [
        {"_dfs_depth": d, "name": f"e{d}_{i}"}
        for d in range(1, 5)
        for i in range(3)
    ]
    graph_paths = [f"path_{i}" for i in range(8)]
    breakdown = compute_scope(
        docs=filler_docs,
        graph_context=graph_context,
        graph_paths=graph_paths,
    )
    # Expected: graph_reach=1.0, weighted 0.25 → scope ≈ 0.25
    assert breakdown.graph_reach == pytest.approx(1.0)
    assert breakdown.scope == pytest.approx(0.25, abs=1e-9)
    # Other raw components preserved
    assert breakdown.effective_k == 0.0
    assert breakdown.score_entropy > 0.9
    assert breakdown.doc_spread == pytest.approx(1.0)


def test_k_positive_uses_all_four_components_unchanged():
    """Regression pin — when at least one doc is above threshold,
    the original 4-component aggregate is unchanged (no surprise
    shifts from the F5 fix)."""
    # 1 doc above threshold + 4 below
    mixed = [{"score": 0.6, "source": "good.md"}] + [
        {"score": 0.2, "source": f"low_{i}.md"} for i in range(4)
    ]
    breakdown = compute_scope(
        docs=mixed, graph_context=[], graph_paths=[],
    )
    # ek = 1/8 = 0.125. With docs from 5 sources, ds = 5/5 = 1.0.
    # score_entropy > 0 (mixed distribution). graph contribution 0.
    expected_min = 0.125 * 0.35 + 1.0 * 0.20  # = 0.04 + 0.20 = 0.24
    assert breakdown.scope >= expected_min, (
        f"k>0 path must include doc_spread + entropy weights; "
        f"got {breakdown.scope}"
    )
    assert breakdown.effective_k == pytest.approx(1 / 8)


# ─── Flag parsing ─────────────────────────────────────────────────


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("JAMES_SCOPE_ROUTING", raising=False)
    assert scope_routing_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "TRUE", "Yes", "  on  "])
def test_flag_on_recognized(monkeypatch, value):
    monkeypatch.setenv("JAMES_SCOPE_ROUTING", value)
    assert scope_routing_enabled() is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "blah", "2"])
def test_flag_off_or_invalid_treated_as_off(monkeypatch, value):
    monkeypatch.setenv("JAMES_SCOPE_ROUTING", value)
    assert scope_routing_enabled() is False


# ─── Audit payload shape ──────────────────────────────────────────


def test_scope_breakdown_audit_payload_shape():
    """L.C `reason:route` row schema pin — 5 keys, all rounded to 4."""
    docs = [{"score": 0.7, "source": "a.md"}, {"score": 0.5, "source": "b.md"}]
    breakdown = compute_scope(docs=docs, graph_context=[], graph_paths=[])
    payload = breakdown.as_audit_payload()

    assert set(payload.keys()) == {
        "evidence_scope",
        "effective_k",
        "score_entropy",
        "graph_reach",
        "doc_spread",
    }
    for k, v in payload.items():
        assert isinstance(v, float), f"{k} must be float, got {type(v)}"
        # round(_, 4) guarantee — no value should have more than 4 decimals
        assert v == round(v, 4), f"{k}={v} not rounded to 4 decimals"


# ─── Determinism pin ──────────────────────────────────────────────


def test_compute_scope_pure_deterministic():
    """Same inputs → identical output across repeated calls."""
    docs = [{"score": 0.65, "source": "a.md"}, {"score": 0.55, "source": "b.md"}]
    graph_context = [{"_dfs_depth": 2, "name": "x"}]
    graph_paths = ["a→b"]

    first = compute_scope(
        docs=docs, graph_context=graph_context, graph_paths=graph_paths
    )
    for _ in range(100):
        again = compute_scope(
            docs=docs, graph_context=graph_context, graph_paths=graph_paths
        )
        assert again == first


# ─── ScopeBreakdown is a frozen dataclass ─────────────────────────


def test_scope_breakdown_is_frozen():
    """Defends against accidental mutation in downstream call sites."""
    breakdown = ScopeBreakdown(
        effective_k=0.5,
        score_entropy=0.5,
        graph_reach=0.5,
        doc_spread=0.5,
        scope=0.5,
    )
    with pytest.raises((AttributeError, Exception)):
        breakdown.scope = 0.9  # type: ignore[misc]
