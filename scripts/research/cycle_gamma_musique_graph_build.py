"""Cycle γ D4 — build the entity graph on the MuSiQue workspace.

The cycle γ MuSiQue corpus build (cycle_gamma_musique_corpus_build.py)
filled the vector store but NOT the entity graph — the JAMES graph layer
(run_loop_1_expand) had 0 entities, so all six prior multi-hop
measurements ran on a graph-less stack. This script runs JAMES's own
entity-extraction pipeline (process_document_for_entities) over the same
MuSiQue paragraphs so the graph layer is actually populated.

Pre-registration: docs/research/cycle-gamma-d4-graph-traversal-preregistration-2026-06-10.md

Isolated: writes only to the workspace named by JAMES_WORKSPACE
(cycle_gamma_musique_ans). Production graph (BASE_DIR/wiki) untouched.

Usage:
    JAMES_WORKSPACE=./workspaces/cycle_gamma_musique_ans \
    JAMES_LLM_MODEL=gemma4:e4b \
    python scripts/research/cycle_gamma_musique_graph_build.py \
        --variant ans --split dev --max-rows 25
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


def _read_musique(path: Path, max_rows=None) -> list:
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
            if isinstance(entry, dict):
                rows.append(entry)
            if max_rows is not None and len(rows) >= max_rows:
                break
    return rows


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="cycle_gamma_musique_graph_build")
    p.add_argument("--variant", default="ans", choices=("ans", "full"))
    p.add_argument("--split", default="dev", choices=("train", "dev", "test"))
    p.add_argument("--fixture", default=None)
    p.add_argument("--max-rows", type=int, default=25)
    p.add_argument("--progress-every", type=int, default=10)
    args = p.parse_args(argv)

    if not os.environ.get("JAMES_WORKSPACE"):
        print("!! JAMES_WORKSPACE must be set (isolation). Refusing to "
                "run against the production graph.", file=sys.stderr)
        return 2

    root = _resolve_root()
    sys.path.insert(0, str(root))
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                    errors="replace")

    fixture = (Path(args.fixture).resolve() if args.fixture
               else root / "eval" / "external" / "_fixtures" / "musique"
                    / f"musique_{args.variant}_v1.0_{args.split}.jsonl")
    if not fixture.exists():
        print(f"!! fixture not found: {fixture}", file=sys.stderr)
        return 2

    rows = _read_musique(fixture, max_rows=args.max_rows)

    from core.graph_engine import GraphEngine
    g = GraphEngine()
    wg = g.wiki_generator

    print("=== cycle γ MuSiQue graph build ===")
    print(f"  workspace : {os.environ['JAMES_WORKSPACE']}")
    print(f"  fixture   : {fixture}  (rows={len(rows)})")
    print(f"  model     : {os.environ.get('JAMES_LLM_MODEL', 'default')}")
    print()

    n_para = 0
    n_entities = 0
    t0 = time.time()
    for i, row in enumerate(rows, 1):
        row_id = str(row.get("id", "noid")).strip() or "noid"
        paragraphs = row.get("paragraphs") or []
        for j, para in enumerate(paragraphs):
            if not isinstance(para, dict):
                continue
            text = str(para.get("paragraph_text", "")).strip()
            if not text:
                continue
            title = str(para.get("title", ""))
            idx = para.get("idx")
            idx = int(idx) if isinstance(idx, int) else j
            doc = f"{title}\n{text}" if title else text
            source_id = f"musique-{args.variant}-{row_id}-p{idx}"
            try:
                ids = wg.process_document_for_entities(
                    source_id, doc, [],
                    user_role="admin",
                    metadata={"source_type": "prod",
                              "category": f"musique-{args.variant}-paragraph"},
                )
                n_entities += len(list(ids) if ids else [])
            except Exception as e:
                print(f"  !! {source_id}: {e}", file=sys.stderr)
            n_para += 1
        if i % max(args.progress_every, 1) == 0 or i == len(rows):
            el = time.time() - t0
            print(f"  [{i}/{len(rows)}] {el:.0f}s — paras={n_para} "
                    f"entities={n_entities}", flush=True)

    el = time.time() - t0
    print()
    print("=== GRAPH BUILD COMPLETE ===")
    print(f"  rows={len(rows)}  paragraphs={n_para}  entities={n_entities}")
    print(f"  elapsed={el:.0f}s ({el/60:.1f} min)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
