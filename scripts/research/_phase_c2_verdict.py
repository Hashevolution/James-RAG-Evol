"""Cycle γ Phase C.2 — tradeoff verdict combiner.

Reads the MuSiQue paired-ablation result JSONs (R0 + DISABLE_RERANK +
DISABLE_COGNITIVE_STAGES per model) and combines the MuSiQue Δ (the
GAIN half) with the Phase E-min RGB-en Δ (the LOSS half, hardcoded
from the cross-model handover) to apply the pre-registered §5 verdict
table.

Δ convention (pre-registration §5): Δ = score(R0) − score(component OFF).
Δ > 0 ⇒ the component contributes on this axis.

Reads only; prints a verdict table. No mutation of any measurement.

Pre-registration: docs/research/cycle-gamma-phase-c2-preregistration-2026-06-10.md
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


OUTDIR = Path("reports/cycle_gamma/phase-c2")
MODELS = [("mixtral:8x7b", "mxtral"), ("gemma4:e4b", "gemma4"),
          ("llama3.1:8b", "llama")]
KNOBS = ["rerank", "cognitive_stages"]

# Noise bands (pre-registration §4).
BAND_EM = 0.04
BAND_F1 = 0.03

# RGB-en LOSS half (Phase E-min cross-model handover, Δnoise / Δnegrej
# when the component is DISABLED — positive = disabling HELPS RGB
# abstention, i.e. the component HURTS RGB abstention).
RGB_LOSS = {
    "rerank":           {"mxtral": (+0.040, +0.050),
                          "gemma4": (+0.040, +0.209),
                          "llama":  (+0.040, +0.098)},
    "cognitive_stages": {"mxtral": (+0.160, +0.050),
                          "gemma4": (+0.040, +0.111),
                          "llama":  (+0.120, +0.050)},
}


def _load_axes(tag: str, label: str) -> dict:
    """Return {axis_name: score} for one result JSON, or {} if missing."""
    path = OUTDIR / f"musique-ans-{tag}-{label}.json"
    if not path.exists():
        return {}
    d = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for ax in d.get("axes", []):
        out[ax["name"]] = ax.get("score")
    return out


def main() -> int:
    print("=== Cycle γ Phase C.2 — tradeoff verdict ===\n")
    print("Δ = score(R0) − score(component OFF); Δ>0 ⇒ component helps the axis.")
    print(f"Noise band: |Δem| ≤ {BAND_EM}, |Δf1| ≤ {BAND_F1}\n")

    any_missing = False
    for knob in KNOBS:
        print(f"\n### Component: {knob}")
        print(f"{'model':<8} {'R0_f1':>7} {'OFF_f1':>7} {'Δf1':>8} "
              f"{'R0_em':>7} {'OFF_em':>7} {'Δem':>8}   "
              f"{'RGB Δnoise/Δnegrej (LOSS)':>26}")
        gain_dirs = []
        for model_id, tag in MODELS:
            r0 = _load_axes(tag, "R0")
            off = _load_axes(tag, knob)
            if not r0 or not off:
                print(f"{tag:<8}  (missing result JSON — run not complete)")
                any_missing = True
                continue
            d_f1 = (r0.get("f1", 0.0) or 0.0) - (off.get("f1", 0.0) or 0.0)
            d_em = (r0.get("em", 0.0) or 0.0) - (off.get("em", 0.0) or 0.0)
            rgb = RGB_LOSS[knob].get(tag, (None, None))
            rgb_str = f"+{rgb[0]:.3f} / +{rgb[1]:.3f}" if rgb[0] is not None else "n/a"
            # GAIN direction: Δf1 > band ⇒ helps multihop (+); < -band ⇒ hurts (−)
            if d_f1 > BAND_F1:
                gain_dirs.append("+")
            elif d_f1 < -BAND_F1:
                gain_dirs.append("-")
            else:
                gain_dirs.append("0")
            print(f"{tag:<8} {r0.get('f1',0):>7.3f} {off.get('f1',0):>7.3f} "
                  f"{d_f1:>+8.3f} {r0.get('em',0):>7.3f} {off.get('em',0):>7.3f} "
                  f"{d_em:>+8.3f}   {rgb_str:>26}")

        # Per-component verdict (pre-registration §5).
        print(f"  MuSiQue GAIN directions (Δf1): {gain_dirs}")
        n_help = gain_dirs.count("+")
        n_hurt = gain_dirs.count("-")
        n_flat = gain_dirs.count("0")
        if len(gain_dirs) < 3:
            verdict = "PENDING (need all 3 models)"
        elif n_help >= 2:
            verdict = ("HYP 2 PROVEN (tradeoff) — component helps multi-hop "
                       "while hurting RGB abstention → KEEP + harmonize "
                       "(query-type routing). Default-off FORBIDDEN.")
        elif n_flat == 3 or (n_flat >= 2 and n_hurt == 0 and n_help == 0):
            verdict = ("HYP 1 PROVEN (deadweight) — flat on home turf + "
                       "hurts RGB → default-off PR LICENSED (R4 registry).")
        elif n_hurt >= 2:
            verdict = ("HYP 1 strengthened — OFF better on home turf too "
                       "→ default-off LICENSED (prior-art check before "
                       "novelty claim).")
        else:
            verdict = ("SPLIT (model-dependent) — no global default change; "
                       "route to R10 model-capability-tier profile.")
        print(f"  >>> VERDICT [{knob}]: {verdict}")

    if any_missing:
        print("\n(some cells missing — re-run after all 9 runs complete)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
