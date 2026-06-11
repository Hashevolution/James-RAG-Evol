"""LRB v0.2.4 HR smoke runner — end-to-end pipeline validation.

Generates answers from an LRB SUT + scores HR with RoBERTa-MNLI +
cross-checks with DeBERTa-v3.

Usage:
  # Quick smoke (5 queries × james × gemma4:e4b, RoBERTa only — ~3min)
  PYTHONPATH=. python scripts/research/lrb_v024_hr_smoke.py \
    --n 5 --sut james --model gemma4:e4b

  # Cross-NLI smoke (5 queries × james × gemma4:e4b × both verifiers)
  PYTHONPATH=. python scripts/research/lrb_v024_hr_smoke.py \
    --n 5 --sut james --model gemma4:e4b --verifiers roberta,deberta

  # 3-SUT comparison (5 queries × {vanilla, naive, james} × gemma4)
  PYTHONPATH=. python scripts/research/lrb_v024_hr_smoke.py \
    --n 5 --sut all --model gemma4:e4b

Outputs:
  * stdout summary (HR per cell + cross-NLI agreement)
  * reports/external/lrb/v024-hr-smoke-<ts>.<sut>-<model>-<nli>.result.json
  * .bench.jsonl per cell (per-query answer / claims / NLI labels)
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from eval.external.lrb.adapters import (
    JamesValidityAdapter, NaiveSupersedeAdapter, VanillaRagAdapter)
from eval.external.lrb.answer_gen import answer_from_adapter
from eval.external.lrb.driver import load_scenario
from eval.external.lrb.hr_scorer import aggregate_to_axes, score_hr
from eval.external.lrb.nli_verifier import get_verifier

ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE_S1 = ROOT / "eval" / "external" / "_fixtures" / "lrb" / \
    "scenario_S1_quarterly.json"
OUT_DIR = ROOT / "reports" / "external" / "lrb"

SUT_FACTORIES = {
    "vanilla":         VanillaRagAdapter,
    "naive-supersede": NaiveSupersedeAdapter,
    "james":           JamesValidityAdapter,
}


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


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


def build_adapter_at(sut_name: str, scenario: dict, t_week: int):
    factory = SUT_FACTORIES[sut_name]
    adapter = factory()
    for doc in scenario["initial_corpus"]:
        adapter.ingest(doc["doc_id"], doc["title"], doc["text"], 0)
    for ev in scenario["events"]:
        if ev["week"] <= t_week:
            _apply_event(adapter, ev)
    return adapter


def generate_answers(scenario: dict, sut_name: str, model: str,
                      n: int, *, k: int = 5, t_week: int = 12,
                      ollama_url: str = "http://localhost:11434",
                      timeout: float = 60.0) -> List[Dict[str, Any]]:
    """Pick first n queries, generate answers at the final timestamp."""
    adapter = build_adapter_at(sut_name, scenario, t_week)
    queries = scenario["queries"][:n]
    ts_label = f"T={t_week}w"
    out: List[Dict[str, Any]] = []
    for q in queries:
        question = q["q"]
        result, retrieved = answer_from_adapter(
            adapter, question, k=k,
            query_time=t_week, valid_time=t_week,
            model=model, ollama_url=ollama_url, timeout=timeout)
        ctx_parts = []
        for doc_id in retrieved:
            rec = adapter.get_doc(doc_id)
            if rec is None:
                continue
            title, text = rec
            ctx_parts.append(f"[{title}] {text[:600]}")
        out.append({
            "query_id":          q["query_id"],
            "query":             question,
            "retrieved":         retrieved,
            "retrieved_context": "\n".join(ctx_parts),
            "answer":            result.answer,
            "gen_elapsed_s":     result.elapsed_s,
            "gen_error":         result.error,
            "gold":              q["gold"][ts_label],
            "category":          q.get("category", ""),
        })
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="LRB v0.2.4 HR smoke runner")
    parser.add_argument("--n", type=int, default=5)
    parser.add_argument("--sut", default="james",
                        choices=list(SUT_FACTORIES) + ["all"])
    parser.add_argument("--model", default="gemma4:e4b")
    parser.add_argument("--t-week", type=int, default=12)
    parser.add_argument("--verifiers", default="roberta-mnli")
    parser.add_argument("--ollama-url",
                        default="http://localhost:11434")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    ts = utc_stamp()

    scenario = load_scenario(FIXTURE_S1)
    suts = list(SUT_FACTORIES) if args.sut == "all" else [args.sut]
    verifiers = [v.strip() for v in args.verifiers.split(",")
                  if v.strip()]

    # 1. Generate answers per SUT
    print(f"\n=== ANSWER GENERATION ({args.model}, n={args.n}, "
          f"T={args.t_week}w) ===")
    answers_by_sut: Dict[str, List[Dict[str, Any]]] = {}
    for sut in suts:
        print(f"\n  SUT: {sut}")
        answers = generate_answers(
            scenario, sut, args.model, args.n,
            t_week=args.t_week,
            ollama_url=args.ollama_url, timeout=args.timeout)
        ok = sum(1 for a in answers if a["answer"])
        avg_lat = (sum(a["gen_elapsed_s"] for a in answers)
                    / max(len(answers), 1))
        print(f"    {ok}/{len(answers)} non-empty; "
              f"avg gen latency = {avg_lat:.1f}s")
        answers_by_sut[sut] = answers

    # 2. Score HR per SUT × verifier
    print(f"\n=== HR SCORING ({', '.join(verifiers)}) ===")
    for verifier_name in verifiers:
        print(f"\n  Verifier: {verifier_name}")
        verifier = get_verifier(verifier_name)
        for sut in suts:
            queries_for_hr = [{
                "query_id":          a["query_id"],
                "query":             a["query"],
                "retrieved_context": a["retrieved_context"],
                "answer":            a["answer"],
            } for a in answers_by_sut[sut]]
            hr_result = score_hr(queries=queries_for_hr,
                                  verifier=verifier)
            axes = aggregate_to_axes(hr_result)
            print(f"    {sut:15s}  HR={axes['HR_mean']:.4f}  "
                  f"claims={axes['n_claims_total']}  "
                  f"entailed={axes['n_entailed']}  "
                  f"empty={axes['n_empty_answers']}")

            cell_label = f"v024-hr-smoke-{ts}.{sut}-{args.model.replace(':', '-')}-{verifier_name}"
            result = {
                "benchmark":     "lrb-v024-hr-smoke",
                "scenario":      "S1",
                "sut":           sut,
                "model":         args.model,
                "nli_verifier":  verifier_name,
                "n_queries":     args.n,
                "t_week":        args.t_week,
                "honest_tier":   (
                    "v0.2.4 HR smoke (n=<=20). Validates end-to-end "
                    "pipeline (answer gen + claim extract + NLI). NOT "
                    "publication. Cross-NLI agreement check requires "
                    "running both verifiers."
                ),
                "axes":          axes,
                "started_at":    datetime.now(timezone.utc).isoformat(),
            }
            result_path = args.out_dir / f"{cell_label}.result.json"
            result_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8")
            bench_path = args.out_dir / f"{cell_label}.bench.jsonl"
            with bench_path.open("w", encoding="utf-8") as f:
                for q, a in zip(queries_for_hr,
                                  answers_by_sut[sut]):
                    row = dict(a)
                    # also persist gold for traceability
                    row["nli_per_claim"] = [
                        {"label": r.label.value,
                         "ent":   round(r.score_entailment, 4),
                         "neu":   round(r.score_neutral, 4),
                         "con":   round(r.score_contradiction, 4)}
                        for r in next(
                            (p.nli_results
                             for p in hr_result.per_query
                             if p.query_id == q["query_id"]),
                            [])
                    ]
                    row["claims"] = next(
                        (p.claims for p in hr_result.per_query
                         if p.query_id == q["query_id"]), [])
                    row["hr_score"] = next(
                        (p.hr_score for p in hr_result.per_query
                         if p.query_id == q["query_id"]), 0.0)
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
