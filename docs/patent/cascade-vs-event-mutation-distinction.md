# CASCADE vs EVENT — Mutation Type 분리

> **작성일**: 2026-05-21
> **목적**: 자메스 lifecycle architecture 의 핵심 분리 — destructive mutation (CASCADE) vs semantic evolution (EVENT). Patent strategy 핵심 narrative.
>
> **사용자 비판 시리즈 5회 반영**: "CASCADE 와 EVENT 를 분리해서 보는 건 굉장히 중요하다. 많은 시스템이 이걸 섞어서 망가진다."

---

## 0. 한 줄 요약

> **"지식 그래프 mutation 에는 두 종류가 있다 — 무효화 (CASCADE) 와 진화 (EVENT). 둘을 섞으면 contradiction 폭발 / stale retrieval / hallucination. 분리하면 lifecycle 명확."**

---

## 1. 두 종류의 Knowledge — 핵심 분리

### A. Invalidated Knowledge (CASCADE 영역)

**정의**: 완전히 무효화된 지식. 처음부터 잘못됐거나 철회됐음.

**예시**:
- 잘못 업로드된 문서
- 철회된 보고서
- 오탈자 정정 (예: "Joby" → "JoeBy" 잘못 추출)
- 삭제된 증거
- Ingestion 오류 (LLM hallucination 추출)

**처리**: **CASCADE** — provenance invalidation propagation

**철학**: "이 source 가 contribute 한 것은 모두 잘못됐다. 제거 필요."

### B. Superseded Knowledge (EVENT 영역)

**정의**: 과거에는 맞았으나 시간이 지나 최신 상태가 바뀜.

**예시**:
- CEO 교체 (Alice → Bob)
- 정책 변경 (가격, 약관)
- 계약 종료
- 조직 개편
- 시장 상황 변화

**처리**: **EVENT/TEMPORAL** — supersession chain

**철학**: "과거에는 맞았다. 다만 시점이 달라졌다. 과거를 지우지 말고 versioning."

---

## 2. 잘못된 처리의 위험 — Naive RAG 의 문제

### 시나리오 — CEO 교체

**과거 보고서 (2024-01)**:
> "Joby 의 CEO 는 Alice 다."

**최신 보고서 (2026-05)**:
> "Joby 의 CEO 는 Bob 이다."

### Naive 처리들

#### ❌ 방식 1: Append-only (대부분 RAG)
```
KG:
  Joby CEO Alice (conf 0.9)
  Joby CEO Bob   (conf 0.9)
```
→ **두 fact 동시 존재** → retrieval 시 contradiction → hallucination

#### ❌ 방식 2: Overwrite (단순 mutation)
```
KG:
  Joby CEO Bob (Alice 삭제)
```
→ "2024년 당시 Joby CEO 는?" 질문에 답할 수 없음 → historical replay 불가

#### ❌ 방식 3: CASCADE-only (Alice 를 잘못된 정보로 처리)
```
- "Alice CEO 보고서" 도 함께 삭제 시도
- 또는 Alice CEO 사실을 cascade 로 제거
```
→ Alice 가 **틀린 게 아닌** 데 cascade. **forensic 불가**, "왜 그때 그렇게 판단했나" 답변 불가.

### ✅ 올바른 처리 — CASCADE / EVENT 분리

```yaml
edge_001:
  subject: Joby
  predicate: CEO
  object: Alice
  validity: {from: "2024-01", to: "2026-04"}
  status: {active: false, superseded_by: "edge_002"}
  mutation_type: "superseded"   # ← EVENT 영역
  sources: [report_2024Q1.pdf]

edge_002:
  subject: Joby
  predicate: CEO
  object: Bob
  validity: {from: "2026-05", to: null}   # 무기한 (현재)
  status: {active: true}
  mutation_type: "active"
  sources: [report_2026Q2.pdf]
```

→ **시간 변화 = EVENT**. **잘못된 source = CASCADE**. **둘은 다르다.**

---

## 3. CASCADE 영역의 정확한 정의 (재포지셔닝)

