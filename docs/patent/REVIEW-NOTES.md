# 특허 검색·검토 노트

> 본 문서는 James-RAG-Evol 특허 출원 작업 중 수행한 **선행기술 검색·분석·청구 가능성 검토·법규 검토** 결과를 복붙용으로 정리한 문서입니다.
> 절차적 진행 상황은 `HANDOVER.md`, 전략·일정은 `strategy.md`를 보십시오. 본 문서는 **판단·분석 결과만** 압축 정리합니다.
> 작성일: 2026-05-10 / 메인 정합 정정 반영: 2026-05-10
>
> **주요 정정 (메인 브랜치 대조 결과)**:
> - `core/memory_loom.py` → `core/memory/loom.py` (v0.2 패키지 리팩토링)
> - `core/jepa_adapter.py` → `core/query_expander.py` (JEPA는 misnomer였음, v0.2 리네임)
> - 본 문서의 "JEPA-Lite" 표현은 청구항·실시예에서 "키워드 동의어 기반 질의 확장기"로 교체 필요
> - PR #139 (Doc-source gate): **메인 머지 완료** (commit `371838c`)
> - PR #67/97/138 (Observability): **Phase 1 구현 완료, 메인 머지** — `core/observability.py` ~245줄
> - `core/security_layer.py`: 본 분기 라인 169-389 → 메인 라인 시프트 (`cross_stage_abac_verify` ≈ 249, `mask_sensitive` ≈ 339, `filter_answer_by_role` ≈ 363, `pre_check` ≈ 409)

---

## 1. 후보별 선행기술 분석 + 회피 결론

각 후보에 대해 (a) 어떤 선행기술이 있는지, (b) 본 발명이 어떻게 회피하는지, (c) 점수 산정 근거를 정리.

### #0 Umbrella Architecture (3/5 조건부)

**선행기술**:
- LangChain, LlamaIndex, PrivateGPT, Verba, R2R, Ollama+graphRAG — OSS 다수가 "Local LLM + KG + Entity Extraction + Memory" 조합 구현
- 추상적 추론 단계 시퀀스만 나열 시 "추상적 아이디어"로 거절 가능

**회피 조건**: 청구항에 James 고유 5개 specific feature를 모두 명시
1. 키워드 동의어 기반 질의 확장기 (구 명칭 JEPA-Lite — 실제로 Joint-Embedding Predictive Architecture 미구현, v0.2에서 `query_expander.py`로 리네임) (LLM-free 50토큰·3초 timeout)
2. 5-gate Memory Loom
3. Hybrid score (60/20/20) + ontology-weighted DFS depth=4
4. 7-type feedback + decay 0.9 + threshold ±2.0
5. 2-stage cross-stage ABAC verification

**판단**: 단독 출원 비추천. STAGE 1 (Memory Loom)과 결합하여 시스템 청구항 + Memory Loom 종속항 구조로 출원. Umbrella가 거절돼도 종속항 살아남으므로 손해 없음.

### #1 Memory Loom 5-gate (4/5 ⭐)

**선행기술**:
- Wikidata, ConceptNet — confidence threshold만 단일 사용
- Microsoft GraphRAG — 메모리 검증 게이트 단순 (confidence 기반)

**차별점**:
- **5개 게이트의 순차 적용** + **각 거부 사유 분리 audit log**
- write rate 제한 (3/session) 으로 saturation 방지
- conflict detection: 동일 entity+relation의 tail 불일치 또는 confidence 차이 0.3 초과

**판단**: 단독 출원 강함. 4/5.

### #2 Feedback Shadow (2/5)

**선행기술**:
- OpenAI ChatGPT, Anthropic Claude — RLHF는 학습 단계, 운영 단계 즉시 학습 부재
- LangChain memory, ChatGPT Custom Instructions — 단일 발화로 즉시 저장, 누적 검증 부재
- 일반적인 "score accumulation + threshold" 패턴은 흔함

**차별점 (좁힌 청구로 한정)**:
- **(mode, query_topic_hash) hash-keyed direction identifier** — 무관 주제 간 누설 방지
- **0.9 decay × ±2.0 threshold** specific 수치
- **7-type signal + 패턴 매칭 검출** specific 사전

**판단**: 좁힌 청구로 별건 출원. 점수 2/5.

### #3 2-stage Security + ABAC (2/5)

