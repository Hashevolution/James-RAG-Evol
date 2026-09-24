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

# Windows consoles default to cp949 in this operator's environment, and
# this module's help text / report strings contain em dashes. Without
# this, `--help` itself dies with UnicodeEncodeError before printing a
# single option. Same class as the UTF-8 fix in the LRB claude reranker
# (#1124) — a measurement tool that cannot print is a measurement tool
# the operator cannot drive.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass

from eval.qvt.oracle import (  # noqa: E402
    FiveAxisResult,
    score_five_axis,
    score_five_axis_by_question_type,
)
# Shared with scripts/qvt_capture_baseline.py. This runner's server
# lifecycle was a copy of that script, so its guards (#1141-#1143, #1147)
# never reached here - the 2026-09-22 T0 smoke measured 4/7 generation
# failures as abstentions. See eval/qvt/capture_integrity.py.
from eval.qvt import capture_integrity  # noqa: E402
from eval.qvt import host_state  # noqa: E402

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
        # α-8: typed filter disabled here so the cell is a pure pre-α-8
        # graph baseline; comparison reference for C_rag-ontology.
        "JAMES_DISABLE_ABSTENTION":       "1",
        "JAMES_DISABLE_COGNITIVE_STAGES": "1",
        "JAMES_DISABLE_TYPED_FILTER":     "1",
    },
    "C_rag-ontology": {
        # α-8 Phase A/B: C_rag-graph + typed entity filter (R1-R5
        # evidence-of-absence preservation per design memo §2.4).
        # All other layers identical to C_rag-graph so Δ measures the
        # typed filter contribution in isolation.
        "JAMES_DISABLE_ABSTENTION":       "1",
        "JAMES_DISABLE_COGNITIVE_STAGES": "1",
        # JAMES_DISABLE_TYPED_FILTER intentionally NOT set → filter ON.
    },
    "C_rag-full": {
        # Equivalent to α-5 L1 — all sectors on, no routing layers.
        # α-8: typed filter ON here too (matches default production state
        # once α-8 is wired; only C_rag-graph keeps the pre-α-8 path for
        # baseline comparison).
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
    "C_rag-graph":  "+ RAG + graph + S3 preproc + citation (pre-α-8)",
    "C_rag-ontology": "+ typed filter (α-8 R1-R5 evidence-of-absence)",
    "C_rag-full":   "JAMES full stack (= α-5 L1; α-8 typed filter ON)",
    "C_rag-routed": "JAMES + routing layers (= α-5 L5)",
}


# Model tier → Ollama tag (memo §2.2; α-6 Phase 3a adds M_XS / M_XL;
# α-8 cloud tier extension 2026-06-04 adds M_CLOUD — see
# `docs/design/v0.4-alpha-8-cloud-tier-extension.md` §2.1).
#
# For Ollama tiers the value IS the routing key (passed to
# JAMES_LLM_MODEL). For M_CLOUD the value is an empty sentinel: the
# claude_code_cli backend ignores JAMES_LLM_MODEL; routing happens via
# _TIER_BACKEND_OVERRIDE below.
_TIER_MODELS: Dict[str, str] = {
    "M_XS": "gemma3:1b",   # α-6 Phase 3a — extreme small (capability floor probe)
    "M_S": "gemma3:4b",
    "M_M": "gemma4:e4b",   # production default; α-3 baseline tier
    "M_L": "gemma3:12b",
    "M_XL": "gemma3:27b",  # α-6 Phase 3a — large (saturation point probe)
    "M_MIXTRAL": "mixtral:8x7b",  # paper-baseline control (MultiHop-RAG
                                  # Table 6: Mixtral-8x7B retrieved 0.32)
    "M_CLOUD": "",         # α-8 cloud tier — Claude default model (CLI picks)
}

# Default tier universe when --tiers is omitted = the 5 gemma scale
# ladder only. M_MIXTRAL (paper-baseline control, ~26GB CPU-offload slow)
# and M_CLOUD (cloud, Max-plan quota) are **opt-in** via explicit
# --tiers so a stray run doesn't pull a 26GB model or burn cloud quota.
_DEFAULT_TIERS: Tuple[str, ...] = ("M_XS", "M_S", "M_M", "M_L", "M_XL")


