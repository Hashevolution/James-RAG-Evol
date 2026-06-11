# LRB Phase B — time-travel 쿼리 사전 등록 (Pre-registration)

**Date**: 2026-06-11 (S2 fixture + 시간여행 axis 측정 **전** 커밋)
**Status**: LOCKED. 이 doc commit 후 scenario shape / SUT 구성 /
honest tier ladder / scoring axes 변경 금지.

**Bench under test**: LRB Phase B (scenario-S2 + time-travel
extension), 사전 정의 path = LRB v0.1.0 draft 확장.

**Predecessors**:
- LRB design memo (PR #782)
- LRB Phase A prereg (PR #783)
- LRB Phase A 결과 (handover doc, this session)
- **★Phase A의 critical honest finding (2026-06-11)**: naive-supersede
  SUT = JAMES on Phase A S1 (R@10 / R@1 / temporal_acc 모두 0 delta).
  Phase A 의 "JAMES > Vanilla" gap 의 **모든** magnitude 가 "supersede-
  aware" mechanism으로 설명됨. Validity-window 기여 = Phase A 측정 안 됨.

**Why pre-register Phase B**: Phase A 가 자메스 validity-window 의
contribution을 측정하지 못했음을 self-honest 인지. **JAMES validity-
window 가 supersede-aware-RAG 와 차별되는 유일한 axis = time-travel
쿼리** (운영 시점 T 에 valid_at(t') 별도 쿼리, t' ≠ T). 이걸 측정
못하면 자메스 lifecycle architecture 의 contribution claim 자체가
publishable evidence 없음.

**Why now (전체 트랙과의 정합)**: LRB Phase A 의 honest finding 직후
즉시 Phase B 사전등록 lock 으로 post-hoc framing fit 차단
([[feedback_finding_size_honest_framing]] + cycle γ 의 prior art 정정
패턴 mirror).

---

## 1. Scope — Phase B 가 측정할 것과 측정하지 않을 것

### 1.1 측정 (LOCK) — Phase B smoke + cross-scenario

| 항목 | 값 |
|---|---|
| Scenario A | **LRB-S1 (lifecycle-quarterly)** — Phase A 와 동일, 동일 fixture sha |
| Scenario B | **LRB-S2 (lifecycle-yearly-with-time-travel)** — 신규 |
| LRB-S2 initial corpus | 200 docs (RAB S2 city-operations vocabulary 확장; license friction 0) |
| LRB-S2 Evolution | 24 weeks; 매주 12-18 lifecycle events |
| LRB-S2 Total events | ~360 (Phase A 의 1.8x) |
| LRB-S2 Query set | 80 queries × **4 query-types** = 320 evaluations |
| **SUT (Phase B — 3 SUT)** | **Vanilla + Naive-supersede + JAMES** |
| Model | deterministic token-overlap (LRB v0.1 정합; no LLM) |
| n_runs | 1 (deterministic single-run) |
| Honest tier | **⭐⭐ (validate cross-scenario) → ⭐⭐⭐ candidate (gap order reproduced + time-travel axis JAMES uniquely > 0)** |

### 1.2 핵심 신규 axis — time-travel query

| Query type | 비중 | 정의 | SUT 별 expected |
|---|---|---|---|
| **current** | 50% (40 q) | "현재 (T=24w) 디렉터?" — query_time = valid_time = 24w | 3 SUT 모두 가능 |
| **historical-mid** | 25% (20 q) | "T=8w 시점 디렉터?" — query_time=24, valid_time=8 | Vanilla / Naive 부재 (현재만 보유), JAMES 가능 |
| **historical-early** | 12.5% (10 q) | "T=0 시점 (initial) 디렉터?" | Vanilla 우연히 가능 (못 지운 doc), Naive 불가, JAMES 가능 |
| **never-stale** | 12.5% (10 q) | "현재 budget allocation?" — UPDATE 만, no SUPERSEDE | 3 SUT 모두 가능 |

→ Time-travel axis 가 Phase B 의 critical differentiator. JAMES
validity-window 의 **유일한 publishable contribution**.

### 1.3 측정 axes (Phase B — LOCK, 7 + 3)

deterministic only, RAB H1 정합:

| Axis | 정의 | Per-SUT emit |
|---|---|---|
| **R@5** / **R@10** | gold supporting docs ∩ top-k / \|gold\| (per (query, valid_time)) | ✓ |
| **P@5** / **P@10** | gold supporting docs ∩ top-k / k | ✓ |
| **Latency** | retrieve_at wall-clock per query | ✓ |
| **Token cost** | retrieved-context tokens per query | ✓ |
| **temporal_accuracy** | (R@10 == 1.0) per evaluation, mean | ✓ |
| [exp] R@1 / P@1 / strict-top1 | 사용자 첫 결과 정확도 (Phase A 정합) | ✓ |

### 1.4 honest-tier ladder (LOCK) — Phase B 의 결정

| Result shape | Tier |
|---|---|
| 3 SUT 모두 axes emit + **JAMES > Naive-supersede on time-travel axis** + naive-supersede > Vanilla on current axis | **⭐⭐⭐ cross-scenario gap structure validated + validity-window contribution measured** |
| 3 SUT 모두 axes emit + JAMES ≈ Naive on time-travel axis + naive > Vanilla on current | **⭐⭐ honest negative on validity-window axis** — supersede-aware는 충분, validity-window 비기여. cycle 의 critical honest finding 으로 paper. |
| JAMES < Naive on time-travel axis | **⭐ surprising negative** — JAMES adapter 가 실제 inferiority. root-cause cycle 별도 |
| S1 의 gap order 와 S2 의 gap order 가 다름 (cross-scenario non-reproduction) | **⭐ exploratory** — S2 가 self-eval trap 으로 reduce, S1 만 valid |
| 한 SUT exception / no axes | exploratory, fix-PR 별도 |

**Magnitude framing 금지**: Phase B smoke 의 absolute values 는
cross-model / cross-corpus 확인 전 publication-tier claim 금지.

### 1.5 측정하지 **않음** (Phase B — LOCK)

| 항목 | 사유 |
|---|---|
| Microsoft GraphRAG SUT | Phase C / LRB v0.2 publication |
| ActiveGraph SUT | LRB v0.2 publication (collab invite) |
| Hallucination Resistance (HR) NLI axis | LRB v0.2 |
| Cross-model (gemma3:12b / mxtral) | 별도 cycle |
| Korean / cross-lingual scenarios | LRB v0.3 candidate |
| 1000+ docs / 10K events | LRB v0.2 S3 (publication tier) |

## 2. Driver extension — `retrieve_at(q, k, query_time, valid_time)`

신규 driver interface:
```python
def retrieve_at(q: str, k: int, query_time: int,
                valid_time: int) -> List[str]:
    """Retrieve top-k doc_ids valid at `valid_time`, with the SUT
    state up to `query_time`. query_time >= valid_time always."""
```

SUT 별 구현:
- **Vanilla**: ignores `valid_time`, returns top-k from current index
  (= state at query_time). Historical 쿼리는 deterministically wrong.
- **Naive-supersede**: ignores `valid_time`, returns top-k from current
  index. Historical 쿼리는 deterministically wrong.
- **JAMES**: filters docs by `valid_at(valid_time)`. Historical
  쿼리 정확.

기존 Phase A `retrieve(q, k, t_week)` interface 유지 (default
valid_time = t_week, query_time = t_week). 후방 호환.

## 3. Scenario fixture — LRB-S2 (생성 deferred until lock)

| 항목 | 결정 |
|---|---|
| Scenario fixture file | `eval/external/_fixtures/lrb/scenario_S2_yearly_timetravel.json` |
| Generator script | `scripts/research/build_lrb_scenario_s2.py` |
| 200 docs vocabulary | RAB S2 city-operations 확장 (도시 2배 — 20 dept, 60 projects, 40 contracts, 20 budgets, 40 policies, 20 appointments) |
| 24 weeks 의 이벤트 schedule | deterministic, 8/8/8/8 director SUPERSEDE 분포 (weeks 4/8/12/16/20 등) |
| Query gold (per query_time + valid_time) | manually curated. 80 queries × 4 query-types (current / historical-mid / historical-early / never-stale) |

generator + fixture 작성 시점에 fixture sha 결정. 측정 = sha hash-pin 후만.

## 4. 보고 프로토콜 (LOCK)

### 4.1 산출물 (5 파일)

1. `reports/external/lrb/phase-b-cross-scenario-<ts>.<sut>.result.json` (per SUT × per scenario)
2. `reports/external/lrb/phase-b-cross-scenario-<ts>.<sut>.bench.jsonl`
3. `reports/external/lrb/phase-b-gap-table-<ts>.md` (cross-scenario gap structure)
4. `docs/handovers/v0.4-lrb-phase-b-results-<date>.md`
5. memory entry update [[project_lrb_phase_a_smoke]] → Phase B section

### 4.2 보고 시 의무

1. ⭐⭐⭐ / ⭐⭐ / ⭐ tier 명시 (§1.4 의 verdict 그대로)
2. cross-scenario gap structure (S1 의 ranking 이 S2 에서 cell-by-cell
   재현 되는지 — RAB Phase 3 의 패턴)
3. Phase A 의 honest finding (naive ≈ JAMES on S1) 보존 — Phase B 가
   이 finding 을 부정 아닌 보완
4. NOT publication framing (Phase C cross-model + ActiveGraph
   까지)
5. mid-June joint piece 자동 연결 금지

### 4.3 금지 사항

1. Phase A 의 finding "naive ≈ JAMES" 를 Phase B 결과로 retroactive
   덮기 → post-hoc framing 위반
2. time-travel axis 에서 JAMES > Naive 가 측정되더라도 "JAMES wins
   benchmark" 류 magnitude claim → 단일 fixture / 단일 query distribution
   기반 over-claim
3. Gold relabel after measurement
4. GraphRAG / ActiveGraph 의 estimated 점수 인용

## 5. 인프라 reuse

기존 LRB Phase A 인프라 그대로 사용 + 다음 확장:

| 위치 | 역할 |
|---|---|
| `eval/external/lrb/driver.py` | `retrieve_at` 시그너처 확장 + cross-scenario loop |
| `eval/external/lrb/scorer.py` | 동일 (axes 동일) |
| `eval/external/lrb/adapters/vanilla.py` | `retrieve_at` = `retrieve` (ignore valid_time) |
| `eval/external/lrb/adapters/naive_supersede.py` | `retrieve_at` = `retrieve` (ignore valid_time) |
| `eval/external/lrb/adapters/james.py` | `retrieve_at` 정확 구현 (valid_at(valid_time) 필터) |
| `scripts/research/build_lrb_scenario_s2.py` | 신규 |
| `scripts/research/lrb_run_phase_b.py` | 신규 (cross-scenario runner) |

Phase B 신규 코드 surface ≈ 800 줄 (driver extension + S2 generator
+ Phase B runner).

## 6. 실행 순서 (logical chain)

```
0. 이 사전 등록 commit                            ← P0 (이 단계)
1. build_lrb_scenario_s2.py 작성 + 실행
   → eval/external/_fixtures/lrb/scenario_S2_yearly_timetravel.json (sha pin)
2. retrieve_at(query_time, valid_time) interface 확장 (3 adapter)
3. driver cross-scenario loop
4. Phase B smoke run (3 SUT × 2 scenarios)
5. cross-scenario gap table + handover doc + memory update + PR
```

예상 비용:
- S2 generator + fixture: 2-3h
- adapter retrieve_at extension: 1h
- driver / runner: 1h
- smoke run: <1min (deterministic)
- handover: 1h
- 총 ~5-6h 단일-cycle 작업

## 7. ⭐⭐⭐ tier 진입 의미 — 외부 인정 요건

본 cycle (Phase B) 가 ⭐⭐⭐ 진입 시:
- 3 SUT × 2 scenario × 7+3 axes 의 deterministic gap structure
- JAMES validity-window mechanism 의 contribution measured (time-travel axis)
- cross-scenario reproduction = self-eval trap mitigation 강화

⭐⭐⭐ 진입 후에도 publication tier 는 아직 → 추가 요건:
- Cross-model (Phase C — gemma3:12b / mxtral / claude)
- ActiveGraph SUT (LRB v0.2 publication, collab invite)
- 1000+ docs / 10K events scenario (LRB v0.2 S3)
- HR (Hallucination Resistance) NLI axis (LRB v0.2 + verifier dep)

LRB v0.2 publication 까지의 길은 **분명히 정의**되어 있음. Phase B 가
첫 milestone.

## 8. 관련

- [[project_lrb_phase_a_smoke]] — Phase A 결과 + naive-supersede ≈ JAMES finding
- [[project_r1_replayable_audit_benchmark]] — RAB sibling axis
- [[feedback_self_evaluation_trap]] — fixture / SUT discipline
- [[feedback_finding_size_honest_framing]] — magnitude framing 룰
- [[feedback_single_axis_ablation_misframing]] — 단일-axis chase 금지
- [[feedback_eval_cycle_vs_collab_arc_separation]] — joint piece 자동 연결 금지
- [[feedback_james_identity_measurement_driven]] — measurement evidence conditional
- design memo: `docs/design/v0.4-lrb-lifecycle-retrieval-benchmark-design.md`
- Phase A prereg: `docs/research/lrb-phase-a-smoke-preregistration-2026-06-11.md`
- Phase A handover: `docs/handovers/v0.4-lrb-phase-a-results-2026-06-11.md`

## 9. 사전 등록 commit hash = evidence

이 doc 의 첫 commit hash 가 사전 등록 timestamped evidence.
scenario S2 generator + adapter extension + 측정 실행 **전** PR 머지.

---

*Time-travel axis = JAMES validity-window의 measurable contribution.
Phase A의 honest negative (naive ≈ JAMES on current axis)를 보완하는
방식으로 Phase B 가 진행. 결과는 cross-scenario gap structure + tier
ladder 안에서만 보고.*
