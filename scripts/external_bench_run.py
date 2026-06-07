"""Cycle γ Phase A.5 — unified external-benchmark runner (CLI shim).

Thin argparse wrapper around :mod:`eval.external.runner`. All the
plumbing logic lives in the module (testable, importable); this file
only translates CLI arguments into runner kwargs and emits the
result JSON.

Examples
--------

Phase B smoke (20 queries through closed-corpus Gemma)::

    JAMES_WORKSPACE=./workspaces/cycle_gamma_eval \\
    python scripts/external_bench_run.py \\
        --bench rgb --variant en \\
        --mode closed-corpus --model gemma4:e4b \\
        --n-samples 20 \\
        --out reports/cycle_gamma/rgb-en-smoke.json

Full closed-corpus ALCE-ASQA run::

    python scripts/external_bench_run.py \\
        --bench alce --variant asqa \\
        --mode closed-corpus --model gemma4:e4b \\
        --out reports/cycle_gamma/alce-asqa-closed.json

Full JAMES-stack 2WikiMultiHopQA dev run::

    JAMES_WORKSPACE=./workspaces/cycle_gamma_eval \\
    python scripts/external_bench_run.py \\
        --bench 2wiki --split dev \\
        --mode james --model gemma4:e4b \\
        --out reports/cycle_gamma/2wiki-james.json
"""
from __future__ import annotations

import argparse
import io
import os
import sys
import time
from pathlib import Path

# Stream-safe UTF-8 on Windows consoles.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.external.runner import (
    ClosedCorpusGemmaProducer,
    JamesEngineProducer,
    SUPPORTED_BENCHES,
    build_loader,
    build_scorer,
    run_external_bench,
    write_result,
)


def _build_producer(args: argparse.Namespace):
    if args.mode == "closed-corpus":
        return ClosedCorpusGemmaProducer(
            model=args.model,
            max_tokens=args.max_tokens,
            timeout=args.timeout,
            think=args.think,
        )
    if args.mode == "james":
        return JamesEngineProducer(
            model=args.model,
            response_style=args.response_style,
        )
    raise SystemExit(f"unknown mode: {args.mode!r}")


def _progress_printer(i: int, n: int, elapsed: float) -> None:
    print(f"  [{i}/{n}] {elapsed:.0f}s elapsed", flush=True)


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="external_bench_run",
        description=(
            "Cycle γ unified runner: dispatch one external benchmark "
            "through JAMES (or a closed-corpus baseline) and emit one "
            "cross-bench JSON result."
        ),
    )
    p.add_argument("--bench", required=True, choices=SUPPORTED_BENCHES,
                    help="external benchmark to run")
    p.add_argument("--variant", default=None,
                    help="benchmark variant (rgb: en/zh/..., alce: asqa/"
                          "qampari/eli5, musique: ans/full); 2wiki has "
                          "no variant")
    p.add_argument("--split", default="dev",
                    help="benchmark split (musique/2wiki); ignored "
                          "elsewhere. Default: dev.")
    p.add_argument("--cache-dir", default=None,
                    help="loader cache directory (default: each loader's "
                          "_fixtures/ tree)")
    p.add_argument("--allow-download", action="store_true",
                    help="permit live GitHub download (RGB only); other "
                          "benches must be pre-downloaded by the operator")
    p.add_argument("--mode", choices=("closed-corpus", "james"),
                    default="closed-corpus",
                    help="producer mode (default: closed-corpus)")
    p.add_argument("--model", default=os.environ.get("PROOF_MODEL",
                                                      "gemma4:e4b"),
                    help="model id (Ollama tag for closed-corpus; "
                          "JAMES selected_model for james)")
    p.add_argument("--response-style", default="",
                    help="JAMES response style override (james mode only)")
    p.add_argument("--n-samples", type=int, default=None,
                    help="cap on the number of queries (Phase B smoke)")
    p.add_argument("--max-tokens", type=int, default=8192,
                    help="closed-corpus max_tokens (default 8192)")
    p.add_argument("--timeout", type=int, default=180,
                    help="closed-corpus per-call timeout in seconds")
    p.add_argument("--think", action="store_true",
                    help="closed-corpus think=True (default False)")
    p.add_argument("--out", required=True,
                    help="output JSON path (parents created if needed)")
    p.add_argument("--progress-every", type=int, default=10,
                    help="print progress every N queries (default 10)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    loader = build_loader(
        args.bench,
        variant=args.variant,
        split=args.split,
        cache_dir=Path(args.cache_dir) if args.cache_dir else None,
        allow_download=args.allow_download,
    )
    scorer = build_scorer(args.bench, variant=args.variant)
    producer = _build_producer(args)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(
        f"=== cycle γ external bench: bench={args.bench} "
        f"variant={args.variant or '(default)'} split={args.split} "
        f"mode={args.mode} model={args.model} "
        f"n_samples={args.n_samples or 'ALL'} ===",
        flush=True,
    )

    t0 = time.time()
    result = run_external_bench(
        loader=loader,
        scorer=scorer,
        producer=producer,
        split=args.split,
        n_samples=args.n_samples,
        progress_every=args.progress_every,
        on_progress=_progress_printer,
    )
    elapsed = time.time() - t0

    final = write_result(result, out_path)
    print(f"\n=== RESULT (bench={result['benchmark']}, "
            f"n={result['n_queries']}, errors={result['n_errors']}, "
            f"elapsed={elapsed:.1f}s) ===")
    for axis in result["axes"]:
        notes = (axis["notes"] or "").strip().splitlines()[0] if axis["notes"] else ""
        notes_tail = f"  // {notes[:80]}" if notes else ""
        print(f"  {axis['name']:24s} {axis['score']:.4f}  "
                f"(n={axis['n_queries']}){notes_tail}")
    print(f"\nsaved: {os.path.relpath(final, ROOT)}")
    return 0 if result["n_errors"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
