"""RAB Baseline-0 adapter tests — pin the floor.

The pre-reg (`docs/research/r1-4-preregistration-2026-06-10.md`) calls
Baseline-0 the floor: vanilla RAG quickstart + default Python-logging
records. These tests pin that floor empirically:

* Mutations still happen (snapshot is non-empty), but the log doesn't
  carry the structured payload needed to replay them → RF-exact = 0.0
  whenever any ingest happened.
* Vanilla logs don't emit ANSWER events → AC's ANSWER per-type = 0.0.
* No parent_id chain → PC = 0.0.
* The adapter is deterministic (no LLM, no embeddings, no time-dep
  retrieval).

These are not "JAMES wins" tests — they pin what the floor looks like
so the gap table in R1.4 release reads honestly.
"""
from pathlib import Path

import pytest

from eval.rab.adapters.baseline0 import Baseline0Adapter
from eval.rab.driver import load_scenario, run_scenario, score_run

ROOT = Path(__file__).resolve().parent.parent
S1 = ROOT / "eval" / "rab" / "scenarios" / "s1_lifecycle_small.json"


@pytest.fixture(scope="module")
def s1():
    return load_scenario(S1)


def test_baseline0_runs_scenario_without_errors(s1):
    artifacts = run_scenario(s1, Baseline0Adapter())
    # 40 driver ops → 40 e_exec rows
    assert len(artifacts["e_exec"]) == 40
    # snapshots taken at every checkpoint (10)
    assert len(artifacts["snapshots"]) == 10
    assert len(artifacts["replays"]) == 10


def test_baseline0_replay_is_empty_floor(s1):
    """Vanilla logs carry no payload → replay returns empty state.

    With any ingest in the scenario the live snapshot is non-empty, so
    RF-exact must be 0.0 (not a bug — the *point* of being the floor)."""
    artifacts = run_scenario(s1, Baseline0Adapter())
    scores = score_run(artifacts)
    assert scores["RF"]["exact"] == 0.0
    assert scores["RF"]["graded"] == 0.0


def test_baseline0_pc_zero_no_parent_chain(s1):
    artifacts = run_scenario(s1, Baseline0Adapter())
    scores = score_run(artifacts)
    # The adapter emits citations but no parent_id chain — every cite
    # is untraceable per SPEC §2.3.
    assert scores["PC"]["pc"] == 0.0


def test_baseline0_ac_floor_pattern(s1):
    """AC: only the obvious INGEST mapping survives. UPDATE/SUPERSEDE/
    DELETE/ANSWER all degrade because vanilla logs don't distinguish them.
    """
    artifacts = run_scenario(s1, Baseline0Adapter())
    scores = score_run(artifacts)
    per = scores["AC"]["per_type"]
    # Vanilla quickstart logs ingest/update/supersede all as "doc_added"
    # → mapped to INGEST. The driver's executed ops include 11 INGEST
    # ops, so INGEST AC should be 1.0 (matched events available).
    assert per["INGEST"]["ac"] == 1.0
    # ANSWER ops never emit an ANSWER-typed log event in the floor.
    assert per["ANSWER"]["ac"] == 0.0
    # Overall well below reference's 1.0 — exact ratio depends on the
    # scenario op mix; just pin the inequality.
    assert scores["AC"]["overall"] < 0.5


def test_baseline0_snapshot_grows(s1):
    """Live state still works — the floor is about the LOG, not the
    in-memory index."""
    a = Baseline0Adapter()
    a.ingest("d1", "Title One", "Body one.")
    a.ingest("d2", "Title Two", "Body two.")
    snap = a.snapshot()
    assert {e["id"] for e in snap["entities"]} == {"d1", "d2"}
    assert snap["edges"] == []  # no supersede edges in baseline0


def test_baseline0_query_returns_citations():
    a = Baseline0Adapter()
    a.ingest("d1", "Northbridge Labs founding", "founded by Elena.")
    out = a.query("Northbridge?")
    assert "d1" in out["citations"]


def test_baseline0_export_log_canonical_shape(s1):
    """Every exported row must have the SPEC §1 keys, even at the floor."""
    a = Baseline0Adapter()
    a.ingest("d1", "t", "x")
    a.delete("d1")
    for row in a.export_log():
        for key in ("event_id", "ts", "event_type", "parent_id",
                    "inputs_hash", "payload"):
            assert key in row
        # mapping table already applied → canonical type field
        assert row["event_type"] in (
            "INGEST", "UPDATE", "SUPERSEDE", "DELETE",
            "RETRIEVE", "RERANK", "SYNTH", "VERIFY", "ANSWER", "OTHER",
        )


def test_baseline0_deterministic(s1):
    """Two runs on the same scenario produce the same scores (no LLM,
    no embeddings, no time-dep retrieval)."""
    a1 = run_scenario(s1, Baseline0Adapter())
    a2 = run_scenario(s1, Baseline0Adapter())
    s1_scores = score_run(a1)
    s2_scores = score_run(a2)
    # AC/RF/PC values must match — wall-clock differences only affect
    # ts in the audit log (which influences time-window matching but
    # not the totals on a fast-enough machine).
    assert s1_scores["AC"]["overall"] == s2_scores["AC"]["overall"]
    assert s1_scores["RF"]["exact"] == s2_scores["RF"]["exact"]
    assert s1_scores["PC"]["pc"] == s2_scores["PC"]["pc"]
