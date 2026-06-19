# JAMES Reproducibility Program (Phase 3)

We want independent validation of the published RAB / LRB numbers. If you run
`benchmarks/run_all.sh` on your own hardware, please tell us what you got —
**whether it matched or not.** Negative and variant reproductions are as
valuable as confirmations; the project's entire evaluation history is built on
honest null results.

## How to submit a reproduction

1. Run the core tier (and optionally `--full` / `--with-llm`):
   ```bash
   bash benchmarks/run_all.sh
   ```
2. Open a GitHub issue using the **"Reproduction report"** template
   (`.github/ISSUE_TEMPLATE/reproduction-report.yml`). Include:
   - Operating system
   - Hardware configuration (CPU / RAM / GPU)
   - Python version + whether you used `requirements.txt` or `requirements_pinned.txt`
   - Model version (only if you ran the LLM tier)
   - The benchmark output (paste the RAB + LRB tables)
   - Which tier(s) you ran

## How we triage (labels)

| Label | Meaning |
|---|---|
| `reproduction-confirmed` | Core-tier numbers byte-identical to `benchmarks/README.md`; LLM-tier inside bands |
| `reproduction-variant` | Core-tier identical, LLM-tier outside band, OR a documented environment difference explains a delta |
| `reproduction-failed` | Core-tier numbers differ — a real discrepancy we need to investigate |

A `reproduction-failed` on the **core tier** is treated as a potential bug in
a fixture or scorer and gets priority — the core tier is supposed to be
byte-identical, so a mismatch means something genuinely diverged.

## Public tracking

Confirmed/variant/failed reproductions are tracked openly via the labels above
(`is:issue label:reproduction-confirmed` etc.). The goal is **3–5 independent
reproductions** on hardware other than the reference RTX 4070 SUPER machine.

> **Operator note (not auto-created by this doc):** the three labels above
> must be created once in the repo settings (Issues → Labels), and the issue
> template enabled. This file + the template are committed; label creation and
> the "call for reproductions" announcement are manual operator steps — see
> `docs/external/announcement-drafts.md`.

## Scope

This program covers the **deterministic RAB + LRB core** (and the band-checked
RAGAS sibling). It does **not** solicit reproductions of generic "Graph-RAG
reasoning gains" — the project does not claim those; see
`benchmarks/README.md` "What this package deliberately does NOT claim".
