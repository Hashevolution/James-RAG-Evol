"""LRB Phase A smoke tests — fixture determinism + adapter sanity +
scorer math."""
from __future__ import annotations

from pathlib import Path


from eval.external.lrb.adapters import (
    JamesValidityAdapter, VanillaRagAdapter)
from eval.external.lrb.driver import (
    fixture_sha, load_scenario, run_sut, score_run)
from eval.external.lrb.scorer import (
    _precision_at_k, _recall_at_k, _temporal_accuracy)

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "eval" / "external" / "_fixtures" / "lrb" / \
    "scenario_S1_quarterly.json"


# ── Fixture determinism ────────────────────────────────────────────


def test_fixture_exists_and_has_locked_shape():
    sc = load_scenario(FIXTURE)
    assert sc["scenario"] == "LRB-S1"
    assert sc["name"] == "lifecycle-quarterly"
    assert len(sc["initial_corpus"]) == 100
    assert 150 <= len(sc["events"]) <= 250  # prereg-tolerant range
    assert len(sc["queries"]) == 60
    assert sc["timestamps"] == ["T=0", "T=6w", "T=12w"]


def test_fixture_sha_is_stable():
    sha1 = fixture_sha(FIXTURE)
    sha2 = fixture_sha(FIXTURE)
    assert sha1 == sha2
    assert len(sha1) == 64


def test_gold_doc_ids_all_reachable():
    sc = load_scenario(FIXTURE)
    reachable = {d["doc_id"] for d in sc["initial_corpus"]}
    for ev in sc["events"]:
        if ev["op"] in ("INGEST",):
            reachable.add(ev["args"]["doc_id"])
        if ev["op"] == "SUPERSEDE":
            reachable.add(ev["args"]["new_doc_id"])
    for q in sc["queries"]:
        for ts, gold in q["gold"].items():
            for g in gold:
                assert g in reachable, (q["query_id"], ts, g)


# ── Scorer math ────────────────────────────────────────────────────


def test_recall_full_hit():
    assert _recall_at_k(["a", "b", "c"], ["a"], 5) == 1.0


def test_recall_partial():
    assert _recall_at_k(["a", "x"], ["a", "b"], 5) == 0.5


def test_recall_empty_gold_no_retrieval_is_1():
    assert _recall_at_k([], [], 5) == 1.0


def test_recall_empty_gold_with_retrieval_is_0():
    assert _recall_at_k(["a"], [], 5) == 0.0


def test_precision_at_k():
    assert _precision_at_k(["a", "b", "c", "d", "e"], ["a", "b"], 5) == 0.4


def test_temporal_accuracy_strict():
    assert _temporal_accuracy(["a", "b"], ["a", "b"], 10) == 1.0
    assert _temporal_accuracy(["a"], ["a", "b"], 10) == 0.0


# ── Adapter behavioural sanity ─────────────────────────────────────


def test_vanilla_retains_superseded_doc():
    a = VanillaRagAdapter()
    a.ingest("d1", "Department X", "Director Alpha leads Department X", 0)
    a.supersede("d1", "d1.v2", "Department X",
                "Director Beta leads Department X", 5)
    # Both d1 and d1.v2 should be retrievable; vanilla doesn't know d1
    # is stale.
    hits = a.retrieve("Director of Department X", k=5, t_week=10)
    assert "d1" in hits
    assert "d1.v2" in hits


def test_james_filters_stale_at_post_supersede_time():
    a = JamesValidityAdapter()
    a.ingest("d1", "Department X", "Director Alpha leads Department X", 0)
    a.supersede("d1", "d1.v2", "Department X",
                "Director Beta leads Department X", 5)
    # At t=10 (post-supersede), d1 should be filtered, d1.v2 returned
    hits_post = a.retrieve("Director of Department X", k=5, t_week=10)
    assert "d1" not in hits_post
    assert "d1.v2" in hits_post
    # At t=2 (pre-supersede), d1 returned, d1.v2 not yet valid
    hits_pre = a.retrieve("Director of Department X", k=5, t_week=2)
    assert "d1" in hits_pre
    assert "d1.v2" not in hits_pre


def test_james_handles_delete():
    a = JamesValidityAdapter()
    a.ingest("d1", "Project A", "Project A is led by Alpha", 0)
    a.delete("d1", 5)
    hits_post = a.retrieve("Project A", k=5, t_week=10)
    assert "d1" not in hits_post
    hits_pre = a.retrieve("Project A", k=5, t_week=2)
    assert "d1" in hits_pre


# ── End-to-end smoke per SUT ───────────────────────────────────────


def test_run_vanilla_emits_180_rows():
    sc = load_scenario(FIXTURE)
    sha = fixture_sha(FIXTURE)
    r = run_sut(VanillaRagAdapter, sc, sha, sut_name="vanilla")
    assert len(r.per_query) == 180
    axes = score_run(r)
    assert "overall" in axes and "per_timestamp" in axes
    assert axes["overall"]["n"] == 180


def test_run_james_emits_180_rows():
    sc = load_scenario(FIXTURE)
    sha = fixture_sha(FIXTURE)
    r = run_sut(JamesValidityAdapter, sc, sha, sut_name="james")
    assert len(r.per_query) == 180
    axes = score_run(r)
    assert axes["overall"]["n"] == 180


def test_james_beats_vanilla_on_temporal_accuracy():
    """The point of LRB: validity filter must improve temporal
    accuracy. If this fails the smoke is invalid."""
    sc = load_scenario(FIXTURE)
    sha = fixture_sha(FIXTURE)
    v_axes = score_run(run_sut(VanillaRagAdapter, sc, sha, sut_name="v"))
    j_axes = score_run(run_sut(JamesValidityAdapter, sc, sha, sut_name="j"))
    # James should be >= Vanilla on temporal_accuracy (the locked
    # mechanism — if equal, smoke is uninformative; if J<V the test
    # surfaces a regression before report).
    assert (j_axes["overall"]["temporal_accuracy"]
            >= v_axes["overall"]["temporal_accuracy"])
