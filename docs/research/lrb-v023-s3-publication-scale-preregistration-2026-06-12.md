# LRB v0.2.3 — S3 publication-scale generator 사전 등록 (Pre-registration)

**Date**: 2026-06-12 (인프라 구현 + 측정 **전** 커밋 — R5 의무)
**Status**: LOCKED. 이 문서 commit 이후 generator vocabulary / scale preset
파라미터 / honest-tier 게이트 변경 금지. 변경이 필요하면 사유를 본
문서에 append 하고 그 cycle 의 결과는 exploratory 로 강등.

**Generator under test**: `scripts/research/build_lrb_scenario_s3.py`
(이 PR 신규). LRB v0.2.1 S2 (200 docs / 564 events / 80 queries)
의 publication-tier 확장. 동일 schema → 기존 `eval/external/lrb/driver.py`
변경 없이 consume 가능.

**Predecessors**:
- LRB v0.2.1 S2 cross-model ⭐⭐⭐ closed (4-model V<N<J, J@claude
  R@1=0.975, 이전 cycle)
- arXiv preprint Results §5 + Discussion §6 가 N=80 (S2) 기반 —
  publication-tier scale 은 reviewer pushback 대응용 보조 (submit
  pre-flight 아님)

**Why pre-register**:
1. S2 가 published artifact ⭐⭐⭐ 의 base — S2 fixture 는 절대
   변경 금지. S3 는 **별도** 시나리오 파일 / 별도 JSON 으로 격리
2. publication-scale (N=1000) 의 vocabulary / scale rule / event
   density 가 post-hoc tuning 으로 점수 inflate 되지 않도록 사전
   lock
3. publication-grade 라는 honest-tier 격상은 측정 결과 보고
   별도 cycle gate 필요 — 본 cycle 은 **generator infra only**

---

## 1. Scope — Phase v0.2.3 S3 가 측정할 것과 측정하지 않을 것

### 1.1 구현 (LOCK)

| 항목 | 값 |
|---|---|
| 모듈 | `scripts/research/build_lrb_scenario_s3.py` |
| 스케일 preset | `smoke` (10 dept / 100 docs / ~280 events / 100 queries) <br> `dev` (30 dept / 300 docs / ~1.2k events / 300 queries) <br> `publication` (100 dept / 1000 docs / ~5.6k events / 1000 queries) |
| Vocabulary | 프로그래매틱 (20 adj × 10 domain × 50 first × 40 last × …); 핸드-큐레이션 0; 100% deterministic |
| Schema | S2 identical: `scenario / name / spec / weeks / query_times / valid_times / initial_corpus / events / queries` |
| Determinism | byte-identical SHA across 두 번 재생성 (테스트 의무 pin) |
| Gold reachability | 모든 query gold doc_id 가 query_time 기준 reachable (테스트 의무 pin) |
| Honest tier | **infra-only — NOT publication-grade measurement** (측정 결과 보고 별도 cycle) |

### 1.2 구현 안 함 (Phase v0.2.3 S3 OUT of scope)

| 항목 | 사유 |
|---|---|
| 실제 측정 실행 (vanilla / naive / james 3-SUT × publication preset) | operator action; 이 PR 은 **generator only**. CPU LLM-grounded run = 천 단위 시간 |
| S2 fixture 변경 | 절대 금지 — published ⭐⭐⭐ artifact base |
| paper Results / Discussion 갱신 | publication-tier 측정 결과 보고 별도 cycle |
| publication-grade 측정 ranking | research-tier 측정과 별도 honest-tier |
| 비-civic 도메인 vocabulary | mother-platform rule #1 — domain-specific 금지 v1.0 까지 |

## 2. Pre-registered verdict matrix (측정 cycle, 다음 단계)

본 PR 은 generator 만 제공; 측정은 별도 cycle. 측정 결과 publication-
tier verdict 결정 표:

| publication scale 측정 결과 | Verdict | 후속 |
|---|---|---|
| publication 결과가 S2 cross-model V<N<J 패턴 reproduce + R@1 / EM / F1 band 가 S2 cell 의 ±0.05 안 | ⭐⭐⭐ publication-tier scale 강건성 검증 = S2 결과 scale 비의존 finding | paper Results §5 보조 표 / Discussion §6 limitations 항목 → "scale 1000 까지 동일 패턴" |
| publication 결과가 S2 패턴 reproduce 하나 magnitude 가 S2 와 다름 (Δ ≥ 0.05) | ⭐⭐ partial: pattern 강건 / magnitude scale-sensitive finding | paper Limitations 에 "magnitude scale-sensitive; pattern preserved" 명시 |
| publication 결과가 S2 패턴 reproduce 안 함 (V<N<J 깨짐 / J<N) | ⭐ scale-dependent finding (단, S2 publish-ready 결과는 단독 유효) | scale-attribution 별도 cycle; publication-tier paper claim 보류 |
| publication run crash / 측정 불가 | 인프라 결함 | producer / driver scale 디버그, fixture 재생성 retry |

