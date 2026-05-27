"""LEO L.D — operator-runnable scope-routing bench wrapper.

Runs ``scripts/bench.py --suite=step7`` twice against a live JAMES
server (once with ``JAMES_SCOPE_ROUTING=0``, once with ``=1``), queries
``audit_log`` for ``reason:route`` rows emitted during the flag-ON
window, and aggregates per-query delta + scope distribution into
``reports/research-runs/lc-scope-bench-<timestamp>.json``.

Operator workflow::

    # Stop any pre-existing JAMES server on 127.0.0.1:8000 (the
    # wrapper spawns + tears down its own server per arm so the env
    # flags actually reach the routing call sites).
    python scripts/bench_lc_scope_arms.py

## Server lifecycle — wrapper spawns + tears down per arm

``JAMES_SCOPE_ROUTING`` and ``JAMES_AUTO_ROUTER`` are both read by
the server's routing code (``core.reasoning.evidence_scope``,
``core.reasoning.router``), not by bench.py. Setting them on the
bench.py subprocess does nothing: bench.py is an HTTP client. The
2026-05-26 live verify run of the original wrapper exposed this —
both arms ran against the operator's pre-launched server (whose env
was frozen at boot) so the comparison measured pure LLM-sampling
noise, with ``scope_summary={}, backend_counts={}`` and no
``evidence_scope=…`` tokens anywhere in audit_log.

This version spawns ``python -m uvicorn server_llmwiki:app`` with
the correct per-arm env at the start of each arm and shuts it down
after bench.py exits. ``--reload`` is disabled (uvicorn's reload
watcher spawns a child that survives parent termination on Windows
and leaves the port stuck across arms). Override the bind via
``JAMES_BASE_URL`` (default ``http://127.0.0.1:8000``); if the port
is already in use the wrapper refuses to proceed rather than
silently routing against a stale server.

## D5 dependency — both arms run with ``JAMES_AUTO_ROUTER=1`` forced

LEO L.C scope routing only fires inside the D5 router policy tree.
With ``JAMES_AUTO_ROUTER=0`` (D5 off) the router shortcircuits to
legacy at ``Router(enabled=False)`` without consulting
``evidence_scope`` — both arms would degrade to "legacy everywhere"
and audit_log would capture zero scope decisions even with the
server-spawn fix above.

## Mode dependency — ``--mode=retrieval`` forced on bench.py

step7 RAG-style queries (id 1-10) get classified as ``chat`` by the
production IntentClassifier (verified across 40+ historical step7
runs — distribution always ``{'chat': 10, '': 2, 'meta': 1}``).
``chat`` mode bypasses ``run_retrieval_pipeline`` entirely, so the
L.C ``compute_scope`` + ``scope_context(...)`` binding never fires
and audit captures only ``reason=fallback`` rows with no
``evidence_scope`` payload.

This wrapper passes ``--mode=retrieval`` to ``bench.py``, which
populates the ``mode_override`` field on ``/query/`` (already wired
since item #6 / chat-page mode picker). ``ROLE_ALLOWED["external"]``
includes ``"retrieval"`` so the API-key role used by bench passes
the role-allowed gate. Result: step7 queries flow through the
retrieval pipeline → L.C scope binds → audit rows carry
``evidence_scope=X.XXXX effective_k=… …`` payload → wrapper's
``scope_summary`` aggregate is non-empty.

See ``feedback_bench_step7_chat_mode_passthrough`` in memory for
the full structural analysis.

This version forces ``JAMES_AUTO_ROUTER=1`` on BOTH the OFF and ON
arms, so the comparison is:

  - **OFF arm**: D5 budget routing (CAP_SUBSTITUTION / CAP_HEAVY /
                 verify-stage), **without** scope override
  - **ON arm**:  D5 budget routing **plus** scope override
                 (narrow ≤ 0.30 → small / wide ≥ 0.70 → large /
                 mid-band falls through to budget rule)

This isolates the scope-override signal — the delta now actually
measures what scope routing adds on top of D5, instead of measuring
"router on vs router off".

The 4 STEP-7 arms from the LEO L.0 design memo
(``docs/handovers/v0.4-leo-evidence-scope-routing-track.md``
§"STEP 7 bench plan") are observed indirectly via the scope
distribution captured in the audit_log payload:

  - Flag-OFF arm  — D5 budget baseline (no scope override)
  - Flag-ON narrow (scope ≤ 0.30) — small-tier backend routing
  - Flag-ON wide   (scope ≥ 0.70) — large-tier backend routing
  - Flag-ON halt-prone — Gemma 4 ``done_reason=length`` cases. This
                          script does not query Ollama's native field
                          directly; check the per-stage trace_synth_call
                          rows in audit_log for ``length`` markers.

Acceptance criteria for L.D closure (informational; this script
reports but does not enforce them — that's the result doc's job):

  - Flag-OFF arm latency / graph_paths within bench.py baseline
    tolerance bands (post-#519 — the D5-on baseline, NOT the
    pre-LEO byte-identical baseline)
  - Flag-ON narrow arm: latency delta ≤ baseline (small backend wins)
  - Flag-ON wide arm: latency delta within +30% (large backend
    acceptable for synthesis burden)
  - No grounded=true rate regression on any arm vs D1 v2 closure
    (manual check against the per-query answer_len + downstream
    grounded markers; not part of bench.py's automated check yet)

``JAMES_ADAPTIVE_BUDGET`` (D1) is intentionally **inherited** from
the operator's environment rather than forced — D1 is an independent
axis (per-stage cap selection vs per-query backend selection). To
measure scope routing in isolation with D1 on, the operator sets
``JAMES_ADAPTIVE_BUDGET=1`` before invoking this script; the wrapper
preserves it across both arms. Same for any other env not enumerated
above.

Cross-stack note: when Robin (V3'.e schema-adopted) or Ali (Track 3
swap_eval) work runs this stack, BOTH arms MUST stay with all
opt-in flags OFF for apples-to-apples purity — see
``feedback_cross_stack_run_flag_off`` in memory. **Do not use this
wrapper for cross-stack runs** — it forces ``JAMES_AUTO_ROUTER=1``
which violates that purity contract.
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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from utils.console import ensure_utf8_console
    ensure_utf8_console()
except Exception:
    pass


REPORTS_DIR = ROOT / "reports" / "research-runs"
# audit_log SQLite path — matches ``core.audit_bridge._DEFAULT_AUDIT_DB``
# (BASE_DIR / "james_audit.db"). Override via JAMES_AUDIT_DB env if your
# deployment writes to a different location.
AUDIT_DB = Path(
    os.environ.get("JAMES_AUDIT_DB", str(ROOT / "james_audit.db"))
)
SERVER_BASE_URL = os.environ.get("JAMES_BASE_URL", "http://127.0.0.1:8000")
SERVER_HEALTHZ = SERVER_BASE_URL.rstrip("/") + "/healthz"
SERVER_BOOT_TIMEOUT_SEC = int(os.environ.get("JAMES_SERVER_BOOT_TIMEOUT", "120"))


def _port_in_use(host: str, port: int) -> bool:
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    try:
        return sock.connect_ex((host, port)) == 0
    finally:
        sock.close()


def _parse_host_port(base_url: str) -> tuple:
    from urllib.parse import urlparse
    u = urlparse(base_url)
    return (u.hostname or "127.0.0.1", int(u.port or 8000))


def _wait_for_healthz(timeout_sec: int) -> bool:
    """Poll SERVER_HEALTHZ until 200 OK or timeout."""
    import urllib.request
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
    """Spawn uvicorn server with the given env. Returns Popen or None.

    Uses ``python -m uvicorn`` directly (not ``python server_llmwiki.py``)
    so we can disable ``--reload`` — reload spawns a watcher child that
    survives parent termination on Windows and leaves port 8000 stuck.
    """
    host, port = _parse_host_port(SERVER_BASE_URL)
    if _port_in_use(host, port):
        print(
            f"[server] {host}:{port} already in use. Stop the existing "
            f"server (or set JAMES_BASE_URL to a free port) before "
            f"running this wrapper — env flags applied here would not "
            f"reach the operator-launched server."
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
    print(f"[server] healthy after {SERVER_BOOT_TIMEOUT_SEC}s budget")
    return proc


def _shutdown_server(proc: subprocess.Popen) -> None:
    """Stop the spawned server gracefully, escalating to kill if needed."""
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
    # Give the OS a moment to release the port before the next arm spawns.
    time.sleep(2.0)


def _mint_employee_jwt() -> Optional[str]:
    """Mint a short-lived employee-role JWT for the bench subprocess.

    Retrieval mode requires the ``query.internal_rag`` feature, which
    the default policy grants to ``admin / manager / employee`` only.
    The bench's ``api_key`` alone resolves to ``external`` (per
    ``server_llmwiki.get_role_from_request``'s default-deny fallback),
    so without this elevation ``mode_override="retrieval"`` is silently
    routed back to ``handle_chat`` by the engine's internal_rag gate
    and L.C ``scope_context`` never binds.

    Returns the JWT string, or None if minting fails (caller falls
    back to api_key-only auth and surfaces the chat-mode passthrough
    issue in audit_log — same as pre-fix behavior).
    """
    try:
        from core.auth import create_token
        return create_token("bench-runner", "employee")
    except Exception as e:
        print(f"[server] JWT mint failed ({type(e).__name__}: {e}) — "
              f"falling back to api_key-only auth (mode_override may "
              f"silently fall through to handle_chat)")
        return None


def _run_arm(arm_name: str, scope_routing: str) -> Optional[Path]:
    """Run one bench arm with the given JAMES_SCOPE_ROUTING value.

    Server lifecycle: spawns its own uvicorn with the per-arm env so
    ``JAMES_SCOPE_ROUTING`` / ``JAMES_AUTO_ROUTER`` actually reach the
    routing call sites. Without this, both flags would be set only on
    the bench.py subprocess (an HTTP client that doesn't read them) —
    the operator-launched server would keep its boot-time env on both
    arms, and the bench would measure pure sampling noise.

    Returns the path to bench.py's output JSON file, or None on
    failure. bench.py writes to ``reports/bench_<sha>_step7_<stamp>.json``;
    we find the most recently created matching file and assume it
    belongs to this run.

    Forces ``JAMES_AUTO_ROUTER=1`` on this arm — see module docstring
    for the D5 dependency rationale. The OFF arm is "D5 budget
    routing without scope override"; the ON arm is "D5 budget routing
    + scope override". Without ``JAMES_AUTO_ROUTER=1`` the router
    shortcircuits to legacy and audit_log captures zero scope
    decisions.
    """
    server_env = os.environ.copy()
    server_env["JAMES_SCOPE_ROUTING"] = scope_routing
    server_env["JAMES_AUTO_ROUTER"] = "1"

    print(
        f"\n=== ARM: {arm_name} "
        f"(JAMES_SCOPE_ROUTING={scope_routing}, "
        f"JAMES_AUTO_ROUTER=1) ==="
    )
    server = _spawn_server(server_env)
    if server is None:
        print(f"[{arm_name}] server boot failed — aborting arm")
        return None
    try:
        pre_existing = set((ROOT / "reports").glob("bench_*_step7_*.json"))
        t0 = time.time()
        try:
            # --mode=retrieval forces step7 RAG queries into
            # run_retrieval_pipeline so the L.C scope_context binding
            # actually fires — without this, IntentClassifier routes
            # all 10 RAG queries to chat mode and scope_compute never
            # runs (see `feedback_bench_step7_chat_mode_passthrough`).
            # JWT bearer elevates the request to employee role so the
            # engine's `query.internal_rag` gate doesn't kick the
            # retrieval-mode request back to handle_chat.
            bench_env = {**os.environ, "JAMES_BASE_URL": SERVER_BASE_URL}
            bearer = _mint_employee_jwt()
            if bearer:
                bench_env["JAMES_BENCH_BEARER"] = bearer
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "bench.py"),
                 "--suite=step7", "--mode=retrieval"],
                env=bench_env,
                cwd=str(ROOT),
                capture_output=False,
                check=False,
                timeout=1200,
            )
        except subprocess.TimeoutExpired:
            print(f"[{arm_name}] TIMEOUT after 20 min — aborting arm")
            return None
        elapsed = time.time() - t0
        print(
            f"[{arm_name}] bench.py finished in {elapsed:.1f}s "
            f"(exit code {result.returncode})"
        )
    finally:
        _shutdown_server(server)

    after = set((ROOT / "reports").glob("bench_*_step7_*.json"))
    new = sorted(after - pre_existing)
    if not new:
        print(f"[{arm_name}] no new bench output found under reports/")
        return None
    return new[-1]


def _load_run(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _query_audit_log_scope_rows(after_iso: str) -> List[Dict]:
    """Query audit_log for reason:route rows since ``after_iso``.

    Returns parsed payload dicts (one per emitted route decision).
    Empty list if audit_log not present — operator may have a custom
    deployment; this is best-effort observability, not core path.

    Row shape: ``core.audit_bridge.mirror_to_audit_db`` packs every
    non-reserved key (incl. ``query`` and ``answer`` from the
    ``emit_route_event`` dict) into a JSON blob stored in the
    ``audit_log.answer`` column. The DB ``query`` column ends up empty
    for these rows because ``_resolve_query`` only knows about
    tool-style fields (tool_used / target_file / path). So we read the
    JSON blob, lift the nested ``query`` → ``stage`` and tokenize the
    nested ``answer`` (the ``backend=… tier=… reason=… [evidence_scope=…
    effective_k=… …]`` k=v string emitted by ``emit_route_event``).
    """
    if not AUDIT_DB.exists():
        print(f"[audit] {AUDIT_DB} not found — skipping scope row capture")
        return []
    try:
        import sqlite3
        conn = sqlite3.connect(str(AUDIT_DB))
        cur = conn.cursor()
        cur.execute(
            "SELECT timestamp, answer FROM audit_log "
            "WHERE endpoint = 'reason:route' AND timestamp >= ? "
            "ORDER BY timestamp",
            (after_iso,),
        )
        rows: List[Dict] = []
        for ts, blob in cur.fetchall():
            row: Dict = {"timestamp": ts, "raw": blob}
            stage = ""
            tok_str = ""
            try:
                payload = json.loads(blob) if blob else {}
                if isinstance(payload, dict):
                    stage = str(payload.get("query") or "")
                    tok_str = str(payload.get("answer") or "")
            except (ValueError, TypeError):
                # Fallback for non-JSON legacy rows: treat the blob as the
                # k=v token string directly.
                tok_str = blob or ""
            row["stage"] = stage
            for tok in tok_str.split():
                if "=" in tok:
                    k, v = tok.split("=", 1)
                    row[k] = v
            rows.append(row)
        conn.close()
        return rows
    except Exception as e:
        print(f"[audit] query failed: {e}")
        return []


def _aggregate(
    off_run: Dict, on_run: Dict, scope_rows: List[Dict],
) -> Dict:
    """Per-query delta + scope distribution summary."""
    off_by_id = {r["id"]: r for r in off_run.get("results", [])}
    on_by_id = {r["id"]: r for r in on_run.get("results", [])}

    deltas: List[Dict] = []
    for qid in sorted(set(off_by_id) | set(on_by_id)):
        off_r = off_by_id.get(qid, {})
        on_r = on_by_id.get(qid, {})
        delta_pct: Optional[float] = None
        if off_r.get("elapsed") and on_r.get("elapsed"):
            delta_pct = round(
                (on_r["elapsed"] - off_r["elapsed"]) / off_r["elapsed"] * 100, 1
            )
        deltas.append({
            "id": qid,
            "text": (off_r.get("text") or on_r.get("text") or "")[:60],
            "category": off_r.get("category") or on_r.get("category"),
            "off_elapsed": off_r.get("elapsed"),
            "on_elapsed": on_r.get("elapsed"),
            "elapsed_delta_pct": delta_pct,
            "off_graph_paths": off_r.get("graph_paths_count"),
            "on_graph_paths": on_r.get("graph_paths_count"),
            "off_answer_len": off_r.get("answer_len"),
            "on_answer_len": on_r.get("answer_len"),
        })

    # Scope distribution from audit_log (flag-ON window only)
    scope_values: List[float] = []
    for row in scope_rows:
        try:
            scope_values.append(float(row.get("evidence_scope", "")))
        except (ValueError, TypeError):
            pass

    scope_summary: Dict = {}
    if scope_values:
        scope_summary = {
            "count": len(scope_values),
            "mean": round(sum(scope_values) / len(scope_values), 4),
            "min": round(min(scope_values), 4),
            "max": round(max(scope_values), 4),
            "narrow_count": sum(1 for v in scope_values if v <= 0.30),
            "mid_count": sum(1 for v in scope_values if 0.30 < v < 0.70),
            "wide_count": sum(1 for v in scope_values if v >= 0.70),
        }

    backend_counts: Dict[str, int] = {}
    for row in scope_rows:
        b = row.get("backend", "")
        if b:
            backend_counts[b] = backend_counts.get(b, 0) + 1

    return {
        "deltas": deltas,
        "scope_summary": scope_summary,
        "backend_counts": backend_counts,
        "scope_rows": scope_rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="LEO L.D scope-routing 3-arm bench wrapper.",
    )
    ap.add_argument(
        "--skip-off", action="store_true",
        help=(
            "Skip the flag-OFF baseline arm. Requires --off-path to "
            "supply a prior bench.py output for the OFF comparison."
        ),
    )
    ap.add_argument(
        "--off-path", type=Path, default=None,
        help="Reuse a prior bench.py output JSON for the flag-OFF arm.",
    )
    args = ap.parse_args()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # Pre-flight audit_log path warning. The wrapper still proceeds —
    # the bench runs regardless — but it tells the operator up front
    # that the scope_summary block in the output will be empty.
    if not AUDIT_DB.exists():
        print(
            f"[bench_lc] WARNING: audit_log not found at {AUDIT_DB} — "
            f"scope_summary + backend_counts in the output will be "
            f"empty. Set the JAMES_AUDIT_DB env var to override the "
            f"path if your deployment writes to a different location."
        )

    # Arm 1: flag OFF (baseline)
    if args.off_path:
        off_path = args.off_path
        if not off_path.exists():
            print(f"[bench_lc] --off-path {off_path} does not exist")
            return 1
        print(f"=== Re-using flag-OFF result: {off_path}")
    elif args.skip_off:
        print("[bench_lc] --skip-off requires --off-path")
        return 1
    else:
        off_path = _run_arm("flag-OFF baseline", "0")
        if not off_path:
            print("[bench_lc] flag-OFF arm failed — aborting")
            return 1
    off_run = _load_run(off_path)

    # Capture timestamp boundary for audit_log query on flag-ON window
    on_started_iso = datetime.now().isoformat()

    # Arm 2: flag ON
    on_path = _run_arm("flag-ON scope routing", "1")
    if not on_path:
        print("[bench_lc] flag-ON arm failed — aborting")
        return 1
    on_run = _load_run(on_path)

    # Query audit_log for scope rows from the flag-ON window
    scope_rows = _query_audit_log_scope_rows(on_started_iso)
    print(
        f"\n[audit] captured {len(scope_rows)} reason:route rows "
        f"from flag-ON window"
    )

    agg = _aggregate(off_run, on_run, scope_rows)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = REPORTS_DIR / f"lc-scope-bench-{stamp}.json"
    out_path.write_text(
        json.dumps({
            "generated_at": datetime.now().isoformat(),
            "off_run_path": str(off_path.relative_to(ROOT)),
            "on_run_path": str(on_path.relative_to(ROOT)),
            "off_run_total_seconds": off_run.get("total_seconds"),
            "on_run_total_seconds": on_run.get("total_seconds"),
            "aggregate": agg,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n[bench_lc] saved: {out_path.relative_to(ROOT)}")

    # Brief operator-facing summary
    if agg["scope_summary"]:
        ss = agg["scope_summary"]
        print(
            f"\n=== Scope distribution (flag-ON, "
            f"{ss['count']} routing decisions) ==="
        )
        print(
            f"  mean={ss['mean']:.3f}  "
            f"min={ss['min']:.3f}  max={ss['max']:.3f}"
        )
        print(f"  narrow (≤0.30): {ss['narrow_count']}")
        print(f"  mid    (0.30 < scope < 0.70): {ss['mid_count']}")
        print(f"  wide   (≥0.70): {ss['wide_count']}")

    if agg["backend_counts"]:
        print("\n=== Backend selection counts (flag-ON) ===")
        for b, c in sorted(agg["backend_counts"].items()):
            print(f"  {b}: {c}")

    print("\n=== Per-query elapsed delta ===")
    for d in agg["deltas"]:
        if d["elapsed_delta_pct"] is not None:
            sign = "+" if d["elapsed_delta_pct"] >= 0 else ""
            print(
                f"  q{d['id']:2}: {d['off_elapsed']:>5.1f}s -> "
                f"{d['on_elapsed']:>5.1f}s  "
                f"({sign}{d['elapsed_delta_pct']:.1f}%)"
            )
        else:
            print(f"  q{d['id']:2}: incomplete result on one or both arms")

    print(
        "\n[bench_lc] L.D closure: paste aggregate into "
        "reports/promo-assets/v3prime-leo-evidence-scope-result.md"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