**선행기술**:
- 일반적인 RBAC/ABAC — 다수 시스템 구현
- prompt injection 검출 — Garak, NeMo Guardrails 등 다수 시스템 보유
- PII 마스킹 — Microsoft Presidio 등

**차별점 (좁힌 청구)**:
- **Cross-stage ABAC verification** — Vector·Graph·Output 3단계 동일 정책 일관성 사후 검증
- **키워드+값 함께 마스킹** (예: "급여: 5000만원" 전체 치환)
- **External 역할의 person entity 이름 마스킹** (graph + wiki 양쪽)
- **admin도 차단되는 prompt injection 정책**

**판단**: "3-stage" 표현 빼고 "input + output 2-stage + cross-stage verification"으로 좁혀 출원. ⚠️ "graph traversal per-hop role gating"은 미구현 → 청구 제외 필수.

### #4 Trait Pair Auto-rebalance (2/5)

**선행기술**:
- ChatGPT Custom Instructions, Character.AI — trait 독립 변수
- 일반 슬라이더 UI — 무수히 많음
- "opposing trait" 개념 자체는 게임 RPG 등에서 흔함

**차별점**:
- **Sum=1.0 invariant 강제** + **자동 재조정** — 한 trait X → opposing trait 1−X 자동
- **4 pair + 3 독립 trait 혼합** 시스템
- **0.7 / 0.3 threshold prompt directive 자동 생성** — 운영자 instruction 불필요

**판단**: 좁게 청구. 점수 2/5.

### #5 Hybrid RAG Paradigm (1/5)

**선행기술 광범위**:
- Vector + BM25 + Keyword hybrid: Weaviate, Elasticsearch, Pinecone, OpenSearch (2020년 이전부터)
- Graph context expansion: Microsoft GraphRAG, RAG-Fusion, KGAT, KGQA 다수 논문
- "쿼리 그래프 변환 단계 없음" 같은 부재(negative limitation)는 청구항으로 인정 약함

**판단**: **별건 출원 비추천**. STAGE 1의 시스템 청구항 + #1/#3 종속항에 specific 구성요소만 흡수 (키워드 동의어 기반 질의 확장기 (구 명칭 JEPA-Lite — 실제로 Joint-Embedding Predictive Architecture 미구현, v0.2에서 `query_expander.py`로 리네임) hard cap, ontology weight×confidence DFS).

### A. Doc-source 출처 게이트 (3/5 ⭐)

**선행기술**:
- Microsoft GraphRAG, RAG-Fusion, KGAT — "source provenance asymmetry"를 traversal gate로 쓰는 발명 없음
- 일반 graph traversal에서 metadata 필터링은 흔하지만, **언급 vs 출처의 비대칭성** 활용은 신규

**차별점**:
- **"문서 D가 엔티티 E를 언급한다" ≠ "D가 E의 출처"** 비대칭 통찰
- E.sources에 D 포함된 경우만 doc→entity hop 유효
- 정방향 (doc→entity) 에만 게이트 적용, 역방향 (entity→doc) 은 미적용 — asymmetric

**판단**: 별건 출원. 검증된 효과 (Palantir → 비트코인 spurious path 차단, baseline 12/13 query 보존). 3/5.

### B. Provenance Cascade + Log-sum (4/5 ⭐⭐ 최강)

**선행기술**:
- Wikidata, ConceptNet — relation에 단일 confidence 스칼라
- KG temporal change 논문 — "다중 출처가 사라질 때 어떻게 derived knowledge가 변하는가" 구체 메커니즘 부재
- Microsoft GraphRAG, LlamaIndex — cascade 메커니즘 자체 부재
- 확률론적 OR (`1 - Π(1 - p_i)`) 자체는 confidence fusion에서 흔히 사용. 그러나 **provenance cascade와 결합한 monotone delete cascade** 발명은 부재

**차별점**:
- **B-1**: confidence = 1 − Π(1−w_i) — 출처 추가/제거에 항상 strict 단조성 보장 (max·mean 공식은 보장 안 됨)
- **B-2**: 파일 삭제 → 모든 relation의 sources에서 doc_id 제거 → confidence 재계산 → sources 비면 relation 삭제 (cascade)
- **role: manual** source는 cascade 면역 — 인간 개입의 영속성
- **diff cascade** — 파일 수정 시 (subject, predicate, object) triple 단위 diff로 surgical update

