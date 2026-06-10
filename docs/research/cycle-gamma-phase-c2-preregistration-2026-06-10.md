# Cycle γ Phase C.2 — MuSiQue paired ablation 사전 등록 (Pre-registration)

**Date**: 2026-06-10 (측정 실행 **전** 작성 — R5 권고 반영)
**Status**: LOCKED before any Phase C.2 run. 이 문서 작성 이후 임계값 /
판정 규칙 변경 금지. 변경이 필요하면 변경 사유를 본 문서에 append 하고
해당 측정은 exploratory 로 강등 (verdict-grade 아님).

> **Why pre-register**: 사용자 catch 9건이 전부 사후 정정으로 작동했다
> (project-direction review 2026-06-09, R5). 사전 등록은 사후 정정보다
> 싸고, post-hoc fit (1st catch 패턴) 을 구조적으로 차단한다.

---

## 1. Verdict question (단 하나)

> **rerank / cognitive_stages 는 자기 home-turf (multi-hop graded) 축에서
> 기여하는가?**

- Phase E-min cross-model 이 RGB-en (abstention 가족 양 axis) 의
  **LOSS 절반**을 잠갔다: rerank 3/3, cognitive_stages 3/3 net+ when
  disabled.
- 본 측정 = **GAIN 절반**. 두 절반을 합쳐 가설 1 (deadweight) vs
  가설 2 (tradeoff) 를 결판한다.
- `typed_filter` 는 **제외** (home turf = adversarial, cycle γ 4 bench
  밖 — Phase E cross-model handover §4).

## 2. 측정 설계 (고정)

| 항목 | 값 |
|---|---|
| Bench | MuSiQue-Ans dev (`musique_ans_v1.0_dev.jsonl`), 외부 표준 + official-scorer mirror (`eval/external/musique_scorer.py`) |
| Cells | R0 (full JAMES) + `JAMES_DISABLE_RERANK=1` + `JAMES_DISABLE_COGNITIVE_STAGES=1` |
| Models | mxtral:8x7b / gemma4:e4b / llama3.1:8b (Phase E-min 과 동일 3종) |
| n | **25 query / cell** (Phase E-min paired comparability; 변경 금지) |
| Query 선택 | 결정적 subsample (seed 고정), 3 모델 × 3 cell 모두 **동일 25 query** (paired) |
| Runs | 9 (3 cells × 3 models), 추가 run 은 사전 등록 위반 아님 단 첫 9 run 결과로 1차 verdict 고정 |
| Workspace | `workspaces/cycle_gamma_musique_ans` (supporting + distractor paragraphs 전부 인제스트, source id `musique-ans-<row_id>-p<idx>`) |

## 3. Axis 역할 라벨링 (methodological-chain 룰 의무 4질문)

| Axis | 역할 | 비고 |
|---|---|---|
| `f1` | **Primary verdict axis** | token-level, graded — multi-hop home turf 의 가장 민감한 축 |
| `em` | Secondary verdict axis | f1 과 방향 일치 확인용 (coarse) |
| `support_idx_recall` | **Diagnostic only** | runner 가 support idx 전달 못 하면 "not measured" — verdict 에 사용 금지 |
| RGB Δnoise / Δnegrej | 이미 잠긴 LOSS 절반 | 재측정 안 함, Phase E-min 값 그대로 결합 |
| step7 | 사용 안 함 | regression check 등급, 본 측정과 무관 |

**Fixture fitness**: MuSiQue dev = 외부 표준 벤치 + official scorer mirror
→ multi-hop graded 에 대해 **verdict-grade** (self-eval trap 통과).

**Leak caveat (사전 명시)**: MuSiQue 는 Wikipedia 기반 — 3 모델 모두 학습
분포 안일 가능성 높음. 따라서 **절대 점수는 leak-unsafe** 하고 publishable
하지 않다. 단 **paired Δ (R0 − OFF)** 는 leak 이 양 arm 에 동일하게 작용
하므로 verdict statistic 으로 유효 (`feedback_evidence_grounded_validity_check`
의 paired-design 해소). 절대 점수를 단독 headline 으로 쓰는 것 금지.

## 4. 노이즈 밴드 (사전 고정)

- n=25 에서 em 1-query 입자 = **0.04**.
- **노이즈 밴드: |Δ| ≤ 0.04 (em), |Δ| ≤ 0.03 (f1)** — 1-query-equivalent
  이하 움직임은 "효과 없음" 으로 읽는다.
- 정직 명시: 정식 power calculation 없음. n=25 는 Phase E-min paired
  comparability 가 근거이고, 부족한 통계력은 **cross-model 일관성** (3/3
  또는 2/3 방향 일치) 으로 보강한다 — Phase E-min 과 동일 관례.
