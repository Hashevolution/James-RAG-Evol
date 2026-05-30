"""Step 2 — Download MultiHop-RAG (Tang & Yang 2024, EMNLP) into the
hotpot_eval workspace.

Pulls two configs from HuggingFace ``yixuantt/MultiHopRAG``:

  - ``corpus``      : 609 news articles  (category, title, body, source, …)
  - ``MultiHopRAG`` : 2,556 queries      (query, answer, evidence_list,
                                          question_type ∈ {comparison_query,
                                          inference_query, temporal_query,
                                          null_query})

Saves:
  - One ``.txt`` per article under ``$JAMES_WORKSPACE/raw/`` so the
    existing JAMES ingest pipeline can absorb them in Step 7.
  - Queries as a single ``$JAMES_WORKSPACE/eval/multihop_rag_raw_queries.json``
    so Step 3 (build_fixture.py) can convert them into the step7-format
    fixture without re-downloading.
  - ``$JAMES_WORKSPACE/ATTRIBUTION.md`` capturing the CC-BY-4.0 license
    + citation per the dataset README.

Idempotent: re-running skips files that already exist (size check). Cap
the article file name to a short slug so Windows long-path limits don't
bite — title can be 200+ chars in this dataset.

Plan reference: `~/.claude/plans/quiet-hugging-iverson.md` Step 2.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DATASET_ID = "yixuantt/MultiHopRAG"
DATASET_CITATION = (
    "Tang, Yixuan and Yang, Yi. "
    "\"MultiHop-RAG: Benchmarking Retrieval-Augmented Generation for "
    "Multi-Hop Queries.\" Findings of EMNLP, 2024. "
    "https://huggingface.co/datasets/yixuantt/MultiHopRAG"
)
LICENSE = "CC-BY-4.0"

# Slug max length so the combined filename stays comfortably under
# Windows MAX_PATH-style limits. Original titles can be 200+ chars.
SLUG_MAX = 80
# Trim/normalize for filesystem safety.
_SLUG_BAD = re.compile(r"[^a-zA-Z0-9\-\.]+")


def _slug(text: str) -> str:
    s = _SLUG_BAD.sub("-", (text or "untitled").strip()).strip("-")
    return s[:SLUG_MAX] if s else "untitled"


def _workspace() -> Path:
    """Resolve workspace. ``JAMES_WORKSPACE`` must be set to point at
    the hotpot_eval workspace; refuse to scribble in the project root.
    """
    raw = os.environ.get("JAMES_WORKSPACE", "").strip()
    if not raw:
        sys.exit(
            "[download_multihop_rag] JAMES_WORKSPACE is not set. Refusing "
            "to write into the project root. Export it first, e.g.:\n"
            "  export JAMES_WORKSPACE=./workspaces/hotpot_eval"
        )
    ws = Path(raw).resolve()
    if not ws.exists():
        sys.exit(f"[download_multihop_rag] workspace {ws} does not exist")
    return ws


def _write_article(out_dir: Path, idx: int, row: dict) -> Path:
    title = row.get("title") or "untitled"
    slug = _slug(title)
    fname = f"multihop_{idx:04d}_{slug}.txt"
    path = out_dir / fname
    if path.exists() and path.stat().st_size > 0:
        return path
    body = row.get("body", "") or ""
    header = (
        f"# {title}\n\n"
        f"Source: {row.get('source', '?')}\n"
        f"URL: {row.get('url', '?')}\n"
        f"Author: {row.get('author', '?')}\n"
        f"Published: {row.get('published_at', '?')}\n"
        f"Category: {row.get('category', '?')}\n\n"
        f"---\n\n"
    )
    path.write_text(header + body, encoding="utf-8")
    return path


def _write_attribution(ws: Path) -> Path:
    path = ws / "ATTRIBUTION.md"
    if path.exists():
        return path
    path.write_text(
        "# Dataset Attribution — MultiHop-RAG\n\n"
        f"**Source**: HuggingFace `{DATASET_ID}`\n"
        f"**License**: {LICENSE}\n"
        f"**Citation**:\n\n"
        f"> {DATASET_CITATION}\n\n"
        "## Use within JAMES\n\n"
        "The MultiHop-RAG corpus (609 news articles, predominantly\n"
        "English-language news from 2023-09 to 2023-12) is ingested into\n"
        "this workspace's `wiki/` via the standard JAMES pipeline\n"
        "(`scripts/ingest_pipeline.py`). The 2,556 query set is converted\n"
        "into step7-format fixture by `scripts/hotpot/build_fixture.py`\n"
        "and consumed by `scripts/qvt_ablation_matrix.py` for the α-5\n"
        "ablation matrix.\n\n"
        "Per CC-BY-4.0, this attribution file MUST stay alongside any\n"
        "redistributed corpus snapshot. Production wiki (project root\n"
        "`./wiki/`) is unaffected by this benchmark workspace — see\n"
        "`workspaces/hotpot_eval/README.md`.\n",
        encoding="utf-8",
    )
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="Download MultiHop-RAG into hotpot_eval workspace")
    ap.add_argument(
        "--limit-articles", type=int, default=0,
        help="Cap article count (0 = all 609). Useful for smoke testing.",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="Print plan + first article preview; write nothing.",
    )
    args = ap.parse_args()

    ws = _workspace()
    raw_dir = ws / "raw"
    eval_dir = ws / "eval"
    raw_dir.mkdir(parents=True, exist_ok=True)
    eval_dir.mkdir(parents=True, exist_ok=True)

    print(f"[download_multihop_rag] workspace: {ws}")
    print(f"[download_multihop_rag] dataset:   {DATASET_ID}")

    try:
        from datasets import load_dataset
    except ImportError:
        sys.exit(
            "[download_multihop_rag] `datasets` library not installed.\n"
            "  pip install 'datasets>=2.14.0'"
        )

    print("[download_multihop_rag] loading corpus split…")
    corpus = load_dataset(DATASET_ID, "corpus", split="train")
    print(f"  → {len(corpus)} articles")

    print("[download_multihop_rag] loading MultiHopRAG (queries) split…")
    queries = load_dataset(DATASET_ID, "MultiHopRAG", split="train")
    print(f"  → {len(queries)} queries")

    if args.dry_run:
        print("\n[dry-run] first article preview:")
        sample = corpus[0]
        print(f"  title:  {sample.get('title', '?')[:80]}")
        print(f"  source: {sample.get('source', '?')}")
        print(f"  body chars: {len(sample.get('body', ''))}")
        print("\n[dry-run] first query preview:")
        q = queries[0]
        print(f"  query:    {q.get('query', '')[:100]}…")
        print(f"  answer:   {q.get('answer', '?')}")
        print(f"  type:     {q.get('question_type', '?')}")
        print(f"  evidence: {len(q.get('evidence_list', []))} entries")
        return 0

    # Articles — flat .txt files under raw/.
    print(f"\n[download_multihop_rag] writing articles to {raw_dir.relative_to(ws.parent.parent if (ws.parent.parent / 'README.md').exists() else ws)}…")
    n_articles = len(corpus) if args.limit_articles <= 0 else min(args.limit_articles, len(corpus))
    n_written = n_skipped = 0
    for i in range(n_articles):
        path = _write_article(raw_dir, i, dict(corpus[i]))
        if path.stat().st_mtime > 0 and path.stat().st_size > 0:
            # Already-existed-or-just-wrote — coarse counter.
            if (datetime.now(timezone.utc).timestamp() - path.stat().st_mtime) > 60:
                n_skipped += 1
            else:
                n_written += 1
        if (i + 1) % 50 == 0:
            print(f"  [{i+1}/{n_articles}] …")
    print(f"  → wrote/refreshed {n_written}, skipped (already present) {n_skipped}")

    # Queries — single JSON for downstream Step 3 (build_fixture).
    queries_path = eval_dir / "multihop_rag_raw_queries.json"
    print(f"\n[download_multihop_rag] writing raw queries to {queries_path.name}…")
    raw_queries_payload = {
        "schema": "multihop-rag-raw-v1",
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_id": DATASET_ID,
        "license": LICENSE,
        "citation": DATASET_CITATION,
        "n_queries": len(queries),
        "queries": [dict(q) for q in queries],
    }
    queries_path.write_text(
        json.dumps(raw_queries_payload, ensure_ascii=False, indent=2,
                   default=str),
        encoding="utf-8",
    )
    print(f"  → {len(queries)} queries saved")

    # Attribution memo.
    attr_path = _write_attribution(ws)
    print(f"\n[download_multihop_rag] attribution: {attr_path.name}")

    print(
        "\n[done] Step 2 complete. Next:\n"
        "  python scripts/hotpot/build_fixture.py --subset balanced-200"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
