# LRB-S2 — why the published R@1 does not reproduce

**Date**: 2026-08-19
**Trigger**: `tests/test_lrb_v021_cross_model.py::test_token_mode_s2_reproduces_phase_b_baseline`
fails at JAMES R@1 **0.6875** against the pinned **0.7125**. Surfaced only
now because `eval/external/_fixtures/` is gitignored, so every LRB test
died on `FileNotFoundError` in CI and this assertion had never once run
there (suite landed in PR #1027, 2026-06-23).
**Status**: root cause established. **No numbers changed, no generator
edited** — the fix touches a pre-registered benchmark and a published
figure, so it is an operator decision.

---

## 1. What was checked

| Step | Result |
|---|---|
| Builder determinism (2 clean rebuilds) | identical SHA `1ddfb6c0…` — **deterministic** |
| Published run's `fixture_sha` | `9f40d2e0…` — **different fixture** |
| `fixture_sha()` definition | plain `sha256(file bytes)` (`driver.py:79`) — comparison valid |
| Git history of the S2 builder | one commit only (`7de6ab7`, 2026-06-23); the 2026-06-11 generator was never committed and is **not recoverable** |
| LRB code touched since | none — builder, adapter, runner and tests all landed in `7de6ab7` |
| Adapter dependencies | `math`, `re`, `collections.Counter` only — no `core/` coupling, so no JAMES-side regression is involved |

## 2. Where the difference lives

Re-running the committed fixture through the same path and comparing to
`reports/external/lrb/v021-s2-token-baseline-token-20260611T133018Z.james.result.json`:

| axis | published | current | Δ |
|---|---|---|---|
| R@5 / R@10 / P@5 / P@10 / temporal_accuracy | 0.9 / 0.975 / 0.18 / 0.0975 / 0.975 | identical | 0 |
| **R@1 / P@1 / temporal_accuracy_strict_top1** | **0.7125** | **0.6875** | **−0.025** |

Everything except rank-1 ordering is untouched. −0.025 × 80 queries = **2
queries**, and the per-category breakdown puts all of it in one cell:

| category | n | published R@1 | current R@1 |
|---|---|---|---|
| **historical-mid-policy** | **4** | **0.5** | **0.0** |
| all eight others | 76 | — | unchanged |

## 3. Root cause — a token collision inside the fixture

All four `historical-mid-policy` queries return the **same** top-1
document regardless of gold:

| qid | gold | top-1 |
|---|---|---|
| lrb-s2-q057 | co-pol-001.v2 | co-pol-016 |
| lrb-s2-q058 | co-pol-005.v2 | co-pol-016 |
| lrb-s2-q059 | co-pol-010 | co-pol-016 |
| lrb-s2-q060 | co-pol-015 | co-pol-016 |

The query template hard-codes the time offset
(`build_lrb_scenario_s2.py:511`):

```python
f"What was the text of {pol_meta[1]} 16 weeks ago?"
```

so q057 reads *"What was the text of **Policy 1**: Operating Standard
**16 weeks ago**?"* — and `co-pol-016` is titled *"Policy **16**:
Operating Standard"*. The time expression injects a bare `16` token into
the query, and the distractor matches `policy` + `16` + `operating` +
`standard` while the gold matches `policy` + its own number + `operating`
+ `standard`.

Only policies are hit because only policy titles carry a bare number.
Exactly three documents in the corpus tokenise a standalone `16`:
`co-bud-016` ("FY26 Operating Budget 16"), `co-app-016` ("Appointment
Record 16") and `co-pol-016` — and of those only the policy shares the
query's other content words. The same template is used for directors
("Department of Public Works") and project leads ("Project Riverwalk
Renewal"); those titles are word-based, so they do not collide, and both
categories reproduce exactly.

**This is a benchmark artifact, not a retrieval finding.** That cell
measures a numeric token collision rather than time-travel retrieval.
It also existed in the published run in weaker form — 0.5 there is 2 of
4 already failing, against 0.4–1.0 in the neighbouring historical cells.

## 4. What is not established

The 2026-06-11 generator is not in git, so *what* changed between it and
the committed one cannot be recovered — only that the change moved this
cell from 2/4 to 0/4. Candidates (untested): different time phrasing,
different policy count, different policy naming.

## 5. Scope beyond S2

`build_lrb_scenario_s3.py` carries the same `16 weeks ago` template (3
occurrences) **and** the same numbered policy titles
(`f"Policy {global_idx}: Operating Standard"`, line 314). S3 is the
publication-scale rung of the S2→S3 ladder. **Not measured here** — but
the same collision is available to it, and the S1 builder does not use
the template at all.

## 6. Why this matters and what it does not touch

`papers/lrb-preprint/README.md` records the abstract's token-mode R@1 as
`0.225 / 0.5375 / 0.7125`. Vanilla (0.225) and naive-supersede (0.5375)
reproduce exactly; only the JAMES cell moves, and only at rank 1.

The ordering claim is unaffected: 0.6875 still clears naive-supersede by
**+0.15** and vanilla by **+0.46**, so V < N < J and the "gap > +0.10"
headline hold on either fixture. What does not hold is the
**reproducibility of the absolute figure** from the repository as
committed.

## 7. Operator decisions (none taken)

1. **Repair the collision** — phrase the offset non-numerically, or give
   policies word-based titles like departments and projects. Either
   changes benchmark numbers, and LRB is pre-registered, so it needs an
   explicit re-run and a note rather than a silent edit.
2. **Re-baseline or annotate the preprint** — restate the JAMES cell
   against a fixture the repository can actually rebuild, or keep 0.7125
   with a footnote naming the generator drift.
3. **Commit the fixtures** (drop `eval/external/_fixtures/` from
   `.gitignore`, or pin SHAs in-repo) so a scenario can never silently
   diverge from a published run again.
4. **Check S3** for the same collision before the ladder is cited further.

Until one is chosen, `test_token_mode_s2_reproduces_phase_b_baseline`
stays red on purpose: it is reporting a true non-reproduction.
