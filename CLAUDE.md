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
- **Active theme**: **Direction α — hybrid cloud reasoning tier**
  (entered 2026-06-03). The α-measurement cycle (α-6/7/8) is closed and
  the **forced discovery hunt has ended** (see memory
  `feedback_alpha_cycle_discovery_loop_end`); emergent CASCADE-class
  findings are still pursued, but we no longer mine measurement cycles
  for breakthroughs.
  - **α-8 closed** = ⭐ operational only (n=3 paired collapsed n=1's
    apparent ⭐⭐); typed filter default ON, no regression. Did NOT
    move the graded-answer ceiling.
  - **Track 2c closed** (JAMES side): Phase 6 α-8 retest = poison_01
    promotion failed (typed filter doesn't generalize to catalog
    poisoning); Ali validation reply **sent 2026-06-03** (cross-stack
    comparison); next Ali action = mid-June 3-author joint-piece.
  - **Direction α landed (2026-06-03)**: design memo
    `docs/design/v0.4-direction-alpha-hybrid-cloud-tier.md`;
    abstraction-layer PoC + real-Claude e2e loop
    (`scripts/research/abstraction_*`); **§5.7.12 Cloud Egress Trust
    Zone** merged (PR #695) = rule #4 gate now OPEN for cloud code.
  - **Premise re-examination**: a reasoning-isolated local-vs-cloud
    measurement (full gold evidence + blinded judge) gave local
    gemma3:4b 9/9 = Claude 9/9 → the "local reasoning ceiling" that
    motivates the cloud tier is **unproven** (likely a retrieval +
    metric artifact). Cloud-tier value must be *proven* alongside the
    build, not assumed. See memory
    `project_direction_alpha_local_vs_cloud_quality_thread`.
  - **Cloud-tier build S0–S5 closed (2026-06-03 evening, 6 PRs)**:
    §5.7.13 abstraction module trust contract (#698) + `core/abstraction/`
    production module (#699, 4-file split, 34 tests) +
    `run_cloud_egress` orchestrator with runner-side keep_local refusal
    (#700, 16 tests) + `local_vs_cloud_paired.py` measurement harness
    (#701, paired n=3 + 6-key caveat block + 17 smoke tests) +
    `JAMES_FORCE_CLOUD` synth wire at `trace_synth_call` (#702, 4-branch
    decision tree + 9 tests, byte-identical OFF). Live wire works:
    `JAMES_ENABLE_CLAUDE_BACKEND=1 + JAMES_FORCE_CLOUD=1 +
    JAMES_BACKEND_SYNTH=claude_code_cli` → every synth call routes
    through abstraction + real Claude. (1)-(5) of the prior "Next" queue
    all closed except (4) UI picker — deferred to S5b (env-flag pattern
    sufficient until measurement gates the UX investment). See memory
    `project_direction_alpha_cloud_tier_build_state`. Cloud = Max-plan
    headless `claude -p` for research; production needs Anthropic API
    key (`feedback_direction_alpha_max_plan_research_cloud`).
  - **Direction α 2026-06-04 cycle closure — premise 측정상 미입증.**
    α-8 cloud tier extension (Stage 1-5 closed, 4 PRs #705/#706/#707
    + cell measurements) 결과: 3 측정 모두 cloud reasoning ceiling
    신호 없음 — (1) v2 reasoning-isolated 9/9=9/9 차이 0, (2) Stage 4
    Run 1 fair evidence-grounded Δ -0.037 (magnitude tiny), (3)
    Stage 4b cloud raw invalid (Claude 학습-지식 leak, multihop=2023
    뉴스). 결과 보고서: `reports/research-runs/alpha-8-cloud-tier-
    extension-20260604.md`. **결정**: cloud-tier 인프라 (S0-S5c +
    Stage 1-2, 10 PR) **보존** (라이브 wire 검증됨, 미래 다른 cloud
    LLM / leak-controlled fixture / 한국어 fixture에서 재활용),
    **S6/S7 무기한 보류** (cloud 가치 자체 미입증), **다음 cycle =
    mother platform 강화 / v0.5 도메인 pilot redirection**. 이번
    cycle 5건 사용자 catch가 박은 measurement-side 룰 (`feedback_
    methodological_chain_before_plan` + `feedback_fixture_fitness_
    before_verdict` + `feedback_evidence_grounded_validity_check`)은
    다음 cycle 진입 시 의무 reading.
  Domain pilot (v0.5) still gated. α-7 closed REJECT (PR #680, 10th
  wrong-fix-averted); α-6 closed 2026-06-01.
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
| **🟢 NEXT SESSION ENTRY (read this first)** | **`docs/handovers/v0.4-cycle-beta-entry-2026-06-06.md`** (BIG: cycle 마감 + cycle β 진입. 6 원칙 + 4-layer matrix + persona = 단축 손해 진짜 source 확정. 첫 작업 = engine_memory persona 옵션화 Phase A-E. 의무 reading 4-doc 묶음 명시.) |
| Prev entry (cycle 마감 + 6 원칙) | `docs/handovers/v0.4-mother-platform-6-principles-cycle-2026-06-05.md` |
| Prev-prev entry (cap[:1000] discovery) | `docs/handovers/v0.4-multihop-synth-context-fix-2026-06-05.md` |
| Prev entry (Direction α 측정 closure) | `reports/research-runs/alpha-8-cloud-tier-extension-20260604.md` (premise 미입증, S6/S7 보류) + 5 measurement-side rules |
| Direction α design memo (§4.1 local-vs-cloud ①) | `docs/design/v0.4-direction-alpha-hybrid-cloud-tier.md` |
| Direction α local-vs-cloud premise + sequencing | memory `project_direction_alpha_local_vs_cloud_quality_thread` |
| Cloud egress trust contract (rule #4 gate) | `docs/ARCHITECTURE.md` §5.7.12 |
| **Abstraction module trust contract (§5.7.13) + `core/abstraction/` API** | `docs/ARCHITECTURE.md` §5.7.13 + `core/abstraction/__init__.py` |
| Operator: live cloud routing | `JAMES_ENABLE_CLAUDE_BACKEND=1 + JAMES_FORCE_CLOUD=1 + JAMES_BACKEND_SYNTH=claude_code_cli` |
| Operator: S4 measurement run | `python scripts/research/local_vs_cloud_paired.py --n-per-type 3 --n-runs 3` |
| Previous entry (2026-06-02 evening — sealed) | `docs/handovers/v0.4-next-session-entry-2026-06-02-evening.md` |
| Previous entry (2026-06-02 post-tracks — now sealed) | `docs/handovers/v0.4-next-session-entry-2026-06-02-post-tracks.md` |
| Previous session entry (α-7 launch — sealed) | `docs/handovers/v0.4-next-session-entry-2026-06-02-alpha7.md` |
| Previous-previous (Phase 3a launch — sealed) | `docs/handovers/v0.4-next-session-entry-2026-06-01-PM.md` |
| Track 2c integration design memo | `docs/design/v0.4-track-2c-arabic-adversarial-integration.md` |
| Bidi normalization audit | `reports/research-runs/bidi-normalization-audit-20260602.md` |
| α-7 closure analysis (mid-fill) | `reports/research-runs/alpha-7-closure-analysis-20260602.md` |
| α-7 baseline run log | `reports/research-runs/_alpha7-baseline-capture.log` |
| α-7 5-tier remeasurement log | `reports/research-runs/_alpha7-5tier-remeasurement.log` |
| Ali Track 2c originals (preserved) | `eval/adversarial/ar_ecommerce-{v1.1-pending.yaml, REPORT-provia.md, ...}` |
| Adversarial runner | `scripts/adversarial_sweep.py` |
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

**현재 위치 (2026-06-04 저녁)**: **Direction α cycle closure — premise 측정상 미입증**. α-8 cloud tier extension 완료 (Stage 1-5, 4 PRs #705/#706/#707 + measurements). 3 측정 모두 cloud reasoning ceiling 신호 없음: (1) v2 reasoning-isolated 9/9=9/9 차이 0, (2) Stage 4 Run 1 fair evidence-grounded Δ -0.037 graded (cloud + JAMES 0.290 vs local + JAMES 0.327, magnitude tiny + n=1), (3) Stage 4b cloud raw **invalid** — Claude 학습-지식 leak (multihop=2023 뉴스가 학습 분포에 포함). cloud-tier 인프라 (S0-S5c 8 PR + Stage 1-2 2 PR, 총 10 PR) **보존** (라이브 wire 검증됨, 미래 재활용). **S6/S7 무기한 보류** (cloud 가치 자체 미입증). **다음 cycle = mother platform 강화 / v0.5 도메인 pilot redirection**. 이번 cycle **5 사용자 catch** (인수인계 fact 무시 패턴) → measurement-side 룰 3개 박힘 (methodological chain / fixture fitness / evidence-grounded validity). α-measurement cycle + **forced discovery hunt END** 룰 재확인. Track 2c JAMES측 closed, Ali 검증 답신 발송됨 (joint piece = mid-June 3-author). v0.5 도메인 (기업 내부지식, 수평) 여전히 gated. 자세한 내용은 `reports/research-runs/alpha-8-cloud-tier-extension-20260604.md` + memory `project_direction_alpha_cloud_tier_build_state` (closure 항목).
