# JAMES — Session Briefing for Claude Code

> Read this first. This file orients any new Claude Code session to
> the project's current direction in under 60 seconds.

## What JAMES is

A local-first, auditable knowledge reasoning system.
See `docs/ARCHITECTURE.md` for full design principles and non-goals.

## Where we are right now

- **Current version**: **v0.4.1 closed** (2026-05-28, DOI
  `10.5281/zenodo.20426719`) — T6 Causality Chain + T2.D ingestion +
  QVT α track. v0.2.0 (Foundation Hardening) and v0.3.0
  (Platform Skeleton) both fully closed; v0.4.0 (Layer 4 Lifecycle:
  T1+T7+T2 first bundle) shipped 2026-05-27.
- **Active theme**: **α-6 measurement cycle in flight (Phase 3a)** —
  MultiHop-RAG external benchmark, 5-axis Pareto oracle, scale-ladder
  measurement of JAMES sector contributions across gemma3 1b/4b/12b/27b
  + gemma4 e4b. Phase 1 + Phase 2 closed (2026-06-01 AM); Phase 3a
  scale ladder running. Closure → α-7 (graph top-K fix) → α-8 (ontology
  typed-filter A/B). Domain pilot (v0.5) still gated.
- **Strategic frame**: We are still building a **mother platform**;
  v1.0 vertical domain branching remains the only authorised
  specialisation point. The 2026-06-01 strategic discussion narrowed
  the v0.5 first-domain candidate to **enterprise internal knowledge
  ontology** (horizontal, audit/ownership/correction moat) — see
  the 2026-06-01 strategy handover; the framing applies to v0.5 domain
  *selection criteria*, not to v0.4 cycle scope.
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
   `core/reasoning` must paste bench numbers + a Quality Delta
   Card** in the description (Axis 2 of v0.2 ROADMAP, extended by
   QVT α-4 2026-05-28, α-5 cycle 2026-05-31). PRs without
   numbers will not land.
   - **Bench numbers**: STEP 7 result deltas (`scripts/bench.py
     --suite=step7 --mode=retrieval`) — latency, graph_paths,
     answer_len.
   - **Quality Delta Card**: 3-axis (or, after α-5 lands, 5-axis)
     paired comparison against `eval/qvt/baseline_<sha>.json`
     (Path Recall / Graded Answer / Abstention F1 / + Token Cost /
     Latency Cost). Template lives in
     `.github/PULL_REQUEST_TEMPLATE.md`. The α-5 Pareto verdict
     rule (`scripts/qvt_ablation_matrix.py::_classify_five_axis_delta`)
     applies once the 5-axis baseline is the canonical reference.
   - **Exemption labels** (skip the Quality Delta Card with one line
     `Quality delta: exempt (label: <name>)`): `external-contributor`
     (Robin / Ali / other collaborator PR), `joint-collab-prep`
     (mid-June joint piece / shared deliverable), `docs` / `chore` /
     `ci` (not touching `core/`), `code` (circular — the PR is the
     oracle / baseline itself), **`fix` (oracle/fixture/bench
     correction PR — the very thing being corrected is what would be
     measured against)**. Rationale: the gate is for measuring
     JAMES-internal marginal contribution, not a collaboration
     friction tool, and not a measurement-side hygiene PR. See
     `docs/design/v0.4-qvt-alpha-non-saturating-oracle.md` §4 for the
     full exemption rule.
   - **`fix` label discipline** (α-5 cycle lesson): when the PR
     corrects a measurement-side artifact in oracle / fixture / bench
     (e.g. bucket-(d) findings per `feedback_oracle_phrase_artifacts`),
     state the exemption explicitly in the description. The α-5 cycle
     saw 5 fix PRs (#618 #619 #622 #623 #625) where the Quality Delta
     Card would either circular-reference the broken oracle or
     measure noise. Explicit `Quality delta: exempt (label: fix)`
     keeps the review readable without paste-noise.
   - **Layer-intent matrix** (α-6 cycle extension 2026-05-31): when a
     PR touches one of the routing / cognitive layers
     (`AUTO_ROUTER` / `ADAPTIVE_BUDGET` / `SCOPE_ROUTING` /
     `ENTITY_ANCHOR` / `QUERY_REWRITE` / `Citation` / `Graph` /
     `Abstention` / `Cognitive Stages`), the Quality Delta Card MUST
     be scored against the layer's **design-intent axes** (per
     `docs/design/v0.4-alpha-6-sector-llm-ablation-matrix.md` §5.6 +
     memory `mechanism_layer_intent_axis_alignment`). Uniform 5-axis
     judgment is rejected for these PRs because it mis-classifies
     cost-optimization layers as quality regressions (α-5 post-closure
     self-audit lesson, sub-categories 5/6 of bucket-(a)). The PR
     description must include a short *"intent axes vs regression
     axes"* split with the appropriate per-layer matrix entry.
     **Layer measurement prerequisites must also be confirmed** —
     e.g., AUTO_ROUTER PRs require multi-tier backend registration
     evidence (otherwise the layer is no-op and the PR's number is
     "not in evidence," not "no effect").

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
| **🟢 NEXT SESSION ENTRY (read this first)** | **`docs/handovers/v0.4-next-session-entry-2026-06-01-PM.md`** |
| Strategic vision + 6-dimension readiness | `docs/PLATFORM_READINESS.md` |
| Architecture & non-goals | `docs/ARCHITECTURE.md` |
| 6-axis v0.2 plan + future v0.3/v0.4/v1.0 | `ROADMAP.md` |
| α-6 cycle PR index (75+ PRs) | `reports/research-runs/alpha-6-cycle-pr-index.md` |
| α-5 cycle PR index | `reports/research-runs/alpha-5-cycle-pr-index.md` |
| α-6 Phase 1 analysis (M_M) | `reports/research-runs/alpha-6-phase-1-analysis-20260601.md` |
| α-6 Phase 2 analysis (M_S; tier-gated REVERSED) | `reports/research-runs/alpha-6-phase-2-analysis-20260601.md` |
| α-6 Phase 3a 1b analysis (⚠️ framing pollution flagged) | `reports/research-runs/alpha-6-phase-3a-gemma3-1b-analysis-20260601.md` |
| α-6 Phase 3a 12b analysis (honest framing) | `reports/research-runs/alpha-6-phase-3a-gemma3-12b-analysis-20260601.md` |
| α-6 Phase 3a recovery curve (live) | `reports/research-runs/alpha-6-phase-3a-recovery-curve-20260601.md` |
| Active backlog reconciliation | `docs/handovers/v0.4.x-backlog-reconciliation-2026-05-30.md` |
| v0.4.1 closure (audit trail) | `docs/handovers/v0.4.1-t6-causality-chain-entry.md` |
| License long-term plan + trigger monitoring | `docs/LICENSE_PLAN.md` |
| **Change Request primitive (v0.2.x cycle)** | `docs/handovers/v0.2.x-cr-track.md` + `docs/ARCHITECTURE.md §5.6` |
| 4-step rule (+ arithmetic step) | `memory/feedback_oracle_phrase_artifacts.md` |
| Layer-intent matrix mechanism | `memory/mechanism_layer_intent_axis_alignment.md` |
| **Honest framing rule** (apply to every closure / publishable claim) | `memory/feedback_finding_size_honest_framing.md` |
| Matrix runner tier override trap | `memory/feedback_matrix_runner_tier_model_override.md` |
| Mother framing position guard | `memory/feedback_jameses_positioning_replayable_rag.md` §"정정 2026-05-31" |
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

