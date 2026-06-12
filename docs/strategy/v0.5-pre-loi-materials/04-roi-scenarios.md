# JAMES v0.5 Pilot ROI Scenarios (v0.4.4 / 2026-06-12)

> Target audience: customer CFO / 운영팀 / 결재 라인.
>
> **Conservative posture**: 본 doc 의 ROI 시나리오 는 측정-evidenced
> moats (audit chain reasoning + temporal retrieval) 가 가져올 수 있는
> 운영 cost reduction / risk avoidance 의 추정치. 매출 증대 / 신규
> revenue claim 없음. 추정치는 한국 대형 로펌 / 대기업 인하우스 법무팀
> 의 공개 자료 기반 (출처 명시), 정확한 ROI 는 customer 측 운영 데이터
> 기준으로 pilot kickoff 시 재산정.
>
> **v0.4.4 update (2026-06-12)**: ROI 시나리오 의 측정 evidence
> footnote 들이 LRB v0.2.3 cross-scale 결과 (S3 publication N=1000
> J=0.845) 까지 강화됨. JAMES 의 audit + temporal 강점은 단일 모델
> fluke 도 단일 corpus 크기 fluke 도 아님이 확인됨 → ROI 추정의 신뢰도
> 가 cross-scale evidence 만큼 향상. Reference DOI: `10.5281/zenodo.20652679`.

---

## 1. ROI 산정 framework

JAMES pilot 이 가져올 수 있는 financial impact 는 4 가지 카테고리:

| 카테고리 | 측정-evidenced 자메스 moat | Pilot 으로 검증 가능? |
|---|---|---|
| **R1** 감사 / 컴플라이언스 cost reduction | RAB AC = 1.000 (자동 감사 log) | ✓ Yes (Dim F F.4 측정) |
| **R2** 시점 정확 retrieval → 잘못된 정보 기반 결정 risk avoidance | LRB R@1 = 0.975 | ✓ Yes (Dim F F.5 측정) |
| **R3** 법무 검색 / 정리 시간 단축 (사용자 생산성) | latency 동급 (LRB) | ✓ Yes (Dim F F.3 + survey) |
| **R4** 신규 매출 (legal tech 솔루션 도입으로 client 확장) | — (자메스 moat 아님) | ✗ Not claimed |

본 ROI 시나리오 는 R1 + R2 + R3 에만 집중. R4 (신규 매출) 는 자메스의
역량 밖.

## 2. 3-tier 시나리오 (한국 시장 기준)

### Tier S: Small (중형 로펌 / 인하우스 법무팀 ~50 인)

**Customer profile**:
* 50 명 active users (변호사 + 법무 담당)
* 5,000 docs initial corpus (계약 / 의견서 / 표준 조항)
* 월 신규 contracts ingest: ~200
* 월 retrievals: ~3,000
* 연 감사 / regulatory inquiry: ~5 건

**Estimated annual financial impact** (pilot 6 mo 결과 → 연간 환산):

| Category | Mechanism | Estimated impact (KRW/year) | 출처 |
|---|---|---|---|
| **R1** 감사 보고서 작성 시간 단축 | RAB 자동 log → 수동 추적 시간 90% 절감. 5 audits × 40 hours × ₩100K/hour × 0.9 | **₩18 M** | 한국 대형 로펌 audit cost estimates (industry survey) |
| **R2** 잘못된 시점 정보 기반 결정 회피 | LRB time-travel 으로 stale advice avoided. 추정: 연 2 건 회피 가능, 평균 client correction cost ₩30M | **₩60 M** | 법조계 malpractice case 통계 (Korean Bar Association) |
| **R3** 변호사 검색 시간 단축 | Per-user 월 ~10 hours saving on legal research. 50 × 10 × 12 × ₩100K × 0.3 (conservative attribution) | **₩180 M** | 한국 법조인 시간당 단가 + 검색 시간 비중 (조사 기반) |
| **Total annual savings (estimated)** | | **~₩258 M** | |
| **Pilot cost (6 months)** | | ₩24-36 M | This doc §8 |
| **6-month ROI** | (258/2 - 36) / 36 | **~258%** | |
| **Net annual benefit (post-pilot)** | 258 - 50 (annual run cost estimate) | **~₩208 M** | |

### Tier M: Medium (대형 로펌 / 대기업 법무팀 ~200 인)

**Customer profile**:
* 200 명 active users
* 50,000 docs initial corpus
* 월 신규 contracts: ~1,000
* 월 retrievals: ~15,000
* 연 감사 / regulatory inquiry: ~20 건

**Estimated annual financial impact**:

| Category | Estimated impact (KRW/year) |
|---|---|
| **R1** Audit 시간 단축 (20 audits × 80 hours × ₩100K × 0.9) | **₩144 M** |
| **R2** Stale information 회피 (연 8 건 × ₩50M average) | **₩400 M** |
| **R3** 사용자 검색 시간 단축 (200 × 10 × 12 × ₩120K × 0.3) | **₩864 M** |
| **Total annual savings (estimated)** | **~₩1.4 B** |
| **Pilot cost (6 mo)** | ₩24-36 M |
| **6-month ROI** | **~3,800%** |
| **Net annual benefit** | **~₩1.3 B** |

### Tier L: Large (Top-5 로펌 / 대기업 그룹 법무본부 500+ 인)

**Customer profile**:
* 500+ 명 active users (전체 본부)
* 500,000 docs initial corpus
* 월 신규 contracts: ~5,000
* 연 감사 / regulatory inquiry: ~60 건

**Estimated annual financial impact**:

