# Enterprise Graph Memory Lifecycle Architecture

> **자메스 의 5-layer 아키텍처 reference 문서**
>
> **작성일**: 2026-05-21
> **마지막 업데이트**: 초안 (사용자 비판 시리즈 반영)
> **상태**: 구현 reference + 외부 공개 / 학술 발표 용

---

## 0. Vision — 한 줄로

> **"넣고 검색만 하는 RAG 가 아니라, 시간에 따라 기억이 변화하는 lifecycle 을 운영하는 시스템."**

대부분의 RAG / GraphRAG 시스템은 **append-only**:
- 벡터 DB 에 chunk 추가
- 재색인
- stale memory 방치
- 삭제 propagation 부재
- 운영자 개입 휘발

자메스는 **lifecycle-aware**:
- Provenance-tracked mutation
- Deterministic cascade
- Manual immunity
- Audit graph
- Effect-based invariants

---

## 1. 5-Layer Architecture

```
┌────────────────────────────────────────────────────────────────┐
│ Layer 5: Agentic Reasoning & Orchestration                      │
│ - Query planning, multi-step reasoning                          │
│ - Agent orchestration, tool use, planning                       │
│ - Reasoning backend plugin contract                             │
│ - Cognitive Middleware (reflection / verification / planner)    │
├────────────────────────────────────────────────────────────────┤
│ Layer 4: Ontology Reasoner & Lifecycle Semantics                │
│ - Entity canonicalization, alias merge                          │
│ - Contradiction detection & arbitration (deterministic)         │
│ - Temporal validity, fact expiration                            │
│ - Causality chain, evidence aging                               │
│ - Write-time governance (Memory Loom 5-gate)                    │
├────────────────────────────────────────────────────────────────┤
│ Layer 3: Memory Operating System (CASCADE Engine) ⭐            │
│ - Provenance-tracked mutation lifecycle                         │
│ - Document add/delete/modify cascade                            │
│ - Confidence recompute (noisy-OR)                               │
│ - Manual immunity                                               │
│ - Cross-doc aggregation                                         │
│ - Audit logging                                                 │
├────────────────────────────────────────────────────────────────┤
│ Layer 2: Extracted Facts                                        │
│ - (subject, predicate, object) triples                          │
│ - Source attribution (sources array)                            │
│ - Confidence weights                                            │
│ - Temporal scope (timestamps)                                   │
├────────────────────────────────────────────────────────────────┤
│ Layer 1: Raw Memory                                             │
│ - Documents (PDFs, MDs, raw text)                               │
│ - Chunks, embeddings                                            │
│ - File provenance (uploads, timestamps)                         │
└────────────────────────────────────────────────────────────────┘
```

---

## 2. Layer 별 책임 + 코드 매핑

### 2.1 Layer 1 — Raw Memory

| 책임 | 코드 매핑 |
|---|---|
| 파일 업로드·저장 | `server_llmwiki.py /upload/` endpoint |
| Chunk 분할 | `core/wiki_generator.py` chunking |
| 임베딩 생성 | `core/wiki_generator.py` (Ollama embedding) |
| File metadata | uploads/ 디렉토리, `.extraction.json` sidecar |

### 2.2 Layer 2 — Extracted Facts

| 책임 | 코드 매핑 |
|---|---|
| (s, p, o) triple 추출 | `core/wiki_generator.py::process_document_for_entities` |
| Entity 식별 | `core/wiki_generator.py` (LLM-based) |
| Source attribution | `core/relations_schema.py` (sources 배열 schema) |
| Confidence weights | LLM 출력 score |

### 2.3 Layer 3 — Memory Operating System ⭐

