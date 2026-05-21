# Session Brief — License & Plugin-API Infrastructure (v0.3 진입 준비)

> **세션 일자**: 2026-05-09 (작성), 2026-05-11 (의사결정 확정 + Track A 재구성)
> **대상 사이클**: v0.2 → v0.3 전환 구간
> **활성 브랜치**: `claude/plugin-api-license-setup-O71bQ`
> **선행 문서**: `CLAUDE.md` → `docs/PLATFORM_READINESS.md` →
> `ROADMAP.md` → `docs/handovers/v0.2.0-platform-track.md` →
> 본 문서 → `docs/LICENSE_PLAN.md` (라이선스 장기 의사결정 보존) →
> `docs/design/v0.3-knowledge-cascade.md`

> **주요 의사결정 (2026-05-11)**: v0.3 단계 라이선스는 **MIT 유지**.
> 라이선스 강화 황금률("보호할 생태계가 생긴 다음에 잠그기")에 따라
> 0→1 채택 구간에서는 진입장벽 최소화가 우선. 다만 **미래 전환을
> trivial 하게 만들 저비용 사전 작업**(CLA relicensing grant, plugin
> manifest license 필드, 상표·특허 트랙) 은 지금 수행. 전환 트리거
> 조건 5종은 `docs/LICENSE_PLAN.md` 에 영구 보존.

---

## 0. 이 문서가 해결하려는 문제

v0.2.0이 5축 엔지니어링 완료 상태이고 Axis 6(두 번째 사용자)만 남아
있는 시점에서, **v0.3 Platform Skeleton**으로 넘어가며 동시에 **외부
홍보 시작**과 **특허 진행**이 같은 분기에 발생한다. 따라서 v0.3 진입
직전에 정리해야 할 인프라성 작업 3건:

1. **라이선스 계획 확정** — 현 단계는 **MIT 유지**로 의사결정 완료.
   다만 미래 전환(AGPL+Commercial dual / Apache 2.0 + Trademark / BUSL
   중 시점·맥락에 맞춰 재선택)을 **trivial 하게 만들 사전 작업**과
   **5종 트리거 조건 모니터링 체계**를 지금 구축한다. 사전 작업이
   없으면 미래 어떤 강화 라이선스로도 깨끗히 전환 불가.
2. **외부 PR CLA 검증 체계** — 홍보 시작 직후 외부 기여자가 PR 을
   열기 시작하면 retroactive CLA 비용이 폭증. CLA Assistant 를 지금
   설치 + CLA 본문에 **relicensing grant 절 포함** 이 미래 전환의
   기술적 전제조건 (MongoDB / Grafana 가 정확히 이 절 덕분에 전환 가능).
3. **v0.3 Plugin API 스켈레톤** — `core/plugins/base.py` 인터페이스
   4종 + 로더 + `packs/general/` 도그푸드 + 버저닝 정책. 추가로 미래
   proprietary pack 호환을 위해 **`pack.yaml` 에 `license:` 필드 사전
   설계** (현 단계 모든 pack 은 `license: mit`, 인프라만 미리).

세 트랙의 의존성:

```
Track A (라이선스 계획) ──► CLA 본문 작성 (Track B-2) ──► CLA Assistant (B-3~)
       │                                                          │
       │                                                          │
       └────────────────────► Plugin API license: field ◄─────────┘
                                  (Track C-4)
```

처리 순서: **Track A(계획+사전작업) → Track B(CLA) → Track C(Plugin API)**.
A 의 LICENSE_PLAN 문서가 먼저 확정되어야 B 의 CLA 본문(특히 relicensing
grant 의 정확한 문구)이 정해진다.

---

## 1. 통합 로드맵 체크리스트 (마스터)

> **v0.3 진입 정식: 2026-05-13** — Axis 6 두 번째 사용자 게이트 통과,
> v0.2 → v0.3 gate clear. 본 트랙은 이제 v0.3 의 첫 deliverable 묶음.
> ROADMAP.md v0.3 섹션 + `v0.2.0-platform-track.md §3` 참조.
>
> **운영 원칙**: 모든 세션의 진행 상황 공유는 아래 체크리스트를
> 그대로 복사해서 `[ ]` → `[x]`로 갱신해 표시할 것. 자유 텍스트
> 진척 보고 금지.

### Track A — 라이선스 계획 (MIT 유지 + 사전 작업 + 모니터링)
- [x] A-1. 라이선스 의사결정 — **MIT 유지** 확정 (2026-05-11)
- [x] A-2. `docs/LICENSE_PLAN.md` 신설 — 트리거 5종 + 전환 절차 영구 보존 (2026-05-11 머지)
- [ ] A-3. `CONTRIBUTING.md` 한 줄 추가 — "License may evolve in future
  versions; CLA grants Hashevolution the right to relicense" (기대 정렬)
  — *CLA 본문(B-2) 확정 후 동시 PR. 현재 L312 는 "MIT 단순 동의" 한 줄.*
- [ ] A-4. `THIRD_PARTY_LICENSES.md` 신설 (의존성 인벤토리, 라이선스
  강도와 무관하게 유효)
