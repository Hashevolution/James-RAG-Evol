# SEKOS — Secure Enterprise Knowledge Operating System

> **SEKOS** 는 사용자 facing 플랫폼; **JAMES** 는 그 안에 들어 있는
> 추론 엔진. 로컬 우선, 감사 가능한 지식 추론 **플랫폼**. Graph-RAG
> 검색, 결정론적 모순 중재, append-only audit log, replayable
> knowledge state, 인간 승인 게이트 기반 자기진화. v1.0 까지
> **범용 mother 플랫폼** 으로 강화; 도메인 팩 (법률 · 식품 · 유통 · 여행 등)
> 분화는 v1.0 이후 (
> [`docs/PLATFORM_READINESS.md`](docs/PLATFORM_READINESS.md) 참조).
>
> **차별점 한 줄**: *Replayable RAG* — T7 supersede 체인 + audit log
> append-only 조합으로 시점 T 의 시스템 상태를 바이트-동일하게 재구성
> 가능 (`reconstruct_view_at`). Graph-RAG 검색, Knowledge Cascade
> (Layer 3), Layer 4 Lifecycle (T1–T7), Plugin API, 결정론적 4-rule
> 모순 트리 등도 모두 first-class 차별점.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-v0.6.1%20on%20main%20(unreleased)-blue.svg)](https://github.com/Hashevolution/James-RAG-Evol/blob/main/docs/handovers/v0.6.2-restart-roadmap-2026-09-03.md)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)]()
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/12806/badge)](https://www.bestpractices.dev/projects/12806)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20652679.svg)](https://doi.org/10.5281/zenodo.20652679)
[![RAB SPEC](https://img.shields.io/badge/RAB%20SPEC-v0.1.1-green.svg)](eval/rab/SPEC-v0.1.md)
[![LRB Benchmark](https://img.shields.io/badge/LRB-v0.2.3-green.svg)](papers/lrb-preprint/main.pdf)

![SEKOS — 3D 온톨로지 그래프 시각화](reports/promo-assets/screenshots/06-3d-graph.jpg)

> *네이밍.* SEKOS = 제품 브랜드. JAMES = 그 안의 추론 엔진 코드명
> (RAG + audit + lifecycle). 두 벤치마크 (RAB / LRB), BibTeX,
> Zenodo DOI, 환경변수 (`JAMES_API_KEY` 등), CLI flag (`--sut james`),
> 소스트리는 JAMES 이름을 그대로 유지 — 외부 reproducibility 보존.
> SEKOS 는 사이드바에 표시되는 이름; JAMES 는 `core/` 안에 박힌 엔진.

> **🚀 처음 시작하시는 분?** 컴퓨터 잘 모르셔도 따라하실 수 있는
> [**비기너 가이드**](README.beginner.ko.md) 를 먼저 보세요.

---

## SEKOS 가 다른 RAG 와 다른 점 (60초 스캔)

LangChain, LlamaIndex, 일반 RAG 스택은 대부분 **고정된 corpus 위 답변 품질** 을 최적화합니다. SEKOS 는 (JAMES 엔진 위에서) 그 프레임워크들이 측정하지 않는 두 축에 맞춰 설계되었습니다:

| 축 | LangChain / LlamaIndex / vanilla RAG | **SEKOS (JAMES engine)** |
|---|---|---|
| **Audit-native lifecycle** | `logger.info()` 문자열; canonical event taxonomy 없음; 로그만으로 replay 불가 | Event-sourced `audit_log` 스키마; `reconstruct_graph_at(t)` 가 로그만으로 시점 T 의 시스템 상태를 바이트-동일하게 재생 — **RAB v0.1.1** 에서 측정 (AC/RF/PC = 1.0 × 3 vs Baseline-0 default-logging 바닥 = 0.275/0/0) |
| **Time-valid retrieval** | 최신 버전만; *"6개월 전 이 계약 6조 항이 어떻게 돼 있었지?"* 같은 질문 외부 versioned store 없이 답 불가 | 문서별 validity window (T1) + supersede chain (T7); time-travel query 는 `query_time` 시점 유효 버전 반환 — **LRB v0.2.3** 에서 측정 (R@1 V<N<J 가 4 모델 × 4 스케일 모두에서 보존, JAMES − Naive gap 모든 cell 에서 +0.10 이상) |
| **Local-first 실행** | Cloud 기본 (OpenAI / Anthropic API 가 모든 retrieval 호출) | Local Ollama 위 동작 (gemma4:e4b 4B → mxtral 47B); cloud 는 query 별 opt-in; 명시 동의 없이 host 밖으로 데이터 안 나감 |
| **EU AI Act 2026-08 정합** | "Compliance" 가 TODO | RAB 3 metric 이 Article 10/12/19 와 verbatim 매핑; AI Act 가 존재한다고 전제하는 audit 측정 도구 자체 |

SEKOS 가 **주장하지 않는 것**:
- **closed-book QA 답변 품질이 더 좋다** — *더 좋다*는 아니고 **동등(parity) 입증**: MuSiQue 에서 V=N=JAMES 가 EM/F1 4-decimal 동일 (gemma4:e4b / gemma3:12b / mxtral 47B) → JAMES 가 추론을 **악화시키지 않음**이 입증됨. closed-book 점수는 백본 모델 능력이고, validity-window 기능은 retrieval-side 라 closed-book 추론에 orthogonal. [LRB preprint](papers/lrb-preprint/main.pdf) §5.5 참조.
- **새 아키텍처 발명** — ActiveGraph ([arXiv:2605.21997](https://arxiv.org/abs/2605.21997)) 가 동일 event-sourced runtime class 독립 co-invention; 벤치마크 자체가 contribution
- **LangChain 의 drop-in 대체** — SEKOS 는 다른 운영 모델 (audit-first) 의 *플랫폼*; 통합은 `pip install` 한 줄이 아니라 integration project

audit / lifecycle / time-travel / on-prem 이 용도라면 — SEKOS 가 그것을 위해 만들어졌고, 측정됐고, 인용 가능합니다. *고정 corpus 에서 가장 빠른 답변* 이 용도라면 LangChain 쓰세요.

> **MRR / NDCG / RAGAS / 환각률 coverage 찾으시면**: [`docs/evaluation/v0.5-evaluation-coverage-mapping.md`](docs/evaluation/v0.5-evaluation-coverage-mapping.md) — 표준 RAG / IR metric 이 SEKOS 의 어디서 측정되는지 (그리고 어떤 metric 은 의도적으로 측정 안 하는지) 의 full mapping + code path + procurement-ready 답변.
>
> **LangChain / LlamaIndex / Haystack / R2R / ActiveGraph 와 1 페이지 비교**: [`docs/evaluation/v0.5-industry-comparison.md`](docs/evaluation/v0.5-industry-comparison.md) — 3 개 매트릭스 (architectural capability presence / public benchmark headline coverage / reproducibility tier), 모든 SEKOS cell 은 committed artifact 에 pin, 모든 경쟁사 cell 은 2026-06-13 기준 public docs 에 pin. 외부 reviewer 60 초 스캔 + 5 분 reproduce command.

---

## 📑 Papers & Reproducibility

두 벤치마크를 sibling 으로 release. 둘 다 측정 전 pre-registration LOCK, 둘 다 결정론적 scorer only, 둘 다 본 repo 에 commit.

### RAB v0.1.1 — Replayable-Audit Benchmark
[📄 PDF (10페이지)](papers/rab-preprint/main.pdf) · [📋 SPEC](eval/rab/SPEC-v0.1.md) · [🧪 Reproduce](#60초-안에-재현)

> *RAB 는 RAG / agent 시스템이 export 한 audit log 의 품질 (Audit Completeness / Replay Fidelity / Provenance Coverage) 을 측정. 3 metric 이 EU AI Act Article 10, 12, 19 와 verbatim 매핑. Headline 은 4-SUT gap (Reference / JAMES audit-native / OpenTelemetry-GenAI bolt-on / vanilla default-logging) 의 구조 — JAMES 점수 자체가 아님.*

### LRB v0.2.3 — Lifecycle Retrieval Benchmark
[📄 PDF (11페이지)](papers/lrb-preprint/main.pdf) · [🧪 Reproduce](#60초-안에-재현)

> *LRB 는 temporal validity (`query_time`, `valid_time`) retrieval 품질을 3 결정론 시나리오 (S1 quarterly, S2 yearly-with-time-travel, S3 publication-scale 1000 docs) 에서 측정. 3 SUT (Vanilla append-only / Naive-supersede / JAMES validity-window) 를 7 결정론 axis + 3 exploratory top-1 axis 로 비교. Headline: R@1 V < N < J 가 **4 모델 × 4 스케일** (12.5× 스케일 폭) 모두에서 보존, JAMES − Naive gap +0.10 이상.*

### 크로스-스택 수렴 기록 (3-author)

[🔗 DOI 10.5281/zenodo.22030935](https://doi.org/10.5281/zenodo.22030935) · Afana, Converse & Seo (2026) · report, CC-BY-4.0

> *substitution-vs-synthesis 를 세 스택에서 독립 측정한 수렴 기록의 한 다리 —
> sovereign 26B MoE (Converse) / JAMES cognitive middleware (Seo) /
> production Arabic e-commerce router (Afana). 세 다리가 **함께 입증하는 것**과
> **명시적으로 주장하지 않는 것**을 그 기록이 규정하며, 본 repo 는 middleware
> 다리의 데이터와 드라이버 — [v0.3.1](https://doi.org/10.5281/zenodo.20363998)
> 에서 마감한 7-tier natural-stop gradient (PR #461/#463) 를 보유.*

### Citation (BibTeX)

<details>
<summary>클릭하여 펼치기</summary>

```bibtex
@misc{seo2026jamesv044,
  author    = {Seo, Jiwon},
  title     = {{PROJECT JAMES} v0.4.4 (LRB v0.2.3 S3 publication-scale + cycle $\gamma$ 4-bench infrastructure closure)},
  year      = {2026},
  month     = {6},
  doi       = {10.5281/zenodo.20652679},
  url       = {https://doi.org/10.5281/zenodo.20652679},
  version   = {v0.4.4},
  publisher = {Zenodo},
  note      = {Source: https://github.com/Hashevolution/James-RAG-Evol}
}

@misc{seo2026rab,
  author        = {Seo, Jiwon},
  title         = {{RAB}: A Replayable-Audit Benchmark for {RAG} and Agent Systems Operationalising {EU AI Act} Articles 10, 12, 19},
  year          = {2026},
  howpublished  = {Preprint v0.1.1},
  url           = {papers/rab-preprint/main.pdf},
  note          = {Data: \href{https://doi.org/10.5281/zenodo.20652679}{10.5281/zenodo.20652679}}
}

@misc{seo2026lrb,
  author        = {Seo, Jiwon},
  title         = {{LRB}: A Lifecycle Retrieval Benchmark for Temporal {RAG}},
  year          = {2026},
  howpublished  = {Preprint v0.2.5},
  url           = {papers/lrb-preprint/main.pdf},
  note          = {Data: \href{https://doi.org/10.5281/zenodo.20652679}{10.5281/zenodo.20652679}}
}
```

</details>

### 60초 안에 재현

```bash
git clone https://github.com/Hashevolution/James-RAG-Evol.git
cd James-RAG-Evol
python -m pip install -r requirements.txt

# RAB scenario-S1 (결정론; LLM 호출 없음; ~5초)
python scripts/research/rab_run.py --sut reference     # AC/RF/PC = 1.000/1.000/1.000
python scripts/research/rab_run.py --sut baseline0     # AC/RF/PC = 0.275/0.000/0.000
python scripts/research/rab_run.py --sut james         # AC/RF/PC = 1.000/1.000/1.000

# LRB Phase B (S2 time-travel) token-mode (결정론; LLM 없음; ~30초)
PYTHONPATH=. python scripts/research/lrb_run_phase_b.py --scenarios S1,S2

# LRB S3 publication-scale (1000 docs / 5.6k events / 1000 queries; ~3분)
python scripts/research/build_lrb_scenario_s3.py --scale publication
python scripts/research/lrb_run_s3.py --scale publication
```

`reports/external/lrb/` 와 `reports/rab/` 의 모든 `result.json` + `bench.jsonl` artifact 가 scenario fixture 의 SHA 에 pin 됨; **바이트-동일 재실행이 검증 protocol** 입니다.

---

## 프로젝트 상태 (2026-09-03 기준) — v0.5 마감 + 미릴리스 v0.6 / v0.6.1 스트림

> **단일 진실원**: [`docs/handovers/v0.6.2-restart-roadmap-2026-09-03.md`](docs/handovers/v0.6.2-restart-roadmap-2026-09-03.md)
> (재개 로드맵 Phase 1–7). 아래 섹션들과 충돌하면 로드맵 문서가 우선입니다.

- **최신 태그 릴리스는 여전히 v0.4.4** (DOI `10.5281/zenodo.20652679`).
  v0.5 / v0.6 / v0.6.1 은 `main` 에만 있고 태그·DOI 가 없습니다.
- **v0.5 마감 2026-06-13**, **v0.6 정식 미진입** — 게이트 = Dim F
  (외부 고객 6 개월 파일럿) 미통과. 2-fork 계약 (Fork A LOI / Fork B
  6 개월 무LOI 재평가) 판정 시점 ≈ **2026-12-13**, operator 결정.
- **v0.6 / v0.6.1 제품 하드닝 스트림** (#886–#1078, 2026-06-13 → 06-26):
  운영 하드닝 (신뢰 프록시 / HTTPS 가이드 / 테넌트 미들웨어 / 온보딩 ·
  지식 롤백 · 추론 시각화 · 용어집) · **양식(템플릿) 엔진** · **에이전트
  트랙** · LLM 라우팅 통합 · 채팅 UX 전면 개편 · UI 8→5 페이지 통합 ·
  비주얼 회귀 하네스 · CSP 인라인 스타일 이관 · 이미지 OCR/비전 수리 ·
  heartbeat 스트리밍 · detailed 답변 스타일.
- **검색 경로의 유일한 동작 변경** = lifecycle live-consistency arc
  (#1018–#1027): 프로브가 **라이브 그래프 탐색이 lifecycle status 를
  무시**함을 측정으로 증명 → `relation_is_live()` 게이트 적용
  (kill-switch `JAMES_DISABLE_STATUS_FILTER`). 백로그 재측정 결과 회귀 없음.
- ⚠️ **CI 빨간불 (규모 축소됨)**: `test.yml` (pytest) 은 최신 실행
  (2026-08-28) 까지 실패이지만, **#1080 이 66 → 6 failed** 로 줄였습니다.
  진짜 원인은 테스트 노후화가 아니라 **프레임워크 변경**이었습니다 —
  FastAPI 0.141.1 / starlette 1.6.0 이 `include_router` 마다 `path` 없는
  `_IncludedRouter` 래퍼를 붙여, 19개 래퍼가 **약 137개 엔드포인트를
  라우트 assertion 에서 숨겼습니다.** `core/` 20 KB 규칙 위반 2 건도 해소
  (1건 분할 / 1건은 STEP 7 벤치가 필요해 계획과 함께 grandfather).
  **결정론 벤치 (`bash benchmarks/run_all.sh`) 와 발표된 RAB / LRB 수치는
  영향 없습니다.** 초록 복구가 재개 로드맵 Phase 2.
- 마지막 **기능** 세션 2026-06-26. 이후 4 PR 은 문서·인용·CI 유지보수
  (#1077 #1078 #1079 #1080).

---

## 프로젝트 상태 (이전): v0.5 마감 — Time-Travel Dashboard + SaaS-readiness + Pack SDK + CSP nonce

**2026-06-12 릴리스** (v0.5 close handover [PR #862](https://github.com/Hashevolution/James-RAG-Evol/pull/862)). v0.5 cycle 은 21 PR (#841 – #861) 로 enterprise document ontology (B.5 시리즈), B.1 audit gap 구현 (G3 / G4 / G5 / G7 LANDED + G1.a / G2.a primitive), B.2 / B.3 multi-tenant / plugin-API design memo, UI 개선 stream (a11y + aria-live + responsive + CSP 경로), 평가 외부 노출 mapping, 그리고 server-side security headers middleware + tenant-id + approval-evidence primitive 를 마감했습니다.

v0.5 마감 이후 **23 PR (#863 – #886) 가 main 에 추가**되어 (2026-06-12 PM – 2026-06-13), **Time-Travel Dashboard quartet** (TT.a/b/c/d — audit-replay overlay + 3-phase reasoning trail panel + side-by-side now-vs-T diff modal), **v0.6 Pack SDK trio** (CLI scaffolder + author guide + `james-pack-sdk` PyPI packaging with SemVer 12개월 deprecation 정책), **v0.5 G1 + G2 SaaS-readiness trio** (replay-side tenant filter + CR merge wire-in + SaaS 배포 가이드 + OIDC resolver hook + async-task-aware `with_tenant_id`), **Track C CSP nonce middleware** (script-flag 안전 즉시 적용 / style-flag 는 inline-style migration 대기), **graph-RAG synthesis Step 1 + Step 2 driver** (+0.41 path_coverage n=3 ⭐⭐⭐ + cross-model scaffold) 가 ship.

**v0.5 → v0.6 gate (Dim F: ≥6 개월 external customer pilot)** 는 **미통과**. 프로젝트는 [v0.6 entry skeleton (PR #886)](docs/handovers/v0.6-entry-skeleton-2026-06-13.md) 의 2-fork entry contract 가 지배하는 **"v0.5 closed, v0.6 not yet entered"** interval 에 있습니다: Fork A = LOI 서명 → Track D vertical pack scoping / Fork B = 6 개월 no-LOI → reassess. 둘 중 하나 해결될 때까지 mother-platform 강화 계속, vertical 콘텐츠는 CLAUDE.md rule #1 에 따라 BLOCKED.

23 마감 후 PR 모두 streak 유지: **vertical 토큰 0, `core/retrieval` + `core/graph` traversal + `core/reasoning` 0 라인 변경, 4-layer rule #1 보호 contract** (code-level capability gate + doc-level "Out of scope" + naming-level domain-agnostic + trigger-level LOI tagging) 모든 PR 에서 유지.

---

## 🔬 Graph-RAG 가 실제로 얼마나 기여했나?

`multihop_rag` fixture 위 단일 4-cell ablation (N=100, n=3 paired, M_M = gemma4:e4b 4B, git_sha `b686f35`):

| Cell | path_coverage | graded_answer | abstention_f1 | token_cost | latency |
|---|---|---|---|---|---|
| C_minus (RAG 없음) | 0.000 | 0.213 | 0.356 | 675 | 9.8s |
| C_rag-basic (+ vector) | 0.000 | 0.260 | 0.306 | 783 | 12.5s |
| **C_rag-graph (+ graph)** | **0.4056** | 0.203 | 0.400 | 1675 | 32.4s |
| C_rag-ontology (+ typed filter) | 0.4056 | 0.230 | 0.4286 | 1695 | 32.4s |

**Graph-RAG 기여** (C_rag-basic → C_rag-graph):
- **path_coverage +0.41** (load-bearing win, noise band 0.02) — vector-only retrieval 은 multi-hop 쿼리에서 gold supporting-doc 경로의 0% 만 회수; graph traversal 은 ~40% 회수.
- abstention_f1 +0.094 (graph evidence 가 "모를 때 모른다" 보정 개선).
- graded_answer −0.057 (honest loss — graph evidence 가 short-answer 쿼리에 noise 추가; typed-filter 가 +0.027 회복).
- **2.1× token cost, 2.6× latency** (path-coverage win 은 공짜가 아님).

**Cross-time 재현성**: α-6 cycle (2026-06-01, n=1) 은 path_coverage 0.408 측정; Step 1 재실행 (2026-06-13, n=3 median) 이 0.4056 확인. **oracle 12 일 revision 에 걸쳐 stable.**

전체 table + LRB V<N<J 아키텍처 ablation + RAB AC/RF/PC audit ablation + honest negative (closed-book QA, cycle γ deep-multi-hop floor, cost trade-off) 모두 [`docs/evaluation/v0.5-graph-rag-contribution.md`](docs/evaluation/v0.5-graph-rag-contribution.md) 참조.

---

## 프로젝트 상태: v0.4.4 — LRB v0.2.3 S3 publication-scale + cycle γ 4-벤치 인프라 마감

**2026-06-12 릴리스**. v0.4.4 는 v0.4.3 (RAB v0.1.1) 에 **LRB v0.2.3** — *Lifecycle Retrieval Benchmark* 의 cross-scale 재현성 확장 + RAB 의 sibling axis — 을 더합니다. v0.2.1 cross-model (gemma4:e4b 4B / gemma3:12b 12B / mixtral:8x7b 47B / claude-haiku-4-5) 가 Phase B (S2 time-travel) 의 **R@1 V<N<J** 가 single-model artefact 가 아님을 입증했고, **v0.2.3 가 scale 축을 추가**: **12.5× 스케일 점프** (S2 N=80 → S3 publication N=1000) 의 4-point ladder 모든 cell 에서 V<N<J 부등호 + JAMES − Naive gap +0.10 이상 유지. **Pattern + gap 은 scale-robust ⭐⭐⭐, 절대 magnitude 는 scenario-sensitive ⭐⭐** (honest framing 은 preprint §5 에 lock — 12번째 wrong-fix-averted 이자 **첫 self-catch** 의 S3.1 contract-vocabulary fix 가 pre-S3.1 over-tight verdict 를 retract).

같은 cycle 에서 **cycle γ 4-벤치 measurement 인프라 마감**: D-alce research-tier NLI adapter (RoBERTa-MNLI + DeBERTa-v3-ANLI) + D-2wiki supporting-fact-aware producer 가 ALCE / 2Wiki 셀을 v0.4.3 의 ⭐ infra-only 에서 4-of-4 research-tier-ready 로 격상.

**Papers 제출 준비 완료** (pre-flight 마감, arXiv endorsement 대기):
- **RAB preprint** (10페이지): [papers/rab-preprint/main.pdf](papers/rab-preprint/main.pdf) — *EU AI Act Art. 10/12/19 를 측정 가능 audit-quality 벤치마크로 operationalise.*
- **LRB preprint** (11페이지): [papers/lrb-preprint/main.pdf](papers/lrb-preprint/main.pdf) — *RAG 의 temporal validity 축; 4 모델 × 4 스케일에서 V<N<J 보존.*

SEKOS production runtime 변경 없음 — v0.4.4 는 generator, scorer, runner, NLI adapter, 8 pre-registration LOCK 문서 만 ship. arXiv preprint 는 Zenodo DOI [10.5281/zenodo.20652679](https://doi.org/10.5281/zenodo.20652679) 를 data availability 로 인용.

---

## 프로젝트 상태: v0.4.3 — RAB v0.1.1 (Replayable-Audit Benchmark) + Cycle γ multi-hop arc 마감

**2026-06-10 릴리스**. v0.4.3 는 **RAB v0.1.1** 출시 — RAG / agent 시스템의 audit log 품질을 측정하는 최초 replayable-audit benchmark. 3 결정론적 metric (AC / RF / PC) 는 EU AI Act Art. 10/12/19 (Art. 113 에 따라 2026-08-02 부터 적용) 의 operationalisation. JAMES AC/RF/PC = 1.000 / 1.000 / 1.000 vs Baseline-0 (vanilla quickstart + default logging) = 0.275 / 0.000 / 0.000 (scenario-S1). Headline 은 SUT 간 **gap structure** — JAMES 점수 자체가 아님 (SPEC §6.5 가 JAMES-wins framing 명시 거부). Honest framing: **벤치마크 자체가 contribution, 아키텍처 아님** — ActiveGraph (arXiv 2605.21997) 가 audit-native runtime 의 독립 co-invention; 빈 곳은 측정이지 시스템이 아님.

같은 cycle 의 companion track 이 **Cycle γ multi-hop arc** 마감 (PR #752 → #757) — 6 honest null: multi-hop improvement 가 SEKOS 로드맵에서 reframe out; **graph build O(N²)** secondary finding 이 RAB 의 RF-cost 축으로 lift.

이전: **v0.4.2** (2026-06-06) 가 T5 Replayable Audit Graph 출시 — 전체 event-sourced graph-wide 재구성 (`reconstruct_graph_at(t)` audit-only primitive, RAB 가 측정하는 품질의 building block).

이전: **v0.4.1** (2026-05-28) 가 v0.4.0 이 절반만 마친 CASCADE
pillar 를 마감합니다. base fact 의 sources 가 모두 제거되면,
`derived_from` 이 그 base 를 가리키는 edge 들이
`invalidate_derived_facts` 로 자동 무효화 — 파생 체인이 운영자
개입 없이 내부 정합성을 유지합니다. derivation-type 별 semantics
(T6.C.b 정정): `transitive` / `inferred` 는 구조적 체인 링크
(any base empty → invalidate); `operator` 는 보조적
(hard deps 가 없고 모든 operator base 가 비었을 때만 invalidate).

이전: **v0.4.0** (2026-05-27) 은 Layer 4 first bundle —
**T1 Temporal Validity + T7 Supersede Chain + T2 Contradiction
Arbitration** — 을 Sprint 5 의 8 PR 시퀀스로 출시. CASCADE 와
EVENT 의 분리 invariant 가
`tests/test_t7_release_gating_invariants.py` (실제 wiki 픽스처
대상, 목 아님) 으로 **end-to-end 증명**. supersede chain
프리미티브 (`reconstruct_view_at`) 가 무관한 CASCADE 삭제 이벤트
후에도 "시점 T 에 무엇이 참이었나" 를 결정론적으로 답변.

이전: v0.3.0 (2026-05-17) Foundation Hardening 마감 — 6 축
(아키텍처 / 평가 / 관찰성 / 보안 / 통제 진화 / 실데이터 검증)
모두 통과; 두 번째 사용자 게이트 2026-05-13 마감.

- **프로덕션 준비 안 됨** — 운영 성숙도 (HTTPS / SSO / 멀티테넌시 /
  백업 CLI) 는 v1.0 산출물. [SECURITY.md](SECURITY.md) 참조
- 보안 우선 원칙으로 end-to-end 설계
- 협업 환영 — 외부 기여자는 첫 PR 시 1회 클릭 CLA 서명
  ([라이선스](#라이선스) 참조)

---

## 전략 프레임: 단일 제품이 아닌 모체 플랫폼

SEKOS 는 **하나의 버티컬**을 만드는 것이 아닙니다. 법률·식품·유통·
여행 등의 도메인 팩이 **v1.0 이후에만** 분기할 수 있는 "모체
플랫폼"으로 강화 중입니다. 그 전까지는:

- 도메인 특화 기능은 `core/` 에 들어가지 않음
- 모든 변경이 동일한 6 차원 readiness 프레임워크로 측정
  (아키텍처 / 확장 API / 평가 계약 / 운영 성숙도 / 보안 경계 /
  프로덕션 검증)
- 미래의 팩이 의존할 플러그인 계약을 설계 + 스트레스 테스트 중

6 차원 / 4 게이트 (v0.2 / v0.3 / v0.4 / v1.0) / 3 분기 형태
(Domain Pack / Distribution / Vertical Product) 전체 설명은
[`docs/PLATFORM_READINESS.md`](docs/PLATFORM_READINESS.md) 참조.

---

## 무엇이 다른가 — Replayable RAG

대부분의 RAG 시스템은 *"답이 뭐야?"* 한 가지 질문에 답합니다.
SEKOS 는 두 가지를 더 답합니다:

- **시점 T 에 시스템이 무엇을 알고 있었나?** — T7 supersede chain
  이 fact 의 과거 상태를 보존하고, `reconstruct_view_at(t)` 가
  무관한 CASCADE 삭제 이벤트 후에도 임의 과거 시점에 활성이었던
  edge 를 반환합니다.
- **왜 그렇게 답했나?** — 모든 추론 단계 (query rewrite, retrieval,
  rerank, planner, reflect, verify, synth) 가 append-only audit row
  를 남깁니다. `scripts/replay_trace.py <trace_id>` 가 전체 시퀀스
  를 바이트-동일하게 재구성합니다.

이 둘의 결합이 SEKOS 를 **Replayable RAG** 카테고리에 위치시킵니다.
Agentic RAG (*"AI 가 무엇을 할 수 있나"* 에 최적화) 와 다르고,
Mem0 형 메모리 layer (LLM judge 로 belief 갱신) 와 다릅니다.
SEKOS 는 LLM-free 결정론적 4-rule decision tree
(`core/lifecycle/contradiction_arbiter.py:classify_contradiction`)
로 belief 를 갱신하고, 과거 fact 를 overwrite 하는 대신 보존해
replay 가능하게 만듭니다.

### 어떻게 만들어졌나

1. **결정론적 메모리 lifecycle** (v0.4.0) — T1 Temporal Validity +
   T7 Supersede Chain + T2 Contradiction Arbitration. CASCADE
   (destructive, Layer 3) 와 EVENT (history-preserving, Layer 4)
   는 코드 path 가 분리 보장 —
   `tests/test_t7_release_gating_invariants.py` 가 실제 wiki
   픽스처로 release-gate.
2. **출처 인식 Graph-RAG** — 12 typed relation 이 임베딩 이상의
   의미를 부여하고, 모든 relation 에 `sources: [{doc_id, weight,
   role, ts}]` 가 부착되어 문서 삭제/수정 시 영향받은 파생 지식만
   외과적으로 갱신 (Knowledge Cascade A→E, v0.3.0).
3. **Cognitive Layer** — cross-encoder reranker (디폴트 ON),
   LLM query rewriter, reflection loop (draft → critique → revise),
   verification engine (security + fact check), tool router.
   하나의 `trace_id` 로 8 단계 추론 시퀀스를
   `scripts/replay_trace.py` 로 재구성 가능.
4. **PolicyEngine — sprinkle 아닌 layer** — 역할/민감도 결정의
   단일 진입점이 retrieval / graph / output / tools 모두에 연결.
   제거하면 6+ 모듈이 깨짐 (v0.2 Axis 4).
5. **Change Request 프리미티브** — 모든 쓰기 (위키 편집, 워크스페이스
   잡, 자가-진화 패치) 가 propose → review → admin 승인 →
   atomic apply → audit 행으로 라우팅. silent write 없음.
6. **인간 게이트 뒤 자가-진화** — 피드백 → 후보 → bench eval →
   인간 승인 → 배포 → 회귀 시 auto-rollback. 배포된 모든 패치는
   `approver_username` 감사 행을 보유 (v0.2 Axis 5).
7. **100% 로컬** — Ollama 로 노트북에서 실행 가능. 기본 설정에서
   클라우드 LLM 의존성 없음.

> 모든 기능은 STEP 7 13-query baseline + RAGAS 메트릭으로 회귀
> 테스트. `core/{retrieval,graph,reasoning}` 을 건드리는 PR 은
> bench 숫자 없이 머지 불가.

---

## 빠른 시작

### 사전 요구사항

- Python 3.11+
- [Ollama](https://ollama.ai) 설치 및 실행
- 최소 16GB RAM (32GB+ 권장)
- (선택) NVIDIA GPU — 빠른 추론
- (선택) Tavily API 키 — 웹 검색 ([무료 1k/월](https://tavily.com))

### 설치

```bash
git clone https://github.com/Hashevolution/James-RAG-Evol
cd James-RAG-Evol

# 환경 설정
cp .env.example .env
# .env 편집 — JAMES_API_KEY, JAMES_JWT_SECRET 설정

# 의존성 설치
pip install -r requirements.txt

# 서버 시작 (첫 로그인 시 admin wizard 가 모델을 자동 추천)
python server_llmwiki.py
```

`http://localhost:8000/admin` 접속 — admin wizard 가 하드웨어를
측정하고 적합한 Ollama 모델을 한 번 클릭으로 설치합니다. 이후
`http://localhost:8000` 에서 채팅 UI 사용.

---

## 아키텍처

```
[사용자 쿼리]
     ↓
[보안 필터]              ← 인젝션 패턴 + PolicyEngine pre-check
     ↓
[쿼리 라우터]            ← chat / coding / retrieval / web_search
     ↓
[Query Rewriter]         ← LLM 재작성 (opt-in, JAMES_ENABLE_QUERY_REWRITE)
     ↓
[하이브리드 검색]        ← Vector(60%) + BM25(20%) + keyword(10%) + name(10%)
     ↓
[Cross-Encoder Rerank]   ← MiniLM-L-6-v2 (디폴트 ON; JAMES_DISABLE_RERANK=1 끄기)
     ↓
[그래프 엔진]            ← DFS + 출처 인식 + 민감도 게이팅
     ↓
[추론 루프]              ← retrieve → expand → reflect (opt-in) → verify (opt-in)
     ↓
[Tool Router]            ← read 툴 직접; write 툴 → Change Request
     ↓
[출력 필터]              ← PII 마스킹 + 역할 기반 필터
     ↓
[답변 + 추론 경로 + trace_id]
```

모든 단계가 하나의 `trace_id` 에 연결된 행을 남깁니다.
`scripts/replay_trace.py <trace_id>` 로 `audit_log` 에서 전체
시퀀스를 재구성. Cognitive Layer 설계는
[`docs/ARCHITECTURE.md §5.7`](docs/ARCHITECTURE.md) 참조.

---

## 폴더 구조

```
James-RAG-Evol/
├── core/
│   ├── reasoning/        retrieval / reflection / verification / tool router
│   ├── retrieval/        하이브리드 검색 + cross-encoder reranker + query rewriter
│   ├── memory/           장기 기억 (db / conversation / summaries)
│   ├── plugins/          플러그인 계약 표면 (Provider Protocol)
│   ├── policy_engine.py  역할/민감도 결정의 단일 진입점
│   ├── change_request.py propose/review/approve 쓰기 프리미티브
│   ├── cascade.py        파일 삭제/수정 → 그래프 외과적 갱신
│   ├── graph_editor.py   edge 편집 (replace/append/delete) + 양방향 동기화
│   └── ...
├── eval/                 STEP 7 회귀 baseline + RAGAS suite
├── llm/                  LLM provider 추상화
├── tools/                capability token 게이팅 툴 모듈
├── frontend/             웹 UI (HTML + JS)
├── processors/           파일 전처리
├── wiki/                 지식 그래프 (마크다운 + sources)
├── memory/               장기 기억 DB
├── workspace/            Change request, 패치, 제안
├── scripts/              bench.py / replay_trace.py / 운영 스크립트
├── reports/              평가 결과 + 홍보 자료
├── docs/                 ARCHITECTURE / PLATFORM_READINESS / ROADMAP / handovers
└── server_llmwiki.py     메인 서버 진입점
```

---

## 보안 접근법

SEKOS 는 보안을 **기능이 아닌 설계 원칙**으로 다룹니다:

- **3단계 접근 제어**: Vector → Graph → Output
- **RBAC** (4가지 역할) + **ABAC** (4가지 민감도)
- **지시어 격리**: 명령과 데이터 분리
- **JWT 인증** + 속도 제한 + 전체 감사 로그
- **샌드박스 실행** (툴 호출용)

> 현실적 고지: 합성 데이터 테스트는 적대적 프로덕션 테스트와 다릅니다. [SECURITY.md](SECURITY.md) 참조.

---

## 현재 기능

| 기능 | 상태 |
|------|------|
| 하이브리드 검색 (Vector + BM25 + keyword + name) | 작동 |
| Cross-encoder reranker (MiniLM-L-6-v2) | 작동 — 디폴트 ON (v0.3) |
| LLM query rewriter | Opt-in (v0.3) |
| 출처 인식 Graph-RAG (Knowledge Cascade A→E) | 작동 (v0.3) |
| PolicyEngine (RBAC + ABAC + capability token) | 작동 (v0.2 Axis 4) |
| Reflection loop (draft → critique → revise) | Opt-in (v0.3) |
| Verification engine (security + fact check) | Opt-in (v0.3) |
| Tool router (read 직접, write → Change Request) | 작동 (v0.3) |
| Change Request 프리미티브 (위키 + 잡 + 패치) | 작동 (v0.2.x + v0.3) |
| 자가-진화 (인간 승인 + auto-rollback) | 작동 (v0.2 Axis 5) |
| Trace replay (하나의 `trace_id` → 전체 추론 시퀀스) | 작동 (v0.3) |
| 멀티모달 (이미지/영상/오디오 + OCR-poison 격리) | 작동 (v0.2 Axis 4) |
| 웹 검색 (Tavily / DuckDuckGo fallback) | 작동 |
| 멀티 LLM 라우팅 (Ollama + Claude CLI 백엔드) | 작동 |
| STEP 7 회귀 baseline + RAGAS | 작동 (v0.2 Axis 2) |
| 실데이터 검증 (두 번째 사용자 게이트) | 통과 2026-05-13 |

---

## 기술 스택

- **백엔드**: FastAPI + Uvicorn
- **LLM**: Ollama (Gemma, DeepSeek-Coder, LLaVA)
- **벡터 DB**: ChromaDB
- **임베딩**: Sentence-Transformers (MiniLM)
- **검색**: BM25 + Vector 하이브리드
- **웹 검색**: Tavily (1순위) + DuckDuckGo (fallback)
- **인증**: JWT (python-jose)
- **저장소**: SQLite + 마크다운 위키

---

## 로드맵

[ROADMAP.md](ROADMAP.md) 와
[`docs/PLATFORM_READINESS.md`](docs/PLATFORM_READINESS.md) 참조.
요약:

- **v0.1**: 핵심 엔진 + 스캐폴딩 (릴리스)
- **v0.2**: Foundation Hardening — 6축 (2026-05-13 마감)
- **v0.3**: Platform Skeleton — Cognitive Layer + Knowledge Cascade
  + Change Request 프리미티브 (현재; 2026-05-17 릴리스)
- **v0.4**: First Domain Pilot — 팩 1개 + 외부 고객 1명, 6개월
  무회귀
- **v1.0**: Production-Grade Mother — HTTPS / SSO / 멀티테넌시 /
  SOC2 준비; 외부 개발자가 자체 팩 출판 가능

멀티에이전트 specialist, optional Neo4j 백엔드, OpenAI 호환 API,
streaming, federation 은 Beyond v1.0 으로 재배치 (speculative) —
[`ROADMAP.md` §Beyond v1.0](ROADMAP.md) 참조.

---

## 기여

환영합니다! [CONTRIBUTING.md](CONTRIBUTING.md) 참조.

우선 영역:
- 문서, 예시, 번역
- 버그 수정, 테스트 커버리지
- 새 툴 및 LLM 제공자 통합

---

## 라이선스

**MIT 라이선스로 배포됩니다.** 자유롭게 사용하세요. [LICENSE](LICENSE) 참조.

외부 기여자는 첫 PR 시 [Contributor License Agreement](docs/legal/CLA.md)
한 번에 서명 (CLA Assistant 봇이 자동 안내). 1회 서명으로 이후 모든 기여
커버. 자세한 안내는 [CONTRIBUTING.md](CONTRIBUTING.md#license--contributor-license-agreement-cla)
§License & CLA 섹션, 서명 없이 기여하는 경로는
[docs/legal/non-cla-contributions.md](docs/legal/non-cla-contributions.md) 참조.

외부 의존성의 라이선스 전체 목록은
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) 참조.

---

## 감사

다음에서 영감을 받았습니다:
- [Microsoft GraphRAG](https://github.com/microsoft/graphrag)
- [LightRAG](https://github.com/HKUDS/LightRAG)
- [Graphiti](https://github.com/getzep/graphiti)
- Palantir 스타일 온톨로지 접근법
- YoungHu 실사용 피드백, 방향성 논의 기여

---

## 면책 조항

**본인 책임 하에 사용하세요.** 이것은 연구 코드입니다. 추가 강화 없이 민감한 데이터 처리나 프로덕션 보안에 대한 어떠한 보증도 없습니다.
