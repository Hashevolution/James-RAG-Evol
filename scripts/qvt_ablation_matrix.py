"""QVT α-5 — 18-cell ablation matrix runner.

Implements the matrix specified in
``docs/design/v0.4-qvt-alpha-5-ablation-matrix.md``:

  6 layer rows  (L0 floor / L1 baseline / L2 +AUTO_ROUTER /
                 L3 +ADAPTIVE_BUDGET / L4 +SCOPE_ROUTING / L5 full)
  5 model tiers (M_XS gemma3:1b / M_S gemma3:4b / M_M gemma4:e4b /
                 M_L gemma3:12b / M_XL gemma3:27b)  -- α-6 Phase 3a
                 added M_XS / M_XL for the gemma3 scale ladder
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

from eval.qvt.oracle import (  # noqa: E402
    FiveAxisResult,
    score_five_axis,
    score_five_axis_by_question_type,
)

# ---------------------------------------------------------------------------
# Matrix definition (memo §2)
# ---------------------------------------------------------------------------

# Layer flags held fixed across all cells regardless of row.
# JAMES_RATE_LIMIT_MAX is set to a large value to effectively
# disable the per-IP rate limiter for benchmark loops -- the
# operator-safe default (30 req / 60s) silently corrupts cells
# whose model responds in sub-2s/query (gemma3:4b with no
# retrieval hits this). Per α-6 Phase 2 corruption post-mortem
# (PR #671). The server's `server_llmwiki.py` reads this env at
# startup; the matrix runner spawns a fresh server per cell.
_FIXED_ENV: Dict[str, str] = {
    "JAMES_EMBEDDING_MODEL": "BAAI/bge-m3",
    "JAMES_RATE_LIMIT_MAX": "10000",
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


# α-6 sector cells (per docs/design/v0.4-alpha-6-sector-llm-ablation-matrix.md §2).
# Each cell layers on L1 (production-default ENTITY_ANCHOR + QUERY_REWRITE)
# but toggles the 5 sector disable-flags (PRs #657-#661) to ablate
# infrastructure sectors. Production-byte-identical when no sector flag
# is set; the matrix runner overlays these on top of L1's row env when
# the operator passes --sector-cells.
#
# Cell taxonomy (S1 RAG / S2 Graph / S3 Preproc / S4 Cite / S5 Abst /
# S6 Cog):
#   C_minus      = none on  (pure LLM, no JAMES)
#   C_rag-basic  = S1 only
#   C_rag-cited  = S1 + S4
#   C_rag-graph  = S1 + S2 + S3 + S4 (= "JAMES retrieval + graph + cite,
#                                       no abstention softener, no
#                                       cognitive stages")
#   C_rag-full   = all on (= α-5 L1 cell — already measured)
#   C_rag-routed = full + routing layers (= α-5 L5 cell — already measured)
_SECTOR_CELL_ENVS: Dict[str, Dict[str, str]] = {
    "C_minus": {
        # Pure LLM — all 5 sector flags ON (disable everything except
        # S3 query preprocessing, which is the row's responsibility).
        # Also disable S3 by overriding the row env below.
        "JAMES_DISABLE_RAG_RETRIEVAL":    "1",
        "JAMES_DISABLE_GRAPH":            "1",
        "JAMES_DISABLE_SOURCES_FIELD":    "1",
        "JAMES_DISABLE_ABSTENTION":       "1",
        "JAMES_DISABLE_COGNITIVE_STAGES": "1",
        # S3 also off — override row ENV's ENABLE flags
        "JAMES_ENABLE_ENTITY_ANCHOR":     "0",
        "JAMES_ENABLE_QUERY_REWRITE":     "0",
    },
    "C_rag-basic": {
        # S1 (RAG) only — everything else off.
        "JAMES_DISABLE_GRAPH":            "1",
        "JAMES_DISABLE_SOURCES_FIELD":    "1",
        "JAMES_DISABLE_ABSTENTION":       "1",
        "JAMES_DISABLE_COGNITIVE_STAGES": "1",
        # S3 off — basic RAG means no entity anchor + no rewrite
        "JAMES_ENABLE_ENTITY_ANCHOR":     "0",
        "JAMES_ENABLE_QUERY_REWRITE":     "0",
    },
    "C_rag-cited": {
        # S1 + S4 on; S2 / S3 / S5 / S6 off.
        "JAMES_DISABLE_GRAPH":            "1",
        "JAMES_DISABLE_ABSTENTION":       "1",
        "JAMES_DISABLE_COGNITIVE_STAGES": "1",
        "JAMES_ENABLE_ENTITY_ANCHOR":     "0",
        "JAMES_ENABLE_QUERY_REWRITE":     "0",
    },
    "C_rag-graph": {
        # S1 + S2 + S3 + S4 on; S5 + S6 off.
        # S3 stays ON (row's defaults: ENTITY_ANCHOR=1, QUERY_REWRITE=1).
        "JAMES_DISABLE_ABSTENTION":       "1",
        "JAMES_DISABLE_COGNITIVE_STAGES": "1",
    },
    "C_rag-full": {
        # Equivalent to α-5 L1 — all sectors on, no routing layers.
        # No sector disable flag; row's L1 default applies.
    },
    "C_rag-routed": {
        # Equivalent to α-5 L5 — all sectors on + all routing layers on.
        # Operator should pair this with --rows L5 instead of using
        # --sector-cells for clarity, but we list it here for the
        # naming-convention completeness.
        "JAMES_AUTO_ROUTER":      "1",
        "JAMES_ADAPTIVE_BUDGET":  "1",
        "JAMES_SCOPE_ROUTING":    "1",
    },
}


_SECTOR_CELL_LABELS: Dict[str, str] = {
    "C_minus":      "pure LLM (no JAMES)",
    "C_rag-basic":  "+ RAG only",
    "C_rag-cited":  "+ RAG + citation (S4)",
    "C_rag-graph":  "+ RAG + graph + S3 preproc + citation",
    "C_rag-full":   "JAMES full stack (= α-5 L1)",
    "C_rag-routed": "JAMES + routing layers (= α-5 L5)",
}


# Model tier → Ollama tag (memo §2.2; α-6 Phase 3a adds M_XS / M_XL)
_TIER_MODELS: Dict[str, str] = {
    "M_XS": "gemma3:1b",   # α-6 Phase 3a — extreme small (capability floor probe)
    "M_S": "gemma3:4b",
    "M_M": "gemma4:e4b",   # production default; α-3 baseline tier
    "M_L": "gemma3:12b",
    "M_XL": "gemma3:27b",  # α-6 Phase 3a — large (saturation point probe)
}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SERVER_BASE_URL = os.environ.get("JAMES_BASE_URL", "http://127.0.0.1:8000")
SERVER_HEALTHZ = SERVER_BASE_URL.rstrip("/") + "/healthz"
SERVER_BOOT_TIMEOUT_SEC = 180  # heavier workspace boot
BENCH_SUBPROCESS_TIMEOUT_SEC = 14400  # 4h ceiling for α-5 multihop_rag suites

_DEFAULT_FIXTURE_PATH = ROOT / "eval" / "regression" / "step7_queries.json"
_OUTPUT_DIR = ROOT / "reports" / "research-runs" / "qvt-ablation-cells"
_REPORT_DIR = ROOT / "reports" / "promo-assets"
_BASELINE_DIR = ROOT / "eval" / "qvt"


def _resolve_fixture(suite: str) -> Path:
    """Same resolution as bench.py:_load_suite — eval/regression/ first,
    workspace's eval/ fallback. Lets `--suite=multihop_rag` find the
    α-5 fixture without hardcoding."""
    canonical = ROOT / "eval" / "regression" / f"{suite}_queries.json"
    if canonical.exists():
        return canonical
    ws_raw = os.environ.get("JAMES_WORKSPACE", "").strip()
    if ws_raw:
        ws_path = Path(ws_raw).resolve() / "eval" / f"{suite}_queries.json"
        if ws_path.exists():
            return ws_path
    return canonical  # caller prints "missing" diagnostic against this


def _resolve_output_dir() -> Path:
    """Per-cell JSON output dir — workspace-relative when set, else the
    project's `reports/research-runs/qvt-ablation-cells/`."""
    ws_raw = os.environ.get("JAMES_WORKSPACE", "").strip()
    if ws_raw:
        return (Path(ws_raw).resolve()
                / "reports" / "research-runs" / "qvt-ablation-cells")
    return _OUTPUT_DIR


