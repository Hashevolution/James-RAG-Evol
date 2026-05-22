# Patent Portfolio Roadmap — Enterprise Graph Memory Lifecycle

> **작성일**: 2026-05-21
> **마지막 업데이트**: 2026-05-21 (사용자 비판 시리즈 반영 — effect equivalence + 5-layer architecture)
> **목적**: STAGE 1B 임시 출원 후, 자메스의 IP 자산을 reference architecture 수준으로 묶는 portfolio 전략

---

## 0. 비전 — Enterprise Graph Memory Lifecycle Architecture

### 핵심 명제

> **"단순 cascade delete 가 아니라, RAG/GraphRAG 운영 계층 의 '기억 lifecycle 운영체계 (Memory Operating System)' 를 reference architecture 로 묶는 것."**

### 차별점

| 일반 RAG / GraphRAG | 자메스 vision |
|---|---|
| 넣고 검색만 함 (append-only) | **시간에 따른 기억 변화 관리** |
| 벡터 DB 재색인 | **deterministic mutation-aware lifecycle** |
| stale memory 방치 | **provenance-tracked cleanup** |
| LLM 으로 conflict 해결 | **deterministic rules + invariant 보장** |
| 운영자 개입 휘발 | **manual immunity + governance** |

→ **"넣는 시스템" 에서 "운영하는 시스템" 으로**.

---

