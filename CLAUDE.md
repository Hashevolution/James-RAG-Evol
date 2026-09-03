# SEKOS / JAMES — Session Briefing for Claude Code

> Read this first. This file orients any new Claude Code session to
> the project's current direction in under 60 seconds.

## What JAMES is

A local-first, auditable knowledge reasoning system.
See `docs/ARCHITECTURE.md` for full design principles and non-goals.

## Where we are right now

> **단일 진실원 (single source of truth)**:
> **`docs/handovers/v0.6.2-restart-roadmap-2026-09-03.md`**.
> 아래는 그 요약입니다. 충돌하면 로드맵 문서가 우선입니다.

- **최신 공식 릴리스**: **v0.4.4** — DOI `10.5281/zenodo.20652679`.
  v0.5 는 `main` 에서 **closed (2026-06-13)** 이지만 DOI 미발행.
- **사이클 상태**: **v0.5 closed / v0.6 정식 미진입.** v0.5 → v0.6 게이트
  = **Dim F** (외부 고객 6 개월 이상 파일럿) **미통과**. 2-fork 계약이
  유효 — **Fork A** LOI 체결 → Track D 버티컬 팩 / **Fork B** 6 개월
  무LOI → 전략 재평가. 판정 시점 ≈ **2026-12-13**. 둘 다 **operator 결정**이며,
  결정 전에도 아래 Phase 1–5 는 전부 진행 가능합니다.
- **실제로 진행된 것**: v0.6 / v0.6.1 **제품 하드닝 스트림** — PR
  **#886–#1078** (약 190 PR, 2026-06-13 → 2026-06-26, **릴리스 태그 없음**).
  주요 산출물: 운영 하드닝 P1–P4 (신뢰 프록시 / HTTPS 가이드 / 테넌트
  미들웨어 / 온보딩·롤백·추론 시각화·용어집) · **템플릿(양식) 엔진** ·
  **에이전트 트랙** (`core/agent_tools` + tool-use 루프 + `run_shell`
  기본 OFF) · LLM 라우팅 통합 + 모드별 측정 라우팅 · 채팅 UX 전면 개편 ·
  UI 8→5 페이지 통합 + **비주얼 회귀 하네스** · CSP 인라인 스타일 이관 ·
  이미지-OCR/비전 체인 수리 · heartbeat 스트리밍 · detailed 답변 스타일.