def _resolve_baseline_dir() -> Path:
    ws_raw = os.environ.get("JAMES_WORKSPACE", "").strip()
    if ws_raw:
        return Path(ws_raw).resolve() / "eval" / "qvt"
    return _BASELINE_DIR


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

def _cell_env(row: str, tier: str,
              think_override: Optional[bool] = None,
              sector_cell: Optional[str] = None) -> Dict[str, str]:
    """Compose the full env for one cell: OS env + fixed + row + tier +
    optional `JAMES_GEMMA4_E4B_THINK_OFF` override + optional α-6 sector
    cell overlay.

    `think_override` semantics:
      None         — inherit from process env (workspace .env's setting).
      True         — force `JAMES_GEMMA4_E4B_THINK_OFF=1` (matrix primary).
      False        — force the variable unset (sanity cell — restores
                     production default = thinking ON).

    `sector_cell` (α-6) — when set to one of `_SECTOR_CELL_ENVS` keys,
    the cell's sector-flag dict overlays the row's flags. This lets
    α-6 cells like `C_minus` (everything off) reuse the L1 row's
    base env while toggling the 5 sector disable-flags
    (JAMES_DISABLE_* per PRs #657-#661).
    """
    env = os.environ.copy()
    env.update(_FIXED_ENV)
    env.update(_ROW_ENVS[row])
    env["JAMES_LLM_MODEL"] = _TIER_MODELS[tier]
    if think_override is True:
        env["JAMES_GEMMA4_E4B_THINK_OFF"] = "1"
    elif think_override is False:
        # Force unset — sanity cell reverts to production default.
        env.pop("JAMES_GEMMA4_E4B_THINK_OFF", None)
    if sector_cell is not None:
        if sector_cell not in _SECTOR_CELL_ENVS:
            raise ValueError(
                f"unknown sector cell {sector_cell!r}; "
                f"choose from {sorted(_SECTOR_CELL_ENVS.keys())}"
            )
        env.update(_SECTOR_CELL_ENVS[sector_cell])
    return env


def _run_single_bench(row: str, tier: str, run_index: int,
                      suite: str = "step7",
                      think_override: Optional[bool] = None,
                      sector_cell: Optional[str] = None) -> Optional[Path]:
    """Run one bench subprocess against the configured suite.

    `suite` carries the matrix runner's --suite argument through; the
    pre-α-5 default was hardcoded "step7" (the legacy regression suite)
    and remained as default for back-compat.

    `sector_cell` (α-6) — when set, the row's flag dict is overlaid
    with the sector cell's `_SECTOR_CELL_ENVS[sector_cell]` so the
    matrix can run α-6 cells (C_minus / C_rag-basic / C_rag-cited /
    C_rag-graph etc.) on top of an L1 row.

    bench JSON output detection uses the same `{suite}_*.json` glob so
    multihop_rag (or any future suite) finds its own newly-written file
    rather than searching an unrelated suite's output.
    """
    server_env = _cell_env(row, tier, think_override=think_override,
                           sector_cell=sector_cell)

    flagged = {k: v for k, v in _ROW_ENVS[row].items()}
    if sector_cell is not None:
        flagged.update(_SECTOR_CELL_ENVS[sector_cell])
    think_tag = ""
    if think_override is True:
        think_tag = " think=OFF (primary)"
    elif think_override is False:
        think_tag = " think=ON (sanity)"
    cell_id = f"{sector_cell}/{tier}" if sector_cell else f"{row}/{tier}"
    print(
        f"\n=== cell {cell_id} run {run_index + 1}/N "
        f"(model={_TIER_MODELS[tier]}, suite={suite}, "
        f"env={flagged}{think_tag}) ==="
    )
    server = _spawn_server(server_env)
    if server is None:
        return None

    bench_output: Optional[Path] = None
    try:
        glob_pattern = f"bench_*_{suite}_*.json"
        pre_existing = set((ROOT / "reports").glob(glob_pattern))
        t0 = time.time()
        try:
            bench_env = {**os.environ, "JAMES_BASE_URL": SERVER_BASE_URL}
            bearer = _mint_employee_jwt()
            if bearer:
                bench_env["JAMES_BENCH_BEARER"] = bearer
            subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "bench.py"),
                 f"--suite={suite}", "--mode=retrieval"],
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

        after = set((ROOT / "reports").glob(glob_pattern))
        new = sorted(after - pre_existing)
        if new:
            bench_output = new[-1]
        else:
            print(f"[cell {row}/{tier} run {run_index + 1}] no new bench "
                  f"output under reports/")
    finally:
        _shutdown_server(server)
    return bench_output


