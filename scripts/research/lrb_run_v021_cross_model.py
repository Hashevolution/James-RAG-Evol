"""LRB v0.2.1 cross-model runner.

Per prereg `docs/research/lrb-v021-cross-model-preregistration-
2026-06-11.md`: 48 cells = 2 scenario × 3 SUT × 4 model × 2 mode.

Phase A finding (S1: naive ≈ JAMES) + Phase B finding (S2 time-travel:
J > N) must reproduce in token mode (deterministic baseline). LLM-mode
adds cross-model gap structure validation.

Usage:
  # Token-mode only smoke (no LLM needed)
  PYTHONPATH=. python scripts/research/lrb_run_v021_cross_model.py \
    --modes token --models token-baseline

  # Full sweep (operator-attended; Ollama + claude wiring needed)
  PYTHONPATH=. python scripts/research/lrb_run_v021_cross_model.py \
    --modes token,llm-grounded \
    --models gemma4:e4b,gemma3:12b,mixtral:8x7b,claude-haiku-4-5

  # Single cell
  PYTHONPATH=. python scripts/research/lrb_run_v021_cross_model.py \
    --modes llm-grounded --models gemma4:e4b --suts james --scenarios S2
"""
from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Callable, Dict, List

from eval.external.lrb.adapters import (
    JamesValidityAdapter, NaiveSupersedeAdapter, VanillaRagAdapter)
from eval.external.lrb.cross_model import retrieve_at_cross_model
from eval.external.lrb.driver import (
    fixture_sha, load_scenario, QueryResult, SutRunResult)
from eval.external.lrb.driver_phase_b import score_run as score_run_phase_b
from eval.external.lrb.driver import score_run as score_run_phase_a
from eval.external.lrb.scorer import (
    _precision_at_k, _recall_at_k, _temporal_accuracy)

ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE_S1 = ROOT / "eval" / "external" / "_fixtures" / "lrb" / \
    "scenario_S1_quarterly.json"
FIXTURE_S2 = ROOT / "eval" / "external" / "_fixtures" / "lrb" / \
    "scenario_S2_yearly_timetravel.json"
OUT_DIR = ROOT / "reports" / "external" / "lrb"

SUT_FACTORIES = {
    "vanilla":         VanillaRagAdapter,
    "naive-supersede": NaiveSupersedeAdapter,
    "james":           JamesValidityAdapter,
}


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# ──────────────────────────────────────────────────────────────────────
# Cross-model SUT runner — Phase B style (qt + vt) for S2, Phase A
# style (single t per query) for S1
# ──────────────────────────────────────────────────────────────────────


def _apply_event(adapter, ev: dict) -> None:
    op = ev["op"]
    a = ev["args"]
    w = ev["week"]
    if op == "INGEST":
        adapter.ingest(a["doc_id"], a["title"], a["text"], w)
    elif op == "UPDATE":
        adapter.update(a["doc_id"], a["title"], a["text"], w)
    elif op == "SUPERSEDE":
        adapter.supersede(a["old_doc_id"], a["new_doc_id"],
                          a["title"], a["text"], w)
    elif op == "DELETE":
        adapter.delete(a["doc_id"], w)
    else:
        raise ValueError(f"unknown op: {op}")