**판단**: 미구현이지만 명세 완성도 최상. v0.3 본 구현 진행 중 → 자연 누설 위험 → **가장 빠르게 출원해 우선일 확보 필수** (1순위). 4/5 ⭐⭐.

### C. Bench-gated Self-Evolution + Byte-Identical Rollback (3/5 ⭐)

**선행기술**:
- AutoML, NAS, Self-RAG, AutoGPT — "더 좋은 모델"을 만드는 데 집중. "안전 배포 메커니즘" 자체 발명 드뭄
- 일반 CI/CD — rollback은 흔하지만 mid-write crash 시뮬레이션 + SHA-256 byte-identical 검증은 드뭄
- Approver_username 누락 시 deploy 거부하는 audit invariant 발명 부재

**차별점**:
- **4-Gate Patch Validation**: static check (eval/exec 등 11개) + PROTECTED_FILES + 회귀 테스트 95%↑ + security bypass 패턴 (pre_check=lambda...True 등 7개)
- **3-조건 안전 배포**: bench-pass + 인간 approver_username + byte-identical rollback
- **mid-write crash 50% 지점 SIGKILL 시뮬레이션** 통과 SHA-256 invariant

**판단**: 별건 출원. 4-gate validator는 실제 구현됨 (`tools/patch/patch_validator.py`). 3/5.

### D. Trace Correlation via ContextVar (2/5)

**선행기술**:
- OpenTelemetry, Datadog APM, Jaeger — trace를 사후 분석용으로 사용
- ChatGPT 류 LLM UI — timer-based 애니메이션 또는 SSE/WebSocket streaming
- 일반적인 ContextVar 사용은 흔함

**차별점**:
- **클라이언트 사전 송신 trace_id** + **race-free pre-response polling** — 서버 응답 전부터 stage event polling 가능
- ContextVar 즉시 초기화로 race-free 보장
- REST polling만으로 동작 (WebSocket·SSE 불필요)

**판단**: 단독 가치 낮음 (2/5). 좁혀 별건 또는 STAGE 1/1B 종속항으로 흡수 검토.

---

## 2. 한국 특허법 핵심 사실 (검토 결과)

| 항목 | 내용 |
|------|------|
| 공지예외 grace period | 12개월 (특허법 30조 1항) — 발명자가 직접 공개한 경우 |
| 임시명세서 | 구현 완료 요구 없음, 청구항 형식 강제 없음, 자유 서술 가능 |
| 정식 출원 전환 | 임시 출원 후 12개월 내 정식 전환 안 하면 자동 취하 (회수 불가) |
| 개인 감면 | 70% (개인 출원인 또는 소기업) → 6만원 → 1.8만원 |
| 시스템 청구 가능 | 다단계 모듈 협력 시스템 청구항 인정 (KIPO) |
| 방법 청구 가능 | 단계 시퀀스 방법 청구항 인정 (KIPO) |
| AI 발명 patentable | KIPO 2021 「인공지능 발명 심사 가이드라인」에서 명시 인정 |
| broad claim 위험 | 추상적 아이디어 단순 나열은 거절 — specific feature 명시 필요 |
| 출원 사이트 | **특허로 (patent.go.kr)** |
| 검색 사이트 | KIPRIS (kipris.or.kr) — 출원 불가, 검색 전용 |
| 정식 전환 비용 | 변리사 자문 20~50만원 + 정식 출원료 약 200만원/건 |
| 미국·PCT 진출 | 번역료 100~200만원/건 추가 |

---

## 3. KIPO AI 발명 심사 가이드라인 적용 검토

KIPO 2021 가이드라인에 따라 AI 추론 프로세스는 다음 조건에서 patentable:

1. **기술적 효과** 존재 — 단순 수학·알고리즘 아닌 시스템 작동에 기여
2. **구체적 구현** — 추상적 아이디어가 아닌 모듈·데이터흐름·임계값 등 구체 한정
3. **재현 가능성** — 통상의 기술자가 재현 가능한 수준의 기재

본 8건 모두 위 조건 충족 가능:
- Memory Loom: 게이트 임계값 0.75/0.3 등 구체
- 키워드 동의어 기반 질의 확장기 (구 명칭 JEPA-Lite — 실제로 Joint-Embedding Predictive Architecture 미구현, v0.2에서 `query_expander.py`로 리네임): 50토큰·3초 hard cap 구체
- Cascade: log-sum 공식·diff cascade 구체
- 이외 모두 코드 인용 또는 의사코드로 구현 명시

