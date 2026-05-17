"""L2 — reconstruct one question's reasoning trace from audit_log.

ARCHITECTURE.md §5.7.2 trace-replay invariant:

    "The full reasoning trace must be reconstructable from audit_bridge
    rows alone. No ephemeral in-memory state may carry decision
    rationale that audit cannot replay."

L1 wired 12 call_gemma sites to emit one TraceStep row each. Each row
carries the request-level ``trace_id`` (from Axis-3 ContextVar) packed
into the answer JSON blob. This script unpacks those rows for one
``trace_id`` and prints the reasoning sequence — the proof that the
invariant holds for v0.3.0 onwards.

Usage:

  python scripts/replay_trace.py <trace_id>
      Pretty-print the reasoning steps in chronological order.

  python scripts/replay_trace.py <trace_id> --json
      Same data as JSON list (one object per row) for programmatic use.

  python scripts/replay_trace.py --recent [--limit N]
      List the N most recent trace_ids that have reason:* rows. Handy
      for finding a trace_id to inspect when the operator forgets which
      question they asked.

  python scripts/replay_trace.py <trace_id> --db PATH
      Override the default james_audit.db path (resolved relative to
      core.audit_bridge._DEFAULT_AUDIT_DB).

Exit codes:
  0 — found ≥ 1 row (or --recent listed ≥ 0 ids)
  1 — trace_id has no rows / DB unreachable / bad args
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# UTF-8 console — output includes Korean output_summary strings.
try:
    from utils.console import ensure_utf8_console
    ensure_utf8_console()
except Exception:
    pass

from core.reasoning.trace_schema import TraceStep, ALLOWED_STAGES   # noqa: E402


def _resolve_db_path(override: Optional[str]) -> str:
    if override:
        return override
    try:
        from core.audit_bridge import _DEFAULT_AUDIT_DB
        return _DEFAULT_AUDIT_DB
    except ImportError:
        return "james_audit.db"


def _row_to_trace_step(row: sqlite3.Row) -> Optional[TraceStep]:
    """Reverse the emit_trace_step mapping (trace_schema.py).

    Returns None when the row cannot be parsed — replay is best-effort
    (the row stays in audit_log either way, available to manual SQL).
    """
    endpoint = row["endpoint"] or ""
    if not endpoint.startswith("reason:"):
        return None
    stage = endpoint[len("reason:"):]
    if stage not in ALLOWED_STAGES:
        return None

    query_field = row["query"] or ""
    backend_id, _, inputs_hash = query_field.partition(":")
    # _resolve_query strips the ": " separator; we accept "<bid>:<hash>"
    # or "<bid>: <hash>" (the bridge formats with a space when both halves
    # are non-empty).
    inputs_hash = inputs_hash.lstrip()

    answer_blob: Dict[str, Any] = {}
    if row["answer"]:
        try:
            answer_blob = json.loads(row["answer"])
        except json.JSONDecodeError:
            answer_blob = {}

    parent_step_id = str(answer_blob.get("parent_step_id", ""))
    output_summary = str(answer_blob.get("output_summary", ""))
    error_msg = str(answer_blob.get("error", ""))

    elapsed = row["elapsed_sec"]
    latency_ms = int(round(elapsed * 1000)) if elapsed else 0

    try:
        return TraceStep(
            stage=stage,
            backend_id=backend_id or "orchestrator",
            parent_step_id=parent_step_id,
            inputs_hash=inputs_hash,
            output_summary=output_summary,
            applied_rule=row["security_event"] or f"reasoning.{stage}",
            latency_ms=latency_ms,
            error=error_msg,
        )
    except (ValueError, TypeError):
        return None


def replay(
    trace_id: str,
    *,
    db_path: Optional[str] = None,
    include_extras: bool = False,
) -> List[Dict[str, Any]]:
    """Return reason:* rows for one trace_id as a list of dicts.

    Each dict has the TraceStep fields plus ``timestamp``, ``user_role``,
    and (when ``include_extras=True``) the full unparsed ``answer`` JSON.

    Chronological order by audit_log.id (insertion order ≈ wall-clock).
    Empty list = no rows for this trace_id.
    """
    if not trace_id:
        return []

    path = _resolve_db_path(db_path)
    if not os.path.exists(path):
        return []

    # Trace correlation lives in the answer JSON blob. SQLite's LIKE
    # against the JSON text is fine for the v0.3 row volume; if a future
    # production ever grows past hundreds of MB of audit rows we'd
    # promote trace_id to its own indexed column (separate PR).
    needle = f'"trace_id": "{trace_id}"'

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, timestamp, user_role, endpoint, query, answer,
                   blocked, security_event, elapsed_sec
            FROM   audit_log
            WHERE  endpoint LIKE 'reason:%' AND answer LIKE ?
            ORDER  BY id ASC
            """,
            (f"%{needle}%",),
        ).fetchall()
    finally:
        conn.close()

    out: List[Dict[str, Any]] = []
    for row in rows:
        step = _row_to_trace_step(row)
        if step is None:
            continue
        record: Dict[str, Any] = {
            **asdict(step),
            "timestamp":  row["timestamp"],
            "user_role":  row["user_role"],
            "blocked":    bool(row["blocked"]),
        }
        if include_extras and row["answer"]:
            try:
                blob = json.loads(row["answer"])
                # surface anything not already in TraceStep
                extras = {
                    k: v for k, v in blob.items()
                    if k not in {"parent_step_id", "output_summary", "error"}
                }
                if extras:
                    record["extras"] = extras
            except json.JSONDecodeError:
                pass
        out.append(record)
    return out


