"""Smoke tests for `scripts/research/local_vs_cloud_paired.py`.

This is a measurement harness — its value is the *data* an operator
runs against it produce, not unit-level correctness. But the harness
itself has logic worth pinning:

  • blinded A/B order is deterministic from (query_id, run_idx) — same
    pair → same slot, so re-runs are reproducible
  • per-question majority across n runs is well-defined under ties
  • aggregate computes the §4.1 delta correctly
  • caveat block is in the output JSON (mandatory per design memo §4.1)
  • candidate error → judge skipped, verdict marked INCORRECT, harness
    keeps running (one bad query doesn't kill the run)

We don't spawn real Claude or Ollama — both backends are
monkey-patched.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "research"))


@pytest.fixture
def harness():
    """Re-import the harness module fresh per test so monkey-patches
    don't bleed."""
    if "local_vs_cloud_paired" in sys.modules:
        del sys.modules["local_vs_cloud_paired"]
    return importlib.import_module("local_vs_cloud_paired")


# ─── Blinded A/B determinism ────────────────────────────────────────


def test_blind_order_deterministic_same_query_run_pair(harness, monkeypatch):
    """Same (id, run_idx) → same a_is_local. Re-runs reproduce the slot
    assignment, so a judge re-grading the same row sees the same A/B."""
    monkeypatch.setattr(harness, "call_local",
                        lambda p, *, model, timeout=180, local_backend='ollama': "LOCAL_REPLY")
    monkeypatch.setattr(harness, "call_cloud_via_abstraction",
                        lambda p, *, timeout=180: "CLOUD_REPLY")
    monkeypatch.setattr(harness, "judge",
                        lambda q, e, a, b, *, timeout=180: ("CORRECT", "CORRECT"))

    q = {"id": "q-001", "text": "Q?", "question_type": "inference_query",
         "expected_path": {"nodes": ["t1"]}}

    r0 = harness.run_one_query(q, "evidence", local_model="m", run_idx=0, timeout=10)
    r0b = harness.run_one_query(q, "evidence", local_model="m", run_idx=0, timeout=10)
    assert r0["a_is_local"] == r0b["a_is_local"]


def test_blind_order_changes_between_runs(harness, monkeypatch):
    """Different run_idx → different blind seed → can flip slot."""
    monkeypatch.setattr(harness, "call_local",
                        lambda p, *, model, timeout=180, local_backend='ollama': "LOCAL_REPLY")
    monkeypatch.setattr(harness, "call_cloud_via_abstraction",
                        lambda p, *, timeout=180: "CLOUD_REPLY")
    monkeypatch.setattr(harness, "judge",
                        lambda q, e, a, b, *, timeout=180: ("CORRECT", "CORRECT"))

    q = {"id": "q-stable", "text": "Q?", "question_type": "inference_query",
         "expected_path": {"nodes": ["t1"]}}
    slots = set()
    for run_idx in range(8):
        r = harness.run_one_query(q, "evidence", local_model="m",
                                  run_idx=run_idx, timeout=10)
        slots.add(r["a_is_local"])
    # over 8 runs the seed should produce both True and False at least once
    assert slots == {True, False}


# ─── Majority verdict logic ────────────────────────────────────────


def test_majority_clear_winner(harness):
    """3 votes → 2-1 clear winner."""
    assert harness._majority(["CORRECT", "CORRECT", "INCORRECT"]) == "CORRECT"
    assert harness._majority(["INCORRECT", "INCORRECT", "CORRECT"]) == "INCORRECT"
    assert harness._majority(["ABSTAINED", "ABSTAINED", "INCORRECT"]) == "ABSTAINED"


def test_majority_tie_prefers_correct_then_abstained(harness):
    """1-1-1 tie: documented preference order CORRECT > ABSTAINED > INCORRECT
    (optimistic — caveat block notes this for downstream readers)."""
    assert harness._majority(["CORRECT", "INCORRECT", "ABSTAINED"]) == "CORRECT"
    assert harness._majority(["INCORRECT", "ABSTAINED"]) == "ABSTAINED"


def test_majority_empty_is_incorrect(harness):
    """Empty input → INCORRECT (conservative — no evidence of correctness)."""
    assert harness._majority([]) == "INCORRECT"


def test_majority_unanimous(harness):
    assert harness._majority(["CORRECT", "CORRECT", "CORRECT"]) == "CORRECT"


# ─── Aggregate logic ────────────────────────────────────────────────


def _row(qid, qtype, run, local, cloud, hops=2):
    return {
        "id": qid, "type": qtype, "run": run, "hops": hops,
        "a_is_local": True,
        "local_verdict": local, "cloud_verdict": cloud,
        "local_abstain": False, "cloud_abstain": False,
        "local_answer": "L", "cloud_answer": "C",
        "local_error": "", "cloud_error": "", "judge_error": "",
        "elapsed_sec": 1.0,
    }


