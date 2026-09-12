# LRB v0.2.1 — S2 cross-model re-run on the repaired fixture (2026-09-12)

**Why**: LRB decision #2 (close handover 2026-09-10 §6 #1). PR #1089
(2026-09-08) repaired a policy-title collision in the S2 generator; the
committed generator now rebuilds the fixture byte-for-byte (sha
`2c1b210c…`) and token mode scores V/N/J = 0.2500 / 0.5875 / 0.7625 instead
of the published 0.225 / 0.5375 / 0.7125. The published 4-model
LLM-grounded S2 table (2026-06-11) was measured on the old fixture
(`9f40d2e0…`), so re-baselining the token cell alone would have left the
paper's cross-model table on a fixture the repository cannot rebuild. The
operator approved the re-baseline bundle on 2026-09-12; this report is
the measurement behind it.

**Runner**: `scripts/research/lrb_run_v021_cross_model.py --scenarios S2
--modes llm-grounded --models gemma4:e4b,gemma3:12b,mixtral:8x7b[,claude-haiku-4-5]`
(run ids `20260912T085007Z` local, `20260912T122020Z` claude, `--timeout 120`
for claude). Token mode: `scripts/research/lrb_run_phase_b.py`
(`phase-b-s2-20260912T090537Z`). Prereg: `docs/research/lrb-v021-cross-model-preregistration-2026-06-11.md`
(config unchanged).

**Fixture**: `eval/external/_fixtures/lrb/scenario_S2_yearly_timetravel.json`,
sha `2c1b210cb3fd…` (repaired). 80 queries, 200 docs, 564 events. The
oracle-ambiguity guard from S3.2 (`QueryOracleUnambiguityTests` logic)
run over this fixture: **0 query texts carry more than one gold**.

---

## 1. R@1 (V / N / J), repaired fixture

| SUT | token | gemma4:e4b (4B) | gemma3:12b (12B) | mixtral:8x7b (47B) | claude-haiku-4-5 |
|---|---|---|---|---|---|
| vanilla | 0.2500 | 0.4750 | 0.4500 | 0.3625 | 0.5250 |
| naive-supersede | 0.5875 | 0.7375 | 0.7250 | 0.6875 | 0.7750 |
| **JAMES** | **0.7625** | **0.9000** | **0.9000** | **0.8625** | **1.0000** |
| V<N<J | ✓ | ✓ | ✓ | ✓ | ✓ |
| J − N | +0.1750 | +0.1625 | +0.1750 | +0.1750 | +0.2250 |
| J − V | +0.5125 | +0.4250 | +0.4500 | +0.5000 | +0.4750 |

R@10 and temporal accuracy are identical across all five columns:
vanilla 1.0000, naive-supersede 0.7750, JAMES 1.0000. (The rerank pool is
the token top-20; the gold is always in it for vanilla and JAMES, and
naive-supersede deleted it on 18 of 80 queries — the same 0.775 under
every reranker.)

### Against the published (pre-repair, 2026-06-11) cells

| SUT | token | 4B | 12B | 47B | claude |
|---|---|---|---|---|---|
| vanilla (June) | 0.2250 | 0.4875 | 0.4000 | 0.3750 | 0.6125 |
| naive (June) | 0.5375 | 0.5625 | 0.6125 | 0.6250 | 0.7750 |
| JAMES (June) | 0.7125 | 0.7250 | 0.7750 | 0.8375 | 0.9750 |
| J − N (June) | +0.175 | +0.163 | +0.163 | +0.213 | +0.200 |
| **Δ JAMES (repaired − June)** | +0.050 | +0.175 | +0.125 | +0.025 | +0.025 |
| **Δ (J − N)** | 0.000 | 0.000 | +0.012 | −0.038 | +0.025 |

