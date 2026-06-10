"""RAB SPEC v0.1 — driver + scorer + reference-adapter tests.

The reference adapter is a perfectly-audited event-sourced SUT, so it
MUST score AC=1.0 / RF-exact=1.0 / PC=1.0 on scenario-S1 — that pins
the whole pipeline. Fault-injection variants then assert each metric
drops for exactly the right reason (no cross-contamination).
"""
import json
from pathlib import Path

import pytest

from eval.rab.adapters.reference import ReferenceAdapter
from eval.rab.driver import load_scenario, run_scenario, score_run
from eval.rab.scorer import canon, score_ac, score_pc, score_rf, state_items

ROOT = Path(__file__).resolve().parent.parent
S1 = ROOT / "eval" / "rab" / "scenarios" / "s1_lifecycle_small.json"


# ─── scenario fixture sanity ───────────────────────────────────────


def test_s1_structure():
    data = json.loads(S1.read_text(encoding="utf-8"))
    ops = data["ops"]
    assert len(ops) == 40
    kinds = {}
    for o in ops:
        kinds[o["op"]] = kinds.get(o["op"], 0) + 1
    assert kinds == {"INGEST": 11, "UPDATE": 4, "SUPERSEDE": 3,
                     "DELETE": 2, "QUERY": 20}
    assert sum(1 for o in ops if o.get("checkpoint")) == 10
    ids = [o["op_id"] for o in ops]
    assert len(set(ids)) == len(ids)
    assert ids == sorted(ids)


# ─── canon ─────────────────────────────────────────────────────────


def test_canon_order_independent():
    a = {"entities": [{"id": "b"}, {"id": "a"}],
         "edges": [{"src": "x", "dst": "y", "type": "S"}]}
    b = {"edges": [{"type": "S", "dst": "y", "src": "x"}],
         "entities": [{"id": "a"}, {"id": "b"}]}
    assert canon(a) == canon(b)


def test_canon_float_normalisation():
    a = {"entities": [{"id": "a", "score": 0.1234564}], "edges": []}
    b = {"entities": [{"id": "a", "score": 0.1234561}], "edges": []}
    assert canon(a) == canon(b)  # both round to 0.123456


def test_canon_none_is_empty():
    assert canon(None) == canon({"entities": [], "edges": []})


def test_state_items():
    s = {"entities": [{"id": "a"}],
         "edges": [{"src": "a", "dst": "b", "type": "S"}]}
    assert state_items(s) == {("entity", "a"), ("edge", "a", "b", "S")}


# ─── unit: scorer on synthetic inputs ──────────────────────────────


def _op(op_id, typ, lo, hi):
    return {"op_id": op_id, "type": typ, "t_start": lo, "t_end": hi}


def _ev(eid, typ, ts, parent=None, payload=None):
    return {"event_id": eid, "ts": ts, "event_type": typ,
            "parent_id": parent, "inputs_hash": "h", "payload": payload or {}}


def test_score_ac_full_and_partial():
    ops = [_op("o1", "INGEST", "T1", "T2"), _op("o2", "ANSWER", "T3", "T4")]
    log_full = [_ev("e1", "INGEST", "T1"), _ev("e2", "ANSWER", "T3")]
    r = score_ac(ops, log_full)
    assert r["overall"] == 1.0
    log_missing = [_ev("e1", "INGEST", "T1")]
    r2 = score_ac(ops, log_missing)
    assert r2["overall"] == 0.5
    assert r2["per_type"]["ANSWER"]["ac"] == 0.0
    assert r2["per_type"]["INGEST"]["ac"] == 1.0


def test_score_ac_no_double_consume():
    ops = [_op("o1", "INGEST", "T1", "T4"), _op("o2", "INGEST", "T1", "T4")]
    log = [_ev("e1", "INGEST", "T2")]  # one event cannot match two ops
    assert score_ac(ops, log)["matched"] == 1


