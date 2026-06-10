# RAB Phase 3 Pre-Registration — Zenodo Deposit Guide

> **For**: the operator (Ji_Won_SEO) — manual web upload.
> **Why now**: arXiv submission takes time. While Phase 3 (scenario-S2)
> measurement proceeds in parallel, the pre-registration's *priority
> date* must be anchored to an external, citable timestamped artifact
> — not just a git commit. A standalone Zenodo DOI is the simplest
> external anchor.

## Quick context

- v0.4.3 software DOI (already minted): `10.5281/zenodo.20625533`
- Pre-registration locking commit (PR #774): `d21c680a...`, 2026-06-10
- This deposit packages that pre-registration as a **separate citable
  record** so reviewers can cite the pre-registration without needing
  the whole software archive.

## What's in the bundle

Built by `scripts/research/build_rab_prereg_deposit.py` →
`reports/zenodo/rab-prereg-phase-3-s2.zip`:

```
README.md
r1-phase-3-scenario-s2-preregistration-2026-06-10.md   ← the prereg
RAB-SPEC-v0.1.md                                       ← the frozen spec
build_rab_prereg_deposit.py                            ← provenance witness
```

Metadata recommendation: `reports/zenodo/rab-prereg-phase-3-s2.metadata.json`.

## Upload steps

1. Sign in at https://zenodo.org (use the same account that holds the
   v0.4.3 record).
2. **New Upload**.
3. Drag-and-drop `reports/zenodo/rab-prereg-phase-3-s2.zip`.
4. Fill the form using the values in
   `reports/zenodo/rab-prereg-phase-3-s2.metadata.json`. The fields
   that matter most:
   - **Title** — copy verbatim.
   - **Upload type**: Publication → Preprint.
     (Zenodo doesn't have a "pre-registration" type. "Preprint" is the
     closest match; the title and description make the intent explicit.)
   - **Publication date**: 2026-06-10 (the locking commit's date).
   - **Authors**: Seo, Ji Won.
   - **Description**: copy from the metadata JSON.
   - **Keywords**: copy from the metadata JSON.
   - **License**: CC-BY-4.0.
   - **Related identifiers** (add two):
     - `10.5281/zenodo.20625533` — relation: *is supplement to*,
       resource type: *software*.
     - `https://github.com/Hashevolution/James-RAG-Evol/commit/d21c680a51ba455f6712cca21db38af310b5868f`
       — relation: *is derived from*, resource type: *publication / other*.
5. **Publish**. The DOI is minted immediately.

## After the DOI is minted

1. Update the entry in `MEMORY.md` (the
   `project_r1_replayable_audit_benchmark` line) to add the prereg DOI.
2. Add a one-line cross-reference at the top of
   `docs/research/r1-phase-3-scenario-s2-preregistration-2026-06-10.md`:

   ```
   > Zenodo deposit (priority anchor): https://doi.org/<minted-DOI>
   ```

   This back-link is what reviewers follow.
3. When Phase 3 results land (in `docs/handovers/v0.4-r1-phase-3-...`),
   cite the prereg DOI directly in the handover's first section.
4. When the v0.4.4 release (containing the S2 measurement) is cut, add
   the prereg DOI to `.zenodo.json`'s `related_identifiers` as
   *cites* / *publication-preprint*. Zenodo will then show the prereg
   ↔ measurement linkage in both directions automatically.

## Why not use `.zenodo.json` for the prereg

The repo's `.zenodo.json` is the metadata Zenodo reads on each GitHub
release. We don't want every release to re-mint a copy of the prereg;
we want exactly one prereg record, dated 2026-06-10. Manual web upload
is the cleanest way to get that.

## What this does NOT do

- It does **not** replace the v0.4.3 software DOI (which archives the
  spec + driver + scorer + adapters at release time).
- It does **not** publish a measurement result — Phase 3 measurement
  comes next; the prereg locks the protocol *before* that measurement.
- It does **not** require arXiv. The arXiv preprint (papers/rab-preprint)
  is on a separate track and may be revised (v1.2 / v1.3) to incorporate
  Phase 3 results before submission. The prereg DOI is independent.

## Cost / time

- Free (Zenodo).
- Operator time: ~10 minutes.

## Open questions for the operator

- Whether to use ORCID in the author field (recommended if you have one;
  add to the metadata JSON before upload).
- Whether to mark "Communities" — RAB doesn't fit any obvious community;
  skip unless you want to surface to a specific group.
