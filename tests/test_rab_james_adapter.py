"""RAB JAMES adapter tests — pin the audit-native demonstration.

The JAMES adapter is audit-native by design (RAB-canonical event types
emitted at the moment each op runs). Tests pin:

* end-to-end S1 run produces AC=1.0 / RF-exact=1.0 / PC=1.0 in
  deterministic mode (= what audit-native looks like)
* workspace isolation: lifecycle DB lives under the workspace, not the
  production audit.db path
* every SUPERSEDE JSONL row has a corresponding lifecycle event in the
  workspace SQLite (= the real JAMES code path is actually exercised)
* reconstruct_graph_at(t) agrees with the JSONL replay on supersede
  edges (cross-verification — JAMES's existing replay primitive sees
  the same picture the RAB log does)
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from eval.rab.adapters.james import JamesAdapter
from eval.rab.driver import load_scenario, run_scenario, score_run

ROOT = Path(__file__).resolve().parent.parent
S1 = ROOT / "eval" / "rab" / "scenarios" / "s1_lifecycle_small.json"


@pytest.fixture(scope="module")
def s1():
    return load_scenario(S1)


# ─── end-to-end on scenario-S1 (deterministic mode) ────────────────


def test_james_audit_native_perfect_scores(s1, tmp_path):
    adapter = JamesAdapter(workspace=tmp_path / "ws", use_engine=False)
    artifacts = run_scenario(s1, adapter)
    scores = score_run(artifacts)
    assert scores["AC"]["overall"] == 1.0, scores["AC"]
    assert scores["RF"]["exact"] == 1.0, scores["RF"]
    assert scores["RF"]["graded"] == 1.0
    assert scores["RF"]["k"] == 10
    assert scores["PC"]["pc"] == 1.0, scores["PC"]
    assert scores["PC"]["total_citations"] > 0


def test_james_workspace_isolation(tmp_path):
    """The lifecycle DB and the JSONL log MUST live under the workspace
    — production audit.db is never touched."""
    ws = tmp_path / "isolated"
    adapter = JamesAdapter(workspace=ws, use_engine=False)
    adapter.ingest("d1", "Title", "Body")
    adapter.supersede("d1", "d2", "Replacement", "Body2")

    # Lifecycle DB under workspace
    assert adapter.lifecycle_db.parent == ws.resolve()
    assert adapter.lifecycle_db.exists()
    # JSONL log under workspace
    log = list(ws.iterdir())
    assert any(p.name == "rab_audit_log.jsonl" for p in log)


def test_james_supersede_emits_lifecycle_event(tmp_path):
    """Every SUPERSEDE op writes both a JSONL row AND a real lifecycle
    event in the workspace SQLite (= JAMES's production code path is
    actually exercised, not just imitated)."""
    adapter = JamesAdapter(workspace=tmp_path / "ws", use_engine=False)
    adapter.ingest("d1", "Original", "Body")
    adapter.supersede("d1", "d2", "Replacement", "Body2")
    adapter.supersede("d2", "d3", "Replacement2", "Body3")

    rows = adapter.export_log()
    n_supersede_jsonl = sum(1 for r in rows
                            if r["event_type"] == "SUPERSEDE")
    assert n_supersede_jsonl == 2

    conn = sqlite3.connect(adapter.lifecycle_db)
    try:
        cur = conn.execute(
            "SELECT COUNT(*) FROM audit_log "
            "WHERE event_type = 'lifecycle.supersede.edge_created'"
        )
        n_lifecycle = cur.fetchone()[0]
    finally:
        conn.close()
    assert n_lifecycle == n_supersede_jsonl


def test_james_reconstruct_graph_at_agrees_on_supersede_chain(tmp_path):
    """reconstruct_graph_at(t) — JAMES's existing primitive — sees the
    same supersede edges the RAB JSONL replay sees. The two reconstructions
    must agree on the chain shape (the JSONL replay's edges set must be
    a superset; reconstruct_graph_at only sees lifecycle events, RAB
    JSONL also has INGEST/UPDATE/DELETE)."""
    adapter = JamesAdapter(workspace=tmp_path / "ws", use_engine=False)
    adapter.ingest("d1", "Original", "Body")
    adapter.supersede("d1", "d2", "Replacement", "Body2")

    # JAMES_AUDIT_DB env was already pointed at the workspace DB by
    # the adapter constructor — reconstruct_graph_at picks it up.
    from core.lifecycle.replay_graph import reconstruct_graph_at
    snap = reconstruct_graph_at(datetime.now())
    # Lifecycle snapshot saw exactly one supersede edge.
    assert snap.event_count == 1
    assert len(snap.edges) == 1
    # JSONL replay at the latest time contains the same supersede edge.
    rab_replay = adapter.replay_at(1, "9999-12-31T00:00:00+00:00")
    supersede_edges = [e for e in rab_replay["edges"]
                       if e["type"] == "SUPERSEDE"]
    assert len(supersede_edges) == 1
    assert supersede_edges[0]["dst"] == "d1"
    assert supersede_edges[0]["src"] == "d2"


# ─── adapter contract ─────────────────────────────────────────────


def test_james_export_log_canonical_shape(tmp_path):
    adapter = JamesAdapter(workspace=tmp_path / "ws", use_engine=False)
    adapter.ingest("d1", "t", "x")
    adapter.update("d1", "t2", "x2")
    adapter.delete("d1")
    for row in adapter.export_log():
        for key in ("event_id", "ts", "event_type", "parent_id",
                    "inputs_hash", "payload"):
            assert key in row
        assert row["event_type"] in (
            "INGEST", "UPDATE", "SUPERSEDE", "DELETE",
            "RETRIEVE", "RERANK", "SYNTH", "VERIFY", "ANSWER", "OTHER",
        )


def test_james_snapshot_shape(tmp_path):
    adapter = JamesAdapter(workspace=tmp_path / "ws", use_engine=False)
    adapter.ingest("d1", "Title One", "x")
    adapter.ingest("d2", "Title Two", "y")
    snap = adapter.snapshot()
    assert {e["id"] for e in snap["entities"]} == {"d1", "d2"}
    assert snap["edges"] == []
    # entities sorted by id (SPEC §2.4)
    ids = [e["id"] for e in snap["entities"]]
    assert ids == sorted(ids)


def test_james_query_emits_provenance_chain(tmp_path):
    adapter = JamesAdapter(workspace=tmp_path / "ws", use_engine=False)
    adapter.ingest("d1", "Northbridge Labs founding note",
                   "founded by Elena Vasquez in 2019.")
    out = adapter.query("Who founded Northbridge?")
    assert "d1" in out["citations"]

    rows = adapter.export_log()
    types = [r["event_type"] for r in rows]
    # INGEST, RETRIEVE, SYNTH, ANSWER all present, in that order
    assert types == ["INGEST", "RETRIEVE", "SYNTH", "ANSWER"]
    # Provenance chain: ANSWER.parent == SYNTH.event_id;
    # SYNTH.parent == RETRIEVE.event_id
    by_type = {r["event_type"]: r for r in rows}
    assert by_type["ANSWER"]["parent_id"] == by_type["SYNTH"]["event_id"]
    assert by_type["SYNTH"]["parent_id"] == by_type["RETRIEVE"]["event_id"]


def test_james_replay_log_only(tmp_path):
    """replay_at MUST be a pure function of the exported log. We simulate
    that by exporting the log, then constructing a fresh adapter pointed
    at the same JSONL and confirming the replay matches.

    (For SPEC §6.2 compliance the replay impl reads ONLY the JSONL —
    no in-memory state, no DB. This test inspects that contract by
    moving the JSONL to a different filesystem location.)
    """
    adapter = JamesAdapter(workspace=tmp_path / "ws", use_engine=False)
    adapter.ingest("d1", "Original", "x")
    adapter.supersede("d1", "d2", "Replacement", "y")

    # Capture replay result with the live adapter.
    live_replay = adapter.replay_at(1, "9999-12-31T00:00:00+00:00")

    # Build a second adapter pointed at a different workspace, but
    # COPY the JSONL log over to it. Replay there must produce the
    # same state (= log-only invariant).
    ws2 = tmp_path / "ws2"
    adapter2 = JamesAdapter(workspace=ws2, use_engine=False)
    # Overwrite the empty fresh log with the first adapter's log.
    adapter2._log_path.write_bytes(adapter._log_path.read_bytes())
    transplant_replay = adapter2.replay_at(1, "9999-12-31T00:00:00+00:00")

    assert json.dumps(live_replay, sort_keys=True) == \
           json.dumps(transplant_replay, sort_keys=True)


def test_james_deterministic_mode_repeat(tmp_path, s1):
    """Same scenario, same adapter, same scores — even though
    timestamps drift between runs the metric values are stable."""
    a1 = JamesAdapter(workspace=tmp_path / "ws1", use_engine=False)
    s1a = score_run(run_scenario(s1, a1))
    a2 = JamesAdapter(workspace=tmp_path / "ws2", use_engine=False)
    s1b = score_run(run_scenario(s1, a2))
    assert s1a["AC"]["overall"] == s1b["AC"]["overall"] == 1.0
    assert s1a["RF"]["exact"] == s1b["RF"]["exact"] == 1.0
    assert s1a["PC"]["pc"] == s1b["PC"]["pc"] == 1.0
