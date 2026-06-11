"""Track C MuSiQue smoke runner.

The first operator-action-free Track C reasoning measurement. MuSiQue
dev split is already in the repo at
``eval/external/_fixtures/musique/musique_ans_v1.0_dev.jsonl``
(2417 multi-hop questions). Each row carries 20 paragraphs (supporting
+ distractor), gold answer + aliases, and per-paragraph
``is_supporting`` flag.

Pipeline per query:
  1. Ingest all 20 paragraphs into an LRB SUT adapter (each as a
     doc_id like ``musique-<q_id>-p<idx>``)
  2. Retrieve top-k via the SUT (validity-window/append-only/naive
     supersede all behave identically here — no lifecycle events on
     a closed-book question)
  3. Generate answer with the chosen LLM
  4. Score answer F1 (SQuAD norm) against gold + aliases
  5. Compute support-fact recall (gold ``is_supporting`` ∩ retrieved)

Per Track C C0 §1.3 sample sizes:
  * Smoke n=100 (this script default)
  * Full n=1000

Per Track C C0 §3.1 scoring axes (deterministic, RAB H1):
  * Token F1 + EM (`answer_f1.score_answer_f1`)
  * Support-fact recall (per-row)

Usage:
  PYTHONPATH=. python scripts/research/track_c_musique_smoke.py \
    --n 20 --sut james --model gemma3:12b

  # All 3 SUT (vanilla / naive / james) × 1 model
  PYTHONPATH=. python scripts/research/track_c_musique_smoke.py \
    --n 20 --sut all --model gemma3:12b
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List

from eval.external.lrb.adapters import (
    JamesValidityAdapter, NaiveSupersedeAdapter, VanillaRagAdapter)
from eval.external.lrb.answer_f1 import score_answer_f1
from eval.external.lrb.answer_gen import generate_answer

ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURE = ROOT / "eval" / "external" / "_fixtures" / "musique" / \
    "musique_ans_v1.0_dev.jsonl"
OUT_DIR = ROOT / "reports" / "external" / "musique"

SUT_FACTORIES = {
    "vanilla":         VanillaRagAdapter,
    "naive-supersede": NaiveSupersedeAdapter,
    "james":           JamesValidityAdapter,
}


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_musique_dev(n: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with FIXTURE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
            if len(rows) >= n:
                break
    return rows


def measure_one_cell(rows: List[Dict[str, Any]], sut_name: str,
                      model: str, *, k: int = 5,
                      ollama_url: str = "http://localhost:11434",
                      timeout: float = 60.0) -> Dict[str, Any]:
    factory = SUT_FACTORIES[sut_name]
    per_query: List[Dict[str, Any]] = []
    for row in rows:
        adapter = factory()
        # Ingest all 20 paragraphs as documents
        idx_to_doc_id: Dict[int, str] = {}
        for para in row["paragraphs"]:
            doc_id = f"musique-{row['id']}-p{para['idx']:02d}"
            idx_to_doc_id[para["idx"]] = doc_id
            adapter.ingest(doc_id, para["title"],
                            para["paragraph_text"], 0)

        # Retrieve top-k for this question
        retrieved = adapter.retrieve_at(
            row["question"], k=k, query_time=0, valid_time=0)

        # Gather snippets for answer gen
        snippets = []
        for doc_id in retrieved:
            rec = adapter.get_doc(doc_id)
            if rec is None:
                continue
            title, text = rec
            snippets.append((doc_id, title, text))

        # Generate answer
        gen = generate_answer(row["question"], snippets, model=model,
                                ollama_url=ollama_url, timeout=timeout)

        # Support-fact recall
        gold_support = {idx_to_doc_id[p["idx"]]
                         for p in row["paragraphs"]
                         if p.get("is_supporting")}
        retrieved_set = set(retrieved)
        support_recall = (len(gold_support & retrieved_set)
                          / len(gold_support) if gold_support else 0.0)

        per_query.append({
            "query_id":   row["id"],
            "question":   row["question"],
            "prediction": gen.answer,
            "gold":       row.get("answer", ""),
            "answer_aliases": row.get("answer_aliases", []),
            "retrieved":  retrieved,
            "support_recall": round(support_recall, 4),
            "gen_elapsed_s":  gen.elapsed_s,
            "gen_error":      gen.error,
        })

    axes = score_answer_f1(per_query)
    axes["support_recall_mean"] = round(
        mean(r["support_recall"] for r in per_query), 6)
    axes["n_empty_pred"] = sum(1 for r in per_query
                                  if not r["prediction"].strip())
    return {
        "axes":      axes,
        "per_query": per_query,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Track C MuSiQue smoke runner")
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--sut", default="james",
                        choices=list(SUT_FACTORIES) + ["all"])
    parser.add_argument("--model", default="gemma3:12b")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--ollama-url",
                         default="http://localhost:11434")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    ts = utc_stamp()

    rows = load_musique_dev(args.n)
    print(f"\n=== Track C MuSiQue smoke ===")
    print(f"  fixture: {FIXTURE.name}  n={len(rows)}  k={args.k}  "
          f"model={args.model}")

    suts = list(SUT_FACTORIES) if args.sut == "all" else [args.sut]
    summary = []
    for sut in suts:
        print(f"\n  SUT: {sut}")
        result = measure_one_cell(rows, sut, args.model, k=args.k,
                                    ollama_url=args.ollama_url,
                                    timeout=args.timeout)
        axes = result["axes"]
        print(f"    EM={axes['EM']:.4f}  F1={axes['F1']:.4f}  "
              f"support_recall={axes['support_recall_mean']:.4f}  "
              f"n_empty={axes['n_empty_pred']}")

        cell_label = f"track-c-musique-smoke-{ts}.{sut}-{args.model.replace(':', '-')}"
        out = {
            "benchmark":     "musique-ans-track-c-smoke",
            "split":         "dev",
            "sut":           sut,
            "model":         args.model,
            "k":             args.k,
            "n_queries":     len(rows),
            "honest_tier":   (
                "Track C MuSiQue smoke; deterministic axes (EM/F1/"
                "support_recall, no LLM judge). n=" f"{args.n}"
                " too small for tier landing; full sweep + cross-model + "
                "cross-bench needed."
            ),
            "axes":          axes,
            "started_at":    datetime.now(timezone.utc).isoformat(),
        }
        result_path = args.out_dir / f"{cell_label}.result.json"
        result_path.write_text(
            json.dumps(out, ensure_ascii=False, indent=2),
            encoding="utf-8")
        bench_path = args.out_dir / f"{cell_label}.bench.jsonl"
        with bench_path.open("w", encoding="utf-8") as f:
            for r in result["per_query"]:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"    wrote: {result_path.name}")
        summary.append((sut, axes))

    # Cross-SUT comparison
    if len(summary) > 1:
        print(f"\n=== CROSS-SUT GAP (MuSiQue smoke) ===")
        for sut, axes in summary:
            print(f"  {sut:15s}  EM={axes['EM']:.4f}  F1={axes['F1']:.4f}  "
                  f"support_recall={axes['support_recall_mean']:.4f}")


if __name__ == "__main__":
    main()