def test_score_rf_exact_graded_cost():
    s = {1: {"entities": [{"id": "a"}], "edges": []},
         2: {"entities": [{"id": "a"}, {"id": "b"}], "edges": []}}
    r_same = dict(s)
    out = score_rf(s, r_same, {"events": 2000, "seconds": 1.0})
    assert out["exact"] == 1.0 and out["graded"] == 1.0
    assert out["cost_s_per_1k_events"] == 0.5
    r_half = {1: s[1], 2: {"entities": [{"id": "a"}], "edges": []}}
    out2 = score_rf(s, r_half)
    assert out2["exact"] == 0.5
    assert 0.0 < out2["graded"] < 1.0


def test_score_pc_chain_and_breaks():
    log = [
        _ev("i1", "INGEST", "T1", payload={"doc_id": "d1"}),
        _ev("r1", "RETRIEVE", "T2", payload={"doc_ids": ["d1"]}),
        _ev("s1", "SYNTH", "T3", parent="r1"),
        _ev("a1", "ANSWER", "T4", parent="s1",
            payload={"citations": ["d1"]}),
    ]
    assert score_pc(log)["pc"] == 1.0
    # break the parent chain → citation untraceable
    broken = [dict(e) for e in log]
    broken[3]["parent_id"] = None
    assert score_pc(broken)["pc"] == 0.0
    # cite a doc never ingested → untraceable
    ghost = [dict(e) for e in log]
    ghost[3] = _ev("a1", "ANSWER", "T4", parent="s1",
                   payload={"citations": ["nope"]})
    assert score_pc(ghost)["pc"] == 0.0


# ─── end-to-end: reference adapter on scenario-S1 ──────────────────


@pytest.fixture(scope="module")
def s1():
    return load_scenario(S1)


def test_reference_adapter_perfect_scores(s1):
    artifacts = run_scenario(s1, ReferenceAdapter())
    scores = score_run(artifacts)
    assert scores["AC"]["overall"] == 1.0, scores["AC"]
    assert scores["RF"]["exact"] == 1.0, scores["RF"]
    assert scores["RF"]["graded"] == 1.0
    assert scores["RF"]["k"] == 10
    # PC: every cited doc must be ingested + in the retrieve chain.
    assert scores["PC"]["pc"] == 1.0, scores["PC"]
    assert scores["PC"]["total_citations"] > 0  # cites actually happened
    assert scores["RF"]["cost_s_per_1k_events"] is not None


def test_fault_drop_audit_lowers_ac_only(s1):
    artifacts = run_scenario(
        s1, ReferenceAdapter(drop_audit_types={"ANSWER"}))
    scores = score_run(artifacts)
    assert scores["AC"]["overall"] < 1.0
    assert scores["AC"]["per_type"]["ANSWER"]["ac"] == 0.0
    # mutations still audited → replay still perfect
    assert scores["RF"]["exact"] == 1.0


def test_fault_corrupt_replay_lowers_rf_only(s1):
    artifacts = run_scenario(s1, ReferenceAdapter(corrupt_replay=True))
    scores = score_run(artifacts)
    assert scores["RF"]["exact"] == 0.0          # ghost doc in every replay
    assert 0.0 < scores["RF"]["graded"] < 1.0    # but mostly overlapping
    assert scores["AC"]["overall"] == 1.0        # audit untouched


def test_fault_break_provenance_lowers_pc(s1):
    artifacts = run_scenario(s1, ReferenceAdapter(break_provenance=True))
    scores = score_run(artifacts)
    # no citations emitted at all → denominator 0 → pc 0.0 by spec
    assert scores["PC"]["pc"] == 0.0
    assert scores["AC"]["overall"] == 1.0
    assert scores["RF"]["exact"] == 1.0


def test_scoring_is_deterministic(s1):
    a1 = run_scenario(s1, ReferenceAdapter())
    s_first = score_run(a1)
    s_again = score_run(a1)  # same artifacts → bit-identical
    assert json.dumps(s_first, sort_keys=True) == \
           json.dumps(s_again, sort_keys=True)
