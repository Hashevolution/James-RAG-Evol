# Cycle γ Phase C.4 — 2WikiMultiHopQA smoke 사전 등록 (Pre-registration)

**Date**: 2026-06-11 (구현 + 측정 **전** 커밋 — R5 의무)
**Status**: LOCKED. 이 문서 commit 이후 fixture 선택 / split / N /
producer / honest-tier 게이트 변경 금지. 변경 시 사유 append + 그
cycle 결과 exploratory 강등.

**Bench under test**: 2WikiMultiHopQA (Ho et al. 2020,
COLING) — `eval/external/wikimulti_loader.py` +
`eval/external/wikimulti_scorer.py` (Phase A 코드 박힘, 측정 미진행).

**Predecessors**:
- Cycle γ Phase B (RGB) + C.2 (MuSiQue) + C.3 (ALCE smoke) 측정 완료
- cycle γ design memo `docs/design/v0.4-cycle-gamma-external-
  benchmark-integration.md` §C.4 항목 (2Wiki = 4-벤치 중 4, multi-
  hop cross-bench confirm).

**Why pre-register**: cycle γ 4-벤치 promise 의 마지막 leg
(RGB ✓ + MuSiQue ✓ + ALCE ⭐ smoke ✓ + **2Wiki ❌**) 채움. multi-hop
arc closure (PR #756) 가 MuSiQue 단일 fixture 위에서 종결됐으므로,
2Wiki cross-bench reproduction 이 그 finding 의 외부 일관성 evidence.

**Why now (RAB 와의 시너지)**: ALCE smoke 와 같은 ⭐ infrastructure-
validation tier — RAB submission B-C-D 진행 중에 main code base
작업으로 진행 가능. 측정 magnitude 보다 인프라 + cross-bench
reproduction pattern 자체가 paper v1.4 후속 PR 의 inline note 가능.

---

## 1. Scope — Phase C.4 가 측정할 것과 측정하지 않을 것

### 1.1 측정 (LOCK)

| 항목 | 값 |
|---|---|
| Split | **dev** (official dev; train + test 제외) |
| Sample 수 | **N=20** (smoke; 2Wiki dev = ~12,576 official) |
| Producer | **`ClosedCorpusGemmaProducer`** (eval/external/runner.py 기존 사용; new producer 작성 안 함) |
| Model | **gemma4:e4b** (cycle β/γ baseline; Phase C.3 ALCE smoke 와 정합) |
| max_tokens | 1024 |
| Honest tier | **⭐ infrastructure validation + cross-bench multi-hop reproduce** — NOT publication |

### 1.2 측정하지 **않음** (LOCK)

| 항목 | 사유 |
|---|---|
| support_fact_f1 | `ClosedCorpusGemmaProducer` 가 `predicted_supporting_facts` 안 emit → scorer 가 "not measured" axis 로 자동 surface ([wikimulti_scorer.py L87-105](../../eval/external/wikimulti_scorer.py)). publication-tier supporting fact prediction 은 별도 D-2wiki cycle. |
| qampari / eli5-style citation | 2Wiki 는 short-answer QA, citation format 무관 |
| JAMES retrieval | closed-corpus mode (loader 의 published 10 paragraphs 그대로 inject). "내 retrieval 자랑" 우회 ([[feedback_self_evaluation_trap]]). JAMES engine 우회. |
| N>20 | smoke scope 외 |
| Cross-model (mxtral / gemma3:27b 등) | smoke scope 외 |
| 4 question types 별 통계 평가 | f1_by_type axis 는 emit (scorer 가 자동 계산) 단 magnitude 의 type-별 framing 금지 (n=20 sample 적음) |

### 1.3 honest-tier 가능 결과 (LOCK)

| 결과 | tier | meaning |
|---|---|---|
| 인프라 작동 + em/f1 둘 다 emit + magnitude in known multi-hop floor (em < 0.2, f1 < 0.3) | **⭐ infrastructure validated + cross-bench multi-hop floor reproduced** | "MuSiQue 의 multi-hop floor finding (Phase C.2) 가 2Wiki 에서 cross-bench reproduce". cycle γ multi-hop arc closure 의 외부 일관성 evidence. |
| 인프라 작동 + magnitude 큰 (em > 0.3 또는 f1 > 0.5) | **⭐⭐ surprising — Phase D-2wiki 진입 evidence** | 단순 closed-corpus baseline 이 multi-hop 잘 풀음 = 추가 측정 필요 (cycle γ MuSiQue arc closure 의 cross-bench challenge). 별도 사전등록으로 D-2wiki 진입. |
| 인프라 실패 (exception / no axes) | exploratory | 측정 invalid, fix PR 별도, 본 cycle 결과 사용 안 함 |

**Magnitude 의 직접 비교 금지** = 2Wiki vs MuSiQue 점수 직접 비교 금지
(다른 fixture, 다른 question type composition, 다른 paragraph 평균
길이). cross-bench reproduce 의미는 "floor pattern" 의 정성 일치만.

## 2. 인프라 (LOCK)

| 위치 | 역할 |
|---|---|
| `eval/external/wikimulti_loader.py` | Phase A 박힘 — dev/train/test split, 10 paragraphs × per-sentence list, 4 question types, supporting_facts 메타 |
| `eval/external/wikimulti_scorer.py` | Phase A 박힘 — em / f1 (SQuAD-norm), support_fact_f1 (predicted_supporting_facts 있을 때만), f1_by_type |
| `eval/external/runner.py::ClosedCorpusGemmaProducer` | Phase A 박힘 — 모든 query.context 를 prompt 에 inject |
| `scripts/research/download_2wiki.py` | 본 사전등록 후 작성 — fixture 다운로드 (HuggingFace mirror 우선, Dropbox fallback) |
| `scripts/research/wiki2_smoke_run.py` | 본 사전등록 후 작성 — alce_smoke_run.py mirror, locked args |

## 3. fixture / data download (LOCK)

| 단계 | 명령 |
|---|---|
| Download | `python scripts/research/download_2wiki.py --split dev` |
| Cache dir | `eval/external/_fixtures/wikimulti/` |
| Expected file | `dev.json` |
| Source | HuggingFace mirror (`xanhho/2WikiMultihop` 또는 동등) 우선, Dropbox (`https://www.dropbox.com/s/npidmtadreo6df2/data.zip`) fallback |
| License | MIT (official 2Wiki; Wikipedia content CC-BY-SA) |

download_2wiki.py 가 download_alce.py 패턴 mirror. fixture 의 hash
(sha256) 는 다운로드 후 결정.

## 4. 실행 순서 (logical chain)

```
0. 이 사전 등록 commit                              ← P0 (이 단계)
1. download_2wiki.py 작성 + 실행 → fixture 확보
2. smoke run script (alce_smoke_run.py mirror)
3. dev N=20 측정 1회 (deterministic; no n=3 paired smoke 단계)
4. handover doc + memory entry + PR
```

예상 비용 (operator-time):
- download_2wiki.py + 실행: 30분
- smoke script + 실행: 30분 (~1-2분 측정)
- handover + memory + PR: 30분
- 총 ~1.5h 단일-cycle 작업 (ALCE 보다 simpler — new producer 안 만듦)

## 5. 보고 프로토콜 (LOCK)

### 5.1 산출물 (4 파일)

1. `reports/external/2wiki/dev-smoke-<ts>.result.json` (axes +
   producer name + fixture sha + sample n + tier)
2. `reports/external/2wiki/dev-smoke-<ts>.bench.jsonl` (per-query
   model answer + question type)
3. `docs/handovers/v0.4-cycle-gamma-phase-c4-2wiki-smoke-<date>.md`
4. `memory/project_cycle_gamma_phase_c4_2wiki_smoke.md`

### 5.2 보고 시 의무

1. **⭐ infrastructure-only** tier 가 모든 자리에 명시
2. **NOT publication** — magnitude framing 금지
3. **em / f1 / f1_by_type** axes emit; support_fact_f1 = "not measured"
   (의도 — producer 가 안 emit)
4. **MuSiQue vs 2Wiki magnitude 직접 비교 금지** — cross-bench
   reproduction 의미는 "floor pattern" 의 정성 일치만
5. cross-bench 표에 2Wiki 셀 추가 시 N=20 smoke 명시
6. mid-June joint piece 자동 연결 금지
   ([[feedback_eval_cycle_vs_collab_arc_separation]])

### 5.3 금지 사항

1. **Producer 변경 후 사전 등록 미수정** (post-hoc) — `JamesEngineProducer`
   사용 또는 prompt 수정 = self-eval trap 위반 + exploratory 강등
2. **fixture cherry-pick** (예: "특정 type 만") — loader 의
   `n_samples=20` deterministic prefix 만 사용
3. **support_fact_f1 axis 보충 측정** (publication-tier supporting
   fact prediction) — 별도 D-2wiki cycle 까지 보류
4. **MuSiQue 결과와 magnitude 직접 비교** — cross-bench floor 정성
   reproduction 만 허용

## 6. 인프라 완성 후 (Phase C.4 OUT of scope, 다음 cycle prerequisite)

| Phase | 작업 |
|---|---|
| C.4+ | train split smoke (optional, supplementary) |
| D-2wiki | **predicted_supporting_facts producer** 작성 (JAMES adapter 가 supporting facts 추출 emit) → support_fact_f1 axis 활성 |
| D-2wiki | full N=1000+ dev 측정 (publication-tier) |
| D-2wiki | cross-model (mxtral / gemma3:27b) reproduce |
| E-2wiki | paper v1.4 § "Multi-hop QA cross-bench reproduce" (MuSiQue + 2Wiki) — multi-hop arc closure 의 외부 일관성 evidence |

D-2wiki 부터는 별도 사전등록 + publication-tier honest-tier 게이트.

## 7. 사전 등록 commit hash = evidence

이 doc 의 첫 commit hash 가 사전 등록의 timestamped evidence.
측정 실행 전 PR 머지 + main 동기화 후 시작.

## 8. 관련

- [[project_cycle_gamma_phase_c2_retrieval_bottleneck]] — MuSiQue
  Phase C.2 multi-hop arc closure (단일 fixture). 2Wiki 가 cross-
  bench reproduction.
- [[project_cycle_gamma_phase_c3_alce_smoke]] — ALCE C.3 smoke
  바로 직전 (같은 pattern: 사전등록 → fixture → producer → smoke
  → handover)
- [[feedback_self_evaluation_trap]] — closed-corpus producer pattern
  은 이 룰의 positive example
- [[feedback_finding_size_honest_framing]] — ⭐ infrastructure tier
  vocabulary
- [[feedback_n1_verdict_inflation_n3_caught]] — smoke n=20 가
  publication-tier n=3-paired 아닌 의도
- [[mechanism_layer_intent_axis_alignment]] — support_fact_f1 의
  intent axis 가 supporting fact prediction (producer side); smoke
  producer 가 안 emit → "not measured" 정직 surface
- design memo: `docs/design/v0.4-cycle-gamma-external-benchmark-
  integration.md` §C.4

---

*이 문서는 fixture 작성 + 측정 실행 전 commit. Commit hash 가 사전
등록 증거. 2Wiki fixture 의 sha 는 download 이후 결정.*
