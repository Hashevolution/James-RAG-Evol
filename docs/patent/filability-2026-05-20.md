# 출원 가능 후보 안정성 평가 — 2026-05-20

> 본 문서는 2026-05-20 시점의 메인 브랜치 상태 (PR #349/350/351/352 머지 후) 를
> 기준으로 14개 특허 후보(8 기존 + 6 신규)의 **안정적 출원 가능성**을 평가한다.
>
> **출원 framing 원칙** (Postmortem PR #352 §4.4):
> - 청구는 **현재 코드 + 테스트** 기반으로 작성 (skeleton/디자인 메모 X)
> - 방향은 **코드 → 청구**, 출원은 사용자 시점적 트리거 발동 시
>
> **사용자 우선순위** (Postmortem §8): 출원 비우선. Phase 2 Planner / Episodic
> Memory / Phase 2 Default ON 이 명시 우선.

---

## 1. 안정성 평가 4단계 기준

| 등급 | 의미 | 출원 권고 |
|---|---|---|
| ⭐⭐⭐ | 코드 ≥3개월 무변동, 테스트 lock-in 견고, 향후 변경 가능성 낮음 | ✅ 즉시 가능 |
| ⭐⭐ | 코드 ≥1개월 안정, 최근 종속/관련 변경 있으나 핵심 미변동 | ✅ 1주 내 가능 |
| ⭐ | 최근 정정 / 종속 PR 진행 / 안정 미확보 | ⚠️ 1~3개월 대기 |
| ❌ | 진행 중 트랙 / 미완성 / 설계 변경 가능 | ❌ 출원 보류 |

---

## 2. 14 후보 안정성 평가표

| Stage | 점수 | 핵심 코드 | 코드 안정성 | 테스트 lock | 향후 변경 위험 | 안정적 출원 |
|---|---|---|---|---|---|---|
| **0 — Umbrella** | 3/5 조건부 | v0.3.0 Platform Skeleton 전체 | ⭐ 아키텍처 진화 중 (Cognitive Layer, Plugin API) | ⚠️ 부분 | HIGH | ❌ WAIT |
| **1 — Memory Loom 5-gate** | 4/5 ⭐ | `core/memory/loom.py:80-149` | ⭐⭐⭐ v0.1 부터 (2026-05-05) 핵심 무변동 | ✅ 단위 테스트 | LOW | ✅ **HIGH — 즉시** |
| **1A — Doc-source gate** | 3/5 ⭐ | `core/graph_engine.py::_doc_outgoing_hop_valid` (PR #139) | ⭐⭐⭐ 단일 PR 머지 후 무변동 | ✅ 회귀 테스트 | LOW | ✅ **HIGH — 즉시** |
| **1B — Cascade** | 4/5 ⭐⭐ | `core/relations_schema.py`, `core/cascade.py`, `core/wiki_generator.py`, `core/graph_editor.py` | ⭐⭐⭐ Phase A-E (2026-05-13/14) + Hotfix 1+2 (2026-05-20) — 명세 ↔ 구현 ↔ 테스트 3자 정합 회복 | ✅ **12 invariant lock** (최다) — 회귀 즉시 검출 | LOW (0.6 threshold 종속항 broad 처리 가능) | ✅ **HIGH — 즉시 가능** |
| **2 — Feedback Shadow** | 2/5 | `core/feedback_engine.py:35-151` | ⭐⭐⭐ 안정 | ✅ 부분 | LOW | ✅ MID (약한 신규성) |
| **3 — Security 2-stage** | 2/5 | `core/security_layer.py` | ⭐⭐ PR #322 (catalog_context) 종속 추가 | ✅ 광범위 | LOW | ✅ MID (#322 종속항) |
| **4 — Trait Pair** | 2/5 | `core/character_profile.py:17-97` | ⭐⭐⭐ 안정 (#160~#170 종결) | ✅ 단위 테스트 | LOW | ✅ LOW (약한 신규성) |
| **4A — Self-Evolution** | 3/5 ⭐ | `tools/patch/patch_validator.py` + PR #69/77/78/79 | ⚠️ PR #78 (rollback)/#79 (audit) 머지 상태 확인 필요 | ⚠️ 부분 | MID | ⚠️ **확인 후** |
| **4B — Trace Correlation** | 2/5 | `core/observability.py` (PR #67/97/138) | ⭐⭐⭐ 안정 | ✅ 부분 | LOW | ✅ MID |
| **5 — Reasoning Backend** | 4/5 추정 | trace_schema, replay_trace (PR #283/284/285) + Plugin API (PR #343/344) | ❌ Plugin API 설계만 완료 (구현 진행 중) | ⚠️ trace 부분만 | HIGH | ❌ WAIT 1~2개월 |
| **6 — Cognitive Middleware** | 3/5 추정 | reflection, verification, tool router, planner (PR #275/289/290/295/297) | ❌ Phase 2 Default ON 미결 (§8 명시) | ⚠️ 부분 | HIGH | ❌ WAIT Phase 2 종결 후 |
| **7 — Change Request** | 2/5 추정 | PR #237/239/240/243 | ⭐⭐ 안정 | ✅ 부분 | LOW | ✅ LOW (약한 신규성) |
| **8 — Episodic Memory** | 2/5 추정 | PR #338 (infra) + #336 (design) | ❌ §8 next priority — 구현 미완 | ❌ infra 만 | HIGH | ❌ WAIT |
| **9 — Catalog Context (Schema v1.1)** | 2/5 추정 | PR #322 | ⭐⭐⭐ 안정 | ✅ injection fixture suite (PR #319/320) | LOW | ✅ **STAGE 3 종속항** 흡수 |
| **10 — Replay-able Audit Trace** | 3/5 추정 | PR #284 (wiring) + #285 (replay_trace.py) | ⭐⭐⭐ 안정 | ✅ 부분 | LOW | ✅ **STAGE 4B 종속항** 또는 별건 |

---

## 3. Tier 분류 — 출원 시점별 권고

### Tier 1: 즉시 안정적 출원 가능 (3건, 약 5.4만 원)

| Stage | 사유 |
|---|---|
| **1 — Memory Loom 5-gate** | v0.1 부터 무변동, 강한 점수 4/5, 청구항 명확 (5 게이트 + audit log) |
| **1A — Doc-source gate** | PR #139 단일 머지 후 무변동, 비대칭 출처 게이트 신규성 강함 |
| **1B — Cascade** | **12 invariant lock (최다)**, 명세 ↔ 구현 ↔ 테스트 3자 정합, 핫픽스 후 회귀 차단 견고. 점수 4/5 ⭐⭐ 최강. Show HN 27일 전 출원 = 글로벌 노출 전 우선일 확보. |

**합계**: 3건 × 1.8만 원 (개인 70% 감면) = **5.4만 원**

### Tier 2: 1주 내 안정적 출원 가능 (5건, 약 9만 원)

| Stage | 사유 | 출원 방식 |
|---|---|---|
| **2 — Feedback Shadow** | 안정. 청구를 (mode, query_topic_hash) hash-keyed 로 좁힘 | 별건 |
| **3 — Security 2-stage** | 안정. PR #322 catalog_context 를 종속항으로 보강 | 별건 (`9` 흡수) |
| **4B — Trace Correlation** | 안정. PR #284/285 (replay_trace) 추가로 강화 | 별건 (`10` 옵션 흡수) |
| **7 — Change Request** | 안정. KG 운영 절차 신규성 약함 | 별건 (약한) |
| **10 — Replay-able Audit Trace** | 안정. STAGE 4B 와 결합 또는 별건 | 4B 종속항 권장 |

**합계**: 5건 × 1.8만 원 = **9만 원**

### Tier 3: (해당 없음 — STAGE 1B 는 Tier 1 로 재분류, 2026-05-20)

> 이전 분류 (2026-05-20 첫 평가) 에서는 STAGE 1B 를 "사용자 우선순위 §8 에
> 없음" 이유로 Tier 3 분류. 그러나 §8 은 **엔지니어링 우선순위** 이지 출원
> 가능성과 무관. 기술적으로는 12 invariant lock + 3자 정합 + 핫픽스 후 회귀
> 차단 견고 → **Tier 1 분류가 정합**. 재분류 적용 (2026-05-20).

### Tier 4: 점수 약함 — 출원 의무 없음 (1건)

| Stage | 사유 |
|---|---|
| **4 — Trait Pair** | 안정하나 점수 2/5, 선행기술 광범위. MIT 공개로 방어 충분. 출원 가치 낮음. |

### Tier 5: 안정성 대기 (4건)

| Stage | 대기 사유 |
|---|---|
| **0 — Umbrella** | 아키텍처 진화 중 (Cognitive Layer, Plugin API) |
| **4A — Self-Evolution** | PR #78/79 머지 상태 확인 필요 |
| **5 — Reasoning Backend** | Plugin API 설계만 완료, 구현 진행 중 (1~2개월) |
| **6 — Cognitive Middleware** | Phase 2 Default ON 미결 (§8 명시) |
| **8 — Episodic Memory** | §8 next priority, 구현 미완 |

### Tier 6: 종속항 흡수 권장 (2건)

| Stage | 흡수 위치 |
|---|---|
| **9 — Catalog Context** | STAGE 3 (Security) 종속항 |
| **10 — Replay-able Audit Trace** | STAGE 4B (Trace) 종속항 또는 별건 |

---

## 4. 권고 시나리오

### 시나리오 A — Tier 1 Bundle (Minimal Strong) — STAGE 1B 재분류 반영 (2026-05-20)
- 출원 건수: **3건 (STAGE 1 + 1A + 1B)**
- 비용: **약 5.4만 원**
- 가치: 가장 강한 단위 발명 3건 우선일 확보 — 점수 4/3/4 의 핵심 3건. STAGE 1B 의 12 invariant + cascade 핵심 IP 포함. Show HN 전 출원 = 글로벌 노출 직전 우선일 확보.
- 권장 시점: Show HN 전 (2026-06-16 까지 27일)

### 시나리오 B — Tier 1 + 강한 Tier 2 (Selective Strong)
- 출원 건수: **5건 (시나리오 A + STAGE 3 + 4B)**
- 비용: **약 9만 원**
- 가치: 핵심 + 안정 + 점수 ≥2/5 보강 + 종속항 흡수 (STAGE 9, 10)
- 권장 시점: Show HN 전, 자금 여유

### 시나리오 C — Comprehensive Stable (Tier 1 + 2 전체)
- 출원 건수: **8건 (시나리오 B + STAGE 2 + 7 + 10)**
- 비용: **약 14.4만 원**
- 가치: 모든 안정 후보 일괄 출원
- 권장 시점: 자금·시간 여유 시. Show HN 전 권장.

### 시나리오 D — (폐기: STAGE 1B 가 Tier 1 으로 이동, 시나리오 C 가 최대 시나리오)

### 시나리오 E — 현 PAUSE 유지
- 출원 건수: 0건
- 비용: 0원
- 가치: MIT 공개로 defensive publication 80% 커버. Grace period 활용.
- 권장 시점: 사용자 우선순위 (§8 Phase 2 트랙) 완료 후 재평가

**현 PAUSE = 시나리오 E**. 사용자 트리거 시 시나리오 A/B/C/D 중 선택.

---

## 5. 시점적 트리거 후보

다음 사건 발동 시 PAUSE 해제 권장:

| 트리거 | 권장 시나리오 |
|---|---|
| Show HN (2026-06-16) 임팩트 큼 → 글로벌 노출 | A 또는 B (출원 후 노출 = 강한 시퀀스) |
| 경쟁사가 유사 발명 출원 발견 | D (긴급 우선일 확보) |
| 투자 라운드 due-diligence 시작 | C 또는 D (IP 자산화) |
| M&A 협상 개시 | D (전체 portfolio) |
| 1년 grace 임박 (2026-12 ~ 2027-01) | B 또는 C (선별 보호) |
| 사용자 명시 결정 | 사용자 선택 |

**현 시점 (2026-05-20)**: 강한 트리거 없음. PAUSE 유지 + 자연 누적 대기.

---

## 6. 즉시 가능한 출원 준비 작업 (PAUSE 중)

트리거 발동 시 빠른 출원을 위해 PAUSE 중에도 가능한 작업:

| 작업 | 대상 stage | 소요 |
|---|---|---|
| Tier 1 stage 청구항 invariant 매핑 (STAGE 1B 처럼) | STAGE 1, 1A | Claude 자동 1시간 |
| 도면 mermaid → PDF 변환 도구 검증 | 8 stage | 30분 |
| 출원인 정보 입력 양식 사전 작성 | 공통 | 15분 |
| KIPRIS 추가 키워드 검색 (STAGE 1 + 1A) | STAGE 1, 1A | 30분 |
| 출원료 결제 수단 사전 등록 (특허로) | 공통 | 10분 |

위 작업은 트리거 발동 시 출원까지 시간을 **2~3일 → 4~6시간** 으로 단축.

---

## 7. 코드 ↔ 청구 ground truth 매핑 (출원 시 reference)

각 안정 stage 의 청구 시 참조해야 할 정확한 위치:

### STAGE 1 (Memory Loom)
- `core/memory/loom.py:80-149` (5 게이트)
- `core/memory/loom.py:200-267` (자가 테스트)
- 임계값: `MAX_WRITES_PER_SESSION=3`, `MEMORY_CONFIDENCE_TH=0.75`, `MEMORY_DEDUP_WINDOW=100`, `CONFLICT_CONFIDENCE_DIFF=0.3`

### STAGE 1A (Doc-source gate)
- `core/graph_engine.py::_doc_outgoing_hop_valid` (PR #139, commit `371838c`)

### STAGE 1B (Cascade) — 트리거 발동 시
- `core/relations_schema.py::compute_confidence_from_sources` (noisy-OR, Hotfix 1)
- `core/wiki_generator.py::_merge_relations_into_existing_entity` (Hotfix 2)
- `core/cascade.py::cascade_remove_doc_from_sources` (Phase C, 153 ~)
- `core/cascade.py::cascade_modify_doc` (Phase D, 432 ~)
- `core/cascade.py::find_orphan_entities` (165 ~)
- `tests/test_relations_schema.py` 7 invariant + `tests/test_phase_b_ingestion_sources.py::CrossDocSourceAggregationTests` 5 invariant

### STAGE 2 (Feedback)
- `core/feedback_engine.py:35-43` (signal dict)
- `core/feedback_engine.py:107-151` (accumulate)

### STAGE 3 (Security) + STAGE 9 (Catalog Context 종속항)
- `core/security_layer.py::pre_check` (메인 ≈ 409)
- `core/security_layer.py::mask_sensitive` (메인 ≈ 339)
- `core/security_layer.py::filter_answer_by_role` (메인 ≈ 363)
- `core/security_layer.py::cross_stage_abac_verify` (메인 ≈ 249)
- PR #322 catalog_context schema v1.1

### STAGE 4 (Trait)
- `core/character_profile.py:17-29` (trait 정의)
- `core/character_profile.py:55-66` (set + rebalance)
- `core/character_profile.py:68-97` (prompt modifier)

### STAGE 4B (Trace) + STAGE 10 (Replay 종속항)
- `core/observability.py` (PR #67/97/138 머지, ~245줄)
- PR #284 trace_synth_call wiring (12 LLM call sites)
- PR #285 replay_trace.py

### STAGE 7 (Change Request)
- PR #237 state machine + storage
- PR #239 workspace UI panel
- PR #240/243 apply dispatcher + endpoints

---

## 8. 출원 차단 조건 (해결되어야 함)

| 조건 | 해당 stage | 해결 상태 |
|---|---|---|
| Skeleton ↔ 구현 명시 불일치 | STAGE 1B (이전) | ✅ Hotfix 1+2 (2026-05-20) |
| Phase A-E 코드 미머지 | STAGE 1B (이전) | ✅ PR #266~#274 (2026-05-13/14) |
| PR #139 머지 상태 | STAGE 1A | ✅ `371838c` 머지 완료 |
| PR #78/79 머지 상태 | STAGE 4A | ⚠️ **확인 필요** |
| Phase 2 Default ON 결정 | STAGE 6 | ❌ 미결 (§8 active) |
| Plugin API 구현 진행 | STAGE 5 | ❌ 설계만 완료 (#343/344) |
| Episodic Memory 구현 | STAGE 8 | ❌ infra 만 (#338) |

---

**End of filability assessment.**

본 평가는 2026-05-20 시점 기준. 메인 브랜치 변경 시 재평가 필요. PAUSE 해제 시
`docs/patent/HANDOVER.md §0` 의 재개 첫 메시지 템플릿 사용.