- [ ] A-5. `README.md` / `README.ko.md` / `README.beginner.ko.md` 의
  라이선스 한 줄을 "**MIT licensed. Use freely.**" 로 통일 (홍보 노이즈 0)
  — *현재 `README.md` L181-183 + `README.ko.md` L182-184 는 표준 문구 미적용,
  `README.beginner.ko.md` 는 라이선스 줄 자체 없음.*
- [ ] A-6. 분기별 트리거 모니터링 시작 — 최초 측정 기록을 `LICENSE_PLAN.md`
  하단 로그 섹션에 기입 (v0.3 릴리스 시점)
  — *현재 §8 표에 `2026-Q2 (v0.3 release)` placeholder 행만 존재 (TBD).*
- [ ] A-7. 상표 등록 트랙 개시 — 변리사 자문 일정(한국+미국 출원) 박기,
  `LICENSE_PLAN.md` §상표 섹션에 진행 상황 기록
- [ ] A-8. 특허 출원 트랙 개시 — v0.3 부터 진행 예정, AGPL §11 정합성
  변리사 자문에 포함, `LICENSE_PLAN.md` §특허 섹션에 진행 상황 기록

### Track B — 외부 PR CLA 검증 체계
- [x] B-1. CLA 방식 선택 — **CLA Assistant 단독** (§3 B-1 표 + recommendation)
- [x] B-2. `docs/legal/CLA.md` 본문 초안 작성 (Apache ICLA 기반 + **§4-bis
  Relicensing Grant 절 필수 포함** — 미래 전환 기술적 전제조건) — **PR #340 (2026-05-19, v1.0 148줄)**
- [x] B-3. CLA 저장소 / 서명 기록 위치 결정 — **`hashevolution/james-rag-evol-cla` private repo 생성 완료**
- [x] B-4. CLA Assistant (또는 DCO bot) 설치 — **사용자 액션 완료 (cla-assistant.io 인증 + Gist 등록 + repo 연결 + `CLA_BOT_PAT` repo secret)**
- [x] B-5. `.github/workflows/cla.yml` 추가 (자동 검증 게이트) — **PR #340 (2026-05-19, 61줄, `contributor-assistant/github-action@v2.6.1`)**
- [x] B-6. 첫 외부 PR 시나리오 dry-run (테스트 계정 1건) — **2026-05-20 별도 GitHub 계정으로 dry-run 통과, 봇 코멘트 → 서명 코멘트 → status check ✅ 전 과정 검증 완료**
- [x] B-7. `CONTRIBUTING.md` 에 CLA 절차 추가 — **PR #340**
- [x] B-8. CLA 거절 시 응대 템플릿 작성 (`.github/ISSUE_TEMPLATE/` 또는 PR template) — **PR #340 + `docs/legal/non-cla-contributions.md`**

### Track C — v0.3 Plugin API 스켈레톤
- [ ] C-1. `core/plugins/` 디렉토리 설계 합의
- [ ] C-2. `core/plugins/base.py` — 4 plugin types 타입 인터페이스
- [ ] C-3. `core/plugins/loader.py` — `JAMES_PLUGINS=` 동적 로더
- [ ] C-4. Manifest 스키마 (`pack.yaml`) + 서명 해시 검증
- [ ] C-5. `packs/general/` — JAMES 기본 동작 추출 (도그푸드)
- [ ] C-6. `JAMES_WORKSPACE=` 환경변수 + 멀티 인스턴스 라우팅
- [ ] C-7. `docs/PLUGIN_AUTHORING.md` — 작성자 가이드
- [ ] C-8. `docs/VERSIONING.md` — SemVer + 12개월 deprecation 정책
- [ ] C-9. Eval 계약 (PR 머지 차단: RAGAS + STEP-N 강제)
- [ ] C-10. 도그푸드 게이트 검증 (`packs/general/` 제거 시 깨끗한 실패)
- [ ] C-11. (선택) Knowledge Cascade Phase A 동시 진행 여부 결정
  — `docs/design/v0.3-knowledge-cascade.md` 참조

### 횡단 — 거버넌스
- [x] G-1. 본 핸드오버를 `CLAUDE.md` 의 "Where to look next" 표에 추가
- [x] G-2. `docs/LICENSE_PLAN.md` 도 `CLAUDE.md` 표에 추가 (영구 보존 문서)
- [ ] G-3. `ROADMAP.md` v0.3 섹션에 CLA / 라이선스 모니터링 항목 반영
- [ ] G-4. PR 라벨 `architecture`, `license`, `cla` 정의 (없으면 생성)
- [ ] G-5. 분기 1회 트리거 모니터링 캘린더 알림 등록

---

## 2. Track A — 라이선스 계획 (MIT 유지 + 사전 작업 + 모니터링)

### A-1. 라이선스 의사결정 — **MIT 유지 확정 (2026-05-11)**

**최종 결정**: v0.3 단계는 **MIT 유지**.

