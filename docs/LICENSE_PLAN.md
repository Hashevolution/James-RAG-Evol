# LICENSE_PLAN — JAMES 라이선스 장기 계획 및 트리거 모니터링

> **문서 성격**: 영구 보존 의사결정 문서. 본 문서는 `docs/handovers/`
> 의 세션 핸드오버와 달리 **머지 후에도 유지**되며, 라이선스 의사결정
> 의 역사·근거·트리거 조건을 후임자에게 전달하기 위한 단일 진실
> 소스(SSoT) 다.
>
> **최종 갱신**: 2026-05-13
> **현재 라이선스**: MIT
> **다음 검토 트리거**: §3 의 T1~T5 중 2개 이상 충족 시

---

## 1. 현재 라이선스 상태

| 항목 | 값 |
|---|---|
| 루트 `LICENSE` | MIT |
| 저작권 보유자 | Hashevolution |
| 연도 | 2026 |
| GitHub Repo Settings → License | MIT |
| `CONTRIBUTING.md` 라이선스 동의 | MIT + CLA §4-bis relicensing grant 안내 |
| Plugin manifest `license:` 허용값 | `MIT` (현재) / `Apache-2.0` / `AGPL-3.0` / `proprietary` (인프라만 사전 준비) |

---

## 2. 라이선스 강화의 황금률

> **"보호할 생태계가 생긴 다음에 잠그는 것."**
> 거꾸로 하면 둘 다 잃는다.

### 단계별 라이선스 적합성

| 단계 | MIT | AGPL + Commercial dual | BUSL |
|---|---|---|---|
| 스타 0~수십 (= 현재) | ✅ 진입장벽 0 | ❌ 회사 사용자 99% 이탈 | ❌ 같음 |
| 스타 1k+ / 도입 사례 다수 | ⚠️ 클로닝 위험 노출 | ✅ 합리적 보호 | ✅ 합리적 보호 |
| 상용 문의 실제 발생 | ⚠️ 수익화 어려움 | ✅ 즉시 청구 가능 | ✅ 같음 |
| 매출 후크 필요성 확정 | ❌ 후크 없음 | ✅ 컴플라이언스 + 기능 후크 | ✅ 시한부 상업 제한 |

### 경험적 증거 — 성공한 강화 사례는 모두 permissive 출발

| 프로젝트 | MIT/Apache 시작 → 강화 전환 시점 |
|---|---|
| Elastic | 9년 / 스타 50k+ → SSPL → (최근 AGPL 추가) |
| HashiCorp Terraform | 9년 / 스타 40k+ → BUSL |
| Sentry | 10년 / 스타 30k+ → BUSL → FSL |
| MongoDB | 9년 / ARR $200M+ → SSPL |
| Redis | 15년 / 시장 지배 후 → dual |

**공통점**: 클로닝 손해 실발생 또는 상용 경쟁자 등장 직후 전환.
**반례**: 처음부터 BUSL/AGPL 로 출발한 프로젝트는 대부분 채택률 0
으로 묻힘.

---

## 3. 라이선스 재논의 트리거 (T1~T5)

**규칙**: 다음 5개 트리거 중 **2개 이상 동시 충족 시** 라이선스
재논의를 개시한다. 1개만 충족하면 추가 모니터링 지속.

| ID | 트리거 | 임계값 |
|---|---|---|
| **T1** | 채택 신호 | GitHub stars ≥ 1,000 OR 활성 외부 deployer ≥ 10곳 |
| **T2** | 상용 문의 발생 | "commercial license 가능한가?" 문의 분기당 3건 이상 |
| **T3** | 클로닝 위협 실제화 | 경쟁 SaaS 가 JAMES core 를 fork 호스팅 사례 1건 이상 |
| **T4** | 매출 후크 필요성 확정 | Hashevolution 의 12개월 내 commercial 매출 계획 이사회/임원 의사결정 완료 |
| **T5** | 첫 enterprise 도입 시도 | SOC2/SSO 요구 기업이 PoC 단계 진입 |

