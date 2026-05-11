"""Per-stage latency aggregation over recent traces — #81 phase 3-B.

Walks `reports/trace/<YYYY-MM-DD>/*.jsonl` for a sliding window
(default 24 hours), computes per-stage latency from consecutive
`ts_ns` deltas within the same trace, and returns p50/p90/p99/max +
sample count per stage.

Why per-trace deltas rather than per-line `latency_ms` fields
- Existing `log_stage` calls don't all carry an explicit `latency_ms`
  field. Some do (`log_stage("answer", latency_ms=...)`) but most
  don't. Computing from consecutive `ts_ns` is the only universal
  signal we have without changing every call site.
- The trade-off: this measures wall-clock between log_stage emissions,
  not the actual stage cost. Close enough for operator dashboards
  at v0.2 scale; bigger surgery is post-v0.3 plugin contract work.

Why in-memory aggregation rather than a time-series DB
- v0.2 single-user / single-tenant target. A bench-suite-driven day
  produces low hundreds of traces. Reading + aggregating in-memory
  is fine. Multi-worker / multi-tenant aggregation is v1.0+ scope.

Window semantics
- `window_hours` defines a `now() - window_hours` cutoff.
- Day-partitioned files past the cutoff are skipped at the directory
  level (cheap). Within the most recent partition, entries before
  the cutoff are filtered per-line.
"""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional


def _percentile(sorted_values: List[float], p: float) -> float:
    """p in [0, 100]. Standard nearest-rank percentile (no interpolation —
    keeps the function dependency-free)."""
    if not sorted_values:
        return 0.0
    if p <= 0:
        return sorted_values[0]
    if p >= 100:
        return sorted_values[-1]
    rank = math.ceil((p / 100.0) * len(sorted_values))
    rank = max(1, min(rank, len(sorted_values)))
    return sorted_values[rank - 1]


def _stage_latencies_from_trace(entries: List[dict]) -> Dict[str, float]:
    """Given one trace's entries (chronological), return {stage_name:
    latency_ms}. Latency is the wall-clock from this stage's `ts_ns`
    to the next stage's `ts_ns` (or to the trace's end for the last).

    Notes:
      - Entries must be ordered by ts_ns; we sort defensively.
      - Stages can repeat within a trace (e.g. retrieve loop). Each
        occurrence contributes its own latency sample.
      - Returns a flat list-shape via dict — caller flattens by stage.
    """
    if len(entries) < 2:
        return {}
    # Defensive sort — JSONL append order is normally chronological
    # but some edge cases (mid-write race) could permute.
    ordered = sorted(entries, key=lambda e: e.get("ts_ns", 0))
    out: Dict[str, List[float]] = {}
    for i in range(len(ordered) - 1):
        cur = ordered[i]
        nxt = ordered[i + 1]
        stage = cur.get("stage")
        if not stage:
            continue
        try:
            delta_ns = int(nxt["ts_ns"]) - int(cur["ts_ns"])
        except Exception:
            continue
        if delta_ns < 0:
            continue
        out.setdefault(stage, []).append(delta_ns / 1_000_000.0)  # ns → ms
    # If the last stage carries an explicit latency_ms, include it
    # as its own sample. Lets a precisely-instrumented final stage
    # contribute to its own metric.
    last = ordered[-1]
    if isinstance(last.get("latency_ms"), (int, float)):
        out.setdefault(last["stage"], []).append(float(last["latency_ms"]))
    # Flatten into the {stage: list_of_ms} shape we return — but the
    # function signature says Dict[str, float]. Caller actually wants
    # all samples, so we change return shape via the public function.
    return out  # type: ignore[return-value]


def aggregate_metrics(
    window_hours: int                = 24,
    stage_filter: Optional[str]      = None,
    now:          Optional[datetime] = None,
    trace_root:   Optional[Path]     = None,
) -> Dict[str, dict]:
    """Walk `reports/trace/` for the window, return per-stage stats.

    Args:
      window_hours: how far back to look (clamped to [1, 168] = 1 week).
      stage_filter: if set, return only that stage. Useful for
                    `/admin/metrics?stage=retrieve`.
      now:          test seam — defaults to datetime.now().
      trace_root:   test seam — defaults to <project>/reports/trace.

    Returns:
      {stage_name: {count, p50_ms, p90_ms, p99_ms, max_ms}}
      Empty dict when no traces in window.
    """
    # Clamp the window — operators asking for "all of time" usually
    # want a sensible default, not an unbounded scan.
    window = max(1, min(int(window_hours or 24), 168))
    cutoff = (now or datetime.now()) - timedelta(hours=window)
    cutoff_ns = int(cutoff.timestamp() * 1_000_000_000)

    root = trace_root or (Path(__file__).resolve().parent.parent / "reports" / "trace")
    if not root.exists():
        return {}

    # Day-partitioned: skip whole days past the cutoff cheaply.
    cutoff_day = cutoff.strftime("%Y-%m-%d")

    samples: Dict[str, List[float]] = {}
    for day_dir in root.iterdir():
        if not day_dir.is_dir():
            continue
        if day_dir.name < cutoff_day:
            continue
        for trace_file in day_dir.glob("*.jsonl"):
            try:
                entries = []
                with trace_file.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            e = json.loads(line)
                        except Exception:
                            continue
                        # Per-line cutoff filter for the day right at
                        # the boundary.
                        if e.get("ts_ns", 0) < cutoff_ns:
                            continue
                        entries.append(e)
                if not entries:
                    continue
                per_trace = _stage_latencies_from_trace(entries)
                for stage, lats in per_trace.items():
                    if stage_filter and stage != stage_filter:
                        continue
                    samples.setdefault(stage, []).extend(lats)
            except Exception:
                # One bad file must not break the whole aggregation.
                continue

    out: Dict[str, dict] = {}
    for stage, lats in samples.items():
        if not lats:
            continue
        sorted_lats = sorted(lats)
        out[stage] = {
            "count":  len(sorted_lats),
            "p50_ms": round(_percentile(sorted_lats, 50), 2),
            "p90_ms": round(_percentile(sorted_lats, 90), 2),
            "p99_ms": round(_percentile(sorted_lats, 99), 2),
            "max_ms": round(sorted_lats[-1], 2),
        }
    return out