**근거** (라이선스 강화의 황금률 — *"보호할 생태계가 생긴 다음에
잠그는 것"*):

| 단계 | MIT | AGPL+Commercial dual | BUSL |
|---|---|---|---|
| 스타 0~수십 (= 지금) | ✅ 진입장벽 0 | ❌ 회사 사용자 99% 이탈 | ❌ 같음 |
| 스타 1k+ / 도입 사례 다수 | ⚠️ 클로닝 위험 노출 | ✅ 합리적 보호 | ✅ 합리적 보호 |
| 상용 문의 실제 발생 | ⚠️ 수익화 어려움 | ✅ 즉시 청구 가능 | ✅ 같음 |

**경험적 증거** (성공한 라이선스 강화 사례는 모두 permissive 출발):

| 프로젝트 | MIT/Apache 시작 → 강화 전환 |
|---|---|
| Elastic | 9년 / 스타 50k+ → SSPL |
| HashiCorp Terraform | 9년 / 스타 40k+ → BUSL |
| Sentry | 10년 / 스타 30k+ → BUSL |
| MongoDB | 9년 / ARR $200M+ → SSPL |
| Redis | 15년 / 시장 지배 후 → dual |

**공통점**: 클로닝 손해 실발생 또는 상용 경쟁자 등장 직후 전환.
처음부터 BUSL/AGPL 로 출발한 프로젝트는 대부분 채택률 0 으로 묻힘.

**현 단계 JAMES 컨텍스트**: "이 프로젝트가 존재한다는 사실을 아는
사람이 100명도 안 되는" 0→1 채택 구간. 이 구간에서 AGPL/BUSL 은
**채택률만 떨어뜨리고, 정작 보호할 자산은 없음**.

**완료 조건**: 본 항목으로 의사결정 종결. `LICENSE` 파일은 그대로
MIT 유지. GitHub Repo Settings → License 메타데이터도 `MIT` 그대로.
이 결정의 영속성은 `docs/LICENSE_PLAN.md` 가 보장.

### A-2. `docs/LICENSE_PLAN.md` 신설

라이선스 의사결정의 영구 보존 문서. 본 핸드오버가 머지·아카이브된
후에도 미래 결정자(본인일지 후임일지 모름) 가 참조할 수 있도록
별도 문서로 분리. 구성:

1. 현재 라이선스 (MIT) + 황금률
2. 5종 트리거 조건 (T1~T5) 및 임계값
3. 측정 주기 + 기록 양식
4. 트리거 충족 시 검토 옵션 (AGPL+Commercial, Apache 2.0 + Trademark,
   BUSL — 시점·컨텍스트에 따라 재선택)
5. 사전 준비된 인프라 (CLA §4-bis relicensing grant, plugin manifest
   `license:` 필드, 상표·특허 트랙)
6. 분기별 모니터링 로그 (수치 기록)

**완료 조건**: `docs/LICENSE_PLAN.md` 가 main 에 머지되고, 본
핸드오버에서 해당 문서로 링크가 연결됨.

### A-3. `CONTRIBUTING.md` 라이선스 진화 안내 한 줄 추가

현재 (`CONTRIBUTING.md` L310-L312):
```
By contributing, you agree that your contributions will be licensed
under the [MIT License](LICENSE).
```

CLA 도입 후 다음으로 교체:
```
By contributing, you agree to the terms of the
[Contributor License Agreement](docs/legal/CLA.md). Your contributions
will be initially licensed under the [MIT License](LICENSE). The
project's license may evolve in future versions; by signing the CLA,
you grant Hashevolution the right to relicense your contributions
under such future terms (see CLA §4-bis Relicensing Grant).
```

**왜 한 줄 더 추가하는가**: 기대 정렬. 미래 라이선스 강화 시점에
"약속 위반" 논란 예방. MongoDB / Grafana 가 전환 시 커뮤니티 반발을
일부 받은 이유 중 하나는 사전 안내 부재 — JAMES 는 처음부터 명시.

### A-4. `THIRD_PARTY_LICENSES.md` 신설

`requirements_pinned.txt` 기반 의존성 라이선스 인벤토리. **라이선스
강도와 무관하게 유효** — 모든 OSS 프로젝트가 갖춰야 할 위생.

명령 (Claude 실행):
```
pip install pip-licenses
pip-licenses --format=markdown --with-urls > THIRD_PARTY_LICENSES.md
```

CI 가 분기마다 재생성하도록 GitHub Actions 추가 (선택, 후순위).

### A-5. README 3종의 라이선스 한 줄 통일

홍보 노이즈 최소화를 위해 라이선스 안내는 한 줄로 단순화.

- [ ] `README.md` 끝부분 라이선스 섹션을 다음 한 문장으로 통일:
      `**Licensed under the MIT License.** Use freely. See [LICENSE](LICENSE).`
- [ ] `README.ko.md` 동일 (한국어 번역)
- [ ] `README.beginner.ko.md` 동일

추가 설명(예: dual licensing, commercial option) 은 **현 단계 노이즈**.
트리거 발동 후 라이선스 전환 시점에 README 상단 한 단락으로 확장.

### A-6. 분기별 트리거 모니터링 시작

`docs/LICENSE_PLAN.md` 의 모니터링 로그 섹션에 분기마다 수치 기록.

**최초 측정 기록** (v0.3 릴리스 시점에 실행):
- GitHub stars 현재값
- 활성 외부 deployer 수 (`/feedback` endpoint 데이터 기반)
- 상용 문의 카운트 (분기 누적)
- 클로닝 위협 감지 결과 (none / detected)
- 첫 enterprise 도입 시도 여부

**측정 주기**: 분기 1회. 캘린더 알림 등록 권고.

### A-7. 상표 등록 트랙 개시 (라이선스 독립)

라이선스 강도와 무관하게 브랜드 보호는 항상 유효. AGPL 같은 copyleft
도 상표를 보호하지 않으므로 별도 트랙으로 진행.

- [ ] 변리사 자문 일정 잡기 (한국 + 미국 동시 출원 권고)
- [ ] "JAMES" / "PROJECT JAMES" 워드마크 출원
- [ ] 진행 상황을 `docs/LICENSE_PLAN.md` §상표 섹션에 기록
- [ ] 출원 완료 후 `docs/legal/TRADEMARK_POLICY.md` 신설 (Grafana Labs
      모델 참조)

**예상 일정**: 출원 → 등록 12~18개월. v0.3 진입 시점에 출원 개시하면
v1.0 즈음 등록 완료.

### A-8. 특허 출원 트랙 개시 (라이선스 독립)

사용자 계획대로 v0.3 부터 특허 진행. 라이선스와 독립적이지만 정합
지점이 있음 — 변리사 자문 시 다음 명확화:

- **MIT 코드와 특허의 관계**: MIT 는 implicit patent license 가
  약함(법원에서 다툼 여지). 즉 JAMES 코드를 MIT 로 공개해도 별도
  특허는 보호 가능. 그러나 향후 AGPL+Commercial 전환 시 AGPL §11
  patent grant 가 발동되면 **core 코드 동작에 필요한 특허는 자동
  grant** 되므로 청구범위 작성 시 고려 필요
- **청구범위 분리**: core (= 향후 AGPL 될 영역) vs. enterprise pack
  (= 향후 proprietary 될 영역) 의 특허 청구범위를 의도적으로 분리
- **Defensive Patent Pledge** 옵션 — 침해 소송에 사용하지 않겠다는
  공개 선언이 커뮤니티 신뢰 + 기업 채택률 동시 확보 (Tesla 모델)
- 한국 + 미국 동시 출원 권고 (미국이 AI 특허 인정 범위 더 넓음)

- [ ] 변리사 자문 일정 잡기
- [ ] 특허 가능 영역 식별 (retrieval pipeline, graph reasoning,
      self-evolution, security boundary 후보)
- [ ] 진행 상황을 `docs/LICENSE_PLAN.md` §특허 섹션에 기록

**Note**: `SECURITY.md` 의 "AS IS" 면책 조항은 MIT 와 정합. 변경 불요.

---

## 3. Track B — 외부 PR CLA 검증 체계 (세부)

### B-1. CLA 방식 선택

| 방식 | 작동 | 기여자 부담 | 유지 비용 | 추천 |
|---|---|---|---|---|
| **DCO sign-off** | 커밋 `Signed-off-by:` 라인 추가 | 매우 낮음 | 0 | 솔로 메인테이너 단계 |
| **CLA Assistant** | 첫 PR 시 GitHub 봇이 서명 요청 | 낮음 (체크박스 1회) | 무료 SaaS | Plugin API 공개 후 |
| **Both** | 둘 다 강제 | 중간 | 중간 | 기업 PR 받기 시작할 때 |

**Recommendation**: **CLA Assistant 단독**. 이유:
- DCO 는 GitHub UI 가 자동 사인오프를 지원하지 않아 신규 기여자
  마찰 큼
- CLA Assistant 는 한 번 서명하면 그 GitHub 계정의 모든 후속 PR
  에서 자동 통과 → 운영 부담 최소
- 라이선스 변경(MIT → 듀얼) 시점에만 재서명 요청 필요

### B-2. `CLA.md` 본문 초안

Apache ICLA(Individual) v2.2 를 베이스로 JAMES 용도로 축약 + **§4-bis
Relicensing Grant 절 신규 추가** (미래 라이선스 전환의 기술적 전제조건).
별도 `docs/legal/CLA.md` 위치 권고 (루트 오염 방지).

핵심 조항(요지):

1. **저작권 라이선스 부여** — Hashevolution 에 영구 / 무상 /
   재라이선스 가능한 권리 부여
2. **특허 라이선스 부여** — 기여물에 포함된 특허에 대한 무상 사용권
3. **원본 진술** — 기여물이 본인 저작이거나 권리 보유자임 진술
4. **고용주 권리** — 고용주 권리 충돌 시 본인 책임 명시
5. **No warranty** — 기여물은 "AS IS"

#### §4-bis. Relicensing Grant (**필수 — 미래 전환을 위해**)

> *"You hereby grant to Hashevolution the right, but not the obligation,
> to relicense Your Contributions, in whole or in part, under any other
> license terms of its choosing, including but not limited to other
> open-source licenses (e.g., AGPL-3.0, Apache-2.0, BUSL-1.1) or
> proprietary commercial licenses. This grant is irrevocable for
> Contributions already accepted. You acknowledge that this grant
> enables Hashevolution to evolve the project's license model in
> response to market and ecosystem conditions without obtaining
> further consent from individual contributors."*

**왜 이 절이 결정적인가**:
- MongoDB 가 AGPL → SSPL, Elastic 이 Apache → SSPL → AGPL, Grafana 가
  Apache → AGPL 로 전환할 수 있었던 이유는 모든 기여자가 처음부터
  이 유형의 절에 서명했기 때문
- 이 절이 빠지면 미래 라이선스 강화 시 **모든 기여자 개별 동의 재수집**
  필요 → 사실상 전환 불가능
- 현 단계 MIT 유지여도 이 절은 무해함 (Hashevolution 이 행사하지
  않으면 기여자에게 아무 영향 없음)

Corporate CLA(CCLA) 는 v0.4 First Domain Pilot 시점에 추가 — 동일한
§4-bis 절을 포함시켜야 함.

### B-3. CLA 서명 기록 저장 위치

CLA Assistant 는 자체 저장소(별도 GitHub repo) 에 서명을 기록.
권고 구성:

- `hashevolution/james-rag-evol-cla` (private repo) 생성
- CLA Assistant 가 PR 단위로 issue 를 자동 생성하여 서명 추적

### B-4. CLA Assistant 설치 — **사용자 액션 (초보자용 상세)**

> 이 절차는 Claude 가 대행 불가. 사용자가 직접 수행해야 함.
> 한 단계라도 건너뛰면 다음 단계가 실패함.

**준비물 확인**
- [ ] GitHub 계정에 `hashevolution` 조직 admin 권한 보유 확인
  - 확인 방법: 브라우저에서 `https://github.com/hashevolution` 접속
  - 우측 상단 본인 아바타 → "Your organizations" → `hashevolution`
    옆에 `Owner` 배지가 보이면 OK
- [ ] `hashevolution/james-rag-evol` 저장소가 public 인지 확인
  - 확인 방법: `https://github.com/hashevolution/james-rag-evol`
    접속 → 저장소명 옆에 `Public` 배지

**Step 1. CLA 저장 전용 private repo 생성**
1. 브라우저에서 `https://github.com/organizations/hashevolution/repositories/new` 접속
2. "Repository name" 입력란에 정확히 `james-rag-evol-cla` 입력
3. "Description" 입력란에 `CLA signature records for james-rag-evol` 입력
4. 가시성(Visibility) 선택지에서 **Private** 라디오 버튼 클릭
5. "Initialize this repository with" 섹션의
   "Add a README file" 체크박스를 **체크**
6. "Add .gitignore" 는 **None** 유지
7. "Choose a license" 는 **None** 유지 (CLA 기록 저장소는 라이선스 불필요)
8. 화면 하단 초록색 "Create repository" 버튼 클릭
9. 생성 확인: 브라우저 주소가 `https://github.com/hashevolution/james-rag-evol-cla` 로 이동해야 함

**Step 2. CLA Assistant 앱 설치**
1. 브라우저에서 `https://cla-assistant.io/` 접속
2. 우측 상단 "Sign in with GitHub" 버튼 클릭
3. GitHub 인증 화면이 뜨면 본인 계정으로 로그인
4. CLA Assistant 가 요청하는 권한 목록이 표시됨:
   - "Read access to user email addresses" → 허용 필요
   - "Read access to organization membership" → 허용 필요
   - "Read/Write access to issues" → 허용 필요 (PR에 서명 요청 댓글 작성용)
5. "Authorize cla-assistant" 초록색 버튼 클릭
6. 로그인 후 우측 상단 "Configure CLA" 버튼 클릭

**Step 3. CLA 본문 등록 (B-2 결과물 사용)**
1. "Configure CLA" 화면에서 좌측 "Repository" 드롭다운 클릭
2. 목록에서 `hashevolution/james-rag-evol` 선택
   - 만약 목록에 안 보이면: 우측 상단 본인 아바타 →
     "Switch GitHub Account" → `hashevolution` 선택 → 다시 시도
3. "Gist" 입력란에 CLA 본문 Gist URL 입력
   - Gist 만드는 법:
     1. 브라우저에서 `https://gist.github.com/` 접속
     2. "Gist description" 에 `JAMES Individual CLA v1` 입력
     3. "Filename including extension" 에 `JAMES-ICLA.md` 입력
     4. 본문에 `docs/legal/CLA.md` 의 내용 복사-붙여넣기 (B-2 결과물)
     5. 화면 하단 "Create public gist" 버튼 클릭
     6. 생성된 Gist 페이지에서 우측 "Raw" 버튼 옆 주소창 URL 복사
4. CLA Assistant 의 "Gist" 입력란에 위 URL 붙여넣기
5. "Store signatures in" 옵션에서 "Database" (CLA Assistant 자체 DB)
   또는 "Repository" (`james-rag-evol-cla`) 선택
   - **권고**: "Repository" → `james-rag-evol-cla` 선택 (자체 보관)
6. 화면 하단 "Link" 또는 "Activate" 버튼 클릭
7. 활성화 확인: 같은 화면에 활성 CLA 목록에 `james-rag-evol` 이
   `Active` 상태로 표시되어야 함

**Step 4. 워크플로 파일 추가 (Claude 가 처리)**
- 사용자 액션 종료. 이후 `.github/workflows/cla.yml` 추가는
  Claude 가 PR로 처리.

**Step 5. 검증 (다음 외부 PR 시 자동)**
- B-6 항목 참조.

### B-5. `.github/workflows/cla.yml`

CLA Assistant 가 제공하는 GitHub Action 을 사용 (자체 호스팅 불필요).
Action 마켓플레이스: `contributor-assistant/github-action`.

샘플 (실제 작성은 PR 단계에서 검증):

```yaml
name: "CLA Assistant"
on:
  issue_comment:
    types: [created]
  pull_request_target:
    types: [opened, closed, synchronize]

permissions:
  actions: write
  contents: read
  pull-requests: write
  statuses: write

jobs:
  CLAAssistant:
    runs-on: ubuntu-latest
    steps:
      - name: "CLA Assistant"
        if: (github.event.comment.body == 'recheck' || github.event.comment.body == 'I have read the CLA Document and I hereby sign the CLA') || github.event_name == 'pull_request_target'
        uses: contributor-assistant/github-action@v2.6.1
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          PERSONAL_ACCESS_TOKEN: ${{ secrets.CLA_BOT_PAT }}
        with:
          path-to-signatures: 'signatures/version1/cla.json'
          path-to-document: 'https://github.com/hashevolution/james-rag-evol/blob/main/docs/legal/CLA.md'
          branch: 'main'
          allowlist: dependabot[bot]
          remote-organization-name: hashevolution
          remote-repository-name: james-rag-evol-cla
```

**사용자 액션 — `CLA_BOT_PAT` 생성**

1. 브라우저에서 `https://github.com/settings/personal-access-tokens/new` 접속
2. "Token name" 에 `JAMES-CLA-Assistant-Bot` 입력
3. "Resource owner" 드롭다운에서 `hashevolution` 선택
4. "Expiration" 은 `90 days` 권고 (만료 시 갱신 알림)
5. "Repository access" 에서 "Only select repositories" 선택 →
   `james-rag-evol-cla` 선택
6. "Repository permissions" 에서 다음만 활성화:
   - "Contents" → `Read and write`
   - "Pull requests" → `Read and write`
   - "Issues" → `Read and write`
7. 화면 하단 "Generate token" 클릭
8. **즉시 토큰 문자열 복사** (이 화면을 벗어나면 다시 볼 수 없음)
9. `https://github.com/hashevolution/james-rag-evol/settings/secrets/actions` 접속
10. "New repository secret" 클릭
11. "Name" 에 정확히 `CLA_BOT_PAT` 입력
12. "Secret" 에 위에서 복사한 토큰 붙여넣기
13. "Add secret" 클릭

### B-6. 첫 외부 PR Dry-run

테스트 절차:
- [ ] Claude 또는 사용자의 별도 GitHub 계정으로 fork
- [ ] 사소한 변경 (README 오타 수정) PR 생성
- [ ] CLA Assistant 봇이 "Please sign our CLA" 댓글 작성하는지 확인
- [ ] 댓글에 안내된 동의 문구 입력 후 PR 체크가 통과하는지 확인
- [ ] 통과 후 PR close (실제 머지하지 않음)

### B-7. CONTRIBUTING.md 갱신

Track A-7 에서 미리 준비된 문구로 교체.

### B-8. CLA 거절 응대 템플릿

`.github/PULL_REQUEST_TEMPLATE.md` 또는 별도 응대 문서로,
"CLA 서명을 거부하시는 경우 대신 가능한 기여 방법(이슈 보고,
디스커션, 별도 패치셋 공유 등)" 안내.

