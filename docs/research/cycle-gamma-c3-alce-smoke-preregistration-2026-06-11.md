# Cycle γ Phase C.3 — ALCE smoke 사전 등록 (Pre-registration)

**Date**: 2026-06-11 (구현 + 측정 **전** 커밋 — R5 의무)
**Status**: LOCKED. 이 문서 commit 이후 fixture 선택 / verifier 종류 /
보고 honest-tier 게이트 변경 금지. 변경이 필요하면 사유를 본 문서에
append 하고 그 cycle 의 결과는 exploratory 로 강등.

**Bench under test**: ALCE (Gao et al. 2023, EMNLP) — `eval/external/
alce_loader.py` + `eval/external/alce_scorer.py` (코드 인프라는
Phase A 시점에 박혀있음; 실제 측정 미진행).

**Predecessors**:
- Cycle γ Phase B (RGB) + Phase C.2 (MuSiQue) 측정 완료
- cycle γ design memo `docs/design/v0.4-cycle-gamma-external-
  benchmark-integration.md` §C.1 항목 (ALCE = 4-벤치 중 1, citation
  axis).

**Why pre-register**: cycle γ design memo 가 약속한 4-벤치 cross-
confirm 중 ALCE 가 미진행 = publication-grade 4/4 promise 의 1/4
미달. RAB SPEC v0.1.1 의 PC metric (Provenance Coverage) 이 cited-
source chain 측정인데, ALCE 가 그 외부 검증 axis. 사전 등록은
post-hoc verifier 변경 / fixture cherry-pick / scope creep 을 구조적
으로 차단한다.

**Why now (RAB 와의 시너지)**: paper v1.3 가 PC = traceable
citations / total citations (deterministic, RAB SPEC §2.3) 를
publish-ready. ALCE = NLI-based citation entailment 의 표준. RAB
PC = "citation chain reachable from log" (audit-side), ALCE = "cited
passage entails the claim" (semantic-side). 두 axis 가 다른 dimension
이지만 PC story 의 outer validation 으로 paper v1.4 후속 PR
evidence 가 됨 (arXiv submit 후 v1.4 revision 자연 step).

---

## 1. Scope — Phase C.3 가 측정할 것과 측정하지 않을 것

### 1.1 측정 (LOCK)

| 항목 | 값 |
|---|---|
| Variant | **ASQA 만** (asqa). qampari / eli5 는 별도 Phase C.3+ 후속 |
| Sample 수 | **N=20** (smoke; ALCE eval 의 typical full = 1000) |
| Retriever | gtr (ALCE 의 default 그대로; JAMES retrieval 우회) |
| Verifier | **`StringContainmentVerifier(min_overlap=0.5)`** — fallback only |
| Honest tier | **⭐ infrastructure validation only — NOT publication, NOT ALCE-grade** |

### 1.2 측정하지 **않음** (LOCK)

| 항목 | 사유 |
|---|---|
| Full ALCE-grade (T5-XXL TRUE NLI Mixture) | 모델 ~11GB, 로컬 inference 무거움, paper publish-ready scores 별도 cycle 의무 |
| QAMPARI / ELI5 variants | smoke scope 외, infrastructure 검증은 asqa 1개 variant 면 충분 |
| JAMES retrieval ablation | ALCE 가 정의된 retriever (gtr) 그대로 사용, "내 retrieval 자랑" 우회 ([[feedback_self_evaluation_trap]]) |
| N>20 | smoke scope 외; cycle β / γ 의 "n=1/n=3 paired" 규칙 ([[feedback_n1_verdict_inflation_n3_caught]]) 가 smoke 단계에 적용 안 됨 (publication tier 가 아니므로). 다만 결과 magnitude framing 시 "smoke n=20 ⭐ infrastructure-only" 강제 명시 |

### 1.3 honest-tier 가능 결과 (LOCK)

| 결과 | tier | meaning |
|---|---|---|
| 인프라 작동 + citation_precision / citation_recall 둘 다 emit | **⭐ infrastructure validated** | "ALCE adapter + JAMES post-processor 가 작동, 측정 가능" 만 — magnitude claim 없음 |
| 인프라 작동 + 0.0/0.0 (citations [N] 미출현) | **⭐ infrastructure validated + citation-emit 결손 finding** | JAMES adapter 가 inline [N] citation 형식으로 답 못 만듦. paper v1.4 §Limitations 에 명시 + Phase D ALCE-grade-real-NLI cycle prerequisite |
| 인프라 실패 (예외 / score 0개) | exploratory | 측정 invalid, fix PR 별도, 본 cycle 의 결과 사용 안 함 |

**Magnitude 비교 금지** = string-containment fallback (NOT ALCE-
grade) 의 absolute 값은 RGB / MuSiQue 점수와 다른 dimension. 같은
표에 적을 수 있음 (cross-bench 표) 단 `verifier_grade` column 명시
의무.

## 2. JAMES adapter 의 contract (LOCK)

ALCE answer format = sentence-level citations:
```
"Foo is the answer [1]. Bar is also true [2, 3]."
```

JAMES engine.query 는 dict 반환:
```python
{"answer": "...", "sources": ["doc-id-1", "doc-id-2"], ...}
```

→ **JAMES → ALCE post-processor** (`eval/external/_alce_post.py`,
neutral location):
1. JAMES `answer` 의 sentences split
2. 각 sentence 에 1개 이상 `[N]` citation 부착 (1-based, sources order)
3. 모든 sentence 가 `[N]` 부착되면 ALCE citation_recall denominator
   = n_sentences. 부착 없으면 denominator = 0 (axis 미측정 reporting)