---

## 4. 청구 제외 사항 (미구현 → 청구하면 무효 위험)

다음 항목들은 strategy.md/skeleton에 **언급 금지** 또는 **종속항으로만** 표현해야 한다:

| 항목 | 사유 | 영향 받는 stage |
|------|------|----------------|
| "3-stage security" 표현 | 실제로는 2-stage (graph traversal stage 미구현) | STAGE 3 |
| graph traversal per-hop role gating | 미구현 | STAGE 3 |
| Cascade의 실제 production 구현 | 미구현 (설계 메모만 존재) | STAGE 1B |
| ~~Doc-source gate PR #139~~ | **메인 머지 완료** (commit `371838c`) — 미머지 표기 정정됨 | STAGE 1A |
| Self-Evolution PR #69/77/78/79 머지 | 일부 미머지 — commit hash 확인 필요 | STAGE 4A |
| ~~Trace Correlation PR #67/97 머지 안 됨~~ | **Phase 1 구현 완료** (PR #67/97/138, `core/observability.py` ~245줄 메인 머지) | STAGE 4B |
| "opponent mechanics" 표현 | 너무 broad, 게임 도메인 선행기술 | STAGE 4 (좁혀서 sum-invariant만) |

⚠️ 미구현 항목도 임시명세서는 출원 가능하지만, 청구항이 너무 broad하면 정식 전환 시 신규성 검증에서 거절 위험. **구체적 수치·알고리즘·예시로 한정**하는 게 안전.

---

## 5. 비용 산정 근거 (검토 결과)

| 항목 | 단가 | 출원 8건 합계 |
|------|------|---------------|
| 임시명세서 출원료 (개인 정상) | 6만원 | 48만원 |
| 임시명세서 출원료 (개인 70% 감면) | 1.8만원 | **14.4만원** |
| 부대 비용 (공동인증서 등) | 약 1만원 | 1만원 |
| **8건 임시 출원 합계 (감면 적용)** | — | **약 15만원** |
| (선택) 정식 전환 1건 | 200만원 | — |
| (선택) 변리사 자문 1건 | 20~50만원 | — |
| (선택) 미국·PCT 번역 1건 | 100~200만원 | — |

미니멀 시나리오 (STAGE 1 + 1B 두 건) = 약 4만원 (감면) ~ 12만원 (정상).

---

## 6. 청구항 구조 검토 — Umbrella 위험·완화

**검토 결과**: STAGE 1의 Umbrella system claim은 broad해서 신규성 거절 위험이 있다. 그러나 **dependent claim 구조로 완화 가능**.

구조:
```
Independent Claim 1 (System):    [거절 위험: 신규성 약함]
    엔티티 추출 + 검색 + 그래프 + Memory Loom + Feedback + ABAC + Profile
Independent Claim 2 (Method):    [거절 위험: 동일]
    단계 1~7 sequence
Dependent Claim 3~10 (Memory Loom 세부):  [신규성 거의 확실]
    5-gate 각 임계값, 거부 사유, audit log
```

거절 시나리오 분석:
- Claim 1, 2 거절 → Claim 3~10 살아남음 → Memory Loom 부분만 보호
- Claim 3~10 거절은 거의 불가 (구체 수치·로직 구체적)
- 결론: Umbrella 시도해도 **손해 없음**

---

## 7. 사이트 구분 검토 (혼동 주의)

| 사이트 | URL | 용도 | 비고 |
|--------|-----|------|------|
| **특허로 (PATENTRO)** | `patent.go.kr` | 실제 출원·심사·등록 | 회원가입 + KEAPS 설치 + 공동/금융 인증서 |
| KIPRIS | `kipris.or.kr` | 선행기술 검색 전용 | 출원 불가 |
| 특허청 (KIPO) | `kipo.go.kr` | 안내·정책 | 출원 직접 불가 |

⚠️ 처음 작성한 strategy/plan에서 "KIPRIS 가입" 표현이 있었으나 정정 완료 (commit `eb8a625`).

---

## 8. 핵심 코드/PR 참조 매핑

### 구현 완료 (코드 인용 가능)