- Branch naming: current convention is `feat/v0.4-<topic>` / `fix/v0.4-<topic>` /
  `docs/v0.4-<topic>` / `chore/v0.4-<topic>`. (Use `feat/v0.5-<topic>` only
  after v0.4.x cycle closure — currently still in α-6/α-7/α-8 measurement
  phase. Older v0.2 / v0.3 branch prefixes are retained in history but not
  used for new work.)
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

자메스는 **v1.0까지 "범용 모체"로만** 강화합니다. 도메인 분화(법률·식품·유통·여행 등)는 v1.0 이후에만 시작합니다. 이 세션에서 도메인 코드를 추가하지 마세요.

**현재 위치**: v0.4.1 완료 (DOI `10.5281/zenodo.20426719`) → α-6 측정 사이클 Phase 3a 진행 중 (gemma3 1b/12b/27b scale ladder). 다음 사이클 순서: α-7 (graph top-K fix) → α-8 (온톨로지 typed-filter A/B). v0.5 첫 도메인 후보 = 기업 내부지식 온톨로지 (수평 — 도메인 vertical 아님). 자세한 내용은 `docs/PLATFORM_READINESS.md` + `ROADMAP.md` + `docs/handovers/v0.4.x-backlog-reconciliation-2026-05-30.md`.
