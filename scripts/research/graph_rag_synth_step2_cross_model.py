"""v0.6 — Graph-RAG synthesis Step 2 cross-model driver.

Per `docs/evaluation/v0.5-graph-rag-contribution.md` §7 ("Single
model (M_M = gemma4:e4b 4B) for Table 3.1. Cross-model … is the
immediate next measurement cycle if needed").

This script is a **thin wrapper** around the existing
:mod:`scripts.qvt_ablation_matrix` runner that pins the Step 2
scope: 3 sector cells (`C_rag-basic` / `C_rag-graph` /
`C_rag-ontology`) × 2 new tiers (`M_S` = gemma3:4b, `M_L` =
gemma3:12b) × n=3 paired, on the `multihop_rag` fixture.

C_minus is intentionally NOT re-run at cross-model — the n=1 sanity
from Step 0 establishes the no-RAG floor and that floor doesn't
shift with model size in any meaningful way for the synthesis
question (the question is "what does the JAMES stack add on top of
basic RAG?"). Skipping C_minus saves ~30 min of wall time across
both tiers.

The wrapper exists so the operator can launch Step 2 with a single
command + a known invocation. It does NOT run the matrix in this
process — it `subprocess.run`'s `qvt_ablation_matrix` so the
runner's existing per-cell server-spawn / shutdown / aggregation
pipeline stays the authoritative path.

## Usage

::

    python scripts/research/graph_rag_synth_step2_cross_model.py

    # Or pick a single new tier:
    python scripts/research/graph_rag_synth_step2_cross_model.py \\
        --tiers M_S

    # Dry-run to see the exact subprocess invocation that would run:
    python scripts/research/graph_rag_synth_step2_cross_model.py --dry-run

## Wall time estimate

Per Step 1's actual time (`docs/evaluation/v0.5-graph-rag-
contribution.md` §8): 3 cells × n=3 paired ≈ 5h on M_M. M_S is
~25 % faster (smaller model); M_L is ~2 × slower (12b vs 4b).

Aggregate Step 2 estimate: 5h × 0.75 + 5h × 2 = **~14h wall** for
both new tiers. Operator should launch overnight + check artifact
JSONs the next morning.

## Output

Cell JSONs land in the same directory the matrix runner uses:
``workspaces/hotpot_eval/reports/research-runs/qvt-ablation-cells/
qvt-ablation-cell-<row>-<tier>.json``

Aggregator (manual step after both tiers complete): compare each
cell's ``aggregate.mean`` deltas against the Step 1 M_M deltas and
fill Table 3.2 in the synthesis doc.

## What this script does NOT do

* Does NOT auto-update the synthesis doc — that's a human review
  step after the operator inspects the cross-model deltas
* Does NOT run M_XS / M_XL / M_MIXTRAL / M_CLOUD — Step 2 scope
  is the two interior tiers that bracket M_M (one smaller, one
  larger). Extreme-end tiers are a Step 3+ decision
* Does NOT measure C_minus on the cross-model tiers — see the
  module docstring rationale
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Sequence

ROOT = Path(__file__).resolve().parent.parent.parent


# Step 2 scope — pinned per `docs/evaluation/v0.5-graph-rag-
# contribution.md` §7. The 3 cells are the load-bearing ones for
# the "Graph-RAG contribution" comparison (basic → graph) +
# "typed-filter contribution" (graph → ontology).
_STEP_2_SECTOR_CELLS = ("C_rag-basic", "C_rag-graph", "C_rag-ontology")

# Cross-model tiers — Step 1 was M_M (4B); Step 2 brackets M_M with
# M_S (smaller, 4B different family) + M_L (12B). Cycle γ Phase E-min
# showed 3-model bracketing (mxtral / gemma4 / llama) was sufficient
# to confirm trade-off stability without burning compute on every
# scale point.
_STEP_2_TIERS_DEFAULT = ("M_S", "M_L")

# Fixture — multihop_rag is the same one Step 1 used; the cross-time
# path_coverage agreement at M_M (α-6 0.408 ↔ Step 1 0.4056) was
# only demonstrated on this fixture.
_STEP_2_SUITE = "multihop_rag"

# n=3 paired — locked per the synthesis doc + n=1 inflation rule
# (`memory/feedback_n1_verdict_inflation_n3_caught.md`).
_STEP_2_N_RUNS = 3


def _build_subprocess_argv(
    tiers: Sequence[str],
    sector_cells: Sequence[str],
    suite: str,
    n_runs: int,
) -> List[str]:
    """Compose the `qvt_ablation_matrix` invocation.

    Returns the argv list ready for ``subprocess.run`` — does NOT
    actually invoke it (the caller decides whether to dry-run or
    run).
    """
    return [
        sys.executable,
        str(ROOT / "scripts" / "qvt_ablation_matrix.py"),
        "--suite", suite,
        "--tiers", ",".join(tiers),
        "--sector-cells", ",".join(sector_cells),
        "--n-runs", str(n_runs),
    ]


def _build_env(workspace_rel: str) -> dict:
    """Return an environment dict with `JAMES_WORKSPACE` pinned.

    The synthesis doc §8 reproducibility block scopes the runner to
    ``workspaces/hotpot_eval`` so the Chroma collection + cell-JSON
    output directory are the same ones Step 1 used. Pinning it here
    means an operator who forgets to set the env still gets the
    right workspace.
    """
    env = dict(os.environ)
    env["JAMES_WORKSPACE"] = str(ROOT / workspace_rel)
    return env


def _parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="graph_rag_synth_step2_cross_model",
        description=(
            "Run Step 2 cross-model graph-RAG synthesis ablation. "
            "Defaults to M_S + M_L × 3 sector cells × n=3 on "
            "multihop_rag."
        ),
    )
    p.add_argument(
        "--tiers",
        default=",".join(_STEP_2_TIERS_DEFAULT),
        help=(
            "Comma-separated tier ids (default: M_S,M_L). Pass a "
            "single tier to launch only one half of Step 2."
        ),
    )
    p.add_argument(
        "--sector-cells",
        default=",".join(_STEP_2_SECTOR_CELLS),
        help=(
            "Comma-separated sector cells (default: C_rag-basic,"
            "C_rag-graph,C_rag-ontology — the 3 load-bearing cells "
            "for the synthesis-doc Table 3.2)."
        ),
    )
    p.add_argument(
        "--suite",
        default=_STEP_2_SUITE,
        help=f"Fixture suite (default: {_STEP_2_SUITE}).",
    )
    p.add_argument(
        "--n-runs",
        type=int,
        default=_STEP_2_N_RUNS,
        help=f"Paired runs per cell (default: {_STEP_2_N_RUNS}).",
    )
    p.add_argument(
        "--workspace",
        default="workspaces/hotpot_eval",
        help=(
            "Relative workspace path under repo root. Pins "
            "JAMES_WORKSPACE so the runner writes to the same "
            "cell-JSON directory Step 1 used."
        ),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Print the subprocess invocation that would run + exit. "
            "Use this to verify the command shape before launching "
            "the multi-hour measurement."
        ),
    )
    return p.parse_args(argv)


def main(argv: List[str] = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    tiers = [t.strip() for t in args.tiers.split(",") if t.strip()]
    cells = [c.strip() for c in args.sector_cells.split(",") if c.strip()]
    if not tiers:
        print("error: --tiers must be non-empty", file=sys.stderr)
        return 2
    if not cells:
        print("error: --sector-cells must be non-empty", file=sys.stderr)
        return 2

    cmd = _build_subprocess_argv(tiers, cells, args.suite, args.n_runs)
    env = _build_env(args.workspace)

    if args.dry_run:
        print("# Step 2 cross-model invocation (dry-run)")
        print(f"# JAMES_WORKSPACE={env['JAMES_WORKSPACE']}")
        print(" ".join(cmd))
        print()
        print("# Wall time estimate: ~14h for default 2 tiers × 3 cells × n=3.")
        print("# Output: workspaces/hotpot_eval/reports/research-runs/")
        print("#         qvt-ablation-cells/qvt-ablation-cell-<row>-<tier>.json")
        return 0

    print(f"Launching Step 2 cross-model with tiers={tiers} cells={cells}")
    print(f"JAMES_WORKSPACE={env['JAMES_WORKSPACE']}")
    print()
    return subprocess.run(cmd, env=env).returncode


if __name__ == "__main__":
    raise SystemExit(main())