## 1. 5-Layer Architecture — 자메스 portfolio 구조

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 5: Agentic Reasoning & Orchestration                   │
│ - query planning, traversal, multi-step reasoning            │
│ - agent orchestration, tool use                              │
│ - 미래 출원: STAGE 5, 6 (Reasoning Backend, Cognitive)        │
├─────────────────────────────────────────────────────────────┤
│ Layer 4: Ontology Reasoner & Lifecycle Semantics             │
│ - entity canonicalization, alias merge                       │
│ - contradiction detection & arbitration                      │
│ - temporal reasoning, fact validity windows                  │
│ - causality chain, evidence aging                            │
│ - 미래 출원: STAGE T1-T6 (Phase 2)                            │
├─────────────────────────────────────────────────────────────┤
│ Layer 3: Memory Operating System (CASCADE Engine) ⭐ STAGE 1B │
│ - provenance-tracked mutation lifecycle                      │
│ - deletion propagation, mutation handling                    │
│ - orphan cleanup, confidence recompute                       │
│ - cross-doc aggregation, audit logging                       │
│ - manual immunity                                            │
│ - 출원: ✅ STAGE 1B (2026-05-21), STAGE 1A (대기)              │
├─────────────────────────────────────────────────────────────┤
│ Layer 2: Extracted Facts                                     │
│ - (s, p, o) triples with source attribution                  │
│ - extraction confidence weights                              │
│ - temporal scope (when extracted, valid until)               │
├─────────────────────────────────────────────────────────────┤
│ Layer 1: Raw Memory                                          │
│ - documents (chunks, embeddings)                             │
│ - file provenance, upload timestamps                         │
└─────────────────────────────────────────────────────────────┘
```

### Layer 별 자메스의 IP 위치

| Layer | 자메스 현재 | 미래 portfolio |
|---|---|---|
| 5 (Agent) | Cognitive Middleware (구현 진행 중) | STAGE 5, 6 출원 후보 |
| 4 (Reasoner) | 일부 구현 (Memory Loom, Ontology) | **STAGE T1-T6 6 개 신규 출원 후보** |
| **3 (Memory OS)** | **CASCADE + Doc-source gate (출원 완료/대기)** | **STAGE 1B ✅, STAGE 1A ⏳** |
| 2 (Facts) | (s,p,o) extraction (구현됨) | 출원 후보 X (LLM 추출 자체는 prior art 많음) |
| 1 (Raw) | 파일·청크·임베딩 | 출원 후보 X (commodity) |

---

## 2. Phase 1 — Layer 3 Memory OS (현재, 2026)

### 출원 / 계획

| Stage | 이름 | 상태 | 비용 | 우선일 |
|---|---|---|---|---|
| **1B** | Cascade + provenance lifecycle | ✅ 출원 완료 (10-2026-XXXXXXX) | ₩13,800 | 2026-05-21 |
| **1A** | Doc-source asymmetric gate (traversal) | ⏳ 대기 (수리 후 진행) | ₩13,800 | 예정 |

### Phase 1 의 의미

→ **Memory Operating System** 영역 확보.
→ 자메스의 lifecycle pipeline 의 "기초 OS 커널".

### Phase 1 IP 가치

- ✅ 우선일 확보 (2026-05-21)
- ✅ 12 invariant 테스트 lock-in
- ✅ Manual immunity + diff cascade + cross-doc aggregation 청구
- ⚠️ Implementation-bound (정식 전환 시 effect-based broaden 필요)

---

## 3. Phase 2 — Layer 4 Ontology Reasoner (2026 ~ 2027)

### 6 신규 stage 후보 (사용자 제시 영역)

#### STAGE T1 — Temporal Validity & Expiration

| 항목 | 내용 |
|---|---|
| 핵심 발명 | Fact validity windows (valid_from, valid_until), temporal cascade, automatic expiration |
| 차별화 | Bitemporal graph DB 와 결합 가능, 단 RAG/KG 특화 lifecycle 통합 |
| 청구항 후보 | (a) temporal scope per relation, (b) expiration-triggered cascade, (c) temporal conflict resolution |
| 출원 우선도 | ⭐⭐⭐ |
| Phase | 2027 Q1~Q2 |

#### STAGE T2 — Deterministic Contradiction Arbitration

| 항목 | 내용 |
|---|---|
| 핵심 발명 | 동일 (s, p) 에 대해 서로 다른 o 가 등장 시 결정론적 룰 기반 처리 |
| 차별화 | Mem0 / Letta 의 LLM judgment 와 명확 구분. confidence diff + source role + temporal precedence 기반 |
| 청구항 후보 | (a) contradiction detection rule, (b) deterministic arbitration (LLM 미사용), (c) audit trail |
| 출원 우선도 | ⭐⭐⭐ |
| Phase | 2027 Q1~Q2 |

#### STAGE T3 — Evidence Aging & Trust Decay

| 항목 | 내용 |
|---|---|
| 핵심 발명 | source weight 가 시간 경과 따라 자동 decay (예: exponential, half-life) |
| 차별화 | 정적 weight 가 아닌 동적 신뢰도. 분야별 decay 함수 (의료 6개월, 법률 2년 등) |
| 청구항 후보 | (a) decay 함수 family, (b) domain-specific decay, (c) decayed confidence 가 cascade 와 호환 |
| 출원 우선도 | ⭐⭐ |
| Phase | 2027 Q2~Q3 |

#### STAGE T4 — Reviewer Authority Hierarchy

| 항목 | 내용 |
|---|---|
| 핵심 발명 | Manual source 에 reviewer 권한 계층 (analyst < manager < admin) |
| 차별화 | 단일 manual flag 가 아닌 다층 governance |
| 청구항 후보 | (a) reviewer rank, (b) approval workflow, (c) audit trail per reviewer |
| 출원 우선도 | ⭐⭐ |
| Phase | 2027 Q2~Q3 |

#### STAGE T5 — Replayable Audit Graph

| 항목 | 내용 |
|---|---|
| 핵심 발명 | 모든 mutation event 를 event-sourced 로 저장 + 임의 시점의 graph 상태를 replay 로 재구성 가능 |
| 차별화 | STAGE 1B 의 audit log 를 replay 가능한 event stream 으로 확장 |
| 청구항 후보 | (a) event schema, (b) replay engine, (c) point-in-time reconstruction |
| 출원 우선도 | ⭐⭐ |
| Phase | 2027 Q3~Q4 |
| 부수 효과 | STAGE 1B 의 effect equivalence 청구 (claim 18) 와 정합 — event-sourcing 도 우리 우산 안 |

#### STAGE T6 — Causality Chain Tracking (Inference Provenance)

| 항목 | 내용 |
|---|---|
| 핵심 발명 | 추론된 fact 가 어떤 base fact 들로부터 derived 됐는지 graph 로 추적 |
| 차별화 | LLM 추론 답변에 "이 답은 fact X, Y, Z 에서 도출됨" 자동 attribution |
| 청구항 후보 | (a) inference graph schema, (b) derivation tracking, (c) base fact retraction 시 derived fact 자동 invalidation |
| 출원 우선도 | ⭐⭐⭐ |
| Phase | 2027 Q3~Q4 |

### Phase 2 일정 / 비용

| 항목 | 비용 (개인 70% 감면) |
|---|---|
| 6 stage 임시 출원 | 6 × ₩13,800 = ₩82,800 |
| 정식 전환 (선택적, 일부만) | 2~3개 × ₩125만 = ₩250~375만 |
| 총 Phase 2 (임시 출원만) | **약 ₩82,800** |

### Phase 2 효과

→ **"Memory OS + Ontology Reasoner"** 결합 IP 확보.
→ Mem0 / Letta / Zep 와 명확 구분 — "deterministic + auditable + provenance-aware".

---

## 4. Phase 3 — Layer 5 Agentic Reasoning (2027 ~ 2028)

### 기존 미출원 stage

| Stage | 영역 | Layer | 우선일 후보 |
|---|---|---|---|
| 4B (Trace Correlation) | Layer 5 observability | 5 | 2027 Q1 |
| 5 (Reasoning Backend Plugin) | Layer 5 backend | 5 | 2027 Q2 |
| 6 (Cognitive Middleware Layer) | Layer 5 reasoning pipeline | 5 | 2027 Q2 |

### Phase 3 의 의미

→ **Agentic reasoning** + **multi-step orchestration** 영역.
→ Layer 4 (ontology reasoner) 위에 사용하는 actual agent.

### Phase 3 출원 권고

- Phase 2 완료 후 진행 (사업화 진척 / 투자 진척 확인 후)
- 6 stage 중 2~3 개 선별 권장 (가장 강한 IP)

---

## 5. 출원 portfolio 전체 — 통합 일정

```
2026-05-21 ─ STAGE 1B 출원 ✅
        ↓