### 기존 STAGE 1B 청구의 broad 표현
> "출처 문서가 추가·삭제·수정될 때 cascade"

### 재포지셔닝 (narrow + defensible)
> **"Provenance invalidation propagation — 기반 증거가 무효화됐을 때 그 영향을 deterministic 으로 전파하는 시스템."**

### 처리 대상 (CASCADE only)

| 트리거 | CASCADE 동작 |
|---|---|
| 잘못 업로드된 문서 삭제 | source.doc_id 매칭 → sources 에서 제거 → confidence 재계산 |
| 철회된 보고서 | 동일 |
| 오탈자 정정 후 재업로드 | Phase D modify cascade (diff) |
| Ingestion 오류 (LLM 잘못 추출) | source 제거 |

### CASCADE 가 처리하지 않는 것 (EVENT 영역)

| 트리거 | EVENT 동작 (별도 layer) |
|---|---|
| CEO 교체 | edge 의 validity.to 설정 + 새 edge 추가 (superseded_by chain) |
| 정책 변경 | 동일 — temporal transition |
| 계약 종료 | validity.to + status.active=false |
| 시장 변화 | 새 fact event + 기존 fact 의 status update |

---

## 4. 새 Data Model — mutation_type 필드 추가

### Sources schema (CASCADE 영역)
```yaml
sources:
  - doc_id: "report_Q1.pdf"
    weight: 0.7
    role: "extract"
    ts: "2026-04-01"
    mutation_type: "active"  # active | invalidated | retracted
```

### Edge schema (CASCADE + EVENT 통합)
```yaml
edge:
  subject: Joby
  predicate: CEO
  object: Alice
  
  # CASCADE 영역 (provenance)
  sources: [...]
  confidence: 0.9  # derived from sources (noisy-OR)
  
  # EVENT 영역 (temporal)
  validity:
    from: "2024-01"     # 언제부터 참
    to: "2026-04"       # 언제까지 참 (null = 무기한)
  status:
    active: false        # 현재 활성 여부
    superseded_by: "edge_002"   # 대체된 edge ID
  
  # 통합 mutation type
  mutation_type: 
    - "active"           # CASCADE/EVENT 모두 활성
    - "invalidated"      # CASCADE: source 무효 → 제거
    - "retracted"        # CASCADE: source 자체 철회
    - "superseded"       # EVENT: 새 fact 가 대체
    - "expired"          # EVENT: validity.to 경과
```

---

## 5. 의사결정 트리 — 어떤 처리 적용?

```
이벤트 발생
   │
   ├── 발생 유형이 "source 자체의 신뢰성 문제"?
   │       (잘못 업로드, 철회, 오탈자 등)
   │       │
   │       └── YES → CASCADE 처리
   │                ├── source 제거 (doc_id 매칭)
   │                ├── confidence 재계산 (noisy-OR)
   │                ├── orphan entity sweep
   │                └── audit log: type=invalidation
   │
   └── 발생 유형이 "세상의 변화 / 시간 흐름"?
           (CEO 교체, 정책 변경, 계약 종료 등)
           │
           └── YES → EVENT 처리
                   ├── 기존 edge: validity.to 설정
                   ├── 기존 edge: status.active=false
                   ├── 기존 edge: superseded_by 설정
                   ├── 새 edge 생성: validity.from = 현재
                   ├── 새 edge 생성: status.active=true
                   └── audit log: type=supersession + chain
```

---

## 6. 두 영역의 공존 — 자메스 아키텍처

### Layer 3a — CASCADE Engine (Memory OS — Provenance)

- **목적**: provenance invalidation propagation
- **트리거**: source 자체의 무효화 (잘못된 doc, 철회 등)
- **메커니즘**: doc_id-based cascade, role-based immunity
- **현재**: STAGE 1B 출원 완료 ✅

### Layer 3b — EVENT Engine (Memory OS — Evolution)

- **목적**: temporal transition + supersession chain
- **트리거**: 세상의 변화 (시간 흐름, 새 사실 등장)
- **메커니즘**: validity windows, supersession links, mutation_type
- **상태**: 미구현 (v0.4 + 신규 patent 영역 ⭐)

