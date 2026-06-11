"""Build a terse-answer variant of a multihop_rag fixture.

The base fixture's queries elicit JAMES's natural verbose grounded
answers ("Source files: ... [analysis]"). The MultiHop-RAG paper metric
expects single-word answers (entity / yes-no). To compare like-for-like
we append a terse instruction suffix so JAMES emits a paper-shaped
short answer — a measurement-only transform (production answer style is
unchanged; this fixture exists solely for benchmark comparison).

The output fixture is gitignored (workspaces/*/eval/), so this script
is the reproducible source.

Usage:
  python scripts/research/build_terse_fixture.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

SRC = ROOT / "workspaces" / "hotpot_eval" / "eval" / "multihop_rag_queries.json"
DST = ROOT / "workspaces" / "hotpot_eval" / "eval" / "multihop_rag_terse_queries.json"

# Terse instruction — CoT-preserving variant.
#
# Pure "answer with only Yes/No" suppresses small-model chain-of-thought
# (gemma4:e4b drops reasoning → wrong, observed in the comparison smoke:
# 3/3 'No' on Yes-gold). The paper's large models reason internally even
# under single-word answers; a small model needs the reasoning step kept.
# So we ALLOW reasoning and require the canonical answer on a final
# ANSWER: line — the oracle extracts that line (reasoning preserved +
# paper-shaped single answer extractable). Covers all 4 types
# (inference→entity, comparison/temporal→yes-no, null→insufficient).
SUFFIX = (
    " /// Reason through the evidence, THEN on the LAST line write"
    " 'ANSWER:' followed by ONLY the direct answer — the entity name,"
    " or 'Yes' / 'No'. If the context lacks the answer, write"
    " 'ANSWER: insufficient information'."
)


def main() -> int:
    src = json.loads(SRC.read_text(encoding="utf-8"))
    out = {"version": "multihop-rag-terse-v1", "queries": []}
    for q in src["queries"]:
        qq = dict(q)
        qq["text"] = q["text"] + SUFFIX
        out["queries"].append(qq)
    DST.write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    from collections import Counter
    types = Counter(q["question_type"] for q in out["queries"])
    print(f"wrote {DST.relative_to(ROOT)} — {len(out['queries'])} queries")
    print(f"types: {dict(types)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