def run_sut_cross_model(adapter_factory: Callable,
                        scenario: dict,
                        fixture_sha_hex: str,
                        sut_name: str,
                        *,
                        mode: str,
                        model: str,
                        ollama_url: str,
                        timeout: float,
                        k: int = 10) -> SutRunResult:
    """Run one (SUT, scenario, model, mode) cell.

    Detects S1 (per-T query with implicit qt=vt) vs S2 (explicit qt+vt)
    by presence of ``query_time`` field on queries.
    """
    result = SutRunResult(sut_name=sut_name, fixture_sha=fixture_sha_hex)
    start = time.perf_counter()
    initial = scenario["initial_corpus"]
    events = scenario["events"]
    queries = scenario["queries"]

    has_qt = bool(queries) and "query_time" in queries[0]

    if has_qt:
        # S2 style — group by query_time, build fresh adapter per qt
        by_qt: Dict[int, List[dict]] = defaultdict(list)
        for q in queries:
            by_qt[q["query_time"]].append(q)
        for query_time in sorted(by_qt):
            adapter = adapter_factory()
            for doc in initial:
                adapter.ingest(doc["doc_id"], doc["title"], doc["text"], 0)
            for ev in events:
                if ev["week"] <= query_time:
                    _apply_event(adapter, ev)
            for q in by_qt[query_time]:
                vt = q["valid_time"]
                _run_one_query(result, adapter, q, k, query_time, vt,
                               mode=mode, model=model,
                               ollama_url=ollama_url, timeout=timeout,
                               ts_label=f"qt={query_time}/vt={vt}",
                               week=vt)
    else:
        # S1 style — per-timestamp fresh adapter, qt = vt = T
        timestamps = []
        for ts in scenario["timestamps"]:
            t = ts.replace("T=", "").replace("w", "")
            timestamps.append(int(t))
        for t_week in timestamps:
            adapter = adapter_factory()
            for doc in initial:
                adapter.ingest(doc["doc_id"], doc["title"], doc["text"], 0)
            for ev in events:
                if ev["week"] <= t_week:
                    _apply_event(adapter, ev)
            ts_label = f"T={t_week}w" if t_week > 0 else "T=0"
            for q in queries:
                gold = q["gold"][ts_label]
                _run_one_query(result, adapter, q, k, t_week, t_week,
                               mode=mode, model=model,
                               ollama_url=ollama_url, timeout=timeout,
                               ts_label=ts_label, week=t_week,
                               gold_override=gold)

    result.elapsed_s = time.perf_counter() - start
    return result


def _run_one_query(result: SutRunResult, adapter, q: dict, k: int,
                   query_time: int, valid_time: int, *,
                   mode: str, model: str,
                   ollama_url: str, timeout: float,
                   ts_label: str, week: int,
                   gold_override=None) -> None:
    gold = gold_override if gold_override is not None else q["gold"]
    t0 = time.perf_counter()
    retrieved = retrieve_at_cross_model(
        adapter, q["q"], k=k,
        query_time=query_time, valid_time=valid_time,
        mode=mode, model=model,
        ollama_url=ollama_url, timeout=timeout)
    lat = time.perf_counter() - t0
    chars = adapter.retrieved_text_length(retrieved)
    result.per_query.append(QueryResult(
        query_id=q["query_id"],
        timestamp=ts_label,
        week=week,
        gold=gold,
        retrieved=retrieved,
        latency_s=lat,
        context_chars=chars,
    ))


# ──────────────────────────────────────────────────────────────────────
# Per-category breakdown
# ──────────────────────────────────────────────────────────────────────


def per_category_breakdown(rows: List[Dict[str, Any]],
                           qid_to_cat: Dict[str, str]) -> Dict[str, Any]:
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


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────


