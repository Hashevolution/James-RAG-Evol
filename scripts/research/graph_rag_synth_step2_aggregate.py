"""Graph-RAG synthesis Step 2 — cross-model aggregator (Table 3.2).

The Step 2 driver (`graph_rag_synth_step2_cross_model.py`) leaves one
JSON per cell under the hotpot workspace; this script reads the Step 1
M_M cells alongside the Step 2 M_S / M_L cells and prints the two Δ
tables the synthesis doc §3.2 pre-registered, per tier:

  Graph-RAG contribution : C_rag-basic  → C_rag-graph
  Typed-filter           : C_rag-graph  → C_rag-ontology

It also applies §3.2's interpretation rules mechanically — the
±0.05 / >0.10 path_coverage bands, the graded_answer sign flip, the
typed-filter sign at M_L — and prints the verdict each rule yields, so
the doc update is a transcription, not a judgement made at the
keyboard. Medians only (n=3 paired, per
`feedback_n1_verdict_inflation_n3_caught`); the per-axis noise band is
printed next to every Δ so a Δ smaller than its own band is visible as
such.

Usage::

    python scripts/research/graph_rag_synth_step2_aggregate.py
    python scripts/research/graph_rag_synth_step2_aggregate.py --markdown
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
CELLS = ROOT / "workspaces" / "hotpot_eval" / "reports" / "research-runs" / "qvt-ablation-cells"

TIERS = ("M_M", "M_S", "M_L")
SECTOR = ("C_rag-basic", "C_rag-graph", "C_rag-ontology")
AXES = ("path_coverage", "graded_answer", "abstention_f1", "token_cost", "latency_cost")
QUALITY = AXES[:3]


def _load(cell: str, tier: str) -> Optional[dict]:
    p = CELLS / f"qvt-ablation-cell-{cell}-{tier}.json"
    if not p.exists():
        return None
    j = json.loads(p.read_text(encoding="utf-8"))
    if j.get("schema") != "qvt-ablation-cell-v4":
        # A v3 file is an α-6-era n=1 single shot left in the directory;
        # it is not Step 2 evidence and must not be mistaken for it.
        return None
    return j


def _agg(j: dict, axis: str) -> Dict[str, float]:
    return j["aggregate"][axis]


def _delta_row(a: dict, b: dict, axis: str):
    am, bm = _agg(a, axis)["median"], _agg(b, axis)["median"]
    band = max(_agg(a, axis)["noise_band"], _agg(b, axis)["noise_band"])
    if axis in ("token_cost", "latency_cost"):
        ratio = (bm / am) if am else float("nan")
        return am, bm, bm - am, band, ratio
    return am, bm, bm - am, band, None


def _fmt(v: float, axis: str) -> str:
    return f"{v:.0f}" if axis == "token_cost" else (f"{v:.1f}s" if axis == "latency_cost" else f"{v:.4f}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--markdown", action="store_true", help="emit doc-ready tables")
    args = ap.parse_args(argv)

    cells = {(c, t): _load(c, t) for c in SECTOR for t in TIERS}
    missing = [f"{c}/{t}" for (c, t), j in cells.items() if j is None]
    present = {k: v for k, v in cells.items() if v is not None}
    print(f"cells present: {len(present)}/{len(cells)}"
          + (f"  missing: {', '.join(missing)}" if missing else ""))
    for (c, t), j in sorted(present.items()):
        print(f"  {c:16s} {t:4s} n={j['n_runs']} model={j['model']} sha={j['git_sha']} captured={j['captured_at'][:10]}")

    pc_graph_delta: Dict[str, float] = {}
    ga_graph_delta: Dict[str, float] = {}
    tf_ga_delta: Dict[str, float] = {}

    for tier in TIERS:
        basic, graph, onto = (present.get((c, tier)) for c in SECTOR)
        print(f"\n=== {tier} ===")
        for title, a, b in (("Graph-RAG contribution (C_rag-basic -> C_rag-graph)", basic, graph),
                            ("Typed-filter (C_rag-graph -> C_rag-ontology)", graph, onto)):
            if a is None or b is None:
                print(f"  {title}: (incomplete)")
                continue
            print(f"  {title}")
            if args.markdown:
                print("  | Axis | A | B | Δ | noise band | note |\n  |---|---|---|---|---|---|")
            for axis in AXES:
                am, bm, d, band, ratio = _delta_row(a, b, axis)
                note = ""
                if axis in QUALITY and abs(d) <= band:
                    note = "within noise band"
                if ratio is not None:
                    note = f"{ratio:.2f}x"
                if args.markdown:
                    print(f"  | {axis} | {_fmt(am, axis)} | {_fmt(bm, axis)} | {d:+.4f} | {band:.4f} | {note} |")
                else:
                    print(f"    {axis:14s} {_fmt(am, axis):>9s} -> {_fmt(bm, axis):>9s}  Δ {d:+.4f}  band {band:.4f}  {note}")
                if title.startswith("Graph-RAG"):
                    if axis == "path_coverage":
                        pc_graph_delta[tier] = d
                    if axis == "graded_answer":
                        ga_graph_delta[tier] = d
                elif axis == "graded_answer":
                    tf_ga_delta[tier] = d

    # §3.2 interpretation rules, applied mechanically.
    print("\n=== §3.2 interpretation rules ===")
    if len(pc_graph_delta) == 3:
        spread = max(pc_graph_delta.values()) - min(pc_graph_delta.values())
        vals = ", ".join(f"{t} {v:+.3f}" for t, v in pc_graph_delta.items())
        if spread <= 0.05:
            print(f"path_coverage Δ holds within ±0.05 ({vals}; spread {spread:.3f}) -> "
                  "load-bearing on the 4B-12B gemma family")
        elif spread > 0.10:
            print(f"path_coverage Δ diverges by >0.10 ({vals}; spread {spread:.3f}) -> "
                  "MODEL-SPECIFIC; claim narrows to M_M, Table 3.2 documents the divergence")
        else:
            print(f"path_coverage Δ spread {spread:.3f} is between the two bands ({vals}) -> "
                  "neither rule fires; report as partial cross-model support")
    if len(ga_graph_delta) == 3:
        signs = {t: (v > 0) - (v < 0) for t, v in ga_graph_delta.items()}
        if len(set(signs.values())) > 1:
            print("graded_answer Δ flips sign across models -> capability-tier x retrieval-noise "
                  "interaction; model-specific finding")
        else:
            print("graded_answer Δ keeps its sign across models")
    if len(tf_ga_delta) == 3:
        if all(v > 0 for v in tf_ga_delta.values()):
            print("typed-filter graded_answer Δ > 0 on all three -> promote typed-filter to ** operational")
        if tf_ga_delta.get("M_L", 0) < 0:
            print("typed-filter Δ negative at M_L -> honest negative; default-on (PR #689) gets a caveat")
    if missing:
        print(f"\n({len(missing)} cell(s) missing — rules that need all three tiers were skipped)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
