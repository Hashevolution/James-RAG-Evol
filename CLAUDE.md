# JAMES — Session Briefing for Claude Code

> Read this first. This file orients any new Claude Code session to
> the project's current direction in under 60 seconds.

## What JAMES is

A local-first, auditable knowledge reasoning system.
See `docs/ARCHITECTURE.md` for full design principles and non-goals.

## Where we are right now

- **Current version**: v0.2.0 closed → **v0.3.0 진입 (2026-05-13)**.
  6 axes (Foundation Hardening) 모두 통과 — Axis 6 (real-data validation)
  의 두 번째 사용자 게이트도 모집 완료. v0.2 → v0.3 gate clear.
- **Active theme**: **Platform Skeleton** (`core/plugins/` 확정 + 도그푸드
  + CLA + Knowledge Cascade). 도메인 분화는 여전히 v1.0 이후.
- **Strategic frame**: We are not building a single product.
  We are building a **mother platform** from which domain packs
  (legal, food, retail, travel, etc.) will branch off **only at v1.0**.
  See `docs/PLATFORM_READINESS.md` for the 6-dimension readiness
  framework and the v0.2 → v0.3 → v0.4 → v1.0 gate definitions.

## Critical rules for this session

1. **Do not add new domain features** (legal-specific, food-specific,
   retail-specific, etc.) until v1.0. Mother-hardening mode. Any
   domain-coupled work pollutes the platform contract and will be
   reverted in review.
   See `docs/handovers/v0.2.1-business-track.md` §3 for the explicit
   "no parallel domains" rule and what it forbids.

2. **Every PR touching `core/retrieval`, `core/graph`, or
   `core/reasoning` must paste bench numbers** in the description
   (Axis 2 of v0.2 ROADMAP). PRs without numbers will not land.

3. **Self-evolution is opt-in only**. Any change that allows
   auto-deploy without an `approver_username` in the audit log
   is a bug, not a feature.

4. **Architecture changes** (new module, new trust zone, removal
   of a non-goal) require a PR to `docs/ARCHITECTURE.md` with the
   `architecture` label.

5. **Module size gate**: no file in `core/` exceeds 20 KB. If your
   change pushes a file over, split first.

## Where to look next

| Purpose | File |
|---|---|
| Strategic vision + 6-dimension readiness | `docs/PLATFORM_READINESS.md` |
| Architecture & non-goals | `docs/ARCHITECTURE.md` |
| 6-axis v0.2 plan + future v0.3/v0.4/v1.0 | `ROADMAP.md` |
| Active session brief (start here for tasks) | `docs/handovers/v0.3.0-platform-track.md` |
| v0.2 closure (audit trail) | `docs/handovers/v0.2.0-platform-track.md` |
| Business track (current cycle) | `docs/handovers/v0.2.1-business-track.md` |
| v0.3 license / CLA / plugin API session | `docs/handovers/session-2026-05-09-license-infrastructure.md` |
| License long-term plan + trigger monitoring | `docs/LICENSE_PLAN.md` |
| **Change Request primitive (v0.2.x cycle)** | `docs/handovers/v0.2.x-cr-track.md` + `docs/ARCHITECTURE.md §5.6` |
| Open issues by priority | `gh issue list --label priority:high` |
| STEP 7 regression baseline | `eval/regression/step7_queries.json` (or `scripts/step7_query_test.py`) |

## What this session should NOT do

- Fork or specialize the project for a vertical (legal, food, retail, travel, finance)
- Add a feature without a corresponding regression test in the eval harness
- Bypass `PolicyEngine` for a "quick fix"
- Disable the human approval gate on self-evolution
- Enable auto-merge on PRs touching trust boundaries (auth, policy, sandbox)
- Promise plugin API stability before v0.3 lands

## Operational conventions (PR / commit / branch)

- Branch naming: `fix/v0.2-<topic>`, `chore/v0.2-<topic>`, `docs/v0.2-<topic>`,
  `feat/v0.3-<topic>` (only after v0.2 closes)
- Commit messages: conventional commits (`fix:`, `feat:`, `refactor:`,
  `chore:`, `docs:`, `test:`)
- PR body: include `## Summary`, `## Verification`, `## Out of scope`
  sections; bench numbers if applicable
- Issue closing: use `Closes #N` in the PR body, **not** in the commit
  message (GitHub gotcha — commit-message close from squash-merge can
  miss multi-issue cases)
- Always work on a non-main branch; PR into main; self-merge after
  bench verification

## 한국어 요약

자메스는 **v1.0까지 "범용 모체"로만** 강화합니다. 도메인 분화(법률·식품·유통·여행 등)는 v1.0 이후에만 시작합니다. 이 세션에서 도메인 코드를 추가하지 마세요. v0.2의 6축 Foundation Hardening이 현재 우선순위입니다. 자세한 내용은 `docs/PLATFORM_READINESS.md` 참조.
