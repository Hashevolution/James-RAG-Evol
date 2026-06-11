"""LRB Phase B runner -- cross-scenario (S1 + S2) × 3 SUT measurement."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Callable, Dict, List

from eval.external.lrb.adapters import (
    JamesValidityAdapter, NaiveSupersedeAdapter, VanillaRagAdapter)
from eval.external.lrb.driver import (
    fixture_sha, load_scenario, run_sut, score_run as score_run_phase_a)
from eval.external.lrb.driver_phase_b import (
    run_sut_phase_b, score_run as score_run_phase_b)

ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE_S1 = ROOT / "eval" / "external" / "_fixtures" / "lrb" / \
    "scenario_S1_quarterly.json"
FIXTURE_S2 = ROOT / "eval" / "external" / "_fixtures" / "lrb" / \
    "scenario_S2_yearly_timetravel.json"
OUT_DIR = ROOT / "reports" / "external" / "lrb"

SUTS = {
    "vanilla":         VanillaRagAdapter,
    "naive-supersede": NaiveSupersedeAdapter,
    "james":           JamesValidityAdapter,
}


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def per_category_breakdown(rows: List[Dict[str, Any]],
                           qid_to_cat: Dict[str, str]) -> Dict[str, Any]:
    from eval.external.lrb.scorer import (
        _precision_at_k, _recall_at_k, _temporal_accuracy)
    by_cat: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_cat[qid_to_cat.get(r["query_id"], "unknown")].append(r)
    out: Dict[str, Any] = {}
    for cat in sorted(by_cat):
        cat_rows = by_cat[cat]
        out[cat] = {
            "n":     len(cat_rows),
            "R@5":   round(mean(_recall_at_k(r["retrieved"], r["gold"], 5)
                                for r in cat_rows), 6),
            "R@10":  round(mean(_recall_at_k(r["retrieved"], r["gold"], 10)
                                for r in cat_rows), 6),
            "P@5":   round(mean(_precision_at_k(r["retrieved"], r["gold"], 5)
                                for r in cat_rows), 6),
            "P@10":  round(mean(_precision_at_k(r["retrieved"], r["gold"], 10)
                                for r in cat_rows), 6),
            "temporal_accuracy": round(mean(
                _temporal_accuracy(r["retrieved"], r["gold"], 10)
                for r in cat_rows), 6),
            "R@1":   round(mean(_recall_at_k(r["retrieved"], r["gold"], 1)
                                for r in cat_rows), 6),
        }
    return out


def run_scenario(fixture_path: Path, scenario_label: str,
                 phase: str, ts: str, out_dir: Path,
                 k: int = 10) -> Dict[str, Dict[str, Any]]:
    scenario = load_scenario(fixture_path)
    sha = fixture_sha(fixture_path)
    qid_to_cat = {q["query_id"]: q["category"] for q in scenario["queries"]}
    print(f"\n=== Scenario {scenario_label} ({scenario['scenario']}) ===")
    print(f"  fixture_sha: {sha[:16]}...")
    print(f"  docs={len(scenario['initial_corpus'])} "
          f"events={len(scenario['events'])} "
          f"queries={len(scenario['queries'])}")

    results: Dict[str, Dict[str, Any]] = {}
    for sut_name, factory in SUTS.items():
        print(f"\n  --- SUT: {sut_name} ---")
        if phase == "A":
            run = run_sut(factory, scenario, sha, sut_name=sut_name, k=k)
            axes = score_run_phase_a(run, k_recall=k)
        else:
            run = run_sut_phase_b(factory, scenario, sha,
                                  sut_name=sut_name, k=k)
            axes = score_run_phase_b(run, k_recall=k)

        rows = [{
            "query_id":      qr.query_id,
            "timestamp":     qr.timestamp,
            "gold":          qr.gold,
            "retrieved":     qr.retrieved,
            "latency_s":     qr.latency_s,
            "context_chars": qr.context_chars,
        } for qr in run.per_query]
        axes["per_category"] = per_category_breakdown(rows, qid_to_cat)

        result = {
            "benchmark":     "lrb",
            "phase":         phase,
            "scenario":      scenario["scenario"],
            "scenario_label": scenario_label,
            "spec":          scenario["spec"],
            "sut":           sut_name,
            "n_evaluations": len(rows),
            "elapsed_s":     round(run.elapsed_s, 4),
            "fixture_sha":   sha,
            "honest_tier": (
                f"Phase {phase} cross-scenario smoke; deterministic axes "
                "only (RAB H1). NOT publication. Pre-reg: "
                "docs/research/lrb-phase-b-time-travel-preregistration-"
                "2026-06-11.md"
            ),
            "axes":          axes,
            "started_at":    datetime.now(timezone.utc).isoformat(),
        }
        results[sut_name] = result

        result_path = out_dir / f"phase-b-{scenario_label.lower()}-{ts}.{sut_name}.result.json"
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8")
        bench_path = out_dir / f"phase-b-{scenario_label.lower()}-{ts}.{sut_name}.bench.jsonl"
        with bench_path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

        ov = result["axes"]["overall"]
        ex = ov["exploratory"]
        print(f"    R@5={ov['R@5']}  R@10={ov['R@10']}  "
              f"temporal_acc={ov['temporal_accuracy']}  "
              f"R@1={ex['R@1']}")
        print(f"    wrote: {result_path.name}")
    return results


def gap_table_print(scn_results: Dict[str, Dict[str, Any]],
                    label: str) -> None:
    """Print 3-SUT × axis gap table for one scenario."""
    print(f"\n=== GAP TABLE -- {label} ===")
    v = scn_results["vanilla"]["axes"]["overall"]
    n = scn_results["naive-supersede"]["axes"]["overall"]
    j = scn_results["james"]["axes"]["overall"]
    rows = [("Axis", "Vanilla", "Naive", "JAMES",
             "d(N-V)", "d(J-N)", "d(J-V)")]
    for axis in ["R@5", "R@10", "P@5", "P@10",
                 "temporal_accuracy",
                 "latency_s_mean", "token_cost_mean"]:
        rows.append((axis, f"{v[axis]:.4f}", f"{n[axis]:.4f}",
                     f"{j[axis]:.4f}",
                     f"{n[axis] - v[axis]:+.4f}",
                     f"{j[axis] - n[axis]:+.4f}",
                     f"{j[axis] - v[axis]:+.4f}"))
    for axis in ["R@1", "P@1", "temporal_accuracy_strict_top1"]:
        va = v["exploratory"][axis]
        na = n["exploratory"][axis]
        ja = j["exploratory"][axis]
        rows.append((f"[exp] {axis}", f"{va:.4f}", f"{na:.4f}",
                     f"{ja:.4f}",
                     f"{na - va:+.4f}",
                     f"{ja - na:+.4f}",
                     f"{ja - va:+.4f}"))
    col = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for r in rows:
        print("  " + "  ".join(r[i].ljust(col[i]) for i in range(len(r))))


def per_category_compare(scn_results: Dict[str, Dict[str, Any]],
                         label: str) -> None:
    print(f"\n=== PER-CATEGORY R@10 (3-SUT) -- {label} ===")
    cats = sorted(set(
        list(scn_results["vanilla"]["axes"]["per_category"]) +
        list(scn_results["james"]["axes"]["per_category"])
    ))
    rows = [("Category", "Vanilla", "Naive", "JAMES",
             "d(J-N)", "d(J-V)")]
    for cat in cats:
        v_c = scn_results["vanilla"]["axes"]["per_category"].get(
            cat, {}).get("R@10", 0.0)
        n_c = scn_results["naive-supersede"]["axes"]["per_category"].get(
            cat, {}).get("R@10", 0.0)
        j_c = scn_results["james"]["axes"]["per_category"].get(
            cat, {}).get("R@10", 0.0)
        rows.append((cat, f"{v_c:.4f}", f"{n_c:.4f}", f"{j_c:.4f}",
                     f"{j_c - n_c:+.4f}", f"{j_c - v_c:+.4f}"))
    col = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    for r in rows:
        print("  " + "  ".join(r[i].ljust(col[i]) for i in range(len(r))))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LRB Phase B cross-scenario runner")
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--scenarios", default="S1,S2")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    ts = utc_stamp()

    cross: Dict[str, Dict[str, Dict[str, Any]]] = {}

    if "S1" in args.scenarios:
        s1 = run_scenario(FIXTURE_S1, "S1", phase="A", ts=ts,
                          out_dir=args.out_dir, k=args.k)
        cross["S1"] = s1
        gap_table_print(s1, "S1 (Phase A -- current-only)")
        per_category_compare(s1, "S1")

    if "S2" in args.scenarios:
        s2 = run_scenario(FIXTURE_S2, "S2", phase="B", ts=ts,
                          out_dir=args.out_dir, k=args.k)
        cross["S2"] = s2
        gap_table_print(s2, "S2 (Phase B -- time-travel)")
        per_category_compare(s2, "S2")

    # Cross-scenario verdict (the publication-quality check)
    if "S1" in cross and "S2" in cross:
        print("\n=== CROSS-SCENARIO VERDICT ===")
        print("Hypothesis (per prereg §1.4):")
        print("  Phase A finding: naive-supersede ~= JAMES on S1 "
              "(current-only). Both > Vanilla.")
        print("  Phase B prediction: JAMES > naive-supersede on S2 "
              "(time-travel axes). naive > Vanilla on current axes.")

        ts_axis = "temporal_accuracy"
        s1_v = cross["S1"]["vanilla"]["axes"]["overall"][ts_axis]
        s1_n = cross["S1"]["naive-supersede"]["axes"]["overall"][ts_axis]
        s1_j = cross["S1"]["james"]["axes"]["overall"][ts_axis]
        s2_v = cross["S2"]["vanilla"]["axes"]["overall"][ts_axis]
        s2_n = cross["S2"]["naive-supersede"]["axes"]["overall"][ts_axis]
        s2_j = cross["S2"]["james"]["axes"]["overall"][ts_axis]
        print(f"\n  temporal_accuracy:")
        print(f"    S1: V={s1_v:.4f}  N={s1_n:.4f}  J={s1_j:.4f}  "
              f"(J-N={s1_j - s1_n:+.4f})")
        print(f"    S2: V={s2_v:.4f}  N={s2_n:.4f}  J={s2_j:.4f}  "
              f"(J-N={s2_j - s2_n:+.4f})")

        # Per-category S2 historical (the differentiator)
        print(f"\n  S2 historical-* categories (time-travel diff):")
        s2_cats = cross["S2"]["james"]["axes"]["per_category"]
        for cat in sorted(c for c in s2_cats if c.startswith("historical")):
            v_c = cross["S2"]["vanilla"]["axes"]["per_category"][cat]["R@10"]
            n_c = cross["S2"]["naive-supersede"]["axes"]["per_category"][cat]["R@10"]
            j_c = cross["S2"]["james"]["axes"]["per_category"][cat]["R@10"]
            print(f"    {cat:35s}  V={v_c:.4f}  N={n_c:.4f}  "
                  f"J={j_c:.4f}  (J-N={j_c - n_c:+.4f})")


if __name__ == "__main__":
    main()