def list_recent_trace_ids(
    limit: int = 20,
    *,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List the ``limit`` most-recent trace_ids that have reason:* rows.

    Returned dicts: {trace_id, first_seen, last_seen, step_count}.
    Ordered by most-recent ``last_seen`` first.
    """
    path = _resolve_db_path(db_path)
    if not os.path.exists(path):
        return []

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        # Pull every reason:* row and bucket client-side. The volume is
        # bounded (one row per LLM call ≤ ~12 per query) so a scan is
        # cheap. SQLite's JSON1 extension would be cleaner but it's
        # optional in default builds; staying on plain Python keeps the
        # script portable.
        rows = conn.execute(
            """
            SELECT timestamp, answer
            FROM   audit_log
            WHERE  endpoint LIKE 'reason:%'
            ORDER  BY id ASC
            """
        ).fetchall()
    finally:
        conn.close()

    buckets: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not row["answer"]:
            continue
        try:
            blob = json.loads(row["answer"])
        except json.JSONDecodeError:
            continue
        tid = blob.get("trace_id")
        if not tid:
            continue
        ts = row["timestamp"] or ""
        b = buckets.get(tid)
        if b is None:
            buckets[tid] = {
                "trace_id":   tid,
                "first_seen": ts,
                "last_seen":  ts,
                "step_count": 1,
            }
        else:
            b["last_seen"]  = ts
            b["step_count"] += 1

    ordered = sorted(buckets.values(), key=lambda b: b["last_seen"], reverse=True)
    return ordered[:limit]


def _format_text(steps: List[Dict[str, Any]], trace_id: str) -> str:
    if not steps:
        return f"trace_id: {trace_id}\n(no reasoning rows found)"
    lines = [f"trace_id: {trace_id}",
             f"{'=' * (10 + len(trace_id))}"]
    for i, step in enumerate(steps, start=1):
        latency_s = step["latency_ms"] / 1000.0
        marker = "  X" if step["blocked"] else f"  {i:>2}"
        lines.append(
            f"\n[{marker}] {step['applied_rule']:<40} "
            f"{step['backend_id']:<14} {latency_s:>6.2f}s  "
            f"{step['timestamp']}"
        )
        if step["parent_step_id"]:
            lines.append(f"        parent: {step['parent_step_id']}")
        lines.append(f"        input:  {step['inputs_hash']}")
        if step["output_summary"]:
            lines.append(f"        output: {step['output_summary'][:120]}")
        if step["error"]:
            lines.append(f"        error:  {step['error']}")
        if step.get("extras"):
            extras_str = ", ".join(f"{k}={v}" for k, v in step["extras"].items())
            lines.append(f"        extras: {extras_str}")
    lines.append("")
    lines.append(f"{len(steps)} reasoning step(s)")
    return "\n".join(lines)


def _format_recent_text(buckets: List[Dict[str, Any]]) -> str:
    if not buckets:
        return "(no recent reasoning traces in audit_log)"
    lines = [f"{'trace_id':<34} {'step_count':>10}  {'last_seen':<26}",
             "-" * 75]
    for b in buckets:
        lines.append(
            f"{b['trace_id']:<34} {b['step_count']:>10}  {b['last_seen']:<26}"
        )
    return "\n".join(lines)


def _main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Replay one reasoning trace from audit_log",
    )
    ap.add_argument("trace_id", nargs="?",
                    help="trace_id to replay (omit when using --recent)")
    ap.add_argument("--recent", action="store_true",
                    help="list recent trace_ids instead of replaying one")
    ap.add_argument("--limit", type=int, default=20,
                    help="cap for --recent (default 20)")
    ap.add_argument("--json", action="store_true",
                    help="emit JSON instead of human-readable text")
    ap.add_argument("--extras", action="store_true",
                    help="include non-schema answer JSON fields per row")
    ap.add_argument("--db", default=None,
                    help="override audit DB path (default: core.audit_bridge resolution)")
    args = ap.parse_args(argv)

    if args.recent:
        buckets = list_recent_trace_ids(limit=args.limit, db_path=args.db)
        if args.json:
            print(json.dumps(buckets, ensure_ascii=False, indent=2))
        else:
            print(_format_recent_text(buckets))
        return 0

    if not args.trace_id:
        ap.error("trace_id is required unless --recent is given")

    steps = replay(args.trace_id, db_path=args.db, include_extras=args.extras)
    if args.json:
        print(json.dumps(steps, ensure_ascii=False, indent=2))
    else:
        print(_format_text(steps, args.trace_id))
    return 0 if steps else 1


if __name__ == "__main__":   # pragma: no cover
    raise SystemExit(_main())
