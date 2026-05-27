"""F6 (LEO L.D follow-up, 2026-05-27) — q15 entity-extraction stochasticity audit.

Idea 1 (PR #530) observed q15 ("David Soria Parra가 누구야?") landing
zero Path Recall on one bench run despite prior F4/F5 acceptance runs
finding the expected `David Soria Parra → MCP` path. F2 (PR #531)
ruled out the IntentClassifier as the cause (100% mode accuracy) and
the policy gate (F1's JWT bearer pattern bypasses it).

The residual variance must live downstream of the classifier — in
the retrieval pipeline itself. Candidates:
  (a) LLM-side entity extraction (gemma call may pick different
      tokens between runs given low temperature but non-zero noise)
  (b) ChromaDB rerank ordering (with similar low-score docs, top-k
      cutoff can swap unrelated content into the prompt)
  (c) Graph DFS expansion choosing a different seed entity if (a)
      shifts the entity match

This script measures whether the variance is reproducible — repeats
q15 N times against a single fresh server, parses graph_paths from
each response, reports per-run extracted node sets + agreement with
the expected nodes (David Soria Parra, MCP). Output:
``reports/research-runs/q15-repeat-audit-<stamp>.json``.

Server lifecycle: spawns its own uvicorn (same pattern as
bench_lc_scope_arms.py) with employee-role JWT in the request so the
``query.internal_rag`` policy gate doesn't kick the request to
handle_chat.

Usage
-----
    python scripts/research/q15_repeat_audit.py            # N=5
    python scripts/research/q15_repeat_audit.py --runs 10
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
from typing import Dict, List, Optional

import requests

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

try:
    from utils.console import ensure_utf8_console
    ensure_utf8_console()
except Exception:
    pass

# Reuse the Idea 1 path-node parser so the F6 audit and the bench-time
# path_metrics agree byte-for-byte on what counts as a "node hit".
from scripts.bench import _parse_path_nodes  # noqa: E402


REPORTS_DIR = ROOT / "reports" / "research-runs"
SERVER_BASE_URL = os.environ.get("JAMES_BASE_URL", "http://127.0.0.1:8000")
SERVER_HEALTHZ = SERVER_BASE_URL.rstrip("/") + "/healthz"
SERVER_BOOT_TIMEOUT_SEC = int(os.environ.get("JAMES_SERVER_BOOT_TIMEOUT", "120"))

# q15 — the documented variance case. See Idea 1 result doc §"q15
# is a tracking issue, not an Idea 1 blocker" and F2 reattribution.
Q15_TEXT = "David Soria Parra가 누구야?"
Q15_EXPECTED_NODES = {"David Soria Parra", "MCP"}


# ─── server lifecycle (mirrors bench_lc_scope_arms.py) ────────────


def _port_in_use(host: str, port: int) -> bool:
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        return sock.connect_ex((host, port)) == 0
    finally:
        sock.close()


def _parse_host_port(base_url: str):
    from urllib.parse import urlparse
    u = urlparse(base_url)
    return (u.hostname or "127.0.0.1", int(u.port or 8000))


def _wait_for_healthz(timeout_sec: int) -> bool:
    import urllib.request
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(SERVER_HEALTHZ, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(1.0)
    return False


def _spawn_server(env: Dict[str, str]) -> Optional[subprocess.Popen]:
    host, port = _parse_host_port(SERVER_BASE_URL)
    if _port_in_use(host, port):
        print(f"[server] {host}:{port} already in use — refusing to spawn")
        return None
    cmd = [
        sys.executable, "-m", "uvicorn", "server_llmwiki:app",
        "--host", host, "--port", str(port),
    ]
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    proc = subprocess.Popen(
        cmd, env=env, cwd=str(ROOT),
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
        creationflags=creationflags,
    )
    print(f"[server] spawned pid={proc.pid}, waiting for /healthz…")
    if not _wait_for_healthz(SERVER_BOOT_TIMEOUT_SEC):
        _shutdown_server(proc)
        return None
    return proc


def _shutdown_server(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
    time.sleep(2.0)


def _mint_employee_jwt() -> Optional[str]:
    try:
        from core.auth import create_token
        return create_token("q15-audit-runner", "employee")
    except Exception as e:
        print(f"[auth] JWT mint failed: {type(e).__name__}: {e}")
        return None


def _load_api_key() -> str:
    env_v = os.environ.get("JAMES_API_KEY")
    if env_v:
        return env_v.strip()
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8-sig").splitlines():
            if line.startswith("JAMES_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("JAMES_API_KEY not set")


# ─── one query → parsed nodes ─────────────────────────────────────


def _run_once(api_key: str, bearer: str, run_idx: int) -> Dict:
    body = {
        "question":      Q15_TEXT,
        "api_key":       api_key,
        "session_id":    f"q15_audit_{run_idx}",
        "mode_override": "retrieval",
    }
    headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
    t0 = time.time()
    try:
        r = requests.post(
            f"{SERVER_BASE_URL}/query/",
            json=body, headers=headers, timeout=180,
        )
        elapsed = time.time() - t0
    except Exception as e:
        return {
            "run": run_idx, "status": "error",
            "error": f"{type(e).__name__}: {str(e)[:200]}",
            "elapsed": round(time.time() - t0, 1),
        }
    if r.status_code != 200:
        return {
            "run": run_idx, "status": "http_error",
            "http_status": r.status_code,
            "body": (r.text or "")[:200],
            "elapsed": round(elapsed, 1),
        }
    data = r.json() or {}
    paths = data.get("graph_paths") or []
    nodes = _parse_path_nodes(paths)
    hits = nodes & Q15_EXPECTED_NODES
    return {
        "run":               run_idx,
        "status":            "ok",
        "elapsed":           round(elapsed, 1),
        "mode":              data.get("mode", ""),
        "graph_paths_count": len(paths),
        "node_count":        len(nodes),
        "hits_expected":     sorted(hits),
        "missed_expected":   sorted(Q15_EXPECTED_NODES - hits),
        "path_recall":       (
            round(len(hits) / len(Q15_EXPECTED_NODES), 3)
            if Q15_EXPECTED_NODES else None
        ),
        # Sample of actual nodes (first 10) — useful for "which OTHER
        # entities did the extractor latch onto" diagnosis without
        # exploding the report size for graphs with 30+ nodes.
        "nodes_sample":      sorted(nodes)[:10],
        "answer_len":        len(data.get("answer") or ""),
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="F6 — repeat-run q15 to measure entity-extraction variance.",
    )
    ap.add_argument("--runs", type=int, default=5,
                    help="number of repeated /query/ POSTs (default 5)")
    args = ap.parse_args()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # Same env contract as bench_lc_scope_arms.py — D5 router on so the
    # routing decisions are observable, scope routing on so the L.C path
    # actually binds. The audit is about retrieval-pipeline variance,
    # not router decisions, but keeping the same env gives the operator
    # apples-to-apples comparison with the Idea 1 acceptance run.
    server_env = os.environ.copy()
    server_env["JAMES_AUTO_ROUTER"] = "1"
    server_env["JAMES_SCOPE_ROUTING"] = "1"

    print(f"=== q15 repeat-run audit (N={args.runs}) ===")
    print(f"query:    {Q15_TEXT}")
    print(f"expected: {sorted(Q15_EXPECTED_NODES)}")
    print()

    server = _spawn_server(server_env)
    if server is None:
        print("[server] boot failed — aborting")
        return 1

    bearer = _mint_employee_jwt()
    if not bearer:
        print("[auth] no JWT — request will likely fall to chat-mode")

    api_key = _load_api_key()

    runs: List[Dict] = []
    try:
        for i in range(1, args.runs + 1):
            r = _run_once(api_key, bearer, i)
            runs.append(r)
            if r["status"] == "ok":
                print(
                    f"  run {i:2}: {r['elapsed']:>6.1f}s | "
                    f"paths={r['graph_paths_count']:>3d} nodes={r['node_count']:>3d} "
                    f"recall={r['path_recall']:.2f} hits={r['hits_expected']}"
                )
            else:
                print(f"  run {i:2}: {r['status']} — {r.get('error') or r.get('body')!s}")
    finally:
        _shutdown_server(server)

    # ─── summary ──────────────────────────────────────────────────
    ok_runs = [r for r in runs if r["status"] == "ok"]
    summary: Dict = {"runs": args.runs, "ok_runs": len(ok_runs)}
    if ok_runs:
        recalls = [r["path_recall"] for r in ok_runs]
        summary.update({
            "mean_path_recall":          round(sum(recalls) / len(recalls), 3),
            "runs_at_full_recall":       sum(1 for x in recalls if x == 1.0),
            "runs_at_zero_recall":       sum(1 for x in recalls if x == 0.0),
            "runs_hit_david_soria_parra": sum(
                1 for r in ok_runs if "David Soria Parra" in r["hits_expected"]
            ),
            "runs_hit_mcp": sum(
                1 for r in ok_runs if "MCP" in r["hits_expected"]
            ),
            "graph_paths_count_min": min(r["graph_paths_count"] for r in ok_runs),
            "graph_paths_count_max": max(r["graph_paths_count"] for r in ok_runs),
        })

    print()
    print("=== Summary ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = REPORTS_DIR / f"q15-repeat-audit-{stamp}.json"
    out_path.write_text(
        json.dumps({
            "generated_at": datetime.now().isoformat(),
            "query":        Q15_TEXT,
            "expected_nodes": sorted(Q15_EXPECTED_NODES),
            "runs":         runs,
            "summary":      summary,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nsaved: {out_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
