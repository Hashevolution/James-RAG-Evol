"""α-6 Phase 1 closure auto-fill script (CCCC).

Reads:
  - 3 new sector cell JSONs (C_minus / C_rag-basic / C_rag-graph @ M_M)
  - α-5 carryover cells (L1 = C_rag-full, L5 = C_rag-routed)
  - The baseline JSON used for Δ
  - The Phase 1 analysis TEMPLATE (#665)

Writes:
  - reports/research-runs/alpha-6-phase-1-analysis-<YYYYMMDD>.md

Fills:
  - Run metadata block
  - 5-axis Δ table per cell
  - Sector-progression Δ table (cell-to-cell)
  - Predictions vs reality table (match/surprise classification)
  - Publishable claim paragraph

Operator action needed AFTER fill:
  - §4 publishable claim final interpretation (1-2 sentences)
  - §5 per-layer intent verdicts (each layer needs design-intent reading)
  - §6 next phase decision (which trigger fired)
  - §7 findings to promote (mechanism candidates)

Usage::

    JAMES_WORKSPACE=./workspaces/hotpot_eval \\
    PYTHONIOENCODING=utf-8 \\
      python scripts/alpha6_fill_phase1.py

    # Or specify output path:
    python scripts/alpha6_fill_phase1.py \\
        --out reports/research-runs/alpha-6-phase-1-analysis-20260601.md

Returns 0 on success, 2 if required cell JSONs missing.
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

_ALL_AXES = ("path_coverage", "graded_answer", "abstention_f1",
             "token_cost", "latency_cost")

# Predicted Δ direction per progression step (from #662 handover §"Expected
# publishable Δ predictions"). Used to classify each observed Δ as
# "match" or "surprise."
_PREDICTIONS = {
    ("C_minus", "C_rag-basic"): {
        "label": "+ S1 RAG retrieval (quality ↑↑ predicted)",
        "predict": {"path_coverage": "+", "graded_answer": "+",
                    "abstention_f1": "any"},
    },
    ("C_rag-basic", "C_rag-graph"): {
        "label": "+ S2 graph + S3 preproc + S4 citation (path ↑, graded ↑)",
        "predict": {"path_coverage": "+", "graded_answer": "+",
                    "abstention_f1": "any"},
    },
    ("C_rag-graph", "C_rag-full"): {
        "label": "+ S5 abstention + S6 cognitive (abst_f1 ↑, latency ↑)",
        "predict": {"abstention_f1": "+", "latency_cost": "+"},
    },
    ("C_rag-full", "C_rag-routed"): {
        "label": "+ routing layers (= α-5 L5 verdict; inert/regress expected)",
        "predict": {"abstention_f1": "-"},  # known regression from α-5
    },
}


def _resolve_cell_dir() -> Path:
    ws_raw = os.environ.get("JAMES_WORKSPACE", "").strip()
    if ws_raw:
        return Path(ws_raw).resolve() / "reports" / "research-runs" / "qvt-ablation-cells"
    return ROOT / "reports" / "research-runs" / "qvt-ablation-cells"


def _resolve_baseline() -> Optional[Path]:
    ws_raw = os.environ.get("JAMES_WORKSPACE", "").strip()
    base_dir = (Path(ws_raw).resolve() / "eval" / "qvt"
                if ws_raw else ROOT / "eval" / "qvt")
    # Prefer the rescored baseline if present.
    rescored = sorted(base_dir.glob("baseline_*_rescored.json"))
    if rescored:
        return rescored[-1]
    plain = sorted(base_dir.glob("baseline_*.json"))
    return plain[-1] if plain else None


def _load_cell(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _read_axis(cell: Optional[Dict[str, Any]], axis: str) -> Optional[float]:
    if cell is None:
        return None
    return cell.get("aggregate", {}).get(axis, {}).get("median")


def _fmt(v: Optional[float], precision: int = 3) -> str:
    if v is None:
        return "n/a"
    if precision == 0:
        return f"{v:+.0f}"
    return f"{v:+.{precision}f}"


def _abs(v: Optional[float], precision: int = 3) -> str:
    """Absolute (non-delta) format — no leading sign."""
    if v is None:
        return "n/a"
    if precision == 0:
        return f"{v:.0f}"
    return f"{v:.{precision}f}"


def _delta(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    return round(b - a, 4)


def _classify_prediction(observed: Optional[float], predicted: str) -> str:
    if observed is None:
        return "n/a (missing)"
    if predicted == "any":
        return "n/a (no prediction)"
    if predicted == "+":
        if observed > 0.01:
            return "✓ match"
        if observed < -0.01:
            return "✗ SURPRISE (predicted ↑, got ↓)"
        return "~ flat (predicted ↑, got flat)"
    if predicted == "-":
        if observed < -0.01:
            return "✓ match"
        if observed > 0.01:
            return "✗ SURPRISE (predicted ↓, got ↑)"
        return "~ flat (predicted ↓, got flat)"
    return "?"


def _render(cells: Dict[str, Optional[Dict[str, Any]]],
            baseline: Optional[Dict[str, Any]],
            baseline_path: Optional[Path]) -> str:
    """Return a filled analysis markdown."""
    now = datetime.now(timezone.utc).isoformat()
    today = datetime.now().strftime("%Y-%m-%d")

    # Pull baseline axes.
    base_med: Dict[str, Optional[float]] = {}
    for ax in _ALL_AXES:
        base_med[ax] = (baseline.get("aggregate", {}).get(ax, {}).get("median")
                        if baseline else None)

    def _row_for_cell(cell_id: str, cell: Optional[Dict[str, Any]]) -> str:
        if cell is None:
            return f"| {cell_id} | n/a | n/a | n/a | n/a | n/a | _missing_ |"
        deltas: Dict[str, Optional[float]] = {}
        for ax in _ALL_AXES:
            obs = _read_axis(cell, ax)
            deltas[ax] = _delta(base_med[ax], obs)
        return (f"| {cell_id} | "
                f"{_fmt(deltas['path_coverage'])} | "
                f"{_fmt(deltas['graded_answer'])} | "
                f"{_fmt(deltas['abstention_f1'])} | "
                f"{_fmt(deltas['token_cost'], precision=0)} | "
                f"{_fmt(deltas['latency_cost'], precision=2)} | "
                f"_observed_ |")

    # §0 Run metadata
    md = []
    md.append("# α-6 Phase 1 Analysis (auto-filled CCCC)")
    md.append("")
    md.append(f"> **Auto-filled at**: {now}")
    md.append(f"> **Source**: cell JSONs in `{_resolve_cell_dir()}`")
    if baseline_path:
        try:
            rel = baseline_path.relative_to(ROOT)
        except ValueError:
            rel = baseline_path
        md.append(f"> **Baseline**: `{rel}`")
    md.append("> **Filled by**: `scripts/alpha6_fill_phase1.py`")
    md.append("> **Operator action**: fill §4 prose, §5 layer-intent verdicts,")
    md.append(">                     §6 next-phase decision, §7 findings.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 0. Run metadata")
    md.append("")
    md.append("| Field | Value |")
    md.append("|---|---|")
    md.append(f"| Date | {today} |")
    md.append(f"| Workspace | `{os.environ.get('JAMES_WORKSPACE', '(unset)')}` |")
    md.append("| Suite | `multihop_rag` |")
    md.append("| Fixture | `balanced-100` (25 per question_type) |")
    if baseline:
        base_label = (
            f"path {_abs(base_med['path_coverage'])} / "
            f"graded {_abs(base_med['graded_answer'])} / "
            f"abst_f1 {_abs(base_med['abstention_f1'])}"
        )
        md.append(f"| Baseline | `{baseline.get('git_sha', '?')}` ({base_label}) |")
    md.append("| Tier | M_M only (`gemma4:e4b`, think=OFF) |")
    md.append("")
    md.append("---")
    md.append("")

    # §1 Per-cell 5-axis Δ vs baseline
    md.append("## 1. 5-axis Δ table vs baseline")
    md.append("")
    md.append("| Cell | path Δ | graded Δ | abst_f1 Δ | token Δ | latency Δ | Verdict |")
    md.append("|---|---|---|---|---|---|---|")
    for cid in ("C_minus", "C_rag-basic", "C_rag-graph",
                "C_rag-full", "C_rag-routed"):
        md.append(_row_for_cell(cid, cells.get(cid)))
    md.append("")
    md.append(f"Baseline (for reference): path {_abs(base_med['path_coverage'])} / "
              f"graded {_abs(base_med['graded_answer'])} / "
              f"abst_f1 {_abs(base_med['abstention_f1'])} / "
              f"token {_abs(base_med['token_cost'], precision=0)} / "
              f"latency {_abs(base_med['latency_cost'], precision=0)}.")
    md.append("")
    md.append("---")
    md.append("")

    # §2 Sector-progression Δ
    md.append("## 2. Sector-progression Δ (cell-to-cell)")
    md.append("")
    md.append("| From → To | Sector added | path Δ | graded Δ | abst_f1 Δ | token Δ | latency Δ |")
    md.append("|---|---|---|---|---|---|---|")
    progression = [
        ("C_minus", "C_rag-basic", "+ S1 RAG retrieval"),
        ("C_rag-basic", "C_rag-graph", "+ S2 graph + S3 preproc + S4 citation"),
        ("C_rag-graph", "C_rag-full", "+ S5 abstention + S6 cognitive"),
        ("C_rag-full", "C_rag-routed", "+ routing layers (= α-5 L5)"),
    ]
    for from_id, to_id, label in progression:
        a = cells.get(from_id)
        b = cells.get(to_id)
        if a is None or b is None:
            md.append(f"| {from_id} → {to_id} | {label} | "
                      "_missing_ | _missing_ | _missing_ | _missing_ | _missing_ |")
            continue
        deltas: Dict[str, Optional[float]] = {}
        for ax in _ALL_AXES:
            deltas[ax] = _delta(_read_axis(a, ax), _read_axis(b, ax))
        md.append(
            f"| {from_id} → {to_id} | {label} | "
            f"{_fmt(deltas['path_coverage'])} | "
            f"{_fmt(deltas['graded_answer'])} | "
            f"{_fmt(deltas['abstention_f1'])} | "
            f"{_fmt(deltas['token_cost'], precision=0)} | "
            f"{_fmt(deltas['latency_cost'], precision=2)} |"
        )
    md.append("")
    md.append("---")
    md.append("")

    # §3 Predictions vs reality
    md.append("## 3. Predictions vs reality (auto-classified)")
    md.append("")
    md.append("Per-step predictions from #662 handover; each compared against the observed Δ.")
    md.append("")
    md.append("| Step | Predicted | Observed | Match? |")
    md.append("|---|---|---|---|")
    for (from_id, to_id), pred in _PREDICTIONS.items():
        a = cells.get(from_id)
        b = cells.get(to_id)
        if a is None or b is None:
            md.append(f"| {from_id} → {to_id} | {pred['label']} | _missing_ | _missing_ |")
            continue
        observations = []
        classifications = []
        for axis, direction in pred["predict"].items():
            obs = _delta(_read_axis(a, axis), _read_axis(b, axis))
            observations.append(f"{axis}={_fmt(obs)}")
            classifications.append(f"{axis}: {_classify_prediction(obs, direction)}")
        md.append(f"| {from_id} → {to_id} | {pred['label']} | "
                  f"{', '.join(observations)} | {'; '.join(classifications)} |")
    md.append("")
    md.append("[FILL §3 prose: 2-3 sentences interpreting the matches/surprises]")
    md.append("")
    md.append("---")
    md.append("")

    # §4 Publishable claim
    md.append("## 4. Publishable claim (auto-template; operator fills final sentence)")
    md.append("")
    md.append("> **JAMES sector ablation on MultiHop-RAG balanced-100, "
              "gemma4:e4b production tier (think=OFF, bge-m3)**:")
    for cid, prefix in [
        ("C_minus", "Pure gemma4 (no JAMES)"),
        ("C_rag-basic", "+ chroma RAG retrieval"),
        ("C_rag-graph", "+ graph + preprocessing + citation"),
        ("C_rag-full", "JAMES full stack (= α-5 L1)"),
        ("C_rag-routed", "JAMES + routing layers (= α-5 L5)"),
    ]:
        cell = cells.get(cid)
        line = (
            f"> - {prefix}: "
            f"path {_abs(_read_axis(cell, 'path_coverage'))} / "
            f"graded {_abs(_read_axis(cell, 'graded_answer'))} / "
            f"abst_f1 {_abs(_read_axis(cell, 'abstention_f1'))}"
        )
        md.append(line)
    md.append(">")
    md.append("> [FILL: 1-2 sentence operator interpretation. Mother-platform framing per positioning guard.]")
    md.append("")
    md.append("---")
    md.append("")

    # §5-§8 stay TEMPLATE-style for operator
    md.append("## 5. Verdict per layer (operator fills per layer-intent matrix)")
    md.append("")
    md.append("Per CLAUDE.md rule 2 layer-intent extension (#652) + memory")
    md.append("`mechanism_layer_intent_axis_alignment`. Each sector judged on its")
    md.append("**design-intent axes**, not uniform Pareto.")
    md.append("")
    md.append("| Layer | Design intent | Primary axes | Δ on primary | Regression check | Verdict |")
    md.append("|---|---|---|---|---|---|")
    md.append("| S1 RAG retrieval | retrieval recall | path + graded | [FILL] | abst_f1 noise | [FILL] |")
    md.append("| S2 Graph | concept multi-hop | path + graded | [FILL] | cost noise | [FILL] |")
    md.append("| S3 Preproc | input fluency | path + graded | [FILL] | cost noise | [FILL] |")
    md.append("| S4 Citation | source surface | path primary | [FILL] | quality flat | [FILL] |")
    md.append("| S5 Abstention | refusal grounding | abst_f1 primary | [FILL] | quality protection | [FILL] |")
    md.append("| S6 Cognitive | multi-step | graded primary | [FILL] | latency cost expected | [FILL] |")
    md.append("")
    md.append("[FILL §5 prose: per-layer reasoning, applying design-intent matrix not uniform Pareto.]")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 6. Next phase decision (operator)")
    md.append("")
    md.append("Per Phase 2 entry doc trigger matrix (#666 §1):")
    md.append("")
    md.append("- [ ] Phase 1 shows clear sector-additive signal → proceed to Phase 2 (M_S tier)")
    md.append("- [ ] Phase 1 shows ambiguous / mixed signal → run C_rag-cited isolation first")
    md.append("- [ ] Phase 1 shows sectors regressive at production → apply 4-step rule, bucket the result")
    md.append("- [ ] Phase 1 shows clear gemma4:e4b best → Phase 3a lower priority")
    md.append("")
    md.append("[FILL §6: which option fired + chosen action]")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 7. Findings to promote (operator)")
    md.append("")
    md.append("[FILL §7: bucket-tagged findings list. Use `qvt_promote_findings.py` to draft memory entries.]")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 8. Cross-references")
    md.append("")
    md.append("- α-6 design memo: `docs/design/v0.4-alpha-6-sector-llm-ablation-matrix.md`")
    md.append("- Phase 1 template: `reports/research-runs/alpha-6-phase-1-analysis-TEMPLATE.md` (#665)")
    md.append("- Phase 2 entry: `docs/handovers/v0.4-alpha-6-phase-2-entry.md` (#666)")
    md.append("- Layer-intent matrix: `memory/mechanism_layer_intent_axis_alignment.md`")
    md.append("- 4-step rule: `memory/feedback_oracle_phrase_artifacts.md`")
    md.append("- Position guard: `memory/feedback_jameses_positioning_replayable_rag.md`")
    md.append("- Matrix runner sector cells: PR #663")
    md.append("- Renderer sector cells + progression: PR #664")
    md.append("- This auto-fill script: `scripts/alpha6_fill_phase1.py` (#667)")
    md.append("")

    return "\n".join(md) + "\n"


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, default=None,
                   help="Output path (default: "
                        "reports/research-runs/alpha-6-phase-1-analysis-<YYYYMMDD>.md)")
    args = p.parse_args(argv)

    cell_dir = _resolve_cell_dir()
    baseline_path = _resolve_baseline()
    baseline = json.loads(baseline_path.read_text(encoding="utf-8")) \
        if baseline_path else None

    # Load required cells; alias L1/L5 row cells into sector cell slots.
    cells: Dict[str, Optional[Dict[str, Any]]] = {}
    cells["C_minus"]      = _load_cell(cell_dir / "qvt-ablation-cell-C_minus-M_M.json")
    cells["C_rag-basic"]  = _load_cell(cell_dir / "qvt-ablation-cell-C_rag-basic-M_M.json")
    cells["C_rag-graph"]  = _load_cell(cell_dir / "qvt-ablation-cell-C_rag-graph-M_M.json")
    cells["C_rag-full"]   = _load_cell(cell_dir / "qvt-ablation-cell-L1-M_M.json")
    cells["C_rag-routed"] = _load_cell(cell_dir / "qvt-ablation-cell-L5-M_M.json")

    have_any = any(cells.values())
    if not have_any:
        print(f"[error] no cell JSONs found under {cell_dir}")
        return 2

    if args.out is None:
        today = datetime.now().strftime("%Y%m%d")
        args.out = (ROOT / "reports" / "research-runs"
                    / f"alpha-6-phase-1-analysis-{today}.md")

    body = _render(cells, baseline, baseline_path)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(body, encoding="utf-8")
    print(f"[wrote] {args.out}")
    n_filled = sum(1 for v in cells.values() if v is not None)
    print(f"[cells] {n_filled}/5 loaded "
          f"({', '.join(sorted(k for k, v in cells.items() if v))})")
    n_missing = 5 - n_filled
    if n_missing > 0:
        print(f"[note] {n_missing} cell(s) missing — table shows _missing_; "
              "rerun after they land.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
