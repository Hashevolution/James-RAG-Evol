<!-- Synced from session memory 2026-06-10 (review R2: rules audit-trail check-in). -->
---
name: mechanism-layer-intent-axis-alignment
description: "α-5 post-closure 자기-감사에서 발견된 mechanism — RAG 시스템의 각 layer 는 design intent (quality / cost / safety / 가용성) 에 맞는 axis 로만 채점해야 함. uniform multi-axis 채점은 cost-optimization layer 를 quality regression 으로 오판하거나 quality layer 를 cost-axis 한정 채점함. α-6 design memo §5.6 에 박힘."
metadata:
  node_type: memory
  type: feedback
  originSessionId: 1a5409af-4522-45af-a495-bc2a0c82cbb1
---

## Rule

매트릭스 cell 의 verdict 는 **uniform 5-axis Pareto** 가 아니라
**per-layer design-intent axis 매칭** 으로 매겨야 함. 그러지 않으면:

- **cost-optimization layer** (예: ADAPTIVE_BUDGET — 토큰 효율) 가
  quality regression 으로 잘못 판단됨 (디자인 의도상 quality-neutral 인데
  noise band 안 변동을 regression 으로 인식)
- **quality layer** (예: graph traversal) 가 cost axis 채점에 묶여 평가됨
  (cost 가 좀 늘었다고 reject 됨)
- **safety layer** (예: abstention) 가 quality recall 로만 채점됨 (refusal
  의도가 보호하는 것을 놓침)
- **availability layer** (예: routing) 가 single-axis 로 묶임

각 layer 는 design intent 와 **axis 매칭 표** 를 미리 갖고 cell verdict
에 적용.

## Why (실측 사건)

