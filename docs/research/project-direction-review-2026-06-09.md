# JAMES — 프로젝트 방향성 종합 점검 (2026-06-09)

> 전체 코드 상태 + α-5 → cycle γ Phase E-min 측정 데이터 전수 +
> 2025-26 외부 추론 설계 landscape 비교를 통합한 방향성 리뷰.
> 작성 범위: 진단(사실) → 외부 비교 → 제언(개선/정정) → 우선순위.
>
> 점검 방법: CLAUDE.md / ARCHITECTURE / ROADMAP / PLATFORM_READINESS /
> cycle β·γ 전 handover / alpha-5~8 reports / `core/` 134 파일 코드
> 감사 / feature_flags·ablation runner 직접 검증 / 외부 문헌·제품
> survey (RouteLLM, PAPILLON, Minions, LazyGraphRAG, CRAG,
> AbstentionBench, HALT-RAG, EU AI Act, Palantir/Glean 등).

---

## 0. TL;DR

1. **측정 문화는 프로젝트 최대 자산으로 성숙** — 450+ live 측정,
   9건 honest-framing catch, 사전 over-claim 차단 체계. 이 자체가
   외부 landscape에서도 드문 차별점.
2. **Phase E-min 발견 (3 컴포넌트 disabled 시 양 축 Pareto 개선)은
   외부 문헌과 정확히 합치하는 scale-threshold 패턴** — CoT가 ~10B
   미만 모델을 해치고, 소형 모델이 in-pipeline 지시 오버헤드를
   흡수 못 한다는 2025 연구들과 수렴. cross-model 검증 계획은 정당.
   novelty 주장은 불가, default revision은 evidence만으로 정당.
3. **가장 큰 구조적 모순: 프로젝트의 모트(replayable audit)는 측정되지
   않는 축이고, 측정되는 축(abstention/noise F1)은 모트가 아님.**
   Path D 결정("남의 축에서 싸우지 않는다")의 논리적 완성은
   **자기 축(replay fidelity / audit completeness / provenance
   coverage)을 측정 가능하게 만드는 것**. EU AI Act Art.12 전면 발효
   (2026-08)가 이 축을 product moat로 전환시키는 외부 타이밍.
4. **자기 룰 위반 3건이 코드/거버넌스에 누적** — (a) 의무-reading
   memory 룰 파일들이 repo에 부재, (b) 20KB 게이트 6건 위반 + CI
   미강제, (c) feature registry가 측정 knob의 절반만 등록.
   auditability를 파는 프로젝트가 자기 자신에게는 적용하지 않는 모양새.
5. **cloud tier 보류는 외부 동향과도 정합** — 단, 재가동 시
   PAPILLON/Minions 대비 벤치 의무. agentic/iterative retrieval
   (CRAG-style 재검색 1루프)은 cloud tier보다 먼저 시험했어야 할
   저비용 가설로, 측정 실험 1건 가치 있음.

---

## 1. 현재 위치 진단 (사실 확인)

### 1.1 측정 타임라인 핵심 수치 (α-5 → E-min)

| 시점 | 발견 | 수치 |
|---|---|---|
| pre-β (06-05) | cap[:1000] 결함 → 8000 flip | graded +0.077, abst_f1 +0.088 (n=100) |
| pre-β §34 | JAMES 가치 분해 | retrieval +0.18~0.21 / advanced 스택 단축 −0.05·다축 +0.09~0.27 / 4B≈47B |
| cycle β | persona+rule_text fix | +0.06 cumulative = 단축 손실의 27%만 cover |
| Direction α (06-04) | cloud premise 미입증 | 3 측정 모두 cloud 우위 신호 없음 (Δ −0.037, 9/9=9/9) |
| γ Phase C (06-08) | 4-model RGB-en | mxtral≡llama abstention set 동일 {3,9,14,15,17,18} |
| γ Phase D (06-08) | 7-knob ablation | retrieval −0.173 (지배), softener −0.054, graph/verify 0 |
| γ Phase E-min (06-09) | multi-axis 3-knob | disabled 시: rerank +0.04/+0.05, typed_filter +0.08/+0.05, cog_stages **+0.16**/+0.05 (noise/negrej) |

### 1.2 코드 상태 (직접 검증)

- `core/` 134 파일 ~1.3MB. 구조 양호, TODO/FIXME 없음.
- **20KB 게이트 위반 6건**: `reasoning/reflect.py` 29.2KB(+43%),
  `gemma_client.py` 23.7KB, `wiki_generator/_ingestion.py` 22.6KB,
  `wiki_generator/_frontmatter.py` 21.4KB, `reasoning/pipeline_synth.py`
  21.4KB, `graph_engine.py` 21.0KB. 추가 21파일이 15-20KB 경계.
