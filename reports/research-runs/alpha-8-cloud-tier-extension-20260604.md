# α-8 Cloud Tier Extension — Stage 5 Analysis Report (2026-06-04)

> **Status: closure (잠정 verdict)**. Direction α "cloud로 reasoning 천장 풀린다"
> 전제 measurement results — **multihop_rag fair fixture에서 미입증**.
> Magnitude tiny (Δ ~0.04), n=1 caveat. 결정 = Direction α 재검토 trigger,
> S6/S7 보류, cloud-tier 인프라 (S0-S5c) 는 보존.

## 0. TL;DR

| 비교 | Δ graded | n | valid? |
|---|---:|---:|---|
| Cloud + JAMES vs Local + JAMES (evidence-grounded, fair) | **−0.037** | 1 (Run 1만 valid) | ✅ |
| Cloud raw vs Local raw (둘 다 no evidence) | -0.016 | 1 each | ⚠️ leak suspect (Claude 학습-지식 confound) |
| Reasoning-isolated v2 (gold evidence + LLM judge) | 0 (9/9 vs 9/9) | 9Q | ✅ but easy first-N caveat |

**Direction α 전제 verdict**: **3 측정 모두 cloud가 reasoning 천장을 풀어주지 못함**. 단 magnitude tiny + caveat 많음. 다음 cycle 진입 비용 효익 약함.

## 1. 측정 history (이번 cycle, 2026-06-03~04)