| 모듈 | 경로·라인 | 사용 stage |
|------|-----------|-----------|
| Memory Loom 5-gate | `core/memory/loom.py (v0.2 패키지 리팩토링; 구 `core/memory_loom.py`):80-149` | STAGE 1 |
| Memory Loom 자가 테스트 | `core/memory/loom.py (v0.2 패키지 리팩토링; 구 `core/memory_loom.py`):200-267` | STAGE 1 §8 |
| 키워드 동의어 기반 질의 확장기 (구 명칭 JEPA-Lite — 실제로 Joint-Embedding Predictive Architecture 미구현, v0.2에서 `query_expander.py`로 리네임) expand | `core/query_expander.py (구 `core/jepa_adapter.py`):88-157` | STAGE 1 §9.1 |
| 키워드 동의어 기반 질의 확장기 (구 명칭 JEPA-Lite — 실제로 Joint-Embedding Predictive Architecture 미구현, v0.2에서 `query_expander.py`로 리네임) 사전 | `core/query_expander.py (구 `core/jepa_adapter.py`):28-53` | STAGE 1 §9.1 |
| Graph DFS | `core/graph_engine.py:220-307` | STAGE 1 §9.3, STAGE 1A |
| Ontology 가중치 | `core/ontology.py:11-29` | STAGE 1 청구항 9 |
| Feedback signal 사전 | `core/feedback_engine.py:35-43` | STAGE 2 |
| Feedback accumulate | `core/feedback_engine.py:107-151` | STAGE 2 |
| Security pre_check | `core/security_layer.py:323-362` | STAGE 3 |
| Security mask | `core/security_layer.py:253-275` | STAGE 3 |
| Security filter_by_role | `core/security_layer.py:277-316` | STAGE 3 |
| Cross-stage ABAC | `core/security_layer.py:169-224` | STAGE 3 |
| Trait 정의 | `core/character_profile.py:17-29` | STAGE 4 |
| Trait set + rebalance | `core/character_profile.py:55-66` | STAGE 4 |
| Trait prompt modifier | `core/character_profile.py:68-97` | STAGE 4 |
| 4-Gate Patch Validator | `tools/patch/patch_validator.py:69-209` | STAGE 4A |

### 미구현 (설계 메모 또는 미머지 PR — 임시명세서로만 출원 가능)

| 항목 | 출처 | 사용 stage |
|------|------|-----------|
| Doc-source `_doc_outgoing_hop_valid` | PR #139 (**메인 머지 완료**, commit `371838c`) | STAGE 1A |
| Cascade 설계 메모 | `docs/design/v0.3-knowledge-cascade.md` (~430줄) | STAGE 1B |
| Self-Evolution rollback | PR #78 (미머지) | STAGE 4A |
| Self-Evolution audit endpoint | PR #79 (미머지) | STAGE 4A |
| Trace Correlation observability | **PR #67/97/138 메인 머지 완료** — Phase 1 (uuid7 trace_id + contextvars 전파, 245줄) 구현 완료 | STAGE 4B |

---

## 9. 검토에서 도출된 주요 결정 (요약)

1. **시나리오 C (전부 8건 출원)** 채택 — 보호 범위 최대화
2. **STAGE 1B (Cascade) 1순위** — 점수 4/5 ⭐⭐ + 자연 누설 위험
3. **STAGE 1 격상** — Memory Loom 단독 → Umbrella + Memory Loom 결합
4. **Hybrid RAG (#5) 별건 안 함** — 선행기술 풍부, 종속항으로만 흡수
5. **Cross-stage ABAC만 청구** — graph per-hop role gating은 미구현이라 제외
6. **출원은 특허로** — KIPRIS 혼동 정정
7. **임시 → 정식 전환 결정은 D+330일** — 사업화 진척에 따라

---

## 10. 새 세션에서 복사용

새 세션에서 검토 결과만 빠르게 파악하려면 다음 프롬프트:

```
James-RAG-Evol 특허 출원의 선행기술 검토·청구 분석 결과는 다음 파일에 정리되어 있습니다:
docs/patent/REVIEW-NOTES.md

이 파일을 먼저 읽고, 다음 작업을 진행해주세요:
[구체 요청]

전체 진행 상황은 docs/patent/HANDOVER.md 참조.
작업 브랜치: claude/security-audit-LRxjo
```

---

**End of Review Notes.**