- **feature_flags.py registry는 6 knob만 등록** (verify/fact_check/
  reflect/planner/query_rewrite/rerank). 측정 cycle이 다루는
  `JAMES_DISABLE_TYPED_FILTER` / `DISABLE_COGNITIVE_STAGES` /
  `DISABLE_ABSTENTION` / `DISABLE_GRAPH` / `DISABLE_RAG_RETRIEVAL`
  미등록 — admin UI 표면과 측정 표면 불일치.
- **built-but-unwired 2건**: `entity_anchor_expander` (STEP 0.5a
  배선 안 됨), `core/abstraction/` (dormant — 의도된 보존이나 명시
  목록 관리 없음).
- 코드 default vs production `.env` 이중 구조: reflect/planner/
  fact_check/query_rewrite는 코드 기본 OFF + production ON.
  "Default"의 의미가 문맥마다 달라 측정 해석 비용 발생.

### 1.3 거버넌스 발견 (이번 점검의 신규 사항)

**CLAUDE.md와 모든 handover가 의무 reading으로 지정한
`memory/feedback_*.md` 룰 파일들(9건 catch 룰 포함)이 저장소에
존재하지 않는다.** 세션 메모리에만 존재 →
- 버전관리·감사 불가 (auditability 미션과 자기모순)
- bus factor 1 (협업자/미래 세션이 룰 원문 접근 불가)
- handover의 "의무 reading" 지시가 repo만으로는 이행 불가능

---

## 2. 외부 추론 설계 비교 (2025-26 landscape)

### 2.1 JAMES가 field와 정합한 곳

- **hybrid local/cloud routing**: RouteLLM(arXiv:2406.18665) 등
  cascade routing은 이미 혼잡한 연구 lane. Direction α 보류는
  "retrieval 품질 > 모델 크기" field 합의와 정합 — 옳은 결정.
- **long-context vs RAG**: 1M 컨텍스트 시대에도 비용·신선도·
  mid-context 열화로 RAG 지속 — local-first retrieval 베팅 안전.
- **abstention 자기평가**: prior-art doc의 자기 축소(⭐⭐⭐ 기각)는
  AbstentionBench/HALT-RAG 대비 정직하고 정확.

### 2.2 JAMES가 중복/뒤처진 곳

| 영역 | 외부 | JAMES 상태 |
|---|---|---|
| 마스킹/egress | **PAPILLON** (NAACL 2025, PUPA bench, leak 7.5%/품질 85.5%), **Minions** (arXiv:2502.15964, Ollama·AMD 채택, 5.7x 비용↓ 97.9% 품질) | `core/abstraction/`은 이들과 기능 중복. 진짜 delta = typed-graph 기반 결정적 마스크 + replay-auditable egress (incremental). 재가동 시 비교 벤치 의무 |
| Graph 비용/품질 | **LazyGraphRAG** (GraphRAG 대비 700x 비용↓, Azure 출시) | graph+causality chain의 외부 비교 0건. abst_f1 zero-op 확인만 됨 |
| 반복/agentic retrieval | Self-RAG, **CRAG** (+8~36pt 사례), Adaptive-RAG, agentic RAG survey (arXiv:2501.09136) | 정적 1-pass retrieval. multihop 약점(cloud tier 동기)의 직접 치료 후보 미시도 |
| HITL 승인 게이트 | LangGraph interrupt(), HumanLayer 등 commodity | 차별점 아님. 단 self-evolution(코드/KG CR)에 적용한 건 상대적으로 드묾 |

### 2.3 JAMES가 진짜 차별화된 곳

1. **결정적 replay invariant** (trace + graph replay §5.7.2):
   field는 "trace 캡처/디버깅 replay"까지만 — 결정적 replay는
   "missing primitive"로 인식되지만 출시된 곳이 드묾.
2. **규제 타이밍**: EU AI Act Art.12(로깅)·Art.10(데이터 lineage)·
   Art.11(자동 문서화)이 2026-08 전면 발효 — JAMES의 audit-log/
   replay/CR 설계와 거의 1:1 매핑. 경쟁: Palantir Ontology(폐쇄·
   고가), Glean(cloud SaaS) → **local-first open replayable RAG +
   policy-at-retrieval은 방어 가능한 niche**. 단 모트의 본질은
   retrieval 품질이 아니라 **compliance-evidence 생성 능력**.
   gateway형 거버넌스 제품이 "통합 audit trail"을 commodity화
   중이므로, bolt-on이 retrofit 못 하는 **replay identity**가 edge.
