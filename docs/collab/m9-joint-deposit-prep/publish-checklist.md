# Joint deposit publish checklist

**For the operator (you), on the day Ali confirms.**

This is the step-by-step. Do not skip steps. Do not improvise
under deadline pressure — the deposit is permanent (Zenodo DOIs
cannot be deleted, only superseded with new versions).

---

## Pre-flight (all must be ✅)

- [ ] Ali confirmed deposit intent in DM (verbatim quote saved)
- [ ] Ali confirmed Vadym attribution decision (4-author with
      Vadym OR 3-author drop)
- [ ] Robin confirmed Vadym primary citation (Phase 1 — natural-
      trigger piggyback in any recent Robin DM)
- [ ] Title chosen from `title-description-draft.md` (Ali / Robin
      marked preferred OR proposed verbatim)
- [ ] Description chosen from `title-description-draft.md` (same)
- [ ] All ORCID iDs collected (Ali / Robin / Vadym if applicable)
- [ ] Robin DOI `10.5281/zenodo.20570701` listed in
      `related_identifiers` (already in draft)
- [ ] Provia walk-back article DOI / canonical URL collected from
      Ali (placeholder in draft)
- [ ] Cycle γ Phase B+C RGB-en data confirmed NOT in deposit (per
      `memory/feedback_eval_cycle_vs_collab_arc_separation.md`)
- [ ] License confirmed (default CC-BY-4.0; switch to MIT only if
      Ali / Robin prefer)

---

## Submission steps

### Step 1 — Final draft assembly

1. Copy `joint-zenodo-draft.json` to scratch location (NOT git).
2. Edit:
   - Remove all `_DRAFT_WARNING`, `_TBD_*`, `_orcid_tbd`,
     `_attribution_status`, `_license_note`, `_note` underscored
     fields. Zenodo treats them as metadata that fails validation.
   - Insert real ORCID iDs.
   - Resolve Vadym row per Ali confirm.
   - Insert Provia URLs.
   - Insert any Ali / Robin verbatim title / description revisions.
3. Verify JSON validity (`python -c "import json; json.load(open('scratch.json'))"`).

### Step 2 — Zenodo upload

1. Log in to https://zenodo.org with Jiwon account (the
   collaboration was negotiated through this account; lineage
   continuity matters).
2. **New upload** → upload type: **Publication** → publication
   type: **Preprint** (per draft).
3. Upload the joint piece artifact (PDF / source / dataset bundle
   — Ali + Robin decide what's IN the upload at finalization).
4. Paste title + description from final draft.
5. Add creators in alphabetical-by-surname order (Afana / Arnaut
   if 4-author / Converse / Seo). Match the order in the draft.
6. Add ORCID for each creator.
7. Add keywords from draft.
8. Add `related_identifiers` from draft. Drop the placeholder
   row.
9. License → CC-BY-4.0 (or MIT if changed).
10. Access right → Open.
11. Language → English.

### Step 3 — Confirm-before-publish

- [ ] Preview page rendered correctly
- [ ] All 4 (or 3) authors visible
- [ ] Title matches verbatim
- [ ] Description first paragraph + headline visible above the
      fold
- [ ] Related identifiers all clickable
- [ ] No leftover `_DRAFT_WARNING` text anywhere

### Step 4 — Publish

1. Click "Publish".
2. Note the new DOI immediately (`10.5281/zenodo.NNNNNNNN`).
3. **Do not retry the publish action** if it appears to hang;
   Zenodo is sometimes slow but the operation is idempotent on
   the deposit record id.

### Step 5 — Post-publish actions

1. **Send 3-author group DM** (Ali + Robin separately, or 1 group
   chat if exists):

   ```
   [Ali, Robin] — joint deposit live: DOI [10.5281/zenodo.NNNN].

   Title + 4-way attribution per the draft we agreed. Vadym
   attribution per Phase 2 confirmation. Robin DOI cross-linked.

   Outline (Track 3.3) is the next natural step — happy to draft
   first or wait for your input, whichever you prefer.

   — Jiwon
   ```

   **NOT** "please review". The deposit is live; review-after-
   publish is fine since they pre-confirmed structure.

2. **Update JAMES solo .zenodo.json files** (v0.4.2 and forward):
   - In `notes` field, change "Three-author joint-piece
     collaboration with Robin Converse (Triava Labs) and Ali
     Afana (Provia) on the substitution/synthesis cost-asymmetry
     finding remains the mid-June trajectory." to
     "The joint discovery is archived at DOI
     10.5281/zenodo.NNNN (Robin Converse / Ali Afana / [Vadym
     Arnaut /] Seo Jiwon)." with link.
   - Add the joint deposit DOI to `related_identifiers` as
     `isReferencedBy` for future solo releases.

3. **Move this folder to archive**:
   - `git mv docs/collab/m9-joint-deposit-prep/
     reports/promo-assets/m9-joint-deposit-archive/`
   - Add a header to README.md noting "ARCHIVED: deposit
     published DOI 10.5281/zenodo.NNNN on YYYY-MM-DD".

4. **Update memory entry**
   `memory/feedback_ali_resume_notice_june6.md` §M9 prep → mark
   as published with DOI. Update
   `memory/feedback_m6_vadym_attribution_3way_timing.md` Phase 3
   → done.

5. **Update collaboration checkpoint** (`docs/handovers/v0.4.x-
   session-2026-05-29-collaboration-checkpoint.md` §5 M9) → done
   with DOI.

---

## If something goes wrong

| Symptom | Action |
|---|---|
| Zenodo rejects the JSON | Strip the `_*` underscored fields; they're for human review only |
| Author order wrong after publish | Zenodo allows author-order edit before assigning version DOI. After version DOI, must create new version with corrected order. Don't panic — just fix and bump. |
| Ali / Robin notice an attribution error after publish | Create new version with correction. Original DOI remains in history. Note in DM that the correction is in the next version. |
| Vadym contact materializes after publish (we never got direct contact) | Add Vadym to next version with proper ORCID; current version retains the placeholder pattern Robin flagged |

---

## What this checklist does NOT cover

- The joint piece outline / manuscript itself (Track 3.3, after
  Track 3 result)
- Joint publication (arXiv / journal) — separate later step
- Joint-piece-related social posts (LinkedIn / dev.to) — happens
  after deposit lands, separately