- n=1 verdict inflation 룰 (`feedback_n1_verdict_inflation_n3_caught`)
  적용: 단일 모델 결과만으로 ⭐⭐ 승급 금지.

## 5. 판정 규칙 (LOCKED)

Δ 정의: **Δ = score(R0) − score(component OFF)**. Δ > 0 ⇒ component 가
home turf 에서 기여.

### Per-component verdict (rerank, cognitive_stages 각각 독립)

| 결과 패턴 | Verdict | 후속 라이선스 |
|---|---|---|
| Δf1 > +0.03 on **≥2/3 모델**, 나머지 1 모델 방향 일치 또는 밴드 안 | **가설 2 PROVEN (tradeoff)** | **유지 + 조화 설계** licensed: query-type routing (IntentClassifier 확장 — multi-hop/answerable ⇒ ON, abstention-prone ⇒ OFF). **제거/default-off 금지** |
| \|Δf1\| ≤ 0.03 AND \|Δem\| ≤ 0.04 on **3/3 모델** | **가설 1 PROVEN (deadweight)** | RGB LOSS 절반과 결합 → **default-off PR licensed** (R4 feature-registry 정비 동반) |
| Δf1 < −0.03 on ≥2/3 모델 (OFF 가 home turf 에서도 더 좋음) | **가설 1 강화형** | default-off PR licensed + "component 이 multi-hop 도 해친다" 는 별도 finding 으로 기록 (단 prior-art 확인 전 novelty 주장 금지) |
| 모델 간 방향 불일치 (예: 1 모델 Δ > +0.03, 1 모델 Δ < −0.03) | **SPLIT (model-dependent)** | 전역 default 변경 **금지**. R10 model-capability-tier profile 경로로 이관 (≤8B / ≥14B boundary 는 후속 측정으로) |

### Cell 유효성 (사전 고정)

- Cell 당 오류 query > 10% (3/25 초과) ⇒ 해당 cell invalid, 원인 진단 후
  재실행 (재실행은 위반 아님 — 무효 cell 의 교체).
- R0 가 3 모델 모두 f1 ≤ 0.05 ⇒ fixture/ingest wiring 문제 의심 — verdict
  내리지 말고 진단 모드 전환 (`feedback_measurement_smoke_caught_wiring_bugs`:
  라이브 smoke 1회 선행 의무).

### 금지 사항 (사전 명시)

1. 측정 후 임계값 이동 금지 (post-hoc fit 차단).
2. `support_idx_recall` 을 verdict 에 동원 금지 (diagnostic only).
3. 절대 점수 단독 headline 금지 (leak caveat).
4. 가설 2 PROVEN 시 "그래도 제거" framing 금지 — 사용자 사전 선택
   (2026-06-09): 입증 시 **유지 + 조화 설계**.
5. 결과가 어느 쪽이든 **novelty 주장 전 prior-art 확인 의무** — 외부
   리뷰 (2026-06-09) 가 이미 confirmation-tier 예고: CoT 는 ~10B 미만
   모델에서 무익/유해 (Wei et al. 후속), reasoning 추가 시
   instruction-following 저하 (arXiv:2505.11423, 2505.14810), 7-9B 는
   in-pipeline 지시 흡수 못 함 (arXiv:2510.13329). 가설 어느 쪽이 나와도
   기대 framing = "externally-confirmed empirical reproducibility".
6. 본 측정 결과를 mid-June joint piece 에 자동 연결 금지
   (`feedback_eval_cycle_vs_collab_arc_separation` 4-질문 통과 전).

## 6. Honest-framing tier 사전 배정

| 결과 | 최대 tier |
|---|---|
| 가설 1 또는 2 가 3/3 cross-model 일치 | ⭐⭐ (cross-model confirmed) — ⭐⭐⭐ 는 prior-art 가 이미 cover 하므로 도달 불가 (사전 선언) |
| 2/3 일치 | ⭐ stable + model-dependent 주석 |
| SPLIT | finding 아님 — R10 경로 데이터 포인트 |

## 7. 실행 순서 (logical chain)

```
0. 라이브 smoke 1 query (wiring 검증) — verdict 산입 금지
1. MuSiQue download → eval/external/_fixtures/musique/
2. cycle_gamma_musique_corpus_build.py (RGB 템플릿 적응) → workspace 인제스트
3. R0 × 3 모델 (baseline 먼저 — R0 유효성 게이트 §5 통과 확인)
4. DISABLE_RERANK × 3 모델
5. DISABLE_COGNITIVE_STAGES × 3 모델
6. Δ 계산 → §5 판정표 적용 → RGB LOSS 절반과 결합 → verdict
7. Handover doc + (licensed 시) 후속 PR
```

예상 비용: ~15–20 min/run × 9 = 2.5–3h live LLM + 데이터 prep.

---

*이 문서는 측정 실행 전 커밋된다. Commit hash 가 사전 등록 증거.*
