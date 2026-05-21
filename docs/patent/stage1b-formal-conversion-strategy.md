# STAGE 1B 정식 전환 전략 — 2027년 4~5월 시점 의사결정 가이드

> **작성 시점**: 2026-05-21 (STAGE 1B 임시 출원 직후)
> **활용 시점**: 2027-04 ~ 2027-05 (정식 전환 마감 임박, D+330일~D+360일)
> **목적**: 임시명세서 → 정식명세서 변환 시 청구항 broadening + prior art 재검색 + 변리사 자문 가이드
>
> **현재 출원 상태**:
> - 출원번호: 10-2026-XXXXXXX (사용자 비공개 보관)
> - 출원일: 2026-05-21
> - Grace period 만료: 2027-05-08 (디자인 메모) ~ 2027-05-20 (Hotfix 기준)
> - 정식 전환 마감: 출원일 + 12개월 = **2027-05-21** (필수)
> - 심사청구 마감: 출원일 + 3년 = 2029-05-21 (별도)

---

## 1. 정식 전환 결정 트리

### 1.1 진행 (정식 전환) — 조건

다음 중 1개 이상 해당 시 정식 전환 진행:

- ✅ **사업화 진척 명확** — B2B SaaS / API / 라이센싱 계획 구체화
- ✅ **투자 라운드 진행** — VC due-diligence 에서 IP 자산 요구
- ✅ **M&A / 전략적 파트너십 협상** — IP portfolio 가시화 필요
- ✅ **경쟁사 유사 출원 발견** — 방어적 IP 강화 필수
- ✅ **사용자 / 매출 수치 증가** — 시장 검증 신호
- ✅ **연구·학술 가치 입증** — 학회 발표 / 논문 출판

### 1.2 보류 (자동 취하 허용) — 조건

다음 모두 해당 시 정식 전환 포기 (출원 자동 취하):

- ❌ 사업화 가시성 없음
- ❌ 투자 / 매출 진척 없음
- ❌ 경쟁 위협 없음
- ❌ 변리사 자문료 / 정식 출원료 (~200만 원) 부담 큼
- ❌ 우선일 효력 만으로 충분 (defensive publication 효과)

### 1.3 권고

|  결정 | 누적 비용 | 효과 |
|---|---|---|
| 정식 전환 진행 | ~250만 원 (변리사 자문 30~50 + 정식 출원 200) | 최대 20년 보호 시도 |
| 자동 취하 | ₩13,800 (이미 결제) | MIT + GitHub 공개로 defensive 유지 |

---

## 2. 정식 전환 시 청구항 보강 — Gap 분석

### 2.1 임시 출원 청구항 10개 현 보호 범위

| # | 핵심 | 보호 범위 | 회피 난이도 | 보강 필요? |
|---|---|---|---|---|
| 1 | `c = 1 − Π(1 − w_i)` 폐쇄식 | Mixed | ⚠️ 다른 closed-form 회피 가능 | **Yes** (공식 family 로 broader) |
| 2 | 5 단계 cascade 절차 + manual 보존 | Broad | 🟢 회피 어려움 | 미미 |
| 3 | 시스템 (5 모듈) | Broad | 🟡 모듈 변경 가능 | **Yes** (데이터 흐름 명시) |
| 4 | role="manual" + doc_id=null 면역 | ⭐⭐⭐ Strong Concept | 🟢 회피 어려움 | **Yes** (필드명 lock 풀기) |
| 5 | (s,p,o) triple-level diff | ⭐⭐⭐ Strong Concept | 🟡 quadruple 회피 가능 | **Yes** (N-tuple 로 broader) |
| 6 | 단조성 4 성질 | ⭐ Broadest | 🟢 회피 어려움 | 미미 |
| 7 | Cross-doc aggregation + 멱등성 + 대칭 | Mixed | 🟡 매칭 키 변경 가능 | **Yes** (매칭 함수 추상화) |
| 8 | 0.91, 0.973 specific 수치 | ❌ Narrow | 🔴 즉시 회피 가능 | (백업으로 유지) |
| 9 | Audit log 4 항목 | Mixed | 🟡 형식 변경 가능 | (선택) |
| 10 | 임계값 0.6 게이팅 | Narrow | 🟡 변경 가능 | (백업으로 유지) |

### 2.2 정식 전환 시 보강 권고 (5가지 핵심)

#### Gap 1. **공식 family broadening (claim 1)**

**현재**:
```
... confidence = 1 − Π(1 − w_i) ...
```

**문제**: 다른 단조 closed-form (예: `1−exp(−Σw)`, `tanh(Σw)`, `1 − (1-mean(w))^n`) 으로 회피 가능.

