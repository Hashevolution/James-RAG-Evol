"""LRB Phase B smoke tests — S2 fixture + 3-SUT × time-travel."""
from __future__ import annotations

from pathlib import Path


from eval.external.lrb.adapters import (
    JamesValidityAdapter, NaiveSupersedeAdapter, VanillaRagAdapter)
from eval.external.lrb.driver import fixture_sha, load_scenario
from eval.external.lrb.driver_phase_b import run_sut_phase_b, score_run

from tests._lrb_fixtures import ensure_scenario

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_S2 = ensure_scenario("S2")


def test_s2_fixture_shape():
    sc = load_scenario(FIXTURE_S2)
    assert sc["scenario"] == "LRB-S2"
    assert len(sc["initial_corpus"]) == 200
    assert 200 <= len(sc["events"]) <= 600
    assert len(sc["queries"]) == 80
    # 4 query-types
    cats = {q["category"].split("-")[0] for q in sc["queries"]}
    assert "current" in cats or "current-director" in {
        q["category"] for q in sc["queries"]}
    # query_time / valid_time on each query
    for q in sc["queries"]:
        assert "query_time" in q and "valid_time" in q
        assert q["query_time"] >= q["valid_time"]


def test_retrieve_at_interface_present_on_all_adapters():
    for cls in (VanillaRagAdapter, NaiveSupersedeAdapter,
                JamesValidityAdapter):
        a = cls()
        assert hasattr(a, "retrieve_at")


def test_phase_b_run_all_3_suts_emit_80_rows():
    sc = load_scenario(FIXTURE_S2)
    sha = fixture_sha(FIXTURE_S2)
    for cls, name in [
        (VanillaRagAdapter, "v"),
        (NaiveSupersedeAdapter, "n"),
        (JamesValidityAdapter, "j"),
    ]:
        r = run_sut_phase_b(cls, sc, sha, sut_name=name)
        assert len(r.per_query) == 80
        axes = score_run(r)
        assert axes["overall"]["n"] == 80


def test_james_beats_naive_on_time_travel_axis():
    """The Phase B-specific assertion: validity-window must add value
    on time-travel queries beyond naive supersede-aware RAG."""
    sc = load_scenario(FIXTURE_S2)
    sha = fixture_sha(FIXTURE_S2)
    n_axes = score_run(run_sut_phase_b(
        NaiveSupersedeAdapter, sc, sha, sut_name="n"))
    j_axes = score_run(run_sut_phase_b(
        JamesValidityAdapter, sc, sha, sut_name="j"))
    # JAMES must be strictly greater on temporal_accuracy
    assert (j_axes["overall"]["temporal_accuracy"]
            > n_axes["overall"]["temporal_accuracy"])
    # And on R@1
    assert (j_axes["overall"]["exploratory"]["R@1"]
            > n_axes["overall"]["exploratory"]["R@1"])


def test_naive_beats_vanilla_on_current_axis():
    """Phase A finding preserved in Phase B."""
    sc = load_scenario(FIXTURE_S2)
    sha = fixture_sha(FIXTURE_S2)
    v_axes = score_run(run_sut_phase_b(
        VanillaRagAdapter, sc, sha, sut_name="v"))
    n_axes = score_run(run_sut_phase_b(
        NaiveSupersedeAdapter, sc, sha, sut_name="n"))
    # On S2 R@1 (which is the UX-critical axis): Naive must beat Vanilla
    assert (n_axes["overall"]["exploratory"]["R@1"]
            > v_axes["overall"]["exploratory"]["R@1"])
