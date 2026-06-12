# JAMES v0.5 Pilot Risk + Mitigation Matrix (v0.4.4 / 2026-06-12)

> Target audience: customer 측 security officer, compliance officer,
> CISO, 법무팀장.
>
> **Honest posture**: Pilot 은 evidence-gathering exercise — risks 도
> evidence-evaluable. 본 doc 은 10 row risk matrix + customer-facing
> mitigation + post-mitigation residual risk 명시. Risks 의 일부는
> customer 측 controllable, 일부는 mutual.
>
> **v0.4.4 update (2026-06-12)**: Trust signal 추가 — 본 프로젝트는
> measurement-side artefact 의 self-catch 사례 1건 (2026-06-12, LRB
> S3.1 contract-vocabulary 수정 PR #825) 공개 commit. 12번째
> wrong-fix-averted 이자 **첫 self-catch** (이전 11건은 사용자 catch).
> 이는 customer 측 risk 평가에 가장 강한 신뢰 신호 — 외부 reviewer
> 없이도 over-claim 을 catch + retract + 공개 재산정 했다는 commit
> evidence. Reference: `papers/lrb-preprint/main.pdf` §5 + DOI
> `10.5281/zenodo.20652679`.

---

## 1. Risk matrix (10 row)

각 risk:
* **Likelihood** (L): low / medium / high
* **Impact** (I): low / medium / high / catastrophic
* **Mitigation**: 운영자 + customer 공동 actions
* **Residual** (post-mitigation): 잔존 risk level

| # | Risk | L | I | Mitigation | Residual |
|---|---|---|---|---|---|
| **R.1** | Customer 데이터 외부 유출 | low | catastrophic | Workspace 격리 (Option A 권장; customer infra 내 배포). audit_bridge 격리 저장. DPA 사전 합의. 정기 보안 audit (분기). PolicyEngine 단일 boundary 통과 강제. | low |
| **R.2** | Customer 가 core/ 코드 수정 요청 (도메인 feature 추가) | high | medium-high | CLAUDE.md rule #1 enforced — packs/<domain>/ 로 분리. 정중 거부 가능 정당화. mother-platform 안정성 우선. | low |
| **R.3** | Pilot 기간 중 core/ 머지로 production regression | medium | high | F.2 CI 자동 측정 (RAB monthly + per-PR baseline). regression 발생 시 즉시 revert. operator monthly checkpoint 에 customer 측 PR review 참여 권유. | low-medium |
| **R.4** | 6 개월 내 pilot 중단 (customer 측 사유 — 인사이동, 예산 컷, 우선순위 변경 등) | medium | catastrophic | Pilot 시작 시 6 개월 commit clause (proposal §10). monthly checkpoint with sponsor + backup sponsor. NPS / 사용량 leading indicator. | medium |
| **R.5** | F.4 (RAB AC ≥ 0.99) 측정 baseline 측정 불가 — corpus 불완전 / 동의 부족 | medium | high | Kickoff 시 corpus 사이즈 / 동의 / 분류 명시. minimum corpus = 1000 docs (LRB scoring baseline 가능). F.4 측정 불가 시 conditional pass criteria 추가 합의. | low |
| **R.6** | RAB / LRB metric 이 도메인 reality 와 mismatch (예: customer 측 use case 가 measurement 와 다른 axis) | medium | medium | Kickoff 시 도메인-specific 보완 metric (도메인 expert 가 정의). RAB/LRB 외 customer-defined metric 추가. metric 합의 lock 후 변경 금지. | low-medium |
| **R.7** | Customer staff turnover → pilot momentum 상실 | low | medium | Pilot sponsor 3-tier (임원 + 부서장 + 운영 PIC) — 1 명 turnover 도 backup. monthly checkpoint 누락 시 즉시 escalation. | low |
| **R.8** | 가격 협상 결렬 (post-pilot renewal) | medium | high | Pilot 가격 = cost-recovery 진입 friction 최소화 (proposal §8). 정식 v1.0 후 가격 협상. pilot evidence 가 renewal price negotiation 의 backup. | medium |
| **R.9** | LRB / RAB 의 외부 발표 가 customer 데이터 노출 | low | high | Customer 데이터 = pilot evidence 의 anonymized aggregate 만 외부 발표 가능 (proposal §9). 사전 review + 합의. customer can veto specific findings. | low |
| **R.10** | Pilot 결과 negative → 모체 platform credibility 손상 | low | medium | Honest framing rule (cycle γ 패턴) — negative 결과도 publish "what we learned". post-mortem 의 evidence-backed 학습 자체가 mother-platform 강화. 모든 cycle 의 honest negative findings 가 evidence (RAB Phase A finding / Track C MuSiQue identical / etc.) | low |

## 2. Risk 별 detailed mitigation

### R.1 (외부 유출) — catastrophic impact

**Mitigation primary**:
* Option A deployment (customer-hosted) — **권장**
* JAMES instance 가 customer VPC / on-prem 안 만 위치
* outbound network 기본 차단 (오로지 software update 만 외부 통신)
* claude cloud LLM 사용 시 abstraction layer mask + PolicyEngine
  pre-call audit (trust contract §5.7.12 / §5.7.13)

**Mitigation secondary**:
* DPA 사전 합의 (5-year mutual NDA)
* 분기 1회 보안 audit (customer 측 CISO 또는 외부 audit firm)
* Source code review (operator can provide repo access for customer
  security team)
* Audit_bridge 의 access control (RBAC, only customer admins read full log)

**Residual**: low (Option A 채택 + 위 mitigation 모두 적용 시).

### R.2 (도메인 feature 요청) — high impact (mother-platform pollution)

**Why high impact**: CLAUDE.md rule #1 (no domain features until v1.0)
mother-platform 안정성 의 single source. customer 가 "법무 도메인 specific
contract diff 기능" 요청 시 core/ 수정 → 다른 customer 미래 영향.

**Mitigation**:
* Pilot kickoff 부터 명시: domain features = `packs/legal/` plugin
  pattern, core/ 변경 0
* packs/ plugin 개발 가능 시점 = pilot kickoff 후 첫 1 개월 정상 운영
  baseline 확정 후
* 거부 정당화 base = mother-platform discipline 의 measurement-evidenced
  benefit (다른 customer 의 production-proof 가 누적될수록 본 customer
  의 production-stability 도 향상)

**Residual**: low. customer 측 IT team 이 mother-platform 가치 이해
하면 resolved.

### R.3 (Core regression) — high impact

**Why high impact**: pilot 기간 중 다른 cycle / PR 의 영향 으로 customer
의 production 환경 의 RAB / LRB metric 이 떨어질 risk.

**Mitigation**:
* F.2 CI 자동 측정 — 모든 core/ PR 머지 시 RAB Phase 3 S2 자동 재실행
* Δ ≤ -0.01 (any axis) PR 0 개 commitment
* Monthly checkpoint 에 customer 측 PR review 참여 (선택)
* Customer 측 production 의 baseline = pilot week 0 의 RAB measurement;
  monthly delta 추적
* Regression 발생 시: 7 일 안에 revert OR fix-PR commit

**Residual**: low-medium (CI + revert SLA backed).

### R.4 (Pilot 중단) — catastrophic

**Why catastrophic**: customer 측 사유로 6 개월 안 종료 시 → operator
입장 에서 investment loss + Dim F evidence 미확보 → 다음 pilot 진입
어려움.

**Mitigation**:
* Pilot start 시 6 개월 commit clause + monthly checkpoint
* Leading indicators monthly review: NPS / weekly active users / RAB AC
* NPS 또는 active user drop 시 즉시 sponsor escalation
* Backup sponsor (default at proposal §6.1)

**Residual**: medium. Customer 측 통제 불가능 한 사유 (M&A / 인사 / 예산
컷) 일부 잔존.

### R.5-R.10

위 5 가지 외 의 risks 도 mitigation 적용 시 residual low/medium.

## 3. Customer 측 mitigation responsibility

| # | Customer action 필요 |
|---|---|
| R.1 | DPA / NDA 사전 서명. 보안 검토 통과. Workspace 격리 인프라 제공 (Option A). |
| R.2 | Pilot kickoff 시 packs/ pattern 이해 + 합의. |
| R.3 | Monthly PR review 참여 (선택). |
| R.4 | 6 개월 commit. Sponsor 3-tier 지정. NPS survey 참여. |
| R.5 | Initial corpus (≥1000 docs) provision + 동의. |
| R.6 | 도메인 expert 의 monthly 30-query gold labelling. |
| R.7 | Backup sponsor 지정. |
| R.8 | Renewal negotiation 양측 합의. |
| R.9 | Anonymisation review 참여. |
| R.10 | Honest finding sharing 합의 (positive + negative 모두). |

## 4. Operator 측 mitigation responsibility

| # | Operator action |
|---|---|
| R.1 | PolicyEngine + abstraction layer enforcement. 정기 보안 audit. |
| R.2 | Mother-platform discipline enforcement. packs/ plugin 개발 지원. |
| R.3 | CI 자동화 + revert SLA. Monthly RAB measurement. |
| R.4 | Monthly checkpoint 진행. Leading indicator review. |
| R.5 | Minimum corpus 정의. F.4 측정 protocol 합의. |
| R.6 | RAB / LRB 측정 protocol 합의 + 도메인-specific metric 추가. |
| R.7 | Pilot sponsor 3-tier 추적. |
| R.8 | Pricing transparency. |
| R.9 | Anonymisation 처리 + customer veto 권리 보장. |
| R.10 | Honest framing rule enforcement. |

## 5. Risk register lifecycle

* **Pilot kickoff**: 본 risk register 를 customer 측 risk officer 와
  공동 review + 합의. 잔존 risk 가 customer 측 risk appetite 안 인지
  확인.
* **Monthly checkpoint**: risk register 의 each row 의 status update.
  새로운 risk 발견 시 register 에 추가.
* **Pilot 종료**: final risk register 의 post-mortem. 학습된 risks 가
  v1.0 platform discipline 에 fed back.

## 6. Catastrophic risk override (R.1, R.4)

다음 2 risks 는 catastrophic impact — pilot 진입 전 양측 의 명시적
합의 필요:

* **R.1**: Workspace 격리 spec + DPA + 보안 audit 모두 통과 후 만 진입.
  Option A 가 표준 (customer-hosted).
* **R.4**: 6 개월 commit clause + 3-tier sponsor + termination clause
  (proposal §10) 모두 합의 후 만 진입.

위 2 조건 unmet 시 pilot 시작 X.

## 7. 관련

* Pilot proposal template: `03-pilot-proposal-template.md`
* Technical brief (security review checklist): `02-technical-brief.md` §5
* v0.5 pilot scope spec: `docs/strategy/v0.5-pilot-scope-spec-2026-06-11.md`
  §5 risk + mitigation matrix (generic)
* 6-dimension readiness framework: `docs/PLATFORM_READINESS.md`
* Abstraction trust contract: `docs/ARCHITECTURE.md` §5.7.12 / §5.7.13

---

*Risk register 는 living document. Pilot 진입 전 customer 측 risk
officer 와 공동 review + 합의. 잔존 risk 모두 customer 측 risk
appetite 안 인지 확인 후 만 진입.*
