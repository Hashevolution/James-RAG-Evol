# LRB Phase A — smoke 사전 등록 (Pre-registration)

**Date**: 2026-06-11 (corpus generator + 측정 실행 **전** 커밋 — R5 의무)
**Status**: LOCKED. 이 문서 commit 이후 scenario shape / SUT 구성 /
honest tier ladder / scoring axes 변경 금지. 변경 시 사유 append +
그 cycle 의 결과 exploratory 강등.

**Bench under test**: LRB (Lifecycle Retrieval Benchmark) v0.1.0
draft, design memo `docs/design/v0.4-lrb-lifecycle-retrieval-
benchmark-design.md` 의 protocol 그대로.

**Predecessors**:
- RAB v0.1.1 SPEC + scenario S1 + S2 (이번 세션 머지)
- Cycle γ Phase B+C+E-min (RGB) + C.2 (MuSiQue) + C.3 (ALCE) +
  C.4 (2Wiki) — 4-bench promise 4/4
- LRB design memo (PR #782)
- `docs/architecture/memory-lifecycle-architecture.md` (architecture)

**Why pre-register**: 외부 평가자(2026-06-11) 가 정확히 짚은 axis
— 시간에 따라 진화하는 corpus 위에서 retrieval/answer quality. RAB
audit-side 가 측정하지 않는 sibling axis. 사전 등록은 *측정 magnitude
가 어떤 방향이든* — Vanilla < JAMES 이든, Vanilla ≈ JAMES 이든,
JAMES < Vanilla 이든 — honest 보고를 lock 한다. 측정 후 narrative 만
바꾸는 패턴(`feedback_finding_size_honest_framing`) 을 구조적으로
차단.

**Why now (전체 트랙과의 정합)**: arXiv submit B-C-D 가 endorser
대기 단계라 main code base 작업 가능. LRB Phase A 의 사전등록 자체
가 priority anchor (Zenodo deposit 가능, paper v1.4 후속 PR 의 §
"Operational moat" subsection evidence prerequisite).

---

## 1. Scope — Phase A 가 측정할 것과 측정하지 않을 것

### 1.1 측정 (LOCK) — Phase A smoke

| 항목 | 값 |
|---|---|
| Scenario | **LRB-S1 (lifecycle-quarterly)** — design memo §4.1 |
| Initial corpus | 100 docs (RAB scenario-S2 city-operations vocabulary 재사용; license friction 0) |
| Evolution | 12 weeks; 매주 10-20 lifecycle events (INGEST/UPDATE/SUPERSEDE/DELETE) |
| Total events | ~200 (RAB S2 의 400 op 의 절반, scope manageable) |
| Query set | 60 queries × 3 timestamps (T=0 / T=6w / T=12w) = **180 evaluations** |
| Gold | 각 query × timestamp 에 manually-curated supporting doc list (per-timestamp) |
| **SUT (Phase A — only 2)** | **Vanilla in-memory RAG (Baseline) + JAMES (audit-native)** |
| Model | `gemma4:e4b` (cycle β/γ baseline 정합) |
| max_tokens | 1024 |
| n_runs | 1 (single deterministic run; smoke tier) |
| Honest tier | **⭐ infrastructure validated + gap-or-no-gap honest report** — NOT publication |

### 1.2 측정하지 **않음** (Phase A — LOCK)

| 항목 | 사유 |
|---|---|
| **Microsoft GraphRAG SUT** | Phase B smoke 추가. GraphRAG-lite mirror 가 비-trivial (entity extract + community summary build) → 별도 사전등록 |
| **ActiveGraph SUT** | LRB v0.2 publication tier (collab invite). within-class second audit-native point 는 self-eval trap mitigation 의 강도 ↑ — Phase A 의 2-SUT gap structure 는 그것 없이 honest negative 가능 (RAB Phase 3 의 ⭐⭐ partial 패턴 mirror) |
| **Hallucination Resistance (HR) axis** | NLI verifier 필요 (T5-XXL 또는 RoBERTa-NLI). LRB v0.2 candidate. v0.1 = deterministic axes only (RAB H1 정합) |
| **Cross-model (mxtral / gemma3:27b)** | Phase A smoke 외, D-LRB cycle |
| **Scenario S2 publication** (1000 docs / 6 months / 10K events) | LRB v0.2 candidate |
| **JAMES routing axis (auto_router / cog_stages 등)** | `feedback_path_d_james_not_specialty_verifier` 적용. 단일-axis chase 금지 |
| **F1 / EM on free-text answers** | SQuAD-norm 이 lifecycle 답에 부적합 |

### 1.3 측정 axes (Phase A — LOCK)

deterministic only, RAB H1 (no LLM judge in scoring) 정합:

| Axis | 정의 | Per-SUT emit |
|---|---|---|
| **R@5** | gold supporting docs ∩ top-5 retrieved / \|gold\| | ✓ |
| **R@10** | gold supporting docs ∩ top-10 retrieved / \|gold\| | ✓ |
| **P@5** | gold supporting docs ∩ top-5 retrieved / 5 | ✓ |
| **P@10** | gold supporting docs ∩ top-10 retrieved / 10 | ✓ |
| **Latency (s)** | retrieval + generation wall-clock per query | ✓ |
| **Token cost** | total tokens generated per query | ✓ |
| **Temporal accuracy** | T-시점의 정확한 supporting doc 을 retrieve 한 비율 (단순 set intersection over time-filtered gold) | ✓ |

**Magnitude framing 금지** = Phase A smoke 의 absolute values 는
cross-model / cross-scenario 확인 전 publication-tier claim 금지.

### 1.4 honest-tier 가능 결과 (LOCK)

| Result shape | Tier |
|---|---|
| 2 SUT 모두 axes emit + Vanilla < JAMES on temporal_accuracy + R@k @ T>0 | **⭐⭐ infrastructure validated + temporal-quality gap reproduced** |
| 2 SUT 모두 axes emit + Vanilla ≈ JAMES (gap < noise band) | **⭐ infrastructure validated + honest negative — gap missing or below smoke resolution**. paper headline 으로 무게 없음. measurement-driven discovery 정합 |
| 2 SUT 모두 axes emit + **Vanilla > JAMES** (역방향) | **⭐ infrastructure validated + surprising negative — JAMES does worse**. 별도 root-cause cycle (smoke 자체로 conclusion 금지) |
| 한 SUT exception / no axes emit | **exploratory** — fix-PR 별도, 본 cycle 의 결과 사용 안 함 |

**가장 자주 묻는 framing 함정**:
- "JAMES 가 lifecycle 다루니 당연 잘할 것" — pre-measurement claim 금지
- "Vanilla RAG 가 닫힌 corpus 에선 jam 가능" — measurement 후 결과
  보고 결정. 둘 다 사전등록 §1.4 의 honest tier 안에서 처리

## 2. SUT 구성 (Phase A — LOCK)

### 2.1 Vanilla in-memory RAG (Baseline)

- **What**: append-only vector store + BM25 / dense retrieval; no
  supersede 처리; no validity window; INGEST 시점 = stable forever
- **Implementation**: 자체 `eval/external/lrb/vanilla_producer.py`
  (Phase B 에서 build). 단순 sentence-transformers + sklearn cosine
  similarity 또는 chromadb minimal mode.
- **Why**: floor — "전형적 RAG" 의 honest representation. publishable
  comparison 의 lower bound.

### 2.2 JAMES (audit-native)

- **What**: 5-layer Memory Lifecycle Architecture 풀 스택 — Layer 3
  CASCADE + Layer 4-A EVENT/TEMPORAL + supersede chain + validity
  window + entity graph
- **Implementation**: 기존 `core.reasoning.engine.ReasoningEngine` 의
  `eval.external.runner.JamesEngineProducer` 그대로. workspace
  isolated.
- **Why**: 본 system 의 production code path. RAB Phase 3 에서 사용
  한 SUT 그대로.

### 2.3 SUT 선택 사유 — self-eval trap mitigation 의 부분 성취

design memo §5 의 4-SUT (Vanilla + GraphRAG + ActiveGraph + JAMES)
은 publish-grade. Phase A smoke 의 2-SUT 만 은 **partial self-eval
trap exposure** — JAMES 가 own corpus 의 gold 를 만든 게 아니지만,
within-class second audit-native point 없음. 이건 사전등록 §1.4 에
명시한 trade-off: **Phase A 의 honest tier ceiling 이 ⭐⭐ partial 인
이유**.

→ ⭐⭐⭐ tier 는 LRB v0.2 publication 의 4-SUT + cross-scenario
+ replication invite 후만.

## 3. Scenario fixture — 미구축 (corpus generator = 다음 step)

| 항목 | 결정 |
|---|---|
| Scenario fixture file | `eval/external/_fixtures/lrb/scenario_S1_quarterly.json` (다음 cycle 에서 generator + write) |
| Generator script | `scripts/research/build_lrb_scenario_S1.py` (RAB S2 generator mirror; temporal evolution 추가) |
| 100 docs vocabulary | RAB scenario-S2 의 city-operations 그대로 재사용 (license friction 0) |
| Per-query gold (per-timestamp) | manually curated; deterministic. 각 query 의 expected supporting doc 가 T=0/6w/12w 에 따라 다름 (supersede chain 활용) |

generator + fixture 작성 시점에 fixture sha 가 결정. Phase A 측정은
fixture sha hash-pin 후만.

## 4. 보고 프로토콜 (LOCK)

### 4.1 산출물 (4 파일)

1. `reports/external/lrb/phase-a-smoke-<ts>.result.json` (axes + per-
   SUT score + fixture sha + tier + design memo back-link)
2. `reports/external/lrb/phase-a-smoke-<ts>.bench.jsonl` (per-query
   per-timestamp per-SUT model answer + retrieved docs)
3. `docs/handovers/v0.4-lrb-phase-a-smoke-<date>.md`
4. `memory/project_lrb_phase_a_smoke.md`

### 4.2 보고 시 의무

1. **⭐⭐ or ⭐ tier** 가 모든 자리에 명시 — §1.4 의 locked verdict 그대로
2. **NOT publication** — magnitude framing 금지
3. **모든 7 axes emit per SUT** (R@5/R@10/P@5/P@10/Latency/Token cost/Temporal accuracy)
4. cross-SUT 표에 `n=180 evaluations` + `Phase A smoke (2 SUT only — Phase B/v0.2 가 GraphRAG / ActiveGraph 추가)` 명시
5. **JAMES wins / loses framing 금지** — design memo §6 의 verdict 그대로
6. **mid-June joint piece 자동 연결 금지** ([[feedback_eval_cycle_vs_collab_arc_separation]])
7. **외부 평가자 답신은 별도** — handover doc 의 "외부 평가자 답신" 섹션 금지 (별도 collab arc)

### 4.3 금지 사항

1. **SUT 변경 후 사전 등록 미수정** (post-hoc) — 변경 시 별도 cycle,
   exploratory 강등
2. **Gold relabel** — manually curated gold 는 fixture build commit
   에서 frozen; 측정 후 relabel = post-hoc fit
3. **Phase A 결과로 LRB v0.2 publication-tier claim** — Phase B (GraphRAG)
   + LRB v0.2 publication (ActiveGraph + 1000 docs) 까지 가야 함
4. **Microsoft GraphRAG / ActiveGraph 의 "결과 추정"** in handover —
   각 SUT 의 실측 없이 평균값 / 추정값 인용 금지

## 5. 인프라 reuse 의무

기존 cycle γ 인프라 재사용 — 새 코드 최소화:

| 위치 | 역할 |
|---|---|
| `eval/external/runner.py::run_external_bench` | runner 그대로 사용 (loader + scorer + producer dispatch) |
| `eval/external/runner.py::JamesEngineProducer` | JAMES SUT 그대로 |
| `eval/external/runner.py::ClosedCorpusGemmaProducer` | Vanilla RAG SUT 의 starting point (단, append-only vector store 추가 필요) |
| `eval/external/lrb/lrb_loader.py` | 새 — Phase A 에서 build |
| `eval/external/lrb/lrb_scorer.py` | 새 — Phase A 에서 build (deterministic axes only) |
| `eval/external/lrb/vanilla_rag_producer.py` | 새 — Phase A 에서 build |

LRB Phase A smoke 의 신규 코드 surface ≈ 600 줄 (RAB S2 의 1188 줄
보다 작음 — temporal evolution 만 추가, 신규 SPEC 없음).

## 6. 실행 순서 (logical chain)

```
0. 이 사전 등록 commit                              ← P0 (이 단계)
1. (다음 cycle) build_lrb_scenario_S1.py 작성 + 실행
   → eval/external/_fixtures/lrb/scenario_S1_quarterly.json (sha pin)
2. lrb_loader + lrb_scorer + vanilla_rag_producer 작성 + tests
3. Phase A smoke run (Vanilla + JAMES, 180 evaluations each)
4. handover doc + memory entry + PR
```

예상 비용 (operator-time):
- corpus generator + fixture: 4-6h
- loader + scorer + producer + tests: 2-3h
- smoke run + handover: 2-3h
- 총 ~1-1.5일 단일-cycle 작업

## 7. 외부 평가자 답신 plan (사전등록 lock 후만)

이 사전등록이 main 머지된 후 외부 평가자에게 답신 가능:
> "내부 framing 은 5-layer Memory Lifecycle Architecture (architecture) +
> RAB v0.1.1 (audit-side) + LRB v0.1 (retrieval-side, design memo +
> 사전등록 lock 됨). 측정 결과는 측정 후 보고. ActiveGraph (Nakajima
> 2026) 가 architecturally 같은 class — RAB paper §1/§2 'independent
> co-invention' 그대로. 측정 magnitude / 'JAMES wins' 류 framing 은
> Phase A 측정 후 사전등록 §1.4 의 honest tier 안에서만 제공 가능."

답신 자체는 사전등록 lock + Phase A 측정 완료 후. 사전등록만으로 답신
시 measurement-driven discovery 정신 위반 (보고할 결과 없음).

## 8. 사전 등록 commit hash = evidence

이 doc 의 첫 commit hash 가 사전 등록의 timestamped evidence.
corpus generator + 측정 실행 전 PR 머지 + main 동기화 후 시작.

## 9. 관련

- [[project_r1_replayable_audit_benchmark]] — RAB v0.1.1 (sibling
  axis). LRB 가 retrieval-side, RAB 가 audit-side.
- [[project_cycle_gamma_phase_c2_retrieval_bottleneck]] — multi-hop
  arc closure (separate axis from LRB; lifecycle ≠ multi-hop chain)
- [[feedback_self_evaluation_trap]] — gold curate / SUT selection
  discipline
- [[feedback_finding_size_honest_framing]] — magnitude framing 룰
- [[feedback_single_axis_ablation_misframing]] — 단일-axis chase 금지
- [[feedback_eval_cycle_vs_collab_arc_separation]] — joint piece /
  외부 평가자 답신 자동 연결 금지
- [[feedback_james_identity_measurement_driven]] — 9th catch, measurement
  evidence conditional
- design memo (PR #782): `docs/design/v0.4-lrb-lifecycle-retrieval-
  benchmark-design.md`
- Memory Lifecycle Architecture: `docs/architecture/memory-lifecycle-
  architecture.md`

---

*이 문서는 corpus generator + fixture 작성 + 측정 실행 전 commit.
Commit hash 가 사전 등록 증거. SUT 구성 (Vanilla + JAMES) + axes (7
deterministic) + honest tier ladder (§1.4) 모두 lock 됨.*
