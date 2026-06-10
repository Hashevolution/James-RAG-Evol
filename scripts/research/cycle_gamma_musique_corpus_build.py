"""Cycle γ Phase C.2 — build a JAMES workspace whose corpus mirrors
the MuSiQue paragraphs, so the JAMES-engine producer can be measured
on the same queries as the paired ablation plan
(docs/research/cycle-gamma-phase-c2-preregistration-2026-06-10.md).

Mirrors ``cycle_gamma_rgb_corpus_build.py``. Every row's paragraphs
(supporting + distractor, no curation) are ingested under
deterministic per-paragraph source ids::

    musique-<variant>-<row_id>-p<idx>

Per-paragraph ids (rather than RGB's per-row grouping) keep the
paragraph ``idx`` recoverable from a JAMES citation filename, which
is what the ``support_idx_recall`` axis needs the runner to
translate (musique_scorer.py module docstring).

Paired-comparability note: ``eval.external.base.take_sample`` is a
deterministic first-N slice, so running this script with
``--max-rows N`` ingests exactly the rows the bench runner will
query with ``--n-samples N``.

Self-eval trap rule (memory ``feedback_self_evaluation_trap``):
this script reads the published MuSiQue fixture verbatim — no
rewriting, no curation, no re-labelling. Distractor paragraphs are
ingested alongside supporting ones exactly as published.

Usage (operator)::

    JAMES_WORKSPACE=./workspaces/cycle_gamma_musique_ans \
    python scripts/research/cycle_gamma_musique_corpus_build.py \
        --variant ans --split dev \
        --workspace ./workspaces/cycle_gamma_musique_ans \
        --max-rows 25
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


def _read_musique_fixture(path: Path, max_rows=None) -> list:
    """Read the official JSONL fixture (one JSON object per line).
    Bad lines are skipped, mirroring ``MuSiQueLoader.iter_queries``."""
    rows: list = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict):
                continue
            rows.append(entry)
            if max_rows is not None and len(rows) >= max_rows:
                break
    return rows


def _ingest_row(vector_store, row: dict, *, variant: str) -> int:
    """Ingest one row's paragraphs. Returns paragraph count ingested."""
    row_id = str(row.get("id", "noid")).strip() or "noid"
    paragraphs = row.get("paragraphs") or []
    if not isinstance(paragraphs, list):
        return 0

    n = 0
    for i, p in enumerate(paragraphs):
        if not isinstance(p, dict):
            continue
        text = str(p.get("paragraph_text", "")).strip()
        if not text:
            continue
        title = str(p.get("title", ""))
        idx = p.get("idx")
        idx = int(idx) if isinstance(idx, int) else i
        is_supporting = bool(p.get("is_supporting"))
        # Title prepended the way MuSiQue's own context rendering
        # does — the published paragraph is (title, text).
        doc = f"{title}\n{text}" if title else text
        vector_store.add_documents_with_meta(
            [doc],
            source=f"musique-{variant}-{row_id}-p{idx}",
            metadata={
                "category":      f"musique-{variant}-paragraph",
                "source_type":   "prod",
                "paragraph_idx": idx,
                "is_supporting": is_supporting,
            },
        )
        n += 1
    return n


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="cycle_gamma_musique_corpus_build",
        description=(
            "Build a JAMES workspace whose corpus mirrors MuSiQue "
            "paragraphs (supporting + distractor, verbatim). Sets "
            "JAMES_WORKSPACE so the VectorStore writes to the chosen "
            "workspace path."
        ),
    )
    p.add_argument("--variant", default="ans", choices=("ans", "full"),
                    help="MuSiQue variant (default: ans)")
    p.add_argument("--split", default="dev",
                    choices=("train", "dev", "test"),
                    help="dataset split (default: dev)")
    p.add_argument("--workspace", required=True,
                    help="path to the workspace root (chroma_db lives "
                          "at <workspace>/chroma_db/)")
    p.add_argument("--fixture", default=None,
                    help="path to musique_<variant>_v1.0_<split>.jsonl "
                          "(default: eval/external/_fixtures/musique/)")
    p.add_argument("--max-rows", type=int, default=None,
                    help="ingest only the first N rows — MUST equal the "
                          "bench runner's --n-samples for paired "
                          "comparability (take_sample is first-N)")
    p.add_argument("--progress-every", type=int, default=5,
                    help="print progress every N rows (default 5)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)

    root = _resolve_root()
    workspace = Path(args.workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    # Set JAMES_WORKSPACE BEFORE importing core/config. The resolver
    # in core.plugins.workspace reads it at import time.
    os.environ["JAMES_WORKSPACE"] = str(workspace)

    default_fixture = (root / "eval" / "external" / "_fixtures"
                        / "musique"
                        / f"musique_{args.variant}_v1.0_{args.split}.jsonl")
    fixture_path = (Path(args.fixture).resolve() if args.fixture
                    else default_fixture)
    if not fixture_path.exists():
        print(f"!! fixture not found: {fixture_path}", file=sys.stderr)
        print("   download via StonyBrookNLP/musique download_data.sh "
                "and place the official-format JSONL there "
                "(or pass --fixture).", file=sys.stderr)
        return 2

    # UTF-8 console safety on Windows.
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                    errors="replace")

    rows = _read_musique_fixture(fixture_path, max_rows=args.max_rows)

    print(f"=== cycle γ MuSiQue corpus build ===")
    print(f"  workspace : {workspace}")
    print(f"  fixture   : {fixture_path}  (rows={len(rows)})")
    print(f"  variant   : {args.variant}  split: {args.split}")
    print(f"  max-rows  : {args.max_rows}")
    print()

    # Late import so JAMES_WORKSPACE is honoured.
    sys.path.insert(0, str(root))
    from core.vector_store import VectorStore

    vector_store = VectorStore()
    n_para_total = 0
    t0 = time.time()

    for i, row in enumerate(rows, 1):
        n_para_total += _ingest_row(vector_store, row,
                                      variant=args.variant)
        if (i % max(args.progress_every, 1) == 0
                or i == len(rows)):
            elapsed = time.time() - t0
            print(f"  [{i}/{len(rows)}] {elapsed:.0f}s — "
                    f"paragraphs={n_para_total}", flush=True)

    elapsed = time.time() - t0
    final_count = vector_store.count()
    print()
    print(f"=== INGESTION COMPLETE ===")
    print(f"  rows processed   : {len(rows)}")
    print(f"  paragraphs added : {n_para_total}")
    print(f"  vector store count: {final_count}")
    print(f"  elapsed          : {elapsed:.1f}s")
    print(f"  workspace        : {workspace}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
