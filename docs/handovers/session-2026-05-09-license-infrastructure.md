# Session Handover — 2026-05-09 (Part 2: License Infrastructure)

> **Audience**: the next Claude Code session that picks up license / CLA / IP-boundary work.
> **Companion**: `session-2026-05-09-promotion-readiness.md` (Part 1 — separate handover for promotion-readiness work from the same session).
> **Cycle**: v0.2 Foundation Hardening
> **Branch**: `claude/evaluate-james-project-StJ6F`
> **PR**: #155 (this work + Part 1; awaiting operator review)

This file documents only the **license / IP / CLA** portion of the
2026-05-09 session. For external promotion work, see Part 1.

---

## 0. Reading order for fresh sessions

1. `CLAUDE.md`
2. `docs/handovers/v0.2.0-platform-track.md`
3. `docs/handovers/v0.2.1-business-track.md` (especially §3, §7, §8 decision log)
4. `docs/handovers/session-2026-05-09-promotion-readiness.md` (Part 1)
5. **This file** (license infrastructure, 2026-05-09)
6. `docs/strategy/license-and-monetization.md`
7. `docs/strategy/ip-boundary.md`
8. `.github/CLA.md`

---

## 1. What this handover covers

License / IP / CLA infrastructure work from the 2026-05-09 session
(commit 5 of the 6 commits on PR #155):

| # | SHA | Theme |
|---|---|---|
| 5 | `7e8629dd` | `.github/CLA.md` + `docs/strategy/{license-and-monetization,ip-boundary}.md` + Commercial use sections in both READMEs + CONTRIBUTING CLA section + PR template CLA checkbox + business-track multi-section update |

(Commits 1–4 are promotion-readiness; see Part 1.)

**Strategic intent**: preserve future commercial-license options for v0.4+
before any external PR is merged. Without the CLA, relicensing later would
require permission from every contributor — a known failure mode for OSS
projects that try to relicense after contributors are no longer reachable.

---

## 2. New files (license-related)

| File | Purpose |
|---|---|
| `.github/CLA.md` | Contributor License Agreement (Apache-style ICLA, with explicit relicense grant + Korean summary in §11). 11 sections covering grants, representations, signing protocol (§9), and the rationale specific to JAMES (§8) |
| `docs/strategy/license-and-monetization.md` | License + revenue model analytical framework. 4 candidate models (MIT / Open Core / AGPL+dual / BSL), weighted decision matrix scoring Open Core highest at 52, hybrid options, deadlines (§9), recommendation in §6 (analytical, not binding) |
| `docs/strategy/ip-boundary.md` | Mother (engine) / domain pack (knowledge) code-level boundary specification. Current file inventory (all mother today, §3), 11 plugin API requirements derived from license framing for v0.3 (§5) |

## 3. Files modified (license-related)

| File | Change |
|---|---|
| `README.md` | New "Commercial use" section before License section. Declares future domain pack commercial license possibility, references CLA + strategy docs |
| `README.ko.md` | Mirror: new "상용 사용" section |
| `CONTRIBUTING.md` | New "Contributor License Agreement (CLA)" section after Code Review section. Reference CoC file. Add `ip-boundary.md` to required reading. CLA acknowledgment added to PR Process step 8 |
| `.github/PULL_REQUEST_TEMPLATE.md` | New "CLA acknowledgment (required)" section with 2 checkboxes (read CLA + verifiable identity). Discipline checklist + 1 row (no `packs/*` subdirectory) |
| `docs/handovers/v0.2.1-business-track.md` | §5: 2 new rows (license/monetization decisions, mother/pack boundary). §7: public-OK list extends with strategy docs + CLA. §8: 4 new decision log entries (CLA introduced, IP boundary documented, license analysis published, Commercial use sections added). §9: 4 new companion document rows (CLA, strategy docs ×2, CoC). §10: license/monetization update procedure. §11: Korean summary references new strategy docs |

---

## 4. License decision schedule

The single most strategically important pending decision. Per
`docs/strategy/license-and-monetization.md` §9:

| By | Decision required | Status |
|---|---|---|
| v0.2 close (~month 4) | CLA + IP boundary doc in place | ✅ done this session |
| v0.3 close (~month 10) | Plugin API boundary clean enough that domain packs can ship from separate repos | pending v0.3 |
| **v0.4 start (~month 10–14)** | **Final license commitment for first domain pack — IRREVOCABLE** | **decision required** |
| v0.4 close (~month 22) | Decide whether mother license also changes (likely no) | pending v0.4 |
| v1.0 (~month 22+) | Public pricing thesis | pending v1.0 |

**Recommendation (analytical, not binding)**: stay MIT through v0.3; at v0.4
ship first domain pack from a separate private repo under commercial license;
mother stays MIT through v1.0.

The recommendation may shift based on:
- Korean B2B OSS contract culture maturity
- Specific large-customer terms offered before v0.4
- Competitor scenarios (e.g., a hyperscaler announces a managed JAMES)

The actual decision lives in private operator notes per business-track §7
until formally announced via §8 decision log.

---

## 5. The 4 candidate license models (summary)

Full analysis in `docs/strategy/license-and-monetization.md` §3. Quick reference:

| Model | Core idea | Korean B2B fit | Reversibility |
|---|---|---|---|
| **MIT (status quo)** | All free | Low (weak OSS contract culture) | One-way (CLA preserves option) |
| **Open Core** | Mother MIT + packs commercial in private repos | Moderate-High (familiar Atlassian/GitLab pattern) | High (packs additive) |
| **AGPL + Dual** | Whole project AGPLv3 + commercial license sold separately | Mixed (AGPL allergy in Korea) | Hard once contributions merged |
| **Business Source License** | Source-available with restrictions, auto-OSS after 4 yr | Low awareness | Auto-fallback |

Weighted decision matrix in `license-and-monetization.md` §4 scores Open Core
highest (52 / 55).

---

## 6. CLA mechanics

### What the CLA does

- Grants the Maintainer perpetual rights to use, distribute, AND **relicense**
  the project as a whole
- Inbound MIT remains in place
- Contributor retains ownership of their work; can use it elsewhere

### How signing works (per `.github/CLA.md` §9)

1. PR template checkbox: "I have read `.github/CLA.md` and agree to its terms"
2. Verifiable GitHub identity OR `Signed-off-by:` line in commits

Both required. Manual review verifies before merge. No GitHub App installed
yet (operator's call; manual is fine at current PR volume of 0 external PRs).

### Critical rule

**Once a PR is merged WITHOUT CLA acknowledgment, that file's relicense
option is permanently lost.** The next session must enforce this strictly:

- Reject PRs missing the checkbox
- Reject PRs from anonymous or unverifiable accounts
- Manual review must explicitly confirm CLA before merge

---

## 7. IP boundary specification (preview)

Full spec in `docs/strategy/ip-boundary.md`. Quick reference:

> **Mother contains the engine. Packs contain the knowledge.**

| Today | Future (v0.4+) |
|---|---|
| All current source = mother (MIT, public) | Mother stays MIT, public |
| 0 domain packs | First pack: `packs/cafe/` ships from a separate private repo under commercial license |
| No `packs/*` subdirectory in this repo | Same — packs live in different repos |

11 plugin API requirements (`ip-boundary.md` §5) flow from this boundary.
The v0.3 Platform Skeleton milestone implements them.

---

## 8. Discipline rules to enforce (license-side)

1. **No PR merged without CLA acknowledgment** — otherwise relicense option lost permanently for that file
2. **No `packs/*` subdirectory** in this repo, even empty stubs (`.gitkeep` etc.)
3. **No domain code in mother** (`core/`, `tools/`, etc.)
4. **No license decision committed before v0.4** — `license-and-monetization.md` is analytical only
5. **No CLA modification** after first external PR is merged (would require contributor consent)
6. **Decision logs append-only** — `business-track §8`, `ip-boundary.md §8`, `license-and-monetization.md §7` table
7. **Strategy docs are public-friendly analytical** — never commit specific pricing, customer names, or contract terms (those go in private operator notes per business-track §7)
8. **Don't change `LICENSE` file directly** — CLA is the inbound mechanism, MIT remains the outbound

---

## 9. Likely first-actions for the next session

1. v0.3 Plugin API design picks up `ip-boundary.md` §5 11 requirements
2. If first external PR arrives: STRICT CLA enforcement check before merge
3. License analysis micro-revisions if Korean B2B evidence shifts
4. Operator commits final license decision → append to `business-track §8`
   decision log (when v0.4 cutover arrives)
5. Watch for any accidental `packs/*` directory in PRs and reject

---

## 10. Things NOT to do

1. Modify `.github/CLA.md` after any external PR is merged
2. Add license language to repo without explicit operator approval
3. Commit final license decision to repo before v0.4 (it lives in private
   operator notes per §7)
4. Add `packs/*` subdirectory of any kind during v0.2-v0.4
5. Change `LICENSE` file directly — CLA is the inbound mechanism, LICENSE is
   the outbound
6. Modify recommendation in `license-and-monetization.md` §6 without
   explicit operator instruction
7. Merge an external PR without explicit CLA verification (the
   discipline-killing scenario)
8. Disclose specific pricing or customer names in any strategy doc

---

## 11. Risks specific to license infrastructure

| Risk | Mitigation |
|---|---|
| External PR merged without CLA | Manual review check; PR template hard-required checkbox; re-verify before merge |
| `packs/*` slipping into this repo | PR template checkbox; reviewer enforcement; CI grep for `packs/` if/when CI added |
| License recommendation in repo getting taken as commitment | Strategy doc explicitly says "analytical, not binding"; final decision lives in private notes |
| Contributor uses anonymous GitHub account | CLA §9 requires verifiable identity OR `Signed-off-by:`; reject anonymous |
| Corporate signers contributing without CCLA | Per CLA §9, contact maintainer to arrange written CCLA before accepting their PRs |
| Domain knowledge leaking into mother through mis-categorized PR | `ip-boundary.md` §2 boundary rule; reviewer enforces "engine vs knowledge" split |
| Korean enterprise asks for everything under MIT including pack | Per `license-and-monetization.md` §8: pack license non-negotiable; services + customization are |

---

## 12. State summary (30-second read)

- **What**: CLA + license/monetization analysis + IP boundary + Commercial use disclosure
- **Where**: PR #155 commit 5 (`7e8629dd`)
- **Cycle**: v0.2 Foundation Hardening
- **License now**: MIT (CLA preserves future relicense options)
- **License recommendation (analytical)**: Open Core at v0.4 (mother MIT, packs commercial private repo)
- **Critical deadline**: v0.4 start (~month 10–14) — final license commitment, IRREVOCABLE
- **CLA enforcement**: required for every external PR; missing = relicense option permanently lost for that file
- **Forbidden**: `packs/*` directory anywhere in this repo until v0.4
- **Promotion / channel work**: see Part 1 (`session-2026-05-09-promotion-readiness.md`)

---

## 13. 한국어 핵심 요약

이 핸드오버는 **라이선스 / CLA / IP 경계 인프라**만 다룹니다 (외부 홍보 준비는 Part 1 별도).

이 세션이 한 1개 commit (`7e8629dd`):
- `.github/CLA.md` (Apache ICLA 어답테이션 + relicense 권한 명시 + 한국어 요약)
- `docs/strategy/license-and-monetization.md` (4개 모델 분석, 가중치 점수, 추천)
- `docs/strategy/ip-boundary.md` (mother/팬 경계 + 11개 plugin API 요구사항)
- 양 README "Commercial use" / "상용 사용" 섹션
- CONTRIBUTING.md CLA 섹션
- PR 템플릿 CLA 체크박스
- business-track §5/§7/§8/§9/§10/§11 갱신

다음 세션이 알아야 할 핵심:
- **CLA가 도입되었음** — 외부 PR 머지 전 acknowledgment 체크 필수. 머지 후엔 그 파일의 relicense 옵션 영구 손실
- **라이선스 최종 결정은 v0.4 전까지 (~10–14개월 후)** — 현재는 분석만, MIT 유지
- **추천 방향 (잠정)**: Open Core (mother MIT 유지, 도메인 팬 별도 private repo + 상용 라이선스)
- **`packs/*` 디렉토리 v0.2-v0.4 동안 절대 금지** — 빈 디렉토리도 금지
- **strategy 문서는 공개용 분석만** — 가격/고객명/계약조건은 비공개 운영자 노트에 (business-track §7)
- **`.github/CLA.md` 외부 PR 머지 후엔 수정 금지** (contributor 동의 필요)

다음 세션 첫 작업으로 예상:
1. v0.3 Plugin API 설계가 `ip-boundary.md` §5 11개 요구사항 픽업
2. 첫 외부 PR 도착 시 CLA enforcement 검증
3. 한국 B2B 증거 축적되면 license-and-monetization.md 미세 갱신
4. v0.4 cutover 시 운영자가 최종 라이선스 결정 → business-track §8 append

외부 홍보 / 채널 / 커뮤니티 관련 작업은
`session-2026-05-09-promotion-readiness.md` (Part 1) 참조.
