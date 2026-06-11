"""LRB v0.2.3 S3 publication-scale runner.

Wraps `scripts/research/lrb_run_phase_b.py::run_scenario` to point at
an S3 fixture (smoke / dev / publication) and emit the same per-SUT
result.json + bench.jsonl artifacts the Phase B runner produces. Phase
B logic is reused verbatim — same SUTs (vanilla / naive-supersede /
james), same scorer (deterministic time-travel axes), same per-category
breakdown.

Usage::

    python scripts/research/lrb_run_s3.py --scale smoke
    python scripts/research/lrb_run_s3.py --scale publication
    python scripts/research/lrb_run_s3.py --scale publication --k 10

Honest tier: results inherit the **Phase B token-mode honest-tier**
(deterministic axes, no LLM grounding). S3 publication is a scale
robustness check against the S2 ⭐⭐⭐ cross-model published cell — paper
publish-ready claim requires the verdict matrix in the prereg §2.

Pre-reg: `docs/research/lrb-v023-s3-publication-scale-preregistration-2026-06-12.md`
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Force UTF-8 stdout on Windows so the verdict prints survive cp949
# code pages.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from scripts.research.lrb_run_phase_b import (gap_table_print,                                                   # noqa: E402
                                              per_category_compare,
                                              run_scenario, utc_stamp)


FIXTURE_DIR = ROOT / "eval" / "external" / "_fixtures" / "lrb"
SCALE_TO_FIXTURE = {
    "smoke":       FIXTURE_DIR / "scenario_S3_smoke.json",
    "dev":         FIXTURE_DIR / "scenario_S3_dev.json",
    "publication": FIXTURE_DIR / "scenario_S3_publication.json",
}
OUT_DIR = ROOT / "reports" / "external" / "lrb"


def main() -> None:
    p = argparse.ArgumentParser(
        description="LRB S3 publication-scale runner")
    p.add_argument(
        "--scale", default="smoke", choices=list(SCALE_TO_FIXTURE.keys()),
        help=("scale preset: smoke (CI-safe; 100 docs / ~280 events / "
              "100 queries; <60s wall), dev (300 docs / ~1.2k events / "
              "300 queries; ~3-5 min), publication (1000 docs / ~5.6k "
              "events / 1000 queries; ~30-60 min). Must match a "
              "previously-generated fixture."),
    )
    p.add_argument("--k", type=int, default=10)
    p.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = p.parse_args()

    fixture_path = SCALE_TO_FIXTURE[args.scale]
    if not fixture_path.exists():
        print(f"ERROR: fixture {fixture_path} not found.")
        print(f"Generate first: python scripts/research/"
              f"build_lrb_scenario_s3.py --scale {args.scale}")
        sys.exit(1)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    ts = utc_stamp()
    scenario_label = f"S3-{args.scale}"

    print(f"=== LRB S3 runner ({args.scale}) ===")
    print(f"  fixture: {fixture_path}")
    print(f"  k:       {args.k}")
    print(f"  ts:      {ts}")

    # Phase B logic reused verbatim — same SUTs, same scorer.
    s3 = run_scenario(fixture_path, scenario_label, phase="B",
                      ts=ts, out_dir=args.out_dir, k=args.k)
    gap_table_print(s3, f"{scenario_label} (S3 publication-scale)")
    per_category_compare(s3, scenario_label)

    # S3 verdict (Phase B 'CROSS-SCENARIO VERDICT' style, single-scenario).
    # Honest framing: published S2 cross-model claim is R@1 V<N<J. The
    # temporal_accuracy axis suffers from Phase B's known inversion
    # paradox (vanilla looks artificially good on current-* queries
    # because the latest doc is what 'vanilla' retrieves and those are
    # the current-valid ones); R@1 is the publication-tier axis.
    print("\n=== S3 VERDICT (per prereg sec 2) ===")
    print("Hypothesis: R@1 V<N<J pattern reproduces at publication "
          "scale (vs S2 claude cell V=0.6125 N=0.775 J=0.975).")
    ts_axis = "temporal_accuracy"
    v = s3["vanilla"]["axes"]["overall"][ts_axis]
    n = s3["naive-supersede"]["axes"]["overall"][ts_axis]
    j = s3["james"]["axes"]["overall"][ts_axis]
    print(f"\n  temporal_accuracy:  V={v:.4f}  N={n:.4f}  J={j:.4f}")
    print("    (Phase B inversion paradox: V>N expected on current-* "
          "weighted; R@1 is the publication axis)")

    r1_v = s3["vanilla"]["axes"]["overall"]["exploratory"]["R@1"]
    r1_n = s3["naive-supersede"]["axes"]["overall"]["exploratory"]["R@1"]
    r1_j = s3["james"]["axes"]["overall"]["exploratory"]["R@1"]
    print(f"\n  R@1 (PUBLICATION AXIS): "
          f"V={r1_v:.4f}  N={r1_n:.4f}  J={r1_j:.4f}")
    print(f"    pattern V<=N: {r1_v <= r1_n}   N<=J: {r1_n <= r1_j}   "
          f"V<N<J: {r1_v < r1_n < r1_j}")

    # Verdict matrix (per prereg sec 2) — R@1 driven.
    r1_strict = r1_v < r1_n < r1_j
    s2_claude = {"v": 0.6125, "n": 0.775, "j": 0.975}
    delta_v = abs(r1_v - s2_claude["v"])
    delta_n = abs(r1_n - s2_claude["n"])
    delta_j = abs(r1_j - s2_claude["j"])
    max_delta = max(delta_v, delta_n, delta_j)
    within_band = max_delta <= 0.05
    print("\n  verdict:")
    if r1_strict and within_band:
        print(f"    *** publication-tier scale robustness ***  "
              f"R@1 V<N<J pattern preserved + magnitude within "
              f"+/-0.05 band of S2 claude cell (max delta={max_delta:.4f})")
    elif r1_strict:
        print(f"    ** scale-sensitivity finding **  "
              f"R@1 pattern preserved (V<N<J) but magnitudes differ "
              f"(max delta vs S2 = {max_delta:.4f}; rerun on smaller "
              f"scale or check vocabulary load-balance)")
    else:
        print("    * scale-attribution finding *  R@1 V<N<J pattern "
              "broken at publication scale (S2 publish-ready result "
              "stands; scale-attribution requires separate cycle)")

    print(f"\n  artifacts in: {args.out_dir}")
    print(f"  scenario: {scenario_label}, ts: {ts}")


if __name__ == "__main__":
    main()