def test_aggregate_per_question_majority(harness):
    rows = [
        _row("q1", "inference_query", 0, "CORRECT", "CORRECT"),
        _row("q1", "inference_query", 1, "INCORRECT", "CORRECT"),
        _row("q1", "inference_query", 2, "CORRECT", "CORRECT"),
        _row("q2", "comparison_query", 0, "INCORRECT", "INCORRECT"),
        _row("q2", "comparison_query", 1, "INCORRECT", "CORRECT"),
        _row("q2", "comparison_query", 2, "INCORRECT", "CORRECT"),
    ]
    agg = harness.aggregate(rows)
    by_q = {q["id"]: q for q in agg["per_question"]}
    # q1: local 2/3 CORRECT, cloud 3/3
    assert by_q["q1"]["local_majority"] == "CORRECT"
    assert by_q["q1"]["cloud_majority"] == "CORRECT"
    # q2: local 0/3, cloud 2/3
    assert by_q["q2"]["local_majority"] == "INCORRECT"
    assert by_q["q2"]["cloud_majority"] == "CORRECT"


def test_aggregate_delta_correct_cloud_minus_local(harness):
    """One question where cloud wins → Δ = +0.5 over 2 questions."""
    rows = [
        _row("q1", "inference_query", 0, "CORRECT", "CORRECT"),
        _row("q1", "inference_query", 1, "CORRECT", "CORRECT"),
        _row("q1", "inference_query", 2, "CORRECT", "CORRECT"),
        _row("q2", "comparison_query", 0, "INCORRECT", "CORRECT"),
        _row("q2", "comparison_query", 1, "INCORRECT", "CORRECT"),
        _row("q2", "comparison_query", 2, "INCORRECT", "CORRECT"),
    ]
    agg = harness.aggregate(rows)
    s = agg["summary"]
    assert s["local_correct_rate"] == 0.5
    assert s["cloud_correct_rate"] == 1.0
    assert s["delta_correct_cloud_minus_local"] == 0.5


def test_aggregate_stability_flag(harness):
    """Stable = same verdict across all n runs for that question."""
    rows = [
        _row("q1", "inference_query", 0, "CORRECT", "CORRECT"),
        _row("q1", "inference_query", 1, "CORRECT", "CORRECT"),
        _row("q1", "inference_query", 2, "CORRECT", "CORRECT"),
        _row("q2", "comparison_query", 0, "CORRECT", "CORRECT"),
        _row("q2", "comparison_query", 1, "INCORRECT", "CORRECT"),
        _row("q2", "comparison_query", 2, "CORRECT", "CORRECT"),
    ]
    agg = harness.aggregate(rows)
    by_q = {q["id"]: q for q in agg["per_question"]}
    assert by_q["q1"]["local_stable"] is True
    assert by_q["q2"]["local_stable"] is False  # flipped run 1
    assert by_q["q2"]["cloud_stable"] is True


def test_aggregate_by_type_breakdown(harness):
    rows = [
        _row("q1", "inference_query", 0, "CORRECT", "CORRECT"),
        _row("q2", "inference_query", 0, "INCORRECT", "INCORRECT"),
        _row("q3", "comparison_query", 0, "CORRECT", "CORRECT"),
    ]
    agg = harness.aggregate(rows)
    bt = agg["summary"]["by_type"]
    assert bt["inference_query"]["n"] == 2
    assert bt["inference_query"]["local_correct"] == 1
    assert bt["inference_query"]["cloud_correct"] == 1
    assert bt["comparison_query"]["n"] == 1


def test_aggregate_empty_rows_safe(harness):
    """No rows → empty per_question + empty summary. Doesn't raise."""
    agg = harness.aggregate([])
    assert agg["per_question"] == []
    assert agg["summary"] == {}


def test_aggregate_n_runs_per_question_correct_with_single_run(harness):
    """S5c regression — aggregate reported `n_runs/q=0` whenever
    --n-runs=1 because the old form `rows[0].get("run", 0) and max(...)+1`
    short-circuited on the falsy run_idx=0. Caught by S4 smoke
    2026-06-03; fixed in same PR."""
    rows = [
        _row("q1", "inference_query", 0, "CORRECT", "CORRECT"),
        _row("q2", "comparison_query", 0, "CORRECT", "CORRECT"),
    ]
    agg = harness.aggregate(rows)
    assert agg["summary"]["n_runs_per_question"] == 1


def test_aggregate_n_runs_per_question_correct_with_three_runs(harness):
    rows = [
        _row("q1", "inference_query", 0, "CORRECT", "CORRECT"),
        _row("q1", "inference_query", 1, "CORRECT", "CORRECT"),
        _row("q1", "inference_query", 2, "CORRECT", "CORRECT"),
    ]
    agg = harness.aggregate(rows)
    assert agg["summary"]["n_runs_per_question"] == 3


# ─── Caveat block presence ──────────────────────────────────────────


