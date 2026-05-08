"""Bench eval gate for self-evolution patch deploys (#68 phase 2-A).

After `patch_apply()` succeeds inside `/admin/patch/approve`, this
module re-runs the STEP 7 regression suite against the live server
via `scripts/bench.py --check`. On any regression beyond the
configured tolerance, the gate triggers an auto-rollback via
`patch_applier.restore_latest()` and records the outcome in the
patch lifecycle log.

Why a subprocess rather than calling the runner in-process
- bench.py imports `requests` and POSTs against the live server
  (the same uvicorn process that's handling the approve request).
  Doing this in-process would require an HTTP-self-call from inside
  an async handler — fragile and easy to deadlock. A subprocess is
  simpler and matches the operator-CLI invocation pattern.
- Running the subprocess in `asyncio.to_thread` lets the event loop
  keep serving the bench's incoming /query/ requests while the
  approve handler is blocked waiting for the gate result.

What goes in the audit log
- `before_metrics`: latest pre-deploy bench report (most recent
  reports/bench_*_step7_*.json that existed before this approve).
- `after_metrics`: bench report produced by THIS gate run.
- `outcome`: "deployed" if gate passes, "rolled_back" otherwise.
  `record_outcome.detail` carries the bench failure summary.

Operator overrides
- `JAMES_EVOLUTION_GATE=0` skips the bench check entirely. The
  approve still records before_metrics if available; after_metrics
  becomes `{"gate": "skipped"}`. Audit-trail intact, gate disabled.
  Default ON.
- `JAMES_EVOLUTION_GATE_TIMEOUT_S` (default 600) — bench subprocess
  wall-clock cap. Beyond this the gate fails (treated as regression)
  and rollback fires.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent.parent
REPORTS_DIR = ROOT / "reports"


@dataclass(frozen=True)
class GateResult:
    """Outcome of one bench-gate run.

    `passed`: True if bench --check exited 0 OR the gate was skipped.
    `outcome_label`: feeds `record_outcome(outcome=...)` directly —
        "deployed" / "rolled_back" / "deployed_gate_skipped".
    `detail`: short human-readable summary for the audit log.
    `before_metrics` / `after_metrics`: pre-deploy and post-deploy
        bench summaries (the dicts stored on the lifecycle entry).
    """
    passed:         bool
    outcome_label:  str
    detail:         str
    before_metrics: dict
    after_metrics:  dict


def _gate_enabled() -> bool:
    """Default ON. Set JAMES_EVOLUTION_GATE=0 (or false / no) to skip."""
    val = os.getenv("JAMES_EVOLUTION_GATE", "1").strip().lower()
    return val not in ("0", "false", "no", "")


def _gate_timeout_s() -> int:
    raw = os.getenv("JAMES_EVOLUTION_GATE_TIMEOUT_S", "600").strip()
    try:
        n = int(raw)
        return max(30, min(n, 3600))
    except Exception:
        return 600


def _latest_bench_report(suite: str = "step7") -> Optional[Path]:
    """Most recent reports/bench_*_<suite>_*.json (mtime sort).

    Used as `before_metrics` source — the snapshot of system state
    at the time of the approve request, before this patch is applied.
    None if no prior bench has been run. The audit entry then carries
    `before_metrics={}` — still useful, just no comparison baseline.
    """
    if not REPORTS_DIR.exists():
        return None
    candidates = sorted(
        REPORTS_DIR.glob(f"bench_*_{suite}_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _summarize_report(path: Optional[Path]) -> dict:
    """Compact a bench JSON report into the small dict that goes into
    the audit log. Keep it tight — the lifecycle JSONL must remain
    human-scannable; full bench reports stay on disk under reports/.

    Shape:
      {"git_sha": ..., "total_seconds": ..., "queries": N,
       "ok": M, "blocked": K, "report_file": "bench_<sha>_<...>.json"}
    """
    if path is None or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"report_file": path.name, "parse_error": True}
    results = data.get("results") or []
    return {
        "report_file":   path.name,
        "git_sha":       data.get("git_sha", ""),
        "total_seconds": data.get("total_seconds", 0),
        "queries":       data.get("queries", len(results)),
        "ok":            sum(1 for r in results if r.get("status") == "ok" and not r.get("blocked")),
        "blocked":       sum(1 for r in results if r.get("blocked")),
        "errors":        sum(1 for r in results if r.get("status") not in ("ok",)),
    }


def _run_bench_check_blocking(suite: str, timeout_s: int) -> tuple[bool, str]:
    """Synchronous bench subprocess. Returns (passed, stderr_tail).

    Caller wraps in `asyncio.to_thread` so the event loop can serve
    the bench's incoming /query/ requests while we wait.
    """
    cmd = [sys.executable, "scripts/bench.py", f"--suite={suite}", "--check"]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            # encoding/errors required on Windows: bench.py prints
            # Korean query strings; without explicit utf-8 the parent
            # decodes via locale.getpreferredencoding() which is cp949
            # on Korean Windows installs, mojibaking the captured tail
            # that lands in record_outcome.detail.
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return False, f"bench timeout after {timeout_s}s"
    except FileNotFoundError as e:
        return False, f"bench launch failed: {e}"
    passed = (proc.returncode == 0)
    tail = (proc.stdout or "")[-400:] + (proc.stderr or "")[-400:]
    return passed, tail.strip()


async def run_bench_gate(
    patch_id: str,
    target:   str,
    suite:    str = "step7",
) -> GateResult:
    """Run the eval gate after a successful patch_apply().

    Caller responsibility:
      - Call AFTER `patch_apply` succeeded (not before).
      - On `result.passed=False`, the patch file is already rolled
        back via `restore_latest(target)` inside this function.
      - Pass the returned `before_metrics` / `after_metrics` to
        `record_outcome()`.
    """
    before = _summarize_report(_latest_bench_report(suite))

    if not _gate_enabled():
        return GateResult(
            passed=True,
            outcome_label="deployed_gate_skipped",
            detail="JAMES_EVOLUTION_GATE=0 — eval gate skipped",
            before_metrics=before,
            after_metrics={"gate": "skipped"},
        )

    passed, tail = await asyncio.to_thread(
        _run_bench_check_blocking, suite, _gate_timeout_s()
    )

    # The bench run produces a NEW report file regardless of pass/fail.
    # Pick that up as after_metrics.
    after = _summarize_report(_latest_bench_report(suite))

    if passed:
        return GateResult(
            passed=True,
            outcome_label="deployed",
            detail=f"bench gate passed; {after.get('queries', '?')} queries",
            before_metrics=before,
            after_metrics=after,
        )

    # Regression — auto-rollback. Lazy import to avoid pulling
    # patch_applier into smoke-test paths that don't need it.
    rb_msg = ""
    try:
        from tools.patch.patch_applier import restore_latest
        rb_ok, rb_msg = restore_latest(target)
    except Exception as e:
        rb_ok = False
        rb_msg = f"rollback raised: {e}"

    detail = (
        f"bench regression — rollback={'ok' if rb_ok else 'FAIL'}; "
        f"{rb_msg}; bench tail: {tail[-200:]}"
    )
    return GateResult(
        passed=False,
        outcome_label="rolled_back",
        detail=detail[:300],
        before_metrics=before,
        after_metrics=after,
    )