| 책임 | 코드 매핑 |
|---|---|
| Sources schema | `core/relations_schema.py` (Phase A, PR #266) |
| Noisy-OR derivation | `core/relations_schema.py::compute_confidence_from_sources` (Hotfix PR #349) |
| Cross-doc aggregation | `core/wiki_generator.py::_merge_relations_into_existing_entity` (Hotfix PR #350) |
| Delete cascade | `core/cascade.py::cascade_remove_doc_from_sources` (Phase C, PR #270) |
| Modify cascade | `core/cascade.py::cascade_modify_doc` (Phase D, PR #274) |
| Manual immunity | `core/cascade.py` D2 분기 (role check) |
| Orphan entity sweep | `core/cascade.py::find_orphan_entities` |
| Audit logging | `core/cascade.py` + `core/observability.py` |
| Doc-source asymmetric gate | `core/graph_engine.py::_doc_outgoing_hop_valid` (PR #139) |

**Invariant tests (Layer 3 의 effect 보장)**:
- `tests/test_relations_schema.py` (7 invariants)
- `tests/test_phase_b_ingestion_sources.py::CrossDocSourceAggregationTests` (5 invariants)
- 합계 12 invariants

**구현 상태**: ✅ Phase A–E 완료 (v0.3 cycle). v0.3.x hotfix 2건 (PR #349/350)
으로 cross-doc aggregation + noisy-OR derivation 보강.

### 2.4 Layer 4 — Ontology Reasoner & Lifecycle Semantics

| 책임 | 코드 매핑 (현재) | 코드 매핑 (v0.4 계획) |
|---|---|---|
| Write-time governance | `core/memory/loom.py` (5-gate) | (현 구현 그대로) |
| Ontology validation | `core/ontology.py` (relation type list) | + SHACL/OWL extension |
| Temporal validity | ❌ 미구현 | `core/relations_schema.py` 에 valid_from/until 추가 (T1) |
| Contradiction arbitration | ⚠️ 부분 (Gate 5) | `core/conflict_resolver.py` 신규 (T2) |
| Evidence aging | ❌ 미구현 | source weight 의 decay 함수 (T3) |
| Reviewer authority | ❌ 미구현 | manual source 의 reviewer/approval (T4) |
| Causality chain | ❌ 미구현 | derived_from tracking (T6) |

**구현 계획**: T1–T6 6 영역 → `docs/design/v0.4-lifecycle-semantics-roadmap.md`.

### 2.5 Layer 5 — Agentic Reasoning & Orchestration

| 책임 | 코드 매핑 |
|---|---|
| Multi-step reasoning | `core/reasoning/` (Phase 2, 진행 중) |
| Reasoning backend plugin | PR #283/284/285/324/326 |
| Cognitive Middleware | PR #275/289/290/295/297 (v0.3, `docs/ARCHITECTURE.md §5.7` 와 정합) |
| Trace replay | `core/observability.py` + `replay_trace.py` |
| Episodic memory | PR #338 (infra), PR #336 (design) |
| Plugin contract | PR #344 (4 Protocol types) |

---

## 3. Cross-Cutting Concerns

다음은 specific layer 가 아닌 가로지르는 영역:

| 영역 | 코드 |
|---|---|
| Security (RBAC + ABAC) | `core/security_layer.py`, `core/policy_engine.py` |
| Audit log | `core/observability.py`, `core/audit_bridge.py` |
| Personality / character | `core/character_profile.py` |
| Self-evolution | `tools/patch/patch_validator.py` |
| LLM routing | `core/llm_catalog.py`, `llm/router.py` |
| **UI i18n contract** | backend `label_key` 패턴 (7 modules, 2026-05-22 sweep). v0.4 신규 UI-노출 라벨도 동일 패턴 필수 — `tests/test_*_i18n.py` contract test 가 회귀 가드 |

이들은 5-layer 전반에 걸쳐 작용.

---

## 4. Data Flow — 시나리오 예시

### 4.1 새 문서 업로드 (예: report_2026Q3.pdf)

```
[Layer 1] /upload/ → 파일 저장 → chunks 분할 → embedding 생성
                                        ↓
[Layer 2] process_document_for_entities → LLM 추출 → (s,p,o) triples 도출
                                        ↓
[Layer 3] _merge_relations_into_existing_entity → 기존 관계 sources 에 append
                                        ↓ (or 새 relation 행 추가)
[Layer 3] compute_confidence_from_sources → noisy-OR 로 confidence 재계산
                                        ↓
[Layer 4] (Write-time gate) Memory Loom 5-gate → confidence/ontology/dedup/conflict 검증
                                        ↓
[Layer 1] sidecar JSON 저장 (.extraction.json) ← 미래 modify diff 시작점
                                        ↓
        Audit log: ingestion event 기록
```

### 4.2 문서 삭제 (예: report_2026Q1.pdf 삭제)

```
[User] /admin/files/delete?file=report_2026Q1.pdf
                                        ↓
[Layer 3] cascade_remove_doc_from_sources
   - 모든 entity 의 relations.sources 스캔
   - doc_id == "report_2026Q1.pdf" + role != "manual" 항목 제거 (claim 4 면역)
   - confidence 재계산 (noisy-OR)
   - sources 빈 relation 삭제
                                        ↓
[Layer 3] find_orphan_entities → 고립 entity 제거
                                        ↓
[Layer 1] vector_store.delete_by_source
                                        ↓
        Audit log: file_delete event + before/after sources
```

### 4.3 질의 (예: "Joby 와 NVIDIA 관계?")

```
[User] /query/?q=Joby와+NVIDIA의+관계
                                        ↓
[Layer 5] Query planner → 쿼리 의도 분석
                                        ↓
[Layer 1] Vector search (chunks)
                                        ↓
[Layer 3] Graph traversal — `_doc_outgoing_hop_valid` (asymmetric gate) 적용
                                        ↓
[Layer 4] Ontology-weighted DFS score
                                        ↓
[Layer 5] Cognitive Middleware: reflection → verification → final answer
                                        ↓
        Audit log: trace_id 로 추론 경로 기록
```

---

## 5. 차별화 — 진짜 경쟁자 5 영역과 비교

### 5.1 vs Temporal Graph DB (bitemporal, versioned edges)

| 측면 | Temporal Graph DB | 자메스 |
|---|---|---|
| 차원 | **시간** (when fact was valid) | **출처** (which doc contributed) |
| 변화 트리거 | timestamp progression | document add/delete/modify event |
| 결합 가능? | ✅ Yes (T1 신규 stage 가 결합) |

→ 차별화: 자메스는 **출처 차원 lifecycle**. T1 (Temporal Validity) 추가 시 두 차원 결합.

### 5.2 vs Truth Maintenance Systems (TMS, 1980s)

| 측면 | TMS | 자메스 |
|---|---|---|
| 방식 | Belief revision (논리) | 신뢰도 누적 (확률) |
| 계산 | iterative consistency check | closed-form noisy-OR |
| 결정성 | 부분 (cycle 가능) | strict deterministic |
| Audit | 부분 | replayable + invariant tests |

→ 차별화: 자메스는 **closed-form + deterministic + invariant lock-in**.

### 5.3 vs CRDT / Replicated Knowledge

| 측면 | CRDT | 자메스 |
|---|---|---|
| 환경 | 분산 multi-node | 단일 node |
| 일관성 | eventual consistency | strict immediate consistency |
| 충돌 해결 | 자동 merge (LWW, OR-Set 등) | deterministic rules + manual immunity |
| 결합 가능? | ✅ Yes (T5 replayable audit 와) |

→ 차별화: 자메스는 **단일 node deterministic**. 분산 시 T5 (event-sourced replay) 로 확장 가능.

### 5.4 vs Provenance-aware DB (W3C PROV)

| 측면 | Provenance DB | 자메스 |
|---|---|---|
| 영역 | 일반 DB lineage | RAG/KG 특화 lifecycle |
| 추적 단위 | tuple / row lineage | (s,p,o) triple + source 분리 |
| 정리 메커니즘 | 일반 (사용자 정의) | claim 2~7 specific cascade |

→ 차별화: 자메스는 **RAG/GraphRAG 운영 계층 특화**.

### 5.5 vs Knowledge Ledger (blockchain-like immutable)

| 측면 | Knowledge Ledger | 자메스 |
|---|---|---|
| 데이터 | append-only immutable | mutable cleanup |
| 사용처 | audit / compliance | operational RAG |
| 패러다임 | event sourcing only | hybrid (state + event) |

→ 차별화: 자메스는 **mutable state + audit log dual**. T5 (replayable audit) 로 event-sourced 우산 가능.

---

## 6. Invariant Test 철학

자메스의 lifecycle 보장은 **invariant 테스트 lock-in** 으로 보장:

### 6.1 현재 (Layer 3)

12 invariants (`tests/test_relations_schema.py` + `tests/test_phase_b_ingestion_sources.py`):

| Invariant | 보장 |
|---|---|
| F1: single source identity | c({w}) = w |
| F2: two-source divergence | c({w_1, w_2}) ≠ min(w_1+w_2, 1) |
| F3: 3-source concrete | c({0.7, 0.7, 0.7}) = 0.973 |
| F4: asymptotic, no saturation | c → 1 but < 1 |
| F5: strict increase | adding source → c increases |
| F6: strict decrease | removing source → c decreases |
| F7: weight clamp | w ∉ [0,1] → element-wise clamp |
| S1: cross-doc append | 2nd doc → sources.append (not new row) |
| S2: symmetric | forward + inverse aggregation |
| S3: joint contract | (F2 + S1) → 2 sources × 0.7 = 0.91 |
| S4: idempotency | same doc_id → skip |
| S5: new target | new triple → new row |

→ 미래 누가 코드를 잘못 바꾸면 즉시 CI 실패 → lifecycle invariant 영구 보장.

### 6.2 Layer 4 (v0.4 계획)

신규 invariants:

| 영역 | 신규 invariant 후보 |
|---|---|
| T1 Temporal | T1.1: valid_until 경과 시 자동 expiration |
| T2 Contradiction | T2.1: 동일 (s, p) 의 다른 o 발생 시 deterministic 결정 (LLM 미사용) |
| T3 Aging | T3.1: source weight 가 시간에 따라 단조 감소 |
| T4 Reviewer | T4.1: lower-rank reviewer 의 manual 은 higher-rank 가 override 가능 |
| T5 Replayable | T5.1: 임의 시점 graph 를 event 만으로 재구성 가능 |
| T6 Causality | T6.1: base fact 제거 시 derived fact 자동 invalidation |

→ Layer 4 의 effect 도 invariant 로 lock-in.

---

## 7. Reference Implementation 가치

### 7.1 MIT 오픈소스 우위

자메스는 MIT 라이선스 + GitHub public:
- 누구나 reference 로 사용 / fork
- 학술 인용 / 산업 adoption
- 시장 표준 정의 우위

### 7.2 Show HN / 글로벌 노출

- 본 architecture 메모가 외부 공개 reference
- "Memory OS for LLM agents" 카테고리 정의

---

## 8. Roadmap — 구현 phase

| Phase | Layer | 시점 | 구현 상태 |
|---|---|---|---|
| Phase 1 | Layer 3 (Memory OS) | 2026 v0.3 cycle | ✅ Phase A–E + Hotfix 2건 완료 |
| Phase 2 | Layer 4 (Ontology Reasoner) | 2026 Q4 ~ 2027 Q2 (v0.4) | T1–T6 6 영역 디자인 → 구현 |
| Phase 3 | Layer 5 (Agentic Reasoning) | 2027 Q3 ~ 2028 (v0.5+) | Cognitive Middleware 부분 구현, 확장 계획 |

상세: `ROADMAP.md`

---

## 9. 외부 활용

### 9.1 누구를 위한 문서인가?

| 독자 | 활용 |
|---|---|
| 신규 기여자 | onboarding gate |
| 학회 reviewer | architecture context |
| 사용자 (개발자) | reference 백서 |

### 9.2 활용 예시

- Show HN 본문 link: "5-layer architecture reference 참조"
- 학회 paper introduction: "We define the following 5-layer model..."

---

## 10. 관련 문서

| 문서 | 용도 |
|---|---|
| `docs/ARCHITECTURE.md` | 메인 architecture 문서 (Mission / Non-goals / Trust Zones / Cognitive Middleware §5.7) |
| `docs/design/v0.3-knowledge-cascade.md` | Layer 3 디자인 (구현됨) |
| `docs/design/v0.4-lifecycle-semantics-roadmap.md` | Layer 4 디자인 (계획, 신규) |
| `docs/postmortems/2026-05-20-knowledge-cascade-defects.md` | Hotfix 발견·정정 |
| `ROADMAP.md` | 전체 product roadmap (v0.3 / v0.4 / v0.5 / v1.0) |

---

**End of Memory Lifecycle Architecture Reference.**

본 문서는 자메스의 5-layer vision 의 구현 reference.
