"""live_eval — 실사용(real-use) 트래픽 → 평가 루프 하니스.

Why this exists (v0.6.1 design review, 2026-07-01)
--------------------------------------------------
JAMES already *captures* everything a real-use evaluation needs —
`james_audit.db` (every query/answer/latency/block),
`workspace/feedback_shadow.jsonl` (👍/👎 signals from chat.js), and the
per-trace JSONL under `reports/trace/`. What was missing is the
connective tissue: nothing read that live traffic back OUT into an
evaluation artefact. Benchmarks (STEP7 / QVT / RAB / LRB) all run on
hand-authored fixtures; the operator's actual phone-dogfood queries
never became regression material.

This harness closes the loop with two subcommands:

  report   Join audit_log × feedback_shadow over a time window and
           print a real-use quality report (volume, block rate,
           LLM-error rate, abstention rate, latency percentiles,
           feedback summary, worst queries). Optional JSON output for
           dashboards / tracking over time.

  promote  Select real queries (default: those that received negative
           feedback) into ``eval/regression/live_queries.json`` — the
           same suite format ``scripts/bench.py`` already consumes, so

               python scripts/bench.py --suite=live_queries

           replays yesterday's real failures against today's build.
           Promotion is merge-safe: existing entries keep their ids and
           any operator-added ``gold_signals`` / ``expected_path``
           enrichment; re-promoting the same query text is a no-op.

Both subcommands are read-only with respect to production state
(promote writes only the eval fixture). No live LLM needed — this is
offline analysis of already-captured traffic, so it runs anywhere the
repo + the data files exist.

Usage:
  python scripts/live_eval.py report [--days 7] [--db PATH] [--json OUT]
  python scripts/live_eval.py promote [--days 7] [--all] [--limit 20]
                                      [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT_DB = ROOT / "james_audit.db"
DEFAULT_SHADOW = ROOT / "workspace" / "feedback_shadow.jsonl"
DEFAULT_SUITE = ROOT / "eval" / "regression" / "live_queries_queries.json"

# Answer-text markers, mirroring the taxonomy the runtime itself uses:
#   errors — core/gemma_client/errors.ERROR_PREFIXES family
#   abstention — engine_synth NO_INFO family ("자료에 없음" normalisation)
ERROR_MARKERS = ("[Gemma 오류]", "[Gemma 응답 없음]", "[Gemma Vision 오류]")
ABSTENTION_MARKERS = (
    "자료에 없",
    "자료에는 없",
    "자료에는 직접 언급이 없",
    "insufficient information",
)

# Negative / positive signal names from core/feedback_engine.FEEDBACK_SIGNALS.
NEGATIVE_SIGNALS = {"explicit_negative", "implicit_negative", "correction",
                    "objection"}
POSITIVE_SIGNALS = {"explicit_positive", "implicit_positive"}


# ─── Data loading ──────────────────────────────────────────────────

def load_audit_rows(db_path: Path, since: datetime,
                    endpoint_prefix: str = "/query") -> List[Dict]:
    """Read audit_log rows for user-facing query endpoints since ``since``.

    Returns plain dicts (no sqlite3.Row leakage) so callers/tests can
    build fixtures easily. Missing DB → empty list (a fresh install has
    no traffic yet; the report should say so, not crash).
    """
    if not Path(db_path).exists():
        return []
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT timestamp, user_role, endpoint, query, answer,
                      graph_paths, blocked, security_event, elapsed_sec
               FROM audit_log
               WHERE endpoint LIKE ? AND timestamp >= ?
               ORDER BY timestamp ASC""",
            (endpoint_prefix + "%", since.isoformat()),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def load_feedback_entries(shadow_path: Path, since: datetime) -> List[Dict]:
    """Read feedback_shadow.jsonl entries since ``since``.

    Tolerates missing file and malformed lines (append-only JSONL
    written by a live server can have a torn final line).
    """
    p = Path(shadow_path)
    if not p.exists():
        return []
    out: List[Dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = entry.get("time", "")
        if ts and ts >= since.isoformat():
            out.append(entry)
    return out


# ─── Metrics ───────────────────────────────────────────────────────

def _percentile(sorted_vals: List[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(int(len(sorted_vals) * q), len(sorted_vals) - 1)
    return sorted_vals[idx]


def _classify_answer(answer: str) -> str:
    a = answer or ""
    if any(m in a for m in ERROR_MARKERS):
        return "error"
    if any(m in a for m in ABSTENTION_MARKERS):
        return "abstention"
    return "answered"


def build_report(rows: List[Dict], feedback: List[Dict],
                 window_days: int) -> Dict:
    """Compute the real-use quality report as a plain dict.

    Feedback ↔ query join: feedback entries carry ``query[:80]`` (see
    FeedbackEngine.accumulate); audit rows carry ``query[:500]``. Join
    on the 80-char prefix — deterministic and independent of the md5
    direction_id (which hashes mode+query and can't be inverted).
    """
    total = len(rows)
    blocked = sum(1 for r in rows if r.get("blocked"))
    latencies = sorted(
        float(r.get("elapsed_sec") or 0.0)
        for r in rows if not r.get("blocked")
    )
    kinds = {"answered": 0, "abstention": 0, "error": 0}
    for r in rows:
        if not r.get("blocked"):
            kinds[_classify_answer(r.get("answer") or "")] += 1

    # Feedback summary + negative-feedback query texts.
    sig_counts: Dict[str, int] = {}
    neg_queries: Dict[str, int] = {}
    pos_count = neg_count = 0
    for e in feedback:
        sig = e.get("signal", "")
        sig_counts[sig] = sig_counts.get(sig, 0) + 1
        if sig in NEGATIVE_SIGNALS:
            neg_count += 1
            q = (e.get("query") or "").strip()
            if q:
                neg_queries[q] = neg_queries.get(q, 0) + 1
        elif sig in POSITIVE_SIGNALS:
            pos_count += 1

    # Slowest non-blocked queries (top 5).
    slowest = sorted(
        (r for r in rows if not r.get("blocked")),
        key=lambda r: float(r.get("elapsed_sec") or 0.0),
        reverse=True,
    )[:5]

    answered_total = max(1, total - blocked)
    return {
        "window_days": window_days,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total_queries": total,
        "blocked": blocked,
        "block_rate": round(blocked / total, 3) if total else 0.0,
        "answered": kinds["answered"],
        "abstention": kinds["abstention"],
        "abstention_rate": round(kinds["abstention"] / answered_total, 3),
        "llm_errors": kinds["error"],
        "llm_error_rate": round(kinds["error"] / answered_total, 3),
        "latency": {
            "p50": round(_percentile(latencies, 0.50), 2),
            "p90": round(_percentile(latencies, 0.90), 2),
            "p99": round(_percentile(latencies, 0.99), 2),
            "max": round(latencies[-1], 2) if latencies else 0.0,
        },
        "feedback": {
            "total": len(feedback),
            "positive": pos_count,
            "negative": neg_count,
            "by_signal": sig_counts,
        },
        "negative_feedback_queries": [
            {"query": q, "count": c}
            for q, c in sorted(neg_queries.items(), key=lambda kv: -kv[1])
        ],
        "slowest_queries": [
            {"query": (r.get("query") or "")[:80],
             "elapsed_sec": round(float(r.get("elapsed_sec") or 0.0), 1),
             "timestamp": r.get("timestamp", "")}
            for r in slowest
        ],
    }


def format_report_md(rep: Dict) -> str:
    """Render the report dict as operator-readable markdown."""
    fb = rep["feedback"]
    lines = [
        f"# 실사용 평가 리포트 (최근 {rep['window_days']}일)",
        "",
        f"- 생성: {rep['generated_at']}",
        f"- 총 질의: **{rep['total_queries']}** "
        f"(차단 {rep['blocked']}, 차단율 {rep['block_rate']:.1%})",
        f"- 정상 답변: {rep['answered']} · "
        f"무응답(자료 없음): {rep['abstention']} "
        f"({rep['abstention_rate']:.1%}) · "
        f"LLM 오류: {rep['llm_errors']} ({rep['llm_error_rate']:.1%})",
        f"- 지연 (비차단): p50 {rep['latency']['p50']}s / "
        f"p90 {rep['latency']['p90']}s / p99 {rep['latency']['p99']}s / "
        f"max {rep['latency']['max']}s",
        f"- 피드백: 총 {fb['total']} (👍 {fb['positive']} / 👎 {fb['negative']})",
        "",
    ]
    if rep["negative_feedback_queries"]:
        lines.append("## 👎 부정 피드백 질의 (promote 후보)")
        for item in rep["negative_feedback_queries"]:
            lines.append(f"- ({item['count']}×) {item['query']}")
        lines.append("")
    if rep["slowest_queries"]:
        lines.append("## 🐢 최다 지연 질의 (top 5)")
        for item in rep["slowest_queries"]:
            lines.append(
                f"- {item['elapsed_sec']}s — {item['query']}")
        lines.append("")
    lines.append(
        "다음 단계: `python scripts/live_eval.py promote` 로 부정 피드백 "
        "질의를 `eval/regression/live_queries_queries.json` 에 승격 → "
        "`python scripts/bench.py --suite=live_queries` 로 리플레이.")
    return "\n".join(lines)



# ─── Promotion ─────────────────────────────────────────────────────

def _empty_suite() -> Dict:
    return {
        "version": "live-v1",
        "description": (
            "Real-use regression suite — queries promoted from live "
            "traffic by scripts/live_eval.py. Each entry records why it "
            "was promoted (negative feedback / operator pick). Operators "
            "may enrich entries with gold_signals / expected_path over "
            "time; promotion NEVER overwrites existing enrichment. "
            "Replay: python scripts/bench.py --suite=live_queries"
        ),
        "endpoint": {"url": "/query/", "method": "POST", "timeout": 120},
        "queries": [],
    }


def load_suite(path: Path) -> Dict:
    if Path(path).exists():
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return _empty_suite()


def promote_queries(suite: Dict, candidates: List[Dict]) -> Dict:
    """Merge candidate queries into the suite (idempotent).

    ``candidates``: [{"text": ..., "reason": ..., "first_seen": ...}].
    Existing entries are matched by exact query text and left
    untouched (ids stable, operator enrichment preserved).
    """
    existing_texts = {q.get("text", "") for q in suite.get("queries", [])}
    next_id = 1 + max(
        (int(q.get("id", 0)) for q in suite.get("queries", [])), default=0,
    )
    added = 0
    for cand in candidates:
        text = (cand.get("text") or "").strip()
        if not text or text in existing_texts:
            continue
        suite["queries"].append({
            "id": next_id,
            "category": "live",
            "text": text,
            "promoted": {
                "reason": cand.get("reason", "operator"),
                "first_seen": cand.get("first_seen", ""),
                "promoted_at": datetime.now().isoformat(timespec="seconds"),
            },
        })
        existing_texts.add(text)
        next_id += 1
        added += 1
    suite["_last_promotion_added"] = added
    return suite


def collect_candidates(rows: List[Dict], feedback: List[Dict],
                       include_all: bool = False,
                       limit: int = 20) -> List[Dict]:
    """Pick promotion candidates from the window's traffic.

    Default: queries with negative feedback (join on the 80-char query
    prefix, same rule as build_report). ``include_all`` adds every
    distinct non-blocked query in the window (rate-limited by
    ``limit``, newest first) for corpus-building sessions.
    """
    # audit rows by 80-char prefix → full text + first_seen
    by_prefix: Dict[str, Dict] = {}
    for r in rows:
        if r.get("blocked"):
            continue
        q = (r.get("query") or "").strip()
        if not q:
            continue
        key = q[:80]
        if key not in by_prefix:
            by_prefix[key] = {"text": q, "first_seen": r.get("timestamp", "")}

    out: List[Dict] = []
    seen = set()
    for e in feedback:
        if e.get("signal") not in NEGATIVE_SIGNALS:
            continue
        key = (e.get("query") or "").strip()[:80]
        if not key or key in seen:
            continue
        seen.add(key)
        hit = by_prefix.get(key, {"text": key, "first_seen": e.get("time", "")})
        out.append({**hit, "reason": "negative_feedback"})

    if include_all:
        for key, hit in sorted(by_prefix.items(),
                               key=lambda kv: kv[1]["first_seen"],
                               reverse=True):
            if key in seen:
                continue
            if len(out) >= limit:
                break
            seen.add(key)
            out.append({**hit, "reason": "window_sample"})
    return out


# ─── CLI ───────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--days", type=int, default=7,
                        help="lookback window in days (default 7)")
    common.add_argument("--db", default=str(DEFAULT_DB),
                        help="james_audit.db path")
    common.add_argument("--shadow", default=str(DEFAULT_SHADOW),
                        help="feedback_shadow.jsonl path")

    p_rep = sub.add_parser("report", parents=[common],
                           help="real-use quality report")
    p_rep.add_argument("--json", dest="json_out", default="",
                       help="also write the raw report dict to this path")

    p_pro = sub.add_parser("promote", parents=[common],
                           help="promote live queries into the bench suite")
    p_pro.add_argument("--suite", default=str(DEFAULT_SUITE),
                       help="target suite JSON (bench.py format)")
    p_pro.add_argument("--all", action="store_true",
                       help="also sample non-feedback queries from the window")
    p_pro.add_argument("--limit", type=int, default=20,
                       help="max sampled queries with --all (default 20)")
    p_pro.add_argument("--dry-run", action="store_true",
                       help="print candidates without writing the suite")

    args = ap.parse_args(argv)
    since = datetime.now() - timedelta(days=args.days)
    rows = load_audit_rows(Path(args.db), since)
    feedback = load_feedback_entries(Path(args.shadow), since)

    if args.cmd == "report":
        rep = build_report(rows, feedback, args.days)
        print(format_report_md(rep))
        if args.json_out:
            out = Path(args.json_out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(rep, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            print(f"\n[live_eval] JSON → {out}")
        return 0

    # promote
    candidates = collect_candidates(rows, feedback,
                                    include_all=args.all, limit=args.limit)
    if not candidates:
        print("[live_eval] promote 후보 없음 (창 내 부정 피드백 질의 0건)")
        return 0
    if args.dry_run:
        for c in candidates:
            print(f"- [{c['reason']}] {c['text'][:100]}")
        print(f"[live_eval] dry-run — {len(candidates)}건 (미기록)")
        return 0
    suite_path = Path(args.suite)
    suite = load_suite(suite_path)
    suite = promote_queries(suite, candidates)
    added = suite.pop("_last_promotion_added", 0)
    suite_path.parent.mkdir(parents=True, exist_ok=True)
    suite_path.write_text(
        json.dumps(suite, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[live_eval] {added}건 신규 승격 (총 {len(suite['queries'])}건) "
          f"→ {suite_path}")
    print("[live_eval] 리플레이: python scripts/bench.py --suite=live_queries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
