"""Compare two QVT matrix-runner cell JSONs and produce Δ + verdict.

Reusable post-measurement comparison tool — born 2026-06-03 for the β-1
reranker swap measurement. Designed so future cycle measurements
(β-2 top_k, γ chunk size, δ hybrid weights) can reuse without code change.

Usage::

    python scripts/research/compare_paired_cells.py \\
        --baseline path/to/baseline.json \\
        --candidate path/to/candidate.json \\
        --label-baseline "ms-marco" \\
        --label-candidate "bge-reranker-base" \\
        [--fixture eval/regression/step7_queries.json]   # for per-question detail
        [--noise-band-mode max|baseline]                  # default: max

Output: prints a structured comparison + writes a markdown report at
``reports/research-runs/compare-<baseline_label>-vs-<cand_label>-<ts>.md``.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional


def _load_cell(path: str) -> Dict:
    with open(path, encoding="utf-8") as fp:
        return json.load(fp)


def _verdict_for(graded_delta: float, abst_delta: float,
                 noise_graded: float, noise_abst: float) -> str:
    """Apply the verdict tree from design memo §4.1 + honest framing.

    Returns one of:
      ⭐⭐⭐ saturate    — graded Δ ≥ +0.10 AND outside noise
      ⭐⭐ clear adopt   — graded Δ ≥ +0.030 AND outside noise
      ⭐⭐ tier-gated    — graded Δ +0.010 to +0.030 outside noise
      ⭐ operational    — graded Δ in noise OR < +0.010
      regression       — graded Δ < −0.010 outside noise
      no-change        — both Δ flat inside noise

    Noise band uses MAX of baseline/candidate noise per axis.
    """
    inside_noise_graded = abs(graded_delta) <= noise_graded
    inside_noise_abst = abs(abst_delta) <= noise_abst

    if graded_delta < -0.010 and not inside_noise_graded:
        return "🔴 REGRESSION"
    if graded_delta >= 0.10 and not inside_noise_graded:
        return "⭐⭐⭐ saturate"
    if graded_delta >= 0.030 and not inside_noise_graded:
        return "⭐⭐ clear adopt"
    if 0.010 <= graded_delta < 0.030 and not inside_noise_graded:
        return "⭐⭐ tier-gated"
    if inside_noise_graded and inside_noise_abst:
        return "⚪ no-change (within noise)"
    return "⭐ operational only"


def _per_query_delta(b: Dict, c: Dict, fixture_map: Optional[Dict] = None) -> Dict:
    """Aggregate per-query refusal change across 3 paired runs.
    Returns dict: query_id → {label, baseline_refusals, candidate_refusals, ...}
    """
    out: Dict[int, Dict] = defaultdict(lambda: {
        "label": "", "intent": "?", "baseline_refusals": 0,
        "candidate_refusals": 0, "baseline_hallucinations": 0,
        "candidate_hallucinations": 0,
    })

    for cell_label, cell in [("baseline", b), ("candidate", c)]:
        for r in cell.get("runs", []):
            for pq in r.get("scores", {}).get("abstention", {}).get("per_query", []):
                qid = pq.get("id")
                if qid is None:
                    continue
                d = out[qid]
                if pq.get("abstained"):
                    d[f"{cell_label}_refusals"] += 1
                else:
                    d[f"{cell_label}_hallucinations"] += 1
                if fixture_map and not d["label"]:
                    fq = fixture_map.get(qid, {})
                    d["label"] = fq.get("text", "")[:60]
                    d["intent"] = fq.get("expected_intent") or fq.get("question_type", "?")

    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--baseline", required=True,
                        help="Baseline cell JSON path")
    parser.add_argument("--candidate", required=True,
                        help="Candidate cell JSON path")
    parser.add_argument("--label-baseline", default="baseline",
                        help="Short label for baseline (e.g., 'ms-marco')")
    parser.add_argument("--label-candidate", default="candidate",
                        help="Short label for candidate (e.g., 'bge-reranker-base')")
    parser.add_argument("--fixture", default=None,
                        help="Fixture JSON path for per-query labels")
    parser.add_argument("--output", default=None,
                        help="Optional output markdown path")
    args = parser.parse_args(argv)

    b = _load_cell(args.baseline)
    c = _load_cell(args.candidate)
    fixture_map = None
    if args.fixture:
        try:
            f = json.load(open(args.fixture, encoding="utf-8"))
            fixture_map = {q["id"]: q for q in f.get("queries", [])}
        except (OSError, json.JSONDecodeError, KeyError) as e:
            print(f"[warn] fixture load failed: {e}")

    lines = []
    add = lines.append

    add(f"# β-1 Comparison Report — {args.label_baseline} vs {args.label_candidate}")
    add("")
    add(f"> Generated: {datetime.now().isoformat(timespec='seconds')}  ")
    add(f"> baseline:  `{args.baseline}` ({b.get('captured_at', '?')[:19]})  ")
    add(f"> candidate: `{args.candidate}` ({c.get('captured_at', '?')[:19]})  ")
    add(f"> suite: {b.get('row', '?')} / {b.get('tier', '?')}; "
        f"git_sha baseline={b.get('git_sha','?')} candidate={c.get('git_sha','?')}")
    add("")

    # Δ table
    add("## Aggregate Δ (candidate − baseline)")
    add("")
    add(f"| Axis | {args.label_baseline} median | {args.label_candidate} median | Δ | noise (max) | Inside/Outside |")
    add("|---|---:|---:|---:|---:|---|")
    deltas = {}
    for axis in ["path_coverage", "graded_answer", "abstention_f1", "token_cost", "latency_cost"]:
        ga = b["aggregate"].get(axis, {})
        oa = c["aggregate"].get(axis, {})
        b_med = ga.get("median", 0.0)
        c_med = oa.get("median", 0.0)
        d = c_med - b_med
        nb = max(ga.get("noise_band", 0.0), oa.get("noise_band", 0.0))
        deltas[axis] = (b_med, c_med, d, nb)
        sign = "+" if d >= 0 else ""
        if abs(d) <= nb:
            io = "✓ inside noise"
        elif d > 0:
            io = "✗ OUTSIDE +"
        else:
            io = "✗ OUTSIDE −"
        add(f"| {axis} | {b_med:.4f} | {c_med:.4f} | **{sign}{d:.4f}** | ±{nb:.4f} | {io} |")
    add("")

    # Verdict
    g_b, g_c, g_d, g_n = deltas["graded_answer"]
    a_b, a_c, a_d, a_n = deltas["abstention_f1"]
    verdict = _verdict_for(g_d, a_d, g_n, a_n)
    add(f"## Verdict: {verdict}")
    add("")
    add("Per design memo §4.1 + honest framing ([[feedback_finding_size_honest_framing]]).")
    add("")

    # Confusion matrix change
    def sum_abs(cell):
        s = {"TP": 0, "FP": 0, "FN": 0, "TN": 0}
        for r in cell.get("runs", []):
            a = r["scores"].get("abstention", {})
            s["TP"] += a.get("tp_abstain", 0)
            s["FP"] += a.get("fp_incorrect_abstention", 0)
            s["FN"] += a.get("fn_hallucination", 0)
            s["TN"] += a.get("tn_answer", 0)
        return s

    b_sum = sum_abs(b)
    c_sum = sum_abs(c)
    add("## Confusion matrix aggregate (sum across 3 runs)")
    add("")
    add("```")
    add(f"{args.label_baseline:>16}:  TP={b_sum['TP']:>3}  FP={b_sum['FP']:>3}  "
        f"FN={b_sum['FN']:>3}  TN={b_sum['TN']:>3}")
    add(f"{args.label_candidate:>16}:  TP={c_sum['TP']:>3}  FP={c_sum['FP']:>3}  "
        f"FN={c_sum['FN']:>3}  TN={c_sum['TN']:>3}")
    add(f"{'Δ':>16}:  ΔTP={c_sum['TP']-b_sum['TP']:+d}  "
        f"ΔFP={c_sum['FP']-b_sum['FP']:+d}  "
        f"ΔFN={c_sum['FN']-b_sum['FN']:+d}  "
        f"ΔTN={c_sum['TN']-b_sum['TN']:+d}")
    add("```")
    add("")
    if b_sum["FN"] > 0:
        fn_pct = (b_sum["FN"] - c_sum["FN"]) / b_sum["FN"] * 100
        add(f"**FN reduction**: {fn_pct:+.1f}% ({b_sum['FN']}→{c_sum['FN']})")
    add("")

    # Per-run breakdown
    add("## Per-run results")
    add("")
    add(f"| Run | {args.label_baseline} graded | {args.label_baseline} abst_f1 | "
        f"{args.label_candidate} graded | {args.label_candidate} abst_f1 |")
    add("|---:|---:|---:|---:|---:|")
    for i in range(max(len(b.get("runs", [])), len(c.get("runs", [])))):
        b_r = b["runs"][i]["scores"] if i < len(b.get("runs", [])) else None
        c_r = c["runs"][i]["scores"] if i < len(c.get("runs", [])) else None
        b_g = b_r["graded_answer"]["mean_accuracy"] if b_r else None
        b_a = b_r["abstention"]["f1"] if b_r else None
        c_g = c_r["graded_answer"]["mean_accuracy"] if c_r else None
        c_a = c_r["abstention"]["f1"] if c_r else None
        add(f"| {i+1} | {b_g:.3f} | {b_a:.3f} | {c_g:.3f} | {c_a:.3f} |")
    add("")

    # Per-query analysis
    if fixture_map:
        pq = _per_query_delta(b, c, fixture_map)
        add("## Per-query analysis (refusals across 3 runs each)")
        add("")
        # Categorize: rescued (cand more refusals), regressed (cand fewer), unchanged
        rescued = []  # candidate fixes a baseline hallucination
        regressed = []  # candidate breaks a baseline refusal
        unchanged_correct = []
        unchanged_wrong = []
        for qid, d in sorted(pq.items()):
            delta = d["candidate_refusals"] - d["baseline_refusals"]
            if delta > 0:
                rescued.append((qid, delta, d))
            elif delta < 0:
                regressed.append((qid, delta, d))
            elif d["baseline_refusals"] >= 2:
                unchanged_correct.append((qid, d))
            else:
                unchanged_wrong.append((qid, d))

        add(f"- ✅ rescued (candidate refuses more): **{len(rescued)} queries**")
        add(f"- ❌ regressed (candidate refuses less): **{len(regressed)} queries**")
        add(f"- ⚪ unchanged-correct: {len(unchanged_correct)}")
        add(f"- ⚪ unchanged-wrong: {len(unchanged_wrong)}")
        add("")
        if rescued:
            add("### Rescued queries (candidate caught what baseline missed)")
            add("")
            add("| id | intent | Δrefusals | query |")
            add("|---:|---|---:|---|")
            for qid, delta, d in rescued[:15]:
                add(f"| {qid} | `{d['intent']}` | +{delta} | {d['label']!r} |")
            add("")
        if regressed:
            add("### Regressed queries (candidate broke what baseline caught)")
            add("")
            add("| id | intent | Δrefusals | query |")
            add("|---:|---|---:|---|")
            for qid, delta, d in regressed[:15]:
                add(f"| {qid} | `{d['intent']}` | {delta} | {d['label']!r} |")
            add("")

    # Cost axes
    add("## Cost axes")
    add("")
    _, _, tc_d, tc_n = deltas["token_cost"]
    _, _, lat_d, lat_n = deltas["latency_cost"]
    add(f"- token_cost Δ: {tc_d:+.1f} chars  (noise ±{tc_n:.1f})")
    add(f"- latency Δ:    {lat_d:+.3f}s     (noise ±{lat_n:.3f}s)")
    add("")

    # Recommendation
    add("## Recommendation")
    add("")
    if verdict.startswith("⭐⭐⭐"):
        add("**Adopt + ARCHITECTURE.md entry**. Strong cross-fixture confirm "
            "should follow before any publishable claim.")
    elif verdict.startswith("⭐⭐"):
        add("**Adopt or tier-gated adopt**. Run cross-fixture sanity (different "
            "fixture) before ⭐⭐⭐ promotion.")
    elif verdict.startswith("⭐"):
        add("**Operational only**. Keep code if no regression cost; document "
            "honest framing. Mechanism does not produce publishable Δ at this "
            "fixture/N.")
    elif verdict.startswith("⚪"):
        add("**No change**. Candidate makes no measurable difference; default "
            "to baseline for ops simplicity.")
    else:
        add("**REGRESSION — do NOT adopt**. Investigate. Possible candidates: "
            "model-specific failure mode, environmental confound, fixture mismatch.")
    add("")
    add("---")
    add("")
    add("*Generated by `scripts/research/compare_paired_cells.py`.*")

    report = "\n".join(lines)

    # Always print summary to stdout
    print(report)

    # Write to file
    if args.output:
        out_path = Path(args.output)
    else:
        ts = datetime.now().strftime("%Y%m%dT%H%M%S")
        slug = f"{args.label_baseline}-vs-{args.label_candidate}".replace(" ", "_").replace("/", "_")
        out_path = Path(f"reports/research-runs/compare-{slug}-{ts}.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"\n[wrote] {out_path}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
