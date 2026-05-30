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


def _resolve_bearer() -> str:
    """Return the JWT bearer for retrieval-mode bench access.

    Precedence:
      1. ``JAMES_BENCH_BEARER`` env (operator-provided, e.g. a token
         minted with a specific role for a targeted scenario).
      2. Auto-mint an admin token via ``core.auth.create_token`` and
         emit a stderr warning so the operator knows where the token
         came from.

    The fallback exists because ``/query/`` routes through
    ``query.internal_rag``, which blocks external role and silently
    falls through to ``handle_chat`` (``mode="chat"``,
    ``graph_paths_count=0``). Without a bearer, bench numbers reflect
    chat-passthrough latency, not RAG-path latency — a category
    mistake easy to miss because the script still exits 0.

    Surfaced 2026-05-29 during M4 step7 baseline reproduction: an
    attempt to re-measure the 2026-05-28 baseline yielded ~6× faster
    totals + ``graph_paths_total=0``, traced to ``JAMES_BENCH_BEARER``
    being unset in the new session. Same code, same fixture, same
    sha — only the bearer presence differed. See
    ``feedback_bench_step7_chat_mode_passthrough`` for the original
    2026-05-27 diagnostic, and
    ``reports/research-runs/step7-bench-variance-analysis-2026-05-29.md``
    §10 for the follow-up.
    """
    env_v = os.environ.get("JAMES_BENCH_BEARER", "").strip()
    if env_v:
        return env_v
    try:
        from core.auth import create_token
    except Exception as e:
        print(
            f"[bench] WARN: could not import core.auth.create_token "
            f"({e!r}). Proceeding without bearer — expect chat-passthrough "
            f"numbers (mode=chat, graph_paths_count=0).",
            file=sys.stderr,
        )
        return ""
    token = create_token("bench", "admin")
    print(
        "[bench] JAMES_BENCH_BEARER not set — auto-minted admin token "
        "for RAG-path measurement (subject=bench, role=admin). Set the "
        "env var to override (e.g. role=employee for tier checks).",
        file=sys.stderr,
    )
    return token


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
    """Locate suite fixture. Two search locations, in order:

    1. ``eval/regression/{name}_queries.json`` (project-root canonical,
       used by step7 and any future internal regression suites).
    2. ``$JAMES_WORKSPACE/eval/{name}_queries.json`` (workspace-relative,
       used by external benchmark suites like ``multihop_rag`` that live
       under ``workspaces/<name>/``). The workspace abstraction
       (config.py:74, ``core/plugins/workspace.py::get_workspace_root``)
       isolates the benchmark corpus + fixture from production state.

    Raises if neither location resolves — caller sees both attempted
    paths so a typo or missing build step is diagnosable in one read.
    """
    canonical = ROOT / "eval" / "regression" / f"{name}_queries.json"
    if canonical.exists():
        return json.loads(canonical.read_text(encoding="utf-8"))

    ws_raw = os.environ.get("JAMES_WORKSPACE", "").strip()
    if ws_raw:
        ws_path = Path(ws_raw).resolve() / "eval" / f"{name}_queries.json"
        if ws_path.exists():
            return json.loads(ws_path.read_text(encoding="utf-8"))
        # Workspace set but file missing — surface it explicitly.
        raise RuntimeError(
            f"suite definition not found:\n"
            f"  tried: {canonical}\n"
            f"  tried: {ws_path}\n"
            f"  hint:  build it first (e.g. scripts/hotpot/build_fixture.py)"
        )
    raise RuntimeError(
        f"suite definition not found: {canonical}\n"
        f"(set JAMES_WORKSPACE to also search a benchmark workspace's eval/)"
    )


def _parse_path_nodes(path_strs) -> set:
    """Extract entity node names from JAMES graph-path strings.

    Path string format (from `core.graph_engine.expand_dynamic`):
        "<source> -[REL(w=0.7)]→ <target1> -[REL(w=0.7)]→ <target2> …"
    where the entity-name token between separators is the wiki entity
    name (`name:` frontmatter field) — or, for relation targets, the
    `target` string from the relation dict (usually matches the wiki
    name; falls back to the entity_id when not declared).

    Returns the set of unique node names spanning all paths. Used by
    `_path_metrics` to compute Path Recall against the suite's
    `expected_path.nodes` ground truth (Idea 1, 2026-05-27).
    """
    nodes = set()
    if not path_strs:
        return nodes
    for ps in path_strs:
        if not isinstance(ps, str):
            continue
        # Source name is everything before the first " -[".
        parts = ps.split(" -[")
        if parts and parts[0].strip():
            nodes.add(parts[0].strip())
        # Subsequent parts are "REL(w=X)]→ target_name" — target follows ']→ '.
        for part in parts[1:]:
            if "]→ " in part:
                target = part.split("]→ ", 1)[1].strip()
                # Strip any trailing fragment if a later " -[" gets eaten
                # by this iteration (defensive — the split-by " -[" above
                # already isolates these in practice).
                if target:
                    nodes.add(target)
    return nodes


