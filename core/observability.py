"""Observability — trace_id propagation + structured stage logs (#47, Axis 3 phase 1).

Phase 1 scope: foundation for end-to-end request tracing. Issues a
`trace_id` (uuid7, time-sortable) at the API edge, propagates via
`contextvars.ContextVar` (no per-call kwarg pollution), and writes a
per-trace JSONL file under `reports/trace/<YYYY-MM-DD>/`.

What lives outside this module (deferred to phase 2):
  - `GET /admin/trace/{trace_id}` endpoint that reads back the JSONL.
  - `/admin/metrics` per-stage latency histograms (rolling window).
  - Auto-pruning of trace files older than 7 days.

Why ContextVar rather than threading.local:
  - FastAPI runs handlers on `asyncio` tasks. `threading.local` does
    not isolate per-task, so a concurrent second request would clobber
    the first request's `trace_id`. ContextVar isolates correctly under
    both threading and asyncio.

Per-trace file layout:
  reports/trace/2026-05-07/01HZX...abc.jsonl

  Each line is one JSON object:
    {"trace_id": "...", "stage": "retrieve", "ts_ns": 1746..., ...fields}

Cheap reads (one file == one trace) and no global JSONL contention.
The reports/trace/ tree is gitignored (per-run artifact, not committed).

Usage from a request handler:

    from core.observability import start_trace, log_stage

    @app.post("/query/")
    async def query(...):
        trace_id = start_trace()              # set ContextVar at edge
        log_stage("auth", role=role, allowed=allowed)
        ...
        log_stage("retrieve", top_k=8, top_vector_score=0.82)
        ...
        return {"trace_id": trace_id, ...}

Fire-and-forget: `log_stage` swallows IO errors so a disk-full event
never crashes a live query. Failures are silent — the request still
succeeds and the operator notices via missing traces.

Console mirror (operator workflow):
  Default ON — `log_stage` mirrors every JSONL line to stdout in
  addition to the per-trace file. This is the v2 default (single-user
  operator setup is the dominant case). Set `JAMES_TRACE_STDOUT=0`
  (or `false` / `no`) to silence the console while keeping the JSONL
  files. The mirror is wrapped in try so a cp949 console encoding
  crash can never wedge a live request.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Optional


# ContextVar empty default — `log_stage` no-ops when called outside a
# tracked request (defensive backwards compat with code paths that
# import this module but aren't yet instrumented at the edge).
current_trace_id: ContextVar[str] = ContextVar("current_trace_id", default="")


# Resolved lazily on first write. We can't compute at import time
# because the project root depends on `config.BASE_DIR`, which itself
# depends on environment / .env. ENV override exists primarily for
# tests (point traces at a tmpdir).
_TRACE_ROOT_OVERRIDE: Optional[Path] = None


def _trace_root() -> Path:
    if _TRACE_ROOT_OVERRIDE is not None:
        return _TRACE_ROOT_OVERRIDE
    # Default: <project_root>/reports/trace
    here = Path(__file__).resolve().parent.parent
    return here / "reports" / "trace"


def set_trace_root(path: Optional[Path]) -> None:
    """Test-only: redirect trace files at a tmpdir.

    Pass `None` to revert to the default `<project_root>/reports/trace`.
    Production code never calls this — it's a regression-test seam.
    """
    global _TRACE_ROOT_OVERRIDE
    _TRACE_ROOT_OVERRIDE = path


def _trace_file_for(trace_id: str) -> Path:
    """Per-trace file path: reports/trace/<YYYY-MM-DD>/<trace_id>.jsonl."""
    day = datetime.now().strftime("%Y-%m-%d")
    return _trace_root() / day / f"{trace_id}.jsonl"


def start_trace(trace_id: Optional[str] = None) -> str:
    """Generate (or accept) a trace_id and bind it to the current context.

    Call this at the API edge — exactly once per inbound request.
    Returns the trace_id so the handler can put it in the response
    body (so users can quote it when reporting issues).

    `trace_id=None` (default) generates a fresh uuid7 (time-sortable;
    Python 3.14+). Pass an explicit string to accept an externally-
    propagated id (e.g. a downstream service handing JAMES a parent
    span — out of scope for v0.2 but the seam exists).
    """
    if trace_id is None:
        trace_id = uuid.uuid7().hex
    current_trace_id.set(trace_id)
    return trace_id


def get_trace_id() -> str:
    """Return the current request's trace_id, or "" if not in a tracked
    context. Useful for embedding in legacy `print` lines + JSONL
    audit records during the gradual instrumentation rollout."""
    return current_trace_id.get()


def log_stage(stage: str, **fields) -> None:
    """Append one JSONL line to the current trace's file.

    No-op when `current_trace_id` is empty (uninstrumented entry path).
    Swallows IO errors — a disk-full event must not crash a live query.

    Args:
      stage:  short identifier — `auth` / `policy` / `retrieve` /
              `rerank` / `graph` / `tool` / `answer` / `complete`.
              See ROADMAP Axis 3 for the canonical stage table.
      **fields: stage-specific structured fields. Values must be
                JSON-serialisable (str / int / float / bool / list /
                dict / None). Non-serialisable values are coerced to
                str so a stale `repr` never blocks a live request.
    """
    tid = current_trace_id.get()
    if not tid:
        return
    entry = {
        "trace_id": tid,
        "stage":    stage,
        "ts_ns":    time.time_ns(),
        **fields,
    }
    line = json.dumps(entry, ensure_ascii=False, default=str)
    try:
        path = _trace_file_for(tid)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        # Silent — observability must never wedge a request on disk
        # failure. Operators see the gap (missing trace) and act.
        pass
    # Stdout mirror — default ON for the single-user operator setup.
    # Set JAMES_TRACE_STDOUT=0 (or false / no) to silence the console
    # while keeping the JSONL files. Wrapped in try so a cp949 console
    # encoding crash can never wedge a live request.
    if os.getenv("JAMES_TRACE_STDOUT", "1").strip().lower() not in ("0", "false", "no", ""):
        try:
            print(f"[trace {tid[:8]}] {line}", flush=True)
        except Exception:
            pass


def read_trace(trace_id: str, day: Optional[str] = None) -> list:
    """Read back all stage entries for a trace. Phase-1 helper used by
    tests and (in phase 2) by the `/admin/trace/{id}` endpoint.

    `day` defaults to today (YYYY-MM-DD). Pass an explicit day if the
    trace is from an earlier run.
    """
    if day is None:
        day = datetime.now().strftime("%Y-%m-%d")
    path = _trace_root() / day / f"{trace_id}.jsonl"
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out
