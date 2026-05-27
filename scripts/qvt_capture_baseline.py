"""QVT α-3 baseline capture — operator-runnable, paired N=3 rerun.

Spawns its own JAMES server with the v0.4.0 production env (entity
anchor + bge-m3 + query-rewrite ON, routing layers OFF — see memo §3),
runs ``scripts/bench.py --suite=step7 --mode=retrieval`` N=3 times,
applies the 3-axis oracle to each run, and writes the aggregated
baseline JSON to ``eval/qvt/baseline_<sha>.json``.

The output JSON is the immovable reference that every future
``Quality delta vs baseline_<sha>`` PR-gate comparison is paired
against. Re-capture only when the baseline environment intentionally
changes (e.g. embedding model swap, default-flag flip) — never
silently overwrite.

Operator workflow::

    # Stop any pre-existing JAMES server on 127.0.0.1:8000 first.
    python scripts/qvt_capture_baseline.py

Output (success)::

    eval/qvt/baseline_<sha>.json   (paired N=3 + noise band + aggregate)

Cost: ~16 queries × ~80s × 3 reruns ≈ 64 minutes. Plus server boot
(~30s × 3) and oracle scoring (~milliseconds). Budget ~70 minutes
on a small-tier-only fleet.

Cross-stack note: This wrapper holds the v0.4.0 production flags
fixed — same constraint as ``feedback_cross_stack_run_flag_off``.
Operator MUST NOT toggle JAMES_AUTO_ROUTER / SCOPE_ROUTING /
ADAPTIVE_BUDGET while a baseline capture is running.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Imported after sys.path manipulation so the script remains runnable
# from any cwd.
from eval.qvt.oracle import (  # noqa: E402
    ThreeAxisResult,
    score_three_axis,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SERVER_BASE_URL = os.environ.get("JAMES_BASE_URL", "http://127.0.0.1:8000")
SERVER_HEALTHZ = SERVER_BASE_URL.rstrip("/") + "/healthz"
SERVER_BOOT_TIMEOUT_SEC = 120
BENCH_SUBPROCESS_TIMEOUT_SEC = 2400

# v0.4.0 production baseline flags (memo §3). Routing layers OFF — they
# are the things being measured *against* this baseline by future PRs.
_BASELINE_ENV: Dict[str, str] = {
    "JAMES_ENABLE_ENTITY_ANCHOR": "1",
    "JAMES_EMBEDDING_MODEL": "BAAI/bge-m3",
    "JAMES_ENABLE_QUERY_REWRITE": "1",
    "JAMES_AUTO_ROUTER": "0",
    "JAMES_ADAPTIVE_BUDGET": "0",
    "JAMES_SCOPE_ROUTING": "0",
}

_FIXTURE_PATH = ROOT / "eval" / "regression" / "step7_queries.json"
_OUTPUT_DIR = ROOT / "eval" / "qvt"


# ---------------------------------------------------------------------------
# Server lifecycle helpers (paralleling bench_lc_scope_arms.py)
# ---------------------------------------------------------------------------

def _parse_host_port(url: str) -> Tuple[str, int]:
    stripped = url.replace("http://", "").replace("https://", "")
    host_part, _, rest = stripped.partition("/")
    host, _, port_str = host_part.partition(":")
    return host or "127.0.0.1", int(port_str or "8000")


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        try:
            sock.connect((host, port))
            return True
        except OSError:
            return False


def _wait_for_healthz(timeout_sec: int) -> bool:
    deadline = time.time() + timeout_sec
    last_err = "no attempt yet"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(SERVER_HEALTHZ, timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:80]}"
        time.sleep(1.0)
    print(f"[server] /healthz never returned 200 ({last_err})")
    return False


def _spawn_server(env: Dict[str, str]) -> Optional[subprocess.Popen]:
    host, port = _parse_host_port(SERVER_BASE_URL)
    if _port_in_use(host, port):
        print(
            f"[server] {host}:{port} already in use. Stop the existing "
            f"server before running this wrapper — env flags applied "
            f"here would not reach an operator-launched server."
        )
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
    print(f"[server] spawned pid={proc.pid} on {host}:{port}, waiting for /healthz…")
    if not _wait_for_healthz(SERVER_BOOT_TIMEOUT_SEC):
        _shutdown_server(proc)
        return None
    print("[server] healthy")
    return proc


def _shutdown_server(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        print(f"[server] pid={proc.pid} did not exit on terminate, killing")
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print(f"[server] pid={proc.pid} still alive after kill — orphaned")
    time.sleep(2.0)


def _mint_employee_jwt() -> Optional[str]:
    """Mint a short-lived employee-role JWT for the bench subprocess
    so the engine's ``query.internal_rag`` gate doesn't kick retrieval-
    mode requests back to ``handle_chat``."""
    try:
        from core.auth import create_token
        return create_token("qvt-baseline-runner", "employee")
    except Exception as e:
        print(f"[server] JWT mint failed ({type(e).__name__}: {e}) — "
              f"falling back to api_key-only auth (results will likely "
              f"show chat-mode passthrough)")
        return None


# ---------------------------------------------------------------------------
# Per-run execution
# ---------------------------------------------------------------------------

def _run_single_bench(run_index: int) -> Optional[Path]:
    """Spawn server, run bench.py once, return path to the bench JSON
    output. Server is torn down between runs so each run starts from
    the same warm-cache-cold state."""
    server_env = os.environ.copy()
    server_env.update(_BASELINE_ENV)

    print(
        f"\n=== run {run_index + 1}/N "
        f"(env: ENTITY_ANCHOR=1 EMBEDDING=bge-m3 REWRITE=1 "
        f"AUTO_ROUTER=0 ADAPTIVE_BUDGET=0 SCOPE_ROUTING=0) ==="
    )
    server = _spawn_server(server_env)
    if server is None:
        return None

    bench_output: Optional[Path] = None
    try:
        pre_existing = set((ROOT / "reports").glob("bench_*_step7_*.json"))
        t0 = time.time()
        try:
            bench_env = {**os.environ, "JAMES_BASE_URL": SERVER_BASE_URL}
            bearer = _mint_employee_jwt()
            if bearer:
                bench_env["JAMES_BENCH_BEARER"] = bearer
            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "bench.py"),
                 "--suite=step7", "--mode=retrieval"],
                env=bench_env,
                cwd=str(ROOT),
                capture_output=False,
                check=False,
                timeout=BENCH_SUBPROCESS_TIMEOUT_SEC,
            )
        except subprocess.TimeoutExpired:
            print(f"[run {run_index + 1}] bench TIMEOUT after "
                  f"{BENCH_SUBPROCESS_TIMEOUT_SEC}s")
            return None
        elapsed = time.time() - t0
        print(f"[run {run_index + 1}] bench finished in {elapsed:.1f}s")

        after = set((ROOT / "reports").glob("bench_*_step7_*.json"))
        new = sorted(after - pre_existing)
        if new:
            bench_output = new[-1]
        else:
            print(f"[run {run_index + 1}] no new bench output under reports/")
    finally:
        _shutdown_server(server)
    return bench_output


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _aggregate_runs(runs: List[ThreeAxisResult]) -> Dict[str, Any]:
    """Compute median + noise band (max - min) for each axis across runs."""
    if not runs:
        return {}

    path_means = [r.path_coverage.mean_recall for r in runs]
    graded_means = [r.graded_answer.mean_accuracy for r in runs]
    abstention_f1s = [r.abstention.f1 for r in runs]

    def _stats(values: List[float]) -> Dict[str, float]:
        values_sorted = sorted(values)
        median = values_sorted[len(values_sorted) // 2]
        return {
            "median": round(median, 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "noise_band": round(max(values) - min(values), 4),
        }

    return {
        "path_coverage": _stats(path_means),
        "graded_answer": _stats(graded_means),
        "abstention_f1": _stats(abstention_f1s),
        "n_runs": len(runs),
    }


def _current_git_sha() -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT), capture_output=True, text=True, check=True,
            timeout=5,
        )
        return out.stdout.strip()[:7]
    except Exception:
        return None


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="QVT α-3 baseline capture (paired N=3 rerun + "
                    "3-axis oracle aggregation).",
    )
    parser.add_argument(
        "--n-runs", type=int, default=3,
        help="Paired rerun count (default 3, matches memo §4 noise-band "
             "design).",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output JSON path. Default: "
             "eval/qvt/baseline_<git-sha>.json",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print the planned env + output path; do not spawn server "
             "or run bench.",
    )
    args = parser.parse_args(argv)

    sha = _current_git_sha() or "unknown"
    out_path = (
        Path(args.output) if args.output
        else _OUTPUT_DIR / f"baseline_{sha}.json"
    )

    print("=== QVT α-3 baseline capture ===")
    print(f"git_sha:      {sha}")
    print(f"fixture:      {_FIXTURE_PATH.relative_to(ROOT)}")
    print(f"output:       {out_path.relative_to(ROOT)}")
    print(f"n_runs:       {args.n_runs}")
    print(f"baseline env: {_BASELINE_ENV}")

    if args.dry_run:
        print("[dry-run] not spawning server, not running bench.")
        return 0

    if not _FIXTURE_PATH.exists():
        print(f"[error] fixture {_FIXTURE_PATH} missing")
        return 2

    fixture = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))

    runs: List[ThreeAxisResult] = []
    run_paths: List[str] = []
    for i in range(args.n_runs):
        bench_path = _run_single_bench(i)
        if bench_path is None:
            print(f"[error] run {i + 1} failed to produce bench output")
            return 3
        result = score_three_axis(bench_path, fixture)
        print(f"[run {i + 1}] {result.summary()}")
        runs.append(result)
        run_paths.append(str(bench_path.relative_to(ROOT)))

    aggregate = _aggregate_runs(runs)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "qvt-baseline-v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": sha,
        "fixture_version": fixture.get("version"),
        "fixture_path": str(_FIXTURE_PATH.relative_to(ROOT)),
        "n_runs": args.n_runs,
        "env": _BASELINE_ENV,
        "aggregate": aggregate,
        "runs": [
            {
                "bench_output": run_paths[i],
                "scores": runs[i].to_dict(),
            }
            for i in range(args.n_runs)
        ],
    }
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(f"\n[done] baseline written to {out_path.relative_to(ROOT)}")
    print(f"aggregate: {aggregate}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
