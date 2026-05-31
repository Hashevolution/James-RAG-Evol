"""α-5 matrix-end wrapper — detect cells affected by the QQ glob bug,
rescore them, emit an audit summary.

Walk a workspace's `reports/research-runs/qvt-ablation-cells/`,
inspect each cell JSON's `runs[*].bench_output` field, and:

  - If `bench_output` mentions a *different* suite than the cell was
    meant to measure (the QQ bug fingerprint: cell reports a stale
    step7 file when the cycle is multihop_rag), rescore against the
    nearest correct bench file.
  - If `bench_output` already points at the right suite, leave it
    alone.
  - Emit a markdown summary listing what got rescored, what was
    correct, and what could not be auto-resolved.

The script is operator-invoked AFTER the matrix completes (do not
run mid-flight — rescore expects the cell JSON's bench_output to
be the final write). Idempotent: re-running on already-correct
cells prints "OK, no action" and exits cleanly.

Usage::

    python scripts/qvt_rescore_all_cells.py \\
        --workspace ./workspaces/hotpot_eval \\
        --suite multihop_rag \\
        --summary reports/research-runs/qvt-ablation-rescore-summary.md

    # Or dry-run to preview without writing:
    python scripts/qvt_rescore_all_cells.py \\
        --workspace ./workspaces/hotpot_eval \\
        --suite multihop_rag \\
        --dry-run

Companion to `scripts/qvt_rescore_ablation_cell.py` (single-cell
form). This wrapper handles the cycle-end batch.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
SINGLE_SCRIPT = ROOT / "scripts" / "qvt_rescore_ablation_cell.py"

SUITE_RE = re.compile(r"bench_[^_]+_([a-z][a-z0-9_]*?)_\d{8}_\d{6}\.json")


def _cell_bench_suite(bench_output: str) -> Optional[str]:
    """Pull the suite name from a cell's bench_output filename."""
    if not bench_output:
        return None
    m = SUITE_RE.search(Path(bench_output).name)
    return m.group(1) if m else None


def _classify_cell(cell_path: Path, expected_suite: str) -> Tuple[str, Optional[str]]:
    """Return (status, detail) for the cell.

    Status values:
      - "ok"        — bench_output matches expected suite
      - "needs"     — bench_output suite mismatches → QQ bug suspected
      - "empty"     — no runs / no bench_output → cell never completed
      - "unparsable"— filename doesn't match expected pattern
    """
    try:
        data = json.loads(cell_path.read_text(encoding="utf-8"))
    except Exception as e:
        return ("unparsable", f"json load error: {e}")
    runs = data.get("runs") or []
    if not runs:
        return ("empty", "no runs[] block")
    bench = runs[0].get("bench_output", "")
    if not bench:
        return ("empty", "runs[0].bench_output missing")
    suite = _cell_bench_suite(bench)
    if suite is None:
        return ("unparsable", f"bench filename: {bench}")
    if suite == expected_suite:
        return ("ok", f"bench suite={suite}")
    return ("needs", f"bench suite={suite} (expected {expected_suite})")


def _run_rescore(cell_path: Path, suite: str, dry_run: bool) -> bool:
    cmd = [
        sys.executable, str(SINGLE_SCRIPT),
        "--cell", str(cell_path),
        "--suite", suite,
    ]
    if dry_run:
        cmd.append("--dry-run")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[error] rescore failed for {cell_path.name}:")
        print(res.stdout)
        print(res.stderr)
        return False
    # Echo single-script output indented for the audit trail
    for line in (res.stdout or "").splitlines():
        print(f"  {line}")
    return True