| Stage | 무엇 | 결과 / 상태 |
|---|---|---|
| S0~S5c (cloud tier build) | abstraction module + runner + synth wire + bug fix | 8 PRs (#697-#704) closed |
| Stage 1 (design memo) | M_CLOUD tier 통합 설계 | PR #705 merged |
| Stage 2 (matrix runner code) | `_TIER_BACKEND_OVERRIDE` + cost guard | PR #706, 17 tests |
| Stage 3 (step7 smoke) | wiring 검증 (cloud + audit + bench output) | wiring ✅. quality는 verdict-grade fixture 아님 |
| Stage 4 (multihop n=3 paired) | 진짜 verdict 측정 시도 | **Max-plan 토큰 rate-limit으로 Run 2 partial / Run 3 fully boilerplate**. Run 1만 valid (99/100). |
| Stage 4b (C_minus M_CLOUD n=1) | "JAMES 거두기" 사용자 가설 검증 시도 | **invalid** — evidence 없는데 fixture가 Claude 학습 분포 leak (메모리 `feedback_evidence_grounded_validity_check`) |

## 2. Valid 데이터 — Stage 4 Run 1만

(Stage 4 Run 1: 99/100 valid answers, 1 timeout, multihop_rag 100Q)

| Axis | C_rag-ontology × M_CLOUD (Run 1) | C_rag-ontology × M_M (n=3 paired baseline) | Δ |
|---|---:|---:|---:|
| path_coverage | 0.3636 | 0.4111 | **−0.048** (outside M_M noise ±0.008, 6x) |
| **graded_answer** | **0.290** | **0.327** | **−0.037** (outside M_M noise ±0.017, 2x) |
| abstention_f1 | 0.474 | 0.429 | +0.045 (inside M_M noise ±0.10) |
| token_cost | 1479 | 1584 | −105 |
| latency_cost | 39.8s | 29.5s | +10.3s |

**해석**:
- graded -0.037, path -0.048 = cloud + JAMES (evidence-grounded) 가 local + JAMES을 **OUTSIDE noise but tiny magnitude** 로 못 이김
- abstention_f1는 cloud가 +0.045 (inside band) — cloud의 abstain 정책이 약간 더 신중
- latency +10.3s = cloud는 같은 evidence에서 3.5배 느림 (29s → 40s)
- token -105 = cloud가 약간 짧게 답 (concise)

## 3. Invalid 데이터 — Stage 4b (보존, 결과 인용 금지)

C_minus × M_CLOUD × N=1:
- sources=0, graph_paths=0 (RAG 자체 disabled = evidence 안 전달)
- Cloud는 자체 학습 지식으로 답 (Sam Bankman-Fried, Trump, Sam Altman 등 실명 직답)
- multihop_rag fixture = 2023 뉴스 = Claude 학습 분포 leak 거의 확실
- graded 0.347은 "cloud reasoning power" 아니라 "cloud 학습 지식 recall"

→ Stage 4b 결과는 cell JSON에 남겨두지만 **Direction α verdict 자료로 사용 금지**. 메모리 `feedback_evidence_grounded_validity_check` 박힘.

## 4. Direction α 전제 평가 — 3 측정 종합

| 측정 | 측정 design | Δ (cloud − local) | valid? |
|---|---|---:|---|
| v2 reasoning-isolated (`local_vs_cloud_multihop.py`) | gold evidence + LLM judge, 9Q | 0 (9/9 vs 9/9) | ✅ but easy first-N caveat |
| Stage 4 Run 1 (fair evidence-grounded) | JAMES pipeline 동등, multihop 99Q | −0.037 graded | ✅ but n=1 |
| Stage 4b (cloud raw) | no evidence + leak fixture | (−0.057 reported, **invalid**) | ❌ |

**3 측정 모두 "cloud가 천장 풀어준다" 신호 없음:**
- v2: 둘 다 9/9 → 차이 0
- Stage 4 Run 1: cloud +-0 또는 약간 못함
- Stage 4b: invalid (cloud 학습 지식 leak)

= **Direction α 핵심 전제 (cloud reasoning ceiling 가설) 측정상 미입증**. Magnitude tiny + n=1 caveat라 "강한 반증"은 아니지만, "큰 양의 Δ"가 데이터에서 보이지 않음. 추가 측정이 이를 뒤집을 가능성 작음.

## 5. JAMES pipeline의 sector progression (참고 — M_M baseline)

(이번 cycle 데이터 아님, α-8 closure data 메모리)

| Sector | M_M graded | Δ vs C_minus |
|---|---:|---:|
| C_minus | 0.363 (n=1) | baseline |
| C_rag-basic | 0.327 (n=1) | -0.036 |
| C_rag-graph | 0.300 (n=3) | -0.063 |
| C_rag-ontology | 0.327 (n=3) | -0.036 |
| C_rag-full | 0.337 (n=1) | -0.026 |

= **JAMES pipeline 추가가 graded answer를 약화시킴** (학계 기지 "RAG often hurts capable LLM" 패턴 — Pinecone 2024 등 `feedback_alpha6_findings_mostly_known_to_literature` 메모리). 단 path coverage / citation / abstention 신중도는 JAMES가 보장.

**이 fact는 사용자 가설 (JAMES가 cloud에 부담) 의 부분 supporting evidence** — M_M에서도 같은 패턴이므로 cloud에서도 가능성 높음. 그러나 **fair 검증은 leak-controlled fixture 필요** (다음 cycle 후보).

## 6. 운영방식 — JAMES 정체성 vs cloud trade-off

| 모드 | graded | 추적성 (pipeline) | LLM internal reasoning | JAMES 정체성 |
|---|---|---|---|---|
| Local + JAMES (현 production) | 0.327 (baseline) | ✅ 완전 | black-box (어떤 LLM이든) | 보존 |
| Cloud + JAMES (S5 wire, evidence-grounded) | 0.290 (Δ -0.037) | ✅ 완전 + egress audit | black-box | 보존 |
| Cloud raw (no JAMES) | (측정 invalid) | ❌ pipeline 없음 | black-box | 손상 (citation/abstention 없음) |
| Hybrid (evidence curator + cloud raw + post-validate) | TBD | 부분 (evidence/citation only) | black-box | 부분 양립 |

**핵심 정리**: LLM internal reasoning chain은 **어떤 모델이든 black-box** (산업 공통 한계). JAMES는 "pipeline 단위 추적" 보장하지 "LLM 내부 추적" 보장 안 함. cloud 사용 시 input/output/decision 차원 audit는 보존, citation/abstention 손상 trade-off.

## 7. Caveats (honest framing 의무)

- **n=1**: 모든 valid 측정이 n=1. `feedback_n1_verdict_inflation_n3_caught` 룰 위반. n=3 paired confirm 안 됐음.
- **magnitude tiny**: Δ -0.037 graded는 M_M noise band 2배지만 small. noise band 자체가 0.017로 작아 statistical significance 약함.
- **Max-plan rate-limit**: Stage 4 N=3 시도가 토큰 소진으로 invalid 됐음. fair n=3 측정은 quota 분산 + 시간 두고만 가능 (별도 cycle).
- **multihop_rag = 영어 only**: 한국어 측면 미측정 (step7 한국어 fixture는 verdict-grade 아님).
- **Cloud model = Opus 4.7 1M + Haiku 4.5 (보조)**: default `claude -p` 사용. 다른 cloud LLM (GPT-4 / Gemini) 비교 안 됨.
- **학계 기지**: "RAG hurts capable LLM"은 Pinecone 2024 / Semantic Invariance 2026 등에서 알려진 패턴. 자메스만의 발견 X (`feedback_alpha_cycle_discovery_loop_end` 룰).

## 8. 결정 — Direction α 재검토

**Direction α premise** (= cloud로 reasoning 천장 풀린다) 는 이번 cycle에서 **측정상 미입증**. magnitude tiny + n=1 caveat로 강한 반증은 아니지만, "큰 양의 Δ" 신호 없음.

| 의사결정 | 결과 |
|---|---|
| Cloud tier 인프라 (S0-S5c, 8 PR) | **보존** — 라이브 wire 동작 검증됨. 미래 다른 cloud LLM 또는 다른 fixture에서 재활용 가능 |
| S6 (난이도 라우터) | **무기한 보류** — measurement-driven 설계인데 cloud 가치 자체 미입증으로 design data 약함 |
| S7 (full egress masking) | **무기한 보류** — 같은 이유 + 현 fixture에 PII 없음 |
| Stage 4 n=3 paired 재시도 | **선택 사항** — quota 분산 (시간 두고) 필요, magnitude 작아 verdict 뒤집을 가능성 낮음 |
| **다음 cycle 후보** | **mother platform 강화 / v0.5 도메인 pilot** 으로 redirection. cloud-tier는 backlog |

**Forced discovery hunt END** 룰 (`feedback_alpha_cycle_discovery_loop_end`) 그대로 적용. Direction α 자체가 forced discovery 였을 가능성 — premise가 학계 기지 ("frontier cloud > local 7B")의 잘못된 적용이었음. JAMES setting에서는 production gemma4:e4b이 이미 충분히 강함.

## 9. 다음 작업 큐 (재정렬)

1. **Stage 6 — memory + briefing 갱신** (직접 후속): `project_direction_alpha_local_vs_cloud_quality_thread` 정정 / `project_direction_alpha_cloud_tier_build_state` 종결 / CLAUDE.md briefing Direction α 종결 + 다음 anchor
2. **B 묶음 housekeeping** (병렬 가능): router.py 20KB ceiling split / v2 script deprecate / MEMORY.md cleanup / pre-existing test failures fix
3. **Ali resume 2026-06-07** anchor (외부 일정)
4. **v0.5 domain pilot launch decision** (장기) — enterprise internal knowledge ontology 후보

## 10. 측정-side 룰 박힌 ledger (이번 cycle, 5 catch)

| # | 사용자 catch | 룰 박힘 |
|---|---|---|
| 1 | "같은 9Q paired 또 돌리자" 제안 | `feedback_methodological_chain_before_plan` |
| 2 | fixture upgrade만 제안 (matrix infra 무시) | 같은 룰 |
| 3 | step7 → multihop 거꾸로 측정 순서 | `feedback_fixture_fitness_before_verdict` + methodological chain |
| 4 | step7 결과 over-read | `feedback_fixture_fitness_before_verdict` |
| 5 | Stage 4b evidence 전달 + 모델 catch | `feedback_evidence_grounded_validity_check` (본 cycle 추가) |

다음 cycle 진입 시 5 룰 모두 의무 reading.
