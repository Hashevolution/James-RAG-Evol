# Cycle γ Phase D-alce — research-tier NLI 사전 등록 (Pre-registration)

**Date**: 2026-06-12 (인프라 구현 + 측정 **전** 커밋 — R5 의무)
**Status**: LOCKED. 이 문서 commit 이후 verifier checkpoint 종류 /
n / honest-tier 게이트 변경 금지. 변경이 필요하면 사유를 본 문서에
append 하고 그 cycle 의 결과는 exploratory 로 강등.

**Bench under test**: ALCE-asqa (Gao et al. 2023, EMNLP) — `eval/external/
alce_nli_adapter.py` (이 PR 신규) + `eval/external/alce_scorer.py`
(infra Phase A) + `eval/external/lrb/nli_verifier.py` (v0.2.4 HR 인프라
재사용).

**Predecessors**:
- Cycle γ Phase C.3 sealed (string-containment fallback infra-only)
- v0.2.4 HR cross-NLI (RoBERTa + DeBERTa) measured on hallucination
  resistance axis (PRs #797 / #798 / #807)
- C.3 prereg §6 "D-alce" 행 prerequisite — 별도 honest-tier 게이트
  의무

**Why pre-register**: cycle γ design memo §C.1 4-벤치 promise 의 ALCE
cell 을 "infrastructure-only" 에서 "research-tier NLI-scored" 로
격상. T5-XXL TRUE NLI (ALCE-official-grade) 는 ~11B 모델 GPU-only —
별도 cycle 로 분리. 본 cycle 의 research-tier 점수는 **ALCE-official-
grade publish 불가**, paper methods cross-verifier robustness 행만
inform.

---

## 1. Scope — Phase D-alce 가 측정할 것과 측정하지 않을 것

### 1.1 측정 (LOCK)

| 항목 | 값 |
|---|---|
| Bench | ALCE asqa (Phase C.3 와 동일 fixture, sha pinned) |
| Variant | `asqa` only (qampari / eli5 는 별도 cycle) |
| Verifier | `roberta-mnli` AND `deberta-v3-anli` (둘 다 측정 — cross-NLI agreement 의무, v0.2.4 HR 와 동일 패턴) |
| Verifier grade | `research-tier-{checkpoint}` (string `research-tier-roberta-mnli` / `research-tier-deberta-v3-anli`) |
| Producer | `ALCEClosedCorpusProducer` (Phase C.3 와 동일) |
| Model under test | `gemma4:e4b` (C.3 baseline) — 추가 모델은 별도 cycle |
| n_samples | 20 (C.3 와 동일 — research-tier 인프라 검증 smoke) |
| n_docs / query | 5 (ALCE default) |
| max_tokens | 1024 |
| Honest tier | **⭐ research-tier infra validation — NOT publication, NOT ALCE-official-grade** |
| Determinism | argmax softmax, no sampling, deterministic per checkpoint |

### 1.2 측정 안 함 (Phase D-alce OUT of scope)

| 항목 | 사유 |
|---|---|
| T5-XXL TRUE NLI Mixture | ~11B 모델, GPU-only, 별도 cycle (publication-grade ALCE-official) |
| Full N=300-1000 | research-tier smoke 우선 — 결과 보고 paper publish-ready 게이트 통과 시에만 N 확대 |
| qampari / eli5 variants | C.3+ row, 별도 사전 등록 |
| 추가 모델 (gemma3:12b / mxtral / claude) | 본 cycle 은 verifier-axis cross-NLI agreement 측정만; model-axis cross 는 별도 |
| paper v1.4 § ALCE outer validation 적용 | D-alce 결과 보고 별도 cycle |

## 2. Pre-registered verdict matrix

| Cross-NLI 일치 | 점수 패턴 | Verdict | 후속 |
|---|---|---|---|
| RoBERTa = DeBERTa, 둘 다 string-containment 보다 LOWER | LOWER 점수가 더 엄격 = research-tier 가 string-containment 의 false-positive 잡음 검증 | ⭐ research-tier infra validated + string-containment over-credits citations finding | paper methods note: string-containment 은 lenient upper bound, research-tier 는 stricter mid-tier, T5-XXL 가 publish-grade |
| RoBERTa ≠ DeBERTa (Δ > 0.10) | cross-NLI disagreement | ⭐ research-tier infra validated + cross-NLI sensitivity finding | T5-XXL cycle prerequisite — research-tier 결과 단독으로 paper 에 적지 않음 (cross-checkpoint 합의 없으면 robustness 미흡) |
| RoBERTa = DeBERTa, 둘 다 string-containment 와 동일 (Δ < 0.05) | string-containment fallback 이 우연히 정합 | ⭐ infra validated + fallback-vs-research band tight finding | string-containment 도 generous estimate 로 paper methods 표에 인용 가능 |
| 둘 중 하나라도 LOAD 실패 / 측정 0건 | 인프라 결함 | NOT infra-validated | adapter 디버그, re-prereg 없이 retry 가능 (config 변경 없을 시) |

## 3. Honest framing 의무

`result.json` 에 다음 field 의무:

```json
{
  "verifier_grade": "research-tier-roberta-mnli",          // or deberta-v3-anli
  "honest_tier": "research-tier: ... STRONGER than ... NOT ALCE-official-grade ...",
  "fixture_sha": "<sha256>",
  "n_evaluations": 20
}
```

본 cycle 결과는 paper publish-ready claim 으로 인용 **금지**.
"Research-tier cross-NLI 합의 / 불일치 finding" 로만 paper methods
robustness 행 inform.

## 4. Cross-bench 표 update 룰

cross-bench 표 (cycle γ 4-벤치 summary) 에 ALCE row 가 갱신될 때:

```
| Bench       | Verifier grade            | Score (citation_p, citation_r) | N | Honest tier |
| ALCE-asqa   | fallback-string-containment | 0.8168 / 0.9067              | 20 | infra-only |
| ALCE-asqa   | research-tier-roberta-mnli  | <TBD>                       | 20 | research-tier |
| ALCE-asqa   | research-tier-deberta-v3-anli | <TBD>                     | 20 | research-tier |
| ALCE-asqa   | alce-official-t5-xxl-true-nli | DEFERRED                    | — | NOT YET RUN |
```

`verifier_grade` column 필수. 한 verifier 점수만 인용 금지 — research-
tier cross-NLI 결과는 항상 페어로 표시.

## 5. 측정 실행 절차 (operator action)

```powershell
# RoBERTa-MNLI
python scripts/research/alce_smoke_run.py `
  --verifier roberta-mnli `
  --n 20 `
  --model gemma4:e4b

# DeBERTa-v3-ANLI
python scripts/research/alce_smoke_run.py `
  --verifier deberta-v3-anli `
  --n 20 `
  --model gemma4:e4b
```

각 실행은 HF cache 에 ~1.5 GB 체크포인트 다운로드 (CPU inference 가능,
20 queries × ~5 passages × ~2 sentences ≈ 200 NLI calls / run ≈
~3-5분 wall time 예상).

## 6. 인프라 완성 후 (Phase D-alce 측정 후, 다음 cycle prerequisite)

| Phase | 작업 |
|---|---|
| D-alce+ | qampari / eli5 variants research-tier 측정 |
| E-alce-t5xxl | T5-XXL TRUE NLI Mixture 통합 (별도 prereg, ALCE-official-grade) |
| F-alce | full N=300-1000 (publication-grade), T5-XXL 결과 |
| G-alce | paper v1.4 § "ALCE outer validation" reverse-publish |

D-alce 측정 자체는 본 prereg 게이트 안에서 진행; D-alce 측정 후
follow-up cycle 들은 별도 prereg 의무.

## 7. 사전 등록 commit hash = evidence

이 doc 의 첫 commit hash 가 사전 등록의 timestamped evidence.
측정 실행 전 PR 머지 + main 동기화 후 시작.

## 8. 관련

- `docs/research/cycle-gamma-c3-alce-smoke-preregistration-2026-06-11.md`
  — Phase C.3 (preceding) string-containment fallback prereg.
- `docs/research/v024-hr-nli-axis-preregistration-2026-06-11.md` —
  HR cross-NLI prereg (재사용 인프라의 sister cycle).
- `eval/external/alce_nli_adapter.py` — 본 cycle 구현 모듈.
- `eval/external/lrb/nli_verifier.py` — v0.2.4 HR NliVerifier (재사용
  대상).
- `eval/external/alce_scorer.py` — Phase A.4.4 NLIVerifier Protocol
  (변경 없음, adapter 가 Protocol 만족).
- `tests/test_alce_nli_adapter.py` — 19 단위 테스트 (transformers 없이
  contract 검증).
- [[project_cycle_gamma_phase_c3_alce_smoke]] — preceding cycle state.
- [[feedback_self_evaluation_trap]] — fixture / scoring authority 외부
  = self-eval trap 통과.
- [[feedback_finding_size_honest_framing]] — research-tier ≠ ALCE-
  official-grade, paper publish-ready claim 금지.