- **🔴 lifecycle live-consistency arc (#1018–#1027, #1033–#1034)**:
  프로브(#1020)가 **라이브 그래프 탐색이 lifecycle status 를 무시**함을
  측정으로 증명 (캐스케이드가 라이브 계층에서 사실상 무효였음) →
  `relation_is_live()` 게이트를 탐색 / 그래프 스코어 / T1 유효 윈도우 /
  3D 스냅샷 전 표면에 적용, 시간여행 경로 격리 검증, 백로그 재측정으로
  회귀 없음 확인 (#1028–#1032). 이것이 `core/graph` traversal **0-라인
  streak 의 유일한, 측정 근거로 승인된 예외**입니다. 이전 핸드오버의
  "0 라인 streak 유지" 문장을 그대로 복사하지 마세요.
- **🟠 `main` CI 는 아직 빨간불 — 단 규모가 크게 줄었습니다** (2026-09-03
  재측정): `.github/workflows/test.yml` (pytest) 은 최신 실행(#1080,
  08-28)까지 `failure` 이지만, **#1080 이 원인별로 정리해 66 → 6 failed**
  가 됐습니다. 로컬 재현 = 3,742 tests 중 **9 failures** (errors 는 의존성
  미설치 환경 탓). CI 가 실제로 도는 실패 모듈은 **4개**
  (`test_v06_agent_paths` / `test_eval_pack_script` (ruff 셸아웃 — 환경
  의심) / `test_measurement_critical_surfaces` / `test_mobile_responsive`).
  → **재개 첫 작업 = 로드맵 Phase 2 (CI 그린 복구). 그 전에 새 기능 금지.**
  ⚠️ 이전 핸드오버의 "60 failures / rule #5 2건 위반"은 **낡은 수치**입니다.
- **유지보수 4 PR** (#1077 #1078 08-19 / **#1079** 08-26 / **#1080** 08-28):
  v0.3.3 DOI 계보 정정, ruff F-class 해소, Ali 엔지니어링 4건 ①②③ 발송 +
  **uuid7 production 결함 수리** (`start_trace()` 가 Python 3.14 전용
  `uuid.uuid7()` 호출 → 지원 인터프리터 전부에서 `/query/` 엣지 다운),
  아랍어 파이프라인 능력 감사, 그리고 **CI 원인별 정리**
  (`_IncludedRouter` 래퍼가 137 라우트를 숨긴 문제 + rule #5 2건).
- **유휴 구간**: 마지막 **기능** 세션 **2026-06-26**. 이후 착륙한 것은
  전부 문서·인용·CI 유지보수입니다.
- **전략 프레임**: 여전히 **mother platform**. v1.0 이전 버티컬 분화 금지
  (rule #1). v0.5 후보 도메인 = enterprise internal knowledge ontology
  (horizontal) — 이는 *선택 기준*이지 구현 승인이 아닙니다.
- **브랜드 규약**: **SEKOS** = 제품 브랜드 (UI / 대외 / 마케팅),
  **JAMES** = 엔진 코드명 (소스, `JAMES_*` env, `--sut james`, RAB/LRB,
  Zenodo DOI). PR #934 에서 확정 — 재현성 때문에 코드/논문 쪽은 JAMES 유지.


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
   ✅ **게이트 통과 중** (2026-09-03): #1080 이 `core/response_style.py`
   를 `core/response_style_presets.py` 로 분할했습니다.
   `core/reasoning/engine.py` (21,464 B) 만 **분할 계획과 함께
   grandfather 등록** — 분할하려면 rule #2 상 STEP 7 벤치가 필요하고
   그건 서버 + Ollama 가 있는 operator 머신에서만 가능합니다.
   grandfather 를 늘리지 말고, 새로 넘기는 파일은 먼저 분할하세요.

6. **상태는 한 곳에만 쓴다 (state single-source)** — NEW 2026-09-03.
   사이클 상태의 원본은 `docs/handovers/` 의 **최신 문서 하나**이고,
   루트 문서 (`CLAUDE.md` / `SUMMARY.md` / `README*.md` / `ROADMAP.md` /
   `CHANGELOG.md` / `HANDOVER.md`) 는 **거기를 가리키기만** 합니다.
   상태 문장을 복제하면 다음 유휴 구간에 다시 갈라집니다 — 2026-06~08
   의 문서 최신성 편차가 정확히 그 실패였습니다.
   가드: `tests/test_v06_claude_md_entry_pointer.py` 가 "Where to look
   next" 첫 행이 **가장 최신 핸드오버**를 가리키는지 검사합니다.

## Where to look next

| Purpose | File |
|---|---|
| **🟢🟢🟢 NEXT SESSION ENTRY (이것부터 읽으세요 — 2026-09-03 재개 로드맵)** | **`docs/handovers/v0.6.2-restart-roadmap-2026-09-03.md`** (재개용 **단일 진실원**. §1 현재 상태 사실 확인 (main HEAD `df55e21` / 유휴 구간 / **CI 상태 2026-09-03 재측정 — #1080 이 66 → 6 failed 로 축소** / rule #5 해소 + 1건 grandfather / 문서 최신성 편차 표) + §2 **Phase 1–7 재개 로드맵** (1 문서 동기화 ✅ → 2 CI 그린 복구 → 3 유휴 부채 청산 → 4 v0.6.1 정식 마감 → 5 측정 백로그 → 6 Fork A/B 전략 결정 (operator) → 7 v0.6 진입) + §3 #886–#1078 실제 진행 요약 + §5 재개 첫 세션 30 분 체크리스트 + §6 하지 말 것. **Phase 2 전에는 새 기능 PR 금지.**) |
| **🟢🟢 직전 기능 세션 close (2026-06-26, PR #1062–#1075)** | `docs/handovers/v0.6.1-session-close-2026-06-26.md` (CSP `style-src` HTML 이관 596 attrs + 모바일 업로드 UX + **이미지 인제스트 4 단 병목 수리** (비전 모델 라우팅 / 이진화 제거 / EasyOCR fallback / qwen2.5vl:7b / num_ctx 8192) + `/query/`·`/upload/` heartbeat 스트리밍 + detailed 답변 스타일. §4 operator open 2 건 (모바일 긴 질의 드롭 / detailed dogfood), §5 deferred, §3 서버 background 실행 금지 교훈.) |
| **🟢🟢 v0.6.1 세션 close (2026-06-23, PR #992–#1037)** | `docs/handovers/v0.6.1-session-close-2026-06-23.md` (UI 8→5 페이지 통합 / de-emoji / 인트로 프론트도어 / 그래프 허브 / trace 링크 루프 / entity-edit cascade Phase 1-3 / **lifecycle live-consistency arc** / 비주얼 회귀 하네스 / 백로그 재측정.) |
| **🟢🟢 lifecycle live-consistency arc (측정 근거)** | `docs/handovers/v0.6.1-measurement-fix-loop-2026-06-22.md` + `reports/research-runs/lifecycle-live-consistency-arc-20260622.md` (프로브 #1020 = 라이브 탐색이 lifecycle status 를 무시 → `relation_is_live()` 게이트. `core/graph` traversal streak 의 **유일한 승인된 예외** — kill-switch `JAMES_DISABLE_STATUS_FILTER`.) |
| **🟢🟢 v0.6 템플릿(양식) 엔진 close (2026-06-13)** | `docs/handovers/v0.6-template-engine-close-2026-06-13.md` (도메인 무관 양식 포맷팅 엔진 PR #909 + `core/templating/` + `routes/templating.py` + 워크스페이스 탭 / 챗 모달. rule #1 준수 = JAMES 는 템플릿을 하나도 동봉하지 않음.) |
| **🟢🟢 v0.6 2-fork 진입 계약 (2026-06-13)** | **`docs/handovers/v0.6-entry-skeleton-2026-06-13.md`** (v0.5 closed + Dim F gate 미통과 = "v0.5 closed, v0.6 not yet entered" state. v0.5 close §5 작업 큐 실질 소진: 20 LANDED + 4 LOI-blocked (Track D / G8.d / F.2 CR.e) + 6 operator-pending (Track E) + 2 prerequisite-gated. v0.5 마감 후 23 PR 추가 (#863-#885) — F.1 Time-Travel Dashboard quartet 완성 (TT.a-d) + G1/G2 SaaS-readiness trio + SDK trio + Track C CSP nonce + graph-RAG Step 1 결과 + Step 2 scaffold. 2-fork v0.6 entry contract: Fork A LOI signed → Track D + G8.d 진입 / Fork B 6 개월 내 no-LOI → reassess. 둘 다 operator 결정. 다음 세션 mechanical entry checklist (§7): Fork A → v0.6-entry-<date>.md + Track D / Fork B → v0.6-reassess-<date>.md + 새 방향 / 미해결 → 이 스켈레톤 + NEW solo-doable items (§5). Rule #1 4-layer 보호 contract 그대로. core/retrieval+graph traversal+reasoning 0 라인 변경 streak 유지.) |
| **🔗 3-author 수렴 기록 (발행 완료 2026-08-19)** | **`reports/promo-assets/m9-joint-deposit-record.md`** — DOI `10.5281/zenodo.22030935` (report, CC-BY-4.0, Afana/Converse/Seo). JAMES 다리 = v0.3.1 7-tier closure (PR #461/#463, DOI `10.5281/zenodo.20363998`). #440 = 3단계 선행, #448 = Converse 축. 우리 정밀 수정 2건 반영. Ali 엔지니어링 4건 = ①②③ **발송 완료 2026-08-26** (`docs/collab/ali-engineering-findings/COMBINED-findings-1-2-3.md`), ④ 는 Track 2c 재측정 대기 (`scripts/research/track2c_remeasure.py --yes`, 운영자 머신). |
| **🟢🟢 직전 v0.5 close handover** | **`docs/handovers/v0.5-close-2026-06-12.md`** (v0.5 cycle close handover — 21 PR (#841-#861) 마감 정리 + 2026-06-12 PM 전략 review 반영 (Track B SDK.a-c + Track F mother-level UI 정식 편입). B.5 series 4 + B.1 audit + 4 gap 구현 5 + B.2/B.3 design memo 2 + UI improvement 6 + 평가 외부 노출 1 + server-side hardening 3. 측정 0, vertical 토큰 0, `core/retrieval`+`core/graph` traversal+`core/reasoning` 0 라인 변경. B.1 8 gap 결과: 4 LANDED + 2 primitive LANDED (G1.a/G2.a) + 2 contract-locked + 1 v1.0-deferred (G6). Solo-doable mother-platform 스코프 **달성 완료**. **v0.5 → v0.6 gate = Dim F**, **아직 미통과** (LOI 또는 reassess 결정 필요). v0.6 entry 시 작업 큐: Track A (G1.b/c+G2.b/c) / Track B (G8.a-c mount + **SDK.a-c CLI/PLUGIN_AUTHORING/PyPI**) / Track C (CSP nonce) / Track D (Dim F, **LOI 필수**) / Track E (operator-pending) / **Track F (NEW)** (F.1 Time-Travel Dashboard TT.a-d + F.2 Change Review Workspace CR.a-d, mother-level UI). Rule #1 4-layer 보호 (code capability gate + doc Out-of-scope + naming domain-agnostic + LOI-gated trigger tagging). Track A/B/C/F 는 solo / LOI 무관. **참고: 위의 entry skeleton 이 close 이후 #863-#885 진행 + 작업 큐 status sweep + 2-fork entry contract 를 종합**.) |
| **🟢🟢 직전 v0.5 entry doc** | `docs/handovers/v0.5-entry-2026-06-12.md` (v0.4.4 closed → v0.5 entry 선언. Stream A/B/C/D scope. 3 new rules. 위의 close doc 가 cycle 결과를 종합) |
| **🟢🟢 직전 entry (2026-06-12 PM, 9 PR v0.4.4 closure)** | `docs/handovers/v0.4-next-session-entry-2026-06-12-pm.md` (사용자 직접 명령 cycle: D-alce + D-2wiki research-tier infra (cycle γ 4/4 promise closure) + S3 publication-scale generator + 4-point scale ladder measurement (R@1 V<N<J PRESERVED S2→S3 1000, 12.5×) + **자기 catch self-correction** (PR #824 의 ±0.05 magnitude claim → broken-category artifact → PR #825 retract → ⭐⭐⭐ pattern + ⭐⭐ magnitude honest framing) + preprint §4.6+§5+§6.1+§7.4 통합 + v0.2.3b cross-model runner ready (operator action). 솔로 가능 모두 마감.) |
| **🟢🟢 이전 entry (2026-06-12 6h autonomous loop, 33 PRs)** | `docs/handovers/v0.4-autonomous-loop-FINAL-2026-06-12.md` (~6h autonomous loop: ⭐⭐⭐ LRB v0.2.1 cross-model 4/4 model V<N<J + JAMES@claude R@1=0.975 → publication tier; v0.2.4 HR axis ⭐⭐ partial cross-NLI; Track C MuSiQue improvement loop 5-variant FINAL — best lever k=20 = **general-model lift, NOT JAMES specific** → ⭐ honest negative SATURATED; v0.5 pilot path 4-phase 완성; arXiv preprint Results+Discussion+11-item checklist 8/11 solo done.) |
| **🟢🟢 이전 entry (2026-06-10 R1 RAB launch, 16 PRs)** | `docs/handovers/v0.4-next-session-entry-2026-06-10-r1-rab.md` (한 세션 16 PR: P0 규율+보안 → **cycle γ multi-hop arc 완전 종결** (7 probe, 6 honest null, 2 자기정정 — 벽 = unsupervised supporting selection; retrieval 충분 0.76; graph build **O(N²)** finding) → **R1 모트 벤치 RAB R1.0–R1.3 완주**.) |
| **🟢🟢 이전 entry (Phase E-min cross-model)** | `docs/handovers/v0.4-cycle-gamma-phase-e-cross-model-results-2026-06-09.md` (Phase E-min **cross-model 완료** = mxtral+gemma4+llama. **Split 결과**: rerank + cognitive_stages 끄면 RGB 양 axis 3/3 net+ (cross-model 확정 = 트레이드오프의 **LOSS 절반**). typed_filter 2/3 (llama noise reversal −0.080) → adversarial track 분리. **★핵심**: RGB noise+negrej = abstention 가족 = LOSS 절반만, 제거(가설1) vs 트레이드오프(가설2) 구분 못 함. **default-off PR 아직 unlicensed.** 다음 세션 자연 entry = **MuSiQue paired ablation (Phase C.2 = GAIN 절반)** → 가설 2 결판. 사용자 선택 우선순위 = 가설 2 입증 시 제거 아닌 **유지 + 조화 설계 (query-type routing)**. prep = MuSiQue download + workspace 인제스트 (RGB corpus-build template) + paired ablation. 인프라 Phase A 빌드됨. 동반 reading: 6th catch (단일-axis-family → 제거 금지) + 9th catch + self-eval trap.) |
| **🟢🟢 Phase E-min mxtral handover (이전, single-model)** | `docs/handovers/v0.4-cycle-gamma-phase-e-min-mxtral-results-2026-06-09.md` (mxtral 3 component 양 axis net+, 9th catch 직접 validation. cross-model 에서 typed_filter split 됨.) |
| **🟢🟢 9th catch rule (framing equilibrium)** | **`memory/feedback_james_identity_measurement_driven.md`** (cycle β code = snapshot, JAMES 정체성 = measurement-driven discovery) |
| **🟢🟢 D2 V2 negative evidence (8번째 catch)** | **`memory/feedback_d2_v2_softener_bilingual_regression.md`** [★9th 정정] |
| **🟢🟢 Path D positioning (7번째 catch)** | **`memory/feedback_path_d_james_not_specialty_verifier.md`** [★9th 정정 — measurement evidence conditional 화] |
| **🟢🟢 Phase D handover (이전)** | **`docs/handovers/v0.4-cycle-gamma-phase-d-results-2026-06-08.md`** (mxtral n=25 7 knobs 완료 + 6번째 catch. Valid: softener -0.054 / retrieval -0.173 / graph/verify zero-op. Speculative: rerank/typed_filter/cog_stages +0.050 NOT defect.) |
| **🟢🟢 Prior-art positioning (이전)** | **`docs/research/cycle-gamma-prior-art-positioning.md`** (★corrected 2026-06-08★) (Prior art search 결과 = JAMES "true signal" mechanism **literature 에 이미 존재**. Schapire 1990 boosting / AbstentionBench 2025 (20 dataset 35k query) / RAG "cheat-sheet effect" / HALT-RAG 2025 F1 0.9786 / KD capacity gap 모두 published. ⭐⭐⭐ universal-law REJECT. JAMES contribution = **empirical reproducibility + per-query overlap method** (modest). **§5 정정 (사용자 catch)**: cycle γ = **JAMES-internal evaluation arc, NOT joint piece content**. 새 룰 `feedback_eval_cycle_vs_collab_arc_separation` 박힘 — collab arc 는 4주+ 사전합의된 scope/contributors/evidence/headline 존재, internal cycle finding 자동 연결 금지. Joint piece track 는 별도 (handover `v0.4.x-session-2026-05-29-collaboration-checkpoint.md` + M9 prep).) |
| **🟢 Phase C 4-model handover (이전, prior art 전)** | `docs/handovers/v0.4-cycle-gamma-phase-c-4model-true-signal-2026-06-08.md` (200 LLM 호출 데이터 + mxtral≡llama 관찰 — 측정 자체 valid, 단 mechanism novelty 주장은 positioning doc 으로 narrowed) |
| **🟢 Phase B Option A results (이전 entry)** | `docs/handovers/v0.4-cycle-gamma-phase-b-option-a-results-2026-06-08.md` (single-model framing — Phase C 에서 부분 부정됨) |
| **🟢 Phase B launch (이전 entry)** | `docs/handovers/v0.4-cycle-gamma-phase-a-closure-and-phase-b-launch-2026-06-08.md` (Phase A 10 PRs #724-#733 + Phase B 3 PRs #734-#736 + 5 production-safety notes) |
| **🟢 Cycle γ design memo** | `docs/design/v0.4-cycle-gamma-external-benchmark-integration.md` (4 외부 벤치 통합 + 진입 조건 §7) |
| Prev entry (cycle β 마감) | `docs/handovers/v0.4-cycle-beta-closure-2026-06-06.md` |
| Prev entry (cycle β 진입 framing — 정정됨) | `docs/handovers/v0.4-cycle-beta-entry-2026-06-06.md` |
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
- Promise plugin API stability before v1.0 (the SDK ships with a SemVer +
  12-month deprecation policy — `docs/SDK_VERSIONING.md` — but the API
  freeze itself is a v1.0 gate)
- **Ship a new feature while `main` CI is red** — 로드맵 Phase 2 가 먼저
- **Delete / skip / xfail a failing test to make CI green** — 각 실패는
  "제품 회귀"인지 "테스트 낡음"인지 판정해 기록해야 합니다
- **Launch the dev server with `run_in_background`** — 이전 세션에서 고아
  프로세스가 `:8000` 을 중복 바인딩해 operator 의 요청을 가로챘습니다.
  테스트는 operator 가 띄운 서버에 curl 로 붙거나 단발 foreground 실행으로
- **Wrap an LLM measurement run in `nohup` or your own `timeout`** —
  detach 되면 완료 통지가 오지 않고, timeout 은 실행을 EXIT 124 로 죽입니다
- **Declare "v0.6 entry"** — Fork A/B 는 operator 의 전략 결정입니다

## Operational conventions (PR / commit / branch)

- Branch naming: current convention is `feat/v0.6.2-<topic>` /
  `fix/v0.6.2-<topic>` / `docs/v0.6.2-<topic>` / `chore/v0.6.2-<topic>`
  (재개 사이클). v0.6.1 접두사는 2026-06-26 까지의 작업에 쓰였고, 그 이전
  v0.2 / v0.3 / v0.4 / v0.5 접두사는 히스토리에만 남습니다. `feat/v0.6-<topic>`
  은 **Fork 결정 후 v0.6 정식 진입 시점부터** 사용하세요.
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

자메스는 **v1.0 까지 "범용 모체(mother platform)"로만** 강화합니다.
도메인 분화(법률·식품·유통·여행·금융)는 v1.0 이후, 또는 Fork A (고객 LOI)
확정 이후에만 시작합니다. 이 세션에서 도메인 코드를 추가하지 마세요.

**현재 위치 (2026-09-03 기준)**

- **v0.5 closed (2026-06-13), v0.6 정식 미진입.** 게이트 = Dim F (외부 고객
  6 개월 파일럿) 미통과. 2-fork 계약 (Fork A LOI / Fork B 6 개월 무LOI
  재평가) 판정 시점 ≈ 2026-12-13. **operator 결정 사항**.
- **최신 공식 릴리스 = v0.4.4** (DOI `10.5281/zenodo.20652679`).
  v0.5 / v0.6 / v0.6.1 은 `main` 에만 존재, 태그·DOI 없음.
- **v0.6 / v0.6.1 제품 하드닝 스트림** (#886–#1078, 약 190 PR) 이
  2026-06-13 → 06-26 에 진행. 운영 하드닝 · 양식 엔진 · 에이전트 트랙 ·
  LLM 라우팅 통합 · 채팅 UX 개편 · UI 8→5 통합 · CSP 이관 · 이미지 OCR/비전
  수리 · heartbeat 스트리밍.
- **🟠 재개 시 첫 작업 = CI 그린 복구** (규모 축소됨). `test.yml` 은
  최신 실행까지 실패이지만 **#1080 (08-28) 이 66 → 6 failed** 로 줄였고,
  rule #5 위반 2건도 해소했습니다 (1건 분할 / 1건 계획과 함께 grandfather).
  남은 로컬 실패 9건 중 **CI 가 실제로 보는 것은 4개 모듈**.
  **초록을 만들려고 테스트를 지우거나 skip 하지 마세요** — 각 실패마다
  "제품이 틀렸나 / 테스트가 낡았나 / 환경 탓인가"를 판정해 기록합니다.
  #1080 이 좋은 선례입니다 (137 라우트를 숨긴 프레임워크 래퍼를 찾아냄).
- **기능 개발은 2026-06-26 에 멈춤.** 이후 4 PR 은 문서·인용·CI 유지보수.
- **단계별 재개 계획 = `docs/handovers/v0.6.2-restart-roadmap-2026-09-03.md`
  §2 (Phase 1–7).** Phase 1(문서 동기화)은 완료, Phase 2(CI 그린)가 다음.

**과거 사이클의 방법론 규율은 그대로 유효합니다** — 사용자의 9 건 catch
(post-hoc fit / 0.000 진위 / family vs size / prior art / cycle ↔ collab arc
분리 / 단일 axis ablation → defect framing 금지 / Path D positioning /
D2 V2 bilingual regression / JAMES 정체성 = measurement-driven discovery)
와 그로부터 박힌 measurement-side 룰
(`feedback_methodological_chain_before_plan` /
`feedback_fixture_fitness_before_verdict` /
`feedback_evidence_grounded_validity_check` /
`feedback_finding_size_honest_framing` /
`feedback_single_axis_ablation_misframing` /
`feedback_eval_cycle_vs_collab_arc_separation`) 는 다음 측정 사이클
(로드맵 Phase 5) 진입 시 의무 reading 입니다. 자세한 서술은
`memory/` 와 v0.4 cycle γ 핸드오버들에 보존돼 있습니다.
