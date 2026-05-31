"""α-5 T0 smoke result analysis — auto-fill the template.

Reads the cell JSONs + baseline JSON and writes a dated analysis MD
with all numeric `[FILL]` placeholders replaced. Sections marked
`[interpret]` stay as `[TODO]` for the human reviewer to add prose.

Usage (run after T0 smoke completes)::

    JAMES_WORKSPACE=./workspaces/hotpot_eval \\
        python scripts/qvt_fill_t0_analysis.py

Output:
    reports/research-runs/qvt-ablation-T0-smoke-result-<YYYYMMDD-HHMM>.md

Cost: seconds. No LLM, no server. Just file IO + arithmetic.

Plan reference: `~/.claude/plans/quiet-hugging-iverson.md`. Template:
`reports/research-runs/qvt-ablation-T0-smoke-analysis-TEMPLATE.md`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parent.parent

TEMPLATE_PATH = (
    ROOT / "reports" / "research-runs"
    / "qvt-ablation-T0-smoke-analysis-TEMPLATE.md"
)

_QUALITY_AXES = ("path_coverage", "graded_answer", "abstention_f1")
_COST_AXES = ("token_cost", "latency_cost")
_ALL_AXES = _QUALITY_AXES + _COST_AXES


def _workspace_path(*parts: str) -> Path:
    ws = os.environ.get("JAMES_WORKSPACE", "").strip()
    base = Path(ws).resolve() if ws else ROOT
    return base.joinpath(*parts)


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _median(agg: Dict[str, Any], axis: str) -> Optional[float]:
    a = agg.get(axis) or {}
    return a.get("median")


def _delta(cell_med: Optional[float], base_med: Optional[float]) -> Optional[float]:
    if cell_med is None or base_med is None:
        return None
    return round(cell_med - base_med, 4)


def _fmt_delta(d: Optional[float], width: int = 7) -> str:
    if d is None:
        return "n/a"
    return f"{d:+.3f}".rjust(width) if abs(d) < 100 else f"{d:+.0f}".rjust(width)


def _fmt_val(v: Optional[float]) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:.4f}" if abs(v) < 100 else f"{v:.1f}"
    return str(v)


def _classify_verdict(deltas: Dict[str, float], noise: Dict[str, float]) -> str:
    """Mirror `_classify_five_axis_delta` for offline summary; the
    matrix runner's auto-emit is the canonical version, this is a
    standalone copy so the script doesn't import the runner."""
    q_pos = q_neg = 0
    for ax in _QUALITY_AXES:
        d = deltas.get(ax, 0.0)
        band = noise.get(ax, 0.0)
        if d is None:
            continue
        if d > band:
            q_pos += 1
        elif d < -band:
            q_neg += 1
    c_pos = c_neg = 0
    for ax in _COST_AXES:
        d = deltas.get(ax, 0.0)
        band = noise.get(ax, 0.0)
        if d is None:
            continue
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


def _format_5axis_row(label: str, deltas: Dict[str, Optional[float]],
                      verdict: str) -> str:
    cells = [_fmt_delta(deltas.get(ax)) for ax in _ALL_AXES]
    return (
        f"| **{label}** | {cells[0]} | {cells[1]} | {cells[2]} | "
        f"{cells[3]} | {cells[4]} | {verdict} |"
    )


def _format_per_type_table(per_type: Dict[str, Dict[str, Any]],
                            mode: str) -> str:
    """`mode` ∈ {'abs', 'delta'}. abs = absolute medians for the
    primary cell. delta = Δ vs baseline_per_type (for L5 and sanity)."""
    out = []
    for qt in ("comparison_query", "inference_query", "temporal_query", "null_query"):
        agg = per_type.get(qt) or {}
        row_cells = []
        for ax in _ALL_AXES:
            v = _median(agg, ax)
            if v is None:
                row_cells.append("n/a")
            elif ax == "path_coverage" and qt == "null_query":
                # null queries have no expected_path; path is omitted.
                row_cells.append("n/a")
            elif mode == "delta":
                row_cells.append(_fmt_delta(v))
            else:
                row_cells.append(_fmt_val(v))
        # Render: comparison/inference/temporal/null shortened
        short = qt.replace("_query", "")
        out.append(
            f"| {short} | {row_cells[0]} | {row_cells[1]} | {row_cells[2]} | "
            f"{row_cells[3]} | {row_cells[4]} |"
        )
    return "\n".join(out)


