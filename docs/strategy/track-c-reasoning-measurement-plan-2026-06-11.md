# Track C — JAMES Reasoning Performance Measurement Plan (2026-06-11)

> **Purpose**: 자메스의 **추론 (reasoning) 성능**을 외부 공개 벤치
> 위에서 측정하여 객관적으로 인정받는 데이터를 산출하는 path.
>
> **Why this doc exists**: 사용자 catch (2026-06-11) — RAB은 audit
> 측정, LRB은 retrieval 측정. 둘 다 reasoning 측정 아님. "자메스
> 추론 성능 우수" 주장은 측정 evidence 없는 상태. 본 doc 은 그 evidence
> 를 만드는 step-by-step plan.
>
> **★ Honest disclaimer up front**: cycle γ 가 정적 multi-hop reasoning
> (RGB / MuSiQue / 2Wiki) 에서 JAMES = literature family 임을 측정.
> 본 Track C 가 reasoning 측정의 **모든** axis 에서 JAMES > literature
> 라는 결과를 약속하는 게 아님. **honest measurement first** —
> measurement-driven discovery (memory `feedback_james_identity_
> measurement_driven`). 결과가 negative 면 negative publish.

---

## 1. 무엇이 "reasoning 성능"인가 (정의 LOCK)

**LRB가 측정 안 함** (재확인):
- LRB axes = R@k / P@k / temporal_accuracy / R@1 / latency / token cost
- 모두 "올바른 문서 가져오기" 측정
- "가져온 문서로 정답 만들기" 안 측정

**Reasoning 성능 = 다음 axes 중 하나 이상**:

| Axis | 정의 | 측정 가능한 방법 |
|---|---|---|
| **Multi-hop inference** | 2+ 문서의 사실을 조합해서 결론 도출 | MuSiQue / 2Wiki / HotpotQA — answer EM/F1 |
| **Temporal reasoning** | 시간 변화에 따른 사실의 변화를 추론 | TimeQA / TempReason / TimeBench |
| **Answer faithfulness** | 답의 claim 이 retrieved context 에 entail 되는지 | NLI verifier (T5-XXL / RoBERTa-NLI) |
| **Hallucination resistance** | 없는 사실 만들기 회피 | HaluEval / FActScore / TruthfulQA |
| **Causal reasoning** | 인과 관계 추론 | CausalQA / CLadder |
| **Counterfactual robustness** | 가정 변경 시 답 일관성 | counterfactual augmentation |
| **Chain-of-thought correctness** | multi-step deduction 의 각 step 정확도 | GSM8K / BIG-Bench Hard |

본 Track C 는 **temporal reasoning + answer faithfulness + multi-hop
inference 3 axes** 에 집중 (mother-platform 측정-evidence 정합):
- temporal reasoning = JAMES validity-window 가 가설적 advantage 있는 axis
- answer faithfulness = RAB provenance + JAMES citation 정합
- multi-hop = JAMES graph layer 가설적 advantage (cycle γ 에서 retrieval-
  bottleneck 측정, reasoning 자체 미측정)

## 2. 외부 객관화 7-요건

"외부에서 인정받는 데이터" = 다음 7 요건 모두 충족:

| # | 요건 | 충족 방법 |
|---|---|---|
| 1 | **외부 표준 fixture** | TimeQA / TempReason / MuSiQue / 2Wiki public dataset 사용 (license-clear) |
| 2 | **외부 표준 scoring** | Token F1 / EM / NLI entailment — 학계 표준 metric |
| 3 | **사전 등록** | 측정 전 prereg doc commit + Zenodo deposit (post-hoc fit 차단) |
| 4 | **deterministic** | LLM judge 0; NLI verifier checkpoint pin |
| 5 | **multi-SUT comparison** | Vanilla + Naive + JAMES + GraphRAG + (option) ActiveGraph — gap structure |
| 6 | **multi-model** | gemma3:12b + mxtral + claude — single-model fluke 차단 |
| 7 | **공개 artifacts + replication** | Zenodo DOI + arXiv preprint + replication invite (collab arc 별도) |

본 plan 의 ⭐⭐⭐ tier 진입 = 7/7 충족.

