# Track C C0 — Bench Selection Lock (2026-06-11)

> **Purpose**: Track C reasoning measurement 의 3 외부 표준 bench 선택
> 을 lock. Track C C1 prereg 의 prerequisite.
>
> **Status**: LOCKED. 이 doc commit 후 bench lineup 변경 금지 (변경
> 시 사유 append + 별도 cycle).
>
> **Predecessors**:
> - Track C plan: `docs/strategy/track-c-reasoning-measurement-plan-2026-06-11.md`
> - cycle γ Phase C.2 (MuSiQue 측정 history): memory `project_cycle_gamma_phase_c2_retrieval_bottleneck`
> - cycle γ Phase B+C prior art: memory `project_cycle_gamma_phase_b_rgb_baseline`

---

## 1. 선택된 3 bench (LOCK)

### 1.1 Bench #1: TimeQA (Primary)

| 항목 | 값 |
|---|---|
| 정식 명칭 | TimeQA: Time-Sensitive Question Answering |
| 저자 | Chen et al. 2021 (NeurIPS Datasets & Benchmarks) |
| 논문 | "A Dataset for Answering Time-Sensitive Questions" |
| URL (operator verify) | https://github.com/wenhuchen/Time-Sensitive-QA |
| License (operator verify) | research use (operator: confirm license type before use) |
| Size | ~41K Q (Easy ~20K, Hard ~21K) |
| Format | JSONL (Wikidata-derived) |
| Question field | `question` |
| Context field | `paragraphs` (Wikipedia evidence) |
| Answer field | `targets` (list of valid answers with time-range) |
| Time annotation | each fact has valid (start_time, end_time) |
| Question types | "Who was X's spouse in <year>?", "Where did X work in <year>?" |
| 예시 query | "Who was the mayor of Paris in 2010?" |

**왜 Primary**:
- Track C 의 핵심 axis = temporal reasoning
- 명시적 시간 annotation = JAMES validity-window 의 가설적
  advantage axis 직접 측정 가능
- Easy / Hard 두 subset → difficulty stratification

**Sample size 결정**:
- Smoke (Phase C4): n=100 from `dev` split (deterministic seed)
- Full (Phase C5): n=1000 from `dev` split

**Gold scoring**: time-aware EM/F1 — answer 가 valid time window 안에
있어야 정답 (논문 official scoring).

### 1.2 Bench #2: TempReason (Secondary)

| 항목 | 값 |
|---|---|
| 정식 명칭 | TempReason |
| 저자 | Tan et al. 2023 (ACL) |
| 논문 | "Towards Benchmarking and Improving the Temporal Reasoning Capability of Large Language Models" |
| URL (operator verify) | https://github.com/DAMO-NLP-SG/TempReason |
| License (operator verify) | research use (operator: confirm) |
| Size | ~13K Q across L1 / L2 / L3 difficulty levels |
| Format | JSON |
| Question field | `question` |
| Context field | `paragraphs` or external retrieval |
| Answer field | `answer` |
| Difficulty levels | L1 (time-time), L2 (time-event), L3 (event-event multi-hop) |
| 예시 query | "Who held the position right after X?" (L2), "Who was born first, X or Y?" (L3) |

**왜 Secondary**:
- Multi-hop + temporal 결합 = JAMES graph + validity-window 양쪽 axis
- Difficulty level 별 break down → reasoning depth 측정

**Sample size 결정**:
- Smoke: n=100 (L1 + L2 + L3 균등 분포)
- Full: n=600 (각 level n=200)

**Gold scoring**: Token F1 + EM (SQuAD-norm)

### 1.3 Bench #3: MuSiQue Re-run (Tertiary, reasoning axis 추가)

