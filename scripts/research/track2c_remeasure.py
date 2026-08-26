#!/usr/bin/env python3
"""Track 2c re-measurement under salted run identities — one command.

Ali Afana's fourth finding invalidated the run identity of the Track 2c
adversarial sweep: every case shared the server-default conversation key,
so case N was answered with the five before it in its prompt. The runner
is fixed (``scripts/adversarial_sweep.py`` now salts per case, per run),
but the numbers that were produced under the old key have not been
re-measured. This script does that end to end.

Why a script rather than the three-line runbook it replaces
-----------------------------------------------------------
The runbook said: wipe ``conversation_history``, re-run the sweep, diff.
**That order destroys the evidence.** Whether any published Track 2c
number was actually contaminated depends on whether the machine that
produced it had accumulated turns under the shared key — and the wipe is
exactly what erases the answer. This script captures that evidence
*before* it wipes, writes it to disk, and refuses to wipe unless asked.

Why paired, and not "re-run and diff the published table"
---------------------------------------------------------
That was the original plan and it does not work. The Track 2c table was
last written on 2026-06-23; 19 commits to ``core/`` and 73 in total have
landed since. Re-running today and diffing against it cannot isolate the
salt — any verdict that moves is confounded by two months of drift, and
a verdict that does not move proves nothing either.

So this runs **both arms on the same build**:

  A. every case shares one conversation key (the pre-fix behaviour,
     via ``--shared-session-key``)
  B. every case gets its own salted key (the fix)

Everything else is identical — same build, same fixture, same model,
same wiped history at the start of each arm. The A↔B difference is the
contamination effect, measured rather than assumed. The published table
is still printed for reference, flagged as drift-confounded.

Steps
-----
  0. preflight   — server, model backend, database, fixture all reachable
  1. evidence    — per-session turn counts, written out BEFORE any wipe
  2. arm A       — wipe, then sweep with one shared key
  3. arm B       — wipe, then sweep with salted keys
  4. compare     — A vs B (the measurement), plus both vs the old table
  5. emit        — the block to paste into the finding ④ letter

Usage
-----
    # look, change nothing (safe anywhere, needs a live server for 0)
    python scripts/research/track2c_remeasure.py --preflight-only

    # capture the contamination evidence, still change nothing
    python scripts/research/track2c_remeasure.py --evidence-only

    # the real run
    python scripts/research/track2c_remeasure.py --yes

Requires a live JAMES server plus a local model backend; neither is
available in a session container, which is why this is operator-run.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE = ROOT / "eval" / "adversarial" / "ar_ecommerce-v1.1-james.yaml"
BASELINE_TABLE = ROOT / "eval" / "adversarial" / "ar_ecommerce-cross-stack-comparison.md"
DEFAULT_OUT = ROOT / "reports" / "research-runs"
SERVER_BASE = os.environ.get("JAMES_SERVER_URL", "http://localhost:8000").rstrip("/")
OLLAMA_BASE = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")


def _rel(p: Path) -> str:
    """Repo-relative path when possible, absolute otherwise.

    ``Path.relative_to`` raises for anything outside the repo, and the
    only caller that matters runs at step 5 — after the history wipe and
    a full sweep. An operator pointing --out-dir at /tmp would have lost
    the run to a formatting call. Never raise here.
    """
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get(url: str, timeout: int = 5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read(2000).decode("utf-8", "replace")
    except Exception as e:                                    # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def _db_path() -> Path:
    """Resolve the memory DB the server actually uses."""
    sys.path.insert(0, str(ROOT))
    try:
        from core.memory.db import DB_PATH
        return Path(DB_PATH)
    except Exception:                                         # noqa: BLE001
        return ROOT / "memory" / "james_memory.db"


# ── 0. preflight ────────────────────────────────────────────────────

def preflight() -> tuple[bool, list[str]]:
    lines, ok = [], True

    status, body = _get(f"{SERVER_BASE}/healthz")
    if status == 200:
        lines.append(f"  [ok]   JAMES server   {SERVER_BASE}")
    else:
        ok = False
        lines.append(f"  [FAIL] JAMES server   {SERVER_BASE} → {body}")
        lines.append("         start it first; the sweep posts to /query/")

    status, _ = _get(f"{OLLAMA_BASE}/api/tags")
    if status == 200:
        lines.append(f"  [ok]   model backend  {OLLAMA_BASE}")
    else:
        ok = False
        lines.append(f"  [FAIL] model backend  {OLLAMA_BASE} unreachable")

    if os.environ.get("JAMES_API_KEY"):
        lines.append("  [ok]   JAMES_API_KEY set")
    else:
        ok = False
        lines.append("  [FAIL] JAMES_API_KEY not set — the sweep cannot authenticate")

    db = _db_path()
    if db.exists():
        lines.append(f"  [ok]   memory DB      {db}")
    else:
        ok = False
        lines.append(f"  [FAIL] memory DB      {db} not found")

    if FIXTURE.exists():
        lines.append(f"  [ok]   fixture        {FIXTURE.name}")
    else:
        ok = False
        lines.append(f"  [FAIL] fixture        {FIXTURE} not found")

    return ok, lines


# ── 1. evidence, captured BEFORE the wipe ───────────────────────────

def capture_evidence(db: Path) -> dict:
    """Per-session turn counts — the only thing that says whether any
    published number was actually answered with prior turns in context.

    Must run before the wipe. This is the step the original runbook got
    in the wrong order.
    """
    out: dict = {"captured_at": _now(), "db": str(db), "available": False}
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        rows = con.execute(
            "SELECT session_id, COUNT(*) AS turns FROM conversation_history "
            "GROUP BY session_id ORDER BY turns DESC"
        ).fetchall()
        total = con.execute(
            "SELECT COUNT(*) FROM conversation_history").fetchone()[0]
        con.close()
    except Exception as e:                                    # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"
        return out

    accumulated = [{"session_id": s, "turns": t} for s, t in rows if t > 2]
    out.update(
        available=True,
        total_turns=total,
        session_count=len(rows),
        sessions_over_two_turns=accumulated,
        default_key_turns=next((t for s, t in rows if s == "default"), 0),
        bench_keys=[{"session_id": s, "turns": t} for s, t in rows
                    if s.startswith(("bench_", "ragas_live_", "q15_audit_"))],
    )
    # The verdict this whole capture exists to produce.
    if not accumulated:
        out["verdict"] = ("no session exceeded two turns — nothing accumulated; "
                          "the exposure was latent and the fix is preventive")
    elif out["default_key_turns"] > 2:
        out["verdict"] = (
            f"the shared 'default' key holds {out['default_key_turns']} turns — "
            "the Track 2c sweep did accumulate there, and its published "
            "verdicts were produced with prior cases in context")
    else:
        out["verdict"] = (
            "sessions accumulated, but not under 'default'; see "
            "sessions_over_two_turns for which measurement paths were affected")
    return out


# ── 4. compare against the published table ──────────────────────────

def parse_baseline_table() -> dict:
    """{case_id: verdict} from the JAMES baseline column of §2."""
    if not BASELINE_TABLE.exists():
        return {}
    out = {}
    for line in BASELINE_TABLE.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip().strip("*").strip() for c in line.strip("|").split("|")]
        if len(cells) < 3 or cells[0].lower() in ("case", "---"):
            continue
        if re.fullmatch(r"[-: ]+", cells[0]):
            continue
        if cells[2] in ("resisted", "partial", "failed", "borderline"):
            out[cells[0]] = cells[2]
    return out


def _verdicts(results_json: Path) -> dict:
    payload = json.loads(results_json.read_text(encoding="utf-8"))
    return {r.get("case_id") or r.get("id"): r.get("verdict")
            for r in payload.get("results", [])}


def compare_arms(arm_a: Path, arm_b: Path) -> tuple[list[dict], dict]:
    """A (shared key) vs B (salted) on the same build — the measurement."""
    a, b = _verdicts(arm_a), _verdicts(arm_b)
    baseline = parse_baseline_table()
    rows, counts = [], {"same": 0, "moved": 0}
    for cid in sorted(set(a) | set(b)):
        va, vb = a.get(cid), b.get(cid)
        state = "same" if va == vb else "moved"
        counts[state] += 1
        rows.append({"case_id": cid, "shared": va, "salted": vb,
                     "state": state, "published": baseline.get(cid)})
    return rows, counts


# ── 5. the block for the finding ④ letter ───────────────────────────

def emit_block(evidence: dict, rows: list[dict], counts: dict,
               arm_a: Path, arm_b: Path) -> str:
    moved = [r for r in rows if r["state"] == "moved"]
    drifted = [r for r in rows
               if r["published"] and r["published"] != r["salted"]]
    L = [
        "─" * 70,
        "PASTE INTO docs/collab/ali-engineering-findings/finding-4-run-identity-salt.md",
        "replacing the WARNING block, and confirm the bold sentence above it.",
        "─" * 70,
        "",
        f"Re-run: {_now()}   paired, same build, history wiped before each arm",
        f"  arm A (shared key): {_rel(arm_a)}",
        f"  arm B (salted)    : {_rel(arm_b)}",
        "",
        "THE MEASUREMENT — A vs B, everything else held constant:",
        f"  {counts['moved']} of {counts['moved'] + counts['same']} cases "
        f"changed verdict when the shared key was removed.",
    ]
    if moved:
        L.append("")
        for r in moved:
            L.append(f"    {r['case_id']}: shared={r['shared']} → salted={r['salted']}")
        L += ["", "  That is the contamination effect, measured directly."]
    else:
        L += ["",
              "  No case changed. Say so plainly: on this fixture and this",
              "  build, the shared conversation key did not move a single",
              "  verdict. That is the result that reflects least well on the",
              "  finding's practical impact, which is exactly why it should be",
              "  stated first and without hedging. The defect was real; its",
              "  measured effect here was nil."]
    L += ["", "Accumulation evidence, captured before the first wipe:",
          f"  {evidence.get('verdict', 'not captured')}"]
    if evidence.get("bench_keys"):
        L.append(f"  other measurement keys carrying turns: "
                 f"{len(evidence['bench_keys'])}")
    L += ["",
          "For reference only — the published Track 2c table vs arm B:",
          f"  {len(drifted)} case{'s' if len(drifted) != 1 else ''} differ"
        f"{'s' if len(drifted) == 1 else ''}."]
    if drifted:
        for r in drifted[:6]:
            L.append(f"    {r['case_id']}: published={r['published']} → now={r['salted']}")
    L += ["  DO NOT read this as the salt effect. The table dates from",
          "  2026-06-23 and ~19 core/ commits have landed since, so these",
          "  differences are confounded by drift. The A-vs-B block above is",
          "  the only clean comparison here.",
          "",
          "REMINDER — do not group any of this by language family. The",
          "eighteen cases split 12 Korean / 6 English under our language",
          "classifier and the split does not follow the fixture labels; only",
          "per-case comparison is valid. See",
          "reports/research-runs/arabic-pipeline-capability-audit-20260822.md §7.",
          "─" * 70]
    return "\n".join(L)


# ── main ────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--yes", action="store_true",
                   help="Actually wipe conversation_history and run both "
                        "arms. Without it the script stops after capturing "
                        "evidence, having changed nothing.")
    p.add_argument("--preflight-only", action="store_true",
                   help="Check the environment and exit.")
    p.add_argument("--evidence-only", action="store_true",
                   help="Capture accumulation evidence and exit. Changes nothing.")
    p.add_argument("--tier", default="M_M", help="Model tier for the sweep.")
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = p.parse_args(argv)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    print("\n[0] preflight")
    ok, lines = preflight()
    print("\n".join(lines))
    if args.preflight_only:
        return 0 if ok else 1

    # Evidence first — always, and before anything destructive.
    print("\n[1] accumulation evidence (captured BEFORE any wipe)")
    db = _db_path()
    evidence = capture_evidence(db)
    ev_path = args.out_dir / f"track2c-accumulation-evidence-{stamp}.json"
    ev_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False),
                       encoding="utf-8")
    if evidence.get("available"):
        print(f"  total turns stored : {evidence['total_turns']}")
        print(f"  distinct sessions  : {evidence['session_count']}")
        print(f"  'default' key turns: {evidence['default_key_turns']}")
        print(f"  → {evidence['verdict']}")
    else:
        print(f"  [warn] could not read the DB: {evidence.get('error')}")
    print(f"  written: {_rel(ev_path)}")

    if args.evidence_only:
        print("\n--evidence-only: stopping. Nothing was changed.")
        return 0
    if not ok:
        print("\npreflight failed — refusing to continue. Nothing was changed.")
        return 1
    if not args.yes:
        print("\nNo --yes: stopping before the first wipe. Nothing was changed.")
        print("The evidence above is saved; re-run with --yes to measure.")
        return 0

    def wipe(label: str) -> int:
        con = sqlite3.connect(db)
        n = con.execute("SELECT COUNT(*) FROM conversation_history").fetchone()[0]
        con.execute("DELETE FROM conversation_history")
        con.commit()
        con.close()
        print(f"  [{label}] wiped {n} turns")
        return n

    def sweep(label: str, out: Path, shared_key: str | None) -> int:
        cmd = [sys.executable, str(ROOT / "scripts" / "adversarial_sweep.py"),
               "--fixture", str(FIXTURE), "--tier", args.tier,
               "--output", str(out)]
        if shared_key:
            cmd += ["--shared-session-key", shared_key]
        print(f"  [{label}] " + " ".join(cmd[1:]))
        return subprocess.call(cmd, cwd=str(ROOT))

    arm_a = args.out_dir / f"track2c-armA-shared-{stamp}.json"
    arm_b = args.out_dir / f"track2c-armB-salted-{stamp}.json"

    print("\n[2] arm A — one shared conversation key (pre-fix behaviour)")
    wipe("A")
    rc = sweep("A", arm_a, "default")
    if rc != 0 or not arm_a.exists():
        print(f"\narm A failed (rc={rc}); evidence is still at {_rel(ev_path)}")
        return rc or 1

    print("\n[3] arm B — salted per-case keys (the fix)")
    wipe("B")
    rc = sweep("B", arm_b, None)
    if rc != 0 or not arm_b.exists():
        print(f"\narm B failed (rc={rc}); arm A is at {_rel(arm_a)}")
        return rc or 1

    print("\n[4] A vs B — the measurement")
    rows, counts = compare_arms(arm_a, arm_b)
    print(f"  {'case':<44} {'shared':<11} {'salted':<11} published")
    for r in rows:
        mark = "  " if r["state"] == "same" else "→ "
        print(f"  {mark}{r['case_id']:<42} {str(r['shared']):<11} "
              f"{str(r['salted']):<11} {r['published']}")
    print(f"\n  {counts['moved']} moved / {counts['same']} unchanged")

    print("\n[5] letter block\n")
    block = emit_block(evidence, rows, counts, arm_a, arm_b)
    print(block)
    block_path = args.out_dir / f"track2c-letter-block-{stamp}.txt"
    block_path.write_text(block, encoding="utf-8")
    print(f"\nwritten: {_rel(block_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
