"""RAB driver — SPEC v0.1 §2.1/§3. Runs a scenario against a SUT
adapter, recording the ground truth the scorer needs.

The adapter contract (duck-typed; see ``adapters/``)::

    class SUTAdapter:
        def ingest(doc_id, title, text) -> None
        def update(doc_id, title, text) -> None
        def supersede(old_doc_id, doc_id, title, text) -> None
        def delete(doc_id) -> None
        def query(q) -> dict            # {"answer": str, "citations": [str]}
        def snapshot() -> dict          # live state per SPEC §2.4 shape
        def export_log() -> list[dict]  # SPEC §1 rows, canonical types
        def replay_at(k, ts) -> dict    # state from the EXPORTED LOG ONLY
                                        # at checkpoint k (1-based) whose
                                        # ground-truth time is ts (UTC ISO) —
                                        # SPEC §2.2 reconstruct_graph_at(t_k)

The driver records, for every op, the canonical type and a UTC
[t_start, t_end] window (AC matching), takes live snapshots at
checkpoints (RF ground truth), then asks the adapter for log-only
replays of each checkpoint and times the replay pass (RF cost).
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

_OP_TO_CANONICAL = {
    "INGEST": "INGEST",
    "UPDATE": "UPDATE",
    "SUPERSEDE": "SUPERSEDE",
    "DELETE": "DELETE",
    "QUERY": "ANSWER",   # a QUERY op's decision-bearing outcome is the ANSWER event
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_scenario(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    ops = data.get("ops") or []
    if not ops:
        raise ValueError(f"scenario has no ops: {path}")
    return data


def run_scenario(scenario: dict, adapter) -> Dict[str, Any]:
    """Execute every op in order. Returns the artifacts bundle the
    scorer consumes::

        {e_exec, snapshots, replays, replay_cost, log,
         answers, scenario_name}
    """
    e_exec: List[dict] = []
    snapshots: Dict[int, dict] = {}
    snapshot_ts: Dict[int, str] = {}
    answers: List[dict] = []
    checkpoint_idx = 0

    for op in scenario["ops"]:
        kind = str(op["op"]).upper()
        args = op.get("args") or {}
        t_start = _utc_now_iso()

        if kind == "INGEST":
            adapter.ingest(args["doc_id"], args.get("title", ""),
                           args.get("text", ""))
        elif kind == "UPDATE":
            adapter.update(args["doc_id"], args.get("title", ""),
                           args.get("text", ""))
        elif kind == "SUPERSEDE":
            adapter.supersede(args["old_doc_id"], args["doc_id"],
                              args.get("title", ""), args.get("text", ""))
        elif kind == "DELETE":
            adapter.delete(args["doc_id"])
        elif kind == "QUERY":
            out = adapter.query(args["q"]) or {}
            answers.append({
                "op_id": op["op_id"],
                "q": args["q"],
                "answer": out.get("answer", ""),
                "citations": list(out.get("citations") or []),
            })
        else:
            raise ValueError(f"unknown op kind: {kind!r} ({op['op_id']})")

        t_end = _utc_now_iso()
        e_exec.append({
            "op_id": op["op_id"],
            "type": _OP_TO_CANONICAL[kind],
            "t_start": t_start,
            "t_end": t_end,
        })

        if op.get("checkpoint"):
            checkpoint_idx += 1
            snapshots[checkpoint_idx] = adapter.snapshot()
            snapshot_ts[checkpoint_idx] = _utc_now_iso()

    # ── log export + log-only replays (RF) ─────────────────────────
    log = adapter.export_log() or []

    replays: Dict[int, dict] = {}
    t0 = time.time()
    for k in sorted(snapshots):
        replays[k] = adapter.replay_at(k, snapshot_ts[k])
    replay_seconds = time.time() - t0
    replay_cost = {"events": len(log), "seconds": round(replay_seconds, 4)}

    return {
        "scenario_name": scenario.get("name", "?"),
        "e_exec": e_exec,
        "snapshots": snapshots,
        "replays": replays,
        "replay_cost": replay_cost,
        "log": log,
        "answers": answers,
    }


def score_run(artifacts: Dict[str, Any]) -> Dict[str, Any]:
    """Apply the three SPEC §2 metrics to a run's artifacts."""
    from eval.rab.scorer import score_ac, score_pc, score_rf
    return {
        "scenario": artifacts.get("scenario_name"),
        "AC": score_ac(artifacts["e_exec"], artifacts["log"]),
        "RF": score_rf(artifacts["snapshots"], artifacts["replays"],
                       artifacts.get("replay_cost")),
        "PC": score_pc(artifacts["log"]),
        "n_log_events": len(artifacts["log"]),
    }


__all__ = ["load_scenario", "run_scenario", "score_run"]