3. **측정 방법론 그 자체**: paired ablation + layer-intent axes +
   honest-framing 룰 + per-query overlap method — 어떤 단일
   mechanism보다 희소한 자산. prior-art doc 결론 그대로.

### 2.4 Phase E-min 발견의 외부 수렴 증거

- CoT는 ~10B 미만에서 무익/유해 (Wei et al. + 후속) →
  cognitive_stages +0.16 noise와 직접 합치.
- reasoning 추가 시 instruction-following 저하 (arXiv:2505.11423,
  2505.14810).
- 7-9B 모델은 in-pipeline rerank 지시를 무시/오흡수, ≥14B부터 순응
  (arXiv:2510.13329) → rerank/typed_filter 결과와 합치.
- "less is more" 실무 합의 + AutoRAG: 최적 파이프라인 구성은
  corpus·모델 의존적, 컴포넌트 단조 증가 아님.

→ cross-model 3/3 일관이 나와도 **novelty가 아닌 confirmation-tier**.
생존하는 framing: "4-8B tier production RAG 스택에서의 컴포넌트
단위 Pareto 실측 + replayable 방법론". default revision PR은
evidence만으로 정당하고, novelty 주장은 불가.

---

## 3. 제언 — 바로잡을 점

### R1. (구조) 모트 축을 측정 가능하게 만들 것 — "자기 축 벤치"

현재 모든 측정 cycle이 품질 축(abstention/noise/graded F1)에 집중.
그 축에서 JAMES는 specialty 시스템(HALT-RAG 0.978)에 lag하고, 발견은
문헌이 이미 cover (cycle γ 결론). 반면 정체성 축(replay/audit/
provenance)은 **"no public bench"** 상태 — 이것은 gap이 아니라
방법론 기여 기회다. 제안:

- **Replay Fidelity Bench**: 동일 trace_id 재생 시 byte-identical
  비율, CASCADE/supersede 후 `reconstruct_view_at(t)` 정확도.
- **Audit Completeness Metric**: 답변 1건당 결정 노드(retrieval/
  policy/synth/egress) 중 audit row가 존재하는 비율.
- **Provenance Coverage**: 답변 claim 중 source+graph path로 역추적
  가능한 비율 (기존 citation 측정의 확장).
- EU AI Act Art.10/11/12 요구사항 → 측정 항목 매핑 문서 1건.

이는 Path D("남의 축에서 싸우지 않는다")의 논리적 완성이며, v0.5
enterprise pilot의 영업 evidence가 측정 인프라에서 직접 생산되는
구조를 만든다.

### R2. (거버넌스) memory 룰을 repo에 체크인할 것

`memory/feedback_*.md` 9+ 룰을 `docs/rules/`(또는 repo `memory/`)로
체크인. 룰 변경도 PR로. auditability 미션의 자기 적용이자 bus factor
해소. 비용 ~1시간, 효과 영구.

### R3. (자기 룰 준수) 20KB 게이트 CI 강제 + 위반 6건 해소

`reflect.py`(+43%)부터 분할. CI에 size check 추가 (현재 미강제 —
규칙이 사람 기억에만 존재). 경계 21파일 목록도 함께 출력.

### R4. (측정-운영 단일 진실) feature registry 완성

측정 cycle이 다루는 11 knob 전부를 `feature_flags.py`(또는
machine-readable defaults 파일)에 등록 + "코드 default vs production
.env" 이중 구조 명시. **cycle β default revision PR이 임박한 지금이
선행 정비 적기** — revision이 registry 밖 knob을 건드리면 audit
표면이 또 갈라진다.

### R5. (통계 엄밀성) cross-model E-min 전 사전 등록(pre-registration)

n=25 단일 run, CI 없음, phrase-based abstention oracle(~25 구문),
seed/temperature 미통제가 현 상태. 9건 catch는 전부 **사후 정정**으로
작동했다 — 사전 등록이 더 저렴하다. cross-model E-min 실행 전에:
(a) 결정 기준(decision tree)을 수치 임계와 함께 사전 고정 (이미
handover §4에 있음 — 임계값만 추가), (b) 가능하면 cell당 n=50 또는
seed 3회로 bootstrap CI, (c) phrase oracle의 모델별 refusal 양식
누락 점검. 비용 +1~2h로 default revision PR의 evidence 등급이 달라짐.

### R6. (저비용 가설) CRAG-style 반복 retrieval 측정 실험 1건