### 두 layer 의 협력

```
새 문서 ingestion
   │
   ├── LLM 추출 → (s, p, o) triples
   │
   ├── 동일 (s, p) 의 기존 edge 존재?
   │
   │   ├── YES → Contradiction Detection (Layer 4 T2)
   │   │         │
   │   │         ├── 동일 source 가 다른 o 주장?
   │   │         │   → CASCADE: 기존 source 의 fact 무효화
   │   │         │
   │   │         └── 새 source 가 다른 o 주장?
   │   │             → EVENT: supersession chain (기존 status=superseded)
   │   │                + 새 edge 추가
   │   │
   │   └── NO → Cross-doc aggregation (Layer 3a/STAGE 1B)
   │            → sources append, confidence noisy-OR
   │
   └── Audit log: 결정 추적
```

→ CASCADE 와 EVENT 는 같은 트리거에서 분기. 어느 쪽으로 갈지 결정하는 게 contradiction detection (Layer 4 T2) 의 역할.

---

## 7. Patent Strategy 함의

### 7.1 STAGE 1B 청구 재포지셔닝

**기존 narrative (broad, 우회 가능)**:
> "지식 그래프의 mutation lifecycle 관리"

**재포지셔닝 (narrow, 강함)**:
> **"Provenance invalidation propagation — source 가 무효화될 때 영향을 deterministic 으로 정리. Semantic evolution (시간 흐름에 의한 supersession) 과는 다른 영역."**

이렇게 narrow 하면:
- ✅ Event-sourcing 우회 차단 (event 는 evolution 영역, 우리는 invalidation)
- ✅ TMS / temporal graph 와 명확 구분 (시간 차원 X, provenance 차원)
- ✅ Defensible — specific 메커니즘 (doc_id-based + role immunity)

### 7.2 STAGE 1B 정식 전환 시 claim 표현

#### Claim 1 (재 narrow)

```
청구항 1 (재포지셔닝):

지식 그래프 시스템에서 source 의 신뢰성이 무효화되었을 때
(invalidation event — 잘못 업로드된 문서 삭제, 철회된 보고서 등),
그 source 가 contribute 한 관계의 신뢰도를 deterministic 으로 정리하는
방법으로서:
(a) 각 관계가 source-attributed weight 집합을 유지하는 단계;
(b) 무효화 event 발생 시 영향 받은 sources 에서 해당 항목을
    제거하는 단계 (단, 인간 입력 source 는 면역);
(c) 신뢰도를 closed-form 으로 재계산하는 단계;
(d) sources 가 빈 관계는 그래프에서 제거하는 단계;
(e) 본 방법은 'temporal supersession' (시간 흐름에 의한 fact 진화) 과는
    구분되어, source invalidation 에 한정됨;
을 포함하는 것을 특징으로 하는 방법.
```

→ "**invalidation 에 한정**" 명시 = scope narrow + 동시에 unique scope 보호.

### 7.3 신규 Patent 영역 — EVENT Engine

EVENT Engine 은 STAGE 1B 와 **별도 patent** 영역:

**제안 명칭**: STAGE T7 — Temporal Supersession Chain (Event Evolution Engine)

핵심 청구:
- `validity.from/to` 필드를 활용한 temporal scope
- `superseded_by` chain 으로 과거 fact 보존 + 현재 fact 우선
- LLM 미사용 deterministic supersession decision
- Historical replay (특정 시점의 graph 재구성)

이 영역은 자메스 portfolio 의 **추가 patent territory**.

---

## 8. 자메스 Lifecycle Architecture 의 격상

### Before (사용자 비판 전)
- Layer 3 = "CASCADE Engine"
- 단일 mutation system
- Event-sourcing 과의 차별점 모호

### After (사용자 비판 5회 반영)
- **Layer 3a = CASCADE Engine** (provenance invalidation propagation)
- **Layer 3b = EVENT Engine** (temporal supersession chain)
- 두 layer 가 **공존 + 협력**
- Patent portfolio: STAGE 1B (3a) + STAGE T7 (3b) = 2 stage

