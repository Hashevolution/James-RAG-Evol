"""Retrieval-side quality metrics — NDCG@k and MRR.

δ-1 cycle deliverable (2026-06-03). Closes a long-standing gap: JAMES
bench measures graded_answer / abstention_f1 / path_coverage but NEVER
isolated *retrieval-side* quality. When a cycle's typed-filter Δ is
near-zero, we couldn't disambiguate "filter broken" from "retrieval
ceiling already reached" because no metric quantified the retrieval
layer in isolation.

Now we can. Given any bench JSON + matching fixture, compute:

  NDCG@k  — Normalized Discounted Cumulative Gain
            Binary relevance (in expected_path.nodes / not).
            Cap k = configurable, default 5.
            Range [0, 1]; 1.0 = perfect ranking up to k.

  MRR     — Mean Reciprocal Rank
            Rank of first relevant doc per query, harmonic mean.
            Range [0, 1]; 1.0 = first hit is always relevant.

  Hits@k  — Recall at k (sanity; what fraction of gold landed in top-k).

Reusable across step7 / multihop_rag / null_v1 fixtures — anywhere the
fixture declares `expected_path.nodes` for at least some queries.
Queries with no expected_path (e.g., abstention-only null queries with
empty `nodes: []`) are skipped from the average; reported as
"queries_without_gold".

Slug normalization mirrors `eval/qvt/oracle.py:_slug_for_match` so a
query's `sources` field (filenames) matches expected_path.nodes
(article titles or entity names) the same way the rest of the QVT
framework does.

Usage::

    python scripts/research/retrieval_quality.py \\
        --bench reports/bench_<sha>_step7_<ts>.json \\
        --fixture eval/regression/step7_queries.json \\
        [--k 5] [--output reports/research-runs/retrieval-quality-<ts>.md]

    # Or compare two bench runs:
    python scripts/research/retrieval_quality.py --compare \\
        --baseline reports/bench_<sha>_old.json \\
        --candidate reports/bench_<sha>_new.json \\
        --fixture eval/regression/step7_queries.json
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

sys.stdout.reconfigure(encoding="utf-8")


# ─── Slug normalization (mirror of eval/qvt/oracle.py:_slug_for_match) ──

_SOURCE_PREFIX_RE = re.compile(r"^multihop_\d+_")
_SLUG_BAD_RE = re.compile(r"[^a-z0-9\-]+")
_SLUG_MAX = 80


def _slug(s: str) -> str:
    if not s:
        return ""
    s = s.strip()
    s = _SOURCE_PREFIX_RE.sub("", s)
    if s.lower().endswith((".txt", ".pdf")):
        s = s[:-4]
    s = s.lower()
    s = _SLUG_BAD_RE.sub("-", s).strip("-")
    return s[:_SLUG_MAX]


# ─── Core metrics ──────────────────────────────────────────────────────


def ndcg_at_k(retrieved_slugs: List[str], gold_slugs: set, k: int) -> float:
    """Binary-relevance NDCG@k.

    retrieved_slugs: list of slugs in retrieval order (rank 1 first).
    gold_slugs: set of relevant slugs.
    k: cap rank for evaluation.

    Returns NDCG in [0, 1]. Returns 0.0 when gold_slugs is empty (no
    relevant doc → no signal).

    Each gold item is credited AT MOST ONCE — a duplicate match (e.g.,
    same PDF appearing twice in the sources list) does not accumulate
    DCG. Otherwise NDCG could exceed 1.0 when retrieval over-returns
    duplicates against a small gold set.
    """
    if not gold_slugs:
        return 0.0
    # DCG: sum of (rel_i / log2(i+1)) — i is 1-indexed; we use log2(i+1)
    # for i starting at 1 to give rank 1 a discount of log2(2)=1.
    # Track which golds we've already credited so duplicates don't
    # accumulate.
    dcg = 0.0
    credited: set = set()
    for i, slug in enumerate(retrieved_slugs[:k], start=1):
        if slug in gold_slugs and slug not in credited:
            dcg += 1.0 / math.log2(i + 1)
            credited.add(slug)
    # IDCG: ideal ranking has all min(k, |gold|) relevant at top
    n_ideal = min(k, len(gold_slugs))
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, n_ideal + 1))
    return dcg / idcg if idcg > 0 else 0.0


def reciprocal_rank(retrieved_slugs: List[str], gold_slugs: set) -> float:
    """Reciprocal rank of first relevant doc. Returns 0.0 if none."""
    if not gold_slugs:
        return 0.0
    for i, slug in enumerate(retrieved_slugs, start=1):
        if slug in gold_slugs:
            return 1.0 / i
    return 0.0


def hits_at_k(retrieved_slugs: List[str], gold_slugs: set, k: int) -> float:
    """Recall@k: fraction of gold slugs found in top-k retrieved."""
    if not gold_slugs:
        return 0.0
    top_k_set = set(retrieved_slugs[:k])
    return len(gold_slugs & top_k_set) / len(gold_slugs)


# ─── Per-query extraction ──────────────────────────────────────────────


def _extract_retrieved_slugs(result: dict) -> List[str]:
    """From a bench result row, extract retrieved doc slugs in rank order.

    Uses `sources` field (the citation list from the answer pipeline).
    bench.py emits this as a list of source filenames in retrieval order.
    Empty slugs (from punctuation-only / non-ascii-only source names)
    are filtered to avoid spurious matches against empty gold slugs.
    """
    sources = result.get("sources") or []
    out = []
    for s in sources:
        if not isinstance(s, str):
            continue
        slug = _slug(s)
        if slug:  # drop empties
            out.append(slug)
    return out


def _extract_gold_slugs(query: dict) -> set:
    """From a fixture query row, extract gold slug set.

    Empty slugs (slug() returning "") are filtered — happens when a
    fixture node is pure punctuation / non-ASCII characters that strip
    to nothing.
    """
    ep = query.get("expected_path") or {}
    nodes = ep.get("nodes") or []
    out = {_slug(n) for n in nodes if isinstance(n, str) and n.strip()}
    out.discard("")
    return out


# ─── Aggregate scoring ─────────────────────────────────────────────────


def score_bench(bench: dict, fixture: dict, k: int = 5) -> Dict:
    """Compute per-query and aggregate retrieval metrics.

    Returns:
        {
          "n_queries": int,
          "queries_with_gold": int,
          "queries_without_gold": int,
          "ndcg@k": float,
          "mrr": float,
          "hits@k": float,
          "per_query": [{id, ndcg, rr, hits, n_gold, ...}, ...]
        }
    """
    qmap = {q["id"]: q for q in fixture.get("queries", [])
            if isinstance(q, dict) and "id" in q}
    per_query = []
    ndcg_sum = 0.0
    mrr_sum = 0.0
    hits_sum = 0.0
    n_scored = 0
    n_no_gold = 0

    for r in bench.get("results", []):
        if not isinstance(r, dict):
            continue
        qid = r.get("id")
        fq = qmap.get(qid, {})
        gold_slugs = _extract_gold_slugs(fq)
        retrieved = _extract_retrieved_slugs(r)
        if not gold_slugs:
            n_no_gold += 1
            per_query.append({
                "id": qid,
                "skipped": True,
                "reason": "no gold expected_path",
            })
            continue
        ndcg = ndcg_at_k(retrieved, gold_slugs, k)
        rr = reciprocal_rank(retrieved, gold_slugs)
        hk = hits_at_k(retrieved, gold_slugs, k)
        ndcg_sum += ndcg
        mrr_sum += rr
        hits_sum += hk
        n_scored += 1
        per_query.append({
            "id": qid,
            "ndcg": round(ndcg, 4),
            "rr": round(rr, 4),
            "hits": round(hk, 4),
            "n_gold": len(gold_slugs),
            "n_retrieved": len(retrieved),
        })

    return {
        "n_queries": len(bench.get("results", [])),
        "queries_with_gold": n_scored,
        "queries_without_gold": n_no_gold,
        "k": k,
        "ndcg@k": round(ndcg_sum / n_scored, 4) if n_scored else 0.0,
        "mrr": round(mrr_sum / n_scored, 4) if n_scored else 0.0,
        "hits@k": round(hits_sum / n_scored, 4) if n_scored else 0.0,
        "per_query": per_query,
    }


# ─── Report renderer ───────────────────────────────────────────────────


def render_single(bench_path: str, fixture_path: str, k: int = 5) -> str:
    bench = json.load(open(bench_path, encoding="utf-8"))
    fixture = json.load(open(fixture_path, encoding="utf-8"))
    result = score_bench(bench, fixture, k=k)
    lines = []
    add = lines.append
    add(f"# Retrieval Quality — {Path(bench_path).name}")
    add("")
    add(f"> Generated: {datetime.now().isoformat(timespec='seconds')}  ")
    add(f"> bench: `{bench_path}`  ")
    add(f"> fixture: `{fixture_path}`  ")
    add(f"> k = {k}")
    add("")
    add("## Aggregate")
    add("")
    add(f"- Queries total:       {result['n_queries']}")
    add(f"- Queries with gold:   {result['queries_with_gold']}")
    add(f"- Queries no gold:     {result['queries_without_gold']}  (skipped)")
    add(f"- **NDCG@{k}**:         **{result['ndcg@k']:.4f}**")
    add(f"- **MRR**:             **{result['mrr']:.4f}**")
    add(f"- **Hits@{k}**:        **{result['hits@k']:.4f}**")
    add("")
    add("## Per-query")
    add("")
    add("| id | ndcg | rr | hits | gold | retrieved |")
    add("|---:|---:|---:|---:|---:|---:|")
    for pq in result["per_query"]:
        if pq.get("skipped"):
            add(f"| {pq['id']} | — | — | — | (no gold) | — |")
        else:
            add(f"| {pq['id']} | {pq['ndcg']:.3f} | {pq['rr']:.3f} | "
                f"{pq['hits']:.3f} | {pq['n_gold']} | {pq['n_retrieved']} |")
    add("")
    return "\n".join(lines)


def render_compare(
    baseline_path: str, candidate_path: str, fixture_path: str,
    label_baseline: str, label_candidate: str, k: int = 5,
) -> str:
    bench_b = json.load(open(baseline_path, encoding="utf-8"))
    bench_c = json.load(open(candidate_path, encoding="utf-8"))
    fixture = json.load(open(fixture_path, encoding="utf-8"))
    rb = score_bench(bench_b, fixture, k=k)
    rc = score_bench(bench_c, fixture, k=k)

    lines = []
    add = lines.append
    add(f"# Retrieval Quality Δ — {label_baseline} vs {label_candidate}")
    add("")
    add(f"> Generated: {datetime.now().isoformat(timespec='seconds')}  ")
    add(f"> baseline:  `{baseline_path}`  ")
    add(f"> candidate: `{candidate_path}`  ")
    add(f"> fixture:   `{fixture_path}`  ")
    add(f"> k = {k}")
    add("")
    add("## Aggregate Δ (candidate − baseline)")
    add("")
    add(f"| Metric | {label_baseline} | {label_candidate} | Δ |")
    add("|---|---:|---:|---:|")
    for metric in ["ndcg@k", "mrr", "hits@k"]:
        b_v = rb[metric]
        c_v = rc[metric]
        d = c_v - b_v
        sign = "+" if d >= 0 else ""
        add(f"| {metric} | {b_v:.4f} | {c_v:.4f} | **{sign}{d:.4f}** |")
    add("")
    add(f"- Queries scored (baseline / candidate): "
        f"{rb['queries_with_gold']} / {rc['queries_with_gold']}")
    add("")

    # Per-query Δ (focusing on movers)
    pq_b = {p["id"]: p for p in rb["per_query"] if not p.get("skipped")}
    pq_c = {p["id"]: p for p in rc["per_query"] if not p.get("skipped")}
    common = set(pq_b.keys()) & set(pq_c.keys())
    improved = []
    regressed = []
    for qid in common:
        d_ndcg = pq_c[qid]["ndcg"] - pq_b[qid]["ndcg"]
        if d_ndcg > 0.05:
            improved.append((qid, d_ndcg, pq_b[qid], pq_c[qid]))
        elif d_ndcg < -0.05:
            regressed.append((qid, d_ndcg, pq_b[qid], pq_c[qid]))

    add("## Per-query Δ (NDCG threshold ±0.05)")
    add("")
    add(f"- ✅ improved (NDCG+0.05+): **{len(improved)}** queries")
    add(f"- ❌ regressed (NDCG−0.05+): **{len(regressed)}** queries")
    add(f"- ⚪ unchanged: {len(common) - len(improved) - len(regressed)}")
    add("")
    if improved:
        add("### Top improved")
        add("")
        add("| id | Δndcg | base ndcg | cand ndcg | base rr | cand rr |")
        add("|---:|---:|---:|---:|---:|---:|")
        for qid, d, b, c in sorted(improved, key=lambda x: -x[1])[:10]:
            add(f"| {qid} | {d:+.3f} | {b['ndcg']:.3f} | {c['ndcg']:.3f} | "
                f"{b['rr']:.3f} | {c['rr']:.3f} |")
        add("")
    if regressed:
        add("### Top regressed")
        add("")
        add("| id | Δndcg | base ndcg | cand ndcg | base rr | cand rr |")
        add("|---:|---:|---:|---:|---:|---:|")
        for qid, d, b, c in sorted(regressed, key=lambda x: x[1])[:10]:
            add(f"| {qid} | {d:+.3f} | {b['ndcg']:.3f} | {c['ndcg']:.3f} | "
                f"{b['rr']:.3f} | {c['rr']:.3f} |")
        add("")
    return "\n".join(lines)


# ─── CLI ───────────────────────────────────────────────────────────────


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--bench", help="Bench JSON path (single mode)")
    parser.add_argument("--baseline", help="Baseline bench JSON (compare mode)")
    parser.add_argument("--candidate", help="Candidate bench JSON (compare mode)")
    parser.add_argument("--fixture", required=True, help="Fixture JSON path")
    parser.add_argument("--k", type=int, default=5, help="Cap rank (default 5)")
    parser.add_argument("--label-baseline", default="baseline")
    parser.add_argument("--label-candidate", default="candidate")
    parser.add_argument("--compare", action="store_true",
                        help="Compare mode (needs --baseline + --candidate)")
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)

    if args.compare:
        if not args.baseline or not args.candidate:
            parser.error("--compare needs --baseline and --candidate")
        report = render_compare(
            args.baseline, args.candidate, args.fixture,
            args.label_baseline, args.label_candidate, args.k,
        )
    else:
        if not args.bench:
            parser.error("--bench required (or use --compare)")
        report = render_single(args.bench, args.fixture, args.k)

    print(report)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"\n[wrote] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
