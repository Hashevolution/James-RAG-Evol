"""Cycle γ Phase C.2 — oracle-retrieval diagnostic.

Splits "JAMES retrieval is the bottleneck" from "model multi-hop
ceiling". Feeds each MuSiQue-ans 2-hop query ONLY its gold supporting
paragraphs (perfect evidence, no distractors, retrieval fully
bypassed) straight to the model and scores em/f1 + abstention.

Interpretation (vs JAMES R0 floor em=0 / abstain ~76-80%):
  - oracle SOLVES (em/f1 up, abstain down)  => retrieval is the
    bottleneck; the model can do the 2-hop once it has the evidence
    => D1 retrieval pivot is justified.
  - oracle ALSO floors                       => model multi-hop
    ceiling; D1 won't help, the gap is the LLM.

Rule basis: feedback_evidence_grounded_validity_check (separate
"evidence delivered" from "model capability"). Reads only; no
production mutation.

Usage:
    PYTHONIOENCODING=utf-8 python scripts/research/_phase_c2_oracle_diag.py \
        --model mixtral:8x7b --n 25 \
        --out reports/cycle_gamma/phase-c2/musique-ans-mxtral-ORACLE.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="_phase_c2_oracle_diag")
    p.add_argument("--model", default="mixtral:8x7b")
    p.add_argument("--n", type=int, default=25)
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)

    from eval.external.musique_loader import MuSiQueLoader
    from eval.external.musique_scorer import MuSiQueScorer
    from core.gemma_client import GemmaClient

    loader = MuSiQueLoader(variant="ans", split="dev",
                            cache_dir=ROOT / "eval" / "external"
                                     / "_fixtures" / "musique")
    queries = loader.iter_queries(n_samples=args.n)

    # Lift the prompt cap so multi-paragraph evidence is not truncated.
    os.environ["JAMES_GEMMA_MAX_PROMPT_CHARS"] = "200000"
    client = GemmaClient()

    rows = []
    t0 = time.time()
    for i, q in enumerate(queries, 1):
        support = set(q.metadata.get("support_idx_set") or [])
        pidx = q.metadata.get("paragraph_idx") or list(range(len(q.context)))
        oracle_ctx = [q.context[j] for j, idx in enumerate(pidx)
                      if idx in support and j < len(q.context)]
        ctx = "\n\n".join(oracle_ctx)
        prompt = (
            "Answer the question using only the provided context. "
            "If the context is insufficient, answer "
            "'Insufficient Information'.\n\n"
            f"Context:\n{ctx}\n\n"
            f"Question: {q.question}\n"
        )
        ans = client.call_gemma(
            prompt, model=args.model, max_tokens=8192,
            think=False, use_cache=False, timeout=180,
        )
        rows.append({"id": q.id, "answer": ans,
                     "n_support_paragraphs": len(oracle_ctx)})
        if i % 5 == 0 or i == len(queries):
            print(f"  [{i}/{len(queries)}] {time.time()-t0:.0f}s", flush=True)

    scorer = MuSiQueScorer(variant="ans")
    axes = scorer.score(queries, rows)
    axes_out = {a.name: a.score for a in axes}

    abst = sum(1 for r in rows
               if "insufficient" in r["answer"].lower()
               or not r["answer"].strip())
    gold_in = sum(1 for q, r in zip(queries, rows)
                  if q.gold_answer
                  and q.gold_answer.lower() in r["answer"].lower())

    result = {
        "mode": "oracle-retrieval (supporting paragraphs only)",
        "model": args.model,
        "n": len(rows),
        "axes": axes_out,
        "abstain": abst,
        "gold_substring_in_answer": gold_in,
        "avg_support_paragraphs": round(
            sum(r["n_support_paragraphs"] for r in rows) / max(len(rows), 1), 2),
        "rows": rows,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    print()
    print("=== ORACLE-RETRIEVAL DIAGNOSTIC ===")
    print(f"  model: {args.model}  n={len(rows)}")
    print(f"  em={axes_out.get('em',0):.4f}  f1={axes_out.get('f1',0):.4f}")
    print(f"  abstain: {abst}/{len(rows)} ({abst/max(len(rows),1)*100:.0f}%)")
    print(f"  gold-substring-in-answer: {gold_in}/{len(rows)}")
    print(f"  avg support paragraphs fed: {result['avg_support_paragraphs']}")
    print(f"  saved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
