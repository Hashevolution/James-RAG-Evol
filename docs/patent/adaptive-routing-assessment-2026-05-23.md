# Adaptive Routing — 정직한 특허 가능성 평가

> **작성일**: 2026-05-23
> **목적**: "Adaptive Budgeting + Auto-Routing" 연구 영역의 **솔직한** 특허 가능성 평가.
> **결론 (먼저)**: 이 영역은 **특허보다 논문 + 제품**. 특허는 skip 권장.
>
> **배경**: 3-author 연구 협력 (Robin Converse + Ali Afana + JAMES) 의
> "memorize vs reason" + "fanning vs clustering" 발견. LinkedIn 공유 + PR #453.

---

## 0. 한 줄 결론

> **"훌륭한 연구이지만 특허 영역이 아니다. 발견 (논문) + 라우팅 제품 (차별점) 이 진짜 가치이고, 특허는 skip 이 정직한 판단. 특허 예산은 STAGE 1B/5/T8 같은 진짜 강한 후보에 집중."**

---

## 1. 연구 발견 요약

| 발견 | 내용 |
|---|---|
| 모드 분리 | (A) 외우기 (recall): byte-identical 답 (sampling layer bypass) / (B) 생각하기 (reason): 발산 |
| Fanning vs Clustering | 작은 모델 (e4b): 20번 다 다른 답 / 큰 모델 (26B): 6개만 다름 (수렴) |
| ~500-token reasoning floor | gemma4:e4b 가 visible output 전 ~500 token hidden reasoning 필요 |
| 모델 스케일 효율 | 파라미터 증가 = capacity 증가가 아니라 **routing 정확도** 증가 ("shortening the path") |
| 9배 절감 | 26B 49 token vs e4b 400-450 token (같은 정답) |

3 독립 검증: Robin (18/18), Ali (12/12), JAMES V3'.a-d (4×10/10), 2 architectures.

---

## 2. 구현 상태 — 사실 확인 (2026-05-23 메인 스캔)

### ✅ 실제 구현된 것 (commodity)

| 기능 | 위치 | 비고 |
|---|---|---|
| Backend registry + protocol | `core/reasoning/backends/__init__.py` | PR #283-285, #324-326 |
| `JAMES_REASONING_BACKEND` env | PR #305 | 4 stage 일괄 switch |
| `JAMES_LLM_TEMPERATURE` env | PR #326 | default 0.2 |
| LLM Router (task-based, keyword) | `llm/router.py` | 전부 gemma4:e4b fallback |
| Cap bump (200/400 → 4096) | PR #399 | 일회성 fix (adaptive 아님) |

### ❌ 디자인만 (구현 0)

| 기능 | 상태 |
|---|---|
| **Adaptive Budgeting + Auto-Routing** | ❌ 코드 0 |
| Task-Weight Gradient (heavy/light/none) | ❌ 없음 |
| 답 발산/수렴 기반 routing | ❌ 없음 |
| 9배 절감 구현 | ❌ 없음 (연구 측정만) |
| Per-stage backend override | ❌ 디자인만 |

→ **핵심 adaptive routing 은 아직 미구현**.

---

## 3. 솔직한 특허 가능성 — 3 분리

### ❌ 3.1 연구 발견 (Discovery) — 특허 불가

특허법 §2 (한국) / 35 U.S.C. §101 Alice (미국): **과학적 발견·수학적 방법·자연 현상은 특허 대상 아님**.

| 발견 | 판정 |
|---|---|
| memorize 답 byte-identical | 자연 현상 관찰 → 불가 |
| fanning vs clustering | 모델 특성 발견 → 불가 |
| ~500-token floor | 측정 결과 → 불가 |
| 파라미터 ↑ = routing ↑ | 통계 관찰 → 불가 |

→ **논문의 영역**.

### ❌ 3.2 Adaptive Routing 시스템 — 선행기술 강함 + 미구현

| 자메스 개념 | 선행기술 |
|---|---|
| 작은/큰 모델 작업별 routing | **FrugalGPT (2023, TMLR 2024) — 98% 비용 절감** |
| task-weight 기반 model 선택 | **RouteLLM (ICLR 2025) — strong/weak routing** |
| budget-aware 선택 | FrugalGPT "given budget" |
| 9배 절감 | FrugalGPT 98% (더 큼) |
| MoE-style routing | MixLLM (2025), Router-R1 (2025) |

