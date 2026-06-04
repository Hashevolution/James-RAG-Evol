# α-8 Paper-Aligned Comparison — JAMES vs MultiHop-RAG Baselines (2026-06-04, P1)

> 자메스 multihop_rag 점수를 **MultiHop-RAG 논문 (Tang & Yang 2024,
> COLM) Table 6 metric으로 재채점**해 외부 baseline과 위치 비교. 기존
> bench JSON 재채점 — 새 측정 없음, cloud quota 0.

## 0. TL;DR

**자메스 + 작은 로컬 모델 (gemma4:e4b)이 paper-aligned primary metric에서
ChatGPT (0.44) 동급, open 70b 모델 (Mixtral 0.32 / Llama-70b 0.28) 초과.**
단 strict metric은 0.11-0.17로 낮아 진짜 verdict는 [strict, primary] band.

## 1. 비교 표 (multihop_rag, paper Table 6 retrieved-chunks metric)

| System | primary | strict |
|---|---:|---:|
| GPT-4 (paper) | 0.56 | — |
| Claude-2.1 (paper) | 0.52 | — |
| Google-PaLM (paper) | 0.47 | — |
| **JAMES + Claude(Opus) ontology** (Stage4 run1) | **0.47** | 0.12 |
| ChatGPT/3.5 (paper) | 0.44 | — |
| **JAMES + gemma4:e4b ontology** (α-8 n=3) | **0.44–0.45** | 0.11–0.17 |
| Mixtral-8x7B (paper) | 0.32 | — |
| Llama-2-70b (paper) | 0.28 | — |
| Claude(Opus) RAW no-JAMES (leak suspect) | 0.72 | 0.21 |

## 2. Metric

- **논문 (paper)**: binary exact match on simple responses (entity /
  yes-no / before-after). null query = "insufficient information" 류면
  correct. 정확한 matching logic은 논문 미공개.
- **자메스 paper-aligned 근사** (`eval/qvt/oracle.py::score_paper_aligned_accuracy`):
  - answerable (abstention_truth=present): gold_signals match.
    **primary** = gold_signals[0] (primary answer + aliases) 매칭;
    **strict** = 모든 gold_signal 매칭.
  - null query (abstention_truth=absent): abstain하면 correct.
  - [strict, primary] band로 보고 — 논문 logic 미공개 + multi-term 차이.

## 3. 발견 3개

### 발견 1 — 자메스 경쟁력 입증 (primary 기준)

JAMES + gemma4:e4b primary **0.44** = ChatGPT (0.44) 동급, Mixtral
(0.32) / Llama-70b (0.28) 초과. **작은 e4b 모델 (≈ Llama-70b의 1/17
크기)로 open 70b 모델 초과** = pipeline 경쟁력 신호.

### 발견 2 — 모델 무관 재확인

JAMES + gemma4:e4b (0.44) ≈ JAMES + Claude Opus (0.47). frontier 모델
붙여도 +0.03. 앞선 cycle의 "JAMES 위에서 모델 무관" 패턴 재확인.

### 발견 3 — Claude RAW 0.72 = 학습-지식 leak 직접 증거

Claude RAW (no JAMES) 0.72 > GPT-4 retrieved 0.56. retrieval 없이
학습 지식만으로 GPT-4 retrieved 초과 = multihop_rag (2023 뉴스) 가
Claude 학습 분포에 포함됐다는 직접 증거. RAW는 논문 "retrieved"
조건 비교 대상 아님 (오히려 ground-truth 0.89 쪽 차원).
→ `feedback_evidence_grounded_validity_check` 룰 재확증.

## 4. Per-question-type (primary, JAMES + gemma4:e4b run2 대표)

| question_type | primary | strict | n |
|---|---:|---:|---:|
| inference_query | 0.68 | 0.08 | 25 |
| temporal_query | 0.32 | 0.04 | 25 |
| comparison_query | 0.24 | 0.00 | 25 |
| null_query | 0.56 | 0.56 | 25 |

- inference (entity 답) 가장 강함 (0.68) — 논문도 GPT-4/PaLM이 inference > 0.9
- comparison (yes/no) 약함 (0.24) — 논문도 Mixtral이 logical negation 약함 명시
- null query 0.56 = abstention 정책 절반 작동 (hallucination 회피)

## 5. 🔴 Honest caveat (over-claim 방지 의무)

| caveat | 영향 |
|---|---|
| **strict 0.11-0.17로 낮음** | 진짜 multi-hop 완전정답은 약함. band = [0.11, 0.45] |
| primary는 lenient 가능 | gold_signals[0] substring match — 논문 exact-match보다 관대할 수 있음 |
| 논문 matching logic 미공개 | 정확 재현 아님, 근사 |
| gold_signals multi-term vs 논문 single | 척도 차이 |
| 모델/corpus 규모 다름 | 100Q subset vs 논문 full 2556Q |

**진실은 band 안**: strict 기준이면 자메스 < Llama-70b, primary 기준이면
ChatGPT급. 확실한 것 = **자메스가 70b open 모델과 비교 가능한 league에
작은 모델로 있음** (정확한 순위는 metric 정밀화 필요).

