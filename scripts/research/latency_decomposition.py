"""Where a JAMES query's wall-clock actually goes, from the audit log.

The 2026-09-22 QVT baseline capture ran at ~146 s per query and nobody
could say which part was expensive. stdout does not carry stage timings
(memory ``feedback_stdout_vs_audit_log_trace_split``) — the ``audit_log``
table does, and every stage already writes a row there.

This reconstructs per-query timelines from those rows and splits the
wall clock into stages, so a latency claim is a measurement rather than
an impression. It opens a committed SQLite DB read-only and spawns
nothing, so it is safe to run while a measurement is in flight.

Method
------
Rows are ordered by ``id`` and split into *episodes* at each ``/query/``
row (written when a query completes). ``blocked`` episodes are dropped:
step7 ships security fixtures that are *supposed* to be refused, and
counting them would distort both latency and failure rates.

Within an episode the gap between two consecutive events is attributed
to the **later** event, because audit rows are written *after* the
operation they describe. A gap ending at ``system:WARN:gemma.timeout``
is therefore time spent on an LLM call that produced nothing — the
distinction this tool exists to make.

Usage
-----
    python scripts/research/latency_decomposition.py --since 2026-09-22T09:43
    python scripts/research/latency_decomposition.py --since ... --md
"""
from __future__ import annotations

import argparse
import sqlite3
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB = ROOT / "james_audit.db"

QUERY_ROW = "/query/"
TIMEOUT_ROW = "system:WARN:gemma.timeout"
# A longer gap means the harness was idle between queries, not that one
# stage took an hour. Excluded rather than silently inflating a stage.
MAX_PLAUSIBLE_GAP_S = 3600.0


def _ts(raw: str) -> datetime:
    return datetime.fromisoformat(raw)


def load_episodes(db: Path, since: str, until: str) -> List[List[tuple]]:
    """Answerable query episodes in the window, oldest first."""
    con = sqlite3.connect("file:{}?mode=ro".format(db.as_posix()), uri=True)
    try:
        rows = list(con.execute(
            "select id, timestamp, endpoint, blocked, elapsed_sec "
            "from audit_log where timestamp between ? and ? order by id",
            (since, until),
        ))
    finally:
        con.close()

    episodes: List[List[tuple]] = []
    current: List[tuple] = []
    for row in rows:
        current.append(row)
        if row[2] == QUERY_ROW:
            episodes.append(current)
            current = []
    return [e for e in episodes if not e[-1][3]]


def decompose(episodes: List[List[tuple]]) -> Dict[str, Any]:
    cost: Dict[str, List[float]] = defaultdict(list)
    walls: List[float] = []
    timeout_gaps: List[float] = []
    per_query: List[Tuple[float, float, int]] = []
    after_timeout: Counter = Counter()
    stage_seen: Counter = Counter()

    for ep in episodes:
        wall = (_ts(ep[-1][1]) - _ts(ep[0][1])).total_seconds()
        walls.append(wall)
        # Count occurrences over every row, but price only the gaps we
        # can measure. A timeout that opens an episode has no preceding
        # event to measure against — it still happened, and classifying
        # that query as "clean" would undercount the failure silently.
        n_to = sum(1 for row in ep if row[2] == TIMEOUT_ROW)
        to_sum = 0.0
        for a, b in zip(ep, ep[1:]):
            gap = (_ts(b[1]) - _ts(a[1])).total_seconds()
            if not (0 <= gap < MAX_PLAUSIBLE_GAP_S):
                continue
            cost[b[2]].append(gap)
            if b[2] == TIMEOUT_ROW:
                to_sum += gap
                timeout_gaps.append(gap)
            if b[2].startswith("reason:"):
                stage_seen[b[2]] += 1
                if a[2] == TIMEOUT_ROW:
                    after_timeout[b[2]] += 1
        per_query.append((wall, to_sum, n_to))

    total_wall = sum(walls)
    clean = [w for w, _t, n in per_query if n == 0]
    dirty = [(w, t) for w, t, n in per_query if n > 0]
    return {
        "n_queries": len(episodes),
        "attributed_s": sum(sum(v) for v in cost.values()),
        "wall_mean_s": statistics.mean(walls) if walls else 0.0,
        "timeout_s": sum(timeout_gaps),
        "timeout_n": len(timeout_gaps),
        "timeout_share": (sum(timeout_gaps) / total_wall) if total_wall else 0.0,
        "timeout_gaps": sorted({round(g) for g in timeout_gaps}),
        "cost": cost,
        "stage_seen": stage_seen,
        "after_timeout": after_timeout,
        "clean_n": len(clean),
        "clean_mean_s": statistics.mean(clean) if clean else None,
        "dirty_n": len(dirty),
        "dirty_mean_s": statistics.mean([w for w, _ in dirty]) if dirty else None,
        "floor_s": (statistics.mean([w - t for w, t, _ in per_query])
                    if per_query else None),
    }


