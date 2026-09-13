# LRB v0.2.3 S3 publication-scale results — S3.2 project-title fix (2026-09-12)

> **Pre-reg**: `docs/research/lrb-v023-s3-publication-scale-preregistration-2026-06-12.md` (unchanged; verdict matrix §2 applied as written)
> **Generator**: `scripts/research/build_lrb_scenario_s3.py` — **S3.2 fix in this PR** (`make_project` / new-project titles)
> **Runner**: `scripts/research/lrb_run_s3.py --scale {smoke,dev,publication}` (Phase B token-mode driver, deterministic)
> **Mode**: token (no LLM). The LLM-grounded S3 publication run on the S3.2 fixture is a separate, later report.
> **Supersedes**: the ladder in `lrb-v023-s3-publication-scale-results-2026-06-12.md` §2 — kept there, marked pre-S3.2.
> **Honest tier**: ⭐⭐⭐ R@1 V<N<J pattern + J−N gap scale-robust / ⭐⭐ absolute magnitude scenario-sensitive (S2 hand-curated ↔ S3 synthetic). **Tier unchanged.** What S3.2 removes is the *within-S3* decline of the magnitude with scale, which was an artefact.
> **Operator decision**: 2026-09-12 — the close handover §6 #7 (S3.2 fix, published S3 figure re-baselined) was approved as part of the LRB re-baseline bundle.

---

## 1. What was wrong

