"""Cycle γ Phase C.3 — ALCE smoke run.

Drives the locked smoke per the pre-registration
(``docs/research/cycle-gamma-c3-alce-smoke-preregistration-2026-06-11.md``):

  - bench    = ``alce``, variant = ``asqa``
  - producer = ``ALCEClosedCorpusProducer`` (Ollama Gemma)
  - verifier = ``StringContainmentVerifier(min_overlap=0.5)``  (fallback,
               NOT ALCE-grade — pre-reg §1.1)
  - n_samples = 20
  - n_docs    = 5  (top-5 from ALCE's published retrieval)
  - honest_tier = "infrastructure-only"

Writes:
  reports/external/alce/asqa-smoke-<ts>.result.json
  reports/external/alce/asqa-smoke-<ts>.bench.jsonl

Usage::

    python scripts/research/alce_smoke_run.py
    python scripts/research/alce_smoke_run.py --model mixtral:8x7b
    python scripts/research/alce_smoke_run.py --n 5     # quick check
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from eval.external.alce_loader import ALCELoader
from eval.external.alce_producer import ALCEClosedCorpusProducer
from eval.external.alce_scorer import ALCEScorer, StringContainmentVerifier
from eval.external.runner import run_external_bench, write_result


def _fixture_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="alce_smoke_run")
    p.add_argument("--model", default="gemma4:e4b",
                   help="Ollama model id (default: gemma4:e4b)")
    p.add_argument("--n", type=int, default=20,
                   help="n_samples (pre-reg locked at 20)")
    p.add_argument("--n-docs", type=int, default=5,
                   help="top-k passages per question (ALCE default 5)")
    p.add_argument("--max-tokens", type=int, default=1024)
    p.add_argument("--out-dir", default=str(ROOT / "reports" / "external" / "alce"))
    args = p.parse_args(argv)

    loader = ALCELoader(variant="asqa")
    verifier = StringContainmentVerifier(min_overlap=0.5)
    scorer = ALCEScorer(variant="asqa", verifier=verifier)
    producer = ALCEClosedCorpusProducer(
        model=args.model,
        n_docs=args.n_docs,
        max_tokens=args.max_tokens,
    )

    fixture_sha = _fixture_sha(loader.cache_path)

    print(f"[alce-smoke] model    = {args.model}")
    print(f"[alce-smoke] n        = {args.n}")
    print(f"[alce-smoke] n_docs   = {args.n_docs}")
    print(f"[alce-smoke] verifier = {verifier.name} "
          f"(is_alce_grade={verifier.is_alce_grade})")
    print(f"[alce-smoke] fixture  = {loader.cache_path.name}")
    print(f"[alce-smoke]   sha    = {fixture_sha[:16]}…")

    def _progress(i, total, elapsed):
        rate = elapsed / max(i, 1)
        eta = rate * (total - i)
        print(f"[alce-smoke]   {i}/{total} "
              f"({elapsed:.1f}s elapsed, ~{eta:.0f}s eta)")

    result = run_external_bench(
        loader=loader,
        scorer=scorer,
        producer=producer,
        split="dev",
        n_samples=args.n,
        progress_every=5,
        on_progress=_progress,
    )

    # Annotate result with pre-reg gate info so the JSON is self-
    # describing without operators needing to cross-reference the
    # pre-reg doc.
    result["honest_tier"] = (
        "infrastructure-only: smoke n=" + str(args.n) +
        " with StringContainmentVerifier fallback. NOT ALCE-grade. "
        "Pre-reg: docs/research/cycle-gamma-c3-alce-smoke-"
        "preregistration-2026-06-11.md"
    )
    result["verifier_grade"] = "fallback-string-containment"
    result["fixture_sha"] = fixture_sha
    result["n_docs_per_query"] = args.n_docs

    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / f"asqa-smoke-{stamp}.result.json"
    bench_path  = out_dir / f"asqa-smoke-{stamp}.bench.jsonl"

    write_result(result, result_path)
    with open(bench_path, "w", encoding="utf-8") as f:
        for row in result["rows"]:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            f.write("\n")

    print()
    print("[alce-smoke] AXES:")
    for axis in result["axes"]:
        print(f"  {axis['name']:>20s} = {axis['score']}   "
              f"(n_queries={axis['n_queries']})")
        if axis.get("notes"):
            print(f"    notes: {axis['notes']}")
    print()
    print(f"[alce-smoke] result -> {result_path}")
    print(f"[alce-smoke] rows   -> {bench_path}")
    print(f"[alce-smoke] errors = {result['n_errors']} / "
          f"{result['n_queries']}")
    print(f"[alce-smoke] elapsed = {result['elapsed_s']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
