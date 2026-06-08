"""Cycle γ Phase B Option A — pairwise comparison of two
external-bench result JSONs.

Reads two ``run_external_bench`` outputs and emits a side-by-side
table of axis scores + a delta column. Designed for the
JAMES-engine-vs-closed-corpus-baseline comparison the Option A
experiment ships, but the shape works for any pair of result
files from ``scripts/external_bench_run.py``.

Usage::

    python scripts/research/cycle_gamma_rgb_compare.py \\
        --baseline reports/cycle_gamma/rgb-en-dual-axis-20260608.json \\
        --treatment reports/cycle_gamma/rgb-en-james-engine-20260608.json \\
        --out reports/cycle_gamma/rgb-en-comparison-20260608.md

The output is a small markdown table — easy to paste into a
handover doc + diff via git. No publish-grade aggregation; the
file is forensic, not a conclusion.

Honest framing rule (memory ``feedback_finding_size_honest_framing``):
this script reports raw deltas, not "wins" or claims. The reader
decides whether a delta is ⭐ / ⭐⭐ / ⭐⭐⭐ based on n_queries,
single-vs-multi-stack, etc. The script writes the n_queries
column prominently so under-powered comparisons cannot be
laundered as conclusions.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _load(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"result file not found: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _axis_table(result: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """{axis_name: {score, n_queries, notes}} for one result."""
    out: Dict[str, Dict[str, Any]] = {}
    for ax in result.get("axes", []):
        out[ax["name"]] = {
            "score":     ax["score"],
            "n_queries": ax["n_queries"],
            "notes":     ax.get("notes", ""),
        }
    return out


def _format_delta(b: float, t: float) -> str:
    """+0.NNN with sign; — when either side is N/A."""
    if b is None or t is None:
        return "—"
    d = t - b
    return f"{d:+.4f}"


def _render(
    baseline: Dict[str, Any],
    treatment: Dict[str, Any],
) -> str:
    base_axes = _axis_table(baseline)
    treat_axes = _axis_table(treatment)
    all_names = sorted(set(base_axes) | set(treat_axes))

    lines: List[str] = []
    lines.append("# Cycle γ RGB-en Phase B Option A comparison")
    lines.append("")
    lines.append("## Headline")
    lines.append("")
    lines.append(f"- baseline  : `{baseline.get('benchmark')}` "
                  f"producer=`{baseline.get('producer')}` "
                  f"n_queries={baseline.get('n_queries')} "
                  f"n_errors={baseline.get('n_errors')}")
    lines.append(f"- treatment : `{treatment.get('benchmark')}` "
                  f"producer=`{treatment.get('producer')}` "
                  f"n_queries={treatment.get('n_queries')} "
                  f"n_errors={treatment.get('n_errors')}")
    lines.append("")
    lines.append("## Per-axis delta")
    lines.append("")
    lines.append("| axis | baseline score (n) | treatment score (n) | "
                  "Δ (treatment − baseline) |")
    lines.append("|---|---|---|---|")
    for name in all_names:
        b = base_axes.get(name)
        t = treat_axes.get(name)
        b_s = (f"{b['score']:.4f} (n={b['n_queries']})"
                if b else "— (n=—)")
        t_s = (f"{t['score']:.4f} (n={t['n_queries']})"
                if t else "— (n=—)")
        delta = _format_delta(
            b["score"] if b else None,
            t["score"] if t else None,
        )
        lines.append(f"| `{name}` | {b_s} | {t_s} | {delta} |")
    lines.append("")
    lines.append("## Notes (per axis, treatment side)")
    lines.append("")
    for name in all_names:
        t = treat_axes.get(name)
        if t and t["notes"]:
            lines.append(f"- **`{name}`**: {t['notes'].strip()}")
    lines.append("")
    lines.append("## Honest framing")
    lines.append("")
    lines.append(
        "Per `memory/feedback_finding_size_honest_framing.md`: a "
        "delta of magnitude X on n_queries=Y is *operational*, not "
        "publishable, until paired with cross-model and/or "
        "cross-bench confirmation. The numbers above are this "
        "session's evidence; framing tier elevation requires a "
        "separate analysis pass."
    )
    lines.append("")
    return "\n".join(lines)


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="cycle_gamma_rgb_compare",
        description="Pairwise comparison of two external-bench "
                     "result JSONs.",
    )
    p.add_argument("--baseline", required=True,
                    help="path to the baseline run's result JSON "
                          "(e.g. raw closed-corpus)")
    p.add_argument("--treatment", required=True,
                    help="path to the treatment run's result JSON "
                          "(e.g. JAMES engine)")
    p.add_argument("--out", default=None,
                    help="output markdown path; if omitted, prints "
                          "to stdout")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                    errors="replace")

    baseline = _load(Path(args.baseline))
    treatment = _load(Path(args.treatment))

    md = _render(baseline, treatment)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md, encoding="utf-8")
        print(f"saved: {out_path}")
    else:
        print(md)

    return 0


if __name__ == "__main__":
    sys.exit(main())
