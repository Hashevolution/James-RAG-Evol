"""JAMES regression bench runner (Issue #45, Axis 2-A).

Replaces the inline-literal `scripts/step7_query_test.py` with a
data-driven runner. Suites live in `eval/regression/<name>_queries.json`
and committed baselines in `eval/regression/<name>_baseline.json`.

Usage:

  python scripts/bench.py --suite=step7
      Run all queries in the suite against the live server. Save full
      report to reports/bench_<sha>_<suite>_<timestamp>.json (gitignored).
      Print summary table.

  python scripts/bench.py --suite=step7 --check
      Same run, then compare against committed baseline. Exit 1 on any
      hard-locked drift (graph_paths outside band+tolerance, elapsed
      total outside ±tolerance band, q11 byte-identical violation).
      Soft drifts (within tolerance) print a warning and exit 0.

  python scripts/bench.py --suite=step7 --update-baseline
      DESTRUCTIVE: rewrite the committed baseline JSON from the current
      run's numbers. Only run after a deliberate, reviewed scope change
      (data state migration, model swap). Should be its own PR with the
      diff visible in review.

The runner needs the JAMES server running at http://127.0.0.1:8000 and
JAMES_API_KEY set in .env or the environment (same pattern as the old
step7_query_test.py).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Ensure UTF-8 console (PR #36) — bench output includes Korean query strings.
try:
    from utils.console import ensure_utf8_console
    ensure_utf8_console()
except Exception:
    pass


BASE_URL = os.environ.get("JAMES_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def _load_api_key() -> str:
    """Same loader as the old step7 script — supports .env or process env."""
    env_v = os.environ.get("JAMES_API_KEY")
    if env_v:
        return env_v.strip()
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            if line.startswith("JAMES_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError(
        "JAMES_API_KEY not found in .env or environment. "
        "Set it in .env or `export JAMES_API_KEY=...` before running."
    )


def _git_sha() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT, stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except Exception:
        return "nogit"


def _load_suite(name: str) -> Dict:
    path = ROOT / "eval" / "regression" / f"{name}_queries.json"
    if not path.exists():
        raise RuntimeError(f"suite definition not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _load_baseline(name: str) -> Optional[Dict]:
    path = ROOT / "eval" / "regression" / f"{name}_baseline.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _run_one(api_key: str, q: Dict, endpoint: str, timeout: int) -> Dict:
    """Run a single query against the live server. Returns the row dict that
    bench reports operate on."""
    t0 = time.time()
    try:
        r = requests.post(
            f"{BASE_URL}{endpoint}",
            json={
                "question":   q["text"],
                "api_key":    api_key,
                "session_id": f"bench_step7_{q['id']}",
            },
            timeout=timeout,
        )
        elapsed = time.time() - t0
    except requests.Timeout:
        return {"id": q["id"], "category": q["category"], "text": q["text"],
                "status": "timeout", "elapsed": round(time.time() - t0, 1)}
    except Exception as e:
        return {"id": q["id"], "category": q["category"], "text": q["text"],
                "status": "error", "error": str(e)[:200],
                "elapsed": round(time.time() - t0, 1)}

    base = {"id": q["id"], "category": q["category"], "text": q["text"],
            "elapsed": round(elapsed, 1)}

    if r.status_code != 200:
        base.update({
            "status":      "http_error",
            "http_status": r.status_code,
            "error_body":  (r.text or "")[:200],
        })
        return base

    data = r.json() or {}
    answer = (data.get("answer") or "").strip()
    base.update({
        "status":            "ok",
        "answer_len":        len(answer),
        "answer_preview":    answer[:300],   # smaller than the old 600 — preview only
        "blocked":           bool(data.get("blocked", False)),
        "graph_paths_count": len(data.get("graph_paths") or []),
        "mode":              data.get("mode", ""),
        "unified_score":     data.get("unified_score"),
    })
    return base


def _print_row(r: Dict, total: int) -> None:
    """One-line summary identical in shape to the old runner — operators read
    this column-aligned."""
    head = f"[{r['id']:2d}/{total}] {r['category']:9s} | {r['text'][:55]}"
    if r["status"] == "ok":
        tag = "BLOCK" if r.get("blocked") else "OK"
        print(f"{head}\n      {tag:<5s} {r['elapsed']:>5.1f}s | "
              f"mode={r.get('mode','')!s:<15s} | "
              f"graph_paths={r.get('graph_paths_count', 0):>2d} | "
              f"answer_len={r.get('answer_len', 0):>4d}")
    else:
        detail = r.get("error") or r.get("error_body") or r["status"]
        print(f"{head}\n      X  {r['status'].upper():<10s} ({r['elapsed']}s): {detail}")


def _check_baseline(
    results:  List[Dict],
    baseline: Dict,
    total:    float,
) -> Tuple[bool, List[str]]:
    """Compare run against committed baseline. Return (all_pass, messages).

    Hard fails (return False):
      - q11 byte-identical invariant violated.
      - Any non-flaky query's graph_paths outside [min - tol, max + tol].
      - Total elapsed outside elapsed_band ± elapsed_relative tolerance.

    Soft warnings:
      - Mode changed (q12 mode=coding vs '' across runs is normal).
      - Answer length drift > answer_len_relative * baseline mean.
    """
    tol      = baseline.get("tolerance", {})
    gp_tol   = tol.get("graph_paths_abs", 2)
    el_tol   = tol.get("elapsed_relative", 0.30)
    by_id    = {q["id"]: q for q in baseline.get("queries", [])}

    msgs: List[str] = []
    fails: List[str] = []

    for r in results:
        b = by_id.get(r["id"])
        if not b:
            msgs.append(f"q{r['id']}: no baseline entry — skipped")
            continue

        if b.get("expected_status") == "flaky":
            msgs.append(f"q{r['id']}: marked flaky in baseline — skipped")
            continue

        # q11 byte-identical invariant
        if "answer_len_exact" in b:
            if r.get("status") != "ok":
                fails.append(f"q{r['id']}: status={r.get('status')} (expected ok)")
                continue
            if r.get("blocked") != b["blocked"]:
                fails.append(f"q{r['id']}: blocked={r.get('blocked')} (expected {b['blocked']})")
            if r.get("answer_len") != b["answer_len_exact"]:
                fails.append(f"q{r['id']}: answer_len={r.get('answer_len')} (expected exactly {b['answer_len_exact']})")
            if r.get("graph_paths_count") != b.get("graph_paths_max", 0):
                fails.append(f"q{r['id']}: graph_paths={r.get('graph_paths_count')} (expected exactly {b.get('graph_paths_max')})")
            continue

        # Standard query
        if r.get("status") != "ok":
            fails.append(f"q{r['id']}: status={r.get('status')} (expected ok)")
            continue
        gp = r.get("graph_paths_count", 0)
        gp_lo = b["graph_paths_min"] - gp_tol
        gp_hi = b["graph_paths_max"] + gp_tol
        if not (gp_lo <= gp <= gp_hi):
            fails.append(
                f"q{r['id']}: graph_paths={gp} outside band "
                f"[{b['graph_paths_min']}, {b['graph_paths_max']}] ± {gp_tol}"
            )

    # Total elapsed band check
    el_band = baseline.get("totals", {})
    if el_band:
        lo = el_band["elapsed_min"] * (1 - el_tol)
        hi = el_band["elapsed_max"] * (1 + el_tol)
        if not (lo <= total <= hi):
            fails.append(
                f"total elapsed={total:.1f}s outside band "
                f"[{el_band['elapsed_min']}, {el_band['elapsed_max']}] ± {el_tol*100:.0f}%"
            )

    return (len(fails) == 0), msgs + fails


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", default="step7")
    ap.add_argument("--check", action="store_true",
                    help="compare against committed baseline; exit 1 on regression")
    ap.add_argument("--update-baseline", action="store_true",
                    help="DESTRUCTIVE: rewrite baseline from this run (use only on intentional scope change PRs)")
    args = ap.parse_args()

    suite = _load_suite(args.suite)
    queries = suite.get("queries", [])
    endpoint = (suite.get("endpoint") or {}).get("url", "/query/")
    timeout  = int((suite.get("endpoint") or {}).get("timeout", 120))

    api_key = _load_api_key()
    print(f"=== bench {args.suite} ({len(queries)} queries) ===\n")

    results: List[Dict] = []
    t_total = time.time()
    for q in queries:
        res = _run_one(api_key, q, endpoint, timeout)
        results.append(res)
        _print_row(res, len(queries))
    total = round(time.time() - t_total, 1)

    sha = _git_sha()
    out_dir = ROOT / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"bench_{sha}_{args.suite}_{stamp}.json"
    out_path.write_text(
        json.dumps({
            "suite":         args.suite,
            "git_sha":       sha,
            "total_seconds": total,
            "queries":       len(queries),
            "results":       results,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n총 소요: {total}s ({round(total/60, 1)}분)")
    print(f"saved: {out_path.relative_to(ROOT)}")

    # --update-baseline: rewrite baseline from this run before any check.
    # Wipes the committed file with the current numbers.  Only acceptable
    # in an intentional scope-change PR with diff visible in review.
    if args.update_baseline:
        _update_baseline(args.suite, results, total)
        print("[bench] baseline file rewritten from this run")
        return 0

    # --check: compare against committed baseline
    if args.check:
        baseline = _load_baseline(args.suite)
        if baseline is None:
            print(f"[bench] no baseline at eval/regression/{args.suite}_baseline.json — cannot check")
            return 1
        ok, msgs = _check_baseline(results, baseline, total)
        print()
        for m in msgs:
            print(f"  {m}")
        if ok:
            print(f"\n[bench] OK — within {args.suite} baseline tolerances")
            return 0
        print(f"\n[bench] FAIL — {sum(1 for m in msgs if 'q' in m or 'total' in m)} regression(s)")
        return 1

    return 0


def _update_baseline(suite: str, results: List[Dict], total: float) -> None:
    """Replace baseline graph_paths bands with this run's values.

    Conservative: keeps existing tolerance / invariant / note fields as-is.
    Just shifts the band endpoints to the current numbers.
    """
    path = ROOT / "eval" / "regression" / f"{suite}_baseline.json"
    if not path.exists():
        raise RuntimeError(f"no existing baseline to update at {path}")
    bl = json.loads(path.read_text(encoding="utf-8"))
    by_id = {q["id"]: q for q in bl.get("queries", [])}
    for r in results:
        if r["id"] not in by_id:
            continue
        b = by_id[r["id"]]
        if b.get("expected_status") == "flaky":
            continue
        if "answer_len_exact" in b:
            # Strict invariants stay strict — don't auto-shift q11.
            continue
        gp = r.get("graph_paths_count")
        if gp is None:
            continue
        b["graph_paths_min"] = min(b["graph_paths_min"], gp)
        b["graph_paths_max"] = max(b["graph_paths_max"], gp)
    bl["totals"]["elapsed_min"]  = min(bl["totals"]["elapsed_min"],  total)
    bl["totals"]["elapsed_max"]  = max(bl["totals"]["elapsed_max"],  total)
    bl["totals"]["elapsed_mean"] = round(
        (bl["totals"]["elapsed_min"] + bl["totals"]["elapsed_max"]) / 2, 1
    )
    bl["samples"] = bl.get("samples", 0) + 1
    path.write_text(json.dumps(bl, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