def _aggregate_runs(runs: List[FiveAxisResult]) -> Dict[str, Any]:
    """5-axis aggregation: 3 quality (path/graded/abstention) + 2 cost
    (token, latency). Same per-axis stats shape (median/min/max/
    noise_band) so the matrix render can compute Δ vs baseline uniformly.
    """
    if not runs:
        return {}
    path_means = [r.path_coverage.mean_recall for r in runs]
    graded_means = [r.graded_answer.mean_accuracy for r in runs]
    abstention_f1s = [r.abstention.f1 for r in runs]
    # Cost axes — lower is better. We report mean (paired with the
    # per-query p95 captured in to_dict() for tail-watching) and same
    # noise-band shape as quality axes.
    token_means = [r.token_cost.mean_chars for r in runs]
    latency_means = [r.latency_cost.mean_s for r in runs]

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
        "token_cost": _stats(token_means),
        "latency_cost": _stats(latency_means),
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


def _cell_output_path(row: str, tier: str,
                      sanity_think_on: bool = False,
                      sector_cell: Optional[str] = None) -> Path:
    suffix = "-thinkON" if sanity_think_on else ""
    if sector_cell:
        return _resolve_output_dir() / f"qvt-ablation-cell-{sector_cell}-{tier}{suffix}.json"
    return _resolve_output_dir() / f"qvt-ablation-cell-{row}-{tier}{suffix}.json"


