"""QVT α-5 — 18-cell ablation matrix runner.

Implements the matrix specified in
``docs/design/v0.4-qvt-alpha-5-ablation-matrix.md``:

  6 layer rows  (L0 floor / L1 baseline / L2 +AUTO_ROUTER /
                 L3 +ADAPTIVE_BUDGET / L4 +SCOPE_ROUTING / L5 full)
  3 model tiers (M_S gemma3:4b / M_M gemma4:e4b / M_L gemma3:12b)
  × paired N=3 reruns
  × 3-axis QVT oracle (path / graded / abstention)
  = 18 cells × ~66 min ≈ 20 hours operator-side compute.

Per cell, the runner:
  1. Boots a fresh JAMES server with the row's env flags + tier's
     ``JAMES_LLM_MODEL`` tag.
  2. Runs ``scripts/bench.py --suite=step7 --mode=retrieval`` N times.
  3. Applies ``eval/qvt/oracle.py:score_three_axis`` to each bench JSON.
  4. Aggregates (median + noise band) and writes a per-cell JSON to
     ``reports/research-runs/qvt-ablation-cells/<row>-<tier>-<ts>.json``
     so a partial / interrupted run is salvageable.

After all cells land (or operator runs ``--render-report`` on whatever
cells exist), the runner reads the per-cell JSONs, joins them against
the α-3 baseline (``eval/qvt/baseline_<sha>.json``), computes per-cell
Δ vs the L1/M_M cell, applies the verdict rule (positive / mixed /
zero / negative / regression), and emits the consolidated report at
``reports/promo-assets/v0.4-qvt-ablation-matrix.md``.

CLI examples (memo §5.1)::

    # Full matrix (operator typically chunks per tier — see below)
    python scripts/qvt_ablation_matrix.py

    # Day-1 production-tier matrix only (load-bearing decision row)
    python scripts/qvt_ablation_matrix.py --tiers M_M

    # Day-2 large-tier comparison
    python scripts/qvt_ablation_matrix.py --tiers M_L

    # Resume — skip cells whose per-cell JSON already exists
    python scripts/qvt_ablation_matrix.py --resume

    # Render the final matrix report from existing per-cell JSONs
    python scripts/qvt_ablation_matrix.py --render-report

    # Dry-run — print the plan without spawning anything
    python scripts/qvt_ablation_matrix.py --dry-run

Cross-stack invariant (same constraint as
``feedback_cross_stack_run_flag_off``): this runner *sets* the routing
flags per row; operator MUST NOT manually flip them during a matrix
run, and MUST NOT have an existing server on the bound port (the
spawn helper refuses to override running processes' env).
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

from eval.qvt.oracle import ThreeAxisResult, score_three_axis  # noqa: E402

# ---------------------------------------------------------------------------
# Matrix definition (memo §2)
# ---------------------------------------------------------------------------

# Layer flags held fixed across all cells regardless of row.
_FIXED_ENV: Dict[str, str] = {
    "JAMES_EMBEDDING_MODEL": "BAAI/bge-m3",
}


# Each row sets the 5 layer flags explicitly. Even L1 (which equals
# the α-3 production baseline) writes all 5 so operators reading the
# cell JSON can see the exact env applied without cross-referencing.
_ROW_ENVS: Dict[str, Dict[str, str]] = {
    "L0": {  # floor — all layers off
        "JAMES_ENABLE_ENTITY_ANCHOR": "0",
        "JAMES_ENABLE_QUERY_REWRITE": "0",
        "JAMES_AUTO_ROUTER": "0",
        "JAMES_ADAPTIVE_BUDGET": "0",
        "JAMES_SCOPE_ROUTING": "0",
    },
    "L1": {  # baseline (production) — matches α-3 baseline JSON
        "JAMES_ENABLE_ENTITY_ANCHOR": "1",
        "JAMES_ENABLE_QUERY_REWRITE": "1",
        "JAMES_AUTO_ROUTER": "0",
        "JAMES_ADAPTIVE_BUDGET": "0",
        "JAMES_SCOPE_ROUTING": "0",
    },
    "L2": {  # + AUTO_ROUTER (D5)
        "JAMES_ENABLE_ENTITY_ANCHOR": "1",
        "JAMES_ENABLE_QUERY_REWRITE": "1",
        "JAMES_AUTO_ROUTER": "1",
        "JAMES_ADAPTIVE_BUDGET": "0",
        "JAMES_SCOPE_ROUTING": "0",
    },
    "L3": {  # + ADAPTIVE_BUDGET (D1)
        "JAMES_ENABLE_ENTITY_ANCHOR": "1",
        "JAMES_ENABLE_QUERY_REWRITE": "1",
        "JAMES_AUTO_ROUTER": "0",
        "JAMES_ADAPTIVE_BUDGET": "1",
        "JAMES_SCOPE_ROUTING": "0",
    },
    "L4": {  # + SCOPE_ROUTING (LEO)
        "JAMES_ENABLE_ENTITY_ANCHOR": "1",
        "JAMES_ENABLE_QUERY_REWRITE": "1",
        "JAMES_AUTO_ROUTER": "0",
        "JAMES_ADAPTIVE_BUDGET": "0",
        "JAMES_SCOPE_ROUTING": "1",
    },
    "L5": {  # full stack
        "JAMES_ENABLE_ENTITY_ANCHOR": "1",
        "JAMES_ENABLE_QUERY_REWRITE": "1",
        "JAMES_AUTO_ROUTER": "1",
        "JAMES_ADAPTIVE_BUDGET": "1",
        "JAMES_SCOPE_ROUTING": "1",
    },
}


_ROW_LABELS: Dict[str, str] = {
    "L0": "floor",
    "L1": "baseline (production)",
    "L2": "+AUTO_ROUTER",
    "L3": "+ADAPTIVE_BUDGET",
    "L4": "+SCOPE_ROUTING",
    "L5": "full stack",
}


# Model tier → Ollama tag (memo §2.2)
_TIER_MODELS: Dict[str, str] = {
    "M_S": "gemma3:4b",
    "M_M": "gemma4:e4b",   # production default; α-3 baseline tier
    "M_L": "gemma3:12b",
}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SERVER_BASE_URL = os.environ.get("JAMES_BASE_URL", "http://127.0.0.1:8000")
SERVER_HEALTHZ = SERVER_BASE_URL.rstrip("/") + "/healthz"
SERVER_BOOT_TIMEOUT_SEC = 120
BENCH_SUBPROCESS_TIMEOUT_SEC = 2400

_FIXTURE_PATH = ROOT / "eval" / "regression" / "step7_queries.json"
_OUTPUT_DIR = ROOT / "reports" / "research-runs" / "qvt-ablation-cells"
_REPORT_DIR = ROOT / "reports" / "promo-assets"
_BASELINE_DIR = ROOT / "eval" / "qvt"


# ---------------------------------------------------------------------------
# Server lifecycle helpers — copied from qvt_capture_baseline.py with
# the env extended to accept per-cell flags. Trimmed comments for brevity;
# see capture_baseline for the verbatim docstrings.
# ---------------------------------------------------------------------------

def _parse_host_port(url: str) -> Tuple[str, int]:
    stripped = url.replace("http://", "").replace("https://", "")
    host_part, _, _ = stripped.partition("/")
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
    try:
        from core.auth import create_token
        return create_token("qvt-ablation-runner", "employee")
    except Exception as e:
        print(f"[server] JWT mint failed ({type(e).__name__}: {e}) — "
              f"falling back to api_key-only auth (results will likely "
              f"show chat-mode passthrough)")
        return None


# ---------------------------------------------------------------------------
# Per-cell execution
# ---------------------------------------------------------------------------

def _cell_env(row: str, tier: str) -> Dict[str, str]:
    """Compose the full env for one cell: OS env + fixed + row + tier."""
    env = os.environ.copy()
    env.update(_FIXED_ENV)
    env.update(_ROW_ENVS[row])
    env["JAMES_LLM_MODEL"] = _TIER_MODELS[tier]
    return env


def _run_single_bench(row: str, tier: str, run_index: int) -> Optional[Path]:
    server_env = _cell_env(row, tier)

    flagged = {k: v for k, v in _ROW_ENVS[row].items()}
    print(
        f"\n=== cell {row}/{tier} run {run_index + 1}/N "
        f"(model={_TIER_MODELS[tier]}, env={flagged}) ==="
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
            print(f"[cell {row}/{tier} run {run_index + 1}] bench TIMEOUT "
                  f"after {BENCH_SUBPROCESS_TIMEOUT_SEC}s")
            return None
        elapsed = time.time() - t0
        print(f"[cell {row}/{tier} run {run_index + 1}] bench finished "
              f"in {elapsed:.1f}s")

        after = set((ROOT / "reports").glob("bench_*_step7_*.json"))
        new = sorted(after - pre_existing)
        if new:
            bench_output = new[-1]
        else:
            print(f"[cell {row}/{tier} run {run_index + 1}] no new bench "
                  f"output under reports/")
    finally:
        _shutdown_server(server)
    return bench_output


def _aggregate_runs(runs: List[ThreeAxisResult]) -> Dict[str, Any]:
    """Same shape as qvt_capture_baseline._aggregate_runs for cell-vs-
    baseline comparability."""
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


def _cell_output_path(row: str, tier: str) -> Path:
    return _OUTPUT_DIR / f"qvt-ablation-cell-{row}-{tier}.json"


def _run_cell(row: str, tier: str, n_runs: int, fixture: Dict[str, Any],
              sha: str, resume: bool) -> Optional[Dict[str, Any]]:
    """Run one cell. Writes per-cell JSON. Returns the payload (or
    loads-and-returns when --resume hits an existing file)."""
    out = _cell_output_path(row, tier)
    if resume and out.exists():
        print(f"[cell {row}/{tier}] --resume: skipping, "
              f"{out.relative_to(ROOT)} exists")
        return json.loads(out.read_text(encoding="utf-8"))

    runs: List[ThreeAxisResult] = []
    run_paths: List[str] = []
    for i in range(n_runs):
        bench_path = _run_single_bench(row, tier, i)
        if bench_path is None:
            print(f"[cell {row}/{tier}] run {i + 1} failed to produce "
                  f"bench output — aborting cell")
            return None
        result = score_three_axis(bench_path, fixture)
        print(f"[cell {row}/{tier} run {i + 1}] {result.summary()}")
        runs.append(result)
        run_paths.append(str(bench_path.relative_to(ROOT)))

    aggregate = _aggregate_runs(runs)
    payload = {
        "schema": "qvt-ablation-cell-v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": sha,
        "row": row,
        "row_label": _ROW_LABELS[row],
        "tier": tier,
        "model": _TIER_MODELS[tier],
        "env": _ROW_ENVS[row],
        "fixed_env": _FIXED_ENV,
        "fixture_version": fixture.get("version"),
        "n_runs": n_runs,
        "aggregate": aggregate,
        "runs": [
            {"bench_output": run_paths[i], "scores": runs[i].to_dict()}
            for i in range(n_runs)
        ],
    }
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(f"[cell {row}/{tier}] wrote {out.relative_to(ROOT)}")
    return payload


# ---------------------------------------------------------------------------
# Report rendering (--render-report)
# ---------------------------------------------------------------------------

def _classify_delta(deltas: Dict[str, float], noise_band: Dict[str, float]) -> str:
    """Memo §3.1 verdict rule."""
    positives = []
    negatives = []
    for axis in ("path_coverage", "graded_answer", "abstention_f1"):
        d = deltas.get(axis, 0.0)
        band = noise_band.get(axis, 0.0)
        if d > band:
            positives.append(axis)
        elif d < -band:
            negatives.append(axis)
    if len(positives) == 3:
        return "positive"
    if len(negatives) == 3:
        return "regression"
    if positives and not negatives:
        return "mixed"
    if negatives and not positives:
        return "negative"
    return "zero"


def _read_baseline() -> Optional[Dict[str, Any]]:
    files = sorted(_BASELINE_DIR.glob("baseline_*.json"))
    if not files:
        print(f"[report] no baseline JSON under {_BASELINE_DIR.relative_to(ROOT)}")
        return None
    # Most recent SHA — operator captures one baseline per release.
    latest = files[-1]
    print(f"[report] using baseline {latest.relative_to(ROOT)}")
    return json.loads(latest.read_text(encoding="utf-8"))


def _render_report(out_path: Path) -> int:
    baseline = _read_baseline()
    if baseline is None:
        return 4
    base_agg = baseline.get("aggregate", {})
    base_med = {
        "path_coverage": base_agg.get("path_coverage", {}).get("median"),
        "graded_answer": base_agg.get("graded_answer", {}).get("median"),
        "abstention_f1": base_agg.get("abstention_f1", {}).get("median"),
    }
    base_noise = {
        "path_coverage": base_agg.get("path_coverage", {}).get("noise_band", 0.0),
        "graded_answer": base_agg.get("graded_answer", {}).get("noise_band", 0.0),
        "abstention_f1": base_agg.get("abstention_f1", {}).get("noise_band", 0.0),
    }

    cells: List[Dict[str, Any]] = []
    for row in _ROW_ENVS:
        for tier in _TIER_MODELS:
            p = _cell_output_path(row, tier)
            if not p.exists():
                continue
            cells.append(json.loads(p.read_text(encoding="utf-8")))

    if not cells:
        print(f"[report] no per-cell JSONs found under "
              f"{_OUTPUT_DIR.relative_to(ROOT)}")
        return 5

    rows: List[str] = [
        "# QVT α-5 ablation matrix — 18-cell verdict",
        "",
        f"**Baseline**: `{baseline.get('git_sha', 'unknown')}` "
        f"(captured {baseline.get('captured_at', '?')}).",
        f"**Cells available**: {len(cells)}/{len(_ROW_ENVS) * len(_TIER_MODELS)}.",
        "",
        "| Row | Tier | Model | Path Δ | Graded Δ | Abst F1 Δ | "
        "Noise band (P/G/A) | Verdict |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for c in cells:
        agg = c.get("aggregate", {})
        med = {
            "path_coverage": agg.get("path_coverage", {}).get("median"),
            "graded_answer": agg.get("graded_answer", {}).get("median"),
            "abstention_f1": agg.get("abstention_f1", {}).get("median"),
        }
        deltas: Dict[str, float] = {}
        for axis in ("path_coverage", "graded_answer", "abstention_f1"):
            if med[axis] is None or base_med[axis] is None:
                deltas[axis] = 0.0
            else:
                deltas[axis] = round(med[axis] - base_med[axis], 4)
        verdict = _classify_delta(deltas, base_noise)
        rows.append(
            f"| {c['row']} ({c['row_label']}) | {c['tier']} | "
            f"`{c['model']}` | {deltas['path_coverage']:+.3f} | "
            f"{deltas['graded_answer']:+.3f} | "
            f"{deltas['abstention_f1']:+.3f} | "
            f"{base_noise['path_coverage']:.3f}/"
            f"{base_noise['graded_answer']:.3f}/"
            f"{base_noise['abstention_f1']:.3f} | "
            f"**{verdict}** |"
        )

    rows += [
        "",
        "## Verdict rule",
        "",
        "Per cell, Δ vs L1/M_M baseline median per axis. Noise band =",
        "max − min across the baseline's paired-N=3 runs. Classification:",
        "",
        "- **positive** — all 3 axes Δ > noise band",
        "- **mixed** — at least one Δ > band, none Δ < −band",
        "- **zero** — all |Δ| ≤ band",
        "- **negative** — at least one Δ < −band, none Δ > band",
        "- **regression** — all 3 axes Δ < −band",
        "",
        "## Routing policy decision (memo §3.2)",
        "",
        "| Per-tier pattern | Policy |",
        "|---|---|",
        "| `positive` on ≥ 2 tiers including M_M | enable as default (flip `.env.example`) |",
        "| `positive` only on one tier | tier-gated (router policy keys on `JAMES_LLM_MODEL`) |",
        "| `zero` on all tiers | delete / document as inert (deprecation PR) |",
        "| `negative` or `regression` on ≥ 1 tier | keep opt-in indefinitely |",
        "",
        "Follow-up PRs (one per layer with non-`zero` verdict) cite the",
        "specific cell here as their Quality Delta Card source.",
    ]
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(rows), encoding="utf-8")
    print(f"[report] wrote {out_path.relative_to(ROOT)}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_subset(arg: Optional[str], universe: List[str], label: str) -> List[str]:
    if not arg:
        return universe
    requested = [x.strip() for x in arg.split(",") if x.strip()]
    unknown = [x for x in requested if x not in universe]
    if unknown:
        raise SystemExit(f"[error] unknown {label}: {unknown} "
                         f"(known: {universe})")
    # Preserve canonical order even if operator lists out of order.
    return [x for x in universe if x in requested]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="QVT α-5 ablation matrix runner (memo §5).",
    )
    parser.add_argument(
        "--n-runs", type=int, default=3,
        help="Paired rerun count per cell (default 3, matches noise-band design).",
    )
    parser.add_argument(
        "--rows", type=str, default=None,
        help="Comma-separated subset of L0..L5 (default: all).",
    )
    parser.add_argument(
        "--tiers", type=str, default=None,
        help="Comma-separated subset of M_S/M_M/M_L (default: all).",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Skip cells whose per-cell JSON already exists.",
    )
    parser.add_argument(
        "--render-report", action="store_true",
        help="Read existing per-cell JSONs + baseline, write the "
             "consolidated matrix report; do not run any bench.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print the planned cells + envs; do not spawn server.",
    )
    parser.add_argument(
        "--t0-smoke", action="store_true",
        help="α-5 prereq §3 T0 smoke gate — equivalent to "
             "`--tiers M_M --rows L1,L5`. The smallest run (~2.2 h) that "
             "tells whether the matrix has any signal at production tier. "
             "If |graded_answer Δ| < 0.05, STOP and skip M_S/M_L — the "
             "matrix is null and 18 h of further compute would be wasted.",
    )
    args = parser.parse_args(argv)

    if args.render_report:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        out_path = _REPORT_DIR / f"v0.4-qvt-ablation-matrix-{ts}.md"
        return _render_report(out_path)

    # T0 smoke gate (α-5 prereq §3) takes precedence over --rows/--tiers
    # so an operator can fire the gate run with one flag.
    if args.t0_smoke:
        if args.rows or args.tiers:
            print("[error] --t0-smoke implies --tiers M_M --rows L1,L5; "
                  "remove --rows/--tiers or drop --t0-smoke")
            return 7
        args.rows = "L1,L5"
        args.tiers = "M_M"
        print("[t0-smoke] α-5 prereq §3 gate — running "
              "M_M × {L1, L5} (~2.2 h). Verdict rule: if |graded_answer "
              "Δ| < 0.05 → matrix null at production tier → STOP.")

    rows = _parse_subset(args.rows, list(_ROW_ENVS.keys()), "rows")
    tiers = _parse_subset(args.tiers, list(_TIER_MODELS.keys()), "tiers")
    sha = _current_git_sha() or "unknown"

    print("=== QVT α-5 ablation matrix ===")
    print(f"git_sha:    {sha}")
    print(f"fixture:    {_FIXTURE_PATH.relative_to(ROOT)}")
    print(f"rows:       {rows}")
    print(f"tiers:      {tiers}  → {[_TIER_MODELS[t] for t in tiers]}")
    print(f"n_runs:     {args.n_runs}")
    print(f"resume:     {args.resume}")
    print(f"cells:      {len(rows) * len(tiers)} "
          f"(~{round(len(rows) * len(tiers) * 66 / 60, 1)} h compute)")

    if args.dry_run:
        print("\n[dry-run] cells planned:")
        for row in rows:
            for tier in tiers:
                print(f"  {row}/{tier} model={_TIER_MODELS[tier]} "
                      f"env={_ROW_ENVS[row]}")
        return 0

    if not _FIXTURE_PATH.exists():
        print(f"[error] fixture {_FIXTURE_PATH} missing")
        return 2
    fixture = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))

    n_ok = 0
    n_fail = 0
    for row in rows:
        for tier in tiers:
            payload = _run_cell(row, tier, args.n_runs, fixture, sha,
                                resume=args.resume)
            if payload is None:
                n_fail += 1
            else:
                n_ok += 1

    print(f"\n[done] cells succeeded: {n_ok}, failed: {n_fail}")
    print(f"Per-cell JSONs at {_OUTPUT_DIR.relative_to(ROOT)}.")

    # T0 smoke verdict — print the prereq §3 decision in-line so the
    # operator knows whether to proceed to T1 or stop, without having
    # to re-render the report.
    if args.t0_smoke and n_fail == 0:
        l1 = _cell_output_path("L1", "M_M")
        l5 = _cell_output_path("L5", "M_M")
        if l1.exists() and l5.exists():
            j1 = json.loads(l1.read_text(encoding="utf-8"))
            j5 = json.loads(l5.read_text(encoding="utf-8"))
            g1 = j1["aggregate"]["graded_answer"]["median"]
            g5 = j5["aggregate"]["graded_answer"]["median"]
            delta = round(g5 - g1, 4)
            print(f"\n=== T0 smoke verdict ===")
            print(f"L1 graded_answer median: {g1:.4f}")
            print(f"L5 graded_answer median: {g5:.4f}")
            print(f"Δ (full stack vs baseline): {delta:+.4f}")
            if abs(delta) < 0.05:
                print(
                    "VERDICT: matrix likely NULL at production tier "
                    f"(|Δ|={abs(delta):.4f} < 0.05). Do NOT run T2 "
                    f"(M_S / M_L) — savings ~18 h. See prereq §3 + §4."
                )
            else:
                print(
                    "VERDICT: matrix has SIGNAL at production tier "
                    f"(|Δ|={abs(delta):.4f} ≥ 0.05). Proceed to T1 "
                    f"(`--tiers M_M`, ~5.5 h) to isolate which layer."
                )

    print(f"\nRender the consolidated report with:\n"
          f"  python scripts/qvt_ablation_matrix.py --render-report")
    return 0 if n_fail == 0 else 6


if __name__ == "__main__":
    raise SystemExit(main())