def _via_graph_via_sources(cell: Dict[str, Any]) -> tuple[int, int, int]:
    """Sum via_graph / via_sources across all per-query rows of the
    aggregated 5-axis result. Returns (sum_via_graph, sum_via_sources,
    sum_union_hits) over the run's `path_coverage.per_query` rows."""
    runs = cell.get("runs", [])
    via_g = via_s = union = 0
    for r in runs:
        per_q = (
            ((r.get("scores") or {}).get("path_coverage") or {}).get("per_query")
            or []
        )
        for row in per_q:
            via_g += int(row.get("via_graph") or 0)
            via_s += int(row.get("via_sources") or 0)
            union += int(row.get("hits") or 0)
    return via_g, via_s, union


def _t1_decision(l5_deltas: Dict[str, Optional[float]],
                 baseline_token: Optional[float],
                 baseline_lat: Optional[float]) -> tuple[str, str]:
    """Mirror the T0 verdict from qvt_ablation_matrix.py main."""
    quality_moved = any(
        l5_deltas.get(ax) is not None and abs(l5_deltas[ax]) >= 0.05
        for ax in _QUALITY_AXES
    )
    cost_thresh_token = 0.10 * (baseline_token or 1.0)
    cost_thresh_lat = 0.10 * (baseline_lat or 0.1)
    cost_moved = (
        (l5_deltas.get("token_cost") is not None
         and abs(l5_deltas["token_cost"]) >= cost_thresh_token)
        or (l5_deltas.get("latency_cost") is not None
            and abs(l5_deltas["latency_cost"]) >= cost_thresh_lat)
    )
    if not quality_moved and not cost_moved:
        return ("stop", "no axis moved past noise — matrix null at "
                        "production tier (~5.5h+ saved by skipping T1)")
    if quality_moved and not cost_moved:
        return ("T1 only", "quality axis moved ≥ 0.05; cost flat. "
                          "Proceed to T1 (M_M × all 6 rows, ~5.5h)")
    if cost_moved and not quality_moved:
        return ("T1 only", "cost moved ≥ 10% of L1 median; quality flat. "
                          "Proceed to T1 — likely efficiency-adopt verdict")
    return ("T1 + likely T2",
            "both quality and cost signals — proceed to T1, and likely "
            "T2 (M_S + M_L, ~13h) for tier-gating evidence")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--output", default=None,
        help="Output MD path. Default: "
             "reports/research-runs/qvt-ablation-T0-smoke-result-<ts>.md",
    )
    ap.add_argument(
        "--workspace-baseline", default=None,
        help="Baseline JSON path. Default: latest baseline_*.json "
             "under $JAMES_WORKSPACE/eval/qvt/",
    )
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    # Resolve baseline.
    if args.workspace_baseline:
        baseline_path = Path(args.workspace_baseline)
    else:
        baseline_dir = _workspace_path("eval", "qvt")
        candidates = sorted(baseline_dir.glob("baseline_*.json"))
        if not candidates:
            print(f"[error] no baseline JSON under {baseline_dir}")
            return 2
        baseline_path = candidates[-1]
    baseline = _load_json(baseline_path)
    if baseline is None:
        print(f"[error] baseline {baseline_path} not loadable")
        return 3
    base_agg = baseline.get("aggregate", {}) or {}
    base_per_type = baseline.get("aggregate_by_question_type", {}) or {}

    # Resolve cells.
    cell_dir = _workspace_path("reports", "research-runs", "qvt-ablation-cells")
    cell_l1 = _load_json(cell_dir / "qvt-ablation-cell-L1-M_M.json")
    cell_l5 = _load_json(cell_dir / "qvt-ablation-cell-L5-M_M.json")
    cell_sanity = _load_json(cell_dir / "qvt-ablation-cell-L1-M_M-thinkON.json")
    if cell_l1 is None or cell_l5 is None:
        print(f"[error] expected L1 and L5 cell JSONs under {cell_dir}")
        return 4

    # Load template.
    if not TEMPLATE_PATH.exists():
        print(f"[error] template not found: {TEMPLATE_PATH}")
        return 5
    md = TEMPLATE_PATH.read_text(encoding="utf-8")

    # Helper — build deltas dict for a cell.
    def _deltas_for(cell: Dict[str, Any]) -> Dict[str, Optional[float]]:
        agg = cell.get("aggregate", {}) or {}
        return {ax: _delta(_median(agg, ax), _median(base_agg, ax))
                for ax in _ALL_AXES}

    l1_deltas = _deltas_for(cell_l1)
    l5_deltas = _deltas_for(cell_l5)
    sanity_deltas = _deltas_for(cell_sanity) if cell_sanity else {}

    # noise band for verdict — use baseline noise_band per axis.
    noise = {ax: ((base_agg.get(ax) or {}).get("noise_band") or 0.0)
             for ax in _ALL_AXES}
    l1_verdict = _classify_verdict(l1_deltas, noise)
    l5_verdict = _classify_verdict(l5_deltas, noise)
    sanity_verdict = (
        _classify_verdict(sanity_deltas, noise) if cell_sanity else "—"
    )

    # ── §0 metadata ──────────────────────────────────────────────
    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    md = md.replace("[FILL: YYYY-MM-DD HH:MM]", now)
    # Compute total compute time from cells (sum of run latency × n_queries)
    # rough: cell's mean latency × ~100 queries × n_runs
    md = md.replace("[FILL] min",
                    f"~{int((cell_l1.get('n_runs', 1) + cell_l5.get('n_runs', 1) + (1 if cell_sanity else 0)) * 100 * ((base_agg.get('latency_cost') or {}).get('median') or 60) / 60)} min")

    # ── §1 5-axis Δ table ─────────────────────────────────────────
    table_lines = [
        _format_5axis_row("L1/M_M primary", l1_deltas, l1_verdict),
        _format_5axis_row("L5/M_M full stack", l5_deltas, l5_verdict),
    ]
    if cell_sanity:
        table_lines.append(_format_5axis_row(
            "L1/M_M-thinkON sanity", sanity_deltas, sanity_verdict))
    new_5axis_block = "\n".join(table_lines)
    # Replace the entire body of the 5-axis table (3 [FILL] rows).
    md = md.replace(
        "| **L1/M_M** primary | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |\n"
        "| **L5/M_M** full stack | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |\n"
        "| **L1/M_M-thinkON** sanity | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |",
        new_5axis_block,
    )

    # ── §2 per-question-type cross-tab ────────────────────────────
    l1_per_type = cell_l1.get("aggregate_by_question_type", {}) or {}
    l5_per_type = cell_l5.get("aggregate_by_question_type", {}) or {}
    sanity_per_type = (
        cell_sanity.get("aggregate_by_question_type", {}) or {}
        if cell_sanity else {}
    )

    # L1 absolute per-type table
    l1_per_block = _format_per_type_table(l1_per_type, mode="abs")
    md = md.replace(
        "| comparison | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |\n"
        "| inference | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |\n"
        "| temporal | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |\n"
        "| null | n/a (0) | [FILL] | [FILL] | [FILL] | [FILL] |",
        l1_per_block,
        1,
    )
    # L5 Δ per-type table (subtract base per type)
    l5_per_delta = {}
    for qt in l5_per_type:
        l5_per_delta[qt] = {}
        for ax in _ALL_AXES:
            cd = _median(l5_per_type[qt], ax)
            bd = _median(base_per_type.get(qt, {}), ax)
            d = _delta(cd, bd)
            l5_per_delta[qt][ax] = {"median": d} if d is not None else {"median": None}
    l5_per_block = _format_per_type_table(l5_per_delta, mode="delta")
    md = md.replace(
        "| comparison | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |\n"
        "| inference | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |\n"
        "| temporal | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |\n"
        "| null | n/a | [FILL] | [FILL] | [FILL] | [FILL] |",
        l5_per_block,
        1,
    )
    # Sanity per-type: Δ vs L1 primary per-type
    if cell_sanity:
        sanity_per_delta = {}
        for qt in sanity_per_type:
            sanity_per_delta[qt] = {}
            for ax in _ALL_AXES:
                cd = _median(sanity_per_type[qt], ax)
                pd = _median(l1_per_type.get(qt, {}), ax)
                d = _delta(cd, pd)
                sanity_per_delta[qt][ax] = {"median": d} if d is not None else {"median": None}
        sanity_per_block = _format_per_type_table(sanity_per_delta, mode="delta")
        md = md.replace(
            "| comparison | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |\n"
            "| inference | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |\n"
            "| temporal | [FILL] | [FILL] | [FILL] | [FILL] | [FILL] |\n"
            "| null | n/a | [FILL] | [FILL] | [FILL] | [FILL] |",
            sanity_per_block,
            1,
        )

    # ── §3 via_graph vs via_sources ───────────────────────────────
    l1_g, l1_s, l1_u = _via_graph_via_sources(cell_l1)
    l5_g, l5_s, l5_u = _via_graph_via_sources(cell_l5)
    md = md.replace(
        "| L1/M_M | [FILL] | [FILL] | [FILL] |\n"
        "| L5/M_M | [FILL] | [FILL] | [FILL] |",
        f"| L1/M_M | {l1_g} | {l1_s} | {l1_u} |\n"
        f"| L5/M_M | {l5_g} | {l5_s} | {l5_u} |",
    )

    # ── §4 sanity cell — A2 default-flip ──────────────────────────
    if cell_sanity:
        l1_agg = cell_l1.get("aggregate", {}) or {}
        sanity_agg = cell_sanity.get("aggregate", {}) or {}
        rows = []
        for ax in _ALL_AXES:
            primary = _median(l1_agg, ax)
            think_on = _median(sanity_agg, ax)
            d = _delta(think_on, primary)
            rows.append(
                f"| {ax} | {_fmt_val(primary)} | {_fmt_val(think_on)} | "
                f"{_fmt_delta(d)} |"
            )
        sanity_a2_block = "\n".join(rows)
        # Replace the 5-row [FILL] block in §4.
        md = md.replace(
            "| path_coverage | [FILL] | [FILL] | [FILL] |\n"
            "| graded_answer | [FILL] | [FILL] | [FILL] |\n"
            "| abstention_f1 | [FILL] | [FILL] | [FILL] |\n"
            "| token_cost | [FILL] | [FILL] | [FILL] |\n"
            "| latency_cost | [FILL] | [FILL] | [FILL] |",
            sanity_a2_block,
        )

    # ── §6 T1 / stop decision ─────────────────────────────────────
    decision, rationale = _t1_decision(
        l5_deltas,
        _median(base_agg, "token_cost"),
        _median(base_agg, "latency_cost"),
    )
    md = md.replace(
        "**Decision**: [FILL — stop / T1 only / T1+T2]",
        f"**Decision**: {decision}",
    )
    md = md.replace(
        "**Rationale**: [interpret]",
        f"**Rationale (auto)**: {rationale}. "
        "[REVIEWER: confirm / override based on per-axis Δ + bucket-(d) "
        "discipline (`feedback_oracle_phrase_artifacts`).]",
    )

    # Mark remaining [FILL] in §5 + §7 as TODOs (human interpretation).
    md = md.replace("[FILL]", "[TODO — fill before publishing]")

    # Write output.
    out_path = args.output and Path(args.output) or (
        ROOT / "reports" / "research-runs"
        / f"qvt-ablation-T0-smoke-result-{datetime.now().strftime('%Y%m%d-%H%M')}.md"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    print(f"[done] analysis written to {out_path}")
    print(f"  L1/M_M verdict:    {l1_verdict}")
    print(f"  L5/M_M verdict:    {l5_verdict}")
    if cell_sanity:
        print(f"  sanity verdict:    {sanity_verdict}")
    print(f"  T1 decision:       {decision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