# α-8 cloud tier (2026-06-04) — tiers that route through a non-Ollama
# backend need extra env vars set at server-spawn time. Per design memo
# §2.1 (Option B): kept as a sibling dict so the existing 5 local tiers
# stay byte-identical (no struct change to _TIER_MODELS values).
#
# Tier id → dict of env vars to apply ON TOP OF the row env in
# `_cell_env`. For tiers not in this dict, `_cell_env` falls back to
# the pre-α-8-cloud `JAMES_LLM_MODEL = _TIER_MODELS[tier]` path
# (regression-safe).
_TIER_BACKEND_OVERRIDE: Dict[str, Dict[str, str]] = {
    "M_CLOUD": {
        # S5 (PR #702) wire — trace_synth_call detects this triplet and
        # routes synth-stage calls through core.abstraction.run_cloud_egress
        # → claude_code_cli backend → real `claude -p` headless CLI.
        # PR #704 fix added Windows env essentials + neutral cwd default
        # to the backend itself.
        "JAMES_ENABLE_CLAUDE_BACKEND": "1",  # opt-in registry switch
        "JAMES_FORCE_CLOUD":            "1",  # synth wrap gate
        "JAMES_REASONING_BACKEND":      "claude_code_cli",  # backend resolution default
    },
}


def _tier_backend_id(tier: str) -> str:
    """Resolve the backend id that a tier's cell will run under.

    M_CLOUD → "claude_code_cli". Local tiers (no override) → the
    legacy default "ollama_local". Used by `_run_cell` payload's new
    `backend_id` field (cell JSON v4) so cloud cells are
    unambiguously identifiable in the output dir alongside local cells.
    """
    override = _TIER_BACKEND_OVERRIDE.get(tier, {})
    return override.get("JAMES_REASONING_BACKEND", "ollama_local")


# ---------------------------------------------------------------------------
# Layer-evidence capture (cell JSON v5)
# ---------------------------------------------------------------------------
#
# CLAUDE.md rule #2: "Layer measurement prerequisites must also be
# confirmed — e.g., AUTO_ROUTER PRs require multi-tier backend
# registration evidence (otherwise the layer is no-op and the PR's
# number is 'not in evidence,' not 'no effect')."
#
# Until cell JSON v5 the matrix recorded the *flag* (JAMES_AUTO_ROUTER=1)
# but never whether the router had anywhere to route to. With a
# single-backend registry `_first_in_tier` returns None for every
# non-small tier and the router falls back to the legacy backend —
# `core/reasoning/router.py::_legacy_backend_id` documents exactly this
# "small-tier-only fleet" case. A null Δ on L2/L5 then reads as "the
# layer does nothing" when the truth is "the layer was never exercised".
#
# This is the same failure shape as the LRB reranker fallback (#1123):
# something silently did not happen, and the artifact looked clean.

_ROUTER_TIERS: Tuple[str, ...] = ("small", "medium", "large", "cloud")
_FLAG_ON = {"1", "true", "yes", "on"}
_registry_snapshot_cache: Optional[Dict[str, Any]] = None


def _backend_registry_snapshot() -> Dict[str, Any]:
    """Registered backends + tier membership, as seen by this process.

    ``probe`` is recorded honestly: this is the *runner's* registry, not
    the spawned server's. They run the same code on the same machine, and
    the cell env this runner passes does not enable extra backends, so the
    two agree — but a future cell that sets e.g.
    ``JAMES_ENABLE_CLAUDE_BACKEND`` in the server env only would diverge,
    and the field name says where the number came from.
    """
    global _registry_snapshot_cache
    if _registry_snapshot_cache is not None:
        return _registry_snapshot_cache
    try:
        from core.reasoning import backends as _backends  # noqa: WPS433
        snap: Dict[str, Any] = {
            "registered": sorted(_backends.list_backends()),
            "by_tier": {
                tier: sorted(_backends.list_backends_by_tier(tier))
                for tier in _ROUTER_TIERS
            },
            "probe": "runner-process",
            "error": None,
        }
    except Exception as exc:  # pragma: no cover - defensive
        snap = {
            "registered": None,
            "by_tier": None,
            "probe": "runner-process",
            "error": f"{type(exc).__name__}: {exc}",
        }
    _registry_snapshot_cache = snap
    return snap