### 트리거 측정 방법

| 트리거 | 측정 방식 | 데이터 출처 |
|---|---|---|
| T1 stars | `gh api repos/hashevolution/james-rag-evol --jq .stargazers_count` | GitHub API |
| T1 deployer | 자발 신고 + `/feedback` endpoint 데이터 | 서버 audit log |
| T2 상용 문의 | `licensing@hashevolution` 메일함 / GitHub Issues 라벨 `commercial-inquiry` | 메일 + 이슈 |
| T3 클로닝 | Google Alerts "JAMES RAG", GitHub 검색 fork 모니터링 | 외부 검색 |
| T4 매출 계획 | 내부 의사결정 기록 | 이사회 / 임원 노트 |
| T5 enterprise PoC | `priority:enterprise` 라벨 이슈 + 직접 컨택 | GitHub + 이메일 |

---

## 4. 트리거 충족 시 검토 절차

### Step 1. 검토 회의 소집
- 트리거 2종 이상 충족 확인 (캡처 첨부)
- Hashevolution 의사결정자 + 변리사 자문 참여

### Step 2. 옵션 비교 — 시점·컨텍스트에 따라 재선택

| 옵션 | 적합 상황 |
|---|---|
| **AGPL-3.0 + Commercial dual** | T2/T3 강함, 컴플라이언스 후크 효과적 시장 (북미·EU 다국적기업 비중 높음) |
| **Apache-2.0 + Trademark Policy** | T1 강함이나 T4 약함 (수익 후크 미확정), 브랜드 통제로 충분 |
| **BUSL-1.1** | T3 매우 강함 (대형 SaaS 경쟁자 등장), Change Date 명시 가능 |
| **Open Core (proprietary enterprise pack)** | T5 강함, 기능 차별로 수익화 가능 |
| **Hybrid (AGPL core + proprietary packs)** | T2 + T5 동시, Grafana 모델 |

### Step 3. 사전 준비 자산 검증

전환 실행 전 다음이 모두 갖춰져 있는지 확인:

- [ ] CLA §4-bis Relicensing Grant 가 모든 기여자에게 적용되었는가
      (CLA Assistant 통계 확인)
- [ ] Plugin manifest `license:` 필드가 모든 pack 에 명시되어 있는가
- [ ] Open Core 로 가는 경우, enterprise 후보 기능이 plugin 으로
      분리 가능한 상태인가 (core 와 결합되어 있으면 분리 비용 큼)
- [ ] 상표 등록 진행/완료 상태 확인
- [ ] 특허 청구범위가 새 라이선스와 정합하는가

### Step 4. 전환 실행 — 표준 절차

1. `docs/ARCHITECTURE.md` 에 라이선스 변경 PR (label: `architecture`)
2. `LICENSE` 파일 교체 (필요 시 `LICENSE-MIT` 백업 + `LICENSE-COMMERCIAL.md`
   신설)
3. `NOTICE` 갱신 (저작권 보유자 + 듀얼 안내)
4. `README.md` / `README.ko.md` / `README.beginner.ko.md` 라이선스
   섹션 동시 갱신 (놓치기 쉬움)
5. `CONTRIBUTING.md` 라이선스 동의 문구 교체
6. CLA 본문 갱신 (새 라이선스로 relicensing grant 행사 시 알림)
7. GitHub Repo Settings → License 메타데이터 갱신
8. CHANGELOG 에 명시 + 블로그/홍보로 사전 공지 (최소 30일 전)

### Step 5. 사후 모니터링

전환 후 90일간 다음 지표 추적:
- GitHub stars 변화율
- Issue / PR 유입률 변화
- 신규 기여자 수
- 상용 문의 전환률 (T2 → 실제 commercial 구매)