def test_caveat_block_covers_every_known_failure_mode(harness):
    """Per design memo §4.1 — the caveat block is mandatory and must
    cover the known failure modes of this measurement design.

    [2026-08-21] The set is exact on purpose: dropping a caveat silently
    is the failure this guards against, so adding one is meant to be a
    conscious edit here too. `chat_mode_lenient_judge` was added to the
    harness (chat-mode fixtures are intrinsically judge-only — only the
    factual_chat sub-class carries gold_signals) and never recorded
    here. Also renamed off "five" — the list has not been five for a
    while, and a count in the name goes stale every time it grows.
    """
    expected = {
        "judge_self_preference",
        "gold_evidence_not_pipeline",
        "small_n",
        "lenient_judge",
        "local_model_caveat",
        "abstraction_no_op",
        "chat_mode_lenient_judge",
    }
    assert set(harness.CAVEAT_BLOCK.keys()) == expected
    # each caveat is a non-trivial sentence
    for k, v in harness.CAVEAT_BLOCK.items():
        assert len(v) >= 60, f"caveat {k!r} too short ({len(v)} chars)"


# ─── Error tolerance ────────────────────────────────────────────────


def test_run_one_query_local_error_keeps_going(harness, monkeypatch):
    """Local call raises → row records the error, judge skipped, harness
    returns a well-formed row instead of crashing."""
    def boom(*a, **kw):
        raise RuntimeError("ollama down")
    monkeypatch.setattr(harness, "call_local", boom)
    monkeypatch.setattr(harness, "call_cloud_via_abstraction",
                        lambda p, *, timeout=180: "CLOUD_REPLY")
    monkeypatch.setattr(harness, "judge",
                        lambda *a, **k: ("CORRECT", "CORRECT"))

    q = {"id": "q-err", "text": "Q?", "question_type": "inference_query",
         "expected_path": {"nodes": ["t1"]}}
    r = harness.run_one_query(q, "evidence", local_model="m",
                              run_idx=0, timeout=10)

    assert r["local_error"].startswith("RuntimeError")
    assert "ollama down" in r["local_error"]
    assert r["local_answer"] == ""
    # judge skipped because one candidate errored
    assert r["judge_error"] == "skipped: candidate error"
    assert r["local_verdict"] == "INCORRECT"
    assert r["cloud_verdict"] == "INCORRECT"


def test_run_one_query_cloud_error_keeps_going(harness, monkeypatch):
    """Symmetric: cloud raises → cloud-side recorded as error, harness
    still produces a row."""
    monkeypatch.setattr(harness, "call_local",
                        lambda p, *, model, timeout=180, local_backend='ollama': "LOCAL_REPLY")

    def boom(*a, **kw):
        raise RuntimeError("claude cli not found")
    monkeypatch.setattr(harness, "call_cloud_via_abstraction", boom)
    monkeypatch.setattr(harness, "judge",
                        lambda *a, **k: ("CORRECT", "CORRECT"))

    q = {"id": "q-cerr", "text": "Q?", "question_type": "inference_query",
         "expected_path": {"nodes": ["t1"]}}
    r = harness.run_one_query(q, "evidence", local_model="m",
                              run_idx=0, timeout=10)

    assert "claude cli not found" in r["cloud_error"]
    assert r["cloud_answer"] == ""
    assert r["judge_error"] == "skipped: candidate error"


def test_run_one_query_judge_error_recorded(harness, monkeypatch):
    """Both candidates succeed but judge fails → verdict marked as
    INCORRECT, error string recorded."""
    monkeypatch.setattr(harness, "call_local",
                        lambda p, *, model, timeout=180, local_backend='ollama': "L")
    monkeypatch.setattr(harness, "call_cloud_via_abstraction",
                        lambda p, *, timeout=180: "C")

    def boom(*a, **k):
        raise RuntimeError("judge net error")
    monkeypatch.setattr(harness, "judge", boom)

    q = {"id": "q-jerr", "text": "Q?", "question_type": "inference_query",
         "expected_path": {"nodes": ["t1"]}}
    r = harness.run_one_query(q, "evidence", local_model="m",
                              run_idx=0, timeout=10)

    assert "judge net error" in r["judge_error"]
    assert r["local_verdict"] == "INCORRECT"
    assert r["cloud_verdict"] == "INCORRECT"


# ─── Abstain detection ─────────────────────────────────────────────


def test_is_abstain_recognizes_known_phrases(harness):
    for s in (
        "I don't know.",
        "I dont know what this means",
        "I cannot determine that from the context.",
        "The answer is not in the context.",
        "Not provided in the evidence.",
    ):
        assert harness._is_abstain(s) is True


def test_is_abstain_does_not_flag_substantive_answers(harness):
    for s in (
        "The capital of France is Paris.",
        "Based on Article 1, the answer is yes.",
        "",
    ):
        assert harness._is_abstain(s) is False