추가:
- **미구현** → 정식 출원 시 재현 가능성 (특허법 42조 3항) 미충족 위험
- General concept = anticipated → 거절 거의 확실

### ⚠️ 3.3 단 하나의 narrow 후보 — Determinism-based Routing (비권장)

> "답이 memorized (deterministic, byte-identical) 인지 감지하여 작은 모델/캐시로 라우팅, reasoning (divergent) 만 큰 모델로"

FrugalGPT (quality score) / RouteLLM (win prediction) 와 다른 각도 (determinism detection).

그러나:
- task-type 분류 (recall vs reasoning) 는 학계 흔함
- determinism 감지 = multiple sampling 추가 비용
- **미구현**
- 등록 가능성 25~35% (낮음)

→ **권장 안 함. 억지스러움.**

---

## 3.5 보충 — 발견 vs 발명의 IP 보호 지형 (discovery ≠ unprotected)

> 질문: **"발견은 기술 보호 대상이 아닌가?"**
> 답: **특허(독점권)는 안 되지만, 발견을 지키는 다른 보호 수단은 분명히 있다.** "특허 불가 = 무방비"가 아니다.

### 3.5.1 발견을 둘러싼 6가지 보호 메커니즘

| 보호 수단 | 발견(memorize/reason)에 적용 | 판정 | 비고 |
|---|---|---|---|
| **특허** (독점권) | 발견·자연현상 자체는 §2 / Alice §101 대상 아님 | ❌ | 응용도 자명 → 진보성 약함 (아래 3.5.3) |
| **방어적 공개** (defensive publication) | arXiv / PR / 블로그로 선공개 | ✅ | **타인의 후속 특허를 차단** — 가장 실효적 |
| **학술 우선권** (academic priority) | 논문 게재 + 피인용 | ✅ | 최초 발견자 권위 = 시장 신뢰 자산 |
| **영업비밀** (trade secret) | 이미 LinkedIn/PR로 공개됨 | ⚠️ | 공개된 순간 비밀성 상실 → 사실상 불가 |
| **저작권** (copyright) | 코드·논문 "표현"은 보호 | ⚠️ | **아이디어·발견 자체는 보호 못 함** (idea–expression 이분법) |
| **선점효과** (first-mover) | 제품(Adaptive Routing) 시장 선점 | ✅ | 9배 절감 = sales point, 특허 없이도 차별화 |

→ 발견에 맞는 보호는 **특허가 아니라 ①방어적 공개 + ②학술 우선권 + ③선점효과** 3종. 본 문서의 기존 3트랙 전략(논문 + 제품 + skip)과 정확히 일치.

### 3.5.2 Diamond v. Chakrabarty — "발견 자체"와 "발견의 응용"의 경계

미국 판례 **Diamond v. Chakrabarty (1980)** + 한국 §2 해석의 공통 원리:

> **발견 그 자체는 특허 불가. 그러나 그 발견을 이용한 신규·진보적 "응용(application)"은 특허 가능.**

- 자연현상(E=mc², 미생물의 존재) → ❌
- 그 현상을 적용한 구체적 인공 산물·공정(유전자 조작 박테리아) → ✅

즉 "memorize는 free, reason은 무게가 있다"는 발견은 불가하지만, 이를 **구체적·신규적으로 구현한 라우팅 메커니즘**이라면 이론상 특허 후보가 될 수 있다. 문제는 그 응용이 진보성 문턱을 넘느냐다.

### 3.5.3 특허 가능한 "응용"의 3요건 — 자메스 라우팅은 셋 다 미달

| 요건 | 내용 | 자메스 Adaptive Routing |
|---|---|---|
| 신규성 (novelty) | 선행기술에 없을 것 | ❌ FrugalGPT/RouteLLM 가 cost-aware routing 선점 |
| 진보성 (non-obviousness) | 통상의 기술자에게 자명하지 않을 것 | ❌ "발견이 강할수록 응용은 자명" (아래 dilemma) |
| 실시가능성 (implementability) | 명세서로 재현 가능할 것 (§42③) | ❌ **미구현** — 코드 0 |

