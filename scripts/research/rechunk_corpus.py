"""Re-chunk the existing ChromaDB corpus with a new chunk_size.

Reuses what's already in the vector store (no PDF re-processing needed):
  1. Snapshot all chunks grouped by `source` metadata
  2. For each source: join chunks in stored order → re-split with new size
  3. Wipe the collection
  4. Re-add with new chunks (preserves source / sensitivity / category /
     owner / source_type metadata)

Built 2026-06-03 for γ cycle (chunk_size 500→1024 measurement). Safer
than full PDF re-ingest because it avoids re-running the LLM entity
extractor (entities stay as-is) and preserves the doc-level metadata.

Caveats:
  - Within-source chunk ORDER is not formally guaranteed by ChromaDB.
    For deterministic re-chunking, we sort chunks by their stored ID
    (lexicographic) which approximates ingest order for the
    standard chunk_<uuid>_<idx> id scheme. If a source's chunks were
    ingested in non-sequential ID order, the concat-then-resplit may
    produce slightly different boundaries from a fresh PDF ingest.
    Acceptable for measurement (we control for it by comparing
    against the equivalent re-chunk at the OLD size as baseline if
    needed) — material answer-quality effect dominates ordering noise.

Usage::

    python scripts/research/rechunk_corpus.py --new-chunk-size 1024 \\
        [--new-overlap 100] [--dry-run] [--backup]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

sys.stdout.reconfigure(encoding="utf-8")


def _backup_collection(coll, out_path: Path) -> None:
    """Snapshot the full collection to a JSON file."""
    all_data = coll.get(include=["documents", "metadatas"])
    payload = {
        "captured_at": datetime.now().isoformat(timespec="seconds"),
        "count": coll.count(),
        "ids": all_data.get("ids", []),
        "documents": all_data.get("documents", []),
        "metadatas": all_data.get("metadatas", []),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"[backup] wrote {out_path}  ({payload['count']} chunks)")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--new-chunk-size", type=int, required=True,
                        help="Target chunk size in chars (e.g., 1024)")
    parser.add_argument("--new-overlap", type=int, default=None,
                        help="Target overlap in chars (default: chunk_size // 10)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without modifying ChromaDB")
    parser.add_argument("--backup", action="store_true", default=True,
                        help="Snapshot current collection to JSON before wiping (default: True)")
    parser.add_argument("--no-backup", dest="backup", action="store_false")
    args = parser.parse_args(argv)

    overlap = args.new_overlap if args.new_overlap is not None else args.new_chunk_size // 10

    import chromadb
    from config import CHROMA_COLLECTION
    from core.vector_store import _chroma_dir_for_model
    from utils.tokenizer import split_chunks

    db_path = _chroma_dir_for_model("chroma_db")
    print(f"[chroma] path: {db_path}")
    client = chromadb.PersistentClient(path=db_path)
    coll = client.get_or_create_collection(name=CHROMA_COLLECTION, metadata={"hnsw:space": "cosine"})
    before_count = coll.count()
    print(f"[chroma] current chunk count: {before_count}")
    print(f"[plan] re-chunk with chunk_size={args.new_chunk_size}, overlap={overlap}")
    print()

    if args.backup:
        ts = datetime.now().strftime("%Y%m%dT%H%M%S")
        backup_path = ROOT / "reports" / "research-runs" / f"chroma-snapshot-pre-rechunk-{ts}.json"
        _backup_collection(coll, backup_path)
        print()

    # Group all chunks by source
    all_data = coll.get(include=["documents", "metadatas"])
    docs_by_source: dict = defaultdict(list)
    meta_by_source: dict = {}
    ids = all_data["ids"]
    documents = all_data["documents"]
    metadatas = all_data["metadatas"]
    # Sort by id to approximate ingest order
    indexed = sorted(zip(ids, documents, metadatas), key=lambda t: t[0])
    for _id, doc, meta in indexed:
        source = (meta or {}).get("source", "_unknown")
        docs_by_source[source].append(doc)
        # Cache the first non-empty metadata per source (all chunks of a
        # source should share the doc-level fields).
        if source not in meta_by_source:
            meta_by_source[source] = meta or {}

    print(f"[group] {len(docs_by_source)} distinct sources")
    if not docs_by_source:
        print("[abort] no chunks found")
        return 1

    # Re-chunk each source
    new_chunks_total = []
    new_metas_total = []
    new_sources_total = []
    for source, chunks in sorted(docs_by_source.items()):
        # Concatenate the source chunks with a single newline separator
        # (joining at original chunk boundaries — not perfect but close
        # to the original ingest pre-chunking layout).
        joined = "\n".join(chunks).strip()
        new_chunks = split_chunks(joined, chunk_size=args.new_chunk_size, overlap=overlap)
        meta = meta_by_source[source]
        for c in new_chunks:
            new_chunks_total.append(c)
            new_metas_total.append(meta)
            new_sources_total.append(source)

    print(f"[rechunk] {before_count} chunks → {len(new_chunks_total)} chunks "
          f"(reduction: {(1 - len(new_chunks_total)/before_count)*100:.1f}%)")
    sizes = [len(c) for c in new_chunks_total]
    import statistics
    print(f"[rechunk] new chunk size: mean={statistics.mean(sizes):.0f}, "
          f"median={statistics.median(sizes):.0f}, "
          f"min={min(sizes)}, max={max(sizes)}")
    print()

    if args.dry_run:
        print("[dry-run] no changes made.")
        return 0

    # Wipe + repopulate. Use VectorStore.add_documents_with_meta to
    # ensure embeddings get computed with the current bge-m3 model.
    print(f"[wipe] deleting all {before_count} chunks from {CHROMA_COLLECTION}…")
    # ChromaDB deletes via ids
    client.delete_collection(name=CHROMA_COLLECTION)
    print("[wipe] collection deleted; recreating…")
    coll = client.get_or_create_collection(name=CHROMA_COLLECTION,
                                            metadata={"hnsw:space": "cosine"})

    # Re-add via VectorStore's add_documents_with_meta. Group by source
    # so each call has uniform metadata.
    from core.vector_store import VectorStore
    vs = VectorStore()
    by_source = defaultdict(list)
    for c, m, s in zip(new_chunks_total, new_metas_total, new_sources_total):
        by_source[s].append((c, m))
    written = 0
    for source, items in by_source.items():
        texts = [c for c, _ in items]
        meta = items[0][1] if items else {}
        meta_clean = {k: v for k, v in meta.items()
                      if k in ("source", "sensitivity", "category", "owner", "source_type")
                      and v is not None}
        vs.add_documents_with_meta(texts=texts, source=source, metadata=meta_clean)
        written += len(texts)
    print(f"[add] wrote {written} chunks to {CHROMA_COLLECTION}")
    print(f"[verify] new chunk count: {coll.count()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
