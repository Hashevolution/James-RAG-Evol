"""Cycle γ Phase D — JAMES component ablation matrix runner.

Wraps `scripts/external_bench_run.py` to run the 7-knob ablation
matrix sequentially with consistent output naming + progress log.

Background: Phase B+C measured a per-query JAMES abstention set on
RGB-en negrej (mxtral / llama → {3, 9, 14, 15, 17, 18}). Phase D
isolates which JAMES component emits the abstention signal by
ablating one component at a time via existing α-6 env-var knobs.

Design + interpretation rules:
``docs/design/v0.4-cycle-gamma-phase-d-mechanistic-ablation.md``.

Usage (operator-gated, ~30-90 min depending on model):

    JAMES_WORKSPACE=./workspaces/cycle_gamma_rgb_negrej \\
    python scripts/research/cycle_gamma_phase_d_ablate.py \\
        --model mixtral:8x7b \\
        --n-samples 25 \\
        --out-dir reports/cycle_gamma/phase-d/

The runner writes 7 JSON files (one per ablation knob) plus a
``_summary.md`` table comparing each ablation's abstention set
against the full-JAMES reference.

Self-eval trap rule (memory ``feedback_self_evaluation_trap.md``):
- Reference R0 (full-JAMES, no ablation) is read from the existing
  Phase C artifact at
  ``reports/cycle_gamma/rgb-en-james-negrej-<model>-20260608.json``
  if present. The runner does NOT re-run the reference because
  doing so would invalidate the comparison (different env state).
- If the reference is absent, the runner declines to start and
  prints the prerequisite command.

Eval-cycle vs collab-arc rule (memory
``feedback_eval_cycle_vs_collab_arc_separation.md``):
- This is JAMES-internal Phase D evaluation. Output is NOT joint
  piece content. The output files stay under ``reports/cycle_gamma/
  phase-d/`` (gitignored).
"""
from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional


# 7 ablation knobs in the order they should run.
ABLATION_KNOBS: tuple = (
    "JAMES_DISABLE_RAG_RETRIEVAL",
    "JAMES_DISABLE_RERANK",
    "JAMES_DISABLE_GRAPH",
    "JAMES_DISABLE_TYPED_FILTER",
    "JAMES_DISABLE_COGNITIVE_STAGES",
    "JAMES_DISABLE_VERIFY",
    "JAMES_DISABLE_ABSTENTION",
)


def _resolve_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _reference_path(model: str) -> Path:
    """Where the Phase C reference (R0, full-JAMES) lives."""
    model_slug = model.replace(":", "-")
    # Phase C artifact filename pattern from this session:
    # rgb-en-james-negrej-llama-20260608.json
    # rgb-en-james-negrej-mixtral-20260608.json
    # rgb-en-james-negrej-gemma3-12b-20260608.json
    # rgb-en-james-negrej-20260608.json   (gemma4:e4b)
    candidates = [
        f"reports/cycle_gamma/rgb-en-james-negrej-{model_slug}-20260608.json",
    ]
    # gemma4:e4b reference dropped the slug:
    if "gemma4" in model_slug or "e4b" in model_slug:
        candidates.append("reports/cycle_gamma/rgb-en-james-negrej-20260608.json")
    # llama/mixtral/gemma3-12b common slugs:
    if "llama" in model_slug:
        candidates.append("reports/cycle_gamma/rgb-en-james-negrej-llama-20260608.json")
    if "mixtral" in model_slug or "mxtral" in model_slug:
        candidates.append("reports/cycle_gamma/rgb-en-james-negrej-mixtral-20260608.json")
    if "gemma3-12b" in model_slug or "gemma3:12b" in model:
        candidates.append("reports/cycle_gamma/rgb-en-james-negrej-gemma3-12b-20260608.json")
    root = _resolve_root()
    for c in candidates:
        p = root / c
        if p.exists():
            return p
    return root / candidates[0]   # path even if missing, for diagnostic


