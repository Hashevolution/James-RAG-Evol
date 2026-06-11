# Cycle γ Phase D-2wiki — supporting-fact 사전 등록 (Pre-registration)

**Date**: 2026-06-12 (인프라 구현 + 측정 **전** 커밋 — R5 의무)
**Status**: LOCKED. 이 문서 commit 이후 producer 종류 / prompt 형식 /
n / honest-tier 게이트 변경 금지. 변경이 필요하면 사유를 본 문서에
append 하고 그 cycle 의 결과는 exploratory 로 강등.

**Bench under test**: 2WikiMultiHopQA (Ho et al. 2020, COLING) —
`eval/external/wikimulti_loader.py` + `eval/external/wikimulti_scorer.py`
+ `eval/external/wikimulti_cited_producer.py` (이 PR 신규).

**Predecessors**:
- Cycle γ Phase C.4 sealed (closed-corpus producer, em/f1/f1_by_type
  measured, support_fact_f1 "not measured by design")
- cycle γ design memo §C.1 4-벤치 promise 의 **2Wiki cell 의 마지막
  infra-only 잔여물** = supporting-fact axis
- D-alce sibling cycle (PR #820 직전) 가 ALCE citation axis 를
  infra-only → research-tier 격상 — D-2wiki 는 2Wiki supporting-fact
  axis 의 동일 격상

**Why pre-register**: cycle γ design memo §C.1 4-벤치 promise 의 2Wiki
cell `support_fact_f1` axis 를 "infra-only" 에서 "research-tier
producer-emitted" 로 격상. 작은 open 모델 (gemma4:e4b 등) citation
정확도 자체는 RAG citations literature 의 known weak axis — 본 cycle
이 측정하는 것은 *infrastructure / pipeline 작동*, 절대 정확도 score
publish-ready claim 아님.

---

## 1. Scope — Phase D-2wiki 가 측정할 것과 측정하지 않을 것

### 1.1 측정 (LOCK)

| 항목 | 값 |
|---|---|
| Bench | 2WikiMultiHopQA dev split (Phase C.4 와 동일 fixture, sha pinned) |
| Producer | `WikiMultiCitedProducer` (이 PR 신규, supporting-fact 출력 prompt) |
| Scorer | `WikiMultiScorer` (Phase A.3 기존, 변경 없음 — `support_fact_f1` axis 가 producer-emit `predicted_supporting_facts` 를 소비) |
| Model | `gemma4:e4b` (C.4 baseline 과 동일) |
| n_samples | 20 (C.4 와 동일 — research-tier 인프라 검증 smoke) |
| max_tokens | 1024 |
| Honest tier | **⭐ research-tier infra validation — NOT publication-grade citation quality** |
| Determinism | producer-side: stable prompt + parser; LLM-side: ollama temperature default |

### 1.2 측정 안 함 (Phase D-2wiki OUT of scope)

| 항목 | 사유 |
|---|---|
| 큰 모델 / instruction-tuned cited models | E-2wiki 별도 cycle (gemma3:12b / mxtral / claude 가 citation 정확도 본 cycle 의 단순 분기 → 모델-cross 별도) |
| qampari / eli5 / 추가 변형 | 2Wiki 는 단일 bench; ALCE variants 와 무관 |
| Full N=300-1000 | research-tier smoke 우선 — 결과 보고 paper publish-ready 게이트 통과 시에만 N 확대 |
| Cross-bench 표 publish-ready ranking | research-tier 점수는 publish ready 아니므로 ranking 표 갱신 보류 |
| paper v1.4 § "2Wiki supporting-fact outer validation" | D-2wiki 결과 보고 별도 cycle |

## 2. Pre-registered verdict matrix

| support_fact_f1 결과 | answer EM/F1 vs C.4 비교 | Verdict | 후속 |
|---|---|---|---|
| support_fact_f1 > 0 AND answer EM/F1 within ±0.05 of C.4 baseline | infra OK + answer 안정 | ⭐ research-tier infra validated + citation emission working at small model | E-2wiki 모델 ladder cycle prereq 통과 (publish-ready 가능성 평가) |
| support_fact_f1 > 0 AND answer EM/F1 regression > 0.10 vs C.4 | infra OK BUT citation prompt 가 answer quality 깎음 | ⭐ research-tier infra validated + small-model prompt tradeoff finding | prompt design 별도 cycle (cited vs uncited 의 answer tax 정량화) |
| support_fact_f1 = 0 AND `predicted_supporting_facts` 전부 비어있음 | 모델이 SUPPORTING_FACTS 형식 못 따라옴 | ⭐ research-tier infra validated (parser working) + small-model citation-emission ceiling finding | E-2wiki larger-model cycle prerequisite 직접 evidence |
| 측정 0건 / pipeline crash | 인프라 결함 | NOT infra-validated | producer/parser 디버그, re-prereg 없이 retry 가능 (config 변경 없을 시) |

## 3. Honest framing 의무

`result.json` 에 다음 field 의무 (이 PR 의 wiki2_smoke_run.py 가 emit):

```json
{
  "producer_grade":  "research-tier-cited",
  "honest_tier":     "research-tier: ... STRONGER than C.4 ... NOT publication-grade ... E-2wiki ...",
  "fixture_sha":     "<sha256>",
  "scope": {
    "producer_emits_supporting_facts": true,
    "support_fact_f1_axis":            "measured (research-tier)",
    "comparable_to_musique_magnitude": false,
    "cross_bench_claim":               "..."
  }
}
```

본 cycle 결과는 paper publish-ready claim 으로 인용 **금지**.
"Research-tier 2Wiki citation infra working at small model" /
"small-model citation-emission ceiling" / "prompt-induced answer
tradeoff" finding 으로만 paper methods robustness 행 inform.

## 4. Cross-bench 표 update 룰

cross-bench 표 (cycle γ 4-벤치 summary) 에 2Wiki row 가 갱신될 때:

```
| Bench    | Producer grade            | Axes (em / f1 / f1_by_type / support_fact_f1) | N | Honest tier |
| 2Wiki    | infra-only-uncited        | 0.10 / 0.16 / 0.22 / --                       | 20 | infra-only |
| 2Wiki    | research-tier-cited       | <TBD> / <TBD> / <TBD> / <TBD>                 | 20 | research-tier |
| 2Wiki    | publication-grade-cited   | DEFERRED                                      | -- | NOT YET RUN |
```

`producer_grade` column 필수. 단일 모델 / 단일 producer 점수 인용 금지
— research-tier 결과는 항상 C.4 baseline 과 페어로 표시 (answer-axis
tradeoff 정량화).

## 5. 측정 실행 절차 (operator action)

```powershell
# D-2wiki research-tier smoke
python scripts/research/wiki2_smoke_run.py `
  --cited `
  --n 20 `
  --model gemma4:e4b
```

C.4 baseline 결과 (`reports/external/2wiki/dev-smoke-20260611T071605Z.*`)
와 paired 비교. 동일 fixture_sha 확인 후 axis 비교.

## 6. 인프라 완성 후 (Phase D-2wiki 측정 후, 다음 cycle prerequisite)

| Phase | 작업 |
|---|---|
| D-2wiki+ | gemma3:12b / mxtral citation prompt 응답 측정 (모델-cross robustness) |
| E-2wiki | claude / instruction-tuned 큰 모델 citation 정확도 (publication-grade prereq) |
| F-2wiki | full N=300-1000 (publication-grade), 모든 모델 |
| G-2wiki | paper v1.4 § "2Wiki supporting-fact outer validation" reverse-publish |

D-2wiki 측정 자체는 본 prereg 게이트 안에서 진행; D-2wiki 측정 후
follow-up cycle 들은 별도 prereg 의무.

## 7. 사전 등록 commit hash = evidence

이 doc 의 첫 commit hash 가 사전 등록의 timestamped evidence.
측정 실행 전 PR 머지 + main 동기화 후 시작.

## 8. 관련

- `docs/research/cycle-gamma-c4-2wiki-smoke-preregistration-2026-06-11.md`
  — Phase C.4 (preceding) 인프라 only prereg.
- `docs/research/cycle-gamma-d-alce-research-tier-nli-preregistration-2026-06-12.md`
  — sibling cycle (ALCE citation axis 의 동일 격상 패턴).
- `eval/external/wikimulti_cited_producer.py` — 본 cycle 구현 모듈.
- `eval/external/wikimulti_scorer.py` — Phase A.3 NLI-free set-F1
  scorer (변경 없음; `predicted_supporting_facts` consumption 그대로).
- `eval/external/wikimulti_loader.py` — Phase A.3 fixture loader
  (변경 없음; metadata.context_titles + context_sentences 가 producer
  prompt 의 ground).
- `tests/test_wikimulti_cited_producer.py` — 24 단위 테스트 (LLM 없이
  parser + prompt + bench row shape + scorer round-trip 검증).
- [[project_cycle_gamma_phase_c4_2wiki_smoke]] — preceding cycle state.
- [[feedback_self_evaluation_trap]] — fixture / scoring authority 외부
  = self-eval trap 통과 (gold supporting_facts 는 2Wiki 공식 fixture).
- [[feedback_finding_size_honest_framing]] — research-tier ≠
  publication-grade, paper publish-ready claim 금지.