`reports/research-runs/lrb-v023b-3model-llm-grounded-publication-20260910.md` §4
(PR #1121) found that at the publication preset the two project-lead
categories — 191 of 1000 queries, 19.1 % — sat at an identical R@1 0.256
for naive-supersede and JAMES under **four** unrelated scorers (token mode
and three LLM rerankers). The cause is in the generator, not in any SUT:

- `make_project` derived the title from `(dept_idx + prj_idx) % 20` and
  `(dept_idx*7 + prj_idx*3) % 20`. Both are periodic in `dept_idx` with
  period 20, so at 100 departments every title recurred five times: 330
  project docs, **70 unique titles**.
- The project-lead query is `Who leads {ptitle}?` — no department — so
  125 current-project-lead queries had **18 distinct texts**, each carrying
  5 distinct golds. Identical input cannot yield gold-specific output, so
  no system could exceed **0.288** on that category (0.273 on
  historical-mid-project-lead). The 2026-06-12 results doc tabulated R@10,
  which cannot see an R@1 ceiling.

The ceiling was a function of department count (smoke 10 depts:
collision-free; dev 30: 10 titles × 2; publication 100: 50 titles × 5), which
is exactly why the pre-S3.2 ladder *declined* with scale (0.930 → 0.913 →
0.845) while R@10 stayed 1.0.

## 2. The fix (S3.2)

- `make_project(dept_idx, prj_idx, projects_per_dept)` now enumerates the
  20 noun × 20 verb table by the **global project index**
  `dept_idx * projects_per_dept + prj_idx` (verb cycles fastest), the same
  construction S3.1 used for contracts. Up to 400 base projects get unique
  titles; publication uses 300.
- New-project ingests continue the table from slot `n_base`, so they
  collide with neither the base titles nor each other (pre-S3.2 they drew
  from the same 20-slot cycle and collided both ways). A denser preset
  that would exhaust the 400 slots now **raises** instead of wrapping.
- Two guards in `tests/test_lrb_s3_generator.py`:
  `ProjectDiversityTests` (every project doc has a unique title, all three
  presets, new ingests included) and `QueryOracleUnambiguityTests` (no
  query text at one `(query_time, valid_time)` maps to more than one gold —
  the generic oracle-ceiling guard). Against the pre-S3.2 generator the
  second guard fails with **36 ambiguous query texts**; against S3.2 both
  pass on all presets (0 collisions, 0 ambiguous texts).

Fixtures are gitignored and regenerate byte-deterministically:

| preset | file sha256 (S3.2) | pre-S3.2 |
|---|---|---|
| smoke | `4a890011b7c8…` | `1f221bb130d2…` |
| dev | `37aa6d90d4e9…` | `350f97596e40…` |
| publication | `cc98e141a4b4…` | `662fc2b76b8a…` |

## 3. Scale ladder (token mode, S3.2)

| Scenario | N (docs / events / queries) | V R@1 | N R@1 | **J R@1** | V<N<J | J − N | J − V | pre-S3.2 J | pre J − N |
|---|---|---|---|---|---|---|---|---|---|
| S2 token (repaired, #1089) | 200 / 564 / 80 | 0.250 | 0.588 | **0.763** | ✓ | +0.175 | +0.513 | 0.713 (published; LRB decision #2) | +0.175 |
| S3 smoke | 100 / 282 / 100 | 0.540 | 0.760 | **0.950** | ✓ | +0.190 | +0.410 | 0.930 | +0.200 |
| S3 dev | 300 / 1206 / 300 | 0.553 | 0.777 | **0.973** | ✓ | +0.197 | +0.420 | 0.913 | +0.176 |
| **S3 publication** | 1000 / 5620 / 1000 | **0.566** | **0.827** | **0.984** | ✓ | **+0.157** | **+0.418** | 0.845 | +0.124 |

Temporal accuracy (publication): vanilla 0.988 / naive-supersede 0.833 /
james **1.000** — unchanged from pre-S3.2 (0.988 / 0.833 / 1.000). Result
files: `reports/external/lrb/phase-b-s3-{smoke,dev}-20260912T084727Z.*` and
`phase-b-s3-publication-20260912T084729Z.*` (`bench.jsonl` gitignored; the
pre-S3.2 `phase-b-s3-*-20260611T2325*` files stay committed).

## 4. Per-category R@1, publication (post-S3.2 / pre-S3.2)

| category | n | V post | N post | **J post** | V pre | N pre | J pre |
|---|---|---|---|---|---|---|---|
| current-contract | 125 | 0.000 | 1.000 | **1.000** | 0.000 | 1.000 | 1.000 |
| current-director | 125 | 1.000 | 1.000 | **1.000** | 1.000 | 1.000 | 1.000 |
| current-policy | 125 | 0.000 | 0.976 | **0.976** | 0.000 | 0.976 | 0.976 |
| **current-project-lead** | 125 | **0.336** | **0.992** | **0.992** | 0.064 | 0.256 | 0.256 |
| historical-early-contract | 50 | 1.000 | 0.000 | **1.000** | 1.000 | 0.000 | 1.000 |
| historical-early-director | 50 | 0.500 | 0.500 | **1.000** | 0.500 | 0.500 | 1.000 |
| historical-mid-director | 66 | 0.758 | 0.758 | **1.000** | 0.758 | 0.758 | 1.000 |
| historical-mid-policy | 68 | 0.588 | 0.382 | **0.971** | 0.588 | 0.382 | 0.971 |
| **historical-mid-project-lead** | 66 | **0.515** | **0.455** | **0.848** | 0.061 | 0.242 | 0.136 |
| never-stale-budget | 200 | 1.000 | 1.000 | **1.000** | 1.000 | 1.000 | 1.000 |

- **Eight of ten categories are byte-identical** to the pre-S3.2 run. The
  fix touched project titles only, and the numbers say so: every
  movement is inside the two project-lead categories.
- current-project-lead: naive-supersede and JAMES both 0.992 (124/125)
  — the ceiling is gone. vanilla 0.336: stale v1 leads still win rank 1
  on superseded projects, which is the vanilla mechanism.
- historical-mid-project-lead JAMES **0.848** (56/66), R@10 1.000. Not an
  oracle floor — V / N / J differ (0.515 / 0.455 / 0.848) and the guard
  passes — so these ten misses are genuine SUT rank-1 misses on the
  time-travel window (the v1 and v2 of a superseded project share a
  title; both are in the top 10). Recorded as a JAMES imperfection, not
  reinterpreted away.
- No category has R@10 = 0 for all SUTs; naive-supersede
  historical-early-contract 0.000 is the delete-history mechanism, as
  before.

## 5. Verdict (prereg §2, token mode)

| Condition | Observed | Verdict |
|---|---|---|
| R@1 V<N<J at every scale point | ✓ 4/4 (S2 repaired, smoke, dev, publication) | ⭐⭐⭐ pattern scale-robust |
| JAMES − Naive R@1 gap > 0.10 at every point | ✓ +0.175 / +0.190 / +0.197 / +0.157 | ⭐⭐⭐ gap robust |
| JAMES R@1 within ±0.05 of the S2 token cell | ✗ 0.984 vs 0.763 (Δ +0.22) | ⭐⭐ magnitude scenario-sensitive (S2 ↔ S3) |

Composite: **⭐⭐⭐ pattern + gap / ⭐⭐ magnitude scenario-sensitive** —
the same composite as 2026-06-12. Two statements change underneath it:

1. *Retracted*: "absolute magnitude is scale-sensitive within S3". The
   pre-S3.2 decline 0.930 → 0.913 → 0.845 was the title collision growing
   with department count. Post-S3.2 the magnitude is flat-to-rising
   across the 10× S3 span (0.950 → 0.973 → 0.984).
2. *Kept*: "absolute magnitude is scenario-sensitive". S3 synthetic
   vocabulary still yields higher absolute R@1 than the hand-curated S2
   text for all three SUTs; cross-scenario claims stay limited to ordering
   and gap structure.

The gap itself moved +0.124 → +0.157 at publication because the ceiling
had held N and J to the same value on 19.1 % of queries — it compressed
J − N, it never inflated it (as the #1121 report predicted).

## 6. Where the published figure is re-baselined (this PR)

`README.md`, `SUMMARY.md`, `benchmarks/README.md`,
`docs/evaluation/v0.5-evaluation-coverage-mapping.md`,
`docs/evaluation/v0.5-graph-rag-contribution.md`,
`docs/evaluation/v0.5-industry-comparison.md`, the three
`docs/strategy/v0.5-pre-loi-materials/` files, and
`papers/lrb-preprint/main.tex` (abstract + §4.6 table + gap sentence,
PDF rebuilt) now carry 0.566 / 0.827 / 0.984. `docs/release_notes_v0.4.4.md`
gets an erratum line; its artefacts and DOI are unchanged. The
`.zenodo.json` description (the v0.4.4 deposit text) is left as deposited.

**Not in this PR**: the S2 published cell (LRB decision #2 — the S2
LLM-grounded re-run on the repaired fixture is in progress and lands with
the S2 re-baseline), the LLM-grounded S3 publication re-run on the S3.2
fixture (≈ 20 h, in progress after this PR), and preprint §4.7 (needs that
re-run).

> **Update 2026-09-13**: both landed — S2 in PR #1125
> (`reports/research-runs/lrb-v021-s2-llm-grounded-repaired-fixture-20260912.md`),
> the S3 LLM-grounded re-run (3 local rerankers) in
> `reports/research-runs/lrb-v023b-3model-llm-grounded-publication-s32-20260913.md`
> (J 0.989 / 0.991 / 0.893, J−N +0.170 / +0.178 / +0.139). The claude leg and
> preprint §4.7 follow.

## 7. Reproduce

```bash
python scripts/research/build_lrb_scenario_s3.py --scale smoke
python scripts/research/build_lrb_scenario_s3.py --scale dev
python scripts/research/build_lrb_scenario_s3.py --scale publication
PYTHONPATH=. python scripts/research/lrb_run_s3.py --scale publication
python -m pytest -q tests/test_lrb_s3_generator.py
```

Deterministic: stdlib-only builder, token mode, no model and no network.
