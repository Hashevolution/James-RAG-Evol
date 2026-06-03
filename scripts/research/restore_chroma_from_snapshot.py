"""Restore ChromaDB collection from a snapshot JSON file.

Born 2026-06-03 to recover original chunk-500 state after γ cycle
re-chunking experiments left the corpus in a non-original state
(re-chunking is lossy — each cycle scrambles boundaries).

Usage::

    python scripts/research/restore_chroma_from_snapshot.py \\
        --snapshot reports/research-runs/chroma-snapshot-pre-rechunk-20260603T084607.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

sys.stdout.reconfigure(encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--snapshot", required=True,
                        help="Path to chroma snapshot JSON")
    args = parser.parse_args(argv)

    import chromadb
    from config import CHROMA_COLLECTION
    from core.vector_store import _chroma_dir_for_model, VectorStore

    snap = json.load(open(args.snapshot, encoding="utf-8"))
    print(f"[snapshot] captured: {snap['captured_at']}  count: {snap['count']}")

    db_path = _chroma_dir_for_model("chroma_db")
    client = chromadb.PersistentClient(path=db_path)
    coll = client.get_or_create_collection(
        name=CHROMA_COLLECTION, metadata={"hnsw:space": "cosine"}
    )
    before = coll.count()
    print(f"[chroma] current count: {before}")

    print(f"[wipe] deleting collection…")
    client.delete_collection(name=CHROMA_COLLECTION)
    coll = client.get_or_create_collection(
        name=CHROMA_COLLECTION, metadata={"hnsw:space": "cosine"}
    )

    # Re-add via VectorStore (computes fresh embeddings)
    vs = VectorStore()
    docs = snap["documents"]
    metas = snap["metadatas"]
    # Group by source for batched add_documents_with_meta
    by_source = defaultdict(list)
    for doc, meta in zip(docs, metas):
        if not isinstance(meta, dict):
            continue
        source = meta.get("source", "_unknown")
        by_source[source].append((doc, meta))

    print(f"[restore] {len(by_source)} distinct sources → re-embedding…")
    written = 0
    for source, items in by_source.items():
        texts = [d for d, _ in items]
        meta = items[0][1]
        meta_clean = {
            k: v for k, v in meta.items()
            if k in ("source", "sensitivity", "category", "owner", "source_type")
            and v is not None
        }
        vs.add_documents_with_meta(
            texts=texts, source=source, metadata=meta_clean
        )
        written += len(texts)

    print(f"[verify] new chunk count: {coll.count()}  (snapshot was {snap['count']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