## 3. Bench selection (외부 표준)

| Bench | What | License | Size | Track C 사용 |
|---|---|---|---|---|
| **TimeQA** (Chen et al. 2021) | Wikidata time-stamped facts QA | open (CC) | ~41K Q | **★ Primary** — temporal reasoning core |
| **TempReason** (Tan et al. 2023) | multi-hop temporal QA | open | ~13K Q | **Secondary** — multi-hop + temporal 결합 |
| **TimeBench** (Chu et al. 2024) | comprehensive temporal eval suite | open | ~9 sub-bench | Tertiary — cross-axis robustness |
| **MuSiQue** (Trivedi et al. 2022) | multi-hop QA (2-4 hop) | open | ~25K Q | 이미 cycle γ 측정 (retrieval bottleneck) — Track C re-run with reasoning axes |
| **2WikiMultihopQA** | multi-hop temporal | open | ~190K Q | smoke tier 이미 측정 (cycle γ C.4) |
| **HotpotQA** | multi-hop QA | open | ~113K Q | 옵션 — multi-hop generic |
| **HaluEval** | hallucination eval | open | ~35K | answer faithfulness sub-axis |

**선택 (Phase C1 의무 lock)**:
- **TimeQA** (Primary) — temporal reasoning 정합 + JAMES validity-window
  가설적 advantage axis
- **TempReason** (Secondary) — multi-hop + temporal 결합
- **MuSiQue** (Re-run) — 이미 cycle γ에서 retrieval 측정함, 이제
  reasoning answer F1 axis 까지 측정

3 benches × multi-SUT × multi-model 측정으로 publication-tier evidence.

## 4. Phase ladder (8 phase, ~3-4개월 solo)

### Phase C0: Bench survey + selection (1주, solo, this doc 의 §3 완성)
- 위 §3 의 표 lock
- 사용 license 검증 (commercial vs research)
- Sample size 결정 (smoke 500 / full 5000)

### Phase C1: Pre-registration (1주, solo)
- `docs/research/track-c-reasoning-preregistration-<date>.md`
- 3 bench × SUT lineup × model lineup × axes × honest tier ladder
- Zenodo prereg deposit (DOI 받기 — RAB Phase 3 패턴 mirror)

### Phase C2: Answer generation pipeline (2주, solo)
- 기존 `core.reasoning.engine.ReasoningEngine` 위에 bench-adapter
- Bench별 question → query 변환 + answer extraction
- SUT 별 retrieval (Vanilla / Naive / JAMES + GraphRAG if v0.2.2 done)
- LLM 답변 생성 (cross-model: 12B / mxtral / claude)

### Phase C3: Scoring infrastructure (1-2주, solo)
- Token F1 + EM scorer (SQuAD-norm; 학계 표준)
- NLI verifier 통합 (T5-XXL via HF Transformers, deterministic checkpoint)
- Per-axis decomposition (current vs historical / single-hop vs multi-hop)
- Cross-bench gap structure 계산기

### Phase C4: Smoke 측정 (1주, solo + operator)
- TimeQA smoke n=100 / 3 SUT / 1 model (gemma3:12b)
- Verify pipeline + scoring + artifacts emit
- Honest tier landing for smoke

### Phase C5: Full sweep 측정 (2-4주, operator-attended)
- 3 bench × 4 SUT × 3 model × n=500-1000 each
- ~24-36 cells total, batch overnight
- Per-cell deterministic re-run from artifacts

### Phase C6: Cross-axis analysis (1주, solo)
- Per-axis gap table (multi-hop / temporal / faithfulness)
- Honest tier landing per prereg §1.4
- Negative finding 도 publication (cycle γ 패턴)

### Phase C7: arXiv preprint + Zenodo DOI (2주, solo)
- LaTeX draft (RAB / LRB preprint 패턴)
- 11-item pre-submission honesty checklist
- arXiv submission (RAB sibling submission, 같은 endorsement 활용)
- Zenodo software DOI

### Phase C8: External reproducer invite (별도 collab arc)
- 외부 평가자 (Robin / Ali / ActiveGraph 팀) replication invite
- joint piece 자동 연결 금지 ([[feedback_eval_cycle_vs_collab_arc_separation]])