α-5 cycle T0 closure (#645) 후 사용자가 두 가지 catch 했음 (2026-05-31 PM):

**사건 1 — ADAPTIVE_BUDGET (D1) 을 quality axes 로 채점**:
- `core/reasoning/budget.py` 모듈 docstring 명시:
  > "4096 is safe but **wasteful**: a one-size cap pays ~8x for the heavy
  > path and ~70x for the substitution path."
- 메모리 `direction_1_adaptive_budget_closure` 의 명시:
  > "cognitive 4 stage zero truncation + **zero quality regression**"
- 즉 ADAPTIVE_BUDGET 설계 의도 = **token 효율, quality-neutral**
- α-5 verdict 가 abst_f1 -0.091 → "도움 안 됨" 으로 묶음
- 진짜 ADAPTIVE_BUDGET 채점 = **token + latency 우선, quality 는
  regression check 만**

**사건 2 — AUTO_ROUTER (D5) 가 매트릭스에서 no-op**:
- `core/reasoning/backends/__init__.py:329` 의 `_autoregister()` 는 옵트인
  (`JAMES_ENABLE_CLAUDE_BACKEND=1`) 없으면 `ollama_local` (tier="small")
  하나만 등록.
- 라우터 정책 (`_route_policy`) 의 `_first_in_tier("large" / "medium")`
  가 모두 None 반환 → 모든 routing branch 가 `ollama_local` 자체로 떨어짐
- 즉 AUTO_ROUTER 가 켜져 있었지만 라우팅 대상 없음 = no-op
- α-5 L5 cell 의 실제 측정 = ADAPTIVE_BUDGET + SCOPE_ROUTING + (AUTO_ROUTER
  no-op). AUTO_ROUTER 의 진짜 verdict 는 측정 안 됨.

두 catch 모두 사용자 도메인 지식이 잡음. publishable claim 보호의 최종 안전망.

## How to apply

### 매트릭스 cell 설계 시 의무

각 layer 의 design intent 를 먼저 확정하고 **axis 매칭 표** 를 PR description
에 박음. 매칭 안 된 axis 는 cell verdict 에서 weight 0 (또는 regression-only
check).

| Layer | Design intent | Primary axes | Regression-only check axes |
|---|---|---|---|
| AUTO_ROUTER (D5) | right-size model per query | path + graded + abst_f1 + token + latency (all 5) | - |
| ADAPTIVE_BUDGET (D1) | 토큰 효율 (quality-neutral) | **token + latency** | quality axes (noise band 안 보장) |
| SCOPE_ROUTING (LEO) | 검색 범위별 right-size | path + token + latency | graded / abst_f1 |
| ENTITY_ANCHOR + QUERY_REWRITE | 검색 recall + 입력 fluency | path + graded | cost axes |
| Citation (S4) | 출처 surface | path | 다른 모두 (출처는 quality 변화 minimal 의도) |
| Graph (S2) | concept multi-hop | path + graded | cost axes |
| Abstention (S5) | 거절 grounding | abst_f1 | quality regression 보호 |
| Cognitive stages (S6) | multi-step reasoning | graded | latency 비용 acceptable trade-off |

### 매트릭스 verdict 규칙

cell 의 verdict = primary axes 의 Δ 가 noise band 를 의미 있게 넘으면 adopt /
reject; regression-only axes 는 noise band 안 들면 통과, 넘으면 reject 보조.

`strong-adopt` = primary axes 모두 + 방향 + regression axes 통과
`adopt` = primary axes 모두 + 방향
`tier-gated` = primary axes 일부 + 방향 (tier 별 가치)
`reject` = primary axes 가 + 방향 아니거나 regression axes 가 noise band 넘음
`zero` = 모든 axes noise band 안

### Layer 측정 prerequisite 의무

각 layer 가 의도된 효과를 내려면 그 효과가 가능한 환경에 있어야 함:

| Layer | Prerequisite |
|---|---|
| **ALL (시스템 측)** | **Backend service (Ollama / 클라우드) healthy 상태 — query 지연시간 정상 범위, sustained sweep 부하로 degraded 아님** (T1 timeout-cascade 2026-06-01 추가) |
| AUTO_ROUTER (D5) | multi-tier backend 등록 (claude_code_cli 옵트인 또는 ollama tiered backend) |
| ADAPTIVE_BUDGET (D1) | per-stage budget metric 캡처 (eval_count / answer_chars / latency_s) |
| SCOPE_ROUTING (LEO) | evidence_scope 측정 cell-level 캡처 |
| ENTITY_ANCHOR + QUERY_REWRITE | per-query baseline (anchor / rewrite 전후 비교) |
| Citation / Graph / Abstention | 측정 측 oracle 이 그 layer 의 emission 을 정확히 잡음 (sources field, graph_paths, abstain phrases) |
| Cognitive stages | per-stage audit row 캡처 |

prerequisite 빠지면 **그 layer 는 측정 자체 불가능**. cell verdict
"not in evidence" 로 명시. uniform 5-axis 로 판단 금지.

### 사건 7 — T1 timeout cascade (2026-06-01)

α-5 T1 cell L3 + L4 양쪽 100/100 query 가 `status=timeout, elapsed=120s,
answer_len=None` 결과. ~6.7h compute 낭비. 4-step rule 2 단계 (raw sample 직독)
가 즉시 시스템 측 timeout cascade 패턴 catch. 원인: Ollama 서비스가 T0
6+ 시간 sustained 부하 후 degraded. 매트릭스 runner 가 cell 별로 JAMES Python
server 는 재시작하지만 Ollama 는 영속 서비스 — 부하 회복 X.

**Lesson**: layer prerequisite 표에 *"backend service healthy"* 추가. 매트릭스
closure runbook 의 cell launch 전 Ollama healthcheck step 0.5 추가 권장.

α-5 cycle **7번째 wrong-fix-averted** — 그냥 결과만 봤으면 *"ADAPTIVE_BUDGET
이 production 티어 망친다"* false bucket-(b) 결론. Step 2 가 timeout 패턴
잡고 system-side 원인 확정.

## 패턴 generalize

이 mechanism 은 RAG 시스템 한정 아님. 모든 측정 시스템에서:

1. **각 component 가 무엇을 위해 존재하는지** 디자인 의도 명시
2. **그 의도가 어느 metric 으로 측정되는지** 매핑
3. **uniform metric 으로 묶지 않음** (cost component 를 quality 로 판단 X)
4. **prerequisite 가 없으면 측정 자체 못함** — "켜져 있다" ≠ "측정됨"

## 사용자 도메인 지식의 가치

사건 1 + 2 모두 closure PR 머지 후 catch. 즉 **post-closure self-audit 도
사이클 의 일부**. 사용자 도메인 지식 = publishable 결론의 최종 안전망.

## 관련

- [[feedback_oracle_phrase_artifacts]] §"확장 3" — 4-step 룰의 layer-intent
  generalisation, 본 mechanism 의 sub-pattern
- [[direction_1_adaptive_budget_closure]] — ADAPTIVE_BUDGET 의 "zero quality
  regression" 설계 의도 명시 (사건 1 의 근거)
- [[direction_5_auto_routing_closure]] — AUTO_ROUTER 의 "3-tier capability"
  명시 (사건 2 의 root cause)
- [[feedback_jameses_positioning_replayable_rag]] §"정정 2026-05-31" —
  사이클이 단일 framing 으로 묶이지 않도록 안전장치 (이 mechanism 과 동일
  결의 사용자 안전장치)

## 관련 PR

- #648 (α-5 verdict 정정 + layer-intent 박힘)
- α-6 design memo §5.6 (`docs/design/v0.4-alpha-6-sector-llm-ablation-matrix.md`)
- α-6 §5.5 (AUTO_ROUTER multi-tier backend prereq)
