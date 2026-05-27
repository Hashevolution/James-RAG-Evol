"""F7 (LEO L.D follow-up, 2026-05-27) — chroma top-k probe for q15.

F6 (PR #532) pinned q15 zero-recall to "chroma rerank / embedding
miss on cross-lingual prompt" by ruling out classifier (F2), policy
gate (F1 + JWT mitigation), and entity-extraction stochasticity
(5/5 byte-identical extraction). F7 is the one-step-deeper probe:
**what does chroma actually return for the q15 query, and where
does the David Soria Parra source PDF rank?**

If the source PDF (`08_MCP_(Model_Context_Protocol).pdf`) is OUTSIDE
top-k, the systemic fix is BL-9 (multilingual embedding swap —
`multilingual-e5-large` or `bge-m3`). The current default
`paraphrase-multilingual-MiniLM-L12-v2` 384-dim model under-ranks
low-frequency proper nouns in cross-lingual prompts.

If the source PDF is INSIDE top-k but the rerank ordering pushes it
down, a downstream rerank tuning fix is enough.

This probe runs 4 query variations to separate the symptom dimensions:
  1. KO original         "David Soria Parra가 누구야?"  ← q15 exact
  2. EN translation      "Who is David Soria Parra?"
  3. Name only           "David Soria Parra"             ← no question
  4. Concept side        "MCP Model Context Protocol"    ← related entity

The probe makes NO server call, NO LLM call. Just direct vector
store query via ``core.vector_store.VectorStore.search`` against
the same chroma collection the production pipeline uses. ~few seconds.

Output: ``reports/research-runs/q15-chroma-probe-<stamp>.json``.

Usage
-----
    python scripts/research/q15_chroma_probe.py
    python scripts/research/q15_chroma_probe.py --top-k 30
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

try:
    from utils.console import ensure_utf8_console
    ensure_utf8_console()
except Exception:
    pass


REPORTS_DIR = ROOT / "reports" / "research-runs"

# Source PDF that contains David Soria Parra's wiki context —
# extracted from `wiki/entity/prod/person/david_soria_parra.md`
# `attributes.source_document` field. This is what *should* surface
# for the q15 query family if the embedding can bridge Korean
# question → English name → English-titled PDF.
TARGET_SOURCE = "08_MCP_(Model_Context_Protocol).pdf"

QUERY_VARIATIONS = [
    # (label, query text)
    ("ko_q15_exact",  "David Soria Parra가 누구야?"),
    ("en_translation", "Who is David Soria Parra?"),
    ("name_only",      "David Soria Parra"),
    ("concept_side",   "MCP Model Context Protocol"),
]


def _probe_one(label: str, query: str, top_k: int) -> Dict:
    """One chroma query → score-sorted top-k row + target rank."""
    from core.vector_store import VectorStore

    store = VectorStore()
    t0 = time.time()
    try:
        results = store.search(query, top_k=top_k, source_type="prod")
        err = None
    except Exception as e:
        results = []
        err = f"{type(e).__name__}: {str(e)[:200]}"
    elapsed = time.time() - t0

    # Rank lookup — 1-indexed for human-readable output.
    target_rank: Optional[int] = None
    target_score: Optional[float] = None
    for idx, r in enumerate(results, start=1):
        src = (r.get("source") or "").lower()
        if TARGET_SOURCE.lower() in src:
            target_rank = idx
            target_score = round(r.get("score", 0.0), 4)
            break

    # Top-k preview — score + source + 80-char text preview.
    top_preview = [
        {
            "rank":   i + 1,
            "score":  round(r.get("score", 0.0), 4),
            "source": r.get("source", "unknown"),
            "text_preview": (r.get("text", "") or "").strip().replace("\n", " ")[:80],
        }
        for i, r in enumerate(results)
    ]

    return {
        "label":            label,
        "query":            query,
        "top_k":            top_k,
        "elapsed":          round(elapsed, 3),
        "results_count":    len(results),
        "target_pdf":       TARGET_SOURCE,
        "target_rank":      target_rank,
        "target_score":     target_score,
        "top_preview":      top_preview,
        "error":            err,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="F7 — direct chroma top-k probe for q15 variations.",
    )
    ap.add_argument("--top-k", type=int, default=20,
                    help="how many top results to log per variation (default 20)")
    args = ap.parse_args()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    print(f"=== q15 chroma top-k probe (top_k={args.top_k}) ===")
    print(f"target PDF: {TARGET_SOURCE}\n")

    variations: List[Dict] = []
    for label, query in QUERY_VARIATIONS:
        print(f"--- {label}: {query!r} ---")
        row = _probe_one(label, query, args.top_k)
        variations.append(row)
        if row.get("error"):
            print(f"  ERROR: {row['error']}")
            continue
        if row["target_rank"]:
            print(
                f"  ✓ target found at rank {row['target_rank']} / {args.top_k}, "
                f"score={row['target_score']}"
            )
        else:
            print(f"  ✗ target NOT in top-{args.top_k}")
        # Show top 5 sources for context
        for entry in row["top_preview"][:5]:
            print(f"    #{entry['rank']:2}: score={entry['score']:.4f} src={entry['source']}")
        print()

    # ─── summary ──────────────────────────────────────────────────
    ranks = [v["target_rank"] for v in variations if v["target_rank"] is not None]
    summary = {
        "variations_count":   len(variations),
        "target_pdf":         TARGET_SOURCE,
        "top_k":              args.top_k,
        "variations_hit":     len(ranks),
        "best_rank":          min(ranks) if ranks else None,
        "ranks_by_label":     {v["label"]: v["target_rank"] for v in variations},
    }

    print("=== Summary ===")
    print(f"  target PDF found in {summary['variations_hit']} / {len(variations)} variations")
    print(f"  best rank: {summary['best_rank']}")
    print(f"  per-label ranks: {summary['ranks_by_label']}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = REPORTS_DIR / f"q15-chroma-probe-{stamp}.json"
    out_path.write_text(
        json.dumps({
            "generated_at": datetime.now().isoformat(),
            "variations":   variations,
            "summary":      summary,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nsaved: {out_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