**총 비용**: ~3-4개월 solo + 외부 reproducer 의존 추가 time.

## 5. Honest tier ladder (lock before measurement)

| Result shape | Tier | publishable claim |
|---|---|---|
| 3 bench × 4 SUT × 3 model axes emit + JAMES > Vanilla on **temporal reasoning** AND **=/+ on multi-hop** AND **=/+ on faithfulness** | **⭐⭐⭐ publication tier** | "JAMES uniquely improves temporal reasoning, parity on multi-hop and faithfulness" |
| 3 bench × 4 SUT axes emit + JAMES > Vanilla on temporal only | **⭐⭐ specialty advantage** | "JAMES has measurable temporal-reasoning specialty; non-temporal parity with literature" |
| 3 bench × 4 SUT axes emit + JAMES ≈ Vanilla on all axes | **⭐ honest negative** | "JAMES reasoning performance = literature family — cycle γ 결과 reproduced + extended to temporal axis" |
| JAMES < Vanilla on any axis | **⭐ root-cause cycle** | reasoning regression evidence + fix-PR (separate cycle) |

**Magnitude framing 금지**: smoke tier (Phase C4) 결과로 publication-
tier claim 금지. Full sweep (Phase C5) + cross-bench + cross-model
완료 후만 publication-tier framing.

## 6. 가능한 outcome 시나리오 (정직)

**Outcome A — ⭐⭐⭐ specialty advantage (희망적 시나리오)**:
- TimeQA / TempReason 에서 JAMES > Vanilla / GraphRAG
- MuSiQue / 2Wiki 에서 JAMES = literature (cycle γ 결과 reproduced)
- → "JAMES 의 audit-native lifecycle architecture 가 temporal reasoning
  에서 측정-가능한 advantage" — publishable claim

**Outcome B — ⭐ honest negative (가능성 더 높음)**:
- 3 bench 모두 JAMES = literature family
- → "JAMES reasoning = literature 와 동급, audit + retrieval moats 가
  unique" — cycle γ + LRB 결과 정합

**Outcome C — surprising negative (가능)**:
- 일부 axis 에서 JAMES < Vanilla
- → root-cause cycle + fix-PR (separate)

**Outcome A 의 가능성 평가** (사전 추정 — 측정 전):
- Temporal axis 에서 valid-time filter 가 retrieved doc 의 정확성 ↑
  → answer 도 더 정확할 가능성 hypothesis
- 하지만 LRB top-1 정확도 향상 (+0.18) 이 reasoning F1 정확도로
  바로 transfer 될지는 미측정
- → 사전 추정 = ⭐⭐ specialty advantage 가능성 ~50-60%, ⭐ honest
  negative ~30-40%, ⭐⭐⭐ universal advantage ~10%

본 Track C 는 가능성 평가가 아닌 **측정 실행** 이 목표. 결과 honest
report.

## 7. 외부 객관화 evidence 가 만들어내는 것

본 Track C ⭐⭐⭐ 진입 시:

- **arXiv preprint** (LRB sibling submission, 같은 endorsement 활용)
- **Zenodo DOI** (software + prereg + result artifacts)
- **외부 reproducer 가능** (deterministic + public artifacts + replication recipe)
- **회사 결재 자료** 정확 framing:
  > "자메스는 TimeQA / TempReason / MuSiQue 3 외부 표준 벤치에서 측정.
  > JAMES R@1 temporal reasoning subset = X.XX (vs Vanilla R@1 = Y.YY).
  > 측정 사전등록 + 공개 artifacts + replication recipe + Zenodo DOI."

이 framing 이 사용자가 원하는 "외부 인정받을 수준의 데이터"의 정확한 형태.

⭐ honest negative 시:
- 그래도 **"JAMES reasoning = literature family. Audit + retrieval
  moats 가 unique."** publishable
- 회사 결재 자료 framing 정확:
  > "자메스의 차별 가치는 추론 우수가 아닌 audit + retrieval. cycle γ
  > + Track C 측정으로 reasoning parity 확인."

**둘 다 외부 객관화 가능** — measurement-driven discovery 정신 정합.

## 8. 다른 track 과의 관계

