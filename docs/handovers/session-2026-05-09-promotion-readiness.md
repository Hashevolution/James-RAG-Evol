# Session Handover — 2026-05-09 (Part 1: Promotion Readiness)

> **Audience**: the next Claude Code session that picks up promotion / external-visibility work.
> **Companion**: `session-2026-05-09-license-infrastructure.md` (Part 2 — separate handover for license / IP / CLA work from the same session).
> **Cycle**: v0.2 Foundation Hardening
> **Branch**: `claude/evaluate-james-project-StJ6F`
> **PR**: #155 (this work + Part 2; awaiting operator review)

This file documents only the **promotion-readiness** portion of the
2026-05-09 session. For license / CLA / IP boundary work, see Part 2.

---

## 0. Reading order for fresh sessions

1. `CLAUDE.md`
2. `docs/handovers/v0.2.0-platform-track.md`
3. `docs/handovers/v0.2.1-business-track.md` (especially §12 communication discipline)
4. **This file** (promotion readiness, 2026-05-09)
5. `docs/handovers/session-2026-05-09-license-infrastructure.md` (license, 2026-05-09)
6. `docs/marketing/channels.md`

---

## 1. What this handover covers

Promotion-readiness work from the 2026-05-09 session (4 of the 6 commits on PR #155):

| # | SHA | Theme |
|---|---|---|
| 1 | `08e9f111` | `docs/marketing/channels.md` (channel catalog) + `business-track §12` (communication discipline) |
| 2 | `5ce859af` | `CODE_OF_CONDUCT.md` + `.github/ISSUE_TEMPLATE/*` + `.github/PULL_REQUEST_TEMPLATE.md` (initial version) |
| 3 | `419e0367` | README.md polish: 4 new badges, version v0.1.4, roadmap section, "Stay in touch" CTA |
| 4 | `24540729` | README.ko.md mirror of #3 |

(Commit 5 `7e8629dd` is license-infrastructure; see Part 2.)

**Strategic intent**: prepare external visibility (GitHub Topics, awesome
lists, Korean dev community, blog series, eventually Show HN) while
preserving the v0.2-cycle communication discipline (no domain marketing,
no buzzwords, cycle-aligned tagline only).

---

## 2. New files (promotion-related)

| File | Purpose |
|---|---|
| `docs/marketing/channels.md` | External promotion channel catalog. 7 categories, ~25 channels, append-only activity log in §10 |
| `CODE_OF_CONDUCT.md` | Contributor Covenant 2.1 (community signal + OpenSSF Badge requirement) |
| `.github/ISSUE_TEMPLATE/bug_report.yml` | Form-based bug template (component dropdown, environment fields) |
| `.github/ISSUE_TEMPLATE/feature_request.yml` | Cycle-alignment dropdown + domain-agnostic checkbox |
| `.github/ISSUE_TEMPLATE/config.yml` | Disable blank issues + 3 contact links (security / discussions / docs) |
| `.github/PULL_REQUEST_TEMPLATE.md` | Cycle alignment + 7-row discipline checklist (CLA acknowledgment section added later in commit 5; see Part 2) |

## 3. Files modified (promotion-related)

| File | Change |
|---|---|
| `README.md` | 4 new badges (last-commit, GitHub stars, Contributor Covenant 2.1, OpenSSF Best Practices pending) + version v0.1.4 + v0.2 cycle marker + Roadmap section refresh + "Stay in touch" section with star CTA |
| `README.ko.md` | Mirror of README.md changes (badges, 함께하기 section) |
| `docs/handovers/v0.2.1-business-track.md` | New §12 "External communication discipline" (cycle-aligned messaging table, forbidden categories, channel-category overview, approval rules, Korean summary). 3 new decision log entries in §8 (External promotion plan adopted, Show HN held until v0.2 closes, Domain marketing forbidden through v0.4). channels.md row added to §9 companion documents |

(Note: README "Commercial use" sections, CONTRIBUTING.md CLA section, and
business-track license-related updates are documented in Part 2.)

---

## 4. Pending operator actions (D.2 external)

These items require operator account access or external repos — Claude
MCP scope is restricted to `Hashevolution/james-rag-evol` and
`Hashevolution/james-prototype`. Listed in priority order, easiest first:

| # | Action | Where | Time |
|---|---|---|---|
| 1 | GitHub Topics on repo | Settings → General → Topics. Recommended: `graphrag, rag, local-llm, korean, rbac, self-hosted, audit-log, policy-engine, ollama, ontology` | 5 min |
| 2 | OpenSSF Best Practices Badge | https://www.bestpractices.dev/ | 30 min |
| 3 | Awesome-llm-apps PR | github.com/Shubhamsaboo/awesome-llm-apps (108K ★) | 1 hr |
| 4 | Awesome-graphrag PR | (find current top list) | 1 hr |
| 5 | Awesome-self-hosted-ai PR | (find current top list) | 1 hr |
| 6 | Awesome-rag PR | (find current top list) | 1 hr |
| 7 | GeekNews post | news.hada.io | 30 min |
| 8 | Disquiet post | disquiet.io | 30 min |
| 9 | Generative AI Korea (FB) post | Facebook (~100K+ members) | 30 min |

When operator exercises any of items 1–9, append a row to
`channels.md` §10 activity log with format:
`Date | Channel | Summary | Result`. Activity log is append-only.

---

## 5. Held until v0.2 closes (~3-5 months)

Per business-track §12.4:

- Show HN (single-shot, must be paired with RAGAS + STEP 7 numbers from Axis 2-A/B)
- Reddit r/LocalLLaMA + r/selfhosted launches
- PyCon Korea CFP submission
- Modulabs / GDG DevFest speaking slots
- Twitter/X architecture-decision thread
- First blog post launch (drafting OK; publishing held)

---

## 6. Held until later cycles

| Cycle | Held |
|---|---|
| v0.3+ | MCP server registry, LangChain integration, HuggingFace Spaces, Anthropic Cookbooks contribution |
| v0.4+ | Korean tech media interviews (플래텀, 더브이씨), arXiv preprint, NeurIPS/ACL workshop, customer-named claims |
| v1.0+ | HuggingFace Spaces flagship demo, major conference keynote, second domain pack |

Full list in `docs/marketing/channels.md` §8 (cycle-aligned timeline).

---

## 7. Discipline rules to enforce (promotion-side)

1. **Cycle-aligned messaging only**. Current v0.2 tagline:
   *"Local-first, auditable Graph-RAG with role-based access"*. Do NOT use
   v1.0 tagline ("Postgres for AI agents") at v0.2 stage.
2. **No domain marketing pre-v0.4**. No mention of cafe / travel / government
   as current targets in any external copy.
3. **No customer naming** without written permission.
4. **No pricing** disclosure pre-revenue.
5. **No buzzwords** (AGI, autonomous, self-improving, sentient).
6. **No "we / our team"** framing — JAMES is 1 operator + Claude.
7. **No competitor disparagement** (LangChain, Onyx, LlamaIndex, etc.).
8. **No benchmark claims** without RAGAS / STEP 7 evidence attached.
9. **Activity log append-only** — never edit historical entries in
   `channels.md` §10.
10. **Repeated channel hits without new substance burns audience**. Do not
    post the same content to multiple channels the same day.

---

## 8. Likely first-actions for the next session

1. Operator exercised D.2 actions → append to `channels.md` §10 activity log
2. Draft Korean GeekNews / Disquiet post for operator review (matching
   v0.2 message tier per §7 above)
3. Draft awesome-list PR descriptions (operator submits the actual PRs)
4. Draft OpenSSF Best Practices Badge self-assessment answers (operator
   submits via bestpractices.dev account)
5. Draft first English + Korean blog posts (publishing held until v0.2 closes)
6. If v0.2 closing approaches: prepare Show HN draft (title, body, 5 pre-warmed responders)

---

## 9. Things NOT to do

1. Submit external awesome-list PRs directly (out of MCP scope; operator-only)
2. Apply for OpenSSF Badge directly (operator account required)
3. Set GitHub Topics directly (no MCP tool exposes this)
4. Post to GeekNews / Disquiet / Reddit / FB directly (operator accounts
   required, also Show HN/Reddit held until v0.2 closes)
5. Publish Show HN, conference, or media content before v0.2 closes
6. Add domain language anywhere (cafe / travel / government as current target)
7. Write README copy at v1.0 tier when current cycle is v0.2
8. Edit historical entries in `channels.md` §10 activity log (append-only rule)

---

## 10. State summary (30-second read)

- **What**: External promotion catalog + community templates + README polish
- **Where**: PR #155 commits 1–4 (`08e9f111`, `5ce859af`, `419e0367`, `24540729`)
- **Cycle**: v0.2 Foundation Hardening
- **Operator queue**: 9 D.2 external actions (Topics, OpenSSF Badge, awesome lists, Korean dev community)
- **Held**: Show HN, conferences, blog launches, capital channels — all until v0.2 closes
- **Forbidden**: domain marketing, buzzwords, customer naming, pricing
- **Activity log**: `channels.md` §10 (append-only)
- **License / CLA work**: see Part 2 (`session-2026-05-09-license-infrastructure.md`)

---

## 11. 한국어 핵심 요약

이 핸드오버는 **외부 홍보 준비**만 다룹니다 (라이선스 인프라는 Part 2 별도).

이 세션이 한 4개 commit:
1. `channels.md` + business-track §12 (커뮤니케이션 규율)
2. CODE_OF_CONDUCT + GitHub issue/PR 템플릿
3. README badges + 버전 + Roadmap + Stay in touch
4. README.ko 동일 갱신

다음 세션이 알아야 할 핵심:
- **D.2 외부 액션 9가지 운영자 직접 수행 필요** — GitHub Topics, OpenSSF Badge, awesome list PRs, GeekNews 등. 목록은 §4 참조
- **외부 홍보는 v0.2 메시지만** ("Local-first, auditable Graph-RAG with role-based access") 사용. v1.0 메시지 ("Postgres for AI agents") 금지
- **Show HN, 컨퍼런스, 블로그 발행은 v0.2 닫힘 + RAGAS 점수 확보 후**
- **도메인 마케팅 (음료/여행/정부) v0.4까지 금지**
- **`channels.md` §10 활동 로그 append-only** — 이전 항목 수정 금지

다음 세션 첫 작업으로 예상:
1. 운영자 D.2 수행 후 활동 로그 업데이트
2. GeekNews 게시글 초안, awesome list PR 설명 초안, OpenSSF Badge 자가-평가 초안 작성 (최종 제출은 운영자)
3. 첫 블로그 포스트 초안 작성 (발행은 v0.2 닫힘 후)

라이선스 / CLA / IP 경계 관련 작업은
`session-2026-05-09-license-infrastructure.md` (Part 2) 참조.