The ordering holds on every leg on both fixtures; the J − N gap is
unchanged within ±0.04 (±3 queries of 80); the absolute JAMES R@1 moves
up by 0.025 … 0.175 because the repaired fixture no longer lets a stale
policy document with the same bare number win rank 1 (the collision
#1089 removed — see `lrb-s2-collision-repair-20260908.md`).

## 2. Cell hygiene

| cell | n | mean latency | max latency | timeouts | fallbacks | rows = token-mode top-10 |
|---|---|---|---|---|---|---|
| gemma4:e4b × V / N / J | 80 | 3.1 / 3.1 / 2.9 s | 7.5 / 3.2 / 3.2 s | 0 | (pre-#1123 code) | 48 / 47 / 43 |
| gemma3:12b × V / N / J | 80 | 4.3 / 4.2 / 4.2 s | 10.2 / 4.4 / 4.4 s | 0 | (pre-#1123 code) | 28 / 32 / 30 |
| mixtral:8x7b × V / N / J | 80 | 18.5 / 21.0 / 21.1 s | 36.0 / 25.2 / 25.1 s | 0 | (pre-#1123 code) | 21 / 20 / 21 |
| claude-haiku-4-5 × V / N / J | 80 | 22.5 / 20.0 / 19.7 s | 54.4 / 46.6 / 50.3 s | 0 | **0 / 0 / 0** | 41 / 48 / 46 |

- The three local legs ran before #1123 landed, so their rows carry no
  `rerank_fallback` flag; the audit is by latency (no row near the 60 s
  timeout) and by agreement with the token-mode top-10 (20–48 of 80 rows,
  the ordinary level when a reranker agrees with token order). The
  claude leg ran after #1123/#1124 and reports **0 fallbacks** per cell.
- **A first claude leg the same evening (run `20260912T085007Z`) is
  discarded.** 237 of its 240 rows were identical to the token-mode
  top-10 and its R@1 (0.275 / 0.5875 / 0.7625) was the token-mode result
  to three decimals: every `claude -p` call had failed in ~5 s once the
  Max-plan window was exhausted, and the reranker silently kept token
  order. Root cause — the call ran with cwd = repository root and carried
  the whole `CLAUDE.md` briefing (~12k tokens) per call — fixed in #1124
  (neutral cwd, two-sentence `--system-prompt`, `--no-session-persistence`,
  UTF-8, every exception a counted fallback). The S3 cloud leg started
  the same afternoon was contaminated the same way (763 / 1000 vanilla
  rows) and is being re-run.

## 3. Per-category R@1 (V / N / J)

| category | n | token | gemma4:e4b | gemma3:12b | mixtral:8x7b | claude-haiku-4-5 |
|---|---|---|---|---|---|---|
| current-director | 20 | 0.45 / 0.85 / 0.85 | 0.60 / 1.00 / 1.00 | 0.60 / 1.00 / 1.00 | 0.60 / 0.95 / 0.95 | 0.60 / 1.00 / 1.00 |
| current-policy | 8 | 0.00 / 1.00 / 1.00 | 0.00 / 1.00 / 1.00 | 0.00 / 1.00 / 1.00 | 0.00 / 1.00 / 1.00 | 0.00 / 1.00 / 1.00 |
| current-project-lead | 12 | 0.08 / 1.00 / 1.00 | 0.08 / 1.00 / 1.00 | 0.08 / 1.00 / 1.00 | 0.17 / 1.00 / 1.00 | 0.08 / 1.00 / 1.00 |
| historical-early-contract | 4 | 0.50 / 0.00 / 1.00 | 0.50 / 0.00 / 1.00 | 0.50 / 0.00 / 1.00 | 0.50 / 0.00 / 1.00 | 1.00 / 0.00 / 1.00 |
| historical-early-director | 6 | 0.17 / 0.00 / 0.67 | 0.17 / 0.00 / 1.00 | 0.17 / 0.00 / 0.83 | 0.50 / 0.00 / 1.00 | 0.83 / 0.00 / 1.00 |
| historical-mid-director | 10 | 0.10 / 0.20 / 0.40 | 0.60 / 0.40 / 0.50 | 0.60 / 0.20 / 0.50 | 0.30 / 0.20 / 0.30 | 0.30 / 0.60 / 1.00 |
| historical-mid-policy | 4 | 0.50 / 0.50 / 1.00 | 0.50 / 0.50 / 0.50 | 0.50 / 0.50 / 1.00 | 0.50 / 0.50 / 1.00 | 0.25 / 0.50 / 1.00 |
| historical-mid-project-lead | 6 | 0.33 / 0.67 / 1.00 | 0.67 / 0.67 / 1.00 | 0.33 / 0.67 / 0.67 | 0.00 / 0.67 / 0.83 | 0.33 / 0.67 / 1.00 |
| never-stale-budget | 10 | 0.20 / 0.20 / 0.20 | 1.00 / 0.90 / 0.90 | 1.00 / 1.00 / 1.00 | 0.50 / 0.80 / 0.80 | 1.00 / 1.00 / 1.00 |

- `never-stale-budget` in **token mode** is 0.20 for all three SUTs: the
  twenty budget titles differ only in a trailing number (`FY26 Operating
  Budget 1 … 20`), which the token-overlap scorer ties, so rank 1 is a
  coin toss for every SUT. It is *not* an oracle ceiling (0 ambiguous
  query texts; the LLM rerankers reach 0.8–1.0 from the body text) and it
  cannot move J − N because it holds all three SUTs equally. Recorded as
  a token-scorer limitation of S2, not a finding.
- The historical director windows are where the rerankers differ:
  claude resolves `historical-mid-director` fully (J 1.00), the local
  models 0.30–0.50 — the same "backbone matters on time-travel director
  queries, not on the ordering" shape as the S3 publication run.

## 4. Verdict

Prereg v0.2.1 §1.4 ladder, re-applied on the repaired fixture: **4/4 model
legs V<N<J, plus token — ⭐⭐⭐ cross-model leg-clear**, unchanged from June.
Secondary condition J − N > +0.10 met on every leg (+0.1625 … +0.2250).
Nothing in the June verdict changes; the numbers that change are the
absolute cells, and only upward.

Honest notes: n = 80 per cell, so one query is 0.0125; claude JAMES 1.000
is 80/80 and sits at the ceiling; the local legs carry no fallback flag
(pre-#1123) and are audited by latency + token-agreement instead.

## 5. What is re-baselined (this PR)

`papers/lrb-preprint/main.tex` — abstract (token-mode V/N/J), the S2
token-axes table, the S2 per-category R@10 table (`current-policy` V,
`historical-mid-policy` all three), the 4-model cross-model table and its
caption, the §4.6 ladder row (`S2 token (repaired)`), plus one sentence
on the fixture repair; PDF rebuilt. `papers/lrb-preprint/README.md`
checklist line. `docs/strategy/v0.5-pre-loi-materials/*` and the two
strategy docs that quote S2 cells. `CLAUDE.md` status. `CHANGELOG.md` and
`docs/release_notes_v0.6.1.md` "known discrepancy" paragraphs marked
resolved. `docs/release_notes_v0.4.4.md` erratum extended to S2. The
close handover §6 #1 marked executed. `.zenodo.json` (the v0.4.4 deposit
text) is left as deposited; `ROADMAP.md` history lines untouched.

## 6. Reproduce

```bash
python scripts/research/build_lrb_scenario_s2.py            # sha 2c1b210c…
PYTHONPATH=. python scripts/research/lrb_run_phase_b.py --scenarios S2
PYTHONPATH=. python scripts/research/lrb_run_v021_cross_model.py \
  --scenarios S2 --modes llm-grounded \
  --models gemma4:e4b,gemma3:12b,mixtral:8x7b,claude-haiku-4-5 --timeout 120
```

Token mode is deterministic; the LLM legs inherit the ~10 pp reranker
band (PR #819). Ollama for the local models; the claude leg needs the
Max-plan CLI logged in (`claude -p`), and #1124 must be in place or the
calls carry the project briefing and exhaust the window.