| Track | Status | Track C 와의 관계 |
|---|---|---|
| RAB | publication tier (DOI 받음) | Track C 의 audit chain reasoning sub-axis 직접 가용 |
| LRB Phase A/B | ⭐⭐⭐ tier | Track C 의 temporal retrieval prerequisite (이미 측정됨) |
| LRB v0.2.1 cross-model | 진행 중 (8 PR) | Track C 의 LLM-grounded retrieval producer 재사용 |
| LRB v0.2.2 GraphRAG | pending | Track C 의 GraphRAG SUT 직접 제공 |
| LRB v0.2.4 HR NLI axis | pending | Track C 의 NLI scorer 직접 제공 |
| v0.5 first-domain pilot | gated (LOI) | Track C ⭐⭐⭐ → pilot 결재 자료 강화 |
| Cycle γ (4 bench) | ⭐ infra | Track C 의 MuSiQue re-run 의 기반 |

**최적 순서**:
1. **v0.2.4 HR NLI axis 먼저 구현** (Track C 의 scoring infrastructure
   prerequisite)
2. **v0.2.2 GraphRAG SUT 먼저 구현** (Track C 의 SUT lineup prerequisite)
3. **Track C Phase C0-C8 진입**

또는 병행:
- v0.2.x track + Track C C0-C3 (인프라) 병행
- v0.2.x 완료 후 Track C C4+ (측정)

## 9. 다음 cycle 자연 step

본 doc commit 후:

1. **Track C C0** (bench selection lock) — 본 doc 의 §3 표 확정
2. **Track C C1** (prereg + Zenodo deposit) — 측정 전 lock
3. **v0.2.4 HR NLI axis 가속화** (Track C scoring 의 dependency)
4. **v0.2.2 GraphRAG SUT 가속화** (Track C SUT lineup 의 dependency)

각 phase 가 별도 cycle. 단일 세션에서 C0+C1 까지 가능.

## 10. 관련

- 사용자 catch (2026-06-11): "위 측정이 추론 성능을 측정한것이 맞아?"
  + "어떻게 해야 측정하고 그걸 외부지표로 객관적으로 드러낼수있는지"
- LRB Phase A handover (retrieval 측정): `docs/handovers/v0.4-lrb-phase-a-results-2026-06-11.md`
- LRB Phase B handover (retrieval 측정, scope disclaimer 추가됨):
  `docs/handovers/v0.4-lrb-phase-b-cross-scenario-2026-06-11.md`
- LRB v0.2.1 partial (retrieval 측정, scope disclaimer 추가됨):
  `docs/handovers/v0.4-lrb-v021-cross-model-partial-2026-06-11.md`
- LRB v0.2.1 prereg: `docs/research/lrb-v021-cross-model-preregistration-2026-06-11.md`
- RAB SPEC: `eval/rab/SPEC-v0.1.md`
- Cycle γ multi-hop closure: memory `project_cycle_gamma_phase_c2_retrieval_bottleneck`
- Cycle γ prior art: memory `project_cycle_gamma_phase_b_rgb_baseline`
- 6-dim readiness: `docs/PLATFORM_READINESS.md`
- self-eval trap rule: memory `feedback_self_evaluation_trap`
- forced discovery hunt END: memory `feedback_alpha_cycle_discovery_loop_end`
- measurement-driven discovery: memory `feedback_james_identity_measurement_driven`

## 11. ★ Key invariant (lock before any measurement)

**측정 결과가 ⭐ honest negative 여도 publish**. forced discovery
hunt END 룰 정합. measurement-driven discovery 정신. **"reasoning
superior" 결과를 만들기 위한 fixture / scoring / 분석 tweaking 금지**
— self-eval trap 직접 위반.

cycle γ 의 6-9th catch + RAB prior-art positioning + Phase A/B 의
honest finding (naive ≈ JAMES on S1, time-travel 만 unique) 의 정신
그대로 Track C 에 이식.

---

*본 doc 은 strategy plan. 실제 측정은 Phase C0-C8 별도 cycle.
prereg lock 전 어떤 측정도 안 됨. honest tier 진입 결정은 prereg §1.4
ladder 의 leg-by-leg validation.*
