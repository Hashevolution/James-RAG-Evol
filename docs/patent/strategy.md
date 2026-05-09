# James-RAG-Evol 특허 출원 전략 (DIY)

> 본 문서는 한국 특허청(KIPO) 임시명세서 출원을 통해 James-RAG-Evol의 핵심 기술에 대한 우선일을 확보하기 위한 전략 문서입니다.
> 작성일: 2026-05-09 / 변리사 비용 없이 발명자 직접 출원 기준

## 1. 배경

- **공개일**: 2026-05-05 (GitHub public 첫 commit, 라이선스 MIT)
- **공지예외 만료일**: 2027-05-04 (특허법 30조 1항, 12개월 grace period)
- **출원 마감**: 2027-05-04 까지 출원 완료해야 신규성 인정
- **선행기술 검토 결과**: Microsoft GraphRAG / LG QA Method / 한국 대학·대기업 KGQA 특허 모두 회피 (명백한 침해 신호 없음)

## 2. 출원 후보 종합 평가

| # | 후보 | 핵심 파일 | 점수 | 전략 |
|---|------|----------|------|------|
| 0 | **Umbrella Architecture** | `core/main.py`, `core/orchestrator.py` 등 | 3/5 (조건부) | STAGE 1에 흡수 |
| 1 | **Memory Loom 5-gate** | `core/memory_loom.py:80-149` | 4/5 ⭐ | STAGE 1 본체 |
| 2 | **Feedback Shadow** | `core/feedback_engine.py:35-151` | 2/5 | 좁힌 청구로 별건 |
| 3 | **2-stage Security + ABAC** | `core/security_layer.py:169-389` | 2/5 | 좁혀 별건 |
| 4 | **Trait Pair Auto-rebalance** | `core/character_profile.py:55-66` | 2/5 | 좁게 별건 |
| 5 | Hybrid RAG paradigm | `core/jepa_adapter.py`, `core/graph_engine.py:220-307` | 1/5 | 별건 ❌, #0/#1/#3 종속항 흡수 |

## 3. Umbrella(시스템 전체) 출원 가능성

### 3.1 한국법상 인정 범위
- 시스템 청구항: A 모듈 + B 모듈이 특정 데이터 흐름으로 협력하는 시스템 (KIPO 인정)
- 방법 청구항: 추론 단계 시퀀스 (KIPO 인정)
- KIPO 2021 「인공지능 발명 심사 가이드라인」: AI 추론 프로세스 patentable

### 3.2 broad claim의 거절 위험
"Local LLM + KG + Entity Extraction + Memory" 자체 조합은 LangChain, LlamaIndex, PrivateGPT, Verba, R2R, Ollama+graphRAG 등 OSS가 모두 구현. 추상적 추론 단계만 나열하면 "추상적 아이디어"로 거절.

### 3.3 통과 조건 — James 고유 5개 specific feature 명시
1. **JEPA-Lite**: LLM-free 키워드 확장 + 50토큰 hard cap + 3초 timeout (`core/jepa_adapter.py`)
2. **5-gate Memory Loom** (`core/memory_loom.py:80-149`)
3. **Hybrid score** (Vector 60% + BM25 20% + Keyword 20%) + ontology-weighted DFS depth=4 (`core/graph_engine.py:220-307`)
4. **7-type feedback signal** + decay 0.9 + threshold ±2.0 (`core/feedback_engine.py:35-151`)
5. **2-stage cross-stage ABAC verification** (`core/security_layer.py:169-389`)

이 5가지를 모두 포함한 시스템 청구항이라면 신규성 인정 가능성 60% 이상.

## 4. 단계별 진행 (DIY)

### STAGE 0 — 사전 준비 (D+0~3일)

⚠️ **사이트 구분** (자주 혼동):
| 사이트 | URL | 용도 |
|---|---|---|
| **특허로 (PATENTRO)** | `patent.go.kr` | ✅ 출원·심사·등록 (실제 출원 사이트) |
| KIPRIS | `kipris.or.kr` | 선행기술 검색 전용 (출원 불가) |

- [x] disclosure_log.txt 생성 → `docs/patent/disclosure_log.txt`
- [ ] **특허로 (patent.go.kr)** 회원가입 + 본인인증 + 출원인 코드 부여
- [ ] 통합전자출원 SW (KEAPS) 설치 (Windows 권장, macOS 지원 제한적)
- [ ] 공동인증서 또는 금융인증서 등록
- [ ] 공지예외 적용 신청서 양식 다운로드 (특허로 → "민원서식 → 공지예외 적용 주장 신청서")
- [ ] (참고) KIPRIS 가입은 STAGE 5 모니터링 시점에 진행해도 됨

### STAGE 1 — Umbrella + Memory Loom 결합 출원 (D+4~14일, ★)
- 명세서 20~30쪽
- 도면 2매 (시스템 아키텍처 + 5게이트 흐름도)
- Independent Claim 1 (System) + Claim 2 (Method) + Dependent Claims 3~10 (Memory Loom)
- 비용: 6만원 (개인 감면 시 1.8만원)
- 템플릿: `docs/patent/stage1-spec-skeleton.md`

### STAGE 2 — Feedback Shadow 별건 출원 (D+15~21일)
- 청구 한정: "session-scoped accumulator with hash-keyed direction identifier"
- 비용: 6만원

### STAGE 3 — Security 2-stage + ABAC 별건 출원 (D+22~28일)
- ⚠️ "graph traversal per-hop role gating"은 미구현이므로 청구 제외
- 비용: 6만원

### STAGE 4 — Trait Pair Auto-rebalance 별건 출원 (D+29~35일)
- 청구 한정: "paired sum-invariant + threshold prompt directive"
- 비용: 6만원

### STAGE 5 — 1년 모니터링 (D+36~D+360일)
- 분기 1회 KIPRIS(`kipris.or.kr`) 재검색 (경쟁사 출원 추적)
- 비용 0원

### STAGE 6 — 정식 전환 결정 (D+330~D+360일)
| 조건 | 액션 |
|------|------|
| 사업화/투자 진행 | 변리사 자문 → 정식 전환 (200만원/건) |
| 우선일만 유지 | Memory Loom 1건만 정식 전환 |
| 가치 없음 | 자동 취하 |

⚠️ 1년 내 정식 전환 안 하면 자동 취하.

## 5. 총 비용 (1년 차)

| 항목 | 비용 |
|------|------|
| 임시 출원 4건 | 24만원 |
| 개인 감면(70%) | 약 7.2만원 |
| 부대 비용 | 약 1만원 |
| **합계** | **약 8~25만원** |
| (선택) 정식 전환 1건 | 약 200만원 |

## 6. 리스크

1. 청구항 작성 미숙으로 보호 범위 좁아짐 → 정식 전환 시 변리사 도움
2. 명세서 부실로 거절 → 코드 인용·도면 충실히
3. 미국·PCT 진출 시 번역료 (건당 100~200만원)
4. 12개월 카운트다운: 2027-05-04 까지
5. Umbrella claim 거절 시 → dependent claim(Memory Loom) 살아남음, 손해 없음

## 7. 핵심 파일 모음

- `core/memory_loom.py:80-149, 200-267` — Memory Loom 5-gate
- `core/feedback_engine.py:35-43, 107-151, 241-250` — Feedback Shadow
- `core/security_layer.py:169-224, 277-316, 323-362, 382-389` — Security stages
- `core/character_profile.py:17-29, 55-66, 68-97` — Trait pairs
- `core/jepa_adapter.py` — JEPA-Lite
- `core/graph_engine.py:220-307` — Graph DFS
- `core/ontology.py` — Ontology 가중치