### 3.5.4 핵심 딜레마 — "발견이 강할수록 응용은 자명해진다"

> 발견이 **명확하고 설득력 있을수록** → "그렇다면 작은 모델로 라우팅하라"는 응용은 통상의 기술자에게 **자명한 다음 수순**이 된다 → **진보성(non-obviousness) 약화**.

이것이 mechanistic-interpretability 발견을 특허로 끌고 갈 때의 구조적 함정이다. 발견의 설득력(논문 가치)과 응용의 진보성(특허 가치)은 **역상관**한다. 발견이 좋을수록 특허는 더 어려워진다 → 발견은 논문으로, 보호는 방어적 공개로 가는 것이 정합적.

### 3.5.5 자산 구조 — 발견과 발명의 분리 배치

```
┌─────────────────────────────────────────────────────────────┐
│ 발견 (Discovery)                                              │
│   memorize=free / reason=weight / fanning vs clustering       │
│   ↓ 보호 = 특허 ❌                                            │
│   ├─ 방어적 공개 (arXiv/PR)  ── 타인 특허 차단 ✅             │
│   ├─ 학술 논문 (3-author)    ── 우선권 + 권위 ✅              │
│   └─ 제품 (Adaptive Routing) ── 선점 + 9배 절감 ✅            │
├─────────────────────────────────────────────────────────────┤
│ 발명 (Invention)                                              │
│   Cascade(1B) / Plugin Contract(5) / Event Node(T8)           │
│   ↓ 보호 = 특허 ✅                                            │
│   └─ 구체 메커니즘 + 구현됨 + 깨끗한 prior art                │
└─────────────────────────────────────────────────────────────┘
```

→ **발견과 발명을 같은 통(특허)에 담으려 하지 않는다.** 발견은 공개·논문·제품으로 가치화하고, 발명만 특허로 독점한다. 이 분리가 portfolio의 신뢰도(§9 정직성 원칙)를 지킨다.

---

## 4. 강한 후보와의 대비

| 후보 | 무엇 | 강도 | 이유 |
|---|---|---|---|
| STAGE 1B (Cascade) | provenance invalidation | ⭐⭐⭐ | 구체 알고리즘 + 12 invariant + 구현됨 + prior art 깨끗 |
| STAGE 5 (Plugin Contract) | dogfood + eval contract | ⭐⭐⭐ | 구체 시스템 + 구현됨 + prior art 깨끗 |
| STAGE T8 (Event Node) | 5번째 entity + cascade 통합 | ⭐⭐⭐ | 구체 구현 + prior art 깨끗 |
| **Adaptive Routing** | 모델 선택 라우팅 | **⭐** | **발견 + 미구현 + FrugalGPT 강한 선행** |

→ 강한 후보 = "구체 메커니즘 + 구현 + 깨끗한 prior art". Adaptive Routing = 정반대.

---

## 5. 진짜 가치 — 3트랙 전략

### 트랙 1. 학술 논문 ⭐⭐⭐ (최우선)

**무엇**: 3-author joint paper (Robin + Ali + JAMES)

**제목 후보**:
> "Mode-dependent inference cost in local LLMs: memorization is free, reasoning has weight inversely proportional to parameter count"

**3축 통합**:
| 축 | 기여자 |
|---|---|
| 모드 분리 (memorize vs reason) | Robin Converse |
| 작업-무게 gradient (heavy/light/none) | JAMES |
| 모델-스케일 효율 (token + 수렴) | Robin / Ali |

**Venue**: EMNLP / ACL (efficient inference), NeurIPS / ICML efficiency workshops, MLSys. arXiv preprint 먼저.

**강점**: 3 독립 deployment cross-validation + 2 architectures + 정량 mechanism (~500-token floor) = 재현 가능 + 독립 검증.

→ **특허보다 학술 인용 + 시장 권위가 더 큰 자산**.

### 트랙 2. 제품 기능 ⭐⭐⭐ (구현 가치)

**무엇**: Adaptive Budgeting + Auto-Routing 을 자메스 제품 핵심 기능으로.