def run_cell(scenario_label: str, sut_name: str, model: str, mode: str,
             ts: str, out_dir: Path, k: int, ollama_url: str,
             timeout: float) -> Dict[str, Any]:
    fixture_path = FIXTURE_S1 if scenario_label == "S1" else FIXTURE_S2
    scenario = load_scenario(fixture_path)
    sha = fixture_sha(fixture_path)
    qid_to_cat = {q["query_id"]: q["category"]
                  for q in scenario["queries"]}

    print(f"  cell: scenario={scenario_label} sut={sut_name} "
          f"model={model} mode={mode}")
    factory = SUT_FACTORIES[sut_name]
    run = run_sut_cross_model(factory, scenario, sha, sut_name=sut_name,
                              mode=mode, model=model,
                              ollama_url=ollama_url, timeout=timeout,
                              k=k)
    has_qt = bool(scenario["queries"]) and \
        "query_time" in scenario["queries"][0]
    axes = score_run_phase_b(run, k_recall=k) if has_qt \
        else score_run_phase_a(run, k_recall=k)
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
        "version":       "v0.2.1",
        "scenario":      scenario_label,
        "scenario_spec": scenario["spec"],
        "sut":           sut_name,
        "model":         model,
        "mode":          mode,
        "n_evaluations": len(rows),
        "elapsed_s":     round(run.elapsed_s, 4),
        "fixture_sha":   sha,
        "honest_tier": (
            "v0.2.1 cross-model cell; deterministic scoring (RAB H1). "
            "NOT publication. Pre-reg: docs/research/lrb-v021-"
            "cross-model-preregistration-2026-06-11.md"
        ),
        "axes":          axes,
        "started_at":    datetime.now(timezone.utc).isoformat(),
    }

    cell_label = f"v021-{scenario_label.lower()}-{model.replace(':', '-').replace('/', '-')}-{mode}"
    result_path = out_dir / f"{cell_label}-{ts}.{sut_name}.result.json"
    result_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8")
    bench_path = out_dir / f"{cell_label}-{ts}.{sut_name}.bench.jsonl"
    with bench_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    ov = result["axes"]["overall"]
    ex = ov["exploratory"]
    print(f"    R@10={ov['R@10']}  temporal_acc={ov['temporal_accuracy']}  "
          f"R@1={ex['R@1']}  elapsed={result['elapsed_s']}s")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LRB v0.2.1 cross-model runner")
    parser.add_argument("--scenarios", default="S1,S2",
                        help="comma-separated: S1,S2")
    parser.add_argument("--suts", default="vanilla,naive-supersede,james",
                        help="comma-separated SUT names")
    parser.add_argument("--models", default="token-baseline",
                        help="comma-separated model names (token-baseline "
                        "is a synonym for any model in token mode)")
    parser.add_argument("--modes", default="token",
                        help="comma-separated: token,llm-grounded")
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    ts = utc_stamp()

    scenarios = [s.strip() for s in args.scenarios.split(",") if s.strip()]
    suts = [s.strip() for s in args.suts.split(",") if s.strip()]
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]

    cells: List[Dict[str, Any]] = []
    print(f"\n=== LRB v0.2.1 cross-model sweep "
          f"({len(scenarios)}×{len(suts)}×{len(models)}×{len(modes)} cells) ===")
    for scn in scenarios:
        print(f"\nScenario {scn}:")
        for mode in modes:
            for model in models:
                # In token mode the LLM model is irrelevant — collapse
                # to single 'token-baseline' label to avoid redundant
                # work.
                effective_model = ("token-baseline"
                                   if mode == "token" else model)
                # Skip duplicate token cells across models
                seen_key = (scn, "_token_only_"
                            if mode == "token" else model, mode)
                if mode == "token" and any(
                        c["model"] == "token-baseline" and
                        c["scenario"] == scn and c["mode"] == "token"
                        for c in cells):
                    continue
                for sut in suts:
                    cell = run_cell(scn, sut, effective_model, mode,
                                    ts, args.out_dir, args.k,
                                    args.ollama_url, args.timeout)
                    cells.append(cell)

    # Token-mode reproduction check vs Phase B baseline
    print("\n=== TOKEN-MODE REPRODUCTION (vs Phase B baseline) ===")
    print("Expected: R@1 / R@10 / temporal_acc reproduce Phase B "
          "exactly (deterministic).")
    print("  S1 baseline: V=0.617/0.894/0.894  N=J=0.739/0.917/0.917")
    print("  S2 baseline: V=0.225/0.950/0.950  N=0.538/0.750/0.750  "
          "J=0.713/0.975/0.975")
    for cell in cells:
        if cell["mode"] != "token":
            continue
        ov = cell["axes"]["overall"]
        ex = ov["exploratory"]
        print(f"  {cell['scenario']} {cell['sut']:15s} "
              f"R@1={ex['R@1']}  R@10={ov['R@10']}  "
              f"temporal_acc={ov['temporal_accuracy']}")


if __name__ == "__main__":
    main()
