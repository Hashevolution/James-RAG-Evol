# LRB v0.2.1 — Cross-Model 사전 등록 (Pre-registration)

**Date**: 2026-06-11 (cross-model producer 구현 + 측정 실행 **전** 커밋)
**Status**: LOCKED. 이 doc commit 후 모델 lineup / producer interface /
honest tier ladder / 측정 axes 변경 금지.

**Bench under test**: LRB v0.2.1 — Phase B 의 LRB-S1 / S2 fixture 위에
**LLM-grounded retrieval producer** 를 추가하여 cross-model 측정. v0.2
publication tier 의 첫 번째 step.

**Predecessors**:
- LRB design memo (PR #782)
- LRB Phase A prereg (PR #783) + 측정 (PR #784)
- LRB Phase B prereg (PR #785) + 측정 (PR #786, ⭐⭐⭐ tier landed)

**Why pre-register**: Phase A+B 가 token-overlap deterministic only.
"LRB 가 LLM 영향 없는 axis 만 측정" 비판이 외부 인정 ❌ 항목 (cross-
model). v0.2.1 은 LLM-grounded retrieval producer 를 도입하여 retrieval
quality 가 model size / family 에 따라 어떻게 변하는지 측정. cross-
model gap reproduction = self-eval trap mitigation 강화.

**Why now (전체 트랙과의 정합)**: Track A v0.2 publication tier 의
첫 milestone. 외부 인정 7/10 → 8/10 진입.

---

## 1. Scope — v0.2.1 가 측정할 것과 측정하지 않을 것

### 1.1 측정 (LOCK)

| 항목 | 값 |
|---|---|
| Scenario | **LRB-S1 + LRB-S2** (Phase B 와 동일 fixture, 동일 sha) |
| SUTs | **3 (Phase B 와 동일)** — Vanilla + Naive-supersede + JAMES |
| **Models (cross-model lineup)** | **4 family** — `gemma4:e4b` (Phase A/B baseline) + `gemma3:12b` (mid-size) + `mxtral` (mid-large) + `claude-haiku-4-5` (cloud, abstraction layer) |
| Retrieval modes | **2** — (a) token-overlap-only (Phase B baseline) + (b) **LLM-grounded retrieval** (model-rerank top-20 by token-overlap → LLM scores top-20 → top-k by LLM score) |
| n_runs | 1 per (model, mode, SUT, scenario) — deterministic 단일 run |
| Honest tier | **⭐⭐ infra validated + cross-model gap reproduction → ⭐⭐⭐ candidate (if gap rank-order survives cross-model)** |

### 1.2 핵심 신규 axis — cross-model reproduction

| Question | Test |
|---|---|
| (Q1) Token-overlap 결과가 LLM grounding 으로 바뀌나? | 4 model × 2 mode × 3 SUT × 2 scenario = 48 cells. mode delta (LLM − token-only) per SUT |
| (Q2) Cross-model gap rank-order 가 유지되나? | S2 R@1 ranking: Vanilla < Naive < JAMES — 모든 model 에서 reproduce 되어야 ⭐⭐⭐ |
| (Q3) Model size 가 retrieval quality 결정하나? | gemma4:e4b (~4B) < gemma3:12b < mxtral (~47B) < claude — strict ordering 시 size 효과; tied 면 architecture 효과 |

### 1.3 측정 axes (Phase B 와 동일 LOCK)

deterministic-first; LLM 은 **scoring 단계가 아니라 retrieval 단계 only**
(RAB H1 정신 유지 — scoring 여전 deterministic):

- R@5 / R@10 / P@5 / P@10
- Latency / Token cost (LLM call 포함 시 retrieval latency 가 token-only 대비 크게 증가 예상)
- temporal_accuracy
- [exp] R@1 / P@1 / temporal_accuracy_strict_top1

### 1.4 honest-tier ladder (LOCK)

| Result shape | Tier |
|---|---|
| 4 model × 3 SUT axes emit + S2 R@1 rank-order (V < N < J) 가 **모든 model 에서 reproduce** | **⭐⭐⭐ cross-model gap structure validated** |
| 4 model × 3 SUT axes emit + S2 rank-order 가 일부 model 에서 partial (3 of 4 reproduce) | ⭐⭐ partial cross-model reproduction |
| Rank-order 가 절반 이하 model 에서 reproduce | ⭐ cross-model reverse — root-cause cycle 별도 |
| 한 model exception / no axes | exploratory |

**Magnitude framing 금지**: v0.2.1 cross-model 의 magnitude 는 v0.2.3
S3 publication-scale 확인 전 publication-tier claim 금지.

### 1.5 측정하지 **않음** (v0.2.1 — LOCK)

| 항목 | 사유 |
|---|---|
| LLM-graded **answer quality** axis | v0.2.4 HR (NLI) axis 별도 |
| GraphRAG SUT | v0.2.2 별도 |
| ActiveGraph SUT | v0.2 publication collab arc |
| S3 publication-scale (1000+ docs) | v0.2.3 별도 |
| Korean / cross-lingual | LRB v0.3 candidate |

## 2. Cross-model producer 설계

기존 token-overlap retrieve_at() 를 **두 모드**로 분리:

```python
class CrossModelAdapter:
    def retrieve_at(self, q, k, query_time, valid_time, *,
                    mode: Literal["token", "llm-grounded"],
                    model: str):
        if mode == "token":
            return token_overlap_top_k(q, k, vt)
        else:
            top_20 = token_overlap_top_k(q, 20, vt)
            llm_scores = llm_rerank(top_20, q, model=model)
            return top_k_by_score(top_20, llm_scores, k)
```

LLM rerank prompt (deterministic JSON output):
```
Given query: "{q}"
Score each candidate doc 0-10 by relevance:
1. {title} — {first 200 chars of text}
2. ...
Return JSON: {{"scores": [0..10, ...]}}
```

3 adapter (Vanilla / Naive / JAMES) 모두 이 layer 위에 build — 즉
**모드 + 모델은 SUT 외부의 cross-cutting concern**. SUT 자체 코드는
변경 0 (retrieve_at signature 만 model/mode keyword).

## 3. Models lineup (locked)

| Model | Family | 사용 방식 | 의무 |
|---|---|---|---|
| `gemma4:e4b` | Google Gemma | Ollama local | Phase A/B baseline reuse |
| `gemma3:12b` | Google Gemma | Ollama local | mid-size in-family |
| `mxtral` (= `mixtral:8x7b`) | Mistral | Ollama local | mid-large cross-family |
| `claude-haiku-4-5` | Anthropic | abstraction layer (Direction α §5.7.13) | cloud cross-family |

→ 1 local-small + 1 local-mid + 1 local-large + 1 cloud = 4-family
spread. Family / size 효과 분리 가능.

**Operator action 요건**:
- Ollama service 가동 + 3 model 다운로드 (`ollama pull gemma3:12b`,
  `ollama pull mixtral:8x7b`)
- Claude API key (또는 Max-plan headless `claude -p` per
  `feedback_direction_alpha_max_plan_research_cloud`)
- abstraction layer (`core/abstraction/`) 가용성 확인

## 4. 보고 프로토콜 (LOCK)

### 4.1 산출물 (per (scenario, sut, model, mode))

48 cells = 2 scenario × 3 SUT × 4 model × 2 mode. 각 cell:
- `reports/external/lrb/v021-<scn>-<model>-<mode>-<ts>.<sut>.result.json`
- `reports/external/lrb/v021-<scn>-<model>-<mode>-<ts>.<sut>.bench.jsonl`

Cross-cell handover: `docs/handovers/v0.4-lrb-v021-cross-model-<date>.md`

### 4.2 보고 시 의무

1. ⭐⭐⭐ / ⭐⭐ / ⭐ tier 명시 (§1.4 의 verdict 그대로)
2. cross-model gap rank-order 4-cell summary 표
3. Phase A finding (naive ≈ JAMES on S1) + Phase B finding (J > N on S2)
   보존 — cross-model 측정이 부정 아닌 보완
4. NOT publication framing
5. mid-June joint piece 자동 연결 금지
6. operator action evidence (어떤 model 이 어떤 hardware 에서, 어떤
   prompt 로) 명시

### 4.3 금지 사항

1. Phase A/B finding 의 retroactive 덮기
2. token-overlap 결과를 LLM-grounded 결과로 overwrite (post-hoc fit)
3. 4 model 중 1-2 cells exception 발생 시 결과 cherry-pick
4. magnitude claim ("12b 가 4b 의 X 배") without v0.2.3 publication-scale

## 5. 인프라 reuse

기존 LRB Phase A/B 인프라 그대로 + 다음 확장:

| 위치 | 역할 |
|---|---|
| `eval/external/lrb/adapters/*.py` | 동일 (변경 0) |
| `eval/external/lrb/driver_phase_b.py` | retrieve_at signature 에 mode + model keyword 추가 |
| `eval/external/lrb/llm_rerank.py` | 신규 — Ollama + abstraction layer dispatch |
| `eval/external/lrb/scorer.py` | 동일 (axes 동일) |
| `scripts/research/lrb_run_v021_cross_model.py` | 신규 — CLI runner |

v0.2.1 신규 코드 surface ≈ 500 줄 (llm_rerank + runner + handover).

## 6. 실행 순서 (logical chain)

```
0. 이 사전 등록 commit                      ← P0 (이 단계, 솔로)
1. retrieve_at signature 확장 (mode/model)  ← 솔로
2. llm_rerank.py 모듈 + Ollama + abstraction dispatch ← 솔로
3. CLI runner + tests                        ← 솔로
4. 단일 cell smoke (gemma4:e4b, token-mode)  ← 솔로 (baseline reproduction)
5. operator 의존: full sweep 48 cells (3-5h overnight batch)
6. cross-cell analysis + handover + PR        ← 솔로 분석
```

예상 비용:
- 사전 등록 + signature 확장 + llm_rerank 모듈: 2-3h
- CLI runner + tests: 1-2h
- smoke (1 cell): 5-10분
- full 48-cell sweep: 3-5h (operator-attended, overnight 권장)
- handover + 분석: 2-3h
- 총 ~10-15h 단일-cycle 작업

## 7. ⭐⭐⭐ tier 진입 의미

v0.2.1 ⭐⭐⭐ 진입 시:
- 외부 인정 7/10 → **8/10** (외부 model ❌ → ✅ 해소)
- 다음 step = v0.2.2 GraphRAG SUT → 9/10 (external SUT ❌ → ✅)
- v0.2.6 reproducer invite → 10/10 (collab arc 별도)

⭐⭐⭐ 후 publication 요건 추가:
- v0.2.3 S3 publication scale
- v0.2.4 HR NLI axis
- v0.2.5 arXiv preprint

## 8. 관련

- [[project_lrb_phase_a_smoke]] — Phase A+B 결과
- [[project_r1_replayable_audit_benchmark]] — RAB sibling axis
- [[feedback_self_evaluation_trap]] — fixture / oracle discipline
- [[feedback_finding_size_honest_framing]] — magnitude framing 룰
- [[feedback_single_axis_ablation_misframing]] — 단일 axis chase 금지
- [[feedback_eval_cycle_vs_collab_arc_separation]] — joint piece 자동 연결 금지
- [[feedback_direction_alpha_max_plan_research_cloud]] — cloud abstraction 정합
- design memo: `docs/design/v0.4-lrb-lifecycle-retrieval-benchmark-design.md`
- Phase B prereg: `docs/research/lrb-phase-b-time-travel-preregistration-2026-06-11.md`
- Phase B handover: `docs/handovers/v0.4-lrb-phase-b-cross-scenario-2026-06-11.md`

## 9. 사전 등록 commit hash = evidence

이 doc 의 첫 commit hash 가 사전 등록 timestamped evidence.
llm_rerank.py / cross-model runner / 측정 실행 **전** PR 머지.

---

*v0.2.1 = LRB v0.2 publication tier 의 첫 milestone. Token-overlap
결과의 cross-model reproduction 이 본 cycle 의 핵심 측정.*