def _path_metrics(actual_paths, expected_nodes) -> Optional[Dict]:
    """Compute Path Recall / Precision against the suite's expected nodes.

    Idea 1 schema:
        expected_path.nodes — list of wiki-canonical entity names the
        query's answer should traverse. Per-query Recall = how many of
        those nodes appear in the actual graph_paths returned by /query.

    Returns None when `expected_nodes` is empty (skip metric — caller
    omits the field from the per-query row). Otherwise returns a dict:

        {
          "expected_count": int,
          "actual_node_count": int,    # unique nodes across all paths
          "hits": int,                 # |expected ∩ actual|
          "path_recall": float,        # hits / expected_count, [0, 1]
          "path_precision": float,     # hits / actual_node_count, [0, 1]
          "missed": list[str],         # expected nodes NOT found
        }

    Path Precision is reported but interpreted with care — `actual` is
    every node the DFS ever touched (typically 5–50 per query), not the
    "answer-evidence" subset, so precision will read low even on good
    runs. Recall is the primary signal.
    """
    if not expected_nodes:
        return None
    actual = _parse_path_nodes(actual_paths)
    expected = set(expected_nodes)
    hits = actual & expected
    actual_count = len(actual)
    return {
        "expected_count": len(expected),
        "actual_node_count": actual_count,
        "hits": len(hits),
        "path_recall": round(len(hits) / len(expected), 3),
        "path_precision": (
            round(len(hits) / actual_count, 3) if actual_count else 0.0
        ),
        "missed": sorted(expected - actual),
    }


