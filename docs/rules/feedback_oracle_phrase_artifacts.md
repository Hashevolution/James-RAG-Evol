<!-- Synced from session memory 2026-06-10 (review R2: rules audit-trail check-in). -->
---
name: oracle-phrase-artifacts-vs-real-signal
description: "매트릭스 결과 해석 시 oracle phrase / field 커버리지 부족이 \"신호\" 처럼 보이는 함정. α-5 1차 baseline 의 \"76% null_query hallucination\" 과 \"path_recall=0\" 둘 다 oracle 측 매처 갭이었음."
metadata:
  node_type: memory
  type: feedback
  originSessionId: 1a5409af-4522-45af-a495-bc2a0c82cbb1
---

## Rule

α-5 매트릭스의 모든 axis 결과는 **oracle 측 매처가 자메스 응답 형태를 정확히 잡고
있는지** 먼저 검증한 후 해석. 함정 두 가지 (2026-05-31 발견):

### Why (실측 사건 2건)

**사건 1 — path_recall=0** (해결: PR #618, **bucket: (d) measurement artifact**)
- 1차 baseline 보고: `path_recall = 0.000` on 75/75 queries
- 사용자 질문: "자메스 출처 인용 설계 정상이라 기억하는데..."
- 진단: `core/reasoning/pipeline.py:343` 가 `sources: [d["source"] for d in docs[:3]]`
  로 **상위 3 출처 문서 응답에 박음**. 자메스 정상.
- 함정: `scripts/bench.py` 가 응답의 `graph_paths` (entity 노드) 만 보고
  `sources` (citation) 필드 무시. graph_paths 는 개념 entity (Sam Bankman-Fried 같은)
  만 surface — MultiHop-RAG fixture 의 article-title 매칭에 fundamental mismatch.
- 수정: bench.py 가 sources 필드 캡처 + oracle 이 slug-normalise 후 graph_paths +
  sources union 으로 path-recall 계산.

**사건 2 — abstention F1 = 0.32, "76% hallucination on null_query"** (해결: PR #619, **bucket: (d) measurement artifact**)
- 1차 baseline 보고: FN=19/25 → 76% hallucination
- 직접 확인: 19개 답변 모두 **자메스 정상 거절** — "Source files: None of the
  provided internal data relate to..." / "impossible to answer" / "cannot be
  determined" 등.
- 함정: `eval/qvt/oracle.py::_ABSTENTION_PHRASES` 가 한국어 + 영어 일반 거절만
  커버. gemma4:e4b 의 grounding-training 영문 거절 phrasings (예: "impossible to
  determine", "cannot be answered", "insufficient information") 누락.
- 수정: 7 narrow phrase 추가 (전체 거절 위치에만 나타나는 것만). F1 0.32 → 0.63.
  진짜 hallucination 율 = 36% (9/25), 76% 아님.

### How to apply

운영자 검증 1차 순서 (매트릭스 결과 받기 직전):

1. **axis 별 0 / saturated / 비정상값** 보면 즉시 oracle 매처 vs 자메스 응답
   format 점검
2. **응답 sample 3-5 개** 의 raw 답변 직접 읽기 — oracle 의 binary 분류 (hit/miss,
   abstain/answer) 가 의미상 맞는지 확인
3. 의심스러우면 **자메스 응답 키 (response.sources / response.graph_paths /
   response.answer 등) 가 무엇 담는지** 코드 확인 (`routes/query.py` +
   `core/reasoning/pipeline.py`)
4. **자메스 설계 의도와 oracle 채점 일치 여부** 확인 — citation, abstention, graded
   answer 모두 자메스 본연 emit 형태 vs fixture/oracle 매처 기대 형태 매핑 검증

이 4 단계 안 거치면 "자메스 X 못함" 으로 잘못 결론. α-5 1차 baseline 에서 두 번
당함 (path + abstention 둘 다).

### 패턴 generalize

- **oracle 측 phrase 리스트 / field selection 은 모델/시스템 stylistic 변화에 brittle**
- 새 모델 도입 (예: gemma4:e4b → 다음 세대) 시 phrase list 도 같이 update 필요
- 새 fixture 도입 (예: MultiHop-RAG, 영문) 시 oracle 의 매처도 같이 review 필요
- **모델/벤치마크 처음 도입 시 baseline 의 N=2 이상 sample manual 검토** 가 axis
  생사 결정. saturated/floored axis 는 fixture/oracle 문제일 확률 ≥ 50%.

### 관련

- PR #616: 1차 baseline + path_recall=0 finding
- PR #618: source-recall fix (`pipeline.py:343` sources field)
- PR #619: abstention phrase coverage (narrow 7 additions)
- 자메스 출처 인용 설계: `core/reasoning/pipeline.py:343`
  → `routes/query.py::QueryResponse.sources`
- `eval/qvt/oracle.py::_ABSTENTION_PHRASES` — phrase list (도메인 / 모델 변화 시
  update 대상)
- 자메스 영문 거절 패턴 (gemma4:e4b grounding-trained):
  - "impossible to {answer, determine, identify}"
  - "cannot be {determined, answered}"
  - "insufficient {information, data}"
  - (FP 위험으로 미적용) "does not contain" / "lacking the specific" / "is not present"

관련: [[alpha_5_multihop_rag_reset]] [[feedback_per_derivation_semantics]]
[[a3_a2_think_mode_track_closure]]

---

## 확장 — 4-bucket 진단 분류 (사용자 가이드 2026-05-31 PM-2)

매트릭스에서 약점 발견 시 **반드시 4 bucket 중 어느 것인지 판단 후** 해결책
선택. bucket 잘못 잡으면 헛수고 또는 회귀.

| Bucket | 증상 | 해결 종류 | 본 cycle 사례 |
|---|---|---|---|
| **(a) Architecture** | layer 설계 자체의 boundary / shape 문제 | 재설계 / 분리 / 통합 | (없음 이번엔) |
| **(b) LLM model** | 모델 capability 천장 | tier 변경 / 모델 swap | A3 #608 — gemma4:e4b thinking trace |
| **(c) Feature gap** | 다루는 layer 자체 없음 | 신규 layer 설계 | abstention LLM-judge 후보 (deferred D6) |
| **(d) Measurement artifact** | oracle / fixture / bench 측 미스 | matcher 보완 (자메스 코드 변경 0) | path=0 #618, 76% hallucination #619 |

### 진단 순서 (priority)

1. **(d) 먼저 배제** — 자메스 응답 raw 직독 + response key 정합성 확인 (4단계 룰). 가장 흔하고 잡기 cheap.
2. **(b) 다음** — 같은 layer 가 다른 model tier 에서도 같은 약점? tier_gated 여부.
3. **(a) 다음** — layer 의 설계 의도와 실측 거동 사이 mismatch. 예: routing 의 의도가 "narrow query 는 small tier" 인데 실측은 random.
4. **(c) 마지막** — 위 3 도 아닌, 진짜 빈 칸. 신규 layer 설계 candidate.

순서를 거꾸로 가면 (c → a → b → d) 잘못된 신규 layer 추가, 또는 모델 잘못 swap, 또는 architecture 잘못 재설계.

### 사용자 요구와 매핑

α-5 측정의 이중 목적:
- **라우팅 결정** (1차) — layer 별 flag-ON 가치 → (a)/(b)/(c) bucket 결과 입력
- **추론 능력 비교 우위 입증** (2차) — JAMES 의 layer 적층이 외부 벤치마크에서 다른
  제품 대비 얼마나 강한지 publishable evidence → bucket (a)/(b)/(c) 의 매트릭스
  결과가 narrative 의 핵심 신호. bucket (d) 가 섞이면 narrative 신뢰도 손상.

### 헛수고 예방 패턴

- "JAMES 가 X 못함" 결론 전: bucket 분류 명시 의무.
- findings.md 의 모든 entry 에 `bucket:` 필드 추가 (mechanism-candidate / universal-law / anti-pattern / data-quality / operational 에 더해 bucket-(a/b/c/d) 태깅).
- 신규 layer / 모델 swap / architecture 변경 PR 은 **본문에 bucket 근거 명시**.

---

## 확장 2 — 4-step rule generalises to bucket-(a) wiring (2026-05-31 PM Correction 4)

원래 본 메모 의 4단계 룰은 **bucket-(d) "matcher coverage"** 함정 잡기용으로
문서화. α-5 T0 smoke cell 1 결과 받기 직전 추가 사례 (PR #638):

**사건 4 — matrix runner glob hardcoded step7** (해결: PR #638, **bucket: (a)
architecture**)
- cell L1/M_M JSON 의 aggregate: `path=0.000 / abst_f1=0.000 / graded=0.028`
  세 quality axis 동시 saturated
- 4 단계 룰 적용:
  1. axis 0/saturated — 즉시 trigger
  2. cell JSON 의 `runs[0].bench_output` 직독 → `bench_nogit_step7_20260507_*.json`
     (24일 전 step7 파일, 12 쿼리). 진짜 multihop_rag bench 100 queries 옆에
     unreferenced.
  3. 매트릭스 runner 코드 점검 → `scripts/qvt_ablation_matrix.py:380` 의 glob
     이 여전히 `bench_*_step7_*.json` hardcoded. #625 가 subprocess CALL 만
     고치고 OUTPUT 감지 glob 놓침.
  4. 설계 vs 매처: subprocess 는 옳은 multihop bench 작성 중, 그러나 runner 의
     score-collection wiring 이 보지 못함.
- 수정: 한 줄 변경 `glob_pattern` 변수 사용. 동반 도구
  `scripts/qvt_rescore_ablation_cell.py` 가 기존 cell JSON 들 재스코어.

**Real vs stale**:

| Axis | Stale step7 | Real multihop_rag |
|---|---|---|
| path | 0.000 | **0.419** |
| graded | 0.028 | **0.327** |
| abst_f1 | 0.000 | **0.591** |

자메스 코드 변경 **0줄**. 측정 측 wiring 만 고침.

### 룰 generalisation

원래 룰은 "oracle phrase / field coverage" 의 bucket-(d) 함정용. 사건 4 는
같은 절차가 **bucket-(a) plumbing 함정** 도 동일하게 잡는다는 점 증명:

- saturated axis → 1단계 trigger 동일
- sample read → 2단계가 "bench file 자체가 stale" 까지 확장
- response key → 3단계가 "runner code 의 wiring layer" 까지 확장
- design vs matcher → 4단계가 "측정 *경로 전체* 가 의도된 경로인지" 까지 확장

즉 4 단계 룰의 적용 범위 = **"모든 measurement-side wiring"**, oracle phrase
coverage 만이 아님. 다음 cycle 진입 시 매트릭스 cell 결과 받자마자 자동
적용 의무.

### 누적 wrong-fix-averted 카운트

α-5 cycle 안에서 4 건:
- #618 path_recall=0 (bucket-d)
- #619 + #623 hallucination 76%→36% (bucket-d)
- #625 subprocess suite arg (bucket-a)
- #638 score-collection glob (bucket-a)

**누적 자메스 코드 변경 = 0 줄**.

### 다음 cycle 운영 의무

1. **매트릭스 cell JSON 작성 직후 즉시 4 단계 룰 적용**. 자동 alert script
   (PR #633 `qvt_promote_findings.py` 와 같은 pattern) 후속 가능.
2. PR `fix` 라벨 면제 (CLAUDE.md rule 2) 는 bucket-(d) 뿐 아니라 **bucket-(a)
   measurement-side wiring** 도 포함. PR #638 이 worked example.
3. publishable narrative `reports/research-runs/alpha-5-publishable-narrative-DRAFT.md`
   §5.5 가 이 generalisation 의 reviewer-facing form.

관련 PR: #638 (fix), #639 (narrative absorb).

---

## 확장 3 — Layer-intent vs measurement-axis 정합 (2026-05-31 PM 후-closure self-audit)

α-5 T0 closure (#645) 후 publishable narrative 정정 도중 사용자가 두 가지
추가 함정 catch. 정정 PR (#648 또는 후속) 에서 절차 동일하게 4-step 룰 적용해서
잡힘. **사이클 안 5번째 + 6번째 wrong-fix-averted**.

### 사건 5 — AUTO_ROUTER 는 α-5 에서 no-op 였음 (해결: 정정 PR, **bucket-(a) wiring**)

- α-5 verdict: "L5 (모든 라우팅 on) = abst_f1 -0.091 regression"
- 사용자 catch: *"이것은 사실 젬마4 모델만 돌린것인지? 라우팅 되서 다른 llm 모델이
  돌아갔는것 까지 체크가된것인가? 전자의 경우면 당연히 나아질리가 없자나"*
- 코드 검증: `core/reasoning/backends/__init__.py:329` 의 `_autoregister()` 가
  옵트인 (`JAMES_ENABLE_CLAUDE_BACKEND=1`) 없으면 `ollama_local` (tier="small")
  하나만 등록. α-5 매트릭스 env 에 옵트인 X.
- 라우터 정책 (`core/reasoning/router.py::_route_policy`):
  - `_first_in_tier("large")` → None (등록 안 됨)
  - `_first_in_tier("medium")` → None
  - `_first_in_tier("small")` → `ollama_local` 자체
  - → 모든 routing branch 가 `ollama_local` 반환
  - → `JAMES_LLM_MODEL=gemma4:e4b` 고정. **다른 모델 호출 0**
- 즉 AUTO_ROUTER 가 "켜져 있었지만 라우팅 대상 없음" 으로 no-op.
- α-5 L5 cell 의 실제 측정 = `ADAPTIVE_BUDGET + SCOPE_ROUTING + (AUTO_ROUTER no-op)`
- **AUTO_ROUTER 진짜 verdict 는 α-5 에서 측정 안 됨**. α-6 의 5.5 (multi-tier
  backend 등록) prerequisite.

### 사건 6 — ADAPTIVE_BUDGET 은 wrong axes 로 채점됨 (해결: 정정 PR, **bucket-(a) layer-intent mismatch**)

- α-5 verdict: ADAPTIVE_BUDGET 도 "도움 안 됨" 으로 묶음 (L5 abst_f1 -0.091)
- 사용자 catch: *"적응형 예산 부분도 추론의 질이 나아지는 것보다는 소비 토큰과
  답변 속도, 답변 효율 최적화, 향후 클라우드 llm 이용시 예산 최적화 등에 이용
  하기 위한 것이 맞을 것같다"*
- 코드 검증: `core/reasoning/budget.py` 모듈 docstring 명시:
  > "4096 is safe but **wasteful**: ... a one-size cap pays ~8x for the heavy
  > path and ~70x for the substitution path."
- 즉 ADAPTIVE_BUDGET 설계 의도 = **토큰 효율성, quality-neutral**.
- 채점한 5-axis 중 **quality 3 axes 는 ADAPTIVE_BUDGET 의 success criterion 아님**.
- 진짜 ADAPTIVE_BUDGET 성공 기준:
  1. **Quality regression check** — quality axes within noise (target 0)
  2. **Token efficiency** — eval_count / chars 감소
  3. **Latency 감소** — 속도 개선
  4. **(향후) cloud-LLM $-cost** — API 사용 시 비용 감소
- α-5 L5 cell: quality regression 실패 (abst_f1 -0.091), token 미세 감소
  (1.5%), latency 악화 (3.6%). 종합: 의도된 cost 이득 없이 quality regression.
  하지만 SCOPE_ROUTING 와 동시 ON 이라 attribution 불가.
- **L3 (ADAPTIVE_BUDGET only) cell 측정 안 됨** → 단독 verdict 미정.

### 새 generalisation — Layer-intent vs measurement-axis 정합 룰

4 단계 룰을 한 단계 더 확장:

- 원래: "axis 0/saturated → sample read → response key → design vs matcher"
- 확장 2 (#638): "모든 measurement-side wiring"
- **확장 3 (이번)**: "Layer A 의 design intent 와 채점 axis 가 정합하나?"
  추가 검증.

각 layer 별로 **design intent → 채점 axis 매핑** 명시 의무. α-6 design memo
§5.6 에 layer-intent matrix 박힘.

| Layer | Design intent | 채점 axis (primary) |
|---|---|---|
| AUTO_ROUTER (D5) | 쿼리별 right-size model | all 5 (quality + cost) |
| ADAPTIVE_BUDGET (D1) | 토큰 효율 (quality-neutral) | **token + latency primary, quality 만 regression check** |
| SCOPE_ROUTING (LEO) | 검색 범위별 right-size | path + token + latency primary |
| ENTITY_ANCHOR + QUERY_REWRITE | 검색 recall + 입력 fluency | path + graded primary |
| Citation layer (S4) | 출처 surface | path primary |
| Graph layer (S2) | concept-centric multi-hop | path + graded primary |
| Abstention (S5) | 거절 grounding | abst_f1 primary |
| Cognitive stages (S6) | multi-step reasoning | graded primary |

매트릭스 cell verdict 는 **per-layer intent column** 기준으로 매김. uniform
5-axis Pareto 가 아님.

### 누적 wrong-fix-averted 카운트 (정정 후)

α-5 cycle 안에서 **6 건**:
- #618 path_recall=0 (bucket-d phrase coverage)
- #619 + #623 hallucination 76%→36% (bucket-d phrase coverage)
- #625 subprocess suite arg (bucket-a wiring)
- #638 score-collection glob (bucket-a wiring)
- **사건 5: AUTO_ROUTER no-op** (bucket-a wiring — multi-tier backend not registered)
- **사건 6: ADAPTIVE_BUDGET wrong axes** (bucket-a **layer-intent vs axis mismatch**, 새 sub-category)

**누적 자메스 코드 변경 = 0 줄** (정정 도중에도 시스템 코드 손 안 댐, 정정은
narrative + design memo + memory 만).

### 가장 큰 lesson — 사이클 자체가 self-auditing

사건 5 와 6 둘 다 **closure PR (#645) 가 머지된 후 사용자 catch**. 즉 "닫고
넘어가자" 가 아니라 **post-closure self-audit 도 정직한 publishable
contribution**. 사용자가 두 번 다 정확하게 catch — 운영자 도메인 지식이
publishable 결론 보호하는 최종 안전망.

### 다음 cycle 운영 의무 (정정)

1. **모든 layer 의 design intent → 채점 axis 매핑** 을 매트릭스 cell 설계 시
   명시 의무. uniform 5-axis 적용 금지.
2. **Multi-tier backend 등록 여부** 가 라우팅 layer 측정 prerequisite. 안 했으면
   "AUTO_ROUTER" 켰다고 측정 가능 아님.
3. **Per-layer attribution** 요구. L5 (all-on) cell 은 어느 layer 가 무엇을
   기여했는지 모름. L2 / L3 / L4 cell 들 필요.

관련 PR: #648 (정정 narrative + ROADMAP + α-6 design + 본 memory)
