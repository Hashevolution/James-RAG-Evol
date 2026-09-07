# LRB-S3 — does the S2 token collision carry into the publication rung?

**Date**: 2026-09-03
**Companion to**: [`lrb-s2-fixture-nonreproduction-20260819.md`](lrb-s2-fixture-nonreproduction-20260819.md)
**Trigger**: that report's §5 — *"`build_lrb_scenario_s3.py` carries the
same `16 weeks ago` template … **Not measured here** — but the same
collision is available to it"* — left the publication-scale rung of the
S2→S3 ladder unverified while it is the rung the README and the preprint
cite.
**Status**: measured. **No generator edited, no published number
changed.** This report only adds evidence.

---

## 1. Headline

**S3 does not carry the defect at any committed preset, and the S3
publication figure reproduces exactly from the repository as committed.**

| | S2 (yearly time-travel) | S3 (all three presets) |
|---|---|---|
| `historical-mid-policy` JAMES R@1 | **0.000** (0/4) | 0.750 / 0.900 / **0.971** |
| top-1 concentration in that cell | **4 of 4 → one distractor** (`co-pol-016`) | max **2** occurrences of any doc |
| overall JAMES R@1 vs published | 0.6875 vs 0.7125 — **−0.025, does not reproduce** | **reproduces exactly** (below) |

So the non-reproduction established on 2026-08-19 is **confined to S2**.
The scale-ladder headline rests on S3, and S3 is sound.

## 2. S3 reproduces the published numbers exactly

Rebuilt from the committed generator (`scripts/research/build_lrb_scenario_s3.py --scale publication`),
scored through the same token-mode path the test uses:

| SUT | README / SUMMARY published | this rebuild | Δ |
|---|---|---|---|
| Vanilla | 0.502 | **0.5020** | 0 |
| Naive-supersede | 0.721 | **0.7210** | 0 |
| **JAMES** | **0.845** | **0.8450** | **0** |

(`README.md:496`, `SUMMARY.md:33`.) All three cells land on the published
value. The `V < N < J` ordering and the `J − N > +0.10` gap hold, as they
also do on S2 under either fixture.

## 3. Per-scale measurement

`weeks - mid_t` (with `mid_t = weeks // 3`) is the bare number the query
template injects — S3 computes it rather than hard-coding `16` as S2
does, so it differs per preset:

| preset | weeks | mid_t | injected token | title contains that bare token? | `historical-mid-policy` JAMES R@1 | overall JAMES R@1 |
|---|---|---|---|---|---|---|
| smoke | 24 | 8 | **16** | **no** (0 docs) | 0.750 (6/8) | 0.9300 |
| dev | 36 | 12 | **24** | **no** (0 docs) | 0.900 (18/20) | 0.9133 |
| publication | 52 | 17 | **35** | **no** (0 docs) | 0.971 (66/68) | 0.8450 |

For contrast, the same probe on S2 reproduces the 2026-08-19 finding
exactly: injected token `16`, **three** documents carry it as a bare
title token (`co-bud-016`, `co-pol-016`, `co-app-016`), the policy cell
scores 0/4, and all four queries return `co-pol-016`.

## 4. Why S3 is not exposed — and the exact condition under which it would be

S2 numbers its policies **locally**: `POLICIES = [(f"co-pol-{i:03d}",
f"Policy {i}: Operating Standard", …)]` (`build_lrb_scenario_s2.py:139`),
so titles carry small integers `1…20`, and the hard-coded offset `16`
falls inside that range.

S3 numbers them **globally** (`build_lrb_scenario_s3.py:313`):

```python
global_idx = dept_idx * 1000 + pol_idx + 1
return f"pol-{global_idx:06d}", f"Policy {global_idx}: Operating Standard"
```

With `policies_per_dept = 2` in all three presets, the bare numbers that
actually appear are `{1, 2} ∪ {1001, 1002} ∪ {2001, 2002} ∪ …`. Every
injected offset (16 / 24 / 35) falls in the empty gap between `2` and
`1001`. **The immunity is arithmetic, not design** — nothing in the
generator forbids the collision.

The collision returns as soon as either holds:

1. **`policies_per_dept` ≥ the injected offset** (≥16 smoke / ≥24 dev /
   ≥35 publication) — then `Policy 16` (etc.) exists and the S2 failure
   mode reappears verbatim. This is the realistic one: raising policy
   density is an ordinary scale knob.
2. `weeks` is chosen so `weeks - weeks//3` lands on some `dept*1000 +
   j + 1`. Only reachable at absurd values, so not a practical risk.

Budgets (`FY26 Operating Budget {global_idx}`) and appointments
(`Appointment Record {global_idx}`) use the same numbering, so they
acquire the collision under the same condition — the policy cell is
simply where the query template points.

## 5. What this does and does not settle

**Settles**: the S2→S3 ladder's publication rung is reproducible, and
the S2 defect is not systemic to the LRB generator family. The
2026-08-19 report's operator decision #4 ("check S3 before the ladder is
cited further") can be closed on evidence.

**Does not settle**: any of the other three operator decisions. The S2
generator drift is still unrecovered (the 2026-06-11 generator is not in
git), `test_token_mode_s2_reproduces_phase_b_baseline` is still red on
purpose, and the preprint's S2 cell still needs either a re-baseline or
a footnote. **Nothing here licenses editing the 0.7125 constant.**

**Adds one item**: the arithmetic immunity in §4 is silent and easy to
break. A guard asserting that no corpus title tokenises the injected
offset would make the next density change fail loudly instead of
quietly degrading a benchmark cell. Cheap, and it does not change a
single published number — but it is a benchmark-side change, so it is
listed here rather than taken.

## 6. Reproduce

```bash
python scripts/research/build_lrb_scenario_s3.py --scale publication
python - <<'EOF'
from pathlib import Path
from eval.external.lrb.driver import load_scenario, fixture_sha
from eval.external.lrb.adapters import (VanillaRagAdapter,
    NaiveSupersedeAdapter, JamesValidityAdapter)
from eval.external.lrb.driver_phase_b import score_run
from scripts.research.lrb_run_v021_cross_model import run_sut_cross_model

p = Path("eval/external/_fixtures/lrb/scenario_S3_publication.json")
sc, sha = load_scenario(p), fixture_sha(p)
for cls in (VanillaRagAdapter, NaiveSupersedeAdapter, JamesValidityAdapter):
    r = run_sut_cross_model(cls, sc, sha, sut_name="probe", mode="token",
                            model="token-baseline",
                            ollama_url="http://localhost:11434",
                            timeout=10.0, k=10)
    print(cls.__name__, score_run(r)["overall"]["exploratory"]["R@1"])
EOF
```

Deterministic: stdlib-only builder, token mode, no model and no network.
