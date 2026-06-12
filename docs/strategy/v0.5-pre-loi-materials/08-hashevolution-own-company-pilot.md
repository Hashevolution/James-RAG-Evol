# Hashevolution Own-Company Pilot Scenario (v0.4.4 / 2026-06-12)

> **Audience**: Operator (Jiwon Seo / Hashevolution) — 본인 결재 판단 자료.
>
> **Scope**: External pilot 협상 시작 전, **Hashevolution 자체** 가
> JAMES 의 first customer 가 되는 시나리오를 evaluation. v0.5 pilot
> 의 Dim F (production proof) gate 충족 가능 여부 판단 + Tier S contact
> outreach 대비 진입 timing 단축 가능성 평가.
>
> **Honest posture**: 본 doc 은 self-eval. Customer-facing 자료 아님.
> Conflict of interest 명시 — operator 가 customer + supplier 동시 역할.
> 그러나 v1.0 production 진입 timing 을 결정짓는 Dim F gate (6개월
> external customer pilot) 의 시간 비용 (~9-15개월 LOI 협상 + pilot)
> 을 줄일 수 있는 path 라면 분석 가치 있음.

---

## 1. 가능성 frame

### 1.1 Hashevolution 의 현 상태 (operator self-assessment)

| 차원 | 상태 | First-customer 시나리오 적합도 |
|---|---|---|
| 법인 형태 | 1인 사업자 (개인) | △ — 법인격 명확하면 더 강함 |
| 운영 매출원 | (operator 답변 필요 — 본인 회사 운영 자료 외부 컨설팅 / 솔루션 개발 / 라이선스 등) | ? |
| 도메인 자료 | 본인 회사 내부 계약 / 정책 / 매출 기록 / 업무 문서 | ✓ 실제 사용 가능 (소량) |
| 사용자 수 | 1 명 (operator) → 향후 확장 가능성 | ✗ 50-200 user 기준 미달 |
| 회사 결재 / IT / 보안 부서 | 분리되지 않음 (1인 사업자) | ✗ 다부서 사용 시나리오 불가 |
| 데이터 보안 / 컴플라이언스 의무 | 일반 사업자 수준 (특정 인증 X) | △ — EU AI Act 대응 모델 케이스 빈약 |
| Pilot 비용 부담 | self-funded | ✓ — cost-recovery negotiation 불필요 |

### 1.2 자체 pilot 의 가치 (가설 시나리오)

만약 Hashevolution 자체를 first customer 로 활용하면:

| 측면 | 가치 | Risk |
|---|---|---|
| **timing 단축** | external LOI 대기 (~3-9개월) 우회 → pilot kickoff 즉시 | external evidence 약함 |
| **iteration 속도** | operator = user → 피드백 loop 무한 | self-eval trap (자기 검증) |
| **first-domain 실증** | legal pack 의 generic 부분 / 본인 contracts/policies 에 mounting | 법무 도메인 자료 양 부족 |
| **internal evidence base** | Dim F success metrics 측정 가능 | 사용자 수 = 1 → 통계 의미 약함 |
| **scoping discipline** | 본인이 진짜 사용자 → "mother 만 강화" rule 자연 enforce | 일부 features 가 단일 user 에 특화될 위험 |

→ **Risk**: 자체 사용 만으로는 Dim F (≥6개월, external customer, ≥50 user)
충족 못함 — **production readiness 인증 못함**.

