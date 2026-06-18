# Benchmark Challenge (Phase 7)

> Status: **draft** — open for discussion. This defines a fair-comparison
> challenge so improvement claims compete under identical constraints instead
> of in isolation.

JAMES publishes deterministic benchmarks (RAB, LRB) with committed fixtures
and scorers. If you think another system does better, **show it under the same
constraints** and send a PR.

## The challenge

Beat JAMES on a published benchmark **without changing the measurement**.

### Constraints (must all hold)

- **Same datasets** — the committed fixtures in `eval/rab/scenarios/` and
  `eval/external/lrb/`. No re-sampling, no relabeling.
- **Same scorer** — `eval/rab/scorer.py` (AC/RF/PC) and the LRB token-mode
  scorer. The scorer is the contract; don't modify it.
- **Same models / context limits** — if your system uses an LLM, use the
  disclosed model class (`gemma4:e4b`) and `num_ctx=2048`, or disclose the
  exact substitution so it can be reproduced.
- **Same evaluation procedure** — run via `benchmarks/run_all.sh` (or add a
  sibling adapter that the existing runner can call).

### How to submit

1. Add your system as a new SUT adapter next to the existing ones
   (`eval/rab/adapters/`, `eval/external/lrb/adapters/`).
2. Run `bash benchmarks/run_all.sh` and paste the table in your PR.
3. Open a PR. For any PR touching `core/{retrieval,graph,reasoning}`, paste
   the bench numbers + Quality Delta Card per the repository's
   `.github/PULL_REQUEST_TEMPLATE.md` (project rule #2).

## What "winning" means here (honest framing)

RAB's headline is the **gap structure**, not a single score — its SPEC §6.5
disclaims a "JAMES-wins" reading. So a meaningful challenge result is one of:

- A system that **closes the audit gap** (e.g. a default-logging stack that
  reaches AC/RF/PC > baseline-0's 0.275/0/0 without an audit-native runtime), or
- A system that **beats JAMES on LRB R@1** while preserving temporal validity
  semantics, or
- A demonstration that one of the benchmarks is **gameable** — i.e. a trivial
  SUT scores high without the capability the metric intends to measure. That is
  a contribution to the *benchmark*, and we want to hear it.

The aim is a benchmark **competition around JAMES**, with every claim pinned to
a reproducible command — not isolated leaderboard assertions.