**보강 (정식 전환 시)**:
```
청구항 1 (정식 전환 안):
신뢰도를 다음 성질을 모두 만족하는 임의 함수 f 에 의해 도출:
(i) 단조 비감소 (출처 추가 시),
(ii) closed-form (해석적 공식, 학습 모델 미사용),
(iii) 단일 출처에서 identity (f({w}) = w),
(iv) 출력 범위 [0, 1) (asymptotic);
일 구현 예로 f(w_1,...,w_n) = 1 − Π_{i=1..n}(1 − w_i) [noisy-OR];
다른 구현 예로 f(w_1,...,w_n) = 1 − exp(−Σ w_i) [log-sum-exp];
또는 등가의 단조 closed-form.
```

→ Pearl 1988 의 noisy-OR 단독 청구는 anticipation 위험, 위 성질 함수 family 청구로 broader.

#### Gap 2. **Manual immunity 필드명 lock 풀기 (claim 4)**

**현재**:
```
... role 필드와 doc_id 필드를 가지며, role 값이 "manual" 이고
    doc_id 값이 null 인 항목 ...
```

**문제**: 다른 필드명 (예: `source_type="human"`, `curated_by="user"`) 으로 회피 가능.

**보강**:
```
청구항 4 (정식 전환 안):
각 source 항목이 다음을 만족하는 것을 특징으로 하는 방법:
(i) 자동 추출 source 와 수동 편집 source 를 구분 가능한 필드를 보유;
(ii) 수동 편집 source 는 doc_id 또는 그에 대응하는 식별자가 null 또는 부재;
(iii) cascade 동작에서 (i)(ii) 의 조건을 만족하는 source 는
     자동 추출 source 와 동일 doc_id 매칭 조건에서 제외되어 보존;
일 구현 예로 role 필드의 "manual" 값이 (i)(ii) 의 식별에 사용됨.
```

→ 필드명 무관, 기능 자체로 broad.

#### Gap 3. **Triple → N-tuple broadening (claim 5)**

**현재**:
```
... (subject, predicate, object) 트리플 집합 ...
```

**보강**:
```
청구항 5 (정식 전환 안):
출처 문서 수정 시:
(a) 직전 추출 결과를 N-tuple 관계 집합 (N >= 3) 으로 sidecar 파일에 보존
    — 일 구현 예: (subject, predicate, object) triple;
(b) ~ (d) 차집합 / 교집합 / 합집합 처리 ...
```

→ Triple-only lock 해제, quadruple/RDF-star 등도 커버.

#### Gap 4. **Cross-doc aggregation 매칭 키 추상화 (claim 7)**

**현재**:
```
... (target_name, normalized_type) 매칭 ...
```

**보강**:
```
청구항 7 (정식 전환 안):
... 동일 관계 식별을 위한 정규화된 매칭 키 (canonical matching key);
일 구현 예: (target_name, normalized_relation_type) 의 튜플;
다른 구현 예: (target_entity_id, normalized_predicate_uri) 의 튜플;
또는 동일 관계 의미를 식별하는 등가의 키 ...
```

→ entity_id vs target_name, predicate vs predicate_uri 등 매칭 키 변형 회피 차단.

#### Gap 5. **시스템 데이터 흐름 명시 (claim 3)**

**현재**:
```
(1) ~ (5) 모듈을 포함하는 시스템 ...
```

**보강**:
```
청구항 3 (정식 전환 안):
출처 추적 기반 지식 그래프 시스템으로서, 다음 모듈을 포함하며 다음
데이터 흐름으로 동작하는 것을 특징으로 하는 시스템:
(1) 관계 저장소 — sources 배열을 보유;
(2) 신뢰도 계산기 — (1) 의 sources 를 입력받아 claim 1 의 도출 공식에 의해
    confidence 를 산출;
(3) Cascade 엔진 — (1) 의 sources 에서 doc_id 삭제 트리거 발생 시
    role 필드 조건에 따라 항목 제거하고 (2) 를 호출하여 재계산;
(4) Cross-doc aggregation 모듈 — ingestion 시 (1) 에 새 source append,
    (2) 호출하여 재계산;
(5) Audit 로거 — (3), (4) 의 cascade 이벤트마다 before/after sources 와
    metrics 기록.
```

→ 일부 모듈 교체 시에도 데이터 흐름 동일 시 침해.

### 2.3 신규 추가 청구항 (정식 전환 시 새로 만들 청구항 11~15)

#### 청구항 11 (방법 — Defense-in-depth manual 면역)
- D1 (doc_id 매칭) → No → Keep (1차 면역)
- D1 → Yes → D2 (role == manual) → Yes → Keep (2차 면역)
- 이 conjunctive 면역 메커니즘이 single defense 보다 강함을 주장

