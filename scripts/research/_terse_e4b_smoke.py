"""Smoke: does gemma4:e4b emit a PARSEABLE ANSWER: line under terse mode?

Role = SMOKE (NOT verdict). Gate before any full paper-aligned
measurement. Earlier finding (build_terse_fixture.py docstring): e4b
drops reasoning under pure single-word answers. The CoT+ANSWER suffix +
the new response_style=terse (3-layer collapse) is the fresh path. If
e4b still won't emit a parseable ANSWER:, the full measurement would be
a parser confound — switch the measurement model to an
instruction-following one (qwen2.5:7b / gemma3:27b).

Checks per query: (1) terse answer length, (2) ANSWER: line present,
(3) _extract_terse_answer non-empty, (4) primary-signal match.
"""
from __future__ import annotations
import io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from core.reasoning.engine import ReasoningEngine
from eval.qvt.oracle import _extract_terse_answer, _primary_answer_match

MODEL = os.environ.get("PROOF_MODEL", "gemma4:e4b")
FIX = os.path.join(ROOT, "workspaces", "hotpot_eval", "eval",
                   "multihop_rag_terse_queries.json")


def pick(queries, n_per=2):
    by_type: dict[str, list] = {}
    for q in queries:
        by_type.setdefault(q["question_type"], []).append(q)
    out = []
    for t, qs in by_type.items():
        out.extend(qs[:n_per])
    return out


def run_one(eng, q):
    out = eng.query(q["text"], user_role="admin", response_style="terse",
                    selected_model=MODEL, mode_override="retrieval",
                    session_id="e4b-smoke")
    if isinstance(out, dict):
        ans = out.get("answer", "")
        srcs = out.get("sources") or out.get("docs") or []
        n_src = len(srcs) if isinstance(srcs, (list, tuple)) else 0
    else:
        ans, n_src = str(out), 0
    extracted = _extract_terse_answer(ans)
    gold = q.get("gold") or q.get("gold_signals") or []
    primary = gold[0] if gold else {"term": "", "aliases": []}
    match = _primary_answer_match(extracted.lower(), primary, q["question_type"])
    return ans, extracted, primary.get("term", ""), match, n_src


def main():
    d = json.loads(open(FIX, encoding="utf-8").read())
    sample = pick(d["queries"], 2)
    eng = ReasoningEngine()
    print(f"\n=== e4b terse smoke: model={MODEL} n={len(sample)} ===")
    parse_ok = match_ok = evid_ok = 0
    for i, q in enumerate(sample, 1):
        ans, ext, gold, match, n_src = run_one(eng, q)
        has_answer = "ANSWER:" in ans
        parse_ok += 1 if (has_answer and ext.strip()) else 0
        match_ok += 1 if match else 0
        evid_ok += 1 if n_src > 0 else 0
        print(f"\n[{i}] type={q['question_type']} gold={gold!r} sources={n_src}")
        print(f"    len={len(ans)} ANSWER:line={has_answer} extracted={ext[:70]!r} match={match}")
    n = len(sample)
    print(f"\n>>> evidence-retrieved: {evid_ok}/{n} (MUST be high — else wrong corpus / workspace)")
    print(f">>> ANSWER-parse rate: {parse_ok}/{n} | primary-match: {match_ok}/{n}")
    if evid_ok < n * 0.7:
        print(">>> INVALID SMOKE: evidence not retrieved — check JAMES_WORKSPACE / corpus ingest")
    else:
        print(">>> VERDICT:", "e4b terse VIABLE — proceed to full measurement"
              if parse_ok >= n * 0.7 else
              "e4b terse NOT viable — switch model (qwen2.5:7b / gemma3:27b)")


if __name__ == "__main__":
    main()
