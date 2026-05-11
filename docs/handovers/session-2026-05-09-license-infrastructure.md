# Session Brief — License & Plugin-API Infrastructure (v0.3 진입 준비)

> **세션 일자**: 2026-05-09 (작성), 2026-05-11 (현재 확장)
> **대상 사이클**: v0.2 → v0.3 전환 구간
> **활성 브랜치**: `claude/plugin-api-license-setup-O71bQ`
> **선행 문서**: `CLAUDE.md` → `docs/PLATFORM_READINESS.md` →
> `ROADMAP.md` → `docs/handovers/v0.2.0-platform-track.md` →
> 본 문서 → `docs/design/v0.3-knowledge-cascade.md`

---

## 0. 이 문서가 해결하려는 문제

v0.2.0이 5축 엔지니어링 완료 상태이고 Axis 6(두 번째 사용자)만 남아
있는 시점에서, **v0.3 Platform Skeleton**으로 넘어가기 직전에 정리해야
할 인프라성 작업 3건이 동시에 떠올랐다.

1. **라이선스 결정 후속** — 현재 MIT를 유지할지, 듀얼 라이선스
   (MIT + AGPL/BSL 등)로 전환할지의 의사결정과 그 후속 정합성 작업.
2. **외부 PR CLA 검증 체계** — v0.3에서 외부 기여자가 Plugin API를
   대상으로 PR을 열 수 있게 되는 순간, CLA(Contributor License
   Agreement) 없이 받으면 라이선스 재배포 책임이 모호해진다.
3. **v0.3 Plugin API 스켈레톤** — `core/plugins/base.py` 인터페이스
   4종 + 로더 + `packs/general/` 도그푸드 + 버저닝 정책.

이 셋은 서로 의존한다:

```
라이선스 결정 ──► CLA 텍스트 정의 ──► CLA Assistant 설치
       │                                       │
       └──────────────► Plugin API ◄───────────┘
                         (외부 PR 받기 위한 인프라)
```

따라서 **Track A(라이선스) → Track B(CLA) → Track C(Plugin API)** 순서로
순차적으로 처리한다. Track A가 끝나기 전에 B를 시작하면 CLA 본문 자체가
바뀌어 다시 써야 한다.

---

## 1. 통합 로드맵 체크리스트 (마스터)

> **운영 원칙**: 모든 세션의 진행 상황 공유는 아래 체크리스트를
> 그대로 복사해서 `[ ]` → `[x]`로 갱신해 표시할 것. 자유 텍스트
> 진척 보고 금지.

### Track A — 라이선스 결정 후속
- [ ] A-1. 라이선스 의사결정 확정 (MIT 유지 vs 듀얼)
- [ ] A-2. `LICENSE` 파일 최종 검토 + (필요 시) 보조 LICENSE 추가
- [ ] A-3. `NOTICE` 파일 신설 (저작권 보유자 + 외부 기여자 트래킹)
- [ ] A-4. `THIRD_PARTY_LICENSES.md` 신설 (의존성 라이선스 인벤토리)
- [ ] A-5. 소스 파일 헤더 일관성 점검 (헤더 정책 결정)
- [ ] A-6. `README.md` / `README.ko.md` 라이선스 섹션 정합성
- [ ] A-7. `CONTRIBUTING.md` 라이선스 동의 문구 갱신
- [ ] A-8. `SECURITY.md` 책임 한정 문구(Disclaimer) 정합성

### Track B — 외부 PR CLA 검증 체계
- [ ] B-1. CLA 방식 선택 (DCO sign-off vs CLA Assistant vs Both)
- [ ] B-2. `CLA.md` 본문 초안 작성 (Apache ICLA 기반)
- [ ] B-3. CLA 저장소 / 서명 기록 위치 결정
- [ ] B-4. CLA Assistant (또는 DCO bot) 설치 — **사용자 액션 필요**
- [ ] B-5. `.github/workflows/cla.yml` 추가 (자동 검증 게이트)
- [ ] B-6. 첫 외부 PR 시나리오 dry-run (테스트 계정 1건)
- [ ] B-7. `CONTRIBUTING.md` 에 CLA 절차 추가
- [ ] B-8. CLA 거절 시 응대 템플릿 작성 (`.github/ISSUE_TEMPLATE/` 또는 PR template)

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
- [ ] G-1. 본 핸드오버를 `CLAUDE.md` 의 "Where to look next" 표에 추가
- [ ] G-2. `ROADMAP.md` v0.3 섹션에 CLA / 라이선스 항목 반영
- [ ] G-3. PR 라벨 `architecture`, `license`, `cla` 정의 (없으면 생성)

---

## 2. Track A — 라이선스 결정 후속 (세부)

### A-1. 라이선스 의사결정 확정

현재 상태: `LICENSE` = MIT, `CONTRIBUTING.md` 도 MIT 명시.

검토할 선택지:

