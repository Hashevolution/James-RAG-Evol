"""Cycle γ Phase B Option A — build a JAMES workspace whose corpus
mirrors the RGB-en docs, so the JAMES-engine producer can be
measured on the same 50 queries the closed-corpus baseline ran.

Two modes (matching the 2-workspace experiment design the operator
chose 2026-06-08):

* ``--mode full``    — ingest every row's positive + negative
                       passages. Pairs with the noise-robustness
                       JAMES measurement.
* ``--mode negrej``  — ingest every row's negative passages only.
                       Pairs with the negative-rejection JAMES
                       measurement (the workspace has no gold for
                       any query, so the JAMES abstention layer
                       drives the result).

The script sets ``JAMES_WORKSPACE`` *before* importing core.config
so the workspace path the operator chose is the path the
VectorStore writes to. Each (row, kind) pair lands under a single
deterministic source id (``rgb-en-<row_id>-{pos|neg}``) so a
re-run that bumps the fixture deletes + re-ingests the matching
slice cleanly (via VectorStore.delete_by_source).

Usage (operator)::

    # Workspace #1 — full (positive + negative)
    JAMES_WORKSPACE=./workspaces/cycle_gamma_rgb_full \
    python scripts/research/cycle_gamma_rgb_corpus_build.py \
        --mode full \
        --workspace ./workspaces/cycle_gamma_rgb_full

    # Workspace #2 — negrej-only (negative only)
    JAMES_WORKSPACE=./workspaces/cycle_gamma_rgb_negrej \
    python scripts/research/cycle_gamma_rgb_corpus_build.py \
        --mode negrej \
        --workspace ./workspaces/cycle_gamma_rgb_negrej

Self-eval trap rule (memory ``feedback_self_evaluation_trap``):
this script reads the published RGB fixture verbatim and routes
the published passages into the JAMES vector store without
rewriting / curating / re-labelling. The "negrej" mode is the
published RGB paper's experimental setting (strip positives), not
a JAMES-internal trick.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from pathlib import Path


def _resolve_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _read_rgb_fixture(path: Path) -> list:
    """Accept either JSONL (the published ``en.json`` shape) or a
    JSON array (the ``*_refine.json`` shape). Mirrors
    ``eval.external.rgb_loader._load_rgb_fixture``."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    head = text.lstrip()[:1]
    if head == "[":
        return json.loads(text)
    out: list = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def _ingest_row(
    vector_store,
    row: dict,
    *,
    mode: str,
) -> tuple:
    """Ingest one row's passages. Returns ``(n_pos_ingested,
    n_neg_ingested)``."""
    row_id = str(row.get("id", "noid"))
    positives = [p for p in (row.get("positive") or [])
                  if isinstance(p, str) and p.strip()]
    negatives = [n for n in (row.get("negative") or [])
                  if isinstance(n, str) and n.strip()]

    n_pos_ingested = 0
    n_neg_ingested = 0

    if mode == "full" and positives:
        vector_store.add_documents_with_meta(
            positives,
            source=f"rgb-en-{row_id}-pos",
            metadata={
                "category":     "rgb-en-positive",
                "source_type":  "prod",
            },
        )
        n_pos_ingested = len(positives)

    if negatives:
        vector_store.add_documents_with_meta(
            negatives,
            source=f"rgb-en-{row_id}-neg",
            metadata={
                "category":     "rgb-en-negative",
                "source_type":  "prod",
            },
        )
        n_neg_ingested = len(negatives)

    return (n_pos_ingested, n_neg_ingested)


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="cycle_gamma_rgb_corpus_build",
        description=(
            "Build a JAMES workspace whose corpus mirrors RGB-en "
            "(full or negrej-only mode). Sets JAMES_WORKSPACE so the "
            "VectorStore writes to the chosen workspace path."
        ),
    )
    p.add_argument("--mode", required=True,
                    choices=("full", "negrej"),
                    help="full = positive + negative; negrej = "
                          "negative only")
    p.add_argument("--workspace", required=True,
                    help="absolute or relative path to the workspace "
                          "root (chroma_db lives at "
                          "<workspace>/chroma_db/)")
    p.add_argument("--fixture", default=None,
                    help="path to RGB en.json (default: "
                          "eval/external/_fixtures/rgb/en.json)")
    p.add_argument("--max-rows", type=int, default=None,
                    help="cap on rows ingested (smoke convenience)")
    p.add_argument("--progress-every", type=int, default=25,
                    help="print progress every N rows (default 25)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)

    root = _resolve_root()
    workspace = Path(args.workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    # Set JAMES_WORKSPACE BEFORE importing core/config. The resolver
    # in core.plugins.workspace reads it at import time.
    os.environ["JAMES_WORKSPACE"] = str(workspace)

    fixture_path = (Path(args.fixture).resolve() if args.fixture
                    else root / "eval" / "external" / "_fixtures"
                         / "rgb" / "en.json")
    if not fixture_path.exists():
        print(f"!! fixture not found: {fixture_path}", file=sys.stderr)
        print("   download via:", file=sys.stderr)
        print("   python -c \"from eval.external.runner import "
                "build_loader; build_loader('rgb', variant='en', "
                "allow_download=True).iter_queries(n_samples=1)\"",
                file=sys.stderr)
        return 2

    # UTF-8 console safety on Windows.
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                    errors="replace")

    rows = _read_rgb_fixture(fixture_path)
    if args.max_rows is not None:
        rows = rows[:args.max_rows]

    print("=== cycle γ RGB-en corpus build ===")
    print(f"  workspace : {workspace}")
    print(f"  fixture   : {fixture_path}  (rows={len(rows)})")
    print(f"  mode      : {args.mode}")
    print()

    # Late import so JAMES_WORKSPACE is honoured.
    sys.path.insert(0, str(root))
    from core.vector_store import VectorStore

    vector_store = VectorStore()
    n_pos_total = 0
    n_neg_total = 0
    t0 = time.time()

    for i, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            continue
        n_pos, n_neg = _ingest_row(
            vector_store, row, mode=args.mode,
        )
        n_pos_total += n_pos
        n_neg_total += n_neg
        if (i % max(args.progress_every, 1) == 0
                or i == len(rows)):
            elapsed = time.time() - t0
            print(f"  [{i}/{len(rows)}] {elapsed:.0f}s — "
                    f"pos={n_pos_total} neg={n_neg_total}",
                    flush=True)

    elapsed = time.time() - t0
    final_count = vector_store.count()
    print()
    print(f"=== INGESTION COMPLETE ({args.mode}) ===")
    print(f"  rows processed         : {len(rows)}")
    print(f"  positive passages added: {n_pos_total}")
    print(f"  negative passages added: {n_neg_total}")
    print(f"  vector store count     : {final_count}")
    print(f"  elapsed                : {elapsed:.1f}s")
    print(f"  workspace              : {workspace}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