def _read_ref_axes(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data


def _run_one_ablation(
    *,
    knob: str,
    model: str,
    out_dir: Path,
    n_samples: int,
    workspace: Path,
    progress_every: int,
    dry_run: bool,
) -> Path:
    """Run one ablation. Returns the output JSON path."""
    model_slug = model.replace(":", "-")
    knob_slug = knob.replace("JAMES_DISABLE_", "").lower()
    out_path = out_dir / f"phase-d-{model_slug}-{knob_slug}.json"

    cmd = [
        sys.executable,
        "scripts/external_bench_run.py",
        "--bench", "rgb",
        "--variant", "en",
        "--mode", "james",
        "--model", model,
        "--setting-filter", "negative_rejection",
        "--n-samples", str(n_samples),
        "--progress-every", str(progress_every),
        "--out", str(out_path),
    ]

    env = dict(os.environ)
    env["JAMES_WORKSPACE"] = str(workspace)
    env[knob] = "1"

    print(f"\n=== Phase D ablation: {knob}=1 model={model} ===",
          flush=True)
    print(f"  out  : {out_path}", flush=True)
    if dry_run:
        print(f"  cmd  : {' '.join(cmd)}", flush=True)
        print(f"  env  : JAMES_WORKSPACE={env['JAMES_WORKSPACE']} "
              f"{knob}=1", flush=True)
        print("  DRY RUN — not executed.", flush=True)
        return out_path

    t0 = time.time()
    result = subprocess.run(cmd, env=env)
    elapsed = time.time() - t0
    if result.returncode != 0:
        print(f"!! Ablation {knob} exited with code {result.returncode} "
              f"after {elapsed:.0f}s", flush=True)
    else:
        print(f"  ablation {knob} OK ({elapsed:.0f}s)", flush=True)
    return out_path


def _emit_summary(
    *,
    model: str,
    out_dir: Path,
    knob_results: List[tuple],
    reference_path: Path,
) -> Path:
    """Write phase-d/_summary.md with a comparison table."""
    summary_path = out_dir / "_summary.md"
    lines: List[str] = []
    lines.append(f"# Cycle γ Phase D ablation summary — model {model}")
    lines.append("")
    lines.append(f"Reference R0 (full-JAMES): "
                  f"`{reference_path.relative_to(_resolve_root())}`")
    lines.append("")
    ref_data = _read_ref_axes(reference_path)
    if ref_data is None:
        lines.append("⚠️ Reference file not found. Re-run Phase C "
                     "full-JAMES negrej first.")
    else:
        for ax in ref_data.get("axes", []):
            if ax["name"] == "negative_rejection_f1":
                lines.append(f"R0 negative_rejection_f1: "
                              f"**{ax['score']:.4f}** "
                              f"(per_query={ax.get('per_query', {})})")
                break
    lines.append("")
    lines.append("## Per-ablation results")
    lines.append("")
    lines.append("| Ablation | Output JSON | F1 | Δ F1 | Notes |")
    lines.append("|---|---|---|---|---|")
    for knob, path in knob_results:
        rel = path.relative_to(_resolve_root()) if path.exists() else f"(missing) {path.name}"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            f1 = None
            for ax in d.get("axes", []):
                if ax["name"] == "negative_rejection_f1":
                    f1 = ax["score"]
                    break
            f1_s = f"{f1:.4f}" if f1 is not None else "—"
        else:
            f1_s = "—"
        lines.append(f"| `{knob}` | `{rel}` | {f1_s} | (compute) | |")
    lines.append("")
    lines.append("## How to read this table")
    lines.append("")
    lines.append("Per `docs/design/v0.4-cycle-gamma-phase-d-")
    lines.append("mechanistic-ablation.md` §3:")
    lines.append("")
    lines.append("- Only `DISABLE_ABSTENTION` collapses → abstention "
                  "softener is the trigger")
    lines.append("- `DISABLE_COGNITIVE_STAGES` or `DISABLE_VERIFY` "
                  "also collapses → cog-stages family")
    lines.append("- Multiple ablations reduce, none zero → distributed "
                  "signal")
    lines.append("- All ablations unchanged → either knobs are no-ops "
                  "or signal in unmapped layer")
    lines.append("")
    lines.append("Per-query overlap analysis: use "
                  "`scripts/research/cycle_gamma_rgb_compare.py` "
                  "pairwise (R0 vs each Rk).")
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    return summary_path


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="cycle_gamma_phase_d_ablate",
        description=(
            "Phase D ablation matrix runner — runs JAMES with one "
            "component disabled at a time on RGB-en negrej n=25 "
            "(workspace #2)."
        ),
    )
    p.add_argument("--model", required=True,
                    help="Model id (e.g. mixtral:8x7b, llama3.1:8b, "
                          "gemma4:e4b)")
    p.add_argument("--workspace",
                    default="./workspaces/cycle_gamma_rgb_negrej",
                    help="Negrej-only workspace path (default: the "
                          "Phase A.5 workspace #2)")
    p.add_argument("--n-samples", type=int, default=25,
                    help="Queries per ablation (default 25 = Phase C "
                          "n)")
    p.add_argument("--out-dir", default="reports/cycle_gamma/phase-d",
                    help="Per-run JSON output directory")
    p.add_argument("--progress-every", type=int, default=5,
                    help="Per-run progress cadence (default 5)")
    p.add_argument("--knobs", nargs="*", default=None,
                    help="Subset of ablation knobs to run; default = "
                          "all 7")
    p.add_argument("--dry-run", action="store_true",
                    help="Print commands without executing — sanity "
                          "check the matrix")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                    errors="replace")

    root = _resolve_root()
    workspace = Path(args.workspace).resolve()
    out_dir = root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    knobs = list(args.knobs) if args.knobs else list(ABLATION_KNOBS)

    # Reference check (R0 = full-JAMES Phase C artifact). Required.
    ref_path = _reference_path(args.model)
    if not ref_path.exists() and not args.dry_run:
        print(f"!! Reference file missing: {ref_path}", file=sys.stderr)
        print("   Run Phase C full-JAMES negrej first:",
              file=sys.stderr)
        print(f"   JAMES_WORKSPACE={workspace} python scripts/"
              f"external_bench_run.py --bench rgb --variant en --mode "
              f"james --model {args.model} --setting-filter "
              f"negative_rejection --n-samples 25 --out {ref_path}",
              file=sys.stderr)
        return 2

    print("=== cycle γ Phase D ablation matrix ===")
    print(f"  model     : {args.model}")
    print(f"  workspace : {workspace}")
    print(f"  out_dir   : {out_dir}")
    print(f"  n_samples : {args.n_samples}")
    print(f"  knobs     : {len(knobs)} ({', '.join(knobs)})")
    print(f"  reference : {ref_path.relative_to(root) if ref_path.exists() else '(missing)'}")
    print(f"  dry_run   : {args.dry_run}")
    print()

    knob_results: List[tuple] = []
    t0 = time.time()
    for knob in knobs:
        out_path = _run_one_ablation(
            knob=knob,
            model=args.model,
            out_dir=out_dir,
            n_samples=args.n_samples,
            workspace=workspace,
            progress_every=args.progress_every,
            dry_run=args.dry_run,
        )
        knob_results.append((knob, out_path))

    summary_path = _emit_summary(
        model=args.model, out_dir=out_dir,
        knob_results=knob_results, reference_path=ref_path,
    )
    elapsed = time.time() - t0
    print(f"\n=== Phase D matrix complete: {len(knobs)} runs, "
          f"{elapsed:.0f}s total ===")
    print(f"summary: {summary_path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
