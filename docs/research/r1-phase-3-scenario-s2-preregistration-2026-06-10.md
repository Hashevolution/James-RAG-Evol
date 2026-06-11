# R1 Phase 3 — scenario-S2 사전 등록 (Pre-registration)

> **Zenodo deposit (priority anchor)**:
> [10.5281/zenodo.20635130](https://doi.org/10.5281/zenodo.20635130)
> — published 2026-06-11. The locking commit `d21c680` (2026-06-10)
> is the in-git priority evidence; this DOI is the external
> third-party timestamped record of that lock.

**Date**: 2026-06-10 (구현 + 측정 **전** 커밋 — R5 의무)
**Status**: LOCKED. 이 문서 commit 이후 시나리오 op 개수 / 어휘 basis /
보고 프로토콜 / honest-tier 게이트 변경 금지. 변경이 필요하면 사유를
본 문서에 append 하고 그 cycle 의 결과는 exploratory 로 강등.

**SPEC under test**: RAB SPEC v0.1.1 (FROZEN, `eval/rab/SPEC-v0.1.md`)
**Predecessor**: scenario-S1 (`eval/rab/scenarios/s1_lifecycle_small.json`)
**Scope**: scenario-S2 정의 + Phase 3 측정 보고 프로토콜.
**Why pre-register**: Phase 1 + Phase 2 의 결과(R1.4 / R1.5 + 4-SUT
gap)가 honest tier ⭐⭐ 에 머무는 가장 큰 이유 = single scenario.
S2 는 ⭐⭐⭐ 게이트 1차 시도이고, 시나리오-시스템 co-design 의심을
약화시키는 main mitigation. 사전 등록이 post-hoc 어휘 정렬을
구조적으로 차단한다.

---

## 1. 두 후보 중 하나 선택 (LOCK 시점에 단일 선택)

| | (A) Cross-lingual S2 | **(B) Larger-graph S2** ← 선택 |
|---|---|---|
| 동기 | 어휘 basis = 영어 가설 깨기 | RF-cost 컬럼이 현재 negligible → 의미를 가질 만큼 큰 graph |
| co-design 의심 약화 | 강 (vocabulary basis 변화) | 중 (op 개수 ↑, 어휘는 동일) |
| RF-cost 활성화 | 약 | 강 |
| Cycle γ "graph build O(N²)" finding 직접 활용 | 약 | 강 |
| 구현 비용 | 중 (Korean 합성 corpus) | 중 (큰 합성 corpus + checkpoint ↑) |

**선택 = (B) Larger-graph S2.** 이유:
- Cycle γ closure 의 graph build O(N²) finding 이 paper Future Work
  에서 명시되어 있는데 v0.1.1 측정에서 그 finding 이 *작동하는 모습*
  은 보이지 못함 (S1 graph 크기 negligible). S2 가 그걸 보임.
- 두 fail-mode 발견이 어느 SUT 가 어떤 axis 에서 부족한지 정밀화 했음
  — 즉 vocabulary basis 약점은 이미 §Limitations + Future Work 에서
  honest 하게 자인됨. 그 axis 의 추가 mitigation 은 (B) 보다 (C)
  replication invite (별도 collab arc) 가 더 직접적.
- 한국어 corpus 는 **S3** 로 자연 후속 (v0.1.2 spec bump + scenario set
  확장).

(A) 는 따라서 S3 후보로 같이 락 (이 doc 의 §6 참조). v0.1.2 release
prerequisite.

## 2. scenario-S2 설계 (LOCK)

| 항목 | 값 |
|---|---|
| 이름 | **lifecycle-large** |
| Spec 호환 | v0.1.1 (변경 X — scenario set 확장만, SPEC §3 의무 그대로) |
| Op 개수 | **400 op** (S1 40 op 의 10×) |
| 분포 | 110 INGEST / 40 UPDATE / 30 SUPERSEDE / 20 DELETE / 200 QUERY |
| Checkpoint 개수 | **40** (S1 10 의 4×) |
| 도메인 | 가상의 도시 운영(City Operations) — 부서/사업/계약/사건/문서. 합성 공개 도메인 영어 prose. 라이선스 friction 0. |
| Supersede chain shape | 평균 길이 ≥ 3 (S1 ≤ 2). 가장 긴 chain ≥ 5 hop 의무. |
| Cross-reference 밀도 | 한 문서가 평균 2.5 다른 문서를 supersede / refer-to (RF-cost graph build 의 O(N²) 가 의미를 가질 정도) |
| 식별자 | 결정적, `co-XXX-...` prefix |

S2 fixture 의 SHA 는 작성 후 hash-pin → SPEC §3 형식 `(spec v0.1.1,
scenario s2, scenario-sha)` 로 모든 결과에 함께 보고.

### 어휘 변경 정책

- **canonical 어휘 변경 0개** — S1 의 INGEST/UPDATE/SUPERSEDE/DELETE/
  QUERY 그대로 사용. S2 의 목적은 *graph 크기 활성화* 이지 어휘 변경
  아님.
- 어휘 변경은 S3 (cross-lingual) 또는 SPEC v0.2 의 별도 작업.

### Driver ground-truth canonical set

- S1 과 동일: {INGEST, UPDATE, SUPERSEDE, DELETE, ANSWER}.
- RETRIEVE / SYNTH / RERANK 는 여전히 SUT-internal — Baseline-1 의
  RETRIEVE event 가 S2 에서도 AC 미적용. 이건 의도된 선택, S1 의
  honest report 와 정합 (paper §10 명시).
- Future scenario (S2 자체 아님) 가 RETRIEVE 를 driver-side ground
  truth 로 올릴지는 별도 lock 대상.

## 3. 4 SUT 모두 측정 (재실행)

S1 결과는 v0.4.3 archive 에 영구. S2 결과는 별도 4 row:

| SUT | S1 결과 (v0.4.3 reference) | S2 측정 의무 |
|---|---|---|
| Reference | 1.000 / 1.000 / 1.000 | gate (1.000×3 안 나오면 driver/scorer 결함 — 측정 invalid) |
| JAMES | 1.000 / 1.000 / 1.000 | 측정 |
| Baseline-1 (OTel) | 0.500 / 0.000 / 0.000 | 측정 |
| Baseline-0 | 0.275 / 0.000 / 0.000 | 측정 |

S2 의 result.json 은 SPEC §4 의 동일 형식 + `scenario: "S2"` +
`scenario_sha: "<S2 sha>"`. S2 측정과 S1 측정 결과는 별도 row 로
보고, S1 number 와 S2 number 를 직접 합치지 않음 (각 scenario 의
honest 한 자기 수치).

## 4. RF-cost 활성화 가설 (사전 명시)

S1 의 RF-cost 컬럼 = ~0.0 s/1k events (작은 graph 라 fold 시간
무시 가능). **S2 가 활성화 가설**:

- Cycle γ Phase D 의 "graph build O(N²)" finding 이 진짜라면
  JAMES SUT 의 RF-cost ∝ N² with N = log event count
- 400 op × 평균 2 event = 800 events → fold 시간이 측정 가능 수준
- **사전 가설**:
  - JAMES RF-cost ≥ 0.05 s/1k events (S1 의 ~0 → S2 에서 측정 가능 수준)
  - JAMES RF-cost 가 S2 의 N² scaling 을 보이면 → finding 확정 → SPEC
    §2.2 의 "RF-cost is the scale axis" 가 evidence 동반
  - Baseline-1 / Baseline-0 의 RF-cost 비교 N/A (둘 다 empty replay)

### 결과 해석 룰

| 결과 패턴 | 해석 |
|---|---|
| JAMES RF-cost @ S2 ≥ 0.05 s/1k events, S1 의 ≥10× | ⭐⭐ **graph build O(N²) finding 외부 시나리오 재현 확정** — paper v2 의 RF-cost 컬럼 main finding 1개 추가 |
| JAMES RF-cost @ S2 < 0.05 s/1k events 또는 S1 ↔ S2 ratio < 5× | finding 미입증 — exploratory. SPEC §2.2 의 RF-cost 컬럼 정의는 유지, finding claim 만 보류 |
| JAMES RF-cost @ S2 > 1 s/1k events | operational concern — adapter 또는 reconstruct_graph_at 의 implementation 문제. v0.4.4 wiring follow-up cycle 과 합쳐 점검 |

## 5. 보고 프로토콜 (LOCKED)

R1.5 (PR #768 release notes) 와 정합. S2 release artifact:

1. **scenario fixture**: `eval/rab/scenarios/s2_lifecycle_large.json`
   (commit + hash-pinned)
2. **4 SUT result triple** (총 12 파일) under `reports/rab/`:
   - `<sut>-S2-<ts>.{result.json,log.jsonl,mapping.json}`
3. **Handover doc**: `docs/handovers/v0.4-r1-phase-3-s2-gap-table-<date>.md`
4. **(optional) Spec bump → v0.1.2**: scenario set 확장이 spec
   normative 의미를 가지면 (예: scenario contract §3 의 size guidance
   추가) v0.1.2 bump + changelog. 그렇지 않으면 v0.1.1 유지.

### 보고 시 의무 (R1.5 와 동일)

1. Gap table 이 headline. SCN-S1 결과와 직접 합치지 않음 (각 scenario
   의 자기 수치).
2. spec version + scenario sha 항상 동반.
3. re-verification triple 동봉.
4. "RAB 컴플라이언스 인증 아님" disclaimer 동일.
5. **JAMES wins framing 금지** (H5).
6. **mid-June joint piece 자동 연결 금지** (`feedback_eval_cycle_vs_collab_arc_separation`).

### honest-tier 사전 배정

| 결과 | 최대 tier |
|---|---|
| 4 SUT 모두 S1 패턴 재현 + RF-cost finding 확정 | **⭐⭐⭐ cross-scenario confirmed** (게이트 해제) |
| 4 SUT 패턴은 재현 / RF-cost finding 미확정 | ⭐⭐ cross-scenario partial + scale-axis pending |
| 4 SUT 중 1개 이상 다른 패턴 (예: JAMES < 1.000) | finding 아님 — wiring 또는 fixture 문제 진단 모드, exploratory 강등 |

## 6. Cell 유효성 / 무효 조건

- Reference 가 S2 에서도 1.000×3 못 맞추면 driver/scorer 결함 →
  scenario fix PR (exempt: fix) → 재실행.
- 어느 SUT 가 scenario 실행 중 예외로 중단되면 그 SUT 의 numbers
  는 "errored" 로 기록, 점수 채우지 않음.
- log_sha / mapping_table_sha / scenario_sha 빠지면 publishable 아님.
- 측정 후 mapping table / scenario / SPEC 변경은 spec bump 필요 (H6).

## 7. 금지 사항 (사전 명시)

1. **scenario sha 변경 후 같은 scenario 이름 유지 금지** — sha 변경
   = 새 scenario, 새 이름 (s2 → s2.1 등).
2. **S1 와 S2 의 점수 평균 / 합산 금지** — 각 scenario 의 자기 수치
   유지.
3. **RF-cost finding 이 S2 단일로 확정 안 됨** — N² scaling claim 은
   최소 2 scenario (S2 + 후속) data point 필요.
4. **Baseline-1 mapping table 변경 금지** in this cycle — OTel GenAI
   semconv 가 v0.1.1 frozen 이므로 어떤 mapping 도 변경 = post-hoc
   fit. mapping table 업데이트가 필요하면 별도 spec bump.
5. **사용자 catches 7-9번 룰 (single-axis ablation → defect framing
   금지, James != specialty, JAMES identity = measurement-driven)
   적용 계속**: S2 에서 nothing surprises 나오면 honest null 보고,
   surprise 가 나오면 multi-axis cross-cell 측정 prerequisite.

## 8. 실행 순서 (logical chain)

```
0. 이 사전 등록 commit                              ← P0 (이 단계)
1. scenario-S2 fixture 작성 + hash 핀
2. 단위 테스트 (S2 op 분포 검증 + Reference 1.000×3)
3. Reference re-run (S2 게이트 통과 확인)
4. 4 SUT 측정 → SPEC §4 triple × 4
5. RF-cost finding 해석 (§4 룰 적용)
6. Handover doc + (필요 시) spec v0.1.2 bump PR
7. paper v1.3 revision 결정 — S2 결과 추가 / Limitations item 1
   재고 / Future Work item 1 (scenario-S2) 제거
8. 별도: S3 (cross-lingual) sub-prereg — 본 doc 의 §1 (A) 옵션을
   v0.1.3 / S3 로 lock
```

예상 비용 (operator-time):
- scenario fixture 작성: 4-6h (400 op 결정적 + 평균 chain 길이 3 +
  cross-reference 밀도 유지)
- Reference test 게이트: 30분
- 4 SUT 측정 + handover: 2-3h
- 총 ~1-2 일 단일-cycle 작업 (대기 시간 X)

## 9. 사전 등록 commit hash = evidence

이 doc 의 첫 commit hash 가 사전 등록의 timestamped evidence. 측정
실행 전 PR 머지 + main 동기화 후 시작.

## 10. 관련

- [[project_r1_replayable_audit_benchmark]] — R1 트랙 상태
- [[feedback_self_evaluation_trap]] — R1 설계의 핵심 제약
- [[feedback_eval_cycle_vs_collab_arc_separation]] — joint piece 와의
  자동 연결 금지
- [[feedback_n1_verdict_inflation_n3_caught]] — single scenario 의
  ⭐⭐ ceiling 정합
- [[mechanism_layer_intent_axis_alignment]] — RF-cost 의 design-intent
  axis 정합 룰 (S2 가 그 axis 를 활성화)
- Cycle γ Phase D handover: `docs/handovers/v0.4-cycle-gamma-phase-c2-musique-retrieval-bottleneck-2026-06-10.md`
  (graph build O(N²) finding 출처)
- R1.5 release notes: `docs/release_notes_v0.4.3.md`
- Phase 2 handover: `docs/handovers/v0.4-r1-phase-2-baseline1-4sut-gap-2026-06-10.md`
- paper v1.2: `papers/rab-preprint/main.tex` (§10 Future Work track 1
  = scenario-S2+, 이 doc 가 그 트랙의 사전 등록)

---

*이 문서는 scenario fixture 작성 + 측정 실행 전 commit. Commit hash 가
사전 등록 증거. SPEC v0.1.1 frozen 동결 유지; S2 scenario 의 sha 는
fixture 작성 commit 에서 결정.*