Phase D가 입증한 것: retrieval이 abstention grounding의 지배 요인
(−0.173). multihop 약점이 cloud tier의 동기였는데, **로컬 호환·
저비용인 "검증 실패 시 재검색 1루프"는 시도된 적 없다.** 외부에서
+8~36pt 사례 보고. 단, 소형 모델에서 agentic 루프가 역효과일 수
있다는 게 바로 E-min의 교훈이므로 — 채택이 아니라 **측정 실험**으로.
기존 external_bench_run 인프라 재사용 가능, ~반나절.

### R7. (graph 투자 점검) LazyGraphRAG 대비 1회 비교

graph 레이어는 abst_f1 zero-op(예상대로)이나 graded/path 축 기여
정량이 §36 외 약함. graph+causality 투자를 지속하려면 외부
비용/품질 기준(LazyGraphRAG급) 대비 1회 측정이 필요. 결과가
나쁘면 그것도 가치 있는 발견 (mother-platform 다이어트).

### R8. (cloud tier) 보류 유지 + 재가동 조건 명문화

보류는 옳다. 재가동 트리거에 다음을 추가 명문화: (a) PAPILLON/
Minions 대비 벤치 의무, (b) leak-controlled fixture, (c) masking의
JAMES 고유 delta(typed-graph 결정적 마스크 + replay-auditable
egress)를 전면에 — "마스킹 자체"는 더 이상 novel하지 않음.

### R9. (v0.5 게이트) cross-bench 1개 + 한국어 fixture 후 진입 평가

현 D2 evidence는 RGB-en n=25 의존 — publication-grade로 약함 (cycle
γ design memo 자체 기준). v0.5 진입 평가는 cross-model E-min +
최소 1개 추가 벤치(MuSiQue 또는 2Wiki) 후가 정합. 또한 **측정이
전부 영어** (RGB-en, MultiHop-RAG) — 한국 enterprise 시장 타겟이면
한국어 fixture가 v0.5 전 필수 인프라 (8th catch가 Korean-only
framing을 기각했지만, bilingual 측정 인프라 부재는 별개 문제).
도메인 선택(enterprise internal knowledge ontology)은 외부 조사로
강하게 지지됨 — 단 포지셔닝 선두는 "compliance-grade replay/
provenance"로.

### R10. (default revision 설계) 모델-tier-aware defaults를
platform contract로

cross-model 결과가 2/3 패턴이면 "모델별 default"가 필요해지는데,
이는 "단일 모체" 철학과 긴장. fork가 아니라 **model-capability-tier
profile**(예: ≤8B tier는 minimal-scaffold preset, ≥14B tier는 full
preset)을 platform contract의 일부로 설계하면 6원칙(원칙 5/6:
auto-selection Default 인정)과 정합한다. 외부 문헌의 scale-threshold
(~10-14B)와도 맞는 자연스러운 경계.

---

## 4. 우선순위 제안

| 순위 | 항목 | 비용 | 근거 |
|---|---|---|---|
| 1 | cross-model Phase E-min (기존 계획) + R5 사전 등록 | ~2.5h + 1h | 이미 큐에 있고 정당. 사전 등록만 추가 |
| 2 | R2 memory 룰 체크인 + R3 CI gate + R4 registry | ~반나절 | 저비용·영구 효과. default revision 전 선행 정비 |
| 3 | R1 자기 축 벤치 (replay/audit/provenance) | 1-2 PR | 모트 측정화. v0.5 영업 evidence 직접 생산 |
| 4 | R6 CRAG-style 재검색 실험 | ~반나절 | retrieval 지배 finding의 직접 후속, 저비용 |
| 5 | R9 cross-bench 1개 + 한국어 fixture | 수일 | v0.5 게이트 prerequisite |
| 6 | R7 LazyGraphRAG 비교, R8 cloud 재가동 조건 명문화 | 선택 | 투자 점검·문서화 |

---

## 5. 종합 평가

프로젝트의 방향 감각은 건강하다: cloud tier 보류, Path D 기각,
prior-art 자기 축소, 9건 catch 모두 외부 검증으로도 옳은 결정이었다.
측정 문화는 field 기준으로도 희소한 자산이다.

남은 비대칭은 하나다 — **측정 에너지가 모트가 아닌 축에 쓰이고
있고, 모트인 축은 측정되지 않고 있다.** 품질 축의 발견은 계속
"문헌이 이미 cover"로 귀결될 것이다 (E-min도 같은 운명일 가능성이
높다 — confirmation-tier). replay/audit/provenance 축은 정반대다:
공개 벤치가 없고, 규제가 수요를 만들고 있으며, JAMES가 이미 코드로
앞서 있다. 다음 1-2 cycle의 측정 투자를 이 축으로 기울이는 것이
이 리뷰의 핵심 제언이다.
