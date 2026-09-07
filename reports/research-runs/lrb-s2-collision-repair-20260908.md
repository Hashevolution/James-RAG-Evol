# LRB-S2 — collision repaired, fixture re-run

**Date**: 2026-09-08
**Decision executed**: #1 of
[`lrb-s2-fixture-nonreproduction-20260819.md`](lrb-s2-fixture-nonreproduction-20260819.md)
§7 — *repair the collision*, chosen by the operator.
**Scope**: `scripts/research/build_lrb_scenario_s2.py` and the S2 assertion
in `tests/test_lrb_v021_cross_model.py`. **S3 is untouched** — it reproduces
its published figure exactly
([`lrb-s3-collision-check-20260903.md`](lrb-s3-collision-check-20260903.md)),
and changing shared naming would have broken that.

---

## 1. The repair

Policy titles were `Policy {i}: Operating Standard`. The historical-policy
query template injects a bare time offset:

```
What was the text of Policy 1: Operating Standard 16 weeks ago?
```

so the token `16` entered the query and matched `co-pol-016`'s title as
strongly as the gold policy's own number matched its own — on top of the
three content words every policy title shares. Departments and projects
never had the problem because their titles are word-based.

Policies now match that: `Policy One: …` … `Policy Forty: …`. The ordinal
is still unique per policy and still a single token, so the gold keeps a
distinguishing term — it is simply no longer a term the query's time
expression can produce by accident.

## 2. Effect on the colliding cell

`historical-mid-policy`, n = 4, top-1:

| query | gold | before | after |
|---|---|---|---|
| lrb-s2-q057 | co-pol-001.v2 | co-pol-016 ✗ | co-pol-001.v2 ✓ |
| lrb-s2-q058 | co-pol-005.v2 | co-pol-016 ✗ | co-pol-005.v2 ✓ |
| lrb-s2-q059 | co-pol-010 | co-pol-010 ✓ | co-pol-010 ✓ |
| lrb-s2-q060 | co-pol-015 | co-pol-015 ✓ | co-pol-015 ✓ |

The cell goes from 2/4 to **4/4** on this machine.

## 3. Re-run — token mode, k=10, all three SUTs

| SUT | published | repaired | Δ |
|---|---:|---:|---:|
| Vanilla RAG | 0.225 | **0.2500** | +0.025 |
| Naive supersede | 0.5375 | **0.5875** | +0.050 |
| JAMES validity | 0.7125 | **0.7625** | +0.050 |

Other axes on the repaired fixture: JAMES R@5 0.9500 / R@10 1.0000 /
P@5 0.1900 / P@10 0.1000 / temporal_accuracy 1.0000.

**The artifact suppressed all three SUTs, so the claims survive it.**
V < N < J still holds, and **J − N is 0.175 on both fixtures** — identical
to four decimals. J − V widens from 0.4875 to 0.5125. The "gap > +0.10"
headline is unaffected.

Fixture sha256 `2c1b210c…`, identical across two clean rebuilds here.

## 4. What the investigation turned up on the way

The 2026-08-19 report recorded the committed builder producing sha
`1ddfb6c0…` and the published run using `9f40d2e0…`, and concluded the
repository could not rebuild the published fixture.

**On this machine the committed builder produces `9f40d2e0…` — the
published fixture — byte for byte**, and scores exactly 0.7125. The
June-dated copy already on disk is byte-identical to that fresh rebuild.

So the same builder, unchanged in git since 2026-06-12, yields different
artifacts in different environments. The consequence is visible in the
colliding cell: it loses **2 of 4** here and **4 of 4** on CI, which is
where the −0.025 came from. The collision is real in both places; only how
many of the four ties break toward the distractor differs.

This is not diagnosed further here — the repair removes the tie entirely,
so the environment sensitivity it exposed goes with it. But it is recorded
because it bears on §7 decision #3 (commit the fixtures): a builder that is
deterministic *within* an environment and not *across* one is exactly the
failure mode that pinning SHAs in-repo would have caught in June rather
than in August.

## 5. What this does not settle

The published figure is now superseded, not reproduced. **0.7125 embedded
the artifact** — 2 of those 4 queries were already failing in the published
run, which is why the report called it "weaker form" there.

Decision #2 is therefore live and is **not taken here**: the old figures
still stand in

- `papers/lrb-preprint/README.md`
- `.zenodo.json`
- `docs/release_notes_v0.4.4.md`
- `CLAUDE.md` and the v0.4 LRB handovers

Re-baselining a preprint or a minted DOI record is an operator decision, so
none of those files is edited. `tests/test_lrb_v021_cross_model.py` now
pins the repaired numbers with that divergence stated in the test itself:
green there means the repository reproduces itself, not that it reproduces
the paper.

Decision #3 (commit the fixtures) and #4 (check S3) are unchanged — #4 was
already closed on 2026-09-03.