| 선택지 | 장점 | 단점 | 권고 시점 |
|---|---|---|---|
| **MIT 유지** | 채택 마찰 최소, 기여자 부담 0 | 상업 포크 대응 수단 없음 | v0.3 단계 권고(기본값) |
| **듀얼: MIT + AGPL-3.0** | 클라우드 재호스팅 방지 옵션 | 라이선스 매트릭스 복잡 | v0.4 Vertical Product 진입 후 |
| **BSL → 변환** | 시한부 상업 제한 가능 | OSI 미인정, 커뮤니티 거부감 | 비권고 (`docs/ARCHITECTURE.md` 비목표와 충돌 가능) |

**Recommendation**: v0.3 진입 시점에는 **MIT 유지**. 듀얼 전환은
v0.4 First Domain Pilot 이후 외부 상업 사용 패턴이 보인 뒤 재논의.
의사결정은 `docs/ARCHITECTURE.md` 의 PR로 기록 (label: `architecture`).

**완료 조건**: `LICENSE` 파일이 그대로(MIT) 또는 변경(듀얼)되었고,
변경 시 GitHub Repo Settings → License 메타데이터도 갱신됨.

### A-2. `LICENSE` 파일 최종 검토

- [ ] 저작권 보유자가 `Hashevolution` 인지 확인 (현재 OK)
- [ ] 연도가 `2026` 인지 확인 (현재 OK)
- [ ] 듀얼 전환 시 `LICENSE-MIT` / `LICENSE-AGPL` 분리 + 루트
      `LICENSE` 는 dispatch 안내문으로 교체

### A-3. `NOTICE` 파일 신설

목적: 외부 기여자가 늘어날 때 저작권 보유자 명단을 한 곳에서
관리하기 위함. CLA가 발효된 후부터 의미가 있음 — Track B와 연결.

```
PROJECT JAMES
Copyright 2026 Hashevolution
Copyright 2026-present Contributors (see git log + CLA records)

This product includes software developed at Hashevolution.
```

### A-4. `THIRD_PARTY_LICENSES.md`

`requirements_pinned.txt` 기반으로 의존성별 라이선스 인벤토리.
자동 생성 도구(`pip-licenses`)로 1회 캡처하고 PR에 첨부.

명령(사용자 액션 아님 — Claude 가 실행):
```
pip install pip-licenses
pip-licenses --format=markdown --with-urls > THIRD_PARTY_LICENSES.md
```

### A-5. 소스 파일 헤더 정책

현재 `core/`, `processors/` 등 대부분 파일에 라이선스 헤더 없음.
선택지:

- (a) 헤더 강제 — black/ruff 와 별개 검사 추가
- (b) 헤더 생략 + `LICENSE` 루트 1회로 충분 (MIT 통례)

**Recommendation**: (b) 유지. MIT 는 루트 LICENSE 만으로 법적
충분성 확보됨. 헤더 추가는 v1.0 SDK 공개 시점에 재검토.

### A-6. README 라이선스 섹션 정합성

- [ ] `README.md` 끝부분 라이선스 섹션이 `MIT` 명시 + `LICENSE`
      파일 링크인지 확인
- [ ] `README.ko.md` 동일 확인
- [ ] `README.beginner.ko.md` 동일 확인
- [ ] 듀얼 전환 시 3개 파일 모두 갱신 (놓치기 쉬움)

### A-7. CONTRIBUTING.md 라이선스 동의 문구

현재 (`CONTRIBUTING.md` L310-L312):
```
By contributing, you agree that your contributions will be licensed
under the [MIT License](LICENSE).
```

이 문구는 CLA 가 도입되면 다음으로 교체:
```
By contributing, you agree to the terms of the
[Contributor License Agreement](CLA.md) and that your contributions
will be licensed under the [MIT License](LICENSE).
```

Track B-2 에서 `CLA.md` 가 만들어진 뒤에 같이 갱신.

### A-8. `SECURITY.md` 책임 한정 문구

라이선스 결정과 직접 충돌하지 않으나, MIT 의 "AS IS" 면책 조항과
중복/모순이 없는지 1회 검토. 변경 없을 가능성 높음.

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

Apache ICLA(Individual) v2.2 를 베이스로 JAMES 용도로 축약.
별도 `docs/legal/CLA.md` 위치 권고 (루트 오염 방지).

핵심 조항(요지):

1. **저작권 라이선스 부여** — Hashevolution 에 영구 / 무상 /
   재라이선스 가능한 권리 부여
2. **특허 라이선스 부여** — 기여물에 포함된 특허에 대한 무상 사용권
3. **원본 진술** — 기여물이 본인 저작이거나 권리 보유자임 진술
4. **고용주 권리** — 고용주 권리 충돌 시 본인 책임 명시
5. **No warranty** — 기여물은 "AS IS"

Corporate CLA(CCLA) 는 v0.4 First Domain Pilot 시점에 추가.

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
license: "MIT"
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
