"""PM-1 verdict run: JAMES + local model on MultiHop-RAG terse fixture.

Direct-engine path (no HTTP server) so response_style="terse" reaches
the engine and the 2026-06-04 platform fix collapses all 3 answer-format
layers — the clean measurement the prior #709/#710 run could not get
(override was hardcoded off then).

Scores with the official eval.qvt.oracle.score_paper_aligned_accuracy
(MultiHop-RAG arXiv:2401.15391 Table 6 approximation) + per-type
cross-tab + paper baseline comparison.

Run (operator):
  JAMES_WORKSPACE=./workspaces/hotpot_eval \
  JAMES_RESPONSE_STYLE=terse JAMES_NUM_CTX=16384 \
  PROOF_MODEL=gemma4:e4b \
  python scripts/research/multihop_terse_run.py
"""
from __future__ import annotations
import io, json, os, sys, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from core.reasoning.engine import ReasoningEngine
from eval.qvt.oracle import score_paper_aligned_accuracy

MODEL = os.environ.get("PROOF_MODEL", "gemma4:e4b")
# 2026-06-04 PM-2 finding: the terse fixture appends a ~250-char ANSWER
# instruction to the query TEXT, pushing 50/100 queries over the 500-char
# security guard (core/security_layer/_detection.py) → blocked before
# retrieval → spurious sources=0 recall gap. Now that the platform fix
# makes response_style="terse" actually work, the format is handled there
# and the query text should be the CLEAN base question (all <500). Default
# to the base fixture; FIXTURE env can override.
FIX = os.environ.get("FIXTURE") or os.path.join(
    ROOT, "workspaces", "hotpot_eval", "eval", "multihop_rag_queries.json")
OUT = os.path.join(ROOT, "reports",
                   f"multihop_terse_{MODEL.replace(':', '-')}_{time.strftime('%Y%m%d_%H%M%S')}.json")

PAPER = {
    "GPT-4": 0.56, "Claude-2.1": 0.52, "PaLM": 0.47,
    "ChatGPT/3.5": 0.44, "Mixtral-8x7B": 0.32, "Llama-2-70b": 0.28,
}


def main():
    fixture = json.loads(open(FIX, encoding="utf-8").read())
    queries = fixture["queries"]
    eng = ReasoningEngine()
    results = []
    t0 = time.time()
    print(f"=== PM-1 multihop terse: model={MODEL} n={len(queries)} ===", flush=True)
    # 2026-06-05 §29 env-gate — session mode for measurement vs production-mirror.
    #   per-query (default)    — each query a fresh session_id (hist_ctx="" →
    #                            engine_memory line 164 gate skips episodic).
    #                            Episodic-isolated measurement; surfaced the
    #                            §20 critique-drift finding cleanly.
    #   fixed-shared           — all queries share one session_id; episodic
    #                            accumulates as in a real multi-turn conversation
    #                            (production fit). Use for production Default
    #                            verdict measurement (§29 mixtral retest).
    # See alpha-8 experiment log §29 for the rationale (per-query was a
    # measurement-isolation artifact; production users share sessions).
    _session_mode = (os.environ.get("JAMES_TERSE_SESSION_MODE", "per-query")
                     .strip().lower())
    _shared_session = (os.environ.get("JAMES_TERSE_SESSION_ID", "")
                       or f"pm-terse-shared-{MODEL.replace(':', '-')}")

    # 2026-06-06 cycle β #2 — env-gate for response_style measurement
    # mode. PM-19/20 = explicit "terse" (4-layer collapse manual).
    # PM-21 = empty "" so AnswerStyleClassifier auto-mount fires per
    # query — production-realistic measurement of the auto-selection
    # layer.
    #   JAMES_RUNNER_RESPONSE_STYLE=terse (default) — PM-19/20 mirror
    #   JAMES_RUNNER_RESPONSE_STYLE=auto            — empty, auto-mount
    #   JAMES_RUNNER_RESPONSE_STYLE=<any other>     — passed through
    _runner_style = os.environ.get("JAMES_RUNNER_RESPONSE_STYLE", "terse").strip()
    _eff_style = "" if _runner_style.lower() == "auto" else _runner_style

    for i, q in enumerate(queries, 1):
        try:
            session_id = (_shared_session if _session_mode == "fixed-shared"
                          else f"pm-terse-q{q['id']}")
            out = eng.query(q["text"], user_role="admin", response_style=_eff_style,
                            selected_model=MODEL, mode_override="retrieval",
                            session_id=session_id)
            ans = out.get("answer", "") if isinstance(out, dict) else str(out)
            srcs = (out.get("sources") or out.get("docs") or []) if isinstance(out, dict) else []
            n_src = len(srcs) if isinstance(srcs, (list, tuple)) else 0
            status = "ok"
        except Exception as e:
            ans, n_src, status = f"[ERROR] {e}", 0, "error"
        results.append({"id": q["id"], "status": status, "answer": ans,
                        "question_type": q["question_type"], "sources": n_src})
        if i % 10 == 0 or i == len(queries):
            json.dump({"model": MODEL, "results": results},
                      open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            el = time.time() - t0
            print(f"  [{i}/{len(queries)}] {el:.0f}s elapsed, checkpoint saved", flush=True)

    axis = score_paper_aligned_accuracy({"results": results}, fixture)
    print(f"\n=== RESULT (model={MODEL}, n={axis.n_queries}) ===")
    print(f"accuracy_primary (lenient) : {axis.accuracy_primary:.3f}  "
          f"({axis.correct_primary}/{axis.n_queries})")
    print(f"accuracy_strict            : {axis.accuracy_strict:.3f}  "
          f"({axis.correct_strict}/{axis.n_queries})")
    print(f"answerable / null          : {axis.n_answerable} / {axis.n_null}")
    print(f"evidence-retrieved         : {sum(1 for r in results if r['sources']>0)}/{len(results)} "
          f"(null queries expected 0)")
    print("\nby question_type:")
    for t, d in sorted(axis.by_question_type.items()):
        print(f"  {t:18s} primary={d['accuracy_primary']:.2f} "
              f"strict={d['accuracy_strict']:.2f}  (n={d['n']})")
    print("\nvs paper Table 6 (retrieved chunks):")
    for name, sc in PAPER.items():
        mark = "<= JAMES primary above" if axis.accuracy_primary >= sc else ""
        print(f"  {name:14s} {sc:.2f}  {mark}")
    print(f"  {'JAMES+'+MODEL:14s} {axis.accuracy_primary:.2f}  (primary) / {axis.accuracy_strict:.2f} (strict)")
    print(f"\nsaved: {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