def _router_evidence(
    effective_env: Dict[str, str],
    snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    """Is AUTO_ROUTER actually exercisable in this cell's environment?

    ``in_evidence`` is deliberately tri-state:

      True  — flag on AND ≥2 tiers hold a backend, so an escalation
              decision can change which backend answers.
      False — flag on but <2 tiers populated: the router runs, logs its
              audit rows, and resolves to the same backend every time.
              A Δ measured here is **not in evidence**, not "no effect".
      None  — flag off (nothing claimed), or the registry probe failed.
    """
    raw = str(effective_env.get("JAMES_AUTO_ROUTER", "0")).strip().lower()
    enabled = raw in _FLAG_ON
    by_tier = snapshot.get("by_tier")

    if by_tier is None:
        return {
            "enabled": enabled,
            "in_evidence": None,
            "reason": f"registry probe failed ({snapshot.get('error')})",
            "populated_tiers": None,
        }

    populated = [tier for tier, names in by_tier.items() if names]

    if not enabled:
        return {
            "enabled": False,
            "in_evidence": None,
            "reason": "AUTO_ROUTER off in this row — nothing claimed",
            "populated_tiers": populated,
        }

    if len(populated) >= 2:
        return {
            "enabled": True,
            "in_evidence": True,
            "reason": (
                f"{len(populated)} tiers populated ({', '.join(populated)}) "
                f"— an escalation can change the answering backend"
            ),
            "populated_tiers": populated,
        }

    return {
        "enabled": True,
        "in_evidence": False,
        "reason": (
            f"only {len(populated)} tier populated "
            f"({', '.join(populated) or 'none'}) out of "
            f"{len(_ROUTER_TIERS)} — every escalation resolves to the same "
            f"backend, so this cell measures AUTO_ROUTER as NOT IN EVIDENCE"
        ),
        "populated_tiers": populated,
    }


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SERVER_BASE_URL = os.environ.get("JAMES_BASE_URL", "http://127.0.0.1:8000")
SERVER_HEALTHZ = SERVER_BASE_URL.rstrip("/") + "/healthz"
SERVER_BOOT_TIMEOUT_SEC = 180  # heavier workspace boot
# α-6 Phase 3a: env override for gemma3:27b on GPU/CPU split (~6-8h C_rag-full)
BENCH_SUBPROCESS_TIMEOUT_SEC = int(
    os.environ.get("JAMES_BENCH_SUBPROCESS_TIMEOUT") or 14400
)

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
    # α-8 cloud tier (2026-06-04) — tiers in _TIER_BACKEND_OVERRIDE
    # route through a non-Ollama backend; JAMES_LLM_MODEL is
    # meaningless for the claude_code_cli backend (CLI picks the
    # model). Apply the cloud env triplet INSTEAD of JAMES_LLM_MODEL.
    # Local tiers (default branch) unchanged — regression-safe.
    # Risk #1 mitigation (2026-06-15) — bypass v0.6.1 LLM-settings DB
    # so the measurement subprocess's JAMES_LLM_MODEL env is the
    # source-of-truth. Without this an operator that set the admin
    # Settings card mid-cycle could silently shadow JAMES_LLM_MODEL.
    # See core/llm_settings.py::_use_db.
    # 2026-09-24 - plus the mode-aware routing kill-switch. Without it
    # resolve_for_mode(mode, requested="") answers chat / retrieval with
    # its preference-list top and ignores JAMES_LLM_MODEL, so every local
    # tier measured the same model under five labels. Applied before the
    # tier / sector overlays; neither sets these keys.
    env.update(capture_integrity.ROUTING_PIN_ENV)
    if tier in _TIER_BACKEND_OVERRIDE:
        env.update(_TIER_BACKEND_OVERRIDE[tier])
        # Explicitly remove JAMES_LLM_MODEL inherited from the OS env —
        # leaving an Ollama tag in the environment of a cloud-routed
        # run is confusing in the spawn log (the value is unused but
        # would show in env dumps).
        env.pop("JAMES_LLM_MODEL", None)
    else:
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
                      sector_cell: Optional[str] = None,
                      host_log: Optional[List[Dict[str, Any]]] = None,
                      ) -> Optional[Path]:
    """Run one bench subprocess against the configured suite.

    `host_log` (cell v6) - when given, one host-state record per run is
    appended to it, including runs that time out, since a slow host is
    the likeliest reason a run times out. Same shape as the baseline
    capture's `host_state` entries.

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
    pin = {k: server_env.get(k) for k in capture_integrity.ROUTING_PIN_ENV}
    print(f"    routing pin: {pin}")
    server = _spawn_server(server_env)
    if server is None:
        return None

    host: Dict[str, Any] = {"run": run_index + 1,
                            "before": host_state.static_snapshot()}
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
            with host_state.GpuSampler(interval_s=15.0) as gpu:
                subprocess.run(
                    [sys.executable, str(ROOT / "scripts" / "bench.py"),
                     f"--suite={suite}", "--mode=retrieval"],
                    env=bench_env,
                    cwd=str(ROOT),
                    capture_output=False,
                    check=False,
                    timeout=BENCH_SUBPROCESS_TIMEOUT_SEC,
                )
            host["gpu_during_bench"] = gpu.summary()
            # Which models were resident when the bench ended - checked
            # against resolved_models, which says what *should* answer.
            host["ollama_after_bench"] = host_state.read_ollama_ps()
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
        if host_log is not None:
            host_log.append(host)
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
    health_by_run: List[Dict[str, Any]] = []
    host_state_by_run: List[Dict[str, Any]] = []
    # What the spawned server will answer with - resolved from the env
    # _run_single_bench applies, not this process's env (#1143).
    resolved = capture_integrity.resolved_models(
        _cell_env(row, tier, think_override=think_override,
                  sector_cell=sector_cell))
    cell_label = (f"{sector_cell}/{tier}" if sector_cell
                  else f"{row}/{tier}")
    cell_label += " (sanity think=ON)" if sanity_think_on else ""
    for i in range(n_runs):
        bench_path = _run_single_bench(row, tier, i,
                                       suite=suite,
                                       think_override=think_override,
                                       sector_cell=sector_cell,
                                       host_log=host_state_by_run)
        if bench_path is None:
            print(f"[cell {cell_label}] run {i + 1} failed to produce "
                  f"bench output — aborting cell")
            return None
        health = capture_integrity.answer_health(bench_path)
        health_by_run.append(health)
        reason = capture_integrity.abort_reason(health)
        if reason:
            # No cell JSON is written: a partial or laundered cell on
            # disk would be picked up by --resume and --render-report
            # as if it were a measurement.
            print(f"[cell {cell_label} run {i + 1}] ABORT — {reason}.")
            for ex in health.get("examples") or []:
                print(f"    {ex}")
            print("    core/reasoning/pipeline.py softens these into "
                  "abstentions, so scoring them would record a failing "
                  "LLM as the system correctly declining.\n"
                  f"    effective model: {resolved.get('effective')}")
            return None
        result = score_five_axis(bench_path, fixture)
        print(f"[cell {cell_label} run {i + 1}] {result.summary()}  "
              f"(answers ok: {health['total'] - health['failed']}"
              f"/{health['total']})")
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

    # v5 — capture the layer prerequisite alongside the numbers, so the
    # artifact carries its own interpretation limits (rule #2).
    _registry_snap = _backend_registry_snapshot()
    _router_ev = _router_evidence(effective_env, _registry_snap)
    if _router_ev.get("in_evidence") is False:
        print(
            f"[cell {cell_label}] ⚠ AUTO_ROUTER is ON but NOT IN EVIDENCE — "
            f"{_router_ev['reason']}"
        )

    payload = {
        # Schema versioning (additive, forward-compat):
        #   v2 — base cell shape
        #   v3 — adds sector_cell + sector_cell_label (α-6)
        #   v4 — adds backend_id (α-8 cloud tier extension, 2026-06-04)
        #        — old renderers fall back to "ollama_local" for the
        #        missing field; new renderers distinguish cloud cells.
        #   v5 — adds backend_registry + layer_evidence (2026-09-22).
        #        Records whether AUTO_ROUTER had ≥2 populated tiers to
        #        route between, so an L2/L5 null Δ can be read as "not
        #        in evidence" rather than "no effect" (CLAUDE.md rule
        #        #2 layer-prerequisite clause). Pre-v5 cells simply
        #        lack the keys and render as "unknown".
        #   v6 - adds resolved_models + answer_health + host_state
        #        (2026-09-24), the baseline capture's guards, now shared
        #        via eval/qvt/capture_integrity.py. Pre-v6 cells ran
        #        without the routing pin: their `model` field is the
        #        tier label, not evidence of what answered.
        "schema": "qvt-ablation-cell-v6",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": sha,
        "row": row,
        "row_label": _ROW_LABELS[row],
        "tier": tier,
        "model": _TIER_MODELS[tier],
        "backend_id": _tier_backend_id(tier),  # α-8 cloud tier extension
        "env": effective_env,
        "fixed_env": _FIXED_ENV,
        # v5 — layer prerequisites (rule #2). See _router_evidence.
        "backend_registry": _registry_snap,
        "layer_evidence": {"auto_router": _router_ev},
        # v6 - integrity record. resolved_models.effective is what
        # answered; `model` above is only the tier's label.
        "resolved_models": resolved,
        "answer_health": health_by_run,
        "host_state": host_state_by_run,
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


_ALL_AXES: Tuple[str, ...] = _QUALITY_AXES + _COST_AXES


def _deltas_vs_baseline(
    med: Dict[str, Optional[float]],
    base_med: Dict[str, Optional[float]],
) -> Tuple[Dict[str, Optional[float]], set]:
    """Per-axis Δ, with "never compared" kept distinct from "equal".

    The previous shape collapsed both into ``0.0``::

        if med[axis] is None or base_med[axis] is None:
            deltas[axis] = 0.0

    That is a silent null. The on-disk baseline is
    ``qvt-baseline-v1`` (2026-05, three axes: path / graded /
    abstention) — it carries no ``token_cost`` or ``latency_cost``. So
    every cell rendered against it got ``token_cost Δ = 0.0`` with
    ``noise_band = 0.0``, the cost loop in
    ``_classify_five_axis_delta`` scored neither cost-positive nor
    cost-regression, and the verdict read *"cost flat"*. A cell that
    doubled token cost classified as **adopt** on the strength of a
    comparison that never happened.

    Returning ``None`` (and the axis name in ``unavailable``) lets the
    caller print ``n/a`` and lets the classifier abstain on that axis
    instead of inventing a flat reading.
    """
    deltas: Dict[str, Optional[float]] = {}
    unavailable: set = set()
    for axis in _ALL_AXES:
        base_v = base_med.get(axis)
        cell_v = med.get(axis)
        if base_v is None or cell_v is None:
            deltas[axis] = None
            unavailable.add(axis)
        else:
            deltas[axis] = round(cell_v - base_v, 4)
    return deltas, unavailable


def _fmt_delta(value: Optional[float], spec: str) -> str:
    """Render a Δ, or ``n/a`` when the axis was never comparable."""
    return "n/a" if value is None else format(value, spec)


def _classify_five_axis_delta(deltas: Dict[str, Any],
                              noise_band: Dict[str, float],
                              unavailable: Optional[set] = None) -> str:
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
    skip = unavailable or set()
    q_pos = q_neg = 0
    for axis in _QUALITY_AXES:
        if axis in skip:
            continue
        d = deltas.get(axis)
        if d is None:
            continue
        band = noise_band.get(axis, 0.0)
        if d > band:
            q_pos += 1
        elif d < -band:
            q_neg += 1
    c_pos = c_neg = 0
    cost_axes_compared = 0
    for axis in _COST_AXES:
        if axis in skip:
            continue
        d = deltas.get(axis)
        if d is None:
            continue
        cost_axes_compared += 1
        band = noise_band.get(axis, 0.0)
        # Cost down (Δ < -band) is good; cost up (Δ > +band) is bad.
        if d < -band:
            c_pos += 1
        elif d > band:
            c_neg += 1
    # No cost axis was comparable — say so rather than letting the
    # cost-flat branches ("adopt" / "zero") stand on nothing.
    if cost_axes_compared == 0:
        if q_neg > 0:
            return "reject (quality only — cost not in baseline)"
        if q_pos > 0:
            return "quality-positive (cost not in baseline)"
        return "quality-flat (cost not in baseline)"
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


def _fixture_mismatch(
    cell: Dict[str, Any],
    baseline: Dict[str, Any],
) -> Optional[str]:
    """Return a human-readable mismatch, or None when comparable.

    A Δ is only a measurement of the *layer* when both sides answered the
    same questions. step7 has moved v5 → v7 (queries were added: q13 meta
    inventory, then q14/q15/q16 narrow-scope), so a v7 cell minus a v5
    baseline is partly a measurement of the fixture change.

    The committed artifacts are exactly that shape — baseline
    ``step7-v5`` (2026-05-28) against cells ``step7-v7`` (2026-06-03) —
    and until now nothing compared the two fields. ``fixture_version``
    was written into every cell and never read.

    Unknown on either side returns None: absence of the field is not
    evidence of a mismatch, and pre-v3 cells predate it.
    """
    cell_fx = cell.get("fixture_version")
    base_fx = baseline.get("fixture_version")
    if not cell_fx or not base_fx or cell_fx == base_fx:
        return None
    return f"baseline {base_fx} vs cell {cell_fx}"


def _read_baseline() -> Optional[Dict[str, Any]]:
    """Load the most recently *captured* baseline.

    This used to be ``sorted(glob(...))[-1]`` under the comment "Most
    recent SHA". Filenames are ``baseline_<git-sha>.json`` and git SHAs
    are hex — their lexicographic order has nothing to do with time. The
    call picked the alphabetically greatest SHA and called it the latest.

    Concretely: once ``baseline_721e109.json`` exists, a *later* capture
    at any SHA sorting below it (``1a2b3c4``, ``0ff9911``, …) is silently
    ignored and every Δ in the report is measured against the stale one.
    Nothing in the output says which baseline lost.

    ``captured_at`` is the real recency signal, is ISO-8601 (so it sorts
    correctly as a string), and is written by
    ``scripts/qvt_capture_baseline.py`` into every baseline. Files that
    predate the field, or carry an unreadable one, fall back to mtime and
    are reported as such rather than silently ranked.
    """
    baseline_dir = _resolve_baseline_dir()
    files = sorted(baseline_dir.glob("baseline_*.json"))
    if not files:
        print(f"[report] no baseline JSON under {baseline_dir}")
        return None

    candidates: List[Tuple[str, str, Path, Dict[str, Any]]] = []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[report] skipping unreadable baseline {path.name}: {exc}")
            continue
        captured = payload.get("captured_at")
        if isinstance(captured, str) and captured:
            candidates.append((captured, "captured_at", path, payload))
        else:
            stamp = datetime.fromtimestamp(
                path.stat().st_mtime, tz=timezone.utc).isoformat()
            print(f"[report] {path.name} has no captured_at — ranking by "
                  f"file mtime ({stamp})")
            candidates.append((stamp, "mtime", path, payload))

    if not candidates:
        print(f"[report] no readable baseline JSON under {baseline_dir}")
        return None

    candidates.sort(key=lambda item: item[0])
    captured, how, latest, payload = candidates[-1]
    print(f"[report] using baseline {latest} "
          f"(captured {captured}, by {how}, "
          f"schema {payload.get('schema', 'unknown')}, "
          f"fixture {payload.get('fixture_version', 'unknown')})")
    if len(candidates) > 1:
        others = ", ".join(p.name for _c, _h, p, _pl in candidates[:-1])
        print(f"[report] {len(candidates) - 1} older baseline(s) ignored: "
              f"{others}")
    return payload


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

    # Cells whose fixture_version differs from the baseline's — their Δ
    # measures the fixture change as much as the layer. Computed over
    # every loaded cell up front, because the row table renders its
    # warning section before the sector table is walked.
    _fixture_gap_cells: List[Tuple[Dict[str, Any], str]] = [
        (c, gap)
        for c in (cells + sector_cells)
        if (gap := _fixture_mismatch(c, baseline)) is not None
    ]

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
    _router_gap_cells: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    # Axes the baseline (or a cell) never carried — rendered n/a and
    # abstained on, rather than silently compared as flat.
    _missing_axis_cells: set = set()
    for c in cells:
        agg = c.get("aggregate", {})
        med = {ax: agg.get(ax, {}).get("median") for ax in _ALL_AXES}
        deltas, _unavail = _deltas_vs_baseline(med, base_med)
        _missing_axis_cells.update(_unavail)
        _fx_gap = _fixture_mismatch(c, baseline)
        if _fx_gap:
            # Both sides answered different question sets — the Δ is not
            # a reading of this layer. Refuse the verdict outright rather
            # than qualify it; a qualified Pareto verdict still invites use.
            verdict = f"not comparable ({_fx_gap})"
        else:
            verdict = _classify_five_axis_delta(deltas, base_noise, _unavail)
        # α-8 cloud tier (2026-06-04) — local cells show model tag;
        # cloud cells (empty model + non-default backend_id) show the
        # backend id instead so the row is informative either way.
        # Pre-v4 cells (missing backend_id) read as "ollama_local" by
        # the .get default — backward compatible.
        model_tag = c.get("model") or ""
        backend_tag = c.get("backend_id", "ollama_local")
        tier_label = f"`{model_tag}`" if model_tag else f"`{backend_tag}`"
        # v5 — a cell whose AUTO_ROUTER had nowhere to route is flagged
        # in the verdict column. Pre-v5 cells have no such key and are
        # left unmarked (unknown, not asserted either way).
        router_ev = (c.get("layer_evidence") or {}).get("auto_router") or {}
        verdict_cell = f"**{verdict}**"
        if router_ev.get("in_evidence") is False:
            verdict_cell += " ⚠ router not in evidence"
            _router_gap_cells.append((c, router_ev))
        rows.append(
            f"| {c['row']} ({c['row_label']}) | {c['tier']} | "
            f"{tier_label} | {_fmt_delta(deltas['path_coverage'], '+.3f')} | "
            f"{_fmt_delta(deltas['graded_answer'], '+.3f')} | "
            f"{_fmt_delta(deltas['abstention_f1'], '+.3f')} | "
            f"{_fmt_delta(deltas['token_cost'], '+.0f')} | "
            f"{_fmt_delta(deltas['latency_cost'], '+.2f')} | "
            f"{verdict_cell} |"
        )

    if _fixture_gap_cells:
        gap_rows = sorted({f"{c['row']}/{c['tier']}" for c, _g in _fixture_gap_cells})
        rows += [
            "",
            "## 🔴 fixture mismatch — these cells are not comparable",
            "",
            f"**{len(gap_rows)} cell(s)** were measured on a different",
            "step7 fixture version than the baseline:",
            "",
            "    " + ", ".join(gap_rows),
            "",
            f"    {_fixture_gap_cells[0][1]}",
            "",
            "A Δ is a reading of the *layer* only when both sides answered",
            "the same questions. step7 moved v5 → v7 by **adding** queries",
            "(q13 meta inventory, then q14/q15/q16 narrow-scope), so a v7",
            "cell minus a v5 baseline is partly a reading of the fixture",
            "change. Their verdict column says `not comparable` rather than",
            "a Pareto verdict — the Δ numbers are left visible because they",
            "are real arithmetic, but they do not answer the question the",
            "matrix is asking.",
            "",
            "`fixture_version` was written into every cell from the start",
            "and never read until now. Re-capturing the baseline",
            "(`python scripts/qvt_capture_baseline.py`) pins it to the",
            "current fixture and makes these cells comparable again — or",
            "re-run the affected cells if the baseline is intentionally held.",
        ]

    if _missing_axis_cells:
        rows += [
            "",
            "## ⚠ axes not comparable against this baseline",
            "",
            "    " + ", ".join(sorted(_missing_axis_cells)),
            "",
            f"Baseline schema: `{baseline.get('schema', 'unknown')}` "
            f"(captured {baseline.get('captured_at', 'unknown')}).",
            "",
            "These axes are rendered **n/a** and the verdict abstains on",
            "them. They are *not* reported as Δ 0.000 — that was the old",
            "behaviour, and it silently turned \"never compared\" into",
            "\"flat\": a cell that doubled token cost classified as",
            "**adopt**, because the 3-axis `qvt-baseline-v1` carries no",
            "`token_cost` / `latency_cost` and the cost loop scored",
            "neither improvement nor regression.",
            "",
            "To restore the cost half of the Pareto verdict, re-capture",
            "the baseline (`python scripts/qvt_capture_baseline.py`,",
            "~70 min) — it writes `qvt-baseline-v2`, which carries all",
            "five axes plus per-question-type. CLAUDE.md rule #2's α-5",
            "Pareto rule is written to apply \"once the 5-axis baseline is",
            "the canonical reference\"; until then these cells are",
            "quality-only readings.",
        ]

    if _router_gap_cells:
        gap_rows = sorted({
            f"{c['row']}/{c['tier']}" for c, _ev in _router_gap_cells
        })
        _, _first_ev = _router_gap_cells[0]
        rows += [
            "",
            "## ⚠ AUTO_ROUTER not in evidence",
            "",
            f"**{len(gap_rows)} cell(s)** ran with `JAMES_AUTO_ROUTER=1` while",
            "the backend registry had fewer than two populated tiers:",
            "",
            "    " + ", ".join(gap_rows),
            "",
            f"Registry at capture: {_first_ev.get('reason')}",
            "",
            "Read these cells as **\"the layer was never exercised\"**, not",
            "\"the layer does nothing\". `core/reasoning/router.py`",
            "(`_legacy_backend_id`) documents the small-tier-only fleet case:",
            "every escalation resolves to the same backend, so the router",
            "emits audit rows and changes no answer. A Δ here measures the",
            "*other* layers in the row.",
            "",
            "CLAUDE.md rule #2 calls this **\"not in evidence,\" not \"no",
            "effect\"** — and α-5's post-closure self-audit",
            "(`feedback_oracle_phrase_artifacts`) is the precedent: AUTO_ROUTER",
            "was scored as a null in a single-backend environment once already.",
            "",
            "To put it in evidence, register a second tier before the run",
            "(e.g. `JAMES_ENABLE_CLAUDE_BACKEND=1` for the cloud tier) and",
            "re-run the affected rows.",
        ]

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
                deltas_qt, _unavail_qt = _deltas_vs_baseline(med, base_med_qt)
                _missing_axis_cells.update(_unavail_qt)
                _fx_qt = _fixture_mismatch(c, baseline)
                if _fx_qt:
                    verdict_qt = f"not comparable ({_fx_qt})"
                else:
                    verdict_qt = _classify_five_axis_delta(
                        deltas_qt, base_noise_qt, _unavail_qt)
                rows.append(
                    f"| {c['row']} | {c['tier']} | `{c['model']}` | "
                    f"{_fmt_delta(deltas_qt['path_coverage'], '+.3f')} | "
                    f"{_fmt_delta(deltas_qt['graded_answer'], '+.3f')} | "
                    f"{_fmt_delta(deltas_qt['abstention_f1'], '+.3f')} | "
                    f"{_fmt_delta(deltas_qt['token_cost'], '+.0f')} | "
                    f"{_fmt_delta(deltas_qt['latency_cost'], '+.2f')} | "
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
            deltas_sc, _unavail_sc = _deltas_vs_baseline(med, base_med)
            _missing_axis_cells.update(_unavail_sc)
            _fx_sc = _fixture_mismatch(c, baseline)
            if _fx_sc:
                verdict_sc = f"not comparable ({_fx_sc})"
            else:
                verdict_sc = _classify_five_axis_delta(
                    deltas_sc, base_noise, _unavail_sc)
            sc_id = c.get("sector_cell") or c.get("row")
            sc_label = c.get("sector_cell_label") or ""
            rows.append(
                f"| {sc_id} ({sc_label}) | {c['tier']} | "
                f"`{c['model']}` | {_fmt_delta(deltas_sc['path_coverage'], '+.3f')} | "
                f"{_fmt_delta(deltas_sc['graded_answer'], '+.3f')} | "
                f"{_fmt_delta(deltas_sc['abstention_f1'], '+.3f')} | "
                f"{_fmt_delta(deltas_sc['token_cost'], '+.0f')} | "
                f"{_fmt_delta(deltas_sc['latency_cost'], '+.2f')} | "
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
        help="Comma-separated subset of M_XS/M_S/M_M/M_L/M_XL/M_CLOUD "
             "(default: all 5 local; M_CLOUD opt-in via explicit list "
             "and requires JAMES_ENABLE_CLAUDE_BACKEND=1).",
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
    # α-8 cloud tier (2026-06-04) — tier opt-in discipline:
    #   • --tiers explicit (any subset, including M_CLOUD) → as listed
    #   • --tiers omitted                                  → default to
    #     LOCAL tiers only (M_CLOUD requires explicit opt-in to avoid
    #     a stray "run everything" command burning the operator's Max-
    #     plan quota).
    if args.tiers:
        tiers = _parse_subset(args.tiers, list(_TIER_MODELS.keys()), "tiers")
    else:
        # Default = 5 gemma scale ladder. M_MIXTRAL / M_CLOUD opt-in only.
        tiers = list(_DEFAULT_TIERS)
    sha = _current_git_sha() or "unknown"
    fixture_path = _resolve_fixture(args.suite)
    out_dir = _resolve_output_dir()

    # α-8 cloud tier (2026-06-04) — pre-flight cost guard. When any
    # tier in this run routes to a non-Ollama backend (cloud), estimate
    # the cloud API call count and refuse to start if it exceeds the
    # operator's declared budget. Per design memo §4.
    cloud_tiers = [t for t in tiers if t in _TIER_BACKEND_OVERRIDE]
    if cloud_tiers:
        try:
            fixture_data = json.loads(fixture_path.read_text(encoding="utf-8"))
            queries_count = len(
                fixture_data.get("queries", fixture_data)
                if isinstance(fixture_data, dict) else fixture_data
            )
        except Exception as e:
            print(f"[error] cloud tier cost guard: cannot read fixture "
                  f"{fixture_path} ({type(e).__name__}: {e})")
            return 8
        # cells × runs × queries — each query is one cloud call on the
        # synth stage (no judge; oracle is deterministic).
        n_cloud_cells = (len(sector_cells) if sector_cells else len(rows)) * len(cloud_tiers)
        estimated_calls = n_cloud_cells * args.n_runs * queries_count
        # Operator budget — env override; default is conservative
        # (Max-plan daily quota safe zone per
        # `memory/feedback_direction_alpha_max_plan_research_cloud`).
        budget_env = os.environ.get("JAMES_CLOUD_CALL_BUDGET", "").strip()
        try:
            budget = int(budget_env) if budget_env else 200
        except ValueError:
            print(f"[error] JAMES_CLOUD_CALL_BUDGET={budget_env!r} is not an integer")
            return 8
        print(f"[cloud-cost] cloud tiers in run: {cloud_tiers}")
        print(f"[cloud-cost] estimated cloud API calls: "
              f"{n_cloud_cells} cells × {args.n_runs} runs × "
              f"{queries_count} queries = {estimated_calls}")
        print(f"[cloud-cost] budget (JAMES_CLOUD_CALL_BUDGET): {budget}")
        if estimated_calls > budget:
            print(f"[error] estimated {estimated_calls} cloud calls "
                  f"> budget {budget}. Raise JAMES_CLOUD_CALL_BUDGET or "
                  f"trim scope (--tiers / --rows / --sector-cells / "
                  f"--n-runs / smaller --suite).")
            return 8

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
    # Display tier → routing target. For local tiers this is the
    # Ollama model tag; for cloud tiers (M_CLOUD) it's the backend id
    # (model is empty since the cloud backend picks its own model).
    tier_display = [
        f"{t}={_TIER_MODELS[t] or _tier_backend_id(t)}" for t in tiers
    ]
    print(f"tiers:      {tier_display}")
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
            print("\n=== T0 smoke verdict (5-axis) ===")
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

    print("\nRender the consolidated report with:\n"
          "  python scripts/qvt_ablation_matrix.py --render-report")
    return 0 if n_fail == 0 else 6


if __name__ == "__main__":
    raise SystemExit(main())
