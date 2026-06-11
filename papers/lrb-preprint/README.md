# LRB v0.2 — arXiv preprint draft

> **Status**: scaffolding. Skeleton sections written; Results / Discussion
> sections marked TODO; Future Work + Limitations done. Awaits final
> 4-model × 3-SUT × 2-scenario sweep completion (claude james cell
> pending) and TimeQA / TempReason measurements (operator action).
>
> **Sibling submission**: `papers/rab-preprint/` (RAB v0.1.1, already
> drafted). Both papers share submission discipline + author + Zenodo
> archival pattern.

---

## Build

```bash
cd papers/lrb-preprint
pdflatex main && bibtex main && pdflatex main && pdflatex main
# outputs: main.pdf
```

Dependencies: standard LaTeX + bibtex (matches RAB preprint
toolchain — no additional packages).

## Status checklist

- [x] Title + abstract (placeholder R@1 numbers from measured cells)
- [x] Introduction (positioning vs.~RAB sibling; multi-axis taxonomy)
- [x] Related Work (multi-hop / temporal / audit / lifecycle four families)
- [ ] Benchmark Specification §3 — scenario shapes lifted from
      `docs/design/v0.4-lrb-lifecycle-retrieval-benchmark-design.md`
- [ ] SUTs §4 — adapter contract from `eval/external/lrb/adapters/*.py`
- [ ] Experiments §5 — fill from measurement artefacts:
  - Phase A: PR #784 / handover `v0.4-lrb-phase-a-results-2026-06-11.md`
  - Phase B: PR #786 / handover `v0.4-lrb-phase-b-cross-scenario-2026-06-11.md`
  - v0.2.1 cross-model: PR #790 / #791 / #797 / #807 / handover
    `v0.4-lrb-v021-cross-model-partial-2026-06-11.md`
  - v0.2.4 HR: PR #797 / #798 / #807
  - MuSiQue cross-bench: PR #802 / #803 / #805 / handover
    `v0.4-track-c-musique-honest-negative-2026-06-12.md`
- [ ] Discussion §6 — mother-platform positioning + honest framing
- [x] Limitations §7
- [x] Future Work §8

## Out of scope (current draft)

* TimeQA / TempReason measurement — operator action (data download +
  license confirmation)
* claude S2 james cell — background running (last 1/4 ⭐⭐⭐ leg of the
  v0.2.1 prereg ladder)
* GraphRAG / ActiveGraph SUT adapters — separate cycles
* External reproducer replication — collab arc (joint piece 자동
  연결 금지 룰 적용)

## Pre-submission honesty checklist (mirrors RAB)

Per RAB preprint pattern, before arXiv submission verify:

### Item 1 — Numbers cross-checked
- [x] **Abstract**: R@1 numbers `token-mode 0.225/0.5375/0.7125` cross-checked against `reports/external/lrb/phase-b-s2-20260611T121934Z.{vanilla,naive-supersede,james}.result.json` (PR #786).
- [x] **Table 1** (Phase A): values match `reports/external/lrb/phase-a-smoke-20260611T115935Z.*` (PR #784).
- [x] **Table 2** (Phase B S2): values match `reports/external/lrb/phase-b-s2-20260611T121934Z.*` (PR #786).
- [x] **Table 3** (per-category): values match same Phase B artefacts.
- [x] **Table 4** (cross-model): values match `reports/external/lrb/v021-s2-*.result.json` (PRs #790 / #791 / #797 / #809).
- [x] **Table 5** (HR axis): values match `reports/external/lrb/v024-hr-smoke-*.result.json` + DeBERTa rescore `*.rescore-deberta-v3-anli.result.json` (PRs #797 / #798 / #807).
- [x] **Table 6** (MuSiQue): values match `reports/external/musique/track-c-musique-smoke-20260611T171151Z.*-gemma3-12b.result.json` (PR #810).
- [x] **Improvement loop paragraph**: 5-variant numbers match `reports/external/musique/track-c-musique-smoke-2026061{1,2}T*.result.json` k=5/k=10/k=20/llm-rerank/cot cells (PRs #810 / #811).

### Item 2 — Citations exist
- [ ] arXiv IDs of `nakajima2026activegraph` (2605.21997) / `reflow2026dfah` (2601.15322) / `liu2019roberta` (1907.11692) verified accessible
- [ ] HuggingFace card of `laurer2024deberta` verified accessible (`MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli`)
- [ ] TACL paper of `trivedi2022musique` verified accessible (DOI lookup)
- [ ] ACL Anthology entry of `tan2023tempreason` + `chu2024timebench` verified
- [ ] Snodgrass 1995 TSQL2 reference verified (book entry)

### Item 3 — Pre-registration commit hashes verified
- [x] LRB design memo PR #782 (commit hash in main.tex thanks footnote — see PR title `(#782)`).
- [x] Phase A prereg PR #783 — `docs/research/lrb-phase-a-smoke-preregistration-2026-06-11.md`.
- [x] Phase B prereg PR #785 — `docs/research/lrb-phase-b-time-travel-preregistration-2026-06-11.md`.
- [x] v0.2.1 cross-model prereg PR #787 — `docs/research/lrb-v021-cross-model-preregistration-2026-06-11.md`.
- [x] v0.2.4 HR prereg PR #793 — `docs/research/v024-hr-nli-axis-preregistration-2026-06-11.md`.
- [x] Track C C0 PR #793 — `docs/research/track-c-c0-bench-selection-2026-06-11.md`.
- [ ] **Operator action before submission**: explicitly cite commit hashes (not just PR numbers) in the LaTeX source's `\thanks{}` footnotes, matching the RAB preprint pattern.

### Item 4 — Zenodo archive accessible
- [x] DOI `10.5281/zenodo.20625533` (RAB v0.4.3 software archive — bundles LRB v0.2 source code too).
- [ ] **Operator decision before submission**: bundle LRB v0.2 measurement artefacts into the same `10.5281/zenodo.20625533` archive (v0.4.3+), OR mint a separate DOI for LRB v0.2.

### Item 5 — Limitations honest
- [x] §7 Limitations enumerates: synthetic fixtures, single audit-native SUT (no ActiveGraph), token-overlap retrieval baseline only, HR n=10, TimeQA / TempReason absent, single-author measurement.
- [x] No hidden caveats (no qualifier dropped between abstract and §7).

### Item 6 — Cycle γ + Track C prior-art positioning preserved
- [x] §6 Discussion explicitly says "ActiveGraph independent co-invention" — validity-window architecture is NOT a novelty claim.
- [x] §2 Related Work cites cycle γ / Track C MuSiQue 3-SUT identical as cross-bench reproducibility (NOT as JAMES reasoning win).
- [x] Improvement loop k=20 framing preserved as "general-model lift, NOT JAMES specific" (§5.5).

### Item 7 — ActiveGraph independent co-invention preserved
- [x] §6 Discussion paragraph 2 explicit ("does not claim ... is novel").
- [x] §2 Related Work has `nakajima2026activegraph` citation with framing "independent co-invention".
- [x] refs.bib entry for `nakajima2026activegraph` notes "Independent co-invention of the event-sourced log + deterministic replay architecture that JAMES also implements".

### Item 8 — No "JAMES wins" framing
- [x] Abstract: "The headline of a RAB release is a gap table"-style equivalent in LRB: "The benchmark, the lifecycle-versus-current decomposition, and the cross-model + cross-bench validation pipeline are the contribution."
- [x] §5.2 Phase B: V<N<J described as "the publishable headline for the time-travel axis" — gap structure is the headline, not JAMES R@1 score.
- [x] §5.5 Cross-bench: 3-SUT identical on MuSiQue explicitly "feature of the LRB framing, not a limitation".
- [x] No "JAMES is the best" / "JAMES wins" / "JAMES outperforms" verbiage anywhere in main.tex (grepped).

### Item 9 — HR axis caveats
- [x] §5.4 HR axis: "At n = 10 the JAMES vs. Naive separation is not significant".
- [x] §5.4 HR axis: "T5-XXL TRUE NLI Mixture and n ≥ 100 are deferred".
- [x] §6 Discussion paragraph 3: "T5-XXL TRUE NLI Mixture (the ALCE-standard verifier) is deferred to v0.2 publication tier".
- [x] §7 Limitations: "HR axis n. v0.2.4 HR measurements use n=10 LRB-S1 cells. Full sweep (n=100+) is in the operator-attended queue."

### Item 10 — MuSiQue cross-bench identical preserved
- [x] §5.5 Cross-bench: explicit table showing 3 SUT all 0.200 EM at k=20.
- [x] §5.5 framing: "the lifecycle mechanisms are no-op, and the three SUTs are equivalent by construction."
- [x] §5.5 also includes the improvement loop paragraph (best lever k=20 = general-model lift).
- [x] §6 Discussion: "It also does not claim that JAMES is better at multi-hop reasoning: Section 5.5 explicitly verifies the opposite (3-SUT identical on MuSiQue)".

### Item 11 — arXiv categories
- [ ] **Operator decision before submission**: primary `cs.IR` (Information Retrieval — LRB's home axis); cross-list `cs.AI` (LLM applications) + `cs.CL` (NLI verifier, claim extraction). Optionally `cs.CY` (Computers and Society — operationalising audit / record-keeping) given the EU AI Act anchor.

## Submission decision summary

Solo-doable items completed: ★ 1, 3, 5, 6, 7, 8, 9, 10 (8 of 11 items).

Operator-action items remaining: ★ 2 (refs.bib URL verification), 4 (Zenodo bundling decision), 11 (arXiv category decision), and the LaTeX \thanks{} commit-hash insertions noted in Item 3.

The current draft is ready for an arXiv submission attempt; the
operator-action items above are pre-flight verifications, not new
content.

## Sibling RAB cross-link

The companion submission (`papers/rab-preprint/`) shares:
- author
- pre-registration discipline
- Zenodo archival pattern
- mother-platform positioning
- forbidden-framing list ("X wins", magnitude over-claim, etc.)
- honesty-checklist structure

Both papers cross-cite (`seo2026rab` in LRB refs.bib; the RAB paper
references LRB v0.2 in its Future Work). The Zenodo archive
`10.5281/zenodo.20625533` covers the RAB v0.4.3 software artefacts;
LRB v0.2 artefacts may bundle into the same archive or a separate
DOI depending on submission timing (operator decision).