90일 후 데이터로 전환 효과 평가 PR (`docs/decisions/`).

---

## 5. 사전 준비된 인프라 (현 단계 완료/진행 중)

미래 전환을 trivial 하게 만들기 위해 라이선스는 안 바꾸되 다음은
지금 갖춘다 (또는 갖추는 중):

### 5.1 CLA §4-bis Relicensing Grant
- **위치**: `docs/legal/CLA.md` §4-bis
- **본문**: "You hereby grant to Hashevolution the right, but not the
  obligation, to relicense Your Contributions, in whole or in part,
  under any other license terms of its choosing..."
- **효과**: MongoDB / Grafana 가 라이선스 전환 가능했던 결정적 절.
  이 절이 빠지면 모든 기여자 개별 동의 재수집 필요 → 사실상 전환
  불가능.
- **상태**: `session-2026-05-09-license-infrastructure.md` Track B-2
  에서 정의, CLA Assistant 활성화 시점에 발효

### 5.2 Plugin Manifest `license:` 필드
- **위치**: `pack.yaml` 스키마 — `core/plugins/manifest.py`
- **허용값**: `MIT` | `Apache-2.0` | `AGPL-3.0` | `proprietary`
- **현 단계 동작**: 모든 pack 이 `license: MIT`. Loader 는 `proprietary`
  값에 대해 warn 만 출력 (stub)
- **미래 활성화**: 트리거 발동 → Open Core 또는 Hybrid 전환 시 loader
  의 commercial license token 검증 로직 활성화
- **상태**: `session-2026-05-09-license-infrastructure.md` Track C-4
  에서 정의

### 5.3 CONTRIBUTING.md 진화 안내
- **위치**: `CONTRIBUTING.md` 라이선스 섹션
- **본문**: "The project's license may evolve in future versions; by
  signing the CLA, you grant Hashevolution the right to relicense..."
- **효과**: 미래 전환 시 "약속 위반" 논란 예방
- **상태**: Track A-3 에서 적용 예정

### 5.4 모듈 분리 압력 (Plugin API)
- **위치**: `core/plugins/` 디렉토리, `packs/general/`
- **효과**: v0.3 Plugin API 가 자연스럽게 "core vs. pack" 경계를
  강제 → 미래 Open Core 전환 시 enterprise 기능을 pack 으로 분리하는
  비용이 낮아짐 (이미 분리 가능한 구조)
- **상태**: `session-2026-05-09-license-infrastructure.md` Track C 진행 중

---

## 6. 상표 트랙 (라이선스 독립)

### 6.1 출원 계획
- **워드마크**: "JAMES", "PROJECT JAMES"
- **출원 국가**: 한국 (1순위), 미국 (2순위)
- **변리사 자문**: 미정 — 자문 일정 잡기 (담당자: TBD)
- **예상 일정**: 출원 → 등록 12~18개월

### 6.2 진행 로그
| 일자 | 단계 | 결과 |
|---|---|---|
| — | 변리사 자문 일정 잡기 | 미진행 |
| — | 한국 출원 | 미진행 |
| — | 미국 출원 | 미진행 |
| — | 등록 | — |

### 6.3 등록 완료 후 필수 작업
- [ ] `docs/legal/TRADEMARK_POLICY.md` 신설 (Grafana Labs 모델 참조)
- [ ] README 에 ® 표기 추가
- [ ] CLA 본문에 상표권 보호 절 추가
- [ ] 라이선스 전환 시 상표가 라이선스에 포함되지 않음을 명시

---

## 7. 특허 트랙 (라이선스 독립)