#### 청구항 12 (방법 — 멱등성 contract)
- 동일 doc_id 의 중복 source 추가는 거부
- 재업로드 / Phase D modify cascade fallback 의 race condition 방어

#### 청구항 13 (방법 — 정/역 대칭 보장)
- forward (s, p, o) + inverse (o, inverse_p, s) 양방향 source append
- normalize_relation 함수에 의한 inverse 도출 명시

#### 청구항 14 (시스템 — invariant 테스트 기반 회귀 차단)
- 12 invariant 테스트가 매 push 시 자동 검증
- CI 차단으로 cascade 의 monotonicity·idempotency 보장

#### 청구항 15 (시스템 — sidecar JSON 인프라)
- ingestion path 에 부착된 sidecar JSON 자동 저장
- Phase D modify cascade 의 diff 시작점

---

## 3. Prior Art 재검색 권고 (정식 전환 직전)

정식 전환 시점 (2027-04~05) 에 다시 검색:

### 3.1 검색 사이트

| 사이트 | 목적 |
|---|---|
| KIPRIS (kipris.or.kr) | 한국 신규 출원 |
| Google Patents | 전 세계 신규 출원 |
| arXiv | 학술 신규 발표 (2026-05 ~ 2027-04 기간) |
| USPTO | 미국 신규 출원 |
| EPO Espacenet | 유럽 패밀리 추적 |

### 3.2 키워드 (2027년 검색 시)

#### 한국 (KIPRIS)
1. 지식그래프 + 출처 + cascade
2. 노이지-OR + 신뢰도
3. 수동편집 + 면역 + cascade

#### 영문 (Google Patents)
1. `"knowledge graph" "noisy-OR" "cascade"`
2. `"manual edit" "immune" "cascade" "knowledge"`
3. `"triple-level diff" "modify cascade"`
4. `"cross-doc aggregation" "knowledge graph"`

#### 학술 (arXiv / Scholar)
1. `"provenance cascade" "knowledge graph" 2026 2027`
2. `"monotone cascade" "knowledge graph"`
3. IBM, Google, Microsoft, OpenAI, Anthropic 의 신규 발표

### 3.3 발견 시 대응

- 🟢 무관 → 정식 전환 그대로 진행
- 🟡 일부 겹침 → narrow claim 강화
- 🟠 상당 겹침 → 청구항 reframe 필수
- 🔴 거의 동일 → 정식 전환 포기 또는 dispute 준비

---

## 4. 변리사 자문 권장 항목

정식 전환 시 변리사에게 검토 요청 (예상 비용 30~50만 원):

### 4.1 청구항 narrowing / broadening

- 위 §2.2 의 5가지 Gap 모두 검토
- 변리사가 한국 KIPO 심사 트렌드 반영해 최적 표현 선택

### 4.2 종속항 추가

- 위 §2.3 의 신규 청구항 11~15 검토
- 종속항이 거절 시 살아남을 fall-back 제공

### 4.3 우선권 주장 (외국 출원)

- 미국 PCT 진출 검토 (출원일 + 12개월 내 PCT 출원)
- 비용: 번역료 100~200만 원 + PCT 출원료
- 시장 진출 계획 (미국 SaaS 등) 시 권장

### 4.4 거절 대응 전략 사전 수립

- 가능한 거절 사유 예상 (특허법 29조 1항 / 2항 / 42조 3항)
- 의견서 / 보정서 사전 템플릿

---

## 5. 비용 견적 (정식 전환 시)

| 항목 | 비용 |
|---|---|
| 변리사 자문 (1차) | 30~50만 원 |
| 정식 출원료 (개인 70% 감면) | 약 60만 원 (정식 명세서, 청구항 추가 시 가산) |
| 심사청구료 (청구항 10개) | ~17.5만 원 (지금 결제 시 옵션 A 였던 금액) |
| **소계 (한국 정식 전환만)** | **약 105~125만 원** |
| (선택) PCT 국제 출원 | + 100~200만 원 (번역료 포함) |
| (선택) 변리사 자문 (지속) | + 30~50만 원/년 (의견서 응답 등) |

→ 사업화 시 ROI 계산 필요. 우선일 효력 만으로 충분하면 정식 전환 X (=자동 취하).

---

## 6. 핵심 일정 (D+ 기준)