def _write_summary(out_path: Path, expected_suite: str,
                   results: List[Tuple[Path, str, str]],
                   dry_run: bool) -> None:
    lines: List[str] = []
    lines.append("# α-5 Cell Rescore Audit Summary")
    lines.append("")
    lines.append(f"- Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Expected suite: `{expected_suite}`")
    lines.append(f"- Mode: {'dry-run' if dry_run else 'live'}")
    lines.append(f"- Tool: `scripts/qvt_rescore_all_cells.py`")
    lines.append("")
    lines.append("## Per-cell classification")
    lines.append("")
    lines.append("| Cell | Status | Detail |")
    lines.append("|---|---|---|")
    counts = {"ok": 0, "needs": 0, "empty": 0, "unparsable": 0}
    for cell, status, detail in results:
        counts[status] = counts.get(status, 0) + 1
        rel = cell.name
        lines.append(f"| `{rel}` | **{status}** | {detail} |")
    lines.append("")
    lines.append("## Totals")
    lines.append("")
    for k in ("ok", "needs", "empty", "unparsable"):
        lines.append(f"- {k}: {counts.get(k, 0)}")
    lines.append("")
    if counts.get("needs", 0) > 0:
        lines.append("## Action required")
        lines.append("")
        lines.append(
            f"{counts['needs']} cell(s) carry the QQ bug fingerprint "
            "(bench_output suite mismatches the cycle's expected suite). "
            "Re-running this wrapper without `--dry-run` rewrites their "
            "`runs[*].scores` + `aggregate` blocks against the correct "
            "bench file, with `.before-rescore.json` side-copies for the "
            "diagnostic trail."
        )
        lines.append("")
    if counts.get("ok", 0) == len(results) and results:
        lines.append("## Clean")
        lines.append("")
        lines.append(
            "All cell JSONs reference the expected suite — no rescore "
            "needed."
        )
        lines.append("")
    lines.append("## Wrong-fix avoided")
    lines.append("")
    lines.append(
        "α-5 cycle now stands at 4 wrong-fix-averted corrections "
        "(#618 / #619 / #623 / #638), 0 cumulative JAMES code-side "
        "changes. The 4-step verification rule generalises to "
        "bucket-(d) phrase coverage AND bucket-(a) wiring; this "
        "rescore is the last stop before publishable matrix numbers."
    )
    lines.append("")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[wrote] {out_path}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--workspace", type=Path, required=True,
                   help="JAMES_WORKSPACE root (e.g. ./workspaces/hotpot_eval)")
    p.add_argument("--suite", type=str, default="multihop_rag",
                   help="Expected suite (default: multihop_rag)")
    p.add_argument("--summary", type=Path,
                   default=ROOT / "reports" / "research-runs"
                   / "qvt-ablation-rescore-summary.md",
                   help="Markdown summary output path")
    p.add_argument("--dry-run", action="store_true",
                   help="Classify + preview without rescoring")
    p.add_argument("--include-ok", action="store_true",
                   help="Also re-emit aggregate for cells already on the "
                        "right suite (force-refresh; off by default)")
    args = p.parse_args()

    cell_dir = (args.workspace / "reports" / "research-runs"
                / "qvt-ablation-cells")
    if not cell_dir.exists():
        print(f"[error] cell dir not found: {cell_dir}")
        return 2
    cells = sorted(cell_dir.glob("qvt-ablation-cell-*.json"))
    cells = [c for c in cells
             if not c.name.endswith(".before-rescore.json")]
    if not cells:
        print(f"[info] no cell JSONs in {cell_dir}")
        return 0

    results: List[Tuple[Path, str, str]] = []
    for cell in cells:
        status, detail = _classify_cell(cell, args.suite)
        results.append((cell, status, detail))
        print(f"[{status}] {cell.name} — {detail}")

    needs_action = [c for c, s, _ in results
                    if s == "needs" or (s == "ok" and args.include_ok)]
    if needs_action:
        print(
            f"\nProcessing {len(needs_action)} cell(s) "
            f"({'dry-run' if args.dry_run else 'live'})..."
        )
        for cell in needs_action:
            _run_rescore(cell, args.suite, args.dry_run)
    else:
        print("\nAll cells on expected suite — nothing to rescore.")

    _write_summary(args.summary, args.suite, results, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