**가치**: 비용 9배 절감 = 강력한 sales point. sovereign-AI / on-premise 직접 ROI.

**구현 로드맵 (v0.4/v0.5)**:
```
1. Task classifier — memorize vs reason (deterministic)
2. Model router — task → 적정 모델
3. Budget allocator — task-weight 따라 token budget
4. Fallback — 작은 모델 실패 시 큰 모델 escalate (FrugalGPT 패턴)
```

→ **특허 없이도 제품 차별화**. MIT 오픈소스 = reference impl.

### 트랙 3. 특허 ⭐ (skip)

**권고: skip**

이유: 발견 불가 + 시스템 선행기술 강함 + 미구현 + narrow 도 약함.

특허 예산은 STAGE 1B/5/T8 에 집중.

---

## 6. 권장 우선순위

### Patent portfolio (강한 것만)

| 우선 | Stage | 강도 |
|---|---|---|
| 1 ✅ | 1B Cascade | ⭐⭐⭐ (완료) |
| 2 | 1A Doc-source gate | ⭐⭐ |
| 3 | 5 Plugin Contract | ⭐⭐⭐ |
| 4 | T8 Event Node | ⭐⭐⭐ |
| 5 | 9 Catalog Poisoning | ⭐⭐ |
| — | ~~Adaptive Routing~~ | ⭐ **skip** |

### 이 연구 영역 트랙

| 트랙 | 우선도 | 시점 |
|---|---|---|
| 논문 (3-author) | ⭐⭐⭐ | 2026 Q3~Q4 (즉시 arXiv) |
| 제품 (Adaptive Routing) | ⭐⭐⭐ | v0.4/v0.5 |
| 특허 | skip | (논문 대체) |

---

## 7. Disclosure 일자 (참고)

| 항목 | 일자 | PR |
|---|---|---|
| Fair-witness report | 2026-05-18 | #307 |
| JAMES_REASONING_BACKEND | 2026-05-18 | #305 |
| LLM Provider Contract 디자인 | 2026-05-18 | #316 |
| V3'.a query_rewriter (~500-token floor) | 2026-05-22 | #399 |
| Cap bump merged | 2026-05-22 | #399 |
| 4-stage validation | 2026-05-23 | #407 |
| V3'.c/.d raw JSON | 2026-05-23 | #426 |

→ 만약 (비권장) narrow 특허 추진 시, grace ≈ 2027-05.

---

## 8. 핵심 메시지

1. **발견은 진짜 좋다 — 논문으로** (memorize vs reason + 3축, 3 검증, 2 architecture)
2. **라우팅 제품은 강력 — 특허 없이** (FrugalGPT 가 이미 98% 절감)
3. **특허는 강한 후보에 집중** (1B/5/T8)
4. **억지 특허는 역효과** (거절 → 시간·비용 손실 + portfolio 신뢰도 하락)

---

## 9. 정직성 원칙

> 사용자 요청: "억지스러운 것이 아닌 솔직한 특허 가능성"

본 평가는 그 원칙의 적용 사례. **모든 것을 특허화하지 않는 것** 이 portfolio 의 질과 신뢰도를 지킨다.

- patent ✓: 구체 메커니즘 + 구현 + 깨끗한 prior art (1B/5/T8)
- paper ✓: 과학적 발견 (memorize/reason)
- product ✓: 비용 절감 차별점 (adaptive routing)
- patent ✗: 발견·미구현·강한 선행기술 (adaptive routing)

---

## 10. 참고 — 선행기술

- FrugalGPT (Chen et al., arXiv 2305.05176, TMLR 2024) — LLM cascade, 98% cost savings
- RouteLLM (Ong et al., ICLR 2025) — strong/weak routing, win prediction
- MixLLM (2025) — dynamic routing in mixed LLMs
- Router-R1 (2025) — RL-based routing
- "Dynamic Model Routing and Cascading for Efficient LLM Inference: A Survey" (arXiv 2603.04445, 2026)

---

**End of Adaptive Routing Patent Assessment.**

본 문서는 정직한 self-assessment 의 기록. 강한 특허 (1B/5/T8) 와 약한 특허 (adaptive routing) 를 구분하여, patent 예산을 효율 배분하기 위한 reference.