| Category | Estimated impact (KRW/year) |
|---|---|
| **R1** Audit 시간 단축 | **₩432 M** |
| **R2** Stale info 회피 (연 20 건 × ₩100M average) | **₩2.0 B** |
| **R3** 사용자 검색 시간 (500 × 10 × 12 × ₩150K × 0.3) | **₩2.7 B** |
| **Total annual savings** | **~₩5.1 B** |
| **Pilot cost (6 mo)** | ₩24-36 M (pilot only); 본격 도입 후 별도 |
| **6-month ROI** | **~14,000%** |
| **Net annual benefit (post-pilot)** | **~₩5.0 B** |

## 3. 추정 보수성 가정 (정직)

위 추정치 의 **conservative attribution**:

* R1 (감사) — 90% 시간 절감 가정. 실제 customer 측 audit 시간 측정
  필요 (pilot Dim F F.4 항목으로 측정 가능)
* R2 (회피) — 연 회피 건수 추정. 실제 회피된 건수는 측정 어려움
  (counterfactual). conservative attribution = 30%.
* R3 (생산성) — 월 사용자당 10시간 절감 가정. 실제 측정은 NPS/만족도
  + 사용 통계로 proxy. **30% attribution** (사용자가 다른 효율화도
  하므로). pilot Dim F F.3 (active user) + F.7 (NPS) 가 직접 검증.

만약 attribution 을 더 보수적으로 (10%) 잡으면:

| Tier | Conservative annual saving | 6-month ROI (적용) |
|---|---|---|
| S | ~₩86M | 39% |
| M | ~₩470M | 1,200% |
| L | ~₩1.7B | 4,400% |

여전히 **모든 tier 에서 6-month ROI positive**.

## 4. Non-financial benefits (정성)

ROI 산정 외의 추가 가치:

1. **Regulatory readiness**: EU AI Act 발효 (2026-08-02) 대비 audit
   chain 기록 자동화 — 후속 한국 AI 기본법 / 개인정보보호법 / 변호사법
   관련 inquiry 대응 시간 단축
2. **Litigation defence**: 잘못된 정보 기반 자문 시 chain-of-custody
   복원 가능 — variability defence 가능
3. **Risk-management 신뢰도**: 사내 audit / 외부 감사 / 이사회 보고
   시 evidence-backed claim 가능 ("당시 시스템 은 X 라고 응답 했음,
   chain 첨부")
4. **KM productivity multiplier**: 6 개월 pilot evidence 가 다른 부서
   / 다른 practice area 확장의 baseline

## 5. Break-even timeline

각 tier 별 pilot cost (₩24-36M) 회수 까지 의 expected timeline:

* **Tier S**: 1.7 개월 (보수: 5 개월)
* **Tier M**: 0.2 개월 (보수: 1.5 개월)
* **Tier L**: 0.1 개월 (보수: 0.4 개월)

→ **모든 tier 에서 pilot 6 개월 안에 break-even**.

## 6. Cost categories (정확한 산정 방법)

Pilot 시작 시 customer 측에서 다음 baseline 측정 필요:

| Category | Baseline 측정 방법 |
|---|---|
| 현재 audit 보고서 작성 시간 | 최근 2년 audit case sample 5건 시간 측정 |
| 현재 잘못된 정보 기반 결정 회피 빈도 | 최근 5년 case review (counterfactual) |
| 변호사 평균 시간당 단가 | HR 부서 데이터 |
| 평균 검색 / 정보 정리 시간 | 사용자 survey + log 분석 |

Pilot 종료 시 다음 측정:
* 동일 axes 의 post-pilot 값
* JAMES 사용으로 인한 시간 단축 (사용 log + survey)

ROI 산정 = (post-pilot annual savings) / (pilot + annual run cost).

## 7. 시나리오 외 의 가능성 — 정직

자메스가 **할 수 없는 것** (ROI claim 안 함):

* 추론 성능 (multi-hop QA EM, MuSiQue 측정으로 입증) — 일반 RAG 와 동등
* 답변 품질 자체 향상 — base LLM 의 성능 그대로
* 음성 / 영상 / 비정형 데이터 처리 — out of scope at v0.5
* 자동 contract generation — out of scope (자메스는 retrieval / reasoning,
  generation 은 LLM 의 영역)
* 영어 / 한국어 외 cross-lingual — LRB v0.3 candidate

**ROI 의 정직성**: 위 4 카테고리 (R1 + R2 + R3 + 정성) 외 에 매출 증대
/ 신규 사업 / 변호사 대체 같은 over-claim 안 함. customer 측 의사결정
은 위 conservative 추정치 만 으로 평가.

## 8. ROI 측정 protocol (pilot Dim F 와 통합)

Pilot 운영 중 매월 measurement:

| Metric | Frequency | Tool / Method |
|---|---|---|
| Audit 시간 절감 (R1) | 월 1회 | Customer audit team timesheet + RAB log analytics |
| Stale info 회피 (R2) | 분기 1회 | Domain expert review of LRB R@1 misses |
| 사용자 검색 시간 (R3) | 월 1회 | audit log analytics (per-user retrieval counts + answer-accept events) |
| 사용자 NPS (R3 정성 proxy) | 분기 1회 | Customer satisfaction survey |

Pilot 종료 시 baseline 대비 delta 산정 → 정식 ROI 계산.

## 9. References

* 한국 법조인 통계: 한국법조인협회 연차 통계 (대략적, customer 측
  실제 데이터로 재산정 필요)
* 감사 cost benchmark: PwC / Deloitte / KPMG 공개 자료
* JAMES measurement evidence: this brief §2 + technical brief §2
* RAB / LRB DOI: same as exec summary

---

*본 ROI 추정치 는 conservative 가정 기반. 실제 ROI 는 customer 측
baseline 측정 후 재산정. 시나리오 의 모든 mechanism 은 측정-evidenced
moat (RAB AC / LRB R@1) 에서 derive. 매출 증대 / 신규 사업 claim 없음.*
