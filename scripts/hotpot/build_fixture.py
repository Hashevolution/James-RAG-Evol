"""Step 3 — Build the step7-compatible fixture from MultiHop-RAG raw queries.

Reads ``$JAMES_WORKSPACE/eval/multihop_rag_raw_queries.json`` (produced by
Step 2) and emits ``$JAMES_WORKSPACE/eval/multihop_rag_queries.json`` in
the same format JAMES's bench.py / QVT oracle already understand.

Field mapping per query
-----------------------
  raw.query           → fixture.text
  raw.question_type   → fixture.category + fixture.question_type
                        ('null_query' ⇒ abstention_truth='absent')
  raw.answer          → fixture.gold_signals[0].term
  evidence.fact[0..1] → fixture.gold_signals[1].term, [2].term
                        (first proper-noun-ish token from each fact)
  evidence.title      → fixture.expected_path.nodes (capped at 4)
  null_query          → no expected_path (no graph traversal target);
                        gold_signals = abstention indicators

Schema version: ``multihop-rag-v1``. Compatible with QVT oracle:
  - 3 gold_signals per query (step7 v5+ invariant)
  - expected_path.nodes + min_recall when applicable
  - abstention_truth ∈ {'present', 'absent'}

Subset modes (--subset):
  balanced-200   50 per question_type (200 total — α-5 default)
  balanced-100   25 per question_type (100 total — smoke / fast smoke)
  balanced-500   125 per question_type (500 total — heavier)
  full           all 2,556 (NOT recommended for α-5 — see plan §risks #4)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

SUBSETS: dict[str, int | None] = {
    "balanced-100": 25,
    "balanced-200": 50,
    "balanced-500": 125,
    "full": None,
}

EXPECTED_PATH_MAX_NODES = 4
GOLD_SIGNAL_COUNT = 3

# Tokens we ignore when picking a "key noun" from an evidence fact.
_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "of", "in", "on", "at", "to",
    "for", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "has", "have", "had", "do", "does", "did", "this",
    "that", "these", "those", "it", "its", "his", "her", "their", "our",
    "we", "they", "them", "he", "she", "you", "your", "my", "i", "me",
    "if", "then", "than", "so", "such", "not", "no", "yes", "also",
})

# Pick "noun-ish" token = starts with capital OR digits-only OR mixed-case acronym.
_NOUN_TOKEN_RE = re.compile(r"\b[A-Z][a-zA-Z0-9\-]{2,}\b|\b\d{4,}\b|\b[A-Z]{2,}\b")

ABSTENTION_SIGNALS = (
    "Insufficient",
    "cannot",
    "no information",
)


def _workspace() -> Path:
    raw = os.environ.get("JAMES_WORKSPACE", "").strip()
    if not raw:
        sys.exit(
            "[build_fixture] JAMES_WORKSPACE is not set. Export it first:\n"
            "  export JAMES_WORKSPACE=./workspaces/hotpot_eval"
        )
    ws = Path(raw).resolve()
    if not ws.exists():
        sys.exit(f"[build_fixture] workspace {ws} does not exist")
    return ws


def _pick_key_noun(fact: str, taken: set[str]) -> str:
    """Pick the first noun-ish token in ``fact`` that is not already in
    ``taken`` (case-insensitive) and not a stopword.
    """
    if not fact:
        return ""
    for m in _NOUN_TOKEN_RE.finditer(fact):
        token = m.group(0)
        if token.lower() in _STOPWORDS:
            continue
        if token.lower() in {t.lower() for t in taken}:
            continue
        return token
    # Fallback — return the first non-stopword word.
    for w in re.split(r"\s+", fact):
        w = w.strip(".,;:()'\"!?")
        if not w or w.lower() in _STOPWORDS:
            continue
        if w.lower() in {t.lower() for t in taken}:
            continue
        return w
    return ""


def _gold_signals_for(answer: str, evidence_list: list[dict]) -> list[dict]:
    """Three gold_signals per query (step7 v5+ invariant).

    - [0] = the gold answer text itself (literal claim).
    - [1] = first noun-ish token from the first evidence fact.
    - [2] = first noun-ish token from the second evidence fact (or
            source name when only one fact exists).
    """
    signals: list[dict] = []
    answer = (answer or "").strip()
    taken: set[str] = set()
    if answer:
        signals.append({"term": answer, "aliases": []})
        taken.add(answer)
    facts = [(e.get("fact") or "") for e in (evidence_list or [])]
    sources = [(e.get("source") or "") for e in (evidence_list or [])]
    for i, fact in enumerate(facts):
        if len(signals) >= GOLD_SIGNAL_COUNT:
            break
        n = _pick_key_noun(fact, taken)
        if n:
            signals.append({"term": n, "aliases": []})
            taken.add(n)
    # Pad with source names if we still need more.
    for src in sources:
        if len(signals) >= GOLD_SIGNAL_COUNT:
            break
        if src and src not in taken:
            signals.append({"term": src, "aliases": []})
            taken.add(src)
    # Final fallback — pad with the answer's first 30 chars so the
    # schema invariant (always 3 signals) holds even for sparse rows.
    while len(signals) < GOLD_SIGNAL_COUNT:
        filler = (answer[:30] + f" [pad{len(signals)}]").strip() or f"pad{len(signals)}"
        signals.append({"term": filler, "aliases": []})
    return signals[:GOLD_SIGNAL_COUNT]


def _null_gold_signals() -> list[dict]:
    """For null_query: gold = abstention phrases. Graded_answer for null
    queries measures whether the answer contains a refusal phrase; the
    abstention_f1 axis is the load-bearing one."""
    return [{"term": s, "aliases": []} for s in ABSTENTION_SIGNALS]


def _min_recall_for_evidence(n_evidence: int) -> float:
    """Tune so a perfectly-retrieving production hits 1.0 but partial
    retrieval registers ≥ 0.5 — keeps the axis non-saturating."""
    if n_evidence <= 1:
        return 1.0
    if n_evidence == 2:
        return 1.0
    if n_evidence == 3:
        return 0.67
    return 0.75


def convert(raw: dict, qid: int) -> dict:
    """Convert one raw MultiHop-RAG query into a step7-format fixture row."""
    qtype = raw.get("question_type", "unknown")
    evidence = raw.get("evidence_list") or []
    is_null = qtype == "null_query"

    out: dict = {
        "id": qid,
        "category": f"hotpot-{qtype.replace('_query', '')}",
        "question_type": qtype,    # preserve original — Step 6 cross-tab keys on this
        "text": raw.get("query", "").strip(),
        "abstention_truth": "absent" if is_null else "present",
    }

    if is_null:
        out["gold_signals"] = _null_gold_signals()
        # No expected_path — graph traversal not meaningful when corpus
        # lacks the answer.
    else:
        out["gold_signals"] = _gold_signals_for(raw.get("answer", ""), evidence)
        # expected_path.nodes from evidence titles (deduplicated, capped).
        seen: list[str] = []
        for e in evidence:
            t = (e.get("title") or "").strip()
            if t and t not in seen:
                seen.append(t)
            if len(seen) >= EXPECTED_PATH_MAX_NODES:
                break
        if seen:
            out["expected_path"] = {
                "nodes": seen,
                "min_recall": _min_recall_for_evidence(len(seen)),
            }
    return out


def _select_subset(raw_queries: list[dict], subset: str) -> list[dict]:
    cap = SUBSETS[subset]
    if cap is None:
        return raw_queries
    by_type: dict[str, list[dict]] = defaultdict(list)
    for q in raw_queries:
        by_type[q.get("question_type", "unknown")].append(q)
    selected: list[dict] = []
    for qtype, lst in by_type.items():
        # Deterministic — take first `cap` per type (no shuffle so re-runs
        # are byte-identical). Operators can re-shuffle by passing a
        # different seed via build_fixture --seed later if desired.
        selected.extend(lst[:cap])
    return selected


def main() -> int:
    ap = argparse.ArgumentParser(description="MultiHop-RAG → step7 fixture")
    ap.add_argument(
        "--subset", choices=list(SUBSETS.keys()), default="balanced-200",
        help=f"Subset selector (default balanced-200). Sizes: {SUBSETS}",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="Print plan + 1 row per type; write nothing.",
    )
    args = ap.parse_args()

    ws = _workspace()
    raw_path = ws / "eval" / "multihop_rag_raw_queries.json"
    out_path = ws / "eval" / "multihop_rag_queries.json"
    if not raw_path.exists():
        sys.exit(
            f"[build_fixture] raw queries not found: {raw_path}\n"
            "Run scripts/hotpot/download_multihop_rag.py first."
        )

    print(f"[build_fixture] reading {raw_path.name}…")
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    raw_queries = raw.get("queries", [])
    print(f"  → {len(raw_queries)} raw queries")

    selected_raw = _select_subset(raw_queries, args.subset)
    print(f"[build_fixture] subset={args.subset!r} → {len(selected_raw)} queries selected")
    type_dist = Counter(q.get("question_type", "?") for q in selected_raw)
    for t, n in type_dist.most_common():
        print(f"  {t}: {n}")

    fixture_queries: list[dict] = []
    for idx, raw_q in enumerate(selected_raw, start=1):
        fixture_queries.append(convert(raw_q, idx))

    if args.dry_run:
        print("\n[dry-run] one row per question_type:")
        seen_types: set[str] = set()
        for q in fixture_queries:
            if q["question_type"] in seen_types:
                continue
            seen_types.add(q["question_type"])
            print(json.dumps(q, ensure_ascii=False, indent=2))
            print()
            if len(seen_types) >= 4:
                break
        return 0

    # Build the final fixture JSON in step7's schema shape so the
    # existing oracle / schema tests recognise it.
    fixture_payload = {
        "version": "multihop-rag-v1",
        "description": (
            "MultiHop-RAG (Tang & Yang 2024, EMNLP) — α-5 external "
            "benchmark fixture. Each query carries 3 gold_signals + "
            "optional expected_path + abstention_truth. question_type "
            "is preserved as fixture field so the α-5 ablation runner "
            "can cross-tab per type. See plan: "
            "~/.claude/plans/quiet-hugging-iverson.md."
        ),
        "source_dataset": raw.get("dataset_id"),
        "source_license": raw.get("license"),
        "source_citation": raw.get("citation"),
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "subset": args.subset,
        "type_distribution": dict(type_dist),
        "queries": fixture_queries,
    }
    out_path.write_text(
        json.dumps(fixture_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n[build_fixture] wrote {out_path.relative_to(ws.parent.parent) if (ws.parent.parent / 'README.md').exists() else out_path}")
    print(
        f"\n[done] Step 3 complete ({len(fixture_queries)} queries). Next:\n"
        f"  python scripts/bench.py --suite=multihop_rag --dry-run  # Step 4 smoke"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