## 6. 품질 향상 필요성 — 결론

1. **자메스는 이미 경쟁력 있음** — 작은 로컬 모델로 open 70b league.
   "심각하게 품질 낮은 시스템" 아님.
2. **general news 향상 여지** = GPT-4 (0.56) / gold (0.89) gap. lever =
   모델 (측정상 무관 확증) 또는 retrieval (gold gap). 둘 다 자메스에서
   제한적 (이미 측정).
3. **strict 0.11 = 진짜 multi-hop 완전정답 약함** = field-wide 어려운
   문제 (GPT-4 gold도 0.89). 진짜 향상 여지는 retrieval bottleneck.
4. **진짜 차별화 lever = 도메인 데이터 + 온톨로지 특화** (general news는
   모든 시스템이 비슷한 retrieval bottleneck — 자메스 mother platform →
   v0.5 도메인 pilot 방향 정합).

## 7. 다음 step 후보 (P2-P4)

- **P2** (선택): MultiHop-RAG full corpus 적재 + 동일 모델 통제 측정으로
  정밀 비교 (현 100Q subset → full)
- **P3** (선택): metric alignment 정밀화 — 논문 exact-match logic에 더
  근접 (single primary answer 추출)
- **P4** (전략): domain pack prototype — 같은 benchmark 인프라 재사용,
  도메인 자료에서 자메스 차별화 측정 (v0.5 도메인 pilot 진입)

P1 결론: **자메스 general-news 경쟁력 입증 (작은 모델로 open 70b league).
품질 lever는 모델 아니라 도메인 데이터/온톨로지. 다음 = domain pack.**

## 9. P3 — metric 정밀화 + answer-format mismatch 발견 (2026-06-04 추가)

P1의 0.44 (ChatGPT급) 결론이 metric 정밀화 후 흔들림. **진짜 confound는
metric이 아니라 answer-format mismatch** 발견.

### P3.1 — yes/no word-boundary 정밀화

P1 `accuracy_primary`의 yes/no 매칭이 substring이라 거짓 hit 위험
("no" in "not"/"now"/"nothing", "yes" 답 중간 등장). word-boundary +
answer-lead(60자) 정밀화 (`_primary_answer_match`):

| System | primary (substring, P1) | primary (word-boundary, P3) |
|---|---:|---:|
| JAMES+gemma4:e4b (n=3) | 0.44-0.45 | **0.29-0.35** |
| JAMES+Claude(Opus) | 0.47 | **0.26** |
| Claude RAW (leak) | 0.72 | 0.56 |

→ P1 0.44는 yes/no substring 거짓 hit 과대평가. 정밀하면 0.29-0.35.

### P3.2 — 진짜 원인: answer-format mismatch

자메스 comparison 답 실제 형태 (서술형, 1400-2000자):
- "Source files: ... [분석] ..." 로 시작
- "We cannot definitively compare..." / "do not necessarily align..."
- **yes/no를 명시 안 함**

논문 모델 = 단답 ("Yes"/"No"). → **같은 metric 비교가 자메스 서술형 답에
부당** (yes/no 앞에 없으니 word-boundary lead에서 miss).

= P1 substring (0.44) = 과대 / P3 word-boundary (0.29) = 과소. 진실은
**answer-format 통제 후**.

### P3.3 — 단답 모드 일시 적용 가능 확정 (코드 0)

측정용 fixture suffix ("Answer with ONLY 'Yes'/'No', no explanation")
smoke (comparison 3Q, gemma4:e4b):

| id | gold | 자메스 답 (단답 모드) |
|---|---|---|
| 26/27/28 | Yes | "No" / "No" / "No." (ans_len 2-3) |

→ **fixture suffix만으로 자메스 단답 produce 확정** (production 코드 0
변경, NATURAL preset 무시하고 단답). 단 comparison 3개 다 틀림 (gold
Yes, 답 No) = **자메스 comparison query 약점이 단답 모드로 명확히 드러남**.

### P3 결론

- P3 precision metric (`score_paper_aligned_accuracy` + `_primary_answer_match`)
  은 **단답 모드 답에 적용해야 정확**. 서술형 답에 적용하면 과소평가.
- **fair 우수성 확정 = 단답 모드 full 측정 (100Q) 필수** (fixture suffix
  로 일시, 코드 0). + 모델 통제 (Mixtral 또는 gemma4:e4b).
- answer-format mismatch = measurement-side 신규 confound
  (`feedback_evidence_grounded_validity_check` 계열 확장).

## 8. 재현

```
python scripts/research/paper_aligned_rescore.py
# 기존 bench JSON 재채점, 새 측정 없음
```

- oracle: `eval/qvt/oracle.py::score_paper_aligned_accuracy`
- tests: `tests/test_qvt_oracle.py::PaperAlignedAccuracyTests` (6 cases)
- bench JSONs: `reports/bench_b3c4562_multihop_rag_20260603_*.json` (α-8 n=3)
  + `reports/bench_4a6c7b9_multihop_rag_20260604_*.json` (Stage 4/4b)