### 효과

1. **Patent 영역 명확** — 두 layer 각각 specific 청구
2. **차별화 명확** — event-sourcing 의 "evolution" 과 우리의 "invalidation" 구분
3. **Forensic 가능** — historical replay (3b) + invalidation audit (3a) 둘 다
4. **시장 narrative 정밀** — "lifecycle management" 가 아니라 **"distinguishing invalidation from supersession"**

---

## 9. 구현 우선순위 — 자메스 코드 트랙

### v0.3 (현재) — Layer 3a CASCADE
- ✅ 구현 완료 (`core/cascade.py`, `core/relations_schema.py`)
- ✅ STAGE 1B 출원 완료

### v0.4 — Layer 3b EVENT Engine (신규)
- 새 작업: edge schema 에 `validity`, `status`, `superseded_by` 필드 추가
- 새 작업: supersession decision logic (deterministic)
- 새 작업: historical replay engine
- 출원: STAGE T7 (신규 patent area)

### v0.4 — Layer 4 (기존 계획)
- T1 (Temporal Validity) — EVENT 영역으로 재분류
- T2 (Contradiction Arbitration) — CASCADE/EVENT 분기 결정 role
- T3 (Evidence Aging) — EVENT 영역
- T4 (Reviewer Authority) — CASCADE governance
- T5 (Replayable Audit) — 둘 다 지원
- T6 (Causality Chain) — CASCADE 영역

### v0.5 — Layer 5 (Agent)
- 기존 계획대로

---

## 10. 결론 — 자메스의 핵심 IP narrative

### 한 줄 정리

> **"CASCADE 는 'semantic evolution' 이 아니라 'provenance invalidation propagation' 에 특화된 deterministic mutation system. EVENT 와 공존."**

### Patent strategy 변화

| 항목 | Before | After |
|---|---|---|
| STAGE 1B scope | Broad lifecycle | **Narrow invalidation propagation** |
| 차별화 | Event sourcing 과 비교 모호 | **Invalidation vs Evolution 분리 명확** |
| Portfolio 깊이 | Layer 3 단일 | **Layer 3a + 3b 분리** |
| 미래 출원 영역 | Layer 4 (T1-T6) 만 | **+ Layer 3b (Event Engine)** |
| 차별화 narrative | "Mutation-aware lifecycle" | **"Invalidation-specific + Evolution-coexistent"** |

### Reference Architecture 의 핵심

```
┌─────────────────────────────────────────┐
│ Layer 3b: EVENT Engine                   │ ← NEW 패턴
│ - Temporal supersession chain            │
│ - validity windows                       │
│ - Historical replay                      │
├─────────────────────────────────────────┤
│ Layer 3a: CASCADE Engine ⭐ STAGE 1B     │
│ - Provenance invalidation propagation    │
│ - Source-based cleanup                   │
│ - Manual immunity                        │
└─────────────────────────────────────────┘
```

→ 두 layer 가 같은 trigger event 에서 분기하되, **각자 다른 mutation semantic** 처리.

---

## 11. 미래 세션 / 변리사 자문 시 참조

본 문서는 자메스의 **lifecycle management 의 핵심 분리** 정의. 다음 시점에 활용:

### 정식 전환 (2027-04 ~ 05)
- STAGE 1B claim 1 narrow 표현 정정 (provenance invalidation propagation)
- claim 18 (umbrella) 의 broad scope 도 invalidation 으로 한정

### Phase 2 신규 출원
- STAGE T7 (Event Engine) 신규 출원 검토
- T1-T6 의 Layer 재배치 적용

### 학회·논문
- "Distinguishing Invalidation from Supersession in Knowledge Graph Lifecycle"
- 새로운 framing

### 외부 발표
- Show HN 본문: "CASCADE 와 EVENT 의 분리"
- 투자자 deck: 핵심 차별점 narrative

---

**End of CASCADE vs EVENT Mutation Type Distinction.**

본 분리는 자메스 lifecycle architecture 의 **결정적 framing**. 사용자 비판 5회 시리즈의 종합 통찰이 도달한 architectural 명확화.