### 7.1 출원 계획
- **출원 시점**: v0.3 부터 (사용자 계획)
- **후보 영역**:
  - Retrieval pipeline (Hybrid Search + Graph-RAG 통합 방식)
  - Self-evolution Patch Pipeline (4-Gate 구조)
  - Security boundary (3-stage RBAC+ABAC+Instruction Isolation)
  - Reasoning mode dispatch (PR #38/39 의 mode 구조)
- **출원 국가**: 한국 + 미국 동시
- **변리사 자문**: 미정 — 자문 일정 잡기 (담당자: TBD)

### 7.2 라이선스 정합 고려사항 (변리사 자문 시 명확화)

- **MIT 단계**: implicit patent license 약함 → 별도 특허는 보호 가능
- **AGPL+Commercial 전환 시**: AGPL §11 patent grant 가 발동되면
  **core 코드 동작에 필요한 특허는 자동 grant** → 청구범위 작성 시
  core 와 enterprise pack 영역을 의도적으로 분리
- **Defensive Patent Pledge**: 침해 소송에 사용하지 않겠다는 공개
  선언 (Tesla 모델). 커뮤니티 신뢰 + 기업 채택률 동시 확보

### 7.3 진행 로그
| 일자 | 단계 | 결과 |
|---|---|---|
| — | 변리사 자문 일정 잡기 | 미진행 |
| — | 특허 가능 영역 식별 + 선행기술 조사 | 미진행 |
| — | 한국 출원 | 미진행 |
| — | 미국 출원 (PCT 경로 또는 직접) | 미진행 |
| — | 심사 / 등록 | — |
| — | Defensive Patent Pledge 공개 | — |

### 7.4 외부 특허 모니터링 (third-party patent watch)

> 우리 출원 트랙과 별개로, **JAMES 아키텍처와 인접한 영역의 타사 특허**를
> 분기 1회 추적합니다. 침해 회피 + 청구항 범위 협소화 압력 + 무효화 카드
> 축적의 세 가지 목적을 동시 달성하기 위함입니다.

**모니터링 키워드 (Google Patents / KIPRIS 검색용):**
- `graph-rag` / `graph rag` / `knowledge graph rag`
- `formal query language` AND (`llm` OR `large language model`)
- `sparql` AND (`llm` OR `chatbot`)
- `vector retrieval` AND (`knowledge graph` OR `ontology`)
- `instruction isolation` AND (`prompt injection` OR `rag`)
- `self-evolution` AND (`patch` OR `code generation`) — 자가진화 영역
- `audit log` AND (`llm response` OR `ai decision`) — 감사 trace 영역

**관심 양수인 (Watch List):**

| 양수인 | 관심 사유 | 알려진 특허 (예) |
|---|---|---|
| Amazon Technologies, Inc. | 2026-01-20 US12531820B2 (neuro-symbolic KG + LLM) — JAMES와 인접 아키텍처 영역 | US12531820B2 (claim 1/5/14 = method/system/CRM) |
| Microsoft Corp. | GraphRAG 공개 + 관련 특허 출원 가능성 | 미식별 (모니터링 필요) |
| Google LLC / DeepMind | Vertex AI RAG + Search API | 미식별 |
| OpenAI OpCo | Assistant API + retrieval | 미식별 |
| Meta Platforms | LlamaIndex 인수 시나리오 시 패밀리 발생 가능 | — |
| IBM / Watson | 전통 NLP + KG 영역 | 다수 (별도 조사 필요) |

**Continuation / divisional / PCT family 추적 항목:**
- `US12531820B2` (Amazon, 2026-01-20) — continuation/divisional 출원 추적
- 동일 패밀리의 PCT 출원 → KIPO (한국), EPO (유럽), JPO (일본) 국가 진입 여부 — 한국 거주 사용자에게는 KIPO 진입이 가장 중요

**점검 주기 + 산출물:**
- 분기 1회, §8 모니터링 로그와 같은 분기에 점검
- 결과는 §7.4 의 외부 특허 watch table 에 행 추가 (특허번호, 양수인, 우선일, 영향 평가, 우리 아키텍처 mitigation 메모)
- 새 특허가 *우리 아키텍처와 element-by-element 비교 필요한 수준* 으로 발견되면 비공개 분석 노트 작성 (저장소는 *공개 repo 외부* — 향후 litigation 시 attorney work-product 보호를 받지 못할 수 있음)

**외부 특허 watch table (분기별 발견 항목 기록):**

| 발견일 | 특허번호 | 양수인 | 우선일 / 등록일 | 인접도 (1~5) | JAMES 아키텍처 mitigation | 비공개 분석 위치 | 비고 |
|---|---|---|---|---|---|---|---|
| 2026-05-19 | US12531820B2 | Amazon Technologies, Inc. | 2023-09-29 / 2026-01-20 | 3 (인접하나 3개 핵심 limitation 부재) | claim 1 의 (b)(e)(g) 요소 — NL→formal 변환, LLM formal 출력, formal→NL 변환 — 모두 부재. ARCHITECTURE.md §3 원칙 8 (NL-throughout pipeline) + §5.6 (Change Request) 가 mitigation 역할. | 비공개 보관 (공개 repo 외부) | Velog K4 댓글로 제3자 문의 받음 → 본 점검의 트리거. 상업화 단계 진입 시 변리사 정식 FTO 필수 |

**트리거 — 외부 특허 모니터링 결과가 라이선스/아키텍처 결정에 영향을 주는 경우:**
1. 인접도 5 (1:1 일치 위험) 신규 특허 발견 → §4 검토 절차에 준해 비공개 변리사 자문 즉시 개시
2. 우리 출원 가능 영역 (§7.1) 과 직접 겹치는 특허 발견 → §7.1 후보 영역 재조정
3. 한국 KIPO 패밀리 진입 확인 → 한국 출원 우선순위 재조정

---

## 8. 분기별 모니터링 로그

> 분기 1회 측정. 결과를 표 아래에 행으로 추가. 트리거 충족 시
> §4 의 검토 절차 개시.

| 분기 | GH stars | Active deployers | 상용 문의 (분기) | 클로닝 | Enterprise PoC | 트리거 충족 | 비고 |
|---|---|---|---|---|---|---|---|
| 2026-Q2 (v0.3 release) | 1 | 0 | 0 | none | none | 0/5 | 최초 baseline 측정 (2026-05-13). repo public 전환 직후 (생성 2026-05-05). `/feedback` endpoint 미설치 → deployer 측정 인프라 미비. T3(클로닝) Google Alerts 등록 미진행. |

---

## 9. 의사결정 이력

| 일자 | 결정 | 근거 | 기록 |
|---|---|---|---|
| 2026-05-11 | v0.3 진입 시점 MIT 유지 결정 | 라이선스 강화 황금률, 0→1 채택 구간에서 AGPL/BUSL 은 채택률만 떨어뜨리고 보호할 자산 없음. 경험적 증거: 성공한 강화 사례 모두 permissive 출발 | `session-2026-05-09-license-infrastructure.md` §2 Track A-1 |

---

## 10. 후임자에게

이 문서를 읽고 있다면, 다음을 먼저 확인하세요:

1. §8 모니터링 로그의 최신 행 — 현재 트리거 상태
2. §3 트리거 임계값 — 2개 이상 충족했는지
3. §4 검토 절차 — 충족 시 다음 행동
4. §9 의사결정 이력 — 과거 판단의 근거
5. §5 사전 준비 인프라 상태 — 전환 실행 가능 여부

**경고**: 트리거 충족 전 라이선스 강화를 단행하지 마세요. 이 문서의
핵심 결정(2026-05-11) 은 그 단계가 가장 비싸다는 경험적 증거에
기반합니다. 트리거를 새로 정의하거나 낮추기 전에 §2 의 사례표를
다시 읽으세요.

---

**End of LICENSE_PLAN.**

본 문서의 갱신은 PR 로 진행하며, `architecture` 라벨을 붙입니다
(CLAUDE.md rule 4 정합).