## 3. Honest framing 의무

**본 PR**: `scripts/research/build_lrb_scenario_s3.py` 만 추가. fixture
JSON 파일은 commit 안 함 (operator 가 측정 시 직접 생성). 즉 본 PR 은
infra-only — `n_initial=1000` claim 도 메모만 가능, paper publish-ready
숫자 인용 금지.

**측정 cycle (다음 PR)**: 결과 result.json 에 다음 field 의무:

```json
{
  "scenario_spec":   "v0.2.3-draft-publication",
  "fixture_sha":     "<deterministic sha of S3 publication json>",
  "scale_preset":    "publication",
  "n_initial":       1000,
  "n_events":        <대략 5620>,
  "n_evaluations":   1000,
  "honest_tier":     "publication-tier-scale: ... STRONGER than S2 (N=80) ... but 측정-evidence depends on observed-vs-prereg matrix ..."
}
```

본 cycle (generator infra) 결과는 paper publish-ready claim 으로 인용
**금지**. publication-tier 측정 cycle 의 결과만 paper 인용 가능.

## 4. Cross-bench / cross-scale 표 update 룰

paper / cross-bench 표에 S3 row 가 갱신될 때:

```
| Scenario  | Scale preset      | N (init/events/queries) | R@1 (V/N/J) | Honest tier |
| S2        | (frozen v0.2.1)   | 200 / 564 / 80          | 0.6125 / 0.775 / 0.975 | ⭐⭐⭐ publication |
| S3        | publication       | 1000 / ~5620 / 1000     | <TBD>                  | <verdict-matrix-dependent> |
| S3        | dev               | 300 / ~1206 / 300       | DEFERRED               | NOT YET RUN |
| S3        | smoke             | 100 / ~282 / 100        | DEFERRED               | NOT YET RUN |
```

`scale_preset` column 필수. 단일 scale 점수 인용 금지 — S3 row 는
항상 S2 paired 비교로 표시 (scale-sensitivity 정량화).

## 5. 측정 실행 절차 (operator action, 다음 cycle)

```powershell
# 1. fixture 생성 (deterministic, write only — no LLM)
python scripts/research/build_lrb_scenario_s3.py --scale publication

# 2. publication-scale 측정 (vanilla / naive / james 3-SUT × token mode)
#    LLM-grounded mode 는 N=1000 × 3 SUT × claude API = 비용 무거움;
#    별도 cycle prereg 권장
python scripts/research/lrb_run_phase_b.py `
  --scenario eval/external/_fixtures/lrb/scenario_S3_publication.json `
  --mode token `
  --sut all
```

token mode 측정은 결정적 — 한 번 측정하면 충분. LLM-grounded mode 는
별도 cycle (S3 publication × LLM-grounded × claude / mxtral / …).

## 6. 인프라 완성 후 (v0.2.3 측정 cycle prerequisite)

| Phase | 작업 |
|---|---|
| v0.2.3a | token-mode S3 publication 측정 (3-SUT) → paper Results §5 보조 |
| v0.2.3b | LLM-grounded S3 publication 측정 (1+ 모델) → paper Discussion §6 보강 |
| v0.2.3c | cross-model S3 publication × 4 models → ⭐⭐⭐ scale 강건성 publication-tier |
| v0.2.4 | S3 publication × HR cross-NLI (hallucination resistance × scale) |

v0.2.3a 부터 별도 prereg 의무. 본 PR 은 generator infra LOCK 만.

## 7. 사전 등록 commit hash = evidence

이 doc 의 첫 commit hash 가 사전 등록의 timestamped evidence. 측정
실행 전 PR 머지 + main 동기화 후 시작.

## 8. 관련

- `scripts/research/build_lrb_scenario_s2.py` — S2 builder (변경 금지,
  ⭐⭐⭐ published artifact base).
- `scripts/research/build_lrb_scenario_s1.py` — S1 builder (변경 없음).
- `eval/external/lrb/driver.py` — S2 driver, S3 도 동일 consumer
  (schema identical).
- `eval/external/lrb/scorer.py` — S2 scorer, S3 도 동일.
- `tests/test_lrb_s3_generator.py` — 25 단위 테스트 (vocabulary
  primitives / scale preset 크기 / 결정성 / gold reachability / query
  분포 / schema 호환 / 중복 ID 부재 / scale monotonicity).
- `docs/research/lrb-v021-cross-model-preregistration-2026-06-11.md` —
  S2 cross-model prereg (sibling).
- [[project_lrb_phase_a_smoke]] — S1/S2 cycle state.
- [[feedback_self_evaluation_trap]] — fixture / scoring authority 외부
  = self-eval trap 통과 (S3 는 S2 와 동일 schema; scoring authority
  변경 없음).
- [[feedback_finding_size_honest_framing]] — infra-only ≠ measurement
  publication-grade, paper publish-ready claim 금지.