def _run_cell(row: str, tier: str, n_runs: int, fixture: Dict[str, Any],
              sha: str, resume: bool,
              sanity_think_on: bool = False,
              suite: str = "step7",
              sector_cell: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Run one cell. Writes per-cell JSON. Returns the payload (or
    loads-and-returns when --resume hits an existing file).

    `sanity_think_on=True` (Step 9): forces gemma4:e4b's `think=ON`
    (matrix sanity supplement — production default). Output JSON gets
    `-thinkON` suffix so the standard L1/M_M cell and the sanity cell
    coexist on disk.

    `sector_cell` (α-6) — when set, the cell's row env is overlaid
    with the sector cell's flag dict (`_SECTOR_CELL_ENVS[sector_cell]`).
    The output filename uses the sector cell name instead of the row
    name (e.g. `qvt-ablation-cell-C_minus-M_M.json`).
    """
    out = _cell_output_path(row, tier, sanity_think_on=sanity_think_on,
                            sector_cell=sector_cell)
    if resume and out.exists():
        cell_tag = (f"{sector_cell}/{tier}" if sector_cell
                    else f"{row}/{tier}")
        cell_tag += " (sanity think=ON)" if sanity_think_on else ""
        print(f"[cell {cell_tag}] --resume: skipping, "
              f"{out.relative_to(ROOT)} exists")
        return json.loads(out.read_text(encoding="utf-8"))

    # Determine think override: sanity cell forces think=ON; other cells
    # inherit (workspace .env sets JAMES_GEMMA4_E4B_THINK_OFF=1 for the
    # primary matrix). Pass through to bench subprocess via _cell_env.
    think_override: Optional[bool] = False if sanity_think_on else None
    runs: List[FiveAxisResult] = []
    # Per-run per-question_type breakdowns (α-5 plan Step 6 cross-tab).
    # Empty for step7 fixtures that don't carry the field — those cells
    # simply skip the per-type aggregation.
    runs_by_type: List[Dict[str, FiveAxisResult]] = []
    run_paths: List[str] = []
    cell_label = (f"{sector_cell}/{tier}" if sector_cell
                  else f"{row}/{tier}")
    cell_label += " (sanity think=ON)" if sanity_think_on else ""
    for i in range(n_runs):
        bench_path = _run_single_bench(row, tier, i,
                                       suite=suite,
                                       think_override=think_override,
                                       sector_cell=sector_cell)
        if bench_path is None:
            print(f"[cell {cell_label}] run {i + 1} failed to produce "
                  f"bench output — aborting cell")
            return None
        result = score_five_axis(bench_path, fixture)
        print(f"[cell {cell_label} run {i + 1}] {result.summary()}")
        runs.append(result)
        runs_by_type.append(score_five_axis_by_question_type(bench_path, fixture))
        run_paths.append(str(bench_path.relative_to(ROOT)))

    aggregate = _aggregate_runs(runs)
    # Per-question_type aggregation. Same shape as `aggregate` but keyed
    # by question_type. Empty for non-cross-tab suites.
    aggregate_by_type: Dict[str, Dict[str, Any]] = {}
    if runs_by_type and any(runs_by_type):
        all_types: set[str] = set()
        for d in runs_by_type:
            all_types.update(d.keys())
        for qt in sorted(all_types):
            sub_runs: List[FiveAxisResult] = [
                d[qt] for d in runs_by_type if qt in d
            ]
            if sub_runs:
                aggregate_by_type[qt] = _aggregate_runs(sub_runs)

    # Compose the effective env block — row flags + sector overlay
    # (α-6). The cell JSON records what *actually* ran, not just the
    # row defaults.
    effective_env: Dict[str, str] = dict(_ROW_ENVS[row])
    if sector_cell:
        effective_env.update(_SECTOR_CELL_ENVS[sector_cell])

    payload = {
        # v3 adds optional sector_cell + sector_cell_label fields. Cells
        # without --sector-cells stay schema-v2 compatible.
        "schema": "qvt-ablation-cell-v3" if sector_cell else "qvt-ablation-cell-v2",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": sha,
        "row": row,
        "row_label": _ROW_LABELS[row],
        "tier": tier,
        "model": _TIER_MODELS[tier],
        "env": effective_env,
        "fixed_env": _FIXED_ENV,
        # Step 9 — sanity cell flag travels in the JSON so the report
        # writer can distinguish it from the primary L1/M_M (think=OFF).
        "sanity_think_on": bool(sanity_think_on),
        # α-6 — sector_cell metadata (None when classic row-based cell)
        "sector_cell": sector_cell,
        "sector_cell_label": (_SECTOR_CELL_LABELS.get(sector_cell)
                              if sector_cell else None),
        "fixture_version": fixture.get("version"),
        "n_runs": n_runs,
        "aggregate": aggregate,
        "aggregate_by_question_type": aggregate_by_type,
        "runs": [
            {"bench_output": run_paths[i], "scores": runs[i].to_dict()}
            for i in range(n_runs)
        ],
    }
    _resolve_output_dir().mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    try:
        rel = out.relative_to(ROOT)
    except ValueError:
        rel = out
    print(f"[cell {cell_label}] wrote {rel}")
    return payload


# ---------------------------------------------------------------------------
# Report rendering (--render-report)
# ---------------------------------------------------------------------------

_QUALITY_AXES = ("path_coverage", "graded_answer", "abstention_f1")
_COST_AXES = ("token_cost", "latency_cost")


def _classify_delta(deltas: Dict[str, float], noise_band: Dict[str, float]) -> str:
    """3-axis quality verdict (legacy, used by step7 path).

    Memo §3.1 verdict rule — positive / mixed / zero / negative / regression
    against quality axes only. Kept for back-compat; the α-5 5-axis
    runner uses `_classify_five_axis_delta` instead.
    """
    positives = []
    negatives = []
    for axis in _QUALITY_AXES:
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


def _classify_five_axis_delta(deltas: Dict[str, float],
                              noise_band: Dict[str, float]) -> str:
    """5-axis Pareto-aware verdict (plan Step 5).

    Quality side: any quality axis Δ > +noise_band ⇒ quality_positive.
                  any quality axis Δ < -noise_band ⇒ quality_negative.
    Cost side  : cost axis is "lower is better", so token/latency Δ
                  < -noise_band (numerically smaller than baseline) is
                  cost-positive, and Δ > +noise_band is cost-regression.

    Combined verdicts (plan §implementation step 5):
      - quality_positive + cost_positive  → "strong-adopt"
      - quality_positive + cost_flat      → "adopt"
      - quality_flat     + cost_positive  → "efficiency-adopt"
      - quality_positive + cost_negative  → "tier-gated"
      - quality_negative + *              → "reject"  (no cost gain redeems quality loss)
      - else (quality_flat + cost_flat)   → "zero"
    """
    q_pos = q_neg = 0
    for axis in _QUALITY_AXES:
        d = deltas.get(axis, 0.0)
        band = noise_band.get(axis, 0.0)
        if d > band:
            q_pos += 1
        elif d < -band:
            q_neg += 1
    c_pos = c_neg = 0
    for axis in _COST_AXES:
        d = deltas.get(axis, 0.0)
        band = noise_band.get(axis, 0.0)
        # Cost down (Δ < -band) is good; cost up (Δ > +band) is bad.
        if d < -band:
            c_pos += 1
        elif d > band:
            c_neg += 1
    if q_neg > 0:
        return "reject"
    if q_pos > 0 and c_pos > 0 and c_neg == 0:
        return "strong-adopt"
    if q_pos > 0 and c_pos == 0 and c_neg == 0:
        return "adopt"
    if q_pos > 0 and c_neg > 0:
        return "tier-gated"
    if q_pos == 0 and c_pos > 0 and c_neg == 0:
        return "efficiency-adopt"
    return "zero"


def _read_baseline() -> Optional[Dict[str, Any]]:
    baseline_dir = _resolve_baseline_dir()
    files = sorted(baseline_dir.glob("baseline_*.json"))
    if not files:
        print(f"[report] no baseline JSON under {baseline_dir}")
        return None
    # Most recent SHA — operator captures one baseline per release.
    latest = files[-1]
    print(f"[report] using baseline {latest}")
    return json.loads(latest.read_text(encoding="utf-8"))


def _render_report(out_path: Path) -> int:
    baseline = _read_baseline()
    if baseline is None:
        return 4
    base_agg = baseline.get("aggregate", {})
    # 5-axis baseline medians + noise bands.
    _ALL_AXES = ("path_coverage", "graded_answer", "abstention_f1",
                 "token_cost", "latency_cost")
    base_med = {
        ax: base_agg.get(ax, {}).get("median") for ax in _ALL_AXES
    }
    base_noise = {
        ax: base_agg.get(ax, {}).get("noise_band", 0.0) for ax in _ALL_AXES
    }

    cells: List[Dict[str, Any]] = []
    for row in _ROW_ENVS:
        for tier in _TIER_MODELS:
            p = _cell_output_path(row, tier)
            if not p.exists():
                continue
            cells.append(json.loads(p.read_text(encoding="utf-8")))

    # α-6 sector cells (qvt-ablation-cell-C_*.json). Stored under the
    # same output dir; picked up separately so the report can render
    # the sector axis below the row axis.
    sector_cells: List[Dict[str, Any]] = []
    for sc in _SECTOR_CELL_ENVS:
        for tier in _TIER_MODELS:
            p = _cell_output_path("L1", tier, sector_cell=sc)
            if not p.exists():
                continue
            sector_cells.append(json.loads(p.read_text(encoding="utf-8")))

    if not cells and not sector_cells:
        print(f"[report] no per-cell JSONs found under "
              f"{_resolve_output_dir()}")
        return 5

    rows: List[str] = [
        "# QVT α-5 ablation matrix — 5-axis × 18-cell verdict",
        "",
        f"**Baseline**: `{baseline.get('git_sha', 'unknown')}` "
        f"(captured {baseline.get('captured_at', '?')}).",
        f"**Cells available**: {len(cells)}/{len(_ROW_ENVS) * len(_TIER_MODELS)}.",
        "",
        "| Row | Tier | Model | Path Δ | Graded Δ | Abst F1 Δ | "
        "Token Δ | Latency Δ (s) | Verdict |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for c in cells:
        agg = c.get("aggregate", {})
        med = {ax: agg.get(ax, {}).get("median") for ax in _ALL_AXES}
        deltas: Dict[str, float] = {}
        for axis in _ALL_AXES:
            if med[axis] is None or base_med[axis] is None:
                deltas[axis] = 0.0
            else:
                deltas[axis] = round(med[axis] - base_med[axis], 4)
        verdict = _classify_five_axis_delta(deltas, base_noise)
        rows.append(
            f"| {c['row']} ({c['row_label']}) | {c['tier']} | "
            f"`{c['model']}` | {deltas['path_coverage']:+.3f} | "
            f"{deltas['graded_answer']:+.3f} | "
            f"{deltas['abstention_f1']:+.3f} | "
            f"{deltas['token_cost']:+.0f} | "
            f"{deltas['latency_cost']:+.2f} | "
            f"**{verdict}** |"
        )

    rows += [
        "",
        "## 5-axis Pareto-aware verdict rule (plan Step 5)",
        "",
        "Per cell, Δ vs L1/M_M baseline median per axis. Noise band =",
        "max − min across the baseline's paired-N=3 runs.",
        "",
        "Quality axes (higher = better): path_coverage, graded_answer, abstention_f1.",
        "Cost axes (lower = better): token_cost (answer chars proxy), latency_cost (seconds).",
        "",
        "- **strong-adopt** — at least one quality Δ > +band AND at least",
        "  one cost Δ < −band (lower = improvement), no cost regression",
        "- **adopt** — quality+ on at least one axis, cost flat",
        "- **efficiency-adopt** — quality flat, cost down on at least one axis",
        "- **tier-gated** — quality+ but cost regressed (justify per tier;",
        "  small-tier accept, large-tier reject)",
        "- **reject** — any quality axis Δ < −band (no cost gain redeems)",
        "- **zero** — within noise band on all five",
        "",
        "## Routing policy decision",
        "",
        "| Per-tier pattern | Policy |",
        "|---|---|",
        "| `strong-adopt` or `adopt` on ≥ 2 tiers incl. M_M | enable as default (flip `.env.example`) |",
        "| `efficiency-adopt` on all tiers | enable as default (free efficiency) |",
        "| only one tier `*-adopt` | tier-gated (router keys on `JAMES_LLM_MODEL`) |",
        "| `zero` on all tiers | delete / document as inert (deprecation PR) |",
        "| `reject` on ≥ 1 tier | keep opt-in indefinitely |",
        "| `tier-gated` verdict on any cell | per-tier evaluation (small ≤ large?) |",
        "",
        "Follow-up PRs (one per layer with non-`zero` verdict) cite the",
        "specific cell here as their Quality Delta Card source.",
    ]

    # ──────────────────────────────────────────────────────────
    # Step 6 — Per-question_type cross-tab + routing policy recs.
    # Skipped silently when no cell carries `aggregate_by_question_type`
    # (legacy v1 cells, or step7 fixture without question_type).
    # ──────────────────────────────────────────────────────────
    cells_with_types = [c for c in cells if c.get("aggregate_by_question_type")]
    if cells_with_types:
        # Union of all question types across all cells.
        all_qts: set[str] = set()
        for c in cells_with_types:
            all_qts.update(c["aggregate_by_question_type"].keys())
        all_qts_sorted = sorted(all_qts)

        rows.append("")
        rows.append("## Cross-tab — verdict per `question_type` × `(row, tier)`")
        rows.append("")
        rows.append(
            "Per question_type Δ vs the **L1/M_M baseline of the same "
            "question_type** (intra-type comparison — keeps the "
            "baseline subgroup size and language consistent). Verdict "
            "uses the 5-axis Pareto rule."
        )
        rows.append("")
        # Find L1/M_M cell once for baseline per type.
        l1_mm_cell = None
        for c in cells_with_types:
            if c["row"] == "L1" and c["tier"] == "M_M":
                l1_mm_cell = c
                break
        if l1_mm_cell is None:
            rows.append("(no L1/M_M cell present — cross-tab uses global baseline instead)")
            rows.append("")

        def _per_type_base_med(qt: str) -> Dict[str, Optional[float]]:
            if l1_mm_cell is not None:
                ag = l1_mm_cell.get("aggregate_by_question_type", {}).get(qt, {})
            else:
                ag = base_agg  # fall back to global baseline
            return {ax: ag.get(ax, {}).get("median") for ax in _ALL_AXES}

        def _per_type_base_noise(qt: str) -> Dict[str, float]:
            if l1_mm_cell is not None:
                ag = l1_mm_cell.get("aggregate_by_question_type", {}).get(qt, {})
            else:
                ag = base_agg
            return {ax: ag.get(ax, {}).get("noise_band", 0.0) for ax in _ALL_AXES}

        # Routing policy aggregator: per question_type, collect winning
        # (cell, verdict) so the recommended routing rule is sourced
        # from the strongest cell per type.
        per_type_winners: Dict[str, List[tuple]] = {qt: [] for qt in all_qts_sorted}

        for qt in all_qts_sorted:
            rows.append(f"### `{qt}`")
            rows.append("")
            rows.append("| Row | Tier | Model | Path Δ | Graded Δ | Abst F1 Δ | "
                        "Token Δ | Latency Δ | Verdict |")
            rows.append("|---|---|---|---|---|---|---|---|---|")
            base_med_qt = _per_type_base_med(qt)
            base_noise_qt = _per_type_base_noise(qt)
            for c in cells_with_types:
                ag_qt = c.get("aggregate_by_question_type", {}).get(qt)
                if not ag_qt:
                    continue
                med = {ax: ag_qt.get(ax, {}).get("median") for ax in _ALL_AXES}
                deltas_qt: Dict[str, float] = {}
                for axis in _ALL_AXES:
                    if med[axis] is None or base_med_qt[axis] is None:
                        deltas_qt[axis] = 0.0
                    else:
                        deltas_qt[axis] = round(med[axis] - base_med_qt[axis], 4)
                verdict_qt = _classify_five_axis_delta(deltas_qt, base_noise_qt)
                rows.append(
                    f"| {c['row']} | {c['tier']} | `{c['model']}` | "
                    f"{deltas_qt['path_coverage']:+.3f} | "
                    f"{deltas_qt['graded_answer']:+.3f} | "
                    f"{deltas_qt['abstention_f1']:+.3f} | "
                    f"{deltas_qt['token_cost']:+.0f} | "
                    f"{deltas_qt['latency_cost']:+.2f} | "
                    f"**{verdict_qt}** |"
                )
                if verdict_qt in ("strong-adopt", "adopt", "efficiency-adopt"):
                    per_type_winners[qt].append(
                        (verdict_qt, c['row'], c['tier'], c['model'])
                    )
            rows.append("")

        # Routing policy recommendation — per question_type, pick the
        # strongest verdict cell. Priority: strong-adopt > adopt >
        # efficiency-adopt. Within tier preference: M_M (production
        # default) > M_S > M_L, so a tie prefers the production-tier cell.
        rows.append("## Routing policy recommendation (auto-generated)")
        rows.append("")
        rows.append(
            "Each row maps a query type to a (model, layer-stack) recipe "
            "derived from the strongest verdict cell on that type. "
            "Operator: feed these into the routing layer's policy file. "
            "Plan §6 deliverable for user requirement #2."
        )
        rows.append("")
        rows.append("| Query type | Recommended (model, row) | Source verdict | Evidence cell |")
        rows.append("|---|---|---|---|")

        _VERDICT_RANK = {"strong-adopt": 3, "adopt": 2, "efficiency-adopt": 1}
        _TIER_RANK = {"M_M": 3, "M_S": 2, "M_L": 1,
                      "M_XS": 0, "M_XL": 0}  # prefer production; α-6 scale-ladder tiers tied last
        for qt in all_qts_sorted:
            winners = per_type_winners[qt]
            if not winners:
                rows.append(f"| `{qt}` | n/a — no adopt verdict | — | — |")
                continue
            # Sort by (verdict rank desc, tier rank desc) — best first.
            winners.sort(key=lambda w: (_VERDICT_RANK[w[0]], _TIER_RANK[w[1]]),
                         reverse=True)
            verdict, row_id, tier_id, model = winners[0]
            rows.append(
                f"| `{qt}` | `{model}` + **{row_id}** ({_ROW_LABELS[row_id]}) | "
                f"{verdict} | {row_id}/{tier_id} |"
            )
        rows.append("")

    # ──────────────────────────────────────────────────────────
    # α-6 — sector cell axis. Rendered separately from the row axis
    # because sector cells answer a different question: "does adding
    # this JAMES sector help vs vanilla LLM / vanilla RAG?" rather
    # than "does adding this routing flag help vs production baseline?"
    # The same 5-axis Pareto rule applies, against the same L1 baseline.
    # ──────────────────────────────────────────────────────────
    if sector_cells:
        rows += [
            "",
            "## α-6 sector-cells — what each JAMES sector adds vs vanilla",
            "",
            "Cells layer JAMES infrastructure sectors on top of the LLM. "
            "Δ vs L1/M_M baseline (= JAMES full stack). "
            "Reading: a *positive* Δ on a partial cell means the sectors "
            "ALREADY ON in that cell match the full stack's quality; a "
            "*negative* Δ means the removed sectors were load-bearing. "
            "Per α-6 design memo §2 + §5.6 layer-intent matrix.",
            "",
            "| Cell | Tier | Model | Path Δ | Graded Δ | Abst F1 Δ | "
            "Token Δ | Latency Δ (s) | Verdict |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for c in sector_cells:
            agg = c.get("aggregate", {})
            med = {ax: agg.get(ax, {}).get("median") for ax in _ALL_AXES}
            deltas_sc: Dict[str, float] = {}
            for axis in _ALL_AXES:
                if med[axis] is None or base_med[axis] is None:
                    deltas_sc[axis] = 0.0
                else:
                    deltas_sc[axis] = round(med[axis] - base_med[axis], 4)
            verdict_sc = _classify_five_axis_delta(deltas_sc, base_noise)
            sc_id = c.get("sector_cell") or c.get("row")
            sc_label = c.get("sector_cell_label") or ""
            rows.append(
                f"| {sc_id} ({sc_label}) | {c['tier']} | "
                f"`{c['model']}` | {deltas_sc['path_coverage']:+.3f} | "
                f"{deltas_sc['graded_answer']:+.3f} | "
                f"{deltas_sc['abstention_f1']:+.3f} | "
                f"{deltas_sc['token_cost']:+.0f} | "
                f"{deltas_sc['latency_cost']:+.2f} | "
                f"**{verdict_sc}** |"
            )
        # Pairwise progression — the intended α-6 reading. Each row
        # shows what ONE more sector added when stacked onto the
        # previous configuration. Operator-friendly framing.
        _PROGRESSION = [
            ("C_minus", "C_rag-basic", "+ S1 RAG retrieval"),
            ("C_rag-basic", "C_rag-cited", "+ S4 citation"),
            ("C_rag-cited", "C_rag-graph", "+ S2 graph + S3 preproc"),
            ("C_rag-graph", "C_rag-full", "+ S5 abstention + S6 cognitive (= α-5 L1)"),
            ("C_rag-full", "C_rag-routed", "+ routing layers (= α-5 L5)"),
        ]
        sc_by_id = {c.get("sector_cell"): c for c in sector_cells
                    if c.get("sector_cell")}
        # Include L1/L5 row cells under their sector-name aliases so
        # the progression table can reach them.
        for c in cells:
            if c.get("row") == "L1":
                sc_by_id.setdefault("C_rag-full", c)
            elif c.get("row") == "L5":
                sc_by_id.setdefault("C_rag-routed", c)
        rows += [
            "",
            "### Sector-progression deltas (cell-to-cell)",
            "",
            "What each marginal sector contributes when added to the "
            "previous configuration. Δ here is *cell-to-previous-cell*, "
            "not vs L1 baseline. This is the publishable answer to "
            "user requirement *\"각 sector 추가 시 좋아지나?\"*",
            "",
            "| From → To | Sector added | Path Δ | Graded Δ | Abst F1 Δ | "
            "Token Δ | Latency Δ |",
            "|---|---|---|---|---|---|---|",
        ]
        for from_id, to_id, what in _PROGRESSION:
            a = sc_by_id.get(from_id)
            b = sc_by_id.get(to_id)
            if a is None or b is None:
                rows.append(
                    f"| {from_id} → {to_id} | {what} | _missing_ | _missing_ | _missing_ | _missing_ | _missing_ |"
                )
                continue
            ag_a = a.get("aggregate", {})
            ag_b = b.get("aggregate", {})
            med_a = {ax: ag_a.get(ax, {}).get("median") for ax in _ALL_AXES}
            med_b = {ax: ag_b.get(ax, {}).get("median") for ax in _ALL_AXES}
            d_path = (med_b["path_coverage"] or 0) - (med_a["path_coverage"] or 0)
            d_graded = (med_b["graded_answer"] or 0) - (med_a["graded_answer"] or 0)
            d_abst = (med_b["abstention_f1"] or 0) - (med_a["abstention_f1"] or 0)
            d_token = (med_b["token_cost"] or 0) - (med_a["token_cost"] or 0)
            d_lat = (med_b["latency_cost"] or 0) - (med_a["latency_cost"] or 0)
            rows.append(
                f"| {from_id} → {to_id} | {what} | "
                f"{d_path:+.3f} | {d_graded:+.3f} | {d_abst:+.3f} | "
                f"{d_token:+.0f} | {d_lat:+.2f} |"
            )
        rows.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(rows), encoding="utf-8")
    # Defensive — out_path may live outside ROOT when the operator passes
    # an absolute path or runs against a JAMES_WORKSPACE that's not a
    # subpath of the project. relative_to would raise ValueError; fall
    # back to the absolute path so the diagnostic line still prints.
    try:
        rel = out_path.relative_to(ROOT)
    except ValueError:
        rel = out_path
    print(f"[report] wrote {rel}")
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
        help="Comma-separated subset of M_XS/M_S/M_M/M_L/M_XL (default: all).",
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
    parser.add_argument(
        "--sanity-think-on", action="store_true",
        help="Plan Step 9 sanity cell — additionally run the L1/M_M cell "
             "with `JAMES_GEMMA4_E4B_THINK_OFF` unset (production default "
             "= think=ON). Output JSON gets a `-thinkON` suffix and the "
             "5-axis Δ vs L1/M_M (primary, think=OFF) lands in the report "
             "as the A2 default-flip evidence supplement. ~22 min extra "
             "compute at n_runs=3.",
    )
    parser.add_argument(
        "--suite", type=str, default="step7",
        help="Suite name. Use 'multihop_rag' for the α-5 external "
             "benchmark (workspace-resolved fixture).",
    )
    parser.add_argument(
        "--sector-cells", type=str, default=None,
        help="α-6 sector ablation cells (comma-separated). Available: "
             f"{','.join(sorted(_SECTOR_CELL_ENVS.keys()))}. Each cell "
             "overlays its sector-flag dict on top of L1's row env. "
             "Mutually exclusive with --rows.",
    )
    args = parser.parse_args(argv)

    if args.render_report:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        out_path = _REPORT_DIR / f"v0.4-qvt-ablation-matrix-{ts}.md"
        return _render_report(out_path)

    # T0 smoke gate (α-5 prereq §3) takes precedence over --rows/--tiers
    # so an operator can fire the gate run with one flag.
    if args.t0_smoke:
        if args.rows or args.tiers or args.sector_cells:
            print("[error] --t0-smoke implies --tiers M_M --rows L1,L5; "
                  "remove --rows/--tiers/--sector-cells or drop --t0-smoke")
            return 7
        args.rows = "L1,L5"
        args.tiers = "M_M"
        print("[t0-smoke] α-5 prereq §3 gate — running "
              "M_M × {L1, L5} (~2.2 h). Verdict rule: if |graded_answer "
              "Δ| < 0.05 → matrix null at production tier → STOP.")

    # α-6 — --sector-cells is mutually exclusive with --rows. When
    # passed, the runner iterates over (sector_cell, tier) pairs;
    # the row used as base is always L1 (production).
    sector_cells: List[Optional[str]] = []
    if args.sector_cells:
        if args.rows:
            print("[error] --sector-cells is mutually exclusive with --rows")
            return 7
        sector_cells = _parse_subset(
            args.sector_cells, list(_SECTOR_CELL_ENVS.keys()), "sector-cells")
        # In sector mode the row is fixed to L1 (production-default
        # ENTITY_ANCHOR + QUERY_REWRITE; sector overlay further toggles).
        args.rows = "L1"

    rows = _parse_subset(args.rows, list(_ROW_ENVS.keys()), "rows")
    tiers = _parse_subset(args.tiers, list(_TIER_MODELS.keys()), "tiers")
    sha = _current_git_sha() or "unknown"
    fixture_path = _resolve_fixture(args.suite)
    out_dir = _resolve_output_dir()

    # Cell count includes sector cells (α-6) when in sector mode.
    n_grid_cells = (len(sector_cells) if sector_cells else len(rows)) * len(tiers)
    n_cells = n_grid_cells + (1 if args.sanity_think_on else 0)
    print("=== QVT α-5 ablation matrix ===")
    print(f"git_sha:    {sha}")
    print(f"suite:      {args.suite}")
    print(f"fixture:    {fixture_path}")
    print(f"output:     {out_dir}")
    if sector_cells:
        print(f"sector_cells: {sector_cells} (base row: L1)")
    else:
        print(f"rows:       {rows}")
    print(f"tiers:      {tiers}  → {[_TIER_MODELS[t] for t in tiers]}")
    print(f"n_runs:     {args.n_runs}")
    print(f"resume:     {args.resume}")
    print(f"sanity:     {'YES (M_M/L1 think=ON extra cell)' if args.sanity_think_on else 'no'}")
    print(f"cells:      {n_cells} "
          f"(~{round(n_cells * 66 / 60, 1)} h compute)")

    if args.dry_run:
        print("\n[dry-run] cells planned:")
        if sector_cells:
            for sc in sector_cells:
                for tier in tiers:
                    print(f"  {sc}/{tier} model={_TIER_MODELS[tier]} "
                          f"(L1 base + sector overlay)")
        else:
            for row in rows:
                for tier in tiers:
                    print(f"  {row}/{tier} model={_TIER_MODELS[tier]} "
                          f"env={_ROW_ENVS[row]}")
        if args.sanity_think_on:
            print(f"  L1/M_M sanity (think=ON, suffix '-thinkON') "
                  f"model={_TIER_MODELS['M_M']}")
        return 0

    if not fixture_path.exists():
        print(f"[error] fixture {fixture_path} missing — build it first "
              f"(e.g. scripts/hotpot/build_fixture.py for multihop_rag)")
        return 2
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    n_ok = 0
    n_fail = 0
    if sector_cells:
        for sc in sector_cells:
            for tier in tiers:
                payload = _run_cell("L1", tier, args.n_runs, fixture, sha,
                                    resume=args.resume, suite=args.suite,
                                    sector_cell=sc)
                if payload is None:
                    n_fail += 1
                else:
                    n_ok += 1
    else:
        for row in rows:
            for tier in tiers:
                payload = _run_cell(row, tier, args.n_runs, fixture, sha,
                                    resume=args.resume, suite=args.suite)
                if payload is None:
                    n_fail += 1
                else:
                    n_ok += 1

    # Step 9 sanity cell — run after the standard grid so its think=ON
    # measurement uses the same fixture + same runner state.
    if args.sanity_think_on:
        if "M_M" not in tiers or "L1" not in rows:
            print("[sanity] WARNING: --sanity-think-on requires the standard "
                  "L1/M_M cell in the run. Skipping sanity cell because "
                  "neither L1 nor M_M is in the subset.")
        else:
            sanity_payload = _run_cell(
                "L1", "M_M", args.n_runs, fixture, sha,
                resume=args.resume, sanity_think_on=True, suite=args.suite,
            )
            if sanity_payload is None:
                n_fail += 1
            else:
                n_ok += 1

    print(f"\n[done] cells succeeded: {n_ok}, failed: {n_fail}")
    print(f"Per-cell JSONs at {out_dir}.")

    # T0 smoke verdict — print the prereq §3 decision in-line so the
    # operator knows whether to proceed to T1 or stop, without having
    # to re-render the report.
    if args.t0_smoke and n_fail == 0:
        l1 = _cell_output_path("L1", "M_M")
        l5 = _cell_output_path("L5", "M_M")
        if l1.exists() and l5.exists():
            j1 = json.loads(l1.read_text(encoding="utf-8"))
            j5 = json.loads(l5.read_text(encoding="utf-8"))
            # 5-axis deltas. Quality threshold 0.05 (unchanged) +
            # cost thresholds: ~10% of L1 median for each cost axis.
            def _med(j: dict, axis: str) -> float:
                return float(j["aggregate"].get(axis, {}).get("median") or 0.0)
            quality_axes = ("path_coverage", "graded_answer", "abstention_f1")
            cost_axes = ("token_cost", "latency_cost")
            quality_d = {ax: round(_med(j5, ax) - _med(j1, ax), 4) for ax in quality_axes}
            cost_d = {ax: round(_med(j5, ax) - _med(j1, ax), 4) for ax in cost_axes}
            print(f"\n=== T0 smoke verdict (5-axis) ===")
            for ax, d in quality_d.items():
                print(f"  {ax:15s} L1={_med(j1, ax):.4f} L5={_med(j5, ax):.4f} Δ={d:+.4f}")
            for ax, d in cost_d.items():
                print(f"  {ax:15s} L1={_med(j1, ax):.4f} L5={_med(j5, ax):.4f} Δ={d:+.4f} (down=better)")
            # Quality signal: any quality axis Δ moves > 0.05.
            quality_moved = any(abs(d) >= 0.05 for d in quality_d.values())
            # Cost signal: token_cost Δ moves > 10% of L1, OR latency Δ > 10% of L1.
            l1_token = max(_med(j1, "token_cost"), 1.0)
            l1_lat = max(_med(j1, "latency_cost"), 0.1)
            cost_moved = (abs(cost_d["token_cost"]) >= 0.10 * l1_token
                          or abs(cost_d["latency_cost"]) >= 0.10 * l1_lat)
            if not quality_moved and not cost_moved:
                print(
                    "VERDICT: matrix likely NULL at production tier "
                    "(no quality axis moves ≥ 0.05 AND no cost axis moves "
                    "≥ 10%). Do NOT run T2 (M_S / M_L) — savings ~18 h."
                )
            elif quality_moved and not cost_moved:
                print(
                    "VERDICT: matrix has QUALITY signal at production tier. "
                    "Proceed to T1 (`--tiers M_M`, ~5.5 h)."
                )
            elif cost_moved and not quality_moved:
                print(
                    "VERDICT: matrix has COST-only signal at production tier "
                    "(quality flat, cost ≥ 10% Δ). Likely efficiency-adopt "
                    "verdict — proceed to T1 to isolate which layer."
                )
            else:
                print(
                    "VERDICT: matrix has both QUALITY and COST signal. "
                    "Proceed to T1 + likely T2 for tier-gating decisions."
                )

    print(f"\nRender the consolidated report with:\n"
          f"  python scripts/qvt_ablation_matrix.py --render-report")
    return 0 if n_fail == 0 else 6


if __name__ == "__main__":
    raise SystemExit(main())