---

## 4. Track C — v0.3 Plugin API 스켈레톤 (세부)

> 본 트랙은 Track A/B 완료 후 시작. Track A/B 가 끝나면 외부
> 기여자가 합법적으로 PR 을 열 수 있는 인프라가 완성되며, 그때
> Plugin API 작업이 의미를 가짐.

### C-1. `core/plugins/` 디렉토리 설계

```
core/plugins/
  __init__.py        # public API re-exports
  base.py            # 4 abstract base classes
  loader.py          # dynamic loader (JAMES_PLUGINS env)
  manifest.py        # pack.yaml schema + hash verification
  registry.py        # in-memory plugin registry
  errors.py          # PluginLoadError, PluginVersionError, ...
packs/
  general/           # JAMES 기본 동작 (도그푸드)
    pack.yaml
    ontology.py
    prompts.py
    ui/
    scorers.py
```

**파일 크기 게이트**: 각 파일 < 20 KB (CLAUDE.md rule 5).

### C-2. `core/plugins/base.py` — 4 인터페이스

```python
class OntologyPack(Protocol):
    entity_types: list[str]
    relation_types: list[str]
    hierarchies: dict[str, list[str]]

class PromptPack(Protocol):
    def system_prompt(self, mode: str) -> str: ...
    def few_shot(self, task: str) -> list[dict]: ...

class UIPanel(Protocol):
    def render(self, ctx: PanelContext) -> str: ...  # server-rendered HTML

class Scorer(Protocol):
    def score(self, query: str, candidate: dict) -> float: ...
```

