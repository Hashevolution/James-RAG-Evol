"""RAB Baseline-1 adapter tests — pin the bolt-on-tracing middle row.

Baseline-1 maps OpenTelemetry GenAI semantic-conventions spans onto RAB
canonical types via the published mapping table
(eval/rab/mappings/otel_genai_to_rab.json). The tests pin the structural
findings the v0.1.1 release will report:

* AC ANSWER = 1.0 (OTel chat span maps to ANSWER perfectly)
* AC INGEST = AC UPDATE = AC SUPERSEDE = AC DELETE = 0
  (corpus lifecycle is out of scope for OTel GenAI semconv → those
  driver ops never match a canonical log event)
* AC overall = 0.5 (20 of 40 driver ops match — every QUERY op finds
  its ANSWER, every mutation op finds nothing)
* RF-exact = RF-graded = 0 (no doc payload in any span)
* PC = 0 (no INGEST → origin chain breaks)
* Baseline-1 still emits RETRIEVE log events (its retrieval span maps
  to RETRIEVE), but RAB AC only scores canonicals that appear in the
  driver's ground-truth op list (e_exec). Scenario-S1's e_exec contains
  mutation ops + ANSWER (= QUERY), not RETRIEVE/SYNTH — those are
  emitted by the SUT internally and would be scored only by a future
  scenario that lifts them to driver-side ground truth.

These numbers are the *finding*. If a future cycle changes any of them
without bumping the spec or the mapping table, that's a regression
under the v0.1.1 honesty clauses.
"""
from pathlib import Path

import pytest

from eval.rab.adapters.baseline1 import Baseline1Adapter
from eval.rab.driver import load_scenario, run_scenario, score_run

ROOT = Path(__file__).resolve().parent.parent
S1 = ROOT / "eval" / "rab" / "scenarios" / "s1_lifecycle_small.json"


@pytest.fixture(scope="module")
def s1():
    return load_scenario(S1)


def test_baseline1_runs_scenario_without_errors(s1):
    artifacts = run_scenario(s1, Baseline1Adapter())
    assert len(artifacts["e_exec"]) == 40
    assert len(artifacts["snapshots"]) == 10
    assert len(artifacts["replays"]) == 10


def test_baseline1_ac_answer_perfect(s1):
    """ANSWER scores 1.0 — every QUERY op finds its mapped chat-span
    answer event in the log. This is the OTel home turf."""
    artifacts = run_scenario(s1, Baseline1Adapter())
    scores = score_run(artifacts)
    per = scores["AC"]["per_type"]
    assert per["ANSWER"]["ac"] == 1.0
    assert per["ANSWER"]["total"] == 20
    assert per["ANSWER"]["matched"] == 20


def test_baseline1_ac_lifecycle_gap_pinned(s1):
    """INGEST / UPDATE / SUPERSEDE / DELETE all score 0 — corpus
    lifecycle is explicitly out of scope for OTel GenAI semconv,
    so no log event of those canonical types exists to match."""
    artifacts = run_scenario(s1, Baseline1Adapter())
    scores = score_run(artifacts)
    per = scores["AC"]["per_type"]
    assert per["INGEST"]["ac"] == 0.0
    assert per["UPDATE"]["ac"] == 0.0
    assert per["SUPERSEDE"]["ac"] == 0.0
    assert per["DELETE"]["ac"] == 0.0


def test_baseline1_retrieve_emitted_but_not_in_ground_truth(s1):
    """Bolt-on tracing emits RETRIEVE events in its log, but RAB AC
    only scores canonicals that appear in the driver's ground-truth
    e_exec. Scenario-S1 has no RETRIEVE ground-truth op, so the
    Baseline-1 RETRIEVE events are unused by AC and don't appear in
    per_type. (They DO appear in the exported log itself — verified
    separately.)"""
    artifacts = run_scenario(s1, Baseline1Adapter())
    scores = score_run(artifacts)
    per = scores["AC"]["per_type"]
    # Driver-ground-truth canonical set on S1 is exactly:
    assert set(per.keys()) == {"INGEST", "UPDATE", "SUPERSEDE",
                                "DELETE", "ANSWER"}
    # But the SUT's exported log DOES contain RETRIEVE events,
    # validating the mapping table.
    log_types = {row["event_type"] for row in artifacts["log"]}
    assert "RETRIEVE" in log_types
    assert "ANSWER" in log_types


