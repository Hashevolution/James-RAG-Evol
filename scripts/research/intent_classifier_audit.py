"""F2 (LEO L.D follow-up, 2026-05-27) — IntentClassifier audit.

Measures whether the production ``core.intent_classifier.classify_intent``
agrees with the step7 suite's design-time category. Surfaces the
chat-mode passthrough pattern that L.D F1 first documented (every step7
RAG-style query gets routed to ``chat`` instead of ``retrieval``).

The audit does NOT modify the classifier. Output is a report card the
operator uses to decide whether to:
  (a) tune the LLM prompt (``IntentClassifier.CLASSIFY_PROMPT``)
  (b) extend fast-pattern rules (``IntentClassifier.FAST_PATTERNS``)
  (c) rename step7 suite categories to match what the classifier
      already does
  (d) accept the divergence and route bench-time traffic with the
      explicit ``--mode=retrieval`` flag forever (F1 workaround)

Each run produces ``reports/research-runs/intent-classifier-audit-
<stamp>.json`` with per-query rows + summary stats.

Pre-requisites
--------------
- Ollama service reachable at the configured endpoint (``OLLAMA_PATH``).
- The classifier reads ``llm.router.RouterWrapper("classify")`` so the
  ``classify`` task model is the one that gets benched; not the synth
  model. Per ``core.intent_classifier.classify_llm`` this uses
  ``LLM_OPTIONS_FAST`` (``num_predict=20``, ``ctx=512``).

Usage
-----
    python scripts/research/intent_classifier_audit.py
    python scripts/research/intent_classifier_audit.py --suite step7
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

try:
    from utils.console import ensure_utf8_console
    ensure_utf8_console()
except Exception:
    pass


REPORTS_DIR = ROOT / "reports" / "research-runs"


# ─── step7 category → expected mode mapping ──────────────────────────
#
# Mirrors the design intent of ``eval/regression/step7_queries.json``.
# Categories were named at suite design time to communicate the
# retrieval shape the query *should* exercise; they say nothing about
# what the IntentClassifier actually returns. This map is the audit's
# ground truth — divergence between this and the classifier's output
# is the chat-mode passthrough finding.
#
# ``security`` queries are routed by the pre-check security layer
# *before* the classifier runs, so they're excluded from the audit
# (the classifier never sees them in production either).
_CATEGORY_TO_EXPECTED_MODE: Dict[str, str] = {
    "retrieve":   "retrieval",
    "relation":   "retrieval",
    "multi-hop":  "retrieval",
    "compare":    "retrieval",
    "dedup":      "retrieval",
    "lang-mix":   "retrieval",
    "negative":   "retrieval",   # no-data answer is still a retrieval attempt
    "narrow":     "retrieval",
    "meta":       "meta",
}

_SKIP_CATEGORIES = {"security"}


def _load_suite(name: str) -> Dict:
    path = ROOT / "eval" / "regression" / f"{name}_queries.json"
    if not path.exists():
        raise RuntimeError(f"suite definition not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _audit_one(query: Dict) -> Dict:
    """Run one query through classify_intent + compute per-row delta."""
    from core.intent_classifier import classify_intent

    expected = _CATEGORY_TO_EXPECTED_MODE.get(query["category"])
    t0 = time.time()
    try:
        got_mode, method = classify_intent(query["text"], user_role="external")
        err = None
    except Exception as e:
        got_mode, method, err = "<error>", "error", f"{type(e).__name__}: {str(e)[:200]}"
    elapsed = time.time() - t0

    row: Dict = {
        "id":           query["id"],
        "category":     query["category"],
        "text":         query["text"],
        "expected":     expected,
        "got":          got_mode,
        "method":       method,
        "agree":        (got_mode == expected) if expected else None,
        "elapsed":      round(elapsed, 2),
    }
    if err:
        row["error"] = err
    return row


def main() -> int:
    ap = argparse.ArgumentParser(
        description="IntentClassifier audit against a regression suite.",
    )
    ap.add_argument("--suite", default="step7")
    args = ap.parse_args()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    suite = _load_suite(args.suite)
    queries = suite.get("queries", [])
    if not queries:
        print(f"[audit] no queries in suite '{args.suite}'")
        return 1

    audited = [q for q in queries if q.get("category") not in _SKIP_CATEGORIES]
    print(
        f"=== IntentClassifier audit (suite={args.suite}, "
        f"queries={len(audited)} of {len(queries)} — "
        f"{len(queries) - len(audited)} skipped: {sorted(_SKIP_CATEGORIES)}) ==="
    )

    rows: List[Dict] = []
    for q in audited:
        row = _audit_one(q)
        rows.append(row)
        tag = "OK " if row["agree"] else ("--" if row["agree"] is None else "X ")
        print(
            f"  {tag} q{row['id']:2}: cat={row['category']:<10s} "
            f"expected={row['expected'] or '?':<10s} "
            f"got={row['got']:<10s} ({row['method']}, {row['elapsed']:>4.2f}s) "
            f"| {row['text'][:50]}"
        )

    # ─── summary ────────────────────────────────────────────────────
    classified = [r for r in rows if r.get("agree") is not None]
    agreements = [r for r in classified if r["agree"]]
    overall_acc = round(len(agreements) / len(classified), 3) if classified else 0.0

    # Per-expected confusion — how often each expected mode got
    # routed to each actual mode.
    confusion: Dict[str, Counter] = {}
    for r in classified:
        confusion.setdefault(r["expected"], Counter())[r["got"]] += 1

    # Method distribution — fast vs llm vs fallback. Useful for telling
    # apart "the prompt is wrong" (llm misroute) from "we need a fast
    # pattern" (everything goes llm and ~50% misroute).
    method_counts = Counter(r["method"] for r in rows)

    summary = {
        "suite":                args.suite,
        "queries_audited":      len(rows),
        "queries_classified":   len(classified),
        "agreements":           len(agreements),
        "overall_accuracy":     overall_acc,
        "method_distribution":  dict(method_counts),
        "confusion_by_expected": {
            exp: dict(cts) for exp, cts in confusion.items()
        },
    }

    print()
    print(f"=== Summary ===")
    print(f"  classified:  {summary['queries_classified']}")
    print(f"  agreements:  {summary['agreements']} ({overall_acc*100:.1f}%)")
    print(f"  methods:     {summary['method_distribution']}")
    print(f"  confusion (expected → got distribution):")
    for exp, cts in summary["confusion_by_expected"].items():
        line = ", ".join(f"{g}={c}" for g, c in sorted(cts.items(), key=lambda x: -x[1]))
        print(f"    {exp:<10s} → {line}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = REPORTS_DIR / f"intent-classifier-audit-{stamp}.json"
    out_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().isoformat(),
                "suite":        args.suite,
                "results":      rows,
                "summary":      summary,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nsaved: {out_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