각 인터페이스는 `core/` 의 기존 타입(`Retriever`, `Reasoner` 등 —
PR #50 으로 확립)과 정합되어야 함.

### C-3. `core/plugins/loader.py`

핵심 동작:
- 환경변수 `JAMES_PLUGINS=general,reference` 파싱
- 각 pack 의 `pack.yaml` 로드 → manifest 검증
- SemVer 체크 (`james_api: ">=0.3,<0.4"`)
- 동적 import → registry 등록
- 실패 시 명확한 에러 (PluginLoadError 에 pack 명 + 실패 단계 포함)

### C-4. Manifest 스키마 (`pack.yaml`)

```yaml
name: general
version: 1.0.0
james_api: ">=0.3,<0.4"
description: "Default JAMES behavior pack"
author: "Hashevolution"
license: "MIT"                            # SPDX identifier (필수)
                                          # 허용값: MIT | Apache-2.0 |
                                          # AGPL-3.0 | proprietary
                                          # (proprietary 는 commercial
                                          # license token 검증 필요 —
                                          # 미래 enterprise pack 대비)
plugins:
  ontology: ontology:GeneralOntology
  prompts: prompts:GeneralPrompts
  ui:
    - ui.search:SearchPanel
    - ui.graph:GraphPanel
  scorers:
    - scorers:HybridScorer
hash: "sha256:abc..."   # CI 가 검증 (서명 인프라는 v1.0)
```

**왜 `license:` 필드를 v0.3 부터 두는가**:
- 현 단계 모든 pack 은 `license: MIT` 이라 강제 검증 없음
- 그러나 미래(트리거 발동 시점) enterprise pack 출시 시 manifest
  스키마 변경 없이 `license: proprietary` 값만 추가하면 됨
- 인프라 비용 0, 미래 옵션 보존 1
- Loader 의 검증 로직은 v0.3 에서 `if license == "proprietary": warn`
  수준으로 stub, 실제 commercial license token 검증은 트리거 후
  AGPL+Commercial 전환 시점에 활성화

### C-5. `packs/general/` 추출 — 도그푸드 게이트

**핵심 검증**: `packs/general/` 디렉토리를 삭제하면 서버가 깨끗하게
실패해야 함 (조용히 기본값으로 폴백하면 도그푸드 실패).

검증 시나리오:
```
unset JAMES_PLUGINS && python server_llmwiki.py
→ 정상 부팅 (general 자동 로드)

JAMES_PLUGINS= python server_llmwiki.py
→ RefusedToStart: "no pack loaded; set JAMES_PLUGINS=general"

JAMES_PLUGINS=general rm -rf packs/general && python server_llmwiki.py
→ PluginLoadError: "pack 'general' not found at packs/general/"
```

### C-6. `JAMES_WORKSPACE=` 환경변수

목적: 동일 코드베이스에서 다른 데이터 루트로 멀티 인스턴스 호스팅.
영향 받는 경로: `wiki/`, `uploads/`, `reports/`, `james_patch_log.jsonl`.

```python
WORKSPACE = Path(os.environ.get("JAMES_WORKSPACE", "."))
WIKI_DIR = WORKSPACE / "wiki"
UPLOADS_DIR = WORKSPACE / "uploads"
# ...
```

기존 하드코딩된 경로를 점진적으로 치환. 변경량이 크므로 별도 PR.

### C-7. `docs/PLUGIN_AUTHORING.md`

내용 구성:
1. Quickstart (no-op pack 5분 안에 만들기)
2. 4 plugin types 각각의 최소 예제
3. Manifest 작성 가이드
4. 로컬 테스트 (`JAMES_PLUGINS=mypack`)
5. RAGAS / STEP-N 통과 요건
6. 배포 (현재 단계 — 단일 저장소 fork)

**Done when**: 새 기여자가 1일 이내에 no-op pack 을 만들 수 있음
(`ROADMAP.md` v0.3 Done when 기준).

### C-8. `docs/VERSIONING.md`

핵심 약속:
- JAMES core 는 `0.x.y` 동안 breaking change 허용
- v1.0 부터 Plugin API 는 **별도 SemVer 트랙** + **12개월 deprecation 보장**
- Plugin API breaking change 는 `JAMES_API_DEPRECATIONS` env 로 사전 경고

### C-9. Eval Contract 강제

CI 가 PR 머지 차단:
- `packs/*/` 변경 → RAGAS + STEP-N 자동 실행
- 결과가 baseline 대비 regression 시 차단
- 현재 `scripts/bench.py --check` 와 동일 패턴

### C-10. 도그푸드 게이트 자동화

`scripts/dogfood_check.py` 추가:
```
python scripts/dogfood_check.py
→ packs/general 제거 시 서버 부팅 실패 확인
→ STEP 7 결과가 v0.2 main 과 byte-identical 확인
```
CI 에서 매 PR 마다 실행.

### C-11. Knowledge Cascade Phase A 병행 여부

`docs/design/v0.3-knowledge-cascade.md` §8 에 따르면 Phase A 는
"reversible / no dependency" 이며 Plugin 추출 시점이 같이 가기
좋다고 명시. 그러나 본 세션 스코프 외이므로 **별도 트랙으로
분리**. 본 핸드오버 체크리스트에서는 C-11 을 결정 항목으로만 유지.

---

## 5. 사용자 액션 통합 (초보자용 step-by-step)

> 이 섹션은 사용자가 직접 GUI/브라우저에서 수행해야 하는 작업만
> 모은 것이다. Claude 가 코드/문서/PR 로 처리하는 항목은 제외.

### Action U-1. 라이선스 의사결정 통보
- **언제**: Track A-1 단계
- **무엇을**: 사용자가 "MIT 유지" 또는 "듀얼 전환" 중 하나를
  본 세션 채팅에 명시적으로 답변
- **왜 사용자만 가능**: 라이선스는 비즈니스/법무 의사결정이며
  Claude 가 일방 결정 불가
- **예상 시간**: 5분

### Action U-2. CLA 저장 private repo 생성
- **언제**: Track B-3 완료 후, B-4 진입 직전
- **무엇을**: `hashevolution/james-rag-evol-cla` 생성
- **상세 절차**: §3 B-4 Step 1 참조 (9단계)
- **예상 시간**: 3분
- **실패 시**: 조직 admin 권한 없음 → Hashevolution Owner 에게
  권한 요청 후 재시도

### Action U-3. CLA Assistant 앱 설치
- **언제**: U-2 완료 직후
- **상세 절차**: §3 B-4 Step 2 참조 (6단계)
- **예상 시간**: 5분
- **실패 시**: GitHub 권한 거부 → 브라우저 시크릿 모드에서 재시도

### Action U-4. CLA Gist 등록
- **언제**: Claude 가 `docs/legal/CLA.md` 초안을 PR 로 올린 후
- **상세 절차**: §3 B-4 Step 3 참조 (7단계)
- **예상 시간**: 5분
- **실패 시**: Gist URL 형식 불일치 → "Raw" 버튼의 URL 인지 재확인

### Action U-5. `CLA_BOT_PAT` 시크릿 등록
- **언제**: U-4 완료 후
- **상세 절차**: §3 B-5 의 "사용자 액션 — `CLA_BOT_PAT` 생성" 참조 (13단계)
- **예상 시간**: 7분
- **실패 시**: PAT 만료 → 90일 단위 재발급 필요 (캘린더 알림 권고)

### Action U-6. 첫 외부 PR Dry-run
- **언제**: Track B-5 워크플로 PR 머지 후
- **무엇을**: 별도 GitHub 계정으로 fork → 사소한 PR 생성 →
  CLA 봇 동작 확인 → PR close
- **예상 시간**: 10분

### Action U-7. (선택) 듀얼 라이선스 전환 시 추가 작업
- **언제**: U-1 에서 "듀얼" 선택한 경우에만
- **무엇을**: GitHub Repo Settings → "License" 메타데이터 갱신,
  README 3종 동시 갱신 확인
- **상세 절차**: U-1 답변 후 Claude 가 별도 step-by-step 제공

---

## 6. 다음 세션 시작 시 읽을 순서

1. `CLAUDE.md` (강제, 5 critical rules 재확인)
2. `docs/PLATFORM_READINESS.md` §3 Gate v0.3 (pass criteria)
3. **본 문서** §1 통합 체크리스트 (현재 진척 확인)
4. 현재 in-progress 트랙의 해당 섹션 (§2 / §3 / §4)
5. `ROADMAP.md` v0.3 섹션 (deliverables 매핑)
6. (Track C 진입 시) `docs/design/v0.3-knowledge-cascade.md`

---

## 7. 진행 보고 양식 (필수)

모든 진행 업데이트는 다음 형식으로 보고:

```
### 진행 보고 (YYYY-MM-DD)

#### Track A — 라이선스 결정 후속
- [x] A-1. ...
- [x] A-2. ...
- [ ] A-3. ...  ← in progress
- [ ] A-4. ...
...

#### Track B — 외부 PR CLA 검증 체계
- [ ] B-1. ...
...

#### Track C — v0.3 Plugin API 스켈레톤
- [ ] C-1. ...
...

#### 사용자 액션 대기 큐
- U-1. 라이선스 의사결정 통보 (대기 중 / 완료)
- U-2. ...

#### 블로커
- (없음 / 있음 — 내용)
```

자유 텍스트 보고 금지. 위 양식 외의 진척 공유는 무효 처리.

---

## 8. 한국어 요약

이 세션은 **라이선스 결정 → CLA 인프라 → v0.3 Plugin API**
세 트랙을 순차적으로 처리합니다. Track A 는 의사결정이 끝나야
B 의 CLA 본문을 확정할 수 있고, B 의 외부 PR 검증 게이트가
서야 C 의 Plugin API 가 외부 기여를 받을 수 있는 상태가
됩니다. 사용자가 직접 수행해야 하는 GUI 작업은 §5 에 6~7건
모아두었으며, 각 단계는 처음 해보는 사람도 따라할 수 있게
세분화되어 있습니다. 모든 진척 공유는 §1 마스터 체크리스트
또는 §7 보고 양식을 사용하며, 자유 텍스트 보고는 무효입니다.

---

**End of brief.**

이 문서는 세 트랙이 모두 완료되어 v0.3 Plugin Skeleton 릴리스
PR 이 머지되는 시점까지 유지됩니다. 트랙 완료 시 해당 섹션을
**제거하지 말고** 체크박스만 `[x]` 로 갱신하여 감사 추적성을
보존하세요.