def stage_table(d: Dict[str, Any]) -> List[Tuple[str, int, float, float, float, float]]:
    """(stage, n, total_s, pct_of_attributed, s_per_query, mean_s)."""
    total = d["attributed_s"] or 1.0
    n_q = d["n_queries"] or 1
    return [
        (name, len(gaps), sum(gaps), 100 * sum(gaps) / total,
         sum(gaps) / n_q, statistics.mean(gaps))
        for name, gaps in sorted(d["cost"].items(), key=lambda kv: -sum(kv[1]))
    ]


def render_text(d: Dict[str, Any]) -> str:
    n_q = max(d["n_queries"], 1)
    out = [
        "queries            : {}".format(d["n_queries"]),
        "wall mean          : {:.1f} s/query".format(d["wall_mean_s"]),
        "timeout total      : {:.1f} min ({:.1f} s/query, n={})".format(
            d["timeout_s"] / 60, d["timeout_s"] / n_q, d["timeout_n"]),
        "TIMEOUT SHARE      : {:.1f}% of wall clock".format(100 * d["timeout_share"]),
        "timeout gap values : {} s".format(d["timeout_gaps"]),
        "",
        "{:40} {:>5} {:>9} {:>6} {:>8} {:>8}".format(
            "stage", "n", "total_s", "%", "s/query", "mean_s"),
    ]
    for name, n, s, pct, per_q, mean in stage_table(d):
        out.append("{:40} {:>5} {:>9.1f} {:>5.1f}% {:>8.1f} {:>8.1f}".format(
            name, n, s, pct, per_q, mean))
    out += ["", "stage logged immediately after a timeout "
                "(its LLM call produced nothing):"]
    for name, seen in d["stage_seen"].most_common():
        n = d["after_timeout"].get(name, 0)
        out.append("  {:20} {:>4}/{:<4} = {:5.1f}%".format(
            name, n, seen, 100 * n / seen))
    out.append("")
    out.append("queries with zero timeouts : {}{}".format(
        d["clean_n"],
        " (mean {:.1f} s)".format(d["clean_mean_s"]) if d["clean_mean_s"] else ""))
    out.append("queries with timeouts      : {}{}".format(
        d["dirty_n"],
        " (mean {:.1f} s)".format(d["dirty_mean_s"]) if d["dirty_mean_s"] else ""))
    if d["floor_s"] is not None:
        out.append("floor if nothing timed out : {:.1f} s/query".format(d["floor_s"]))
    return "\n".join(out)


def render_markdown(d: Dict[str, Any], since: str, until: str) -> str:
    n_q = max(d["n_queries"], 1)
    out = [
        "Window `{}` .. `{}` — **{} answerable queries**, wall mean "
        "**{:.1f} s**.".format(since, until, d["n_queries"], d["wall_mean_s"]),
        "",
        "**Timeout share: {:.1f}%** of wall clock ({:.1f} s/query, n={}); "
        "observed gap budgets {} s.".format(
            100 * d["timeout_share"], d["timeout_s"] / n_q,
            d["timeout_n"], d["timeout_gaps"]),
        "",
        "Floor if no call ever timed out: **{:.1f} s/query**.".format(d["floor_s"]),
        "",
        "| stage | n | total s | % | s/query | mean s |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, n, s, pct, per_q, mean in stage_table(d):
        out.append("| `{}` | {} | {:.1f} | {:.1f}% | {:.1f} | {:.1f} |".format(
            name, n, s, pct, per_q, mean))
    out += ["", "| stage | logged after a timeout | share |", "|---|---:|---:|"]
    for name, seen in d["stage_seen"].most_common():
        n = d["after_timeout"].get(name, 0)
        out.append("| `{}` | {}/{} | {:.1f}% |".format(name, n, seen, 100 * n / seen))
    return "\n".join(out)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Decompose JAMES query latency from the audit log.")
    p.add_argument("--db", default=str(DEFAULT_DB))
    p.add_argument("--since", required=True, help="ISO timestamp, inclusive")
    p.add_argument("--until", default="2100-01-01", help="ISO timestamp")
    p.add_argument("--md", action="store_true", help="markdown instead of text")
    a = p.parse_args(argv)

    db = Path(a.db)
    if not db.is_file():
        print("[error] audit db not found: {}".format(db))
        return 2
    episodes = load_episodes(db, a.since, a.until)
    if not episodes:
        print("[error] no answerable query episodes in {}..{}".format(
            a.since, a.until))
        return 3
    d = decompose(episodes)
    print(render_markdown(d, a.since, a.until) if a.md else render_text(d))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