| 항목 | 값 |
|---|---|
| 정식 명칭 | MuSiQue-Ans v1.0 |
| 저자 | Trivedi et al. 2022 (TACL) |
| URL | https://github.com/StonyBrookNLP/musique |
| License | Apache 2.0 (verified — existing eval/external/musique_loader.py) |
| Size | ~25K Q (Ans subset) |
| Format | JSONL (이미 eval/external/_fixtures/musique/ 에 인프라 있음) |
| Loader | `eval/external/musique_loader.py` (✓ 이미 존재) |
| Scorer | `eval/external/musique_scorer.py` (✓ 이미 존재) |
| Question field | `question` |
| Context field | `paragraphs` (supporting + distractor) |
| Answer field | `answer` + `answer_aliases` |
| Question types | 2-hop / 3-hop / 4-hop multi-hop |

**왜 Re-run**:
- Cycle γ Phase C.2 에서 이미 측정 (retrieval bottleneck 발견)
- 본 Track C 에서 reasoning F1 axis 추가 측정 — cycle γ retrieval
  결과 + Track C answer F1 결과 결합 → "retrieval 충분해도 answer
  F1 가 낮음" 또는 "retrieval 부족이 answer F1 의 root cause" 결정 가능

**Sample size 결정**:
- Smoke: n=100 from `dev` (cycle γ smoke 와 동일 sample 재사용 가능)
- Full: n=1000 from `dev`

**Gold scoring**: Token F1 + EM (이미 `musique_scorer.py` 구현됨)

## 2. Sample sizes summary (LOCK)

| Bench | Smoke (C4) | Full (C5) | Total full |
|---|---|---|---|
| TimeQA | 100 | 1000 | 1000 |
| TempReason | 100 (L1+L2+L3 균등) | 600 (L1/L2/L3 × 200 each) | 600 |
| MuSiQue | 100 | 1000 | 1000 |
| **Total full sweep** | 300 | **2600** | 2600 |

Cells = 2600 queries × 4 SUT × 3 model = **31,200 evaluations**.

Per-query elapsed (cycle γ + LRB v0.2.1 측정 reference):
- gemma3:12b: ~4.6s/query
- mxtral: ~10s/query (8x scaling)
- claude (cloud): ~3-5s/query

Average ~6s/query × 31,200 = ~52 hours full sweep. Operator-attended
overnight × 3-4 nights 가능.

## 3. Scoring metrics (LOCK)

### 3.1 Deterministic axes (RAB H1 strict)

| Axis | Bench | 구현 |
|---|---|---|
| **Token F1** | TimeQA / TempReason / MuSiQue | SQuAD-norm (이미 `musique_scorer.py` 패턴) |
| **Exact Match (EM)** | 위와 동일 | 동일 |
| **TimeQA time-aware F1** | TimeQA only | answer 가 valid time window 안에 있어야 정답 (official scoring) |
| **MuSiQue support-fact F1** | MuSiQue only | retrieved doc 가 supporting 인지 (cycle γ C.2 와 동일) |

### 3.2 NLI-grounded axis (H1-variant — v0.2.4 dependency)

| Axis | Bench | 구현 |
|---|---|---|
| **HR (Hallucination Resistance)** | 모두 | atomic claim 추출 + NLI(context, claim) entailment 비율 |

NLI verifier 선택은 v0.2.4 prereg 에서 LOCK (별도 doc).

### 3.3 Out of scope (이 cycle)

| Axis | 사유 |
|---|---|
| Per-step Chain-of-Thought 정확도 | TimeQA / TempReason 가 CoT label 미제공 |
| Counterfactual robustness | 별도 fixture 필요 (TimeQA 의 counterfactual variant 미존재) |
| Causal reasoning | Track C scope 밖 (별도 cycle candidate) |
| User satisfaction | 측정-evidenced 정합 안 됨 |

## 4. SUT lineup (Track C 기준 LOCK)

| SUT | 상태 | Track C 진입 시점 |
|---|---|---|
| **Vanilla (token-overlap RAG)** | ✓ 구현됨 (LRB Phase A) | Phase C2 진입 시 즉시 가용 |
| **Naive-supersede** | ✓ 구현됨 (LRB Phase B) | 동일 |
| **JAMES (validity-window)** | ✓ 구현됨 (LRB Phase B) | 동일 |
| **Microsoft GraphRAG** | ✗ 미구현 (v0.2.2 pending) | v0.2.2 완료 후 |
| **ActiveGraph** (option) | ✗ 미구현 + collab arc | LRB v0.2 publication tier 후 |