→ **Value**: Dim F path 충족 이전 단계 (intermediate validation; "본인이
실제 매일 쓰는 dogfooding") 로서는 **합리적 + 비용 효율적**.

---

## 2. 시나리오 매트릭스

### 시나리오 A: "Pure dogfooding (Dim F path 무관)"

* Hashevolution operator 가 본인 운영 자료 (계약 / 거래 / 견적 / 매출 / 정책) 를 JAMES 에 ingest
* 매일 사용 + 피드백 → bug fix + UX 개선 + edge case discovery
* **Dim F gate 와는 무관** — production proof 는 external customer 가 따로 충족시켜야

**Pros**:
- v0.5 entry 의 first step 으로 즉시 가능 (LOI 협상 X)
- mother-platform rule 자연 enforce (도메인 코드 추가 = 본인이 사용하는 일반 enterprise 기능)
- external outreach 자료의 "JAMES is used in production" trust signal (조심: customer 가 본인 회사라는 conflict)

**Cons / risks**:
- v1.0 인증으로 활용 불가 (Dim F 미충족)
- 자료 양 적음 (1인 사업자 규모) → corpus 5000 docs 같은 측정 어려움
- external pilot 시간 비용 절감 효과 미미 (Dim F 는 어차피 외부 customer 필요)

**판단**: ✓ **즉시 시작 가능, 항상 valid**. 외부 outreach 와 병행 가능.

### 시나리오 B: "Hashevolution = formal first customer (Dim F path 단축 시도)"

* Hashevolution 을 법인으로 전환 + 별도 법무 / IT / 보안 책임자 가시화
* JAMES 와 Hashevolution 간 formal pilot LOI / DPA / MSA 체결
* 6개월 pilot 운영 + Dim F success metrics 측정 + 외부 발표

**Pros**:
- LOI 협상 시간 우회 (self-deal)
- Pilot operator 와 customer 가 같으므로 iteration 무한
- Dim F evidence 빠른 진입

**Cons / risks**:
- **Conflict of interest 가 명백** → external reviewer / future customers / academic peer review 가 모두 "self-eval trap" 으로 인식
- 1인 사업자 → 50-200 user 시나리오 시뮬레이션 불가 (가짜 데이터 / 가짜 사용자 = 시나리오 invalid)
- Hashevolution 법인화 비용 / 시간 (~1-3개월)
- 외부 customer 가 "Hashevolution self-deal" 을 봤을 때 신뢰도 hit

**판단**: ✗ **Dim F path 로는 권장 안 함**. self-eval trap 룰 위반.

### 시나리오 C: "Intermediate dogfooding + external pilot 병행"

* 시나리오 A 의 dogfooding 즉시 시작 (timing 단축 + iteration 가속)
* 동시에 external outreach (Tier S contact list) 진행
* Dim F 는 external customer 가 따로 달성
* Internal dogfooding 의 결과는 **internal trust signal + bug catch** 로만 활용 (Dim F evidence claim 안 함)

**Pros**:
- 시나리오 A 의 모든 valid value 유지
- Dim F path 자체 risk 회피 (external customer 가 별개로 진행)
- External outreach 시간 동안 internal iteration 으로 product 강화

**Cons / risks**:
- Internal dogfooding 가 외부 outreach 와 timing 경쟁할 수 있음 (operator 시간 분산)
- "Hashevolution 도 본인 자료에 쓴다" 라는 사실은 marketing 으로 활용 가능하나 self-deal 로 보일 수 있는 risk

**판단**: ✓ **권장 path**. Dim F 룰 침해 없이 internal iteration + external 병행.

---

## 3. 시나리오 C 의 구체적 next step

### 3.1 Internal dogfooding (즉시 시작 가능)

| Step | Action | 소요 |
|---|---|---|
| 1 | Hashevolution 운영 자료 inventory (계약, 거래, 정책, 매출 등) | 1-2 day |
| 2 | 본인 workspace 의 JAMES 에 ingest (관리 가능 규모, 100-500 docs) | 1 day |
| 3 | 일일 사용 + 피드백 / bug catch / UX 개선 | 지속 (1+ 개월) |
| 4 | Internal "monthly review" — 어떤 feature 가 실제로 도움 됐나 | 매월 |

### 3.2 External outreach (병행)

| Step | Action | 소요 |
|---|---|---|
| 1 | Tier S contact list 작성 (~30 명, operator 네트워크) | 2-3h |
| 2 | LinkedIn profile + cold outreach 발송 | 수일 |
| 3 | 응답 / 미팅 진행 → technical brief 공유 | 수주 |
| 4 | LOI 진입 → 6개월 pilot 운영 → Dim F evidence | 6-9개월 |

### 3.3 두 path 의 분리 / 정합

- Internal dogfooding 의 **개선 / bug fix** 는 모두 mother-platform 영역 (자연 enforce)
- External pilot 의 **success metrics** 는 Dim F gate 의 정식 evidence
- 둘은 commit 단위에서 명확히 구분 (`feat(internal-dogfood)` vs `feat(v0.5-pilot-customer)`)

---

## 4. 결론

| 평가 | 답 |
|---|---|
| Hashevolution 을 first customer 로 사용 가능한가? | 시나리오 A / C 의 dogfooding 으로는 YES; 시나리오 B 의 Dim F path 로는 NO |
| External outreach timing 단축 효과? | Dim F path 시간 단축 효과는 미미; iteration 속도 향상 효과는 큼 |
| Self-eval trap 룰 위반 위험? | 시나리오 C 에서는 회피 가능 (internal iteration evidence ≠ Dim F evidence 명시 분리) |
| 다음 액션? | **시나리오 C 채택**: internal dogfooding 즉시 시작 + external outreach 병행 |

### 권장 next step (operator action)

1. Hashevolution 본인 운영 자료 inventory (1-2일)
2. 본인 workspace JAMES instance 에 ingest (1일)
3. 일일 사용 → 매주 internal feedback note
4. 동시에 Tier S contact list 작성 + outreach 시작

이 doc 는 **operator 결재용** 이며, customer-facing material 에 포함하지
않음. External pilot 진입 시 Hashevolution dogfooding 은 trust signal 로
언급할 수 있으나 Dim F evidence 로 claim 하지 않음.

---

## 5. 관련

- `docs/strategy/v0.5-domain-candidate-evaluation-2026-06-11.md` —
  domain ranking (legal contract review = primary)
- `docs/strategy/v0.5-pilot-scope-spec-2026-06-11.md` — generic Dim F
  spec
- `docs/strategy/v0.5-pre-loi-materials/03-pilot-proposal-template.md`
  — external customer 용 LOI 기본 템플릿
- `docs/PLATFORM_READINESS.md` §3 — Dim F gate 정의
- `memory/feedback_self_evaluation_trap.md` — self-eval trap rule
  (시나리오 B 회피 이유)
- `memory/feedback_build_dont_broadcast.md` — build-don't-broadcast
  원칙 (internal vs external 정합)
