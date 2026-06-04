"""Diagnose the PM-1 retrieval-recall gap: does the terse fixture's
~250-char ANSWER instruction suffix dilute the retrieval embedding?

Hypothesis: base query (no suffix) retrieves the gold-bearing chunk at
better rank/score than the terse query. If confirmed, the clean
measurement is base-fixture query text + response_style="terse" (format
handled by the platform fix, retrieval query kept clean).

Cheap: vector_store.search() only (embed + chroma), no LLM pipeline.
For each previously-missed answerable id, check whether any gold term
appears in the top-k retrieved chunk text under base vs terse query.
"""
from __future__ import annotations
import io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from core.vector_store import VectorStore

WS = os.path.join(ROOT, "workspaces", "hotpot_eval", "eval")
BASE = json.load(open(os.path.join(WS, "multihop_rag_queries.json"), encoding="utf-8"))
TERSE = json.load(open(os.path.join(WS, "multihop_rag_terse_queries.json"), encoding="utf-8"))
PM1 = json.load(open(os.path.join(ROOT, "reports",
                "multihop_terse_gemma4-e4b_20260604_180358.json"), encoding="utf-8"))

base_map = {q["id"]: q for q in BASE["queries"]}
terse_map = {q["id"]: q for q in TERSE["queries"]}
missed = [r["id"] for r in PM1["results"]
          if r["question_type"] != "null_query" and r["sources"] == 0]

TOP_K = 8


def gold_terms(q):
    out = []
    for s in (q.get("gold_signals") or []):
        t = s.get("term", "")
        if t and t.lower() not in ("yes", "no", "before", "after", "insufficient",
                                   "cannot", "no information"):
            out.append(t.lower())
    return out


def chunk_has_gold(query_text, terms):
    docs = vs.search(query_text, top_k=TOP_K, source_type=None)
    blob = " ".join(
        (d.get("content") or d.get("document") or d.get("text") or str(d)).lower()
        for d in docs
    )
    return any(t in blob for t in terms) if terms else False


vs = VectorStore()
base_hit = terse_hit = both = neither = scored = 0
print(f"=== recall suffix diag: {len(missed)} missed answerable ids, top_k={TOP_K} ===")
for qid in missed:
    bq, tq = base_map.get(qid), terse_map.get(qid)
    if not bq or not tq:
        continue
    terms = gold_terms(bq)
    if not terms:
        continue
    scored += 1
    b = chunk_has_gold(bq["text"], terms)
    t = chunk_has_gold(tq["text"], terms)
    base_hit += b; terse_hit += t
    both += 1 if (b and t) else 0
    neither += 1 if (not b and not t) else 0
    print(f"  id={qid:3d} base_gold={b} terse_gold={t} terms={terms[:1]}")

print(f"\n>>> scored={scored}")
print(f">>> gold-chunk retrieved — BASE: {base_hit}/{scored} | TERSE: {terse_hit}/{scored}")
print(f">>> both={both} neither={neither} (neither = corpus lacks answer / hard)")
print(">>> VERDICT:", "SUFFIX DILUTION confirmed — base recovers recall"
      if base_hit > terse_hit + 2 else
      "suffix NOT the main cause — recall miss is corpus/embedding (deeper)")