| D+ | 일자 | 마감 |
|---|---|---|
| D+0 | 2026-05-21 | 임시 출원 완료 ✅ |
| D+330 | 2027-04-16 | **정식 전환 결정 권장 시점** (변리사 자문 시작) |
| D+360 | 2027-05-15 | 정식 전환 최종 결정 |
| **D+365** | **2027-05-21** | **정식 전환 마감** ⚠️ (놓치면 자동 취하) |
| D+545 | 2027-11-17 | 자동 공개 (특허법 64조, 출원일 + 18개월) |
| D+1095 | 2029-05-21 | 심사청구 마감 ⚠️ |

---

## 7. 자가 점검 체크리스트 (2027년 4월 시점)

정식 전환 결정 전 다음 점검:

### 7.1 사업화 / 가치 검증
- [ ] 사용자 / 매출 수치
- [ ] 투자 라운드 / due-diligence 진행도
- [ ] 경쟁사 출원 모니터링 결과 (KIPRIS 재검색)
- [ ] 학회 / 논문 / 미디어 노출 결과 (Show HN 등)

### 7.2 기술 안정성
- [ ] STAGE 1B Phase A~E 의 production 사용 수치
- [ ] 12 invariant tests 모두 green 유지
- [ ] multi-source 자연 누적 데이터 (Tier 3 검증)
- [ ] 0.6 threshold 재튜닝 결과

### 7.3 정식 전환 준비
- [ ] Prior art 재검색 (KIPRIS + Google Patents + arXiv)
- [ ] 변리사 1차 자문 (30~50만 원)
- [ ] 청구항 보강 안 (위 §2.2 + §2.3)
- [ ] 비용 예산 확보 (105~125만 원)

### 7.4 PCT / 외국 출원 검토 (선택)
- [ ] 미국 시장 진출 계획
- [ ] 번역료 / 외국 변리사 비용 예산
- [ ] 우선권 주장 마감 (출원일 + 12개월 = 2027-05-21 동일)

---

## 8. 결정 시나리오 매트릭스

| 사업화 진척 | 경쟁 위협 | 자금 여유 | 권장 결정 |
|---|---|---|---|
| 명확 | 있음 | 충분 | **정식 전환 + PCT** |
| 명확 | 없음 | 충분 | 정식 전환 (한국 only) |
| 불확실 | 있음 | 충분 | 정식 전환 (한국 only) — 방어 |
| 불확실 | 없음 | 부족 | **자동 취하** (defensive 충분) |
| 명확 | 있음 | 부족 | 정식 전환 + 변리사 자문만 (PCT 보류) |
| 불확실 | 있음 | 부족 | 정식 전환 (한국 only) — 최소 방어 |

---

## 9. 신규 세션에서 본 문서 활용

미래 세션에서 정식 전환 작업 재개 시:

```
James-RAG-Evol STAGE 1B 정식 전환 작업 재개합니다.

다음 파일 참조:
- docs/patent/stage1b-formal-conversion-strategy.md (본 문서)
- docs/patent/HANDOVER.md
- docs/patent/prior-art-1B.md
- docs/patent/stage1b-invariant-claims-mapping.md

현재 일자 D+XXX (2027-XX-XX), 정식 전환 마감 2027-05-21 까지 X일 남음.
[구체 요청 — 예: "변리사 자문 전 청구항 보강 안 작성"]

작업 브랜치: claude/security-audit-LRxjo
```

---

## 10. 참고 — 청구항 1~15 통합 목록 (정식 전환 시)

기존 1~10 (임시 출원분) + 신규 11~15:

| # | 핵심 |
|---|---|
| 1 (수정) | 단조 closed-form 임의 함수 + 일 구현 noisy-OR |
| 2 (수정) | 5단계 cascade 절차 + manual 보존 |
| 3 (수정) | 시스템 + 데이터 흐름 명시 |
| 4 (수정) | Manual 면역 — 필드명 lock 해제 |
| 5 (수정) | N-tuple diff cascade |
| 6 | 단조성 4 성질 (그대로) |
| 7 (수정) | Cross-doc aggregation + 매칭 키 추상화 |
| 8 | 0.91, 0.973 specific 수치 (백업) |
| 9 | Audit log details (그대로) |
| 10 | 임계값 게이팅 (그대로) |
| **11** (신규) | Defense-in-depth manual 면역 (D1 + D2 conjunctive) |
| **12** (신규) | 멱등성 contract (재업로드 안전) |
| **13** (신규) | 정/역 대칭 보장 |
| **14** (신규) | Invariant 테스트 기반 회귀 차단 시스템 |
| **15** (신규) | Sidecar JSON 인프라 |

---

**End of STAGE 1B Formal Conversion Strategy.**

본 문서는 2027년 4~5월 정식 전환 시점에 활용. 그 사이의 prior art 변화·시장 변화·사업화 진척을 반영하여 청구항 보강 결정.