4. 단순 heuristic: 각 sentence 에 모든 source id 부착 (`[1, 2, 3]`)
   = ALCE precision 의 lower bound (모든 citation 평가됨)
   = recall 의 upper bound (sentence 마다 적어도 1개 entail 시 OK)

이 post-processor 의 "naive 모든-citation-부착" mechanism 자체가
JAMES adapter 의 fallback. 더 정교한 sentence-grounded citation
attribution 은 paper v1.4 추가 작업.

## 3. fixture / data download (LOCK)

| 단계 | 명령 |
|---|---|
| Download | `python scripts/research/download_alce.py --variant asqa` |
| Cache dir | `eval/external/_fixtures/alce/data/` |
| Expected file | `asqa_eval_gtr_top100.json` |
| Source | HuggingFace `princeton-nlp/ALCE-data` (tarball) |
| License | MIT (ALCE) |

download_alce.py 가 download_musique.py 패턴 mirror. tarball 1개
download + extract.

## 4. 실행 순서 (logical chain)

```
0. 이 사전 등록 commit                              ← P0 (이 단계)
1. download_alce.py 작성 + 실행 → fixture 확보
2. JAMES → ALCE post-processor 작성 + tests
3. smoke run script (eval/external/runner.py + ALCEScorer + Loader)
4. asqa N=20 측정 1회 (deterministic; no n=3 paired smoke 단계)
5. handover doc + memory entry + PR
```

예상 비용 (operator-time):
- download_alce.py + 실행: 30분
- JAMES → ALCE post-processor + tests: 1-2h
- runner script + smoke: 1h
- handover doc + memory entry: 30분
- 총 ~3-4h 단일-cycle 작업

## 5. 보고 프로토콜 (LOCK)

### 5.1 산출물 (4 파일)

1. `reports/external/alce/asqa-smoke-<ts>.result.json` (axes +
   verifier name + is_alce_grade + sample n + fixture sha)
2. `reports/external/alce/asqa-smoke-<ts>.bench.jsonl` (per-query
   model answer + citations + supported 판정)
3. `docs/handovers/v0.4-cycle-gamma-phase-c3-alce-smoke-<date>.md`
4. `memory/project_cycle_gamma_phase_c3_alce_smoke.md`

### 5.2 보고 시 의무

1. **⭐ infrastructure-only** tier 가 모든 자리에 명시
2. **NOT ALCE-grade** disclaimer (string-containment fallback)
3. **citation_precision / citation_recall** 둘 다 emit (axis-by-axis)
4. cross-bench 표에 ALCE 셀 추가 시 `verifier_grade` column 의무
5. "ALCE paper 의 published numbers 와 직접 비교 금지" 명시
6. mid-June joint piece 자동 연결 금지
   ([[feedback_eval_cycle_vs_collab_arc_separation]])

### 5.3 금지 사항

1. **NLI verifier 변경 후 사전 등록 미수정** (post-hoc) — 변경 시
   별도 cycle, exploratory 강등
2. **fixture cherry-pick** (예: "ASQA 의 첫 20 query 만" 외 sampling)
   — loader 의 `n_samples=20` 만 사용
3. **JAMES retrieval 우회 → JAMES retrieval 자랑** framing — ALCE
   는 retrieval-fixed (gtr) bench, retrieval comparison axis 아님
4. **ALCE-grade scores publish-ready claim** in this cycle — 별도
   ALCE-grade cycle 까지 보류

## 6. 인프라 완성 후 (Phase C.3 OUT of scope, 다음 cycle prerequisite)

| Phase | 작업 |
|---|---|
| C.3+ | qampari / eli5 variants smoke (string-containment 동일) |
| D-alce | T5-XXL TRUE NLI 또는 RoBERTa-NLI 통합 (ALCE-grade) |
| D-alce | full N=300-1000 측정 (publication-grade) |
| E-alce | paper v1.4 § "ALCE outer validation" — Provenance Coverage 의 NLI-grounded 외부 검증 |

D-alce 부터는 별도 사전등록 + ALCE-grade tier promotion 의 별도
honest-tier 게이트.

## 7. 사전 등록 commit hash = evidence

이 doc 의 첫 commit hash 가 사전 등록의 timestamped evidence.
측정 실행 전 PR 머지 + main 동기화 후 시작.

## 8. 관련

- [[project_r1_replayable_audit_benchmark]] — R1 RAB PC metric 의
  citation chain (audit-side, deterministic). ALCE = NLI-grounded
  (semantic-side). 두 axis 가 paper v1.4 의 PC outer validation.
- [[feedback_self_evaluation_trap]] — fixture / scoring authority
  외부 = self-eval trap 통과
- [[feedback_finding_size_honest_framing]] — string-containment
  fallback 의 magnitude framing 의무
- [[feedback_n1_verdict_inflation_n3_caught]] — smoke n=20 ⭐
  infrastructure-only 강제 명시 (n=3 paired 요구는 publication-tier 만)
- [[mechanism_layer_intent_axis_alignment]] — ALCE axis = citation,
  JAMES adapter 의 intent = answer + sources 분리. 직접 매칭 아닌
  post-processor layer 의 의무.
- design memo: `docs/design/v0.4-cycle-gamma-external-benchmark-
  integration.md` §C.1

---

*이 문서는 fixture 작성 + 측정 실행 전 commit. Commit hash 가 사전
등록 증거. SPEC v0.1.1 frozen 동결 유지; ALCE fixture 의 sha 는
download 이후 결정.*
