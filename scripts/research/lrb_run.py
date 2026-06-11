"""LRB Phase A runner — emit per-SUT result.json + bench.jsonl + handover.

Per prereg §4.1 the 4 obligatory artifacts:
  1. reports/external/lrb/phase-a-smoke-<ts>.result.json
  2. reports/external/lrb/phase-a-smoke-<ts>.bench.jsonl
  3. docs/handovers/v0.4-lrb-phase-a-smoke-<date>.md (written by hand
     after the run, not by this script)
  4. memory entry (written by hand)
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from eval.external.lrb.adapters import (
    JamesValidityAdapter, NaiveSupersedeAdapter, VanillaRagAdapter)
from eval.external.lrb.driver import (
    fixture_sha, load_scenario, run_sut, score_run)

ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE = ROOT / "eval" / "external" / "_fixtures" / "lrb" / \
    "scenario_S1_quarterly.json"
OUT_DIR = ROOT / "reports" / "external" / "lrb"

SUTS = {
    "vanilla":         VanillaRagAdapter,
    "naive-supersede": NaiveSupersedeAdapter,
    "james":           JamesValidityAdapter,
}


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def per_category_breakdown(rows: List[Dict[str, Any]],
                           queries_index: Dict[str, str]) -> Dict[str, Any]:
    from collections import defaultdict
    from statistics import mean
    from eval.external.lrb.scorer import (
        _precision_at_k, _recall_at_k, _temporal_accuracy)
    by_cat: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        cat = queries_index.get(r["query_id"], "unknown")
        by_cat[cat].append(r)
    out: Dict[str, Any] = {}
    for cat in sorted(by_cat):
        cat_rows = by_cat[cat]
        out[cat] = {
            "n":                 len(cat_rows),
            "R@5":               round(mean(
                _recall_at_k(r["retrieved"], r["gold"], 5)
                for r in cat_rows), 6),
            "R@10":              round(mean(
                _recall_at_k(r["retrieved"], r["gold"], 10)
                for r in cat_rows), 6),
            "P@5":               round(mean(
                _precision_at_k(r["retrieved"], r["gold"], 5)
                for r in cat_rows), 6),
            "P@10":              round(mean(
                _precision_at_k(r["retrieved"], r["gold"], 10)
                for r in cat_rows), 6),
            "temporal_accuracy": round(mean(
                _temporal_accuracy(r["retrieved"], r["gold"], 10)
                for r in cat_rows), 6),
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="LRB Phase A runner")
    parser.add_argument("--sut", choices=list(SUTS) + ["both"],
                        default="both")
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    scenario = load_scenario(FIXTURE)
    sha = fixture_sha(FIXTURE)
    qid_to_cat = {q["query_id"]: q["category"] for q in scenario["queries"]}

    suts = SUTS if args.sut == "both" else {args.sut: SUTS[args.sut]}
    ts = utc_stamp()
    all_results: Dict[str, Dict[str, Any]] = {}

    for sut_name, factory in suts.items():
        print(f"\n=== Running SUT: {sut_name} ===")
        run = run_sut(factory, scenario, sha, sut_name=sut_name, k=args.k)
        axes = score_run(run, k_recall=args.k)
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
            "benchmark":   "lrb",
            "phase":       "A",
            "scenario":    scenario["scenario"],
            "spec":        scenario["spec"],
            "sut":         sut_name,
            "n_evaluations": len(rows),
            "elapsed_s":   round(run.elapsed_s, 4),
            "fixture_sha": sha,
            "honest_tier": (
                "infrastructure-only smoke: 2-SUT Phase A; "
                "deterministic axes only (RAB H1 strict). NOT publication. "
                "Pre-reg: docs/research/lrb-phase-a-smoke-"
                "preregistration-2026-06-11.md."
            ),
            "axes":        axes,
            "started_at":  datetime.now(timezone.utc).isoformat(),
        }
        all_results[sut_name] = result

        result_path = args.out_dir / f"phase-a-smoke-{ts}.{sut_name}.result.json"
        result_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"  wrote: {result_path.relative_to(ROOT)}")

        bench_path = args.out_dir / f"phase-a-smoke-{ts}.{sut_name}.bench.jsonl"
        with bench_path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"  wrote: {bench_path.relative_to(ROOT)}")

        ov = result["axes"]["overall"]
        print(f"  R@5={ov['R@5']}  R@10={ov['R@10']}  "
              f"P@5={ov['P@5']}  P@10={ov['P@10']}")
        print(f"  temporal_accuracy={ov['temporal_accuracy']}  "
              f"latency_s_mean={ov['latency_s_mean']}  "
              f"token_cost_mean={ov['token_cost_mean']}")

    # Gap table (all SUTs)
    if "vanilla" in all_results and "james" in all_results:
        print("\n=== GAP TABLE ===")
        v = all_results["vanilla"]["axes"]["overall"]
        n = all_results.get("naive-supersede",
                            {}).get("axes", {}).get("overall", v)
        j = all_results["james"]["axes"]["overall"]
        rows_out = [("Axis", "Vanilla", "Naive-supersede",
                     "JAMES", "delta (J-V)")]
        for axis in ["R@5", "R@10", "P@5", "P@10",
                     "temporal_accuracy",
                     "latency_s_mean", "token_cost_mean"]:
            d = round(j[axis] - v[axis], 6)
            rows_out.append((axis, str(v[axis]), str(n[axis]),
                             str(j[axis]), str(d)))
        # Exploratory top-1 axes
        for axis in ["R@1", "P@1", "temporal_accuracy_strict_top1"]:
            v_a = v["exploratory"][axis]
            n_a = n.get("exploratory", v.get("exploratory"))[axis]
            j_a = j["exploratory"][axis]
            d = round(j_a - v_a, 6)
            rows_out.append(
                (f"[exploratory] {axis}", str(v_a), str(n_a),
                 str(j_a), str(d)))
        col = [max(len(r[i]) for r in rows_out)
               for i in range(len(rows_out[0]))]
        for r in rows_out:
            print("  " + "  ".join(r[i].ljust(col[i])
                                   for i in range(len(r))))

        # Per-timestamp comparison
        print("\n=== PER-TIMESTAMP (R@10) ===")
        ts_labels = [t for t in scenario["timestamps"]]
        for ts_label in ts_labels:
            v_r = all_results["vanilla"]["axes"]["per_timestamp"][ts_label]["R@10"]
            n_r = all_results.get("naive-supersede", {}).get(
                "axes", {}).get("per_timestamp", {}).get(
                ts_label, {}).get("R@10", v_r)
            j_r = all_results["james"]["axes"]["per_timestamp"][ts_label]["R@10"]
            d = round(j_r - v_r, 6)
            print(f"  {ts_label}:  V={v_r}  N={n_r}  J={j_r}  delta(J-V)={d}")

        # Per-category comparison
        print("\n=== PER-CATEGORY (R@10) ===")
        cats = sorted(set(
            list(all_results["vanilla"]["axes"]["per_category"]) +
            list(all_results["james"]["axes"]["per_category"])
        ))
        for cat in cats:
            v_c = all_results["vanilla"]["axes"]["per_category"].get(
                cat, {}).get("R@10", 0.0)
            n_c = all_results.get("naive-supersede", {}).get(
                "axes", {}).get("per_category", {}).get(
                cat, {}).get("R@10", v_c)
            j_c = all_results["james"]["axes"]["per_category"].get(
                cat, {}).get("R@10", 0.0)
            d = round(j_c - v_c, 6)
            print(f"  {cat:30s}  V={v_c}  N={n_c}  J={j_c}  d={d}")


if __name__ == "__main__":
    main()
