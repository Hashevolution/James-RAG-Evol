# James-RAG-Evol 특허 출원 전략 (DIY)

> 본 문서는 한국 특허청(KIPO) 임시명세서 출원을 통해 James-RAG-Evol의 핵심 기술에 대한 우선일을 확보하기 위한 전략 문서입니다.
> 작성일: 2026-05-09 (초판) / **2026-05-10 보강** — 신규 후보 4건 (A/B/C/D) 추가
> 변리사 비용 없이 발명자 직접 출원 기준

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
| **A** | **Doc-source 출처 게이트 그래프 탐색** (PR #139, A5-D) | `core/graph_engine.py:_doc_outgoing_hop_valid` | **3/5** ⭐ | **STAGE 1A** 신규 — Memory Loom 종속항 또는 별건 |
| **B** | **Provenance Cascade + Log-sum Confidence** (v0.3 design) | `docs/design/v0.3-knowledge-cascade.md` | **4/5** ⭐⭐ | **STAGE 1B** 신규 — Memory Loom과 동급 본체 |
| **C** | **Bench-gated Self-Evolution + Byte-Identical Rollback** (PR #69/#77/#78) | `tools/patch/`, `scripts/bench.py --check` | **3/5** ⭐ | **STAGE 4A** 신규 — 별건 |
| **D** | **End-to-End Trace Correlation via ContextVar** (PR #67/#97) | `core/observability.py`, `frontend/static/chat.js:1346-1542` | 2/5 | **STAGE 4B** 신규 — 좁혀 별건 |

> ⚠️ 후보 A/B/C/D는 2026-05-10 평가에서 추가됨. 자세한 분석은 §2.5 참조.

## 2.5 신규 후보 (2026-05-10 평가 보강)

기존 5개 후보 외에, v0.2 사이클 + v0.3 설계 작업물을 재검토해 발견된 4개 추가 후보. 주요 출원 가치 평가.

### A. Doc-source 출처 게이트 그래프 탐색 (3/5)

**핵심 발명**: 그래프 traversal 시 문서 노드에서 엔티티 노드로의 hop은, **해당 엔티티의 `sources` 메타데이터에 그 문서가 포함된 경우만** 유효.

**비대칭성 통찰** (특허성의 핵심):
- 문서 D가 엔티티 E를 언급한다 ≠ 문서 D가 엔티티 E의 출처다
- `wiki_generator`는 doc→entity outbound edge에 `inferred:true` 플래그를 안 붙임 (entity→doc 측에는 붙음). 이 비대칭이 spurious path 생성의 근본 원인
- Sources 필드를 traversal 게이트로 활용해 cross-context entity가 만든 가짜 추론 path 차단

**검증된 효과**: Palantir → 비트코인 spurious path 실측 차단, STEP 7 baseline 12/13 query 보존 (낮은 부수 피해). 옵션 1(blanket inferred conf threshold)이 9/13 회귀로 폐기된 후 채택된 surgical 솔루션.

**선행기술 회피**: GraphRAG / RAG-Fusion / KGAT 등 어디서도 "source provenance asymmetry"를 traversal gate로 쓰는 발명 없음.

**청구항 스케치**: 문서 노드에서 엔티티 노드로의 그래프 traversal 중, 대상 엔티티의 source 메타데이터에 해당 문서가 포함되지 않으면 hop을 차단하는 방법 + 시스템.

### B. Provenance Cascade + Log-sum Confidence (4/5 ⭐⭐) — 최강 신규

**핵심 발명** — 두 부분:

**B-1. Confidence 도출 공식**
```
relation.sources = [{doc_id, weight, role, ts}, ...]
relation.confidence = 1 - Π(1 - w_i)        ← log-sum / probabilistic OR
```

다른 후보 공식과의 비교:
| 공식 | 삭제 시 변화 | 단조성 |
|---|---|---|
| `max(weights)` | 최대값 제거 시에만 감소 | ❌ |
| `mean(weights)` | 임의 변화 | ❌ |
| `log-sum (이 발명)` | **항상 strict하게 감소** | ✅ |

monotone cascade 의미가 보장되는 유일한 공식.

**B-2. Cascade 가능한 Cascade**
- 파일 삭제 → 모든 relation의 sources에서 doc_id 제거 → confidence 재계산 → sources 비면 relation 삭제
- 수동 편집(`role: manual`)은 cascade 면역 — 인간 개입의 영속성 보장
- 파일 수정 → extraction diff → 추가/제거된 triple만 surgical update

**선행기술 회피**: Wikidata, ConceptNet 등 confidence 단일 값. KG temporal change 논문은 있지만 "delete file → cascade through provenance with monotone math" 발명 없음. Microsoft GraphRAG / LlamaIndex 등 cascade 메커니즘 자체 부재.

**청구항 스케치**:
1. relation의 confidence를 출처 가중치 집합으로부터 log-sum 도출하는 방법
2. 출처 문서 삭제 시 단조성 보장 cascade로 derived knowledge를 정리하는 방법
3. 수동 편집 source는 cascade 면역으로 인간 개입을 영속화하는 방법

**미구현이지만 출원 가능**: 한국 임시명세서는 "구현 완료" 요구 없음. 명세 + 청구 + 실시예가 충분히 구체적이면 OK. `docs/design/v0.3-knowledge-cascade.md` (~430줄)이 이미 명세 수준. 임시명세서 skeleton: [`docs/patent/stage1b-cascade-spec-skeleton.md`](stage1b-cascade-spec-skeleton.md).

### C. Bench-gated Self-Evolution + Byte-Identical Rollback (3/5 ⭐)

**핵심 발명** — Self-improving AI 시스템의 안전 배포:
```
[feedback signal] → candidate patch → eval gate (bench --check)
                                    ↓ (pass)
                    [human approval (approver_username 필수)]
                                    ↓
                       deploy with rollback handle
                                    ↓ (post-deploy bench fail)
                       auto-rollback to byte-identical state
                                    ↓
                       audit DB: before/after metrics + approver +
                       approval_method + ROLLED_BACK event
```

**선행기술 회피**: AutoML / NAS / Self-RAG 등은 "더 좋은 모델"을 만드는 데 집중. **"안전하게 배포하는 시스템 메커니즘"** 자체에 대한 발명은 드뭄. 특히:
- byte-identical rollback under simulated mid-write crash 검증
- bench-as-gate 강제 (gate 없이 deploy 거부)
- approver_username 없으면 deploy 거부 → audit invariant

**청구항 스케치**: 자기 개선 AI 시스템에서, (1) 회귀 테스트 통과 + (2) 인간 approver 승인 + (3) 미달 시 byte-identical rollback이 모두 충족되어야만 배포가 허용되는 안전 배포 방법.

### D. End-to-End Trace Correlation via ContextVar (2/5)

**핵심 발명**:
- 서버 entry point에서 `trace_id` ContextVar 설정 → 모든 downstream 모듈이 동일 id로 stage event 기록
- 클라이언트가 client-supplied trace_id를 미리 보내고 즉시 `/trace/poll/{trace_id}` 폴링 → 서버 응답 도착 전에 stage event 보임
- UI 애니메이션이 timer-based가 아니라 **실제 서버 stage 진행에 동기화**

**선행기술 회피**: OpenTelemetry / Datadog 등은 trace를 사후 분석용으로 사용. **"실시간 클라이언트 UI 피드백을 위한 trace 폴링"** + **"client-pre-supplied trace_id로 race-free streaming"** 조합은 흔치 않음. 다만 점수 2/5로 단독 가치는 낮으며, 좁혀 별건 또는 #1/#0 종속항으로 흡수 권장.

**청구항 스케치**: 클라이언트가 사전 생성한 trace_id를 서버에 송신하고, 서버 응답을 기다리는 동안 동일 trace_id로 stage event를 폴링하여 UI를 실시간 동기화하는 방법.

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

### STAGE 1A — Doc-source 출처 게이트 출원 (D+10~17일, ⭐ 신규 2026-05-10)
- 청구 한정: "doc→entity hop validity via target's `sources` field"
- STAGE 1과 시간 겹치게 진행 — STAGE 1의 종속항으로 흡수도 가능 (변리사 전환 시점에 결정)
- 본 출원은 단독 임시명세서 형태 권장 — 청구 보호 범위가 명확히 다름
- 비용: 6만원 (개인 감면 시 1.8만원)
- 첫 commit: 2026-05-09 (PR #139) → grace period **2027-05-08**

### STAGE 1B — Provenance Cascade 출원 (D+15~28일, ⭐⭐ 신규 2026-05-10) — 최강 신규
- 명세서 25~35쪽 (cascade 알고리즘 + 도면 3매: schema 변화 / cascade flow / log-sum 곡선)
- Independent Claim 1 (Method - log-sum derivation) + Claim 2 (Method - cascade) + Claim 3 (System) + Dependent 4~12 (manual immunity, modify diff, etc.)
- 미구현이지만 `docs/design/v0.3-knowledge-cascade.md` (~430줄)이 이미 명세 수준 — 임시명세서 핵심 자료로 사용
- 템플릿: `docs/patent/stage1b-cascade-spec-skeleton.md`
- 비용: 6만원 (개인 감면 시 1.8만원)
- 첫 commit: 2026-05-09 (PR #145 design memo) → grace period **2027-05-08**
- ⚠️ v0.3 본 구현 시점까지 자연 누설 위험 — STAGE 1과 함께 진행해 우선일 확보 권장

### STAGE 2 — Feedback Shadow 별건 출원 (D+29~35일)
- 청구 한정: "session-scoped accumulator with hash-keyed direction identifier"
- 비용: 6만원

### STAGE 3 — Security 2-stage + ABAC 별건 출원 (D+36~42일)
- ⚠️ "graph traversal per-hop role gating"은 미구현이므로 청구 제외
- 비용: 6만원

### STAGE 4 — Trait Pair Auto-rebalance 별건 출원 (D+43~49일)
- 청구 한정: "paired sum-invariant + threshold prompt directive"
- 비용: 6만원

### STAGE 4A — Bench-gated Self-Evolution 출원 (D+50~63일, ⭐ 신규 2026-05-10)
- 청구 한정: "bench-pass + human approver + byte-identical rollback" 3-조건 안전 배포
- Independent Claim 1 (Method) + Claim 2 (System) + Dependent (audit invariants, mid-write crash recovery, ROLLED_BACK event)
- 비용: 6만원
- 첫 commit: 2026-05-04 (PR #69) → grace period **2027-05-03**

### STAGE 4B — Trace Correlation via ContextVar 출원 (D+64~70일, 신규 2026-05-10)
- 청구 한정: "client-supplied trace_id + race-free pre-response polling for UI sync"
- 점수 2/5 — 가치 낮으니 STAGE 1/1B 종속항 흡수도 검토 (시간/비용 부담 시 생략 가능)
- 비용: 6만원
- 첫 commit: 일자 확인 필요 (PR #67/#97)

### STAGE 5 — 1년 모니터링 (D+71~D+360일)
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

### 기존 4건 (STAGE 1/2/3/4)
| 항목 | 비용 |
|------|------|
| 임시 출원 4건 | 24만원 |
| 개인 감면(70%) | 약 7.2만원 |
| 부대 비용 | 약 1만원 |
| **소계** | **약 8~25만원** |

### 신규 4건 (STAGE 1A/1B/4A/4B — 2026-05-10 추가)
| 항목 | 비용 |
|------|------|
| 임시 출원 4건 | 24만원 |
| 개인 감면(70%) | 약 7.2만원 |
| **소계** | **약 7~24만원** |

### 종합
| 시나리오 | 합계 (1년차) |
|---|---|
| 핵심만 (STAGE 1 + 1B만 — Memory Loom + Cascade) | 약 4~12만원 |
| 모든 신규 + 핵심 (STAGE 1/1A/1B/4A) | 약 14~48만원 |
| 전부 (1/1A/1B/2/3/4/4A/4B) | 약 14~48만원 |
| (선택) 정식 전환 — 건당 | 약 200만원 |

> 💡 STAGE 4B는 점수 2/5라 비용 대비 가치가 낮음. 예산 압박 시 가장 먼저 생략.

## 6. 리스크

1. 청구항 작성 미숙으로 보호 범위 좁아짐 → 정식 전환 시 변리사 도움
2. 명세서 부실로 거절 → 코드 인용·도면 충실히
3. 미국·PCT 진출 시 번역료 (건당 100~200만원)
4. 12개월 카운트다운: 2027-05-04 까지
5. Umbrella claim 거절 시 → dependent claim(Memory Loom) 살아남음, 손해 없음

## 7. 핵심 파일 모음

### 기존 후보 (#1~#4)
- `core/memory_loom.py:80-149, 200-267` — Memory Loom 5-gate
- `core/feedback_engine.py:35-43, 107-151, 241-250` — Feedback Shadow
- `core/security_layer.py:169-224, 277-316, 323-362, 382-389` — Security stages
- `core/character_profile.py:17-29, 55-66, 68-97` — Trait pairs
- `core/jepa_adapter.py` — JEPA-Lite
- `core/graph_engine.py:220-307` — Graph DFS
- `core/ontology.py` — Ontology 가중치

### 신규 후보 (A/B/C/D — 2026-05-10 추가)
- **A**: `core/graph_engine.py:_doc_outgoing_hop_valid` (PR #139)
- **A**: `tests/test_a5d_doc_source_gate.py` — 14 unit tests (회피 증빙)
- **B**: `docs/design/v0.3-knowledge-cascade.md` (~430줄 설계 명세)
- **B**: `docs/patent/stage1b-cascade-spec-skeleton.md` — 임시명세서 skeleton
- **C**: `tools/patch/patch_extractor.py`, `patch_validator.py`, `patch_applier.py`
- **C**: `scripts/bench.py` (--check 모드 게이트), `eval/regression/step7_baseline.json`
- **C**: PR #69 (opt-in flag), #77 (eval gate), #78 (rollback), #79 (audit endpoint)
- **D**: `core/observability.py:start_trace, log_stage` — ContextVar 기반
- **D**: `frontend/static/chat.js:1346-1542` — 클라이언트 폴링 + UI 동기화
- **D**: `server_llmwiki.py` `/trace/poll/{trace_id}` endpoint

## 8. 공개 시점 / Grace Period 추적

| 후보 | 첫 commit / 공개 | Grace period 만료 | 출원 마감 |
|---|---|---|---|
| #0~#4 (기존) | 2026-05-05 | 2027-05-04 | STAGE 1/2/3/4 |
| **A** (Doc-source gate) | 2026-05-09 (PR #139) | **2027-05-08** | STAGE 1A |
| **B** (Cascade) | 2026-05-09 (PR #145 design memo) | **2027-05-08** | STAGE 1B |
| **C** (Self-Evolution) | 2026-05-04 (PR #69) | **2027-05-03** | STAGE 4A |
| **D** (Trace) | 일자 확인 필요 (PR #67/#97) | (확인 후 기재) | STAGE 4B |

> ⚠️ 모든 후보가 2027-05-04~08 안에 임시명세서 출원 필수. 늦으면 신규성 상실 → 거절.
