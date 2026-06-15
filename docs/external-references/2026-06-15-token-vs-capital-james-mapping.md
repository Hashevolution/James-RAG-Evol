# 외부 글 "토큰 자본 vs 사람 자본 + 학습 루프" → 자메스 구조 정합 검토

> **목적**: 2026-06-15 사용자 공유 글이 자메스의 근본 design intent
> 와 얼마나 정합한지 정직 매핑. 원문 raw quote 는 `docs/internal/
> external-references/2026-06-15-token-vs-capital-zenith-style.md`
> (`.gitignore` 차단, local only — 원작자 동의 절차 미진행).
>
> **결론 한 줄**: 글의 7가지 핵심 주장 중 **4가지는 자메스가 이미
> mechanism 으로 ship** (Replayable RAG / 모델 갈아입어도 노하우
> 유지 / audit-native lifecycle / 사람-운전석). **2가지는 구조적
> hook 은 있으나 메커니즘 미흡** (회사-자체 평가 / 학습 루프 복리).
> **1가지는 자메스가 의도적으로 거부** (모델을 회사 내부에서 직접
> 강화학습으로 단련) — Rule #3 self-evolution 4-Gate 와 충돌하는
> 영역이라 정직 framing 으로 차이 인정.

## 7가지 주장 ↔ 자메스 매핑 표

