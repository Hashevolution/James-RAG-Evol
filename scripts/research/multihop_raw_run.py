"""RAW baseline: vanilla RAG (retrieval + single LLM call), NO JAMES
reasoning stack (no graph expansion, multi-loop, reflect/verify,
abstention softener). Pairs with multihop_terse_run.py (JAMES-full) to
isolate the JAMES pipeline's contribution on the clean paper-aligned
metric.

CRITICAL (evidence-grounded validity, see memory
feedback_evidence_grounded_validity_check): RAW is NOT closed-book. The
Stage 4b "cloud raw" run was INVALID because evidence never reached the
model → it answered from training knowledge (learning-leak). Here we
retrieve the SAME chunks JAMES would and stuff them into the prompt, so
the only difference vs JAMES-full is the reasoning stack — and we HARD-
ASSERT every query actually received evidence (sources>0) before scoring.

This matches the paper's setup (LLM + retrieved chunks), so RAW is the
apples-to-apples row next to paper Table 6.

Run:
  JAMES_WORKSPACE=./workspaces/hotpot_eval \
  JAMES_NUM_CTX=16384 PROOF_MODEL=gemma4:e4b \
  python scripts/research/multihop_raw_run.py
"""
from __future__ import annotations
import io, json, os, sys, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from core.vector_store import VectorStore
from core.gemma_client import GemmaClient
from core.response_style import TERSE_PRESET
from eval.qvt.oracle import score_paper_aligned_accuracy

MODEL = os.environ.get("PROOF_MODEL", "gemma4:e4b")
TOP_K = int(os.environ.get("RAW_TOP_K", "5"))
FIX = os.environ.get("FIXTURE") or os.path.join(
    ROOT, "workspaces", "hotpot_eval", "eval", "multihop_rag_queries.json")
# 2026-06-05 §34 — PROMPT_STYLE env-gate for Layer B framework comparison.
#   james_terse (default) — TERSE_PRESET rule_text_en + [Evidence]/[Question]
#                            sections (JAMES-style raw, terse contract)
#   paper                 — exact paper-style prompt (qa_llama.py prefix +
#                            "Question:/Context:" + '--------------' chunk
#                            separator). Used for Layer B (LlamaIndex-style
#                            baseline approximation on JAMES corpus).
PROMPT_STYLE = (os.environ.get("PROMPT_STYLE", "james_terse")
                .strip().lower())

OUT_TAG = f"raw{'_paper' if PROMPT_STYLE == 'paper' else ''}"
OUT = os.path.join(ROOT, "reports",
                   f"multihop_{OUT_TAG}_{MODEL.replace(':', '-')}_{time.strftime('%Y%m%d_%H%M%S')}.json")

PAPER = {"GPT-4": 0.56, "Claude-2.1": 0.52, "PaLM": 0.47,
         "ChatGPT/3.5": 0.44, "Mixtral-8x7B": 0.32, "Llama-2-70b": 0.28}


# Exact paper-style prompt from yixuantt/MultiHop-RAG qa_llama.py
_PAPER_PREFIX = (
    "Below is a question followed by some context from different sources. "
    "Please answer the question based on the context. "
    "The answer to the question is a word or entity. "
    "If the provided information is insufficient to answer the question, "
    "respond 'Insufficient Information'. "
    "Answer directly without explanation."
)


def build_prompt(context: str, question: str) -> str:
    if PROMPT_STYLE == "paper":
        # Exact paper format (qa_llama.py): prefix + Question + Context.
        # Context joined with '--------------' separator (paper convention).
        return (
            f"{_PAPER_PREFIX}\n\n"
            f"Question:{question}\n\n"
            f"Context:\n\n{context}"
        )
    # JAMES-style raw — same terse contract as JAMES-full.
    return (
        f"{TERSE_PRESET.rule_text_en}\n"
        f"[Evidence]\n{context}\n\n"
        f"[Question]\n{question}\n"
    )


def main():
    fixture = json.loads(open(FIX, encoding="utf-8").read())
    queries = fixture["queries"]
    vs = VectorStore()
    gc = GemmaClient()
    results = []
    no_evidence = []
    t0 = time.time()
    print(f"=== RAW (vanilla RAG, no JAMES stack): model={MODEL} "
          f"n={len(queries)} top_k={TOP_K} ===", flush=True)
    for i, q in enumerate(queries, 1):
        try:
            chunks = vs.search(q["text"], top_k=TOP_K, source_type=None)
            n_src = len(chunks)
            # paper style uses '--------------' separator (qa_llama.py),
            # james_terse style uses '\n\n'
            _sep = "--------------" if PROMPT_STYLE == "paper" else "\n\n"
            context = _sep.join(c.get("text", "") for c in chunks)
            if not context.strip():
                no_evidence.append(q["id"])
            ans = gc.call_gemma(
                build_prompt(context, q["text"]),
                model=MODEL, max_tokens=8192, think=False,
                use_cache=False, timeout=180,
            )
            status = "ok"
        except Exception as e:
            ans, n_src, status = f"[ERROR] {e}", 0, "error"
        results.append({"id": q["id"], "status": status, "answer": ans,
                        "question_type": q["question_type"], "sources": n_src})
        if i % 10 == 0 or i == len(queries):
            json.dump({"model": MODEL, "mode": "raw", "results": results},
                      open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            print(f"  [{i}/{len(queries)}] {time.time()-t0:.0f}s, checkpoint saved", flush=True)

    # ── Evidence-grounded validity guard (the Stage 4b lesson) ──
    answerable = [r for r in results if r["question_type"] != "null_query"]
    ans_no_ev = [r["id"] for r in answerable if r["sources"] == 0]
    print("\n=== VALIDITY GUARD ===")
    print(f"answerable with evidence: {len(answerable)-len(ans_no_ev)}/{len(answerable)}")
    if ans_no_ev:
        print(f"!! WARNING: {len(ans_no_ev)} answerable queries got NO evidence "
              f"(ids={ans_no_ev[:15]}) — raw scores on these = learning-leak risk, "
              f"interpret with care.")
    else:
        print("OK — every answerable query received retrieved evidence (no leak risk).")

    axis = score_paper_aligned_accuracy({"results": results}, fixture)
    print(f"\n=== RAW RESULT (model={MODEL}, n={axis.n_queries}) ===")
    print(f"accuracy_primary : {axis.accuracy_primary:.3f}  ({axis.correct_primary}/{axis.n_queries})")
    print(f"accuracy_strict  : {axis.accuracy_strict:.3f}")
    print(f"answerable / null: {axis.n_answerable} / {axis.n_null}")
    print("\nby question_type:")
    for t, d in sorted(axis.by_question_type.items()):
        print(f"  {t:18s} primary={d['accuracy_primary']:.2f} strict={d['accuracy_strict']:.2f} (n={d['n']})")
    print("\nRAW vs JAMES-full vs paper — fill from multihop_terse_run.py result")
    print(f"  {'paper-Mixtral':16s} 0.32")
    print(f"  {'RAW '+MODEL:16s} {axis.accuracy_primary:.2f} (primary)")
    print(f"\nsaved: {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
