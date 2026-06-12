# LRB v0.2.3b — S3 publication-scale × LLM-grounded × cross-model 사전 등록

**Date**: 2026-06-12 (인프라 구현 + 측정 **전** 커밋 — R5 의무)
**Status**: LOCKED. 이 문서 commit 이후 model 집합 / scale preset / mode /
honest-tier 게이트 변경 금지. 변경이 필요하면 사유를 본 문서에 append
하고 그 cycle 의 결과는 exploratory 로 강등.

**Runner**: `scripts/research/lrb_run_v023b_s3_cross_model.py` (이 PR
신규). v0.2.1 cross-model runner 의 `run_cell` 을 재사용하여 S3
fixture 만 swap. SUT logic / scorer logic 변경 0.

**Predecessors**:
- **v0.2.1 S2 cross-model 4-leg cleared** (gemma4:e4b / gemma3:12b /
  mxtral 47B / claude-haiku-4-5; PR #809 / #810): S2 cell 에서 V<N<J
  4/4 model preserved
- **v0.2.3 S3 token-mode 4-scale ladder PRESERVED** (PR #823-#825): R@1
  V<N<J pattern preserved across 4 scenarios spanning 12.5× scale
  (S2 N=80 → S3 publication N=1000); honest framing pattern-robust,
  magnitude scenario-sensitive

**Why pre-register**:
1. v0.2.1 4-leg cross-model 결과는 S2 (N=80, hand-curated) 에서 측정.
   S3 publication (N=1000, synthetic-templated) 으로 cross-model
   재현이 publication-scale 검증의 마지막 매핑
2. 4-leg condition 의 post-hoc 변경 / model 추가 / scale subset 선택을
   사전 lock 으로 차단
3. LLM-grounded cross-model 측정은 시간 비용 큼 (1000 queries × 4
   models × 3 SUTs × LLM call → 수 시간); 비용 정당화 위해 사전
   verdict matrix 필요

---

## 1. Scope — Phase v0.2.3b 가 측정할 것과 측정하지 않을 것

### 1.1 측정 (LOCK)

| 항목 | 값 |
|---|---|
| Scenario | S3 publication (fixture SHA pinned; deterministic regen via `build_lrb_scenario_s3.py --scale publication`) |
| n_evaluations | 1000 (publication preset) |
| SUTs | vanilla / naive-supersede / james (3) |
| Models | gemma4:e4b / gemma3:12b / mxtral:8x7b / claude-haiku-4-5 (4) |
| Modes | llm-grounded (token mode 는 PR #825 에서 이미 closed) |
| Total cells | 3 SUT × 4 model × 1 scale × 1 mode = **12 cells** |
| 측정 axes | R@1 (primary publication axis) / R@5 / R@10 / P@5 / P@10 / temporal_accuracy |
| Honest tier | **infrastructure / measurement; NOT publication tier** until verdict matrix §2 PASSED |
| Determinism | RAB H1 (scoring deterministic per fixture_sha + retrieval seed; LLM-grounded reranker stochasticity = ~10pp band per PR #819 finding) |

### 1.2 측정 안 함 (Phase v0.2.3b OUT of scope)

| 항목 | 사유 |
|---|---|
| S3 smoke / dev cross-model | publication 셀이 publication-scale claim 의 evidence; 작은 scale 은 token-mode 에서 이미 validated |
| 추가 모델 (qwen / llama / 기타) | 4-leg conditions 는 v0.2.1 prereg 에 lock; 동일 4 model 유지 |
| HR cross-NLI × S3 publication | v0.2.4 separate cycle |
| paper Results / Discussion 갱신 | verdict 결과 보고 별도 cycle |

## 2. Pre-registered verdict matrix

본 cycle 의 12 cells 측정 결과로 다음 verdict 결정:

| Leg condition (per model) | 충족 | Verdict |
|---|---|---|
| leg 1 (gemma4 4B): S3 pub R@1 V<N<J | ? | leg-clear → ⭐⭐⭐ scale × model evidence on 4B |
| leg 2 (gemma3:12b): S3 pub R@1 V<N<J | ? | leg-clear → ⭐⭐⭐ on 12B |
| leg 3 (mxtral 47B): S3 pub R@1 V<N<J | ? | leg-clear → ⭐⭐⭐ on 47B |
| leg 4 (claude cloud): S3 pub R@1 V<N<J | ? | leg-clear → ⭐⭐⭐ on cloud |

Composite verdict:

| Leg 결과 | Composite verdict | 후속 |
|---|---|---|
| 4/4 leg clear | ⭐⭐⭐ S3 publication V<N<J cross-model PUBLICATION-TIER | paper Results §4.7 추가 / Discussion §5 강화 |
| 3/4 leg clear | ⭐⭐ partial-tier cross-model + 1 model artifact finding | failing model attribution 별도 cycle |
| ≤ 2/4 leg clear | ⭐ scale-attribution + model-attribution finding | S2 ↔ S3 difference 별도 분석 cycle |
| 1+ cell crash / 측정 불가 | NOT infra-validated | runner / fixture / Ollama 디버그 retry (config 변경 없을 시 re-prereg 불필요) |

**JAMES − Naive gap > +0.10** at every leg = secondary publishable
condition; gap > +0.05 = ⭐⭐ partial; gap ≤ 0 = honest negative for
that model.

## 3. Honest framing 의무

`result.json` 에 다음 field 의무 (runner emit):

```json
{
  "benchmark":       "lrb",
  "version":         "v0.2.3b",
  "scenario":        "S3-publication",
  "scale_preset":    "publication",
  "model":           "<one of 4>",
  "mode":            "llm-grounded",
  "n_evaluations":   1000,
  "fixture_sha":     "<deterministic sha>",
  "honest_tier":     "v0.2.3b S3-publication cross-model cell; deterministic axes (RAB H1). NOT publication. Pre-reg: ..."
}
```

본 cycle 결과는 paper publish-ready claim 으로 인용 **조건부**:
verdict matrix §2 PASS 조건 충족 시에만. 그 외는 internal cycle
finding 로만 사용.

## 4. Cross-bench / cross-scale 표 update 룰

paper / cross-scale 표에 v0.2.3b row 가 갱신될 때:

```
| Scenario × Mode × Model     | V R@1 | N R@1 | J R@1 | V<N<J | Honest tier |
| S2 token (frozen v0.2.1)    | 0.225 | 0.538 | 0.713 | yes   | ⭐⭐⭐ publication |
| S3 pub token (v0.2.3)       | 0.502 | 0.721 | 0.845 | yes   | ⭐⭐⭐ pattern / ⭐⭐ magnitude |
| S2 llm-gr gemma4 (v0.2.1)   | 0.488 | 0.563 | 0.725 | yes   | ⭐⭐⭐ publication |
| S2 llm-gr gemma3:12b        | 0.400 | 0.613 | 0.775 | yes   | ⭐⭐⭐ publication |
| S2 llm-gr mxtral            | 0.375 | 0.625 | 0.838 | yes   | ⭐⭐⭐ publication |
| S2 llm-gr claude            | 0.613 | 0.775 | 0.975 | yes   | ⭐⭐⭐ publication |
| S3 pub llm-gr gemma4        | <TBD> | <TBD> | <TBD> | ?     | <verdict-matrix-dependent> |
| S3 pub llm-gr gemma3:12b    | <TBD> | <TBD> | <TBD> | ?     | <verdict-matrix-dependent> |
| S3 pub llm-gr mxtral        | <TBD> | <TBD> | <TBD> | ?     | <verdict-matrix-dependent> |
| S3 pub llm-gr claude        | <TBD> | <TBD> | <TBD> | ?     | <verdict-matrix-dependent> |
```

## 5. 측정 실행 절차 (operator action)

```powershell
# 1. S3 publication fixture 생성 (이미 있다면 skip; deterministic 재생성)
python scripts/research/build_lrb_scenario_s3.py --scale publication

# 2. 4-model LLM-grounded sweep
#    - Ollama 가 gemma4:e4b / gemma3:12b / mixtral:8x7b 로컬에 있어야 함
#    - claude-haiku-4-5 는 Anthropic API key 또는 Max-plan headless `claude -p`
$env:PYTHONPATH = "."
python scripts/research/lrb_run_v023b_s3_cross_model.py `
  --scale publication `
  --modes llm-grounded `
  --models gemma4:e4b,gemma3:12b,mixtral:8x7b,claude-haiku-4-5

# 3. 단일 모델 단독 실행 (점진 검증; claude 가 가장 비싸므로 마지막)
python scripts/research/lrb_run_v023b_s3_cross_model.py `
  --scale publication --modes llm-grounded --models gemma4:e4b
```

**예상 비용** (1000 queries × 3 SUT × 4 model):
- gemma4:e4b (4B 로컬): ~30-60분
- gemma3:12b (로컬): ~60-90분
- mixtral:8x7b (로컬): ~2-3시간
- claude-haiku-4-5 (cloud): ~30-60분 (latency + API rate limit dependent)
- **총 estimated**: 4-6시간 wall (모델 sequential)

## 6. 인프라 완성 후 (v0.2.3b 측정 cycle, 다음 단계)

| Phase | 작업 |
|---|---|
| v0.2.3b 결과 분석 | leg matrix 채우기 + composite verdict 결정 + result doc 작성 |
| v0.2.3b results 통합 | paper Results §4.7 신설 (cross-scale × cross-model 표) |
| v0.2.4b | S3 publication × HR cross-NLI (v0.2.4 axis × scale; 별도 prereg) |
| v0.2.5b | preprint 갱신 후 arXiv revision 또는 supplementary |

## 7. 사전 등록 commit hash = evidence

이 doc 의 첫 commit hash 가 사전 등록의 timestamped evidence. 측정
실행 전 PR 머지 + main 동기화 후 시작. 측정 결과는 본 prereg verdict
matrix §2 기준으로만 평가.

## 8. 관련

- `scripts/research/lrb_run_v023b_s3_cross_model.py` — 본 cycle 구현
  runner.
- `scripts/research/lrb_run_v021_cross_model.py` — 재사용 대상 (S1/S2
  cross-model, 변경 없음).
- `docs/research/lrb-v021-cross-model-preregistration-2026-06-11.md` —
  S2 cross-model prereg (paired baseline).
- `docs/research/lrb-v023-s3-publication-scale-preregistration-2026-06-12.md`
  — S3 token-mode prereg (paired sibling, scale-axis).
- `docs/research/lrb-v023-s3-publication-scale-results-2026-06-12.md`
  — S3 token-mode 결과 (4-point scale ladder, pattern preserved).
- `docs/research/lrb-v021-s2-vanilla-reproducibility-band-2026-06-12.md`
  — LLM-grounded reranker stochasticity ~10pp band finding (claude
  vanilla S2 R@1 0.5125↔0.6125).
- `eval/external/lrb/adapters/` — 3 SUT adapters (변경 없음).
- `eval/external/lrb/cross_model.py` — cross-model retrieval helper
  (변경 없음, reused).
- [[project_lrb_phase_a_smoke]] — LRB cycle state.
- [[feedback_finding_size_honest_framing]] — research-tier ≠
  publication-grade, verdict matrix 기준 적용 의무.
- [[feedback_self_evaluation_trap]] — fixture / scoring authority 외부
  (S3 schema는 S2 와 동일; scoring authority 변경 없음).