| # | 글의 주장 | 자메스 매핑 | 정합도 |
|---|---|---|---|
| **A** | 사람 자본 + 토큰 자본 두 축 (글 §3) | 자메스 = **사람-운전석 mother platform**. operator (사람 자본) 가 워크스페이스 / 양식 / 권한을 결정, 자메스 (토큰 자본 인프라) 가 retrieve / synth / audit | 🟢 STRONG |
| **B** | 사람은 AI 에 밀려나는 게 아니라 AI 를 끌고 가는 운전석 (글 §4) | Rule #3 self-evolution opt-in + 4-Gate human approval / Change Review Workspace / approval_evidence (G2.a) / Patch Pipeline 4-Gate | 🟢 STRONG |
| **C** | 모델은 바꿔도 노하우는 남는 구조 (글 §6) | **워크스페이스 격리** (`JAMES_WORKSPACE`) + **#922 LLM Routing 통합** (모델은 admin Settings 에서 토글, 워크스페이스 자료 / audit_log / wiki entity 는 분리). gemma3:4b → mxtral → claude 갈아입어도 자메스 안의 313+ entity / chroma 인덱스 / supersede chain 그대로 | 🟢 STRONG (#922 가 정확히 이 자리) |
| **D** | 회사가 만드는 일과 같이 흘러간 가공된 기록으로 모델 단련 (글 §7) | **Replayable RAG** = `reconstruct_graph_at(t)` (T5) + audit_log append-only + Time-Travel Dashboard (TT.a-d). 모델을 직접 학습시키진 않으나, **모델에 *흘러간 기록을 통째로 컨텍스트로 흘려보내는* RAG retrieval** 이 그 자리. | 🟡 부분 STRONG — 단, "강화학습 환경" 이라는 글의 표현은 RL 까지 의미. 자메스는 RL 안 함 (Rule #3 충돌). 정직 framing. |
| **E** | 학습 루프가 복리로 불어난다 — 두 곡선이 비대칭 차이 (글 §8) | 🔴→🟡 정합 hook 있으나 mechanism 미흡: workspace 자료가 누적될수록 RAG 컨텍스트가 풍부해짐 (한쪽 곡선) + 본인 dogfooding 으로 양식/지시 사이클이 개선됨 (다른 쪽 곡선). 단 **자동으로 모델을 갱신하는 RL 곡선은 없음**. 측정 인프라 (RAB / LRB) 가 복리 효과 측정 가능하나 자동 강화는 없음 | 🟡 PARTIAL — 의식적 결정. Phase E `run_shell` 도 아직 자가 학습 안 됨 |
| **F** | 회사가 직접 정하는 결과로 모델을 자체 평가 (글 §7) — 외부 벤치 아니라 | 🟡 부분: 자메스의 **RAB / LRB / QVT** 는 *내부* 정의 metric (audit-replayable, time-valid retrieval). 그러나 동시에 `cycle_gamma_musique_graph_build.py` 등 *외부 벤치 (RGB / MuSiQue / 2Wiki / ALCE)* 도 사용 — 자메스가 외부 벤치도 동시에 사용 중. **회사-자체 평가** 의 자리는 customer pilot 의 **"6-month uptime + customer attestation"** (PLATFORM_READINESS §3 Gate v1.0 Dim F) 이 직접 대응 — 단 아직 evidence 0. | 🟡 STRUCTURAL hook 만 |
| **G** | 산업이 소수 모델에 가치 다 바치면 정치공학 문제 (글 §9) — 세계화 1막 아웃소싱 비유 (글 §10) | 자메스의 **local-first / on-prem / 데이터 외부 송신 없음** 정체성 정확히 이 risk 회피. README 의 "Cloud-default OpenAI/Anthropic 호출 매 retrieval" 비교 표가 그 framing. Direction α cloud-tier 는 *premise 미입증* 으로 보류 = 의식적으로 cloud 의존 안 만듦 | 🟢 STRONG — 자메스 정체성 명시적으로 이 자리 |

## 자메스 *이미 ship* 된 mechanism (정합 강한 자리)

### 1. Replayable RAG (audit-native lifecycle)

- `core/lifecycle/*` Layer 4 T1–T7 + `reconstruct_graph_at(t)` T5 primitive
- RAB v0.1.1 (2026-06-10 DOI `10.5281/zenodo.20625533`) 가 측정 ship
- 글 §6 "회사 베타랭이가 사라지지 않는다" 의 가장 정확한 mechanism

### 2. 워크스페이스 격리 + LLM Routing 통합 (#917 + #922)

- 모델 토글은 admin Settings UI, 워크스페이스 자료 (313+ entity / chroma /
  audit) 는 그대로
- 글 §6 "모델은 바꿔도 노하우는 남는 구조" 의 정확한 mechanism
- **단** Risk #3 (#923 mitigation 에서 catch) — `llm_settings`
  table 이 global 인 점은 인지 필요

### 3. 사람-운전석 (Rule #3 self-evolution opt-in)

- Patch Pipeline 4-Gate (feedback → candidate → eval → **human
  approval** → deploy → rollback)
- v0.5 G2.a `approval_evidence` primitive + Change Review Workspace
  (CR.a-d) UI
- 글 §4 "사람은 AI 에 밀려나는 게 아니라 AI 를 끌고 가는
  운전석으로 올라간다" 의 정확한 mechanism

### 4. Local-first / 데이터 외부 송신 없음

- README 첫 페이지 차별점 표
- `core/abstraction/` §5.7.12 cloud egress trust zone — 사용 시
  명시적 opt-in + 마스킹
- #923 Risk #2 catch (anthropic backend 의 §5.7.12 우회) 가 정확히
  이 contract 보호
- 글 §9–§10 의 정치공학·세계화 1막 비유에서 회피하려는 자리

## 자메스 *structural hook 만* 있는 자리 (메커니즘 보완 후보)

### 5. 학습 루프 복리 (글 §8) — 측정만, 자동 갱신 없음

- 현재: RAB / LRB / QVT 가 두 곡선 *측정* 은 가능. 그러나 *자동
  강화* 는 없음
- 자메스 정체성 (Rule #3) 과 의도적 충돌 — *human approval gate
  생략한 self-evolution 금지* 가 자메스 핵심 안전망
- 보완 후보 (의식적 결정):
  - 자동 retrieve 컨텍스트 풍부도 측정 (workspace 누적 자료 ↔ RAG
    hit rate)
  - operator 의 양식/지시 (USER GUIDANCE, #916) 누적이 다음 양식
    적용 품질에 영향 측정
  - 단 LLM 자동 fine-tune 은 의식적으로 회피

### 6. 회사 자체 평가 metric (글 §7) — 외부 벤치 동시 사용

- 현재: 자메스 *내부* metric (RAB AC/RF/PC, LRB R@1 V<N<J,
  graph_paths, abstention_f1) + *외부* metric (RGB / MuSiQue / 2Wiki
  / ALCE 일부)
- "회사가 직접 정하는 결과로 평가" 의 정확한 자리 = customer pilot
  의 *6-month uptime + customer attestation* (PLATFORM_READINESS Dim F).
  현재 **evidence 0** (v0.5→v0.6 gate 미통과)
- 본인 dogfooding (Stream A.3) 이 Dim F 의 첫 evidence 가 됨

### 7. 강화학습 환경 (글 §7) — 의도적으로 거부

- 글의 표현: "회사가 만드는 일과 같이 흘러간 가공된 기록으로
  모델을 단련시키는 강화학습 환경이 필요하다"
- 자메스 입장: **fine-tune / RLHF 안 함**. Rule #3 self-evolution
  의 4-Gate 가 그것을 막음. 모델은 *컨텍스트 RAG* 로 자메스 자료에
  접근하나 weights 는 안 바꿈
- 정직 framing: **자메스는 강화학습 환경을 제공하지 않는다.
  audit-native + replayable + operator-approved** 가 자메스가
  선택한 대안. 글의 주장과 가장 큰 차이 — 의식적 결정

## 정합 종합 점수

| 차원 | 자메스 정합 |
|---|---|
| 두 자본 구조 (사람 + 토큰) | 🟢 정합 |
| 모델 바꿔도 노하우 남음 | 🟢 정합 (#922 가 정확히 이 자리) |
| 사람 운전석 | 🟢 정합 (4-Gate) |
| Local-first / 가치 갖다 바치지 않음 | 🟢 정합 (mother platform 정체성) |
| 학습 루프 복리 | 🟡 측정 가능, 자동 강화 X (의도된 결정) |
| 회사 자체 평가 | 🟡 hook 만 — customer pilot evidence 0 |
| 강화학습 환경 | 🔴 의식적 거부 — Rule #3 와 충돌 |

**정직 framing**: 7개 중 4개 STRONG, 2개 PARTIAL (의도된 결정 +
evidence 부족), 1개 의식적 거부.

## 다음 자연 단계

1. **Phase 4 dogfooding doc 작성 시 이 매핑 참고**: 본인 evidence
   가 Dim F + "회사 자체 평가" 첫 자리를 채움
2. **글 §5 (학습 루프) 측정**: 자메스 안에 *"이 워크스페이스의 1주
   동안 RAG hit 비율 변화"* 같은 메트릭 surfacing 후보 — 단 자동
   강화 없이 측정만
3. **글 §10 (세계화 1막 비유)**: Phase 6 외부 outreach 시 자메스의
   *왜 local-first 인가* 의 정확한 framing 으로 차용 가능 — 단
   외부-facing doc verification first 룰 (#888/#889) 적용

## 위반·갱신 여부

- **자메스의 기존 design intent 를 깨뜨리지 않음**. 글이 제안하는
  방향 4개는 이미 ship, 2개는 partial (의도된 한계), 1개는 의식적
  거부 (Rule #3)
- **새 architecture PR 후보로 격상되는 자리 없음**. 글이 dogfooding
  evidence 의 *framing 도구* 로 활용 가능

## References

- 글 원문: `docs/external-references/2026-06-15-token-vs-capital-zenith-style.md`
- `docs/PLATFORM_READINESS.md` Dim F (Production proof)
- `docs/ARCHITECTURE.md` §5.7.12 (cloud egress) / §5.7.15 (agent tools)
  / §5.7.16 (LLM routing unification)
- `core/lifecycle/` Layer 4 T1–T7
- `eval/rab/SPEC-v0.1.md` RAB
- `papers/lrb-preprint/main.pdf` LRB
- `memory/feedback_jameses_positioning_replayable_rag.md` — Replayable
  RAG = 자메스의 한 특성, 전체 정체성은 mother platform