2026-05 ~ 06 ─ STAGE 1A 출원 (현재 대기)
        ↓
2026-06-16 ─ Show HN 노출
        ↓
2026 Q4 ─ Phase 2 출원 시작 (STAGE T1, T2 — 가장 강한 2건)
        ↓
2027 Q1 ─ STAGE T3, T6 추가
        ↓
2027 Q2 ─ STAGE T4, T5 추가
        ↓
2027 Q3 ─ Phase 3 시작 (4B 또는 5 선별)
        ↓
2027-05-21 ─ STAGE 1B 정식 전환 마감 ⚠️
              (이때 청구항 1, 4, 18 = effect-based broader 채택)
        ↓
2027-11 ─ STAGE 1B 자동 공개 (KIPRIS 검색 가능)
        ↓
2028 ─ Phase 3 정식 전환 결정
```

---

## 6. Reference Architecture 우위 vs 단순 특허 우위

### 사용자 통찰

> **"네가 정말 방어력을 높이고 싶다면, 단순 cascade delete 가 아니라 'enterprise memory lifecycle semantics' 를 강화해야 한다. 자메스가 'Enterprise Graph Memory Lifecycle Architecture' 를 먼저 잘 구현하면, 특허보다 훨씬 강한 영향력이 생긴다."**

### 이중 전략

| 트랙 | 목적 | 효과 |
|---|---|---|
| **특허 portfolio** | 법적 보호 + 자산화 | 침해 시 enforcement, M&A 시 valuation |
| **Reference architecture** | 시장 표준 정의 + 영향력 | 시장 정의 + 학술 인용 + adoption |

→ **둘 다 필요**. 특허는 "법적 방패", reference architecture 는 "시장 권위".

### Reference Architecture 구현 권고

1. **공개 디자인 문서** — 5-layer architecture 백서 (현재 부분적)
2. **MIT 오픈소스 구현** — 자메스 자체가 reference impl (✅ 진행 중)
3. **학회·논문 발표** — Phase 1 ~ 2 의 결과를 RAG/KG 학회 (CIKM, ACL, ICML workshops)
4. **표준화 시도** — W3C, ISO 등에 reference architecture 제안 (장기)
5. **기업 협력** — early adopter 와 함께 lifecycle 운영 패턴 정착

→ MIT 오픈소스 + 학술 발표 = "지식 lifecycle 의 reference implementation 은 James" 라는 시장 인식.

---

## 7. 위험 관리

### 위험 1. **AI 업계 우회 속도 빠름**

vector DB, agent workflow, prompt orchestration 등 모두 우회 사례 다수.

**대응**: 
- 청구항 1, 4, 18 = effect-based 로 broaden (정식 전환 시)
- 표준 / 학술 발표 = 시장 인식 선점
- 6 영역 (T1-T6) 으로 portfolio depth 확보

### 위험 2. **Layer 4 영역 prior art 강함**

TMS (1980s), temporal graph DB, provenance-aware DB 등.

**대응**:
- 차별화 narrative — "RAG/KG 운영 특화" 강조
- 결합 청구 (cascade + temporal, cascade + contradiction) 로 신규성 확보

### 위험 3. **Phase 2 비용 (₩82,800 + 정식 전환 시 200만 원+)**

**대응**:
- Phase 2 6 stage 중 가장 강한 2 (T2, T6) 만 진행 권장 (최소)
- 사업화 진척 확인 후 추가 (T1, T3 등)
- 정식 전환은 D+330일 시점 사업화 검증 후

### 위험 4. **Effect equivalence 우회 발견**

**대응**:
- 청구항 18 (umbrella) 의 broad effect 청구
- Replayable audit graph (T5) 가 event-sourced 우산 흡수

---

## 8. 12개월 ~ 18개월 portfolio 일정 표

| 일자 | 작업 |
|---|---|
| 2026-05-21 | STAGE 1B 출원 ✅ |
| 2026-05~06 | STAGE 1A 출원 |
| 2026-06-16 | Show HN |
| 2026-07~12 | STAGE T1, T2 명세서 작성 (Layer 4 진입) |
| 2026-12 | STAGE T1, T2 임시 출원 |
| 2027-01~02 | STAGE T6 명세서 (causality chain) |
| 2027-03 | STAGE T6 임시 출원 |
| 2027-04 | STAGE 1B 정식 전환 결정 (사업화 진척 확인) |
| 2027-04~05 | STAGE 1B 정식 전환 시 effect-based broaden (claims 1, 4, 18) |
| 2027-05-21 | STAGE 1B 정식 전환 마감 ⚠️ |
| 2027-05-21 | STAGE 1A 정식 전환 마감 (1A 도 진행 시) |
| 2027-06~09 | STAGE T3-T5 추가 출원 검토 |
| 2027 Q4 | Phase 3 시작 검토 |
| 2027-11 | STAGE 1B KIPRIS 자동 공개 |
| 2028~ | Phase 3, 국제 PCT 등 |

---

## 9. ROI 분석 — Phase 1 + 2

### 누적 비용 (개인 70% 감면)

| 항목 | 비용 |
|---|---|
| Phase 1 임시 출원 (1B + 1A) | ₩27,600 |
| Phase 2 임시 출원 (T1-T6) | ₩82,800 |
| **임시 출원 누적** | **₩110,400** |
| Phase 1 정식 전환 (선별 1~2건) | ₩125만 ~ ₩250만 |
| Phase 2 정식 전환 (선별 2~3건) | ₩250만 ~ ₩375만 |
| **정식 전환 누적 (선별)** | **₩375만 ~ ₩625만** |

### 가치

| 시나리오 | IP 가치 (추정) |
|---|---|
| 사업화 X | 우선일 확보 + defensive publication = ₩0 ~ ₩100만 (옵션 가치) |
| 사업화 진행 (SaaS / API) | IP 자산 → 투자·라이센싱 협상력 = ₩5,000만 ~ ₩수억 |
| M&A 시 | IP portfolio valuation = ₩수억 ~ ₩수십억 |

→ ROI 는 **사업화 진척에 비례**. 임시 출원만으로도 우선일 확보 ROI 양호.

---

## 10. 결론 — 정직한 권고

### 즉시 (2026)
- ✅ STAGE 1B 완료 (실행됨)
- ⏳ STAGE 1A 진행 (대기 중)
- 📋 **본 roadmap commit + 리뷰** (이번 commit)

### 단기 (2026 Q4 ~ 2027 Q1)
- 사업화 / 사용자 추이 모니터링
- STAGE T1 (Temporal Validity), T2 (Contradiction) 명세서 초안 작성 시작
- Show HN 후 반응 확인

### 중기 (2027 Q1 ~ Q2)
- STAGE T1, T2 임시 출원
- STAGE 1B 정식 전환 결정 + 변리사 자문

### 장기 (2027~2028)
- T3-T6 추가 출원 검토
- Phase 3 (Layer 5) 진입

### 핵심 원칙

1. **각 stage 단독으로는 약함** → portfolio 결합으로 강함
2. **Implementation 청구는 우회됨** → effect-based broader 청구 필수
3. **법적 IP 와 reference architecture 둘 다** → MIT 오픈소스 + 학회 발표 병행
4. **사업화 진척에 맞춰** → 정식 전환 / 확장 결정

---

**End of Patent Portfolio Roadmap.**

본 문서는 자메스의 18~24개월 patent portfolio 전략. STAGE 1B 단독이 아닌 **"Enterprise Graph Memory Lifecycle Architecture"** reference 로 묶는 vision.
