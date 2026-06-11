"""Cycle γ Phase C.4 — 2WikiMultiHopQA smoke run.

Drives the locked smoke per the pre-registration
(``docs/research/cycle-gamma-c4-2wiki-smoke-preregistration-2026-06-11.md``):

  - bench    = ``2wiki``, split = ``dev``
  - producer = ``ClosedCorpusGemmaProducer`` (Ollama Gemma, all 10
               2Wiki paragraphs in the prompt)
  - scorer   = ``WikiMultiScorer`` (em / f1 / f1_by_type;
               support_fact_f1 is "not measured" by design — the
               closed-corpus producer doesn't emit
               predicted_supporting_facts)
  - n_samples = 20
  - honest_tier = "infrastructure-only"

Writes:
  reports/external/2wiki/dev-smoke-<ts>.result.json
  reports/external/2wiki/dev-smoke-<ts>.bench.jsonl

Usage::

    python scripts/research/wiki2_smoke_run.py
    python scripts/research/wiki2_smoke_run.py --model mixtral:8x7b
    python scripts/research/wiki2_smoke_run.py --n 5     # quick check
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

from eval.external.wikimulti_loader import WikiMultiLoader
from eval.external.wikimulti_scorer import WikiMultiScorer
from eval.external.runner import (
    ClosedCorpusGemmaProducer,
    run_external_bench,
    write_result,
)


def _fixture_sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="wiki2_smoke_run")
    p.add_argument("--model", default="gemma4:e4b",
                   help="Ollama model id (default: gemma4:e4b)")
    p.add_argument("--n", type=int, default=20,
                   help="n_samples (pre-reg locked at 20)")
    p.add_argument("--max-tokens", type=int, default=1024)
    p.add_argument("--out-dir",
                   default=str(ROOT / "reports" / "external" / "2wiki"))
    args = p.parse_args(argv)

    loader = WikiMultiLoader(split="dev")
    scorer = WikiMultiScorer()
    producer = ClosedCorpusGemmaProducer(
        model=args.model,
        max_tokens=args.max_tokens,
        # 2Wiki's 10 paragraphs total well under the 100k char cap
        # already in the base producer; no need to override.
    )

    fixture_sha = _fixture_sha(loader.cache_path)

    print(f"[2wiki-smoke] model    = {args.model}")
    print("[2wiki-smoke] split    = dev")
    print(f"[2wiki-smoke] n        = {args.n}")
    print(f"[2wiki-smoke] producer = {producer.name}")
    print(f"[2wiki-smoke] fixture  = {loader.cache_path.name}")
    print(f"[2wiki-smoke]   sha    = {fixture_sha[:16]}…")

    def _progress(i, total, elapsed):
        rate = elapsed / max(i, 1)
        eta = rate * (total - i)
        print(f"[2wiki-smoke]   {i}/{total} "
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

    # Pre-reg-annotated metadata so the result JSON is self-describing.
    result["honest_tier"] = (
        "infrastructure-only: smoke n=" + str(args.n) + " with "
        "ClosedCorpusGemmaProducer. NOT publication. "
        "Pre-reg: docs/research/cycle-gamma-c4-2wiki-smoke-"
        "preregistration-2026-06-11.md"
    )
    result["fixture_sha"] = fixture_sha
    result["scope"] = {
        "producer_emits_supporting_facts": False,
        "support_fact_f1_axis": "not measured by design",
        "comparable_to_musique_magnitude": False,
        "cross_bench_claim": "multi-hop floor pattern qualitative agreement only",
    }

    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path = out_dir / f"dev-smoke-{stamp}.result.json"
    bench_path  = out_dir / f"dev-smoke-{stamp}.bench.jsonl"

    write_result(result, result_path)
    with open(bench_path, "w", encoding="utf-8") as f:
        for row in result["rows"]:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            f.write("\n")

    print()
    print("[2wiki-smoke] AXES:")
    for axis in result["axes"]:
        print(f"  {axis['name']:>20s} = {axis['score']}   "
              f"(n_queries={axis['n_queries']})")
        if axis.get("notes"):
            print(f"    notes: {axis['notes']}")
    print()
    print(f"[2wiki-smoke] result -> {result_path}")
    print(f"[2wiki-smoke] rows   -> {bench_path}")
    print(f"[2wiki-smoke] errors = {result['n_errors']} / "
          f"{result['n_queries']}")
    print(f"[2wiki-smoke] elapsed = {result['elapsed_s']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