def test_baseline1_ac_overall_around_half(s1):
    """20 ANSWER ops match → matched=20 over total=40 → AC = 0.5
    exactly. The middle of the gap between Baseline-0 (0.275) and
    the audit-native row (1.000) lands here."""
    artifacts = run_scenario(s1, Baseline1Adapter())
    scores = score_run(artifacts)
    assert scores["AC"]["overall"] == 0.5


def test_baseline1_rf_zero_no_payload(s1):
    """OTel spans carry no doc payload → replay returns empty state →
    RF = 0 at every checkpoint."""
    artifacts = run_scenario(s1, Baseline1Adapter())
    scores = score_run(artifacts)
    assert scores["RF"]["exact"] == 0.0
    assert scores["RF"]["graded"] == 0.0


def test_baseline1_pc_zero_no_origin(s1):
    """ANSWER → chain → RETRIEVE works (parent_span_id chain), but
    the chain dies at RETRIEVE because there is no INGEST event in
    the log to be its origin. PC must therefore be 0."""
    artifacts = run_scenario(s1, Baseline1Adapter())
    scores = score_run(artifacts)
    assert scores["PC"]["pc"] == 0.0


def test_baseline1_export_log_canonical_shape():
    a = Baseline1Adapter()
    a.ingest("d1", "Title One", "x")
    a.query("Title?")
    for row in a.export_log():
        for key in ("event_id", "ts", "event_type", "parent_id",
                    "inputs_hash", "payload"):
            assert key in row
        assert row["event_type"] in (
            "INGEST", "UPDATE", "SUPERSEDE", "DELETE",
            "RETRIEVE", "RERANK", "SYNTH", "VERIFY", "ANSWER", "OTHER",
        )


def test_baseline1_parent_chain_runs_answer_to_retrieve():
    """A query's chat span has the retrieval span as parent. After
    mapping, ANSWER.parent_id == RETRIEVE.event_id."""
    a = Baseline1Adapter()
    a.ingest("d1", "Northbridge Labs founding note", "founded.")
    a.query("Who founded Northbridge?")
    rows = a.export_log()
    types = [r["event_type"] for r in rows]
    assert types == ["RETRIEVE", "ANSWER"]
    by_type = {r["event_type"]: r for r in rows}
    assert by_type["ANSWER"]["parent_id"] == by_type["RETRIEVE"]["event_id"]


def test_baseline1_mapping_table_pinned():
    """The published mapping table must be the one the adapter loads
    and reports."""
    a = Baseline1Adapter()
    mt = a.MAPPING_TABLE
    assert mt["retrieval"] == "RETRIEVE"
    assert mt["chat"] == "ANSWER"
    assert mt["embeddings"] == "OTHER"
    # INGEST canonicals MUST NOT be in the mapping — that absence is
    # the structural finding.
    assert "INGEST" not in mt.values()
    assert "UPDATE" not in mt.values()
    assert "SUPERSEDE" not in mt.values()
    assert "DELETE" not in mt.values()


def test_baseline1_snapshot_grows_state_but_log_does_not():
    """The live state is non-empty; the OTel-only log is silent on
    state mutations. That divergence is precisely what RF measures."""
    a = Baseline1Adapter()
    a.ingest("d1", "t", "x")
    a.ingest("d2", "t2", "y")
    snap = a.snapshot()
    assert {e["id"] for e in snap["entities"]} == {"d1", "d2"}
    # No spans emitted for ingests → empty log.
    assert a.export_log() == []
