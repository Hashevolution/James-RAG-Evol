# M9 — Joint Zenodo deposit prep (CLOSED — PUBLISHED 2026-08-19)

> **This folder is historical.** The deposit went live on 2026-08-19 as
> DOI `10.5281/zenodo.22030935` (report, CC-BY-4.0, Afana / Converse /
> Seo). The authoritative outcome record is
> `reports/promo-assets/m9-joint-deposit-record.md`. Everything below
> is the pre-publication draft state, kept as the audit trail — the
> publish gates, the draft metadata and the title/description options
> are all superseded by the published text.

**Status**: INTERNAL PREP ONLY. Publish requires Ali Afana
explicit confirm after 6/7+ resume window.
**Date created**: 2026-06-08
**Lineage**: Phase R6 commitment "lightweight joint deposit before
the outline" + Ali 2026-05-28 DM "If a window opens before then,
the joint record is what I'd pick up first".

---

## What this folder is

Internal draft artifacts for the mid-June joint Zenodo deposit (3
or 4-author, TBD on Vadym Phase 2 sequencing). Solo prep is
permitted per `memory/feedback_ali_resume_notice_june6.md` §M9 prep
rule:

> "Joint deposit 사전 준비는 선택적 — `.zenodo.json` 3-author
> skeleton + title/description draft + four-way attribution mapping
> (Vadym 포함) 을 6/7 전에 미리 만들어 두면 window 재개 시 즉시
> submit 가능. 단 publish 는 Ali confirm 후. 일방 진행 안 함."

This folder satisfies the "사전 준비" half. Publish gates explicitly
documented in §4 below.

---

## What this folder is NOT

- ❌ Not a publish-ready artifact. The `joint-zenodo-draft.json`
  here MUST NOT be submitted to Zenodo without Ali's explicit
  go-ahead.
- ❌ Not a replacement for the repo-root `.zenodo.json` (which is
  the JAMES solo-release metadata for v0.4.2 software releases).
- ❌ Not a joint-piece manuscript / publication draft. That's
  Track 3.3 (joint piece outline) after Track 3 cross-family
  results arrive.
- ❌ Not cycle γ Phase B+C evidence pile. Cycle γ is a separate
  JAMES-internal evaluation arc — see
  `memory/feedback_eval_cycle_vs_collab_arc_separation.md`.

---

## Files in this folder

| File | Purpose |
|---|---|
| `README.md` (this file) | Index, publish gates, change-log |
| `joint-zenodo-draft.json` | Draft `.zenodo.json` for the joint deposit — 3-author baseline with Vadym placeholder. Title / description / creators / contributors / related_identifiers all in draft form. |
| `title-description-draft.md` | Title + description text alternatives, with rationale for each option. Ali / Robin can mark preferred. |
| `four-way-attribution-catalog.md` | Full 4-way contributor mapping with verbatim vocabulary quotes from each (joint-piece-locked phrases). Source of truth for any deposit-time citation. |
| `ali-findings/` | The four engineering-findings replies, **one message per finding** (Ali's numbering). `ali-findings/README.md` carries the sending order and the per-message gates. ①②③ are sendable; ④ is held for the Track 2c re-measurement. Supersedes the single merged draft `ali-reply-4-draft-engineering-findings.md`, now removed. |
| `publish-checklist.md` | Operator step-by-step for the day Ali confirms — what to verify, what to paste, what to NOT paste. |

---

## Publish gates (ALL must be ✅ before submit)

1. **Ali Phase 2 confirmation of Vadym attribution** — Ali knows
   Vadym is in the catalog. Per
   `memory/feedback_m6_vadym_attribution_3way_timing.md` Phase 2
   sequencing.
2. **Robin Phase 1 primary citation confirmed for Vadym** — Robin
   confirms the specific Vadym contribution we cite. Natural-
   trigger piggyback on next Robin outgoing DM (Direction 3 result
   share, etc.), NOT a single-purpose ask DM.
3. **3 vs 4-author decision made** — Ali + Robin both prefer one
   shape. If unclear, default = 4-author (Robin/Ali/Vadym/Jiwon)
   with Vadym as the last alphabetical contributor by surname.
4. **Title + description final** — Ali + Robin both marked preferred
   options OR agreed verbatim. The `title-description-draft.md`
   has multiple alternatives precisely so this conversation can
   happen quickly.
5. **No cycle γ findings included** — confirm draft contains only
   the pre-committed scope (3-axis substitution/synthesis +
   workload gradient + model-scale; JAMES axis = Direction 1 7-tier
   closure PR #461/#463 / DOI 10.5281/zenodo.20363998, with V3'.e
   PR #440 as its 3-level precursor; + Robin 26b + Ali e-commerce
   evidence). Cycle γ Phase B+C RGB-en data is OUT.
6. **License agreement** — Joint deposit is MIT (default). If Ali
   prefers CC-BY for the dataset half, adjust.
7. **Related_identifiers cross-link to Robin DOI** —
   `10.5281/zenodo.20570701` listed as `isReferencedBy` for the
   26B byte-identical reproduction track.

---

## What changes after publish

When the deposit goes live, this folder's content moves to
`reports/promo-assets/m9-joint-deposit-record.md` (read-only
archive) and the live `.zenodo.json` on Zenodo replaces this
draft. The draft files here become historical record.

---

## Change log

| Date | What | Why |
|---|---|---|
| 2026-06-08 | Folder created with skeleton files | M9 prep, post Robin DOI arrival (10.5281/zenodo.20570701) + Ali resume window opening |
| 2026-08-19 | Axis-2 citation pointers corrected (PR #440 → Direction 1 PR #461/#463 + DOI 10.5281/zenodo.20363998) across all 4 draft files + `CLAUDE.md`; `eval_count` / thinking-trace caveat + canonical bullet added to `title-description-draft.md` | Ali's third-leg deposit cited this axis as "seven-tier ... PR #440, Issue #448"; the mislabel originated in this folder. See `title-description-draft.md` §Axis 2 |
| 2026-08-19 | Ali final-text review — conditional OK drafted (`ali-reply-2-draft-2026-08-19.md`) | Ali circulated the submit-ready v1.0.0 text after measuring the instruction on/off arm we asked for. Two body sentences overreach his own "does not claim" section (spread-vs-SE inference on the 9% instruction effect; the no-trace explanation stated as measured). Axis-2 wording, the three v0.3.x DOIs, the no-concept-DOI rule and the managed-Gemini → gpt-4o-mini correction all landed verbatim. Robin's model-scale axis is absent from this version — flagged to her, not decided by us. |
| 2026-08-21 | Fourth reply split into `ali-findings/` — one message per finding — and the merged draft removed | Three reasons converge: our own first reply promised each finding "in its own message"; Ali's fourth message states "one message per finding is the right shape"; and finding ④ is blocked on an operator-gated re-measurement, so a merged send would hold ①②③ hostage to it. Second change in the same pass: finding ③ now opens with the **non-reproduction** — `ATTACK_PATTERNS` in `core/security_layer/_policies.py` is English and Korean only, so there is no Arabic keyword gate here to bypass — before the two places it did reproduce (runtime normalisation gate, adversarial scorer). The merged draft opened it as "Reproduced", which led with the convenient half. |