**Phase C5 진입 prerequisite**: v0.2.2 GraphRAG SUT 완료 (없으면
3-SUT Track C → publication tier 약화).

Phase C4 smoke 는 3 SUT 만 으로 진행 가능 (v0.2.2 wait 불필요).

## 5. Model lineup (Track C 기준 LOCK)

| Model | Tier | Track C 사용 |
|---|---|---|
| gemma4:e4b (4B) | small | **제외** (LRB v0.2.1 측정으로 reasoning 부족 입증, 자원 낭비) |
| gemma3:12b (12B) | medium | **Primary** |
| mixtral:8x7b (47B) | large | **Secondary** |
| claude-haiku-4-5 (cloud) | large | **Tertiary** (operator: API key / Max-plan headless) |

3 model = cross-model fluke 차단 + size threshold reproduction.

## 6. License verification (operator action 의무)

Track C C1 prereg LOCK 전 operator 가 다음 확인 의무:

- [ ] TimeQA license 정확 type (research vs commercial)
- [ ] TempReason license 정확 type
- [ ] MuSiQue license = Apache 2.0 (이미 확인됨 ✓)
- [ ] 각 bench 의 redistribution 조건 (Zenodo deposit 가능 여부)
- [ ] Citation 의무 (논문 인용 + license attribution)

License 확인 실패 시:
- TimeQA / TempReason 중 하나 reject → 대안 bench 선정 (예: HotpotQA
  temporal subset / TempTabQA)
- 대안 미선정 시 Track C scope = 2 bench only (Track C plan §3 fallback)

## 7. C1 prereg 에 LOCK 되어야 할 추가 항목

본 doc 의 C0 lock 후 C1 prereg 에 추가 LOCK:
- 최종 SUT lineup (3 or 4)
- 최종 model lineup (3)
- Per-bench sample size (이 doc §2)
- Scoring metric per bench (이 doc §3)
- Honest tier ladder (Track C plan §5)
- Replication recipe template
- Zenodo deposit metadata

## 8. 다음 step

본 doc commit 후:

1. **Operator verify** § 6 의 license 항목 (1-2일)
2. **Track C C1 prereg lock** (1주, solo)
3. **Zenodo prereg deposit** (RAB Phase 3 패턴 mirror)
4. **v0.2.4 HR NLI prereg lock** (병행, 1주 solo)
5. **Phase C2 답변 생성 pipeline 구현** (2주 solo)
6. **Phase C3 scoring infrastructure (NLI 통합)** (1-2주)
7. **Phase C4 smoke 측정** (1주)
8. **Phase C5 full sweep** (operator-attended 2-4주)

## 9. 관련

- Track C plan: `docs/strategy/track-c-reasoning-measurement-plan-2026-06-11.md`
- 사용자 catch (2026-06-11): "위 측정이 추론 성능을 측정한것이 맞아?"
- Cycle γ MuSiQue 측정 history: memory `project_cycle_gamma_phase_c2_retrieval_bottleneck`
- Cycle γ prior art: `docs/research/cycle-gamma-prior-art-positioning.md`
- 기존 인프라 reuse: `eval/external/musique_loader.py` + `eval/external/musique_scorer.py`
- v0.2.4 HR NLI prereg: `docs/research/v0.2.4-hr-nli-axis-preregistration-2026-06-11.md` (별도, 병행 작성)
- self-eval trap rule: memory `feedback_self_evaluation_trap`
- measurement-driven discovery: memory `feedback_james_identity_measurement_driven`

---

*본 doc 의 commit hash = bench selection lock evidence. license
verification 후 Track C C1 prereg + Zenodo deposit 진입.*