def _load_baseline(name: str) -> Optional[Dict]:
    path = ROOT / "eval" / "regression" / f"{name}_baseline.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _run_one(
    api_key: str, q: Dict, endpoint: str, timeout: int,
    default_mode: Optional[str] = None,
    bearer: str = "",
) -> Dict:
    """Run a single query against the live server. Returns the row dict that
    bench reports operate on.

    ``default_mode``: server-side ``mode_override`` value to apply when the
    suite or per-query entry doesn't pin one. Precedence:
    ``q["mode"] > default_mode > omit field``. Passing a value bypasses
    the server's IntentClassifier and forces routing to that mode (e.g.
    ``"retrieval"`` for L.D evidence-scope measurement which would
    otherwise hit chat-mode passthrough). See
    ``feedback_bench_step7_chat_mode_passthrough`` for context.

    ``bearer``: JWT bearer for retrieval-mode bench access. Resolved
    once in ``main()`` via ``_resolve_bearer()`` and passed in so every
    query reuses the same token (consistent expiry window across the
    whole suite). External role is policy-blocked from
    ``query.internal_rag`` and falls through to ``handle_chat``, so
    without a bearer the bench reports chat-passthrough numbers.
    """
    t0 = time.time()
    body: Dict = {
        "question":   q["text"],
        "api_key":    api_key,
        "session_id": f"bench_step7_{q['id']}",
    }
    mode_override = q.get("mode") or default_mode
    if mode_override:
        body["mode_override"] = mode_override
    headers = {}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    try:
        r = requests.post(
            f"{BASE_URL}{endpoint}",
            json=body,
            headers=headers,
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
    # α-5 plan Step 6 — preserve fixture's `question_type` for cross-tab
    # analysis (MultiHop-RAG inference/comparison/temporal/null_query).
    # Quietly skipped when the suite doesn't carry the field (step7).
    if "question_type" in q:
        base["question_type"] = q["question_type"]

    if r.status_code != 200:
        base.update({
            "status":      "http_error",
            "http_status": r.status_code,
            "error_body":  (r.text or "")[:200],
        })
        return base

    data = r.json() or {}
    answer = (data.get("answer") or "").strip()
    actual_paths = data.get("graph_paths") or []
    base.update({
        "status":            "ok",
        "answer_len":        len(answer),
        "answer_preview":    answer[:300],   # smaller than the old 600 — preview only
        "blocked":           bool(data.get("blocked", False)),
        "graph_paths_count": len(actual_paths),
        "mode":              data.get("mode", ""),
        "unified_score":     data.get("unified_score"),
    })
    # Idea 1 (2026-05-27) — Path Recall/Precision when the suite
    # declares `expected_path.nodes`. Queries without the field skip.
    expected_path = q.get("expected_path") or {}
    expected_nodes = expected_path.get("nodes") or []
    pm = _path_metrics(actual_paths, expected_nodes)
    if pm is not None:
        base["path_metrics"] = pm
    return base


def _print_row(r: Dict, total: int) -> None:
    """One-line summary identical in shape to the old runner — operators read
    this column-aligned."""
    head = f"[{r['id']:2d}/{total}] {r['category']:9s} | {r['text'][:55]}"
    if r["status"] == "ok":
        tag = "BLOCK" if r.get("blocked") else "OK"
        pm = r.get("path_metrics")
        path_tail = (
            f" | path_recall={pm['path_recall']:.2f} ({pm['hits']}/{pm['expected_count']})"
            if pm else ""
        )
        print(f"{head}\n      {tag:<5s} {r['elapsed']:>5.1f}s | "
              f"mode={r.get('mode','')!s:<15s} | "
              f"graph_paths={r.get('graph_paths_count', 0):>2d} | "
              f"answer_len={r.get('answer_len', 0):>4d}{path_tail}")
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
    ap.add_argument(
        "--mode", default=None,
        help=(
            "server-side mode_override applied to every query that doesn't "
            "declare its own `mode` field. Bypasses the IntentClassifier "
            "(e.g. --mode=retrieval forces RAG path for L.D evidence-scope "
            "measurement which otherwise hits chat-mode passthrough). "
            "Precedence: per-query `mode` > --mode > suite `default_mode` > omit."
        ),
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help=("Resolve the suite + print plan (count, version, fixture path); "
              "make no HTTP calls and write no bench JSON. Used by the α-5 "
              "wiring smoke check before any compute is spent."),
    )
    args = ap.parse_args()

    suite = _load_suite(args.suite)
    queries = suite.get("queries", [])
    if args.dry_run:
        print(f"=== bench {args.suite} dry-run ===")
        print(f"version:       {suite.get('version', '?')}")
        print(f"description:   {(suite.get('description') or '')[:120]}")
        print(f"queries:       {len(queries)}")
        # Surface question_type distribution if present (multihop_rag fixture
        # builder emits it — useful sanity for the Step 3 → Step 4 wiring).
        dist = suite.get("type_distribution")
        if dist:
            print("type_distribution:")
            for t, n in dist.items():
                print(f"  {t}: {n}")
        return 0

    endpoint = (suite.get("endpoint") or {}).get("url", "/query/")
    timeout  = int((suite.get("endpoint") or {}).get("timeout", 120))
    effective_default_mode = args.mode or suite.get("default_mode")

    api_key = _load_api_key()
    bearer  = _resolve_bearer()
    print(f"=== bench {args.suite} ({len(queries)} queries) ===\n")
    if effective_default_mode:
        print(f"[bench] mode_override default: {effective_default_mode!r} "
              f"(per-query `mode` field still wins)\n")

    results: List[Dict] = []
    t_total = time.time()
    for q in queries:
        res = _run_one(
            api_key, q, endpoint, timeout, effective_default_mode, bearer,
        )
        results.append(res)
        _print_row(res, len(queries))
    total = round(time.time() - t_total, 1)

    sha = _git_sha()
    out_dir = ROOT / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"bench_{sha}_{args.suite}_{stamp}.json"

    # Idea 1 aggregate — mean Path Recall across queries that declared
    # `expected_path.nodes`. None when no query carries the field.
    recalls = [
        r["path_metrics"]["path_recall"]
        for r in results
        if r.get("status") == "ok" and r.get("path_metrics") is not None
    ]
    path_recall_aggregate = (
        {
            "queries_with_expected_path": len(recalls),
            "mean_path_recall": round(sum(recalls) / len(recalls), 3),
            "queries_at_full_recall": sum(1 for x in recalls if x == 1.0),
        }
        if recalls
        else None
    )

    out_path.write_text(
        json.dumps({
            "suite":         args.suite,
            "git_sha":       sha,
            "total_seconds": total,
            "queries":       len(queries),
            "results":       results,
            "path_recall_aggregate": path_recall_aggregate,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n총 소요: {total}s ({round(total/60, 1)}분)")
    print(f"saved: {out_path.relative_to(ROOT)}")
    if path_recall_aggregate:
        agg = path_recall_aggregate
        print(
            f"path recall: mean={agg['mean_path_recall']:.2f} "
            f"({agg['queries_at_full_recall']}/{agg['queries_with_expected_path']} at 1.0)"
        )

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
