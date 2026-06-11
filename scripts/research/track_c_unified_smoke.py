"""Track C unified smoke runner — TimeQA + TempReason + MuSiQue.

Single CLI that dispatches to the right bench loader/scorer based on
``--bench``. Per Track C C0 §1 bench selection lock:
  * TimeQA      (primary, temporal reasoning)
  * TempReason  (secondary, multi-hop + temporal)
  * MuSiQue     (tertiary, generic multi-hop re-run)

Operator-action probe: TimeQA / TempReason require data download
(`is_available()` check). MuSiQue is already in the repo. If a bench's
fixture is missing, the runner reports the operator action needed and
exits cleanly (no crash, no partial output).

Usage:
  # MuSiQue smoke (no operator action needed)
  PYTHONPATH=. python scripts/research/track_c_unified_smoke.py \
    --bench musique --n 20 --sut all --model gemma3:12b

  # TimeQA smoke (operator: drop data into _fixtures/timeqa/easy/dev.jsonl)
  PYTHONPATH=. python scripts/research/track_c_unified_smoke.py \
    --bench timeqa --n 20 --sut all --model gemma3:12b

  # TempReason smoke (operator: drop data into _fixtures/tempreason/)
  PYTHONPATH=. python scripts/research/track_c_unified_smoke.py \
    --bench tempreason --n 30 --sut all --model gemma3:12b
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Callable, Dict, List, Tuple

from eval.external.lrb.adapters import (
    JamesValidityAdapter, NaiveSupersedeAdapter, VanillaRagAdapter)
from eval.external.lrb.answer_f1 import score_answer_f1
from eval.external.lrb.answer_gen import generate_answer
from eval.external.lrb import (
    tempreason_loader, timeqa_loader)

ROOT = Path(__file__).resolve().parent.parent.parent
MUSIQUE_FIXTURE = ROOT / "eval" / "external" / "_fixtures" / "musique" / \
    "musique_ans_v1.0_dev.jsonl"
OUT_DIR = ROOT / "reports" / "external"

SUT_FACTORIES = {
    "vanilla":         VanillaRagAdapter,
    "naive-supersede": NaiveSupersedeAdapter,
    "james":           JamesValidityAdapter,
}


# ──────────────────────────────────────────────────────────────────────
# Bench loaders → unified Track C row shape
# ──────────────────────────────────────────────────────────────────────


def load_timeqa(n: int) -> Tuple[List[Dict[str, Any]], str]:
    """Returns (rows, error_msg). rows empty + non-empty error_msg if
    fixture missing."""
    if not timeqa_loader.is_available("easy", "dev"):
        return [], (f"TimeQA fixture missing at "
                     f"{timeqa_loader.fixture_path('easy', 'dev')}. "
                     "Operator action: download from "
                     "https://github.com/wenhuchen/Time-Sensitive-QA "
                     "+ license confirmation + drop into "
                     "eval/external/_fixtures/timeqa/easy/dev.jsonl")
    rows = timeqa_loader.load_smoke(n=n, difficulty="easy", split="dev")
    return rows, ""


def load_tempreason(n: int) -> Tuple[List[Dict[str, Any]], str]:
    if not tempreason_loader.all_levels_available("val"):
        return [], (f"TempReason fixture missing in "
                     f"{tempreason_loader.DEFAULT_FIXTURE_DIR}. "
                     "Operator action: download from "
                     "https://github.com/DAMO-NLP-SG/TempReason "
                     "+ license confirmation + drop l1/l2/l3 _val.json "
                     "into eval/external/_fixtures/tempreason/")
    rows = tempreason_loader.load_smoke_balanced(n=n, split="val")
    return rows, ""


def load_musique(n: int) -> Tuple[List[Dict[str, Any]], str]:
    """MuSiQue's row shape is more nested (20-paragraph corpus per Q).
    Normalize to the Track C unified shape used by the unified runner:
    each row carries the full 20-paragraph corpus as `paragraphs` so
    the runner ingests them per-query into the SUT."""
    if not MUSIQUE_FIXTURE.exists():
        return [], (f"MuSiQue fixture missing at {MUSIQUE_FIXTURE}.")
    rows: List[Dict[str, Any]] = []
    with MUSIQUE_FIXTURE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            rows.append({
                "query_id":   r["id"],
                "question":   r["question"],
                "paragraphs": r["paragraphs"],
                "gold":       r.get("answer", ""),
                "answer_aliases": r.get("answer_aliases", []),
                "answerable": r.get("answerable", True),
            })
            if len(rows) >= n:
                break
    return rows, ""


BENCH_LOADERS: Dict[str, Callable[[int], Tuple[List[Dict[str, Any]], str]]] = {
    "timeqa":     load_timeqa,
    "tempreason": load_tempreason,
    "musique":    load_musique,
}


# ──────────────────────────────────────────────────────────────────────
# Pipeline (bench-agnostic given the unified row shape)
# ──────────────────────────────────────────────────────────────────────


def measure_one_cell(rows: List[Dict[str, Any]], sut_name: str,
                      model: str, *, bench: str, k: int = 5,
                      ollama_url: str = "http://localhost:11434",
                      timeout: float = 60.0) -> Dict[str, Any]:
    factory = SUT_FACTORIES[sut_name]
    per_query: List[Dict[str, Any]] = []
    for row in rows:
        adapter = factory()
        # Two bench shapes:
        #  * MuSiQue: ingest 20 paragraphs per question
        #  * TimeQA / TempReason: single context string per question
        gold_support_ids: set = set()
        if bench == "musique":
            for para in row["paragraphs"]:
                doc_id = f"musique-{row['query_id']}-p{para['idx']:02d}"
                if para.get("is_supporting"):
                    gold_support_ids.add(doc_id)
                adapter.ingest(doc_id, para["title"],
                                para["paragraph_text"], 0)
        else:
            # TimeQA / TempReason — single context as a single doc
            doc_id = f"{bench}-{row['query_id']}-ctx"
            adapter.ingest(doc_id, row.get("question", "")[:80],
                            row.get("context", ""), 0)

        retrieved = adapter.retrieve_at(
            row["question"], k=k, query_time=0, valid_time=0)
        snippets = []
        for did in retrieved:
            rec = adapter.get_doc(did)
            if rec is None:
                continue
            title, text = rec
            snippets.append((did, title, text))

        gen = generate_answer(row["question"], snippets, model=model,
                                ollama_url=ollama_url, timeout=timeout)

        # Support-fact recall only applies to MuSiQue
        if bench == "musique" and gold_support_ids:
            sr = len(gold_support_ids & set(retrieved)) / \
                len(gold_support_ids)
        else:
            sr = None

        per_query.append({
            "query_id":   row["query_id"],
            "question":   row["question"],
            "prediction": gen.answer,
            "gold":       row.get("gold", ""),
            "answer_aliases": row.get("answer_aliases", []),
            "retrieved":  retrieved,
            "support_recall": (round(sr, 4) if sr is not None
                                else None),
            "gen_elapsed_s":  gen.elapsed_s,
            "gen_error":      gen.error,
        })

    axes = score_answer_f1(per_query)
    if bench == "musique":
        srs = [r["support_recall"] for r in per_query
                if r["support_recall"] is not None]
        axes["support_recall_mean"] = (round(mean(srs), 6)
                                          if srs else None)
    axes["n_empty_pred"] = sum(1 for r in per_query
                                  if not r["prediction"].strip())
    return {"axes": axes, "per_query": per_query}


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Track C unified smoke runner")
    parser.add_argument("--bench", required=True,
                        choices=list(BENCH_LOADERS))
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--sut", default="james",
                        choices=list(SUT_FACTORIES) + ["all"])
    parser.add_argument("--model", default="gemma3:12b")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--ollama-url",
                         default="http://localhost:11434")
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--out-dir", type=Path,
                         default=OUT_DIR)
    args = parser.parse_args()

    # Bench fixture probe
    loader = BENCH_LOADERS[args.bench]
    rows, err = loader(args.n)
    if err:
        print(f"\n[track-c-{args.bench}] cannot run smoke: {err}")
        sys.exit(2)

    bench_out_dir = args.out_dir / args.bench
    bench_out_dir.mkdir(parents=True, exist_ok=True)
    ts = utc_stamp()

    print(f"\n=== Track C unified smoke ({args.bench}) ===")
    print(f"  n={len(rows)}  k={args.k}  model={args.model}")
    suts = list(SUT_FACTORIES) if args.sut == "all" else [args.sut]
    summary = []
    for sut in suts:
        print(f"\n  SUT: {sut}")
        result = measure_one_cell(rows, sut, args.model,
                                    bench=args.bench, k=args.k,
                                    ollama_url=args.ollama_url,
                                    timeout=args.timeout)
        axes = result["axes"]
        if axes.get("support_recall_mean") is not None:
            print(f"    EM={axes['EM']:.4f}  F1={axes['F1']:.4f}  "
                  f"support_recall={axes['support_recall_mean']:.4f}  "
                  f"n_empty={axes['n_empty_pred']}")
        else:
            print(f"    EM={axes['EM']:.4f}  F1={axes['F1']:.4f}  "
                  f"n_empty={axes['n_empty_pred']}")

        cell_label = f"track-c-{args.bench}-smoke-{ts}.{sut}-{args.model.replace(':', '-')}"
        out = {
            "benchmark":     f"{args.bench}-track-c-smoke",
            "sut":           sut,
            "model":         args.model,
            "k":             args.k,
            "n_queries":     len(rows),
            "honest_tier": (
                f"Track C {args.bench} smoke; deterministic axes "
                f"(EM/F1{'+support_recall' if args.bench == 'musique' else ''}, "
                "no LLM judge). NOT publication."
            ),
            "axes":          axes,
            "started_at":    datetime.now(timezone.utc).isoformat(),
        }
        result_path = bench_out_dir / f"{cell_label}.result.json"
        result_path.write_text(
            json.dumps(out, ensure_ascii=False, indent=2),
            encoding="utf-8")
        bench_path = bench_out_dir / f"{cell_label}.bench.jsonl"
        with bench_path.open("w", encoding="utf-8") as f:
            for r in result["per_query"]:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"    wrote: {result_path.name}")
        summary.append((sut, axes))

    if len(summary) > 1:
        print(f"\n=== CROSS-SUT GAP ({args.bench} smoke) ===")
        for sut, axes in summary:
            if axes.get("support_recall_mean") is not None:
                print(f"  {sut:15s}  EM={axes['EM']:.4f}  F1={axes['F1']:.4f}  "
                      f"support_recall={axes['support_recall_mean']:.4f}")
            else:
                print(f"  {sut:15s}  EM={axes['EM']:.4f}  F1={axes['F1']:.4f}")


if __name__ == "__main__":
    main()
