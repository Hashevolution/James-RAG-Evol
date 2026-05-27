"""F9 (LEO L.D follow-up, 2026-05-27) — query_rewriter concept-anchor audit.

Measures whether the production ``core.retrieval.query_rewriter.QueryRewriter``
adds **concept anchors** when rewriting bare proper-noun queries.

Background — the q15 8-cycle diagnosis chain
--------------------------------------------

BL-9 (#534 + #536) confirmed bge-m3 embedding swap is active but the
q15 acceptance gate ("David Soria Parra가 누구야?" → MCP PDF in top-10)
still fails. Direct chroma probe (post-swap, 5 variations):

    "David Soria Parra"                    → not in top-20
    "David Soria Parra가 누구야?"           → not in top-20
    "MCP 설계자 David Soria Parra"          → rank 1, score 0.81
    "Anthropic MCP 공개"                    → rank 1, score 0.78
    "MCP designer Anthropic Justin..."      → rank 1, score 0.76

→ The MCP PDF chunk contains "David Soria Parra와 Justin Spahr-Summers"
in ~80 chars of ~2 KB; the chunk vector is dominated by concept tokens
(MCP / Model Context Protocol / Anthropic / JSON-RPC). ANY 1024-dim
multilingual pooling embedding has the same weakness — concept anchor
in the **query** is the missing piece, not embedding model capacity.

JAMES already has a ``QueryRewriter`` at pipeline STEP 0.5b (gated by
``JAMES_ENABLE_QUERY_REWRITE=1``). The rewriter's Korean prompt asks
the LLM to "strengthen keywords with 1-2 synonyms" — but says NOTHING
about concept anchors. This audit measures whether the prompt's
synonym-only instruction is enough to cover the proper-noun case, or
whether the prompt (or a separate step) needs an explicit
concept-anchor expansion instruction.

What this audit does NOT do
---------------------------

- **No production change.** The rewriter prompt + wiring stays
  byte-identical. This script reads.
- **No corpus-aware fix.** We measure the prompt's behaviour on a
  fixed fixture; we do NOT add corpus-aware anchor generation here.
  That fix lands at F9.2 once this audit pins what the prompt
  currently produces.
- **No ablation of the embedding model.** BL-9 already covered that
  (the swap is active; q15 still fails). This audit's variable is
  **the rewriter prompt**, not the encoder.

Fixture buckets
---------------

Four buckets exercise the four shapes the production query stream
mixes. Each row carries an ``expected_anchors`` list — the set of
corpus tokens that, if any one appears in the rewritten text, would
bridge the query vector to the matching chunk vectors per the BL-9
post-swap probe.

  1. **bare_proper_noun** — q15-shape. The diagnosis cluster. Should
     get concept anchors added; currently does not (hypothesis).
  2. **name_with_concept** — control: anchor already in original.
     Rewriter should preserve, not strip.
  3. **pure_concept** — control: no person name involved. Rewriter
     should leave the concept-side query stable (the bge-m3 swap
     already handles these).
  4. **multi_hop_control** — q2-shape ("팔란티어의 CEO 누구"). Person
     name PLUS company concept implicit in the query. Should already
     work without anchor expansion; included to detect regression
     when F9.2 introduces an expansion step.

Anchor-presence heuristic
-------------------------

Case-insensitive substring match: an anchor counts as "added" if any
member of ``expected_anchors`` appears in the rewritten text but did
NOT appear in the original. We deliberately use a strict "not present
in original" guard so the ``name_with_concept`` bucket scores
correctly — its anchors already exist in the original, so the rewriter
"preserving" them must NOT count as "adding".

Each run produces ``reports/research-runs/query-rewriter-audit-
<stamp>.json`` with per-query rows + per-bucket aggregates.

Pre-requisites
--------------
- Ollama service reachable.
- ``JAMES_LLM_MODEL`` set to the tag you want audited (the audit
  records this so reruns are diffable).

Usage
-----
    python scripts/research/query_rewriter_audit.py
    python scripts/research/query_rewriter_audit.py --with-entity-anchor

The ``--with-entity-anchor`` arm (F9.2) runs each query through
``EntityAnchorExpander.expand()`` BEFORE the LLM rewriter sees it.
A/B against the default arm by running both and diffing the
two ``query-rewriter-audit-<stamp>.json`` outputs — the F9.2
acceptance criterion is that the ``bare_proper_noun`` bucket's
``anchor_added_rate`` rises from the ~0% default-arm baseline to
≥ 67% (2 of 3 q15-cluster queries gain a corpus anchor).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

try:
    from utils.console import ensure_utf8_console
    ensure_utf8_console()
except Exception:
    pass


REPORTS_DIR = ROOT / "reports" / "research-runs"


# ─── Fixture ─────────────────────────────────────────────────────────
#
# Tied to the current corpus (MCP PDF + Palantir wiki + finance docs).
# When the corpus shifts substantially, refresh this fixture so the
# anchor sets continue to reflect the actual concept tokens the
# matching chunk vectors carry. The fixture stays inline (rather than
# a JSON file) because this audit's value is measurement-correctness
# of the heuristic over a known-good ground truth — splitting fixture
# from check would make drift silent.
#
# Anchors are case-insensitive substrings. We list the minimal
# bridging tokens, not exhaustive context — the heuristic is "at
# least one anchor present", so a smaller curated set is more
# diagnostic than a broad keyword list.

_FIXTURE: List[Dict] = [
    # ─── bucket 1: bare_proper_noun (the q15 cluster) ──────────────
    {
        "id":               "bpn-1",
        "bucket":           "bare_proper_noun",
        "text":             "David Soria Parra가 누구야?",
        "expected_anchors": ["MCP", "Model Context Protocol", "Anthropic"],
        "notes":            "step7 v4 q15 exact form — the primary diagnosis case",
    },
    {
        "id":               "bpn-2",
        "bucket":           "bare_proper_noun",
        "text":             "David Soria Parra",
        "expected_anchors": ["MCP", "Model Context Protocol", "Anthropic"],
        "notes":            "name-only — strictest variant",
    },
    {
        "id":               "bpn-3",
        "bucket":           "bare_proper_noun",
        "text":             "Justin Spahr-Summers는 누구야?",
        "expected_anchors": ["MCP", "Model Context Protocol", "Anthropic"],
        "notes":            "co-author of MCP — same chunk, same anchor set",
    },

    # ─── bucket 2: name_with_concept (already-working baseline) ────
    {
        "id":               "nwc-1",
        "bucket":           "name_with_concept",
        "text":             "MCP 설계자 David Soria Parra",
        "expected_anchors": ["MCP", "Model Context Protocol", "Anthropic"],
        "notes":            "BL-9 post-swap rank 1 reference — anchor already in original",
    },
    {
        "id":               "nwc-2",
        "bucket":           "name_with_concept",
        "text":             "Anthropic의 David Soria Parra",
        "expected_anchors": ["MCP", "Model Context Protocol", "Anthropic"],
        "notes":            "company-side anchor — same effect",
    },

    # ─── bucket 3: pure_concept (no person — control) ──────────────
    {
        "id":               "pc-1",
        "bucket":           "pure_concept",
        "text":             "MCP가 뭐야?",
        "expected_anchors": ["MCP", "Model Context Protocol", "Anthropic"],
        "notes":            "no name involved — concept-only baseline",
    },
    {
        "id":               "pc-2",
        "bucket":           "pure_concept",
        "text":             "Model Context Protocol 설명",
        "expected_anchors": ["MCP", "Model Context Protocol", "Anthropic"],
        "notes":            "EN concept — bge-m3 should handle directly",
    },

    # ─── bucket 4: multi_hop_control (q2-shape — already works) ────
    {
        "id":               "mhc-1",
        "bucket":           "multi_hop_control",
        "text":             "팔란티어의 CEO는 누구야?",
        "expected_anchors": ["Palantir", "Karp", "Alex Karp", "CEO"],
        "notes":            "step7 q2 — company + role embedded, name to be retrieved",
    },
    {
        "id":               "mhc-2",
        "bucket":           "multi_hop_control",
        "text":             "Anthropic의 창립자는 누구야?",
        "expected_anchors": ["Anthropic", "Amodei", "founder"],
        "notes":            "company-name carries concept anchor by itself",
    },
]


# ─── Anchor heuristic ────────────────────────────────────────────────


def _anchors_in_text(text: str, anchors: List[str]) -> List[str]:
    """Return anchors that appear (case-insensitive substring) in text.

    Substring rather than word-boundary because Korean/English mixed
    text has no whitespace between Hangul and Latin tokens
    ("MCP설계자" is one token visually, "MCP" is the anchor). A
    word-boundary regex would miss those.
    """
    if not text:
        return []
    low = text.lower()
    found = []
    for a in anchors:
        if a and a.lower() in low:
            found.append(a)
    return found


def _classify_anchor_outcome(
    original: str,
    rewritten: str,
    anchors: List[str],
) -> Dict:
    """Per-row anchor outcome classification.

    Three states for an anchor:
      - **already_present**: in original AND in rewritten (preserved)
      - **added**: in rewritten but NOT in original (the F9 win
        signal)
      - **dropped**: in original but NOT in rewritten (regression
        signal — rewriter stripped a working anchor)
      - **absent**: in neither (no-op)

    Returns dict with anchor lists per state + ``added_count`` aggregate
    used by the summary for "% of queries that got at least one anchor
    added".
    """
    in_original  = set(_anchors_in_text(original,  anchors))
    in_rewritten = set(_anchors_in_text(rewritten, anchors))
    return {
        "anchors_already_present": sorted(in_original  & in_rewritten),
        "anchors_added":           sorted(in_rewritten - in_original),
        "anchors_dropped":         sorted(in_original  - in_rewritten),
        "anchors_absent":          sorted(set(anchors) - in_original - in_rewritten),
        "added_count":             len(in_rewritten - in_original),
        "dropped_count":           len(in_original  - in_rewritten),
    }


# ─── Per-row audit ───────────────────────────────────────────────────


def _entity_anchor_pre_expand(query: str) -> Dict:
    """F9.2 — run the query through ``EntityAnchorExpander`` first.

    Returns a dict with the entity-anchor pre-rewrite outcome:
      - ``pre_expanded``: query text fed into the LLM rewriter
        (= original when the expander returns no hit)
      - ``entity_anchors_added``: list of corpus anchors injected by
        the graph lookup
      - ``entity_anchor_hit``: True iff the graph found at least one
        novel anchor for this query
      - ``entity_anchor_latency_ms``: the ~0ms graph lookup cost
        (recorded for operator comparison against the LLM rewriter's
        per-call cost)
    """
    from core.retrieval.entity_anchor_expander import get_entity_anchor_expander

    expander = get_entity_anchor_expander()
    t0 = time.time()
    try:
        expanded, anchors, hit = expander.expand(query)
        err: Optional[str] = None
    except Exception as e:
        expanded, anchors, hit = query, [], False
        err = f"{type(e).__name__}: {str(e)[:200]}"
    latency_ms = int((time.time() - t0) * 1000)
    out = {
        "pre_expanded":             expanded,
        "entity_anchors_added":     anchors,
        "entity_anchor_hit":        hit,
        "entity_anchor_latency_ms": latency_ms,
    }
    if err:
        out["entity_anchor_error"] = err
    return out


def _audit_one(row: Dict, *, with_entity_anchor: bool = False) -> Dict:
    """Run one query through ``QueryRewriter.rewrite(force=True)``.

    When ``with_entity_anchor`` is True, the query is first passed
    through ``EntityAnchorExpander`` (F9.2). The LLM rewriter then
    sees the pre-expanded form. Anchor outcome classification still
    compares against the **original** query text — so anchors added
    by the entity expander count toward ``anchors_added`` just like
    anchors added by the LLM rewriter would.
    """
    from core.retrieval.query_rewriter import QueryRewriter

    if with_entity_anchor:
        pre = _entity_anchor_pre_expand(row["text"])
        query_for_rewriter = pre["pre_expanded"]
    else:
        pre = {}
        query_for_rewriter = row["text"]

    rewriter = QueryRewriter()
    t0 = time.time()
    try:
        rewritten, latency_ms, attempted = rewriter.rewrite(
            query_for_rewriter, force=True,
        )
        err: Optional[str] = None
    except Exception as e:
        rewritten, latency_ms, attempted = query_for_rewriter, 0, False
        err = f"{type(e).__name__}: {str(e)[:200]}"
    elapsed_s = time.time() - t0

    # Anchor outcome compares the **original** query (row["text"])
    # against the final rewritten form. The entity expander's
    # additions count toward "added" just like LLM-added anchors
    # would, so the F9.2 A/B remains apples-to-apples vs the
    # F9.1 baseline.
    outcome = _classify_anchor_outcome(
        row["text"], rewritten, row["expected_anchors"],
    )
    changed = rewritten != row["text"]

    out: Dict = {
        "id":                       row["id"],
        "bucket":                   row["bucket"],
        "text":                     row["text"],
        "expected_anchors":         row["expected_anchors"],
        "rewritten":                rewritten,
        "changed":                  changed,
        "attempted":                attempted,
        "latency_ms":               latency_ms,
        "elapsed_s":                round(elapsed_s, 2),
        "anchors_already_present":  outcome["anchors_already_present"],
        "anchors_added":            outcome["anchors_added"],
        "anchors_dropped":          outcome["anchors_dropped"],
        "anchors_absent":           outcome["anchors_absent"],
    }
    if pre:
        # Surface the entity-anchor step's contribution distinctly
        # from the LLM rewriter's so the operator can attribute
        # wins/losses to the right layer.
        out["entity_anchor"] = pre
    if err:
        out["error"] = err
    return out


def _print_row(r: Dict) -> None:
    if r.get("error"):
        tag = "X "
    elif r["anchors_added"]:
        tag = "+ "
    elif r["anchors_dropped"]:
        tag = "- "
    elif r["anchors_already_present"]:
        tag = "= "
    else:
        tag = "_ "
    added = ",".join(r["anchors_added"]) or "-"
    text_short = (r["text"][:48] + "...") if len(r["text"]) > 48 else r["text"]
    rew_short  = (r["rewritten"][:48] + "...") if len(r["rewritten"]) > 48 else r["rewritten"]
    print(
        f"  {tag} {r['id']:<6s} {r['bucket']:<19s} added={added:<28s} "
        f"({r['latency_ms']:>5d}ms) {text_short!r} → {rew_short!r}"
    )


def _bucket_summary(rows: List[Dict]) -> Dict[str, Dict]:
    """Per-bucket aggregates: anchor-add rate + drop rate + attempted rate."""
    by_bucket: Dict[str, List[Dict]] = {}
    for r in rows:
        by_bucket.setdefault(r["bucket"], []).append(r)
    out: Dict[str, Dict] = {}
    for bucket, items in by_bucket.items():
        n = len(items)
        with_added   = sum(1 for r in items if r["anchors_added"])
        with_dropped = sum(1 for r in items if r["anchors_dropped"])
        attempted    = sum(1 for r in items if r["attempted"])
        changed      = sum(1 for r in items if r["changed"])
        latencies    = [r["latency_ms"] for r in items if r["attempted"]]
        out[bucket] = {
            "n":               n,
            "attempted":       attempted,
            "changed":         changed,
            "anchor_added":    with_added,
            "anchor_dropped":  with_dropped,
            "anchor_added_rate":   round(with_added / n, 3) if n else 0.0,
            "anchor_dropped_rate": round(with_dropped / n, 3) if n else 0.0,
            "latency_ms_mean":     round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
        }
    return out


# ─── CLI ─────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "F9 query_rewriter concept-anchor audit. Runs the fixture "
            "through QueryRewriter (force=True) and reports per-bucket "
            "anchor-add rate."
        ),
    )
    ap.add_argument(
        "--bucket", default=None,
        help="run only one bucket (bare_proper_noun / name_with_concept / pure_concept / multi_hop_control)",
    )
    ap.add_argument(
        "--with-entity-anchor", action="store_true",
        help=(
            "F9.2 arm — pre-expand each query through the EntityAnchorExpander "
            "(corpus graph lookup) before the LLM rewriter sees it. A/B against "
            "the default arm by running twice and diffing the two JSON outputs."
        ),
    )
    args = ap.parse_args()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    fixture = _FIXTURE
    if args.bucket:
        fixture = [r for r in fixture if r["bucket"] == args.bucket]
        if not fixture:
            print(f"[audit] no rows match bucket={args.bucket!r}")
            return 1

    model_tag = os.environ.get("JAMES_LLM_MODEL", "<unset — backend default>")
    embedding_tag = os.environ.get("JAMES_EMBEDDING_MODEL", "<unset — legacy MiniLM>")
    arm = "with-entity-anchor (F9.2)" if args.with_entity_anchor else "rewriter-only (F9.1 baseline)"
    print(
        f"=== query_rewriter audit — arm={arm}, model={model_tag}, "
        f"embedding={embedding_tag}, rows={len(fixture)} ==="
    )

    rows: List[Dict] = []
    for r in fixture:
        out = _audit_one(r, with_entity_anchor=args.with_entity_anchor)
        rows.append(out)
        _print_row(out)

    # ─── summary ────────────────────────────────────────────────────
    bucket_summary = _bucket_summary(rows)

    overall_n           = len(rows)
    overall_attempted   = sum(1 for r in rows if r["attempted"])
    overall_added       = sum(1 for r in rows if r["anchors_added"])
    overall_dropped     = sum(1 for r in rows if r["anchors_dropped"])
    overall_changed     = sum(1 for r in rows if r["changed"])
    method_counts = Counter(
        ("error" if r.get("error") else ("attempted" if r["attempted"] else "skipped"))
        for r in rows
    )

    summary = {
        "rows":                overall_n,
        "attempted":           overall_attempted,
        "changed":             overall_changed,
        "anchor_added":        overall_added,
        "anchor_dropped":      overall_dropped,
        "anchor_added_rate":   round(overall_added / overall_n, 3) if overall_n else 0.0,
        "anchor_dropped_rate": round(overall_dropped / overall_n, 3) if overall_n else 0.0,
        "outcome_distribution": dict(method_counts),
        "by_bucket":           bucket_summary,
    }

    print()
    print("=== Summary ===")
    print(f"  rows:                {overall_n}")
    print(f"  attempted:           {overall_attempted}")
    print(f"  changed:             {overall_changed}")
    print(f"  anchor_added:        {overall_added} ({summary['anchor_added_rate']*100:.1f}%)")
    print(f"  anchor_dropped:      {overall_dropped} ({summary['anchor_dropped_rate']*100:.1f}%)")
    print(f"  outcome:             {summary['outcome_distribution']}")
    print()
    print("  By bucket:")
    for bucket, s in bucket_summary.items():
        print(
            f"    {bucket:<19s} n={s['n']} attempted={s['attempted']} "
            f"added={s['anchor_added']}/{s['n']} ({s['anchor_added_rate']*100:.0f}%) "
            f"dropped={s['anchor_dropped']}/{s['n']} ({s['anchor_dropped_rate']*100:.0f}%) "
            f"latency_mean={s['latency_ms_mean']:.0f}ms"
        )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    arm_suffix = "-entityanchor" if args.with_entity_anchor else ""
    out_path = REPORTS_DIR / f"query-rewriter-audit{arm_suffix}-{stamp}.json"
    out_path.write_text(
        json.dumps(
            {
                "generated_at":          datetime.now().isoformat(),
                "arm":                   "with_entity_anchor" if args.with_entity_anchor else "rewriter_only",
                "model_tag":             model_tag,
                "embedding_tag":         embedding_tag,
                "results":               rows,
                "summary":               summary,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nsaved: {out_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
