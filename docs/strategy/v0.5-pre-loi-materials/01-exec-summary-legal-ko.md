# JAMES 1-페이지 요약 (법무 도메인 pilot, 2026-06-12)

> **JAMES = 시간 인지 + 감사 추적 가능한 로컬-퍼스트 RAG 시스템**.
> 계약 체결 시점의 정확한 규정 / 본문 / 책임자 정보를 추적 가능하며,
> 모든 검색·답변 chain을 자체 감사 가능. v0.5 pilot은 법률 도메인에서
> 6 개월 측정으로 회사 사용 적합성 검증.

---

## 1. 왜 JAMES 인가 (외부 측정 기반 3 점)

### ① 감사 추적 — RAB benchmark publication tier ✓

**Replayable Audit Benchmark (RAB v0.1.1)** 측정 결과:

| 시스템 | 감사 완전성 | 재현 정확도 | 출처 chain |
|---|---|---|---|
| **JAMES** | **1.000** | **1.000** | **1.000** |
| 일반 RAG (vanilla) | 0.275 | 0.000 | 0.000 |
| OpenTelemetry tracing | 0.500 | 0.000 | 0.000 |

→ **모든 INGEST / UPDATE / SUPERSEDE / DELETE / ANSWER 이벤트** 자동 기록 +
log 만으로 graph 상태 완전 재구성. EU AI Act 발효 (2026-08-02) Art.10 /
12 / 19 대응 가능.

→ DOI: `10.5281/zenodo.20625533` (Zenodo 공개 archive, 외부 재실행 가능)

### ② 시간 인지 검색 — LRB benchmark ⭐⭐⭐ tier ✓

**Lifecycle Retrieval Benchmark (LRB v0.2.1)** 측정 결과 (4 모델 × 3 SUT
× 시간여행 시나리오):

| 시스템 | 첫 결과 정확도 (R@1) — claude 모델 |
|---|---|
| 일반 RAG (vanilla) | 0.6125 |
| Naive supersede | 0.7750 |
| **JAMES** | **0.9750** |

→ "체결 시점 정책 본문은?" / "발령 시점 부서장은?" 같은 시간 시점 질의에
**JAMES만 정확히 답변 가능**. 4 모델 (4B/12B/47B/claude) 모두에서 동일
순위 유지 → 단일 모델 fluke 아님.

### ③ 로컬-퍼스트 + 격리 — 보안 / 영업비밀 / 변호사-의뢰인 비밀특권

* **단일 클라이언트 instance** (workspace 격리, customer 인프라 내 배포 가능)
* **외부 cloud 호출 0** (필요 시 trust zone gate를 통한 opt-in cloud 사용)
* **모든 데이터 customer 보유** (operator side에 raw 데이터 0)
* **공개 source code** (Hashevolution/James-RAG-Evol)

---

## 2. 측정-evidenced 가 아닌 것 (정직)

다음 axes는 **literature와 동급 수준** (자메스만의 우위 측정-evidence 없음):

* **일반 multi-hop reasoning** (MuSiQue 벤치) — 일반 RAG와 동등 (3 SUT
  cell-by-cell identical)
* **단순 retrieval recall** (top-10) — 일반 RAG와 비슷한 수준
* **답변 생성 품질** — base LLM (gemma3:12b / claude 등) 성능 그대로 사용

→ 자메스의 차별 가치는 **"답을 더 잘 만든다"가 아니라 "어떤 답이 어디
서 나왔는지 + 그 답이 어느 시점에 valid 했는지" 추적 가능**.

---

## 3. v0.5 pilot 제안 — 6 개월

### Scope
* 부서: 1 개 부서 (KM / 1 practice area, 예: M&A 또는 노동)
* 사용자: 50-200 명 active
* 데이터: 계약서 / 의견서 / 정책 / 표준 조항 (초기 corpus 5,000-50,000 docs)

### Success metrics (사전 합의)
1. **감사 완전성** (RAB AC) ≥ 0.99
2. **시점 정확 retrieval** (LRB R@1) ≥ 0.65
3. **사용자 만족도** NPS ≥ 30 또는 재계약 의향 ≥ 70%
4. **Production incident** P1=0, P2≤2
5. **Core regression**: 0 (RAB monthly measurement)

### Pricing
* **Cost-recovery base**: 월 450-800 만원 (인프라 + operator 시간 실비)
* 결과 발표권 협의: pilot evidence 외부 공동 발표 가능 시 가격 협상 우대
* 정식 가격 = v1.0 진입 (~22 개월 후) + customer evidence 검증 후

---

## 4. 다음 step

| 단계 | Action | 소요 |
|---|---|---|
| 1 | **이 요약본 검토** (귀사 IT / 법무) | 1-2 주 |
| 2 | **Technical brief 공유** (02-technical-brief.md) | 1 주 |
| 3 | **Pilot proposal 협의** (03 + 04 + 05) | 2-4 주 |
| 4 | **LOI 서명** (NDA + DPA + pilot terms) | 2 주 |
| 5 | **Pilot kickoff** (workspace 배포 + corpus ingest) | 4 주 |
| 6 | **Pilot 운영 + monthly checkpoint** | 6 개월 |

총 LOI 서명까지 1-3 개월, pilot 종료까지 +6 개월.

---

## 5. 문의

* **Email**: karu-7@hanmail.net
* **GitHub**: https://github.com/Hashevolution/James-RAG-Evol
* **Zenodo (RAB DOI)**: https://doi.org/10.5281/zenodo.20625533
* **Reference**: 본 docs 의 모든 측정 결과는 위 repo에서 재실행 가능

---

*Disclaimer: 이 자료의 측정-evidenced 주장 (RAB AC/RF/PC = 1.000 / 0.275;
LRB S2 R@1 J=0.975) 은 commit된 result.json artefacts에서 추적 가능
하며, 사전 등록된 시나리오 fixture로 귀사 환경에서 bit-for-bit 재현
가능합니다. JAMES는 local-first auditable knowledge reasoning system
이며, pilot 의 목적은 측정 evidence를 실제 도메인 workflow에서 검증
하는 것이지 어떤 규제 프레임워크에 대한 compliance 인증이 아닙니다.
EU AI Act 인용은 descriptive 이지 prescriptive 가 아닙니다.*
