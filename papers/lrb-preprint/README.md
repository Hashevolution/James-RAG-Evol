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

1. [ ] All numbers in abstract/intro/experiments cross-checked against committed result.json files
2. [ ] All cited works exist (arXiv ID / DOI / URL verified)
3. [ ] All pre-registration commit hashes verified
4. [ ] Zenodo archive accessible
5. [ ] Limitations honest (no hidden caveats)
6. [ ] Cycle γ + Track C prior-art positioning preserved (validity-window architecture is NOT novelty claim)
7. [ ] ActiveGraph independent co-invention preserved
8. [ ] No "JAMES wins" framing; gap-structure-is-the-headline rule
9. [ ] HR axis caveats (n=10 smoke; T5-XXL deferred)
10. [ ] MuSiQue cross-bench cell-by-cell identical preserved (the strongest possible honest negative on JAMES reasoning)
11. [ ] arXiv categories: cs.IR primary, cs.AI + cs.SE cross-list

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
