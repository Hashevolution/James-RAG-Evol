"""BL-9 (Sprint 4, 2026-05-27) — chroma re-embedding runner.

Re-encodes every chunk in the legacy MiniLM chroma collection into a
new per-model collection using the target embedding model. Required
when the operator promotes ``JAMES_EMBEDDING_MODEL`` from the legacy
``paraphrase-multilingual-MiniLM-L12-v2`` to a 1024-dim multilingual
model (e.g. ``BAAI/bge-m3`` or ``intfloat/multilingual-e5-large``).
Cosine search requires matching dimensions, so a new collection at
``chroma_db_<short>/`` is created rather than mutating the legacy
``chroma_db/`` — that legacy directory stays intact so a rollback is
``unset JAMES_EMBEDDING_MODEL`` away.

This script reads source chunks via raw chromadb (so the source can
keep its 384-dim embeddings) and writes target chunks via a
fresh ``SentenceTransformer`` loaded directly from the target model
id (no ``VectorStore`` singleton pollution between source and target
encoders).

Why F7 motivates BL-9 — short version
-------------------------------------
F7 (PR #533) confirmed the current MiniLM model can't bridge
``"David Soria Parra가 누구야?"`` → ``08_MCP_(Model_Context_Protocol).pdf``
even though the PDF embeds cleanly under its English title. Swapping
to a 1024-dim cross-lingual model is the systemic fix. See
``reports/promo-assets/v3prime-leo-evidence-scope-result.md``
§"F7 follow-up" for the smoking-gun probe.

Usage
-----
    # Dry-run — count chunks + report planned target path; no write
    python scripts/migrate_embedding.py --target BAAI/bge-m3 --dry-run

    # Real run — re-embed + write to new chroma_db_<short>/
    python scripts/migrate_embedding.py --target BAAI/bge-m3

    # First real run will download the target model (~2 GB for bge-m3)
    # to models/<short>/ via SentenceTransformer's HF fallback.

After the migration completes:
    1. Set JAMES_EMBEDDING_MODEL=<target> in .env or shell env
    2. Restart the JAMES server (the VectorStore module reads
       EMBEDDING_MODEL at import time)
    3. Run the BL-9 acceptance gate:
         python scripts/research/q15_chroma_probe.py
       Expected post-swap: target PDF ranks ≤ 10 on the ``name_only``
       variation (pre-swap was NOT in top-20).
       Then run the operator wrapper:
         python scripts/bench_lc_scope_arms.py
       Expected post-swap: step7 v4 q15 path_recall ≥ 0.5 (pre-swap
       was 0.0). Mean path recall expected to rise from 0.80 baseline.

Rollback
--------
    unset JAMES_EMBEDDING_MODEL    # PowerShell: $env:JAMES_EMBEDDING_MODEL=$null
    # Server restart → reads legacy MiniLM tag → chroma_db/ path.
    # The new chroma_db_<short>/ stays on disk and survives the
    # toggle so a re-promote is a one-env-var flip away.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from utils.console import ensure_utf8_console
    ensure_utf8_console()
except Exception:
    pass


# Source = the legacy MiniLM collection. Resolved at config-load time
# so this script can run independently of the runtime VectorStore
# singleton (which would be locked to one model per process).
from config import (  # noqa: E402
    BASE_DIR,
    CHROMA_COLLECTION,
    CHROMA_DIR,
    _embedding_short_name,
)


_LEGACY_MINILM_TAG = "paraphrase-multilingual-MiniLM-L12-v2"


def _target_chroma_dir(target_model: str) -> str:
    """Mirror of ``core.vector_store._chroma_dir_for_model`` — returns
    where the new collection will live. Kept independent of that
    function so the migration script doesn't depend on `EMBEDDING_MODEL`
    being already-set to the target (the operator flips env after the
    migration completes)."""
    if target_model == _LEGACY_MINILM_TAG:
        # No-op migration. The runner refuses to clobber its own source.
        raise ValueError(
            "target model matches the legacy MiniLM tag — "
            "no migration needed. Operator must pass a different "
            "JAMES_EMBEDDING_MODEL target."
        )
    suffix = _embedding_short_name(target_model)
    return f"{CHROMA_DIR}_{suffix}"


def _load_source_chunks():
    """Yield (id, document, metadata) triples from the legacy chroma
    collection. Uses raw chromadb client so we read the source as-is
    without invoking the runtime VectorStore (which would lazy-load
    the legacy SentenceTransformer model, wasting time + memory)."""
    import chromadb
    print(f"[migrate] source chroma dir: {CHROMA_DIR}")
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    collection = client.get_or_create_collection(
        name=CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )
    count = collection.count()
    print(f"[migrate] source chunks: {count}")
    if count == 0:
        return
    page = collection.get(include=["documents", "metadatas"])
    ids = page.get("ids") or []
    docs = page.get("documents") or []
    metas = page.get("metadatas") or [{}] * len(ids)
    for i, doc, meta in zip(ids, docs, metas):
        yield i, doc, (meta or {})


def _ensure_target_model_cached(target_model: str):
    """Load the target SentenceTransformer, with local-first / HF
    fallback. Saves to ``models/<short>/`` on first download so
    subsequent JAMES server startups skip the HF roundtrip."""
    from sentence_transformers import SentenceTransformer

    short = _embedding_short_name(target_model)
    local_dir = os.path.join(BASE_DIR, "models", short)

    if os.path.exists(local_dir):
        try:
            model = SentenceTransformer(local_dir, local_files_only=True)
            print(f"[migrate] target model loaded from local cache: {local_dir}")
            return model
        except Exception as e:
            print(f"[migrate] local target load failed ({e}); falling back to HF")

    print(f"[migrate] downloading target model from HuggingFace: {target_model}")
    print("[migrate]   (this may take several minutes + several GB on first run)")
    model = SentenceTransformer(target_model)
    os.makedirs(local_dir, exist_ok=True)
    model.save(local_dir)
    print(f"[migrate] cached locally: {local_dir}")
    return model


def _encode_in_batches(model, texts: List[str], batch_size: int):
    """Batched encode — small batches keep peak memory predictable
    on operator workstations that may not have a GPU."""
    for start in range(0, len(texts), batch_size):
        end = min(start + batch_size, len(texts))
        chunk = texts[start:end]
        embs = model.encode(chunk, normalize_embeddings=True).tolist()
        yield start, end, embs


def main() -> int:
    ap = argparse.ArgumentParser(
        description="BL-9 chroma re-embedding runner.",
    )
    ap.add_argument(
        "--target", required=True,
        help="HuggingFace model id (e.g. 'BAAI/bge-m3' or "
             "'intfloat/multilingual-e5-large')",
    )
    ap.add_argument(
        "--batch-size", type=int, default=32,
        help="encode batch size (default 32 — bge-m3 ~1024-dim fits "
             "on 16 GB workstations at this size)",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="count chunks + report planned target path; no write",
    )
    args = ap.parse_args()

    try:
        target_dir = _target_chroma_dir(args.target)
    except ValueError as e:
        print(f"[migrate] {e}")
        return 1

    print("=== BL-9 chroma re-embedding ===")
    print(f"  source model:  {_LEGACY_MINILM_TAG} (legacy MiniLM)")
    print(f"  target model:  {args.target}")
    print(f"  source dir:    {CHROMA_DIR}")
    print(f"  target dir:    {target_dir}")
    print(f"  collection:    {CHROMA_COLLECTION}")
    print()

    # Read source chunks first — fast operation, useful in dry-run.
    chunks = list(_load_source_chunks())
    if not chunks:
        print("[migrate] source collection is empty — nothing to migrate")
        return 0

    print(f"[migrate] loaded {len(chunks)} source chunks")
    if args.dry_run:
        print("[migrate] --dry-run set; no target write performed")
        return 0

    if os.path.exists(target_dir):
        existing_files = os.listdir(target_dir)
        if existing_files:
            print(
                f"[migrate] WARNING: target dir already exists with "
                f"{len(existing_files)} entries: {target_dir}"
            )
            print(
                "[migrate]   Re-running on top will duplicate chunks "
                "(chromadb ids are UUIDs from the source — same per "
                "run so chromadb will reject duplicate id inserts)."
            )
            print(
                f"[migrate]   To re-migrate from scratch: stop the JAMES "
                f"server first (it holds a file handle on the target "
                f"dir), then `rm -r {target_dir}` and re-run."
            )

    # Lazy-import the encoder only after dry-run path so dry-run is fast.
    model = _ensure_target_model_cached(args.target)

    import chromadb
    print(f"[migrate] opening target collection at {target_dir}")
    os.makedirs(target_dir, exist_ok=True)
    target_client = chromadb.PersistentClient(path=target_dir)
    target_collection = target_client.get_or_create_collection(
        name=CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )

    ids = [c[0] for c in chunks]
    docs = [c[1] for c in chunks]
    metas = [c[2] for c in chunks]

    t0 = time.time()
    total_done = 0
    for start, end, embs in _encode_in_batches(model, docs, args.batch_size):
        target_collection.add(
            ids=ids[start:end],
            documents=docs[start:end],
            embeddings=embs,
            metadatas=metas[start:end],
        )
        total_done += end - start
        elapsed = time.time() - t0
        rate = total_done / elapsed if elapsed > 0 else 0
        print(
            f"[migrate] {total_done}/{len(chunks)} chunks "
            f"({elapsed:.1f}s elapsed, {rate:.1f} chunks/s)"
        )

    final_count = target_collection.count()
    print()
    print("=== Migration complete ===")
    print(f"  source chunks:  {len(chunks)}")
    print(f"  target chunks:  {final_count}")
    print(f"  total elapsed:  {time.time() - t0:.1f}s")
    print()
    print("Next steps:")
    print(f"  1. Set JAMES_EMBEDDING_MODEL={args.target} in .env or shell env")
    print( "  2. Restart the JAMES server")
    print( "  3. Run BL-9 acceptance: python scripts/research/q15_chroma_probe.py")
    print( "     Expected: MCP PDF reaches top-10 on the `name_only` variation")
    print( "  4. Run bench wrapper for step7 v4 q15 path_recall check:")
    print( "     python scripts/bench_lc_scope_arms.py")
    print( "     Expected: q15 path_recall ≥ 0.5 (pre-swap was 0.0)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
