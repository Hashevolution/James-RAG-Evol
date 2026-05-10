# Session 2026-05-09 — Promotion Readiness

> 외부 홍보 / GeekNews 초안 / Awesome list 등록 / OpenSSF Best Practices Badge
> 작업 브랜치: `claude/promotion-readiness-sPBPQ`
> 작성일: 2026-05-10

---

## 0. Master Roadmap (체크리스트)

진행 상황은 항상 이 체크리스트로 표시합니다. 한 항목을 마칠 때마다 `[ ]` → `[x]`로 바꿉니다.

```
[x] Phase 0  착수 준비
     [x] 0-1  브랜치 생성 (claude/promotion-readiness-sPBPQ)
     [x] 0-2  세션 문서 초안 작성

[ ] Phase 1  외부 홍보 전략 수립
     [ ] 1-1  타깃 채널 후보 확정
     [ ] 1-2  공통 홍보 자료(스니펫·스크린샷·핵심 메시지) 준비
     [ ] 1-3  공개 일정 표 작성 (어떤 채널에 며칠 간격으로)

[ ] Phase 2  GeekNews 초안 + 제출
     [ ] 2-1  GeekNews 계정 가입 / 로그인
     [ ] 2-2  초안 다듬기 (제목·본문·태그)
     [ ] 2-3  제출 (글쓰기 → 검토 → 등록)
     [ ] 2-4  댓글 모니터링 / 답변 (24~72시간)

[ ] Phase 3  Awesome List 등록
     [ ] 3-1  후보 awesome 리포지토리 5종 확정
     [ ] 3-2  각 리포의 CONTRIBUTING 규칙 확인 (한 줄 형식)
     [ ] 3-3  본인 GitHub에서 fork → 브랜치 → 한 줄 추가 → PR
     [ ] 3-4  PR 1개씩, 리뷰 코멘트 대응

[ ] Phase 4  OpenSSF Best Practices Badge (passing)
     [ ] 4-1  bestpractices.dev 가입 (GitHub OAuth)
     [ ] 4-2  프로젝트 등록 (URL 입력)
     [ ] 4-3  passing 18개 카테고리 자가 평가
     [ ] 4-4  미흡 항목 보완 (문서/테스트/공개 정책)
     [ ] 4-5  최종 제출 → 통과 시 README에 뱃지 추가

[ ] Phase 5  세션 문서 커밋 · 푸시
     [ ] 5-1  reports/session-2026-05-09-promotion-readiness.md 커밋
     [ ] 5-2  origin/claude/promotion-readiness-sPBPQ 푸시
```

---

## Phase 1 — 외부 홍보 전략 수립

목표: **"무엇을, 어디에, 어떤 톤으로"**를 한 페이지로 정리. 채널마다 같은 글을 그대로 복붙하지 않고, 각 커뮤니티 톤에 맞춰 변형 발행.

### 1-1. 타깃 채널 후보 (권장 우선순위)

| # | 채널 | 형식 | 우선순위 | 톤 |
|---|------|------|--------|-----|
| 1 | GeekNews (news.hada.io) | 한국어 단신 + 댓글 토론 | **즉시** | 담백 / 장단점 솔직 |
| 2 | Hacker News (news.ycombinator.com) | 영문 Show HN | 1주 후 | 기술적 / 자랑 X / 한계 명시 |
| 3 | Reddit r/LocalLLaMA, r/selfhosted | 영문 / 스크린샷 환영 | 2주 후 | 데모·실사용 사례 중심 |
| 4 | Awesome List PRs | 한 줄 등록 | Phase 3 | 객관적 description |
| 5 | OpenSSF Badge | 메타 신호 | Phase 4 | 자가 평가 + 증빙 |
| 6 | Lobsters (lobste.rs, 초대 필요) | 영문 | 보류 | 초대 받을 때만 |
| 7 | LinkedIn / Twitter(X) | 짧은 글 + 링크 | 보조 | 1줄 후크 + 링크 |

> 처음이라면 **GeekNews 1곳부터 발행**하고 댓글 반응을 보면서 톤을 보정한 뒤 Hacker News로 넘어가는 게 안전합니다. 한 번에 다 던지면 같은 비판이 여러 곳에서 겹쳐 대응이 어렵습니다.

### 1-2. 공통 홍보 자료 — 미리 준비해 둘 것

아래 자료를 한 번 만들어두면 모든 채널에서 재사용할 수 있습니다.

- [ ] **한 줄 설명 (영/한 각 1개)**
  - 한: "보안을 1순위로 설계한, 노트북에서 돌아가는 Graph-RAG 지식 엔진. 추론 경로와 자가진화 스캐폴드를 노출."
  - 영: "Security-first, locally-runnable Graph-RAG knowledge engine with explicit reasoning paths and a self-evolution scaffold."
- [ ] **3줄 요약 (한/영)**
  - 무엇이 다른가 / 누구를 위한 건가 / 현재 단계(alpha) — README의 "What's Different" 섹션을 그대로 활용.
- [ ] **스크린샷 3장**
  - (a) Web UI 검색 결과 화면 (Reasoning path가 보이는 컷)
  - (b) Graph 뷰 또는 ontology 관계 예시
  - (c) Security 흐름 다이어그램 (README의 ASCII 박스를 PNG로 export)
- [ ] **30초 데모 GIF 1개** (선택, 있으면 강력)
  - macOS: Kap / Linux: Peek / Windows: ScreenToGif
  - 800px 너비 이하, 5MB 미만 (GitHub 업로드 제한)
- [ ] **공통 링크 묶음**
  - GitHub: `https://github.com/Hashevolution/James-RAG-Evol`
  - README(한): `README.ko.md`
  - SECURITY.md / ROADMAP.md / CONTRIBUTING.md
  - LICENSE: MIT

### 1-3. 공개 일정 (예시)

| 일자 | 채널 | 액션 |
|-----|------|-----|
| D+0 (오늘) | GeekNews | Phase 2 초안으로 제출 |
| D+1~3 | GeekNews | 댓글 답변 (질문/지적 대응) |
| D+3 | Awesome List | Phase 3에서 PR 1개 시작 |
| D+7 | Hacker News | 한국 시간 23:00~01:00 (PST 오전 6~8시) "Show HN" |
| D+14 | r/LocalLLaMA | 사용 예시 + GIF 게시 |
| 상시 | OpenSSF Badge | Phase 4 진행, 통과 시 발표 |

### Phase 1 완료 조건
- 위 자료 5종이 한 폴더(예: `reports/promo-assets/`)에 모여 있고, 일정표가 확정되어 있다.

---

## Phase 2 — GeekNews 초안 + 제출

GeekNews는 한국 개발자 대상 단신 + 토론 사이트 (news.hada.io). 자기 프로젝트 홍보가 허용되지만, **과장하면 댓글에서 바로 지적**됩니다. 톤은 **담백 + 솔직**이 정답입니다.

### 2-1. 계정 가입 — 처음 해보는 사람용 단계별

1. 브라우저에서 `https://news.hada.io` 접속.
2. 우측 상단 "로그인" 클릭.
3. 계정이 없다면 "회원가입" 클릭.
4. 이메일 + 닉네임 + 비밀번호 입력. (닉네임은 댓글에 노출되니 평소 쓰는 핸들 추천)
5. 등록 후 메일함에서 확인 메일 클릭.
6. 다시 로그인. 우측 상단 닉네임이 보이면 OK.

### 2-2. 초안 — 그대로 복붙 가능

> 제목, 본문, 태그를 따로 적었습니다. 본문은 GeekNews 마크다운(거의 GFM 호환)을 가정.

#### 제목 (택1)

- (A) `JAMES — 보안을 1순위로 설계한 로컬 Graph-RAG 엔진 (오픈소스, alpha)`
- (B) `노트북에서 도는 Graph-RAG + 보안 3-stage + 자가진화 스캐폴드 (MIT)`

> 추천: **(A)**. "오픈소스 / alpha"를 제목에 박아 두면 과대광고로 안 읽힙니다.

#### 본문 초안 (markdown)

```markdown
## 한 줄 요약
보안을 디자인 원칙으로 다룬, 100% 로컬에서 도는 Graph-RAG 지식 엔진.
추론 경로(Reasoning Path)와 자가진화 스캐폴드(Patch Pipeline)가 노출돼 있습니다.

- GitHub: https://github.com/Hashevolution/James-RAG-Evol
- 현재 버전: v0.1.0 (alpha, research stage)
- 라이선스: MIT

## 무엇이 다른가 (다섯 가지가 한 곳에)
1. **Graph-RAG + ontology**: 12종 관계 타입으로 임베딩 너머의 의미를 표현
2. **3-stage 보안**: RBAC + ABAC + Instruction Isolation (벡터 → 그래프 → 출력)
3. **자가진화 스캐폴드**: 피드백 → 패치 제안 → 4-Gate 검증 → 적용
4. **Personality 11 traits**: 응답 톤이 가변
5. **100% 로컬**: Ollama 기반, GPU 없으면 gemma2:2b로 시작 가능

## 솔직한 한계 (alpha 단계)
- 아직 합성 데이터 위주 검증, 실데이터 검증은 v0.2 목표
- 멀티모달은 훅만 들어가 있음 (LLaVA/Whisper 통합 진행 중)
- 자가진화는 스케일 검증 안 됨

## 어디에 쓸 수 있나
- 사내 위키/문서를 로컬에서만 다루고 싶을 때
- 추론 경로가 보여야 하는 RAG 데모/연구
- 보안 RAG 패턴 레퍼런스

## 시작하기
git clone, .env 설정, `pip install -r requirements.txt`, `ollama pull gemma2:2b`,
`python server_llmwiki.py` → http://localhost:8000

피드백/이슈 환영합니다. 특히 보안 모델과 자가진화 부분에 대한 반론이 가장 도움이 됩니다.
```

#### 태그 (GeekNews 권장 5개 이하)

`RAG`, `GraphRAG`, `오픈소스`, `보안`, `로컬LLM`

### 2-3. 제출 절차 — 단계별

1. `https://news.hada.io` 로그인 상태 확인.
2. 상단 메뉴의 **"글쓰기"** 또는 우측 상단 **+** 아이콘 클릭.
3. 입력 폼이 나오면:
   - **제목**: 위 (A) 또는 (B) 복붙.
   - **링크 URL**: `https://github.com/Hashevolution/James-RAG-Evol`
     (외부 링크 + 본인 코멘트 형식이 GeekNews 표준)
   - **본문**: 위 markdown 초안 복붙. 미리보기 탭으로 한 번 확인.
   - **태그**: `RAG, GraphRAG, 오픈소스, 보안, 로컬LLM`
4. **미리보기** 한 번 더. 줄바꿈/링크 깨짐 확인.
5. **등록** 클릭.
6. 등록 직후 자기 글 페이지로 이동. URL을 어디 메모해 두세요 — 모니터링용.

### 2-4. 등록 후 24~72시간 — 댓글 대응 가이드

- **부정적 코멘트는 빠르게(2~6시간 내), 사실로**: "이건 아직 alpha라 그렇습니다", "재현 코드 알려주시면 이슈로 받겠습니다" 식.
- **자랑성 답변 금지**: 한계를 더 깊이 인정하면 오히려 신뢰가 올라갑니다.
- **이슈 트래커로 유도**: 버그성 지적은 "GitHub 이슈로 올려주시면 트래킹하겠습니다."
- **삭제·수정 자제**: 본인 글에 다는 댓글은 즉답하되, 본문을 사후 편집해 비판 맥락을 지우지 마세요. 커뮤니티 신뢰가 깨집니다.

### Phase 2 완료 조건
- GeekNews에 글이 등록되었고, URL을 본 문서 하단의 "공개 결과" 섹션에 기록.
- 첫 24시간 댓글에 1회 이상 응답.

---

## Phase 3 — Awesome List 등록

awesome 리스트는 GitHub 위에서 운영되는 큐레이션 리포입니다. **한 줄 설명 + 링크**만 추가하는 PR을 보내면 끝. 처음 해보는 분이 가장 막막한 부분이 "fork → 브랜치 → 편집 → PR"의 흐름이라, 이 절차를 그대로 풀어 적습니다.

### 3-1. 후보 awesome 리포 (5종 권장)

| # | 리포 | 적합도 | 추가될 섹션 (예측) |
|---|------|------|------|
| 1 | `Hannibal046/Awesome-LLM` | ★★★ | "Open-Source LLM Frameworks" 또는 "RAG" |
| 2 | `awesome-selfhosted/awesome-selfhosted` | ★★★ | "Knowledge Management" |
| 3 | `frutik/awesome-knowledge-graphs` 또는 유사 KG 리스트 | ★★ | "Tools" |
| 4 | `eugeneyan/applied-ml` 류의 RAG 섹션이 있는 리스트 | ★★ | RAG 도구 |
| 5 | `mahseema/awesome-ai-tools` 류 종합 리스트 | ★ | 보조 |

> 정확한 리포 이름은 PR 직전에 GitHub에서 검색해 최신 리포로 확인하세요. awesome 리스트는 메인테이너가 바뀌거나 리포가 옮겨질 때가 잦습니다. 검색 쿼리 예: `awesome rag`, `awesome graph rag`, `awesome local llm`.

### 3-2. 한 줄 엔트리 (복붙 템플릿)

awesome 리스트는 보통 다음 형식을 따릅니다:

```
- [Project Name](URL) - One sentence description, no period at the end if list rule says so. `License`
```

JAMES용 한 줄:

```
- [JAMES](https://github.com/Hashevolution/James-RAG-Evol) - Security-first, locally-runnable Graph-RAG engine with ontology, 3-stage access control (RBAC+ABAC+instruction isolation), and a self-evolution scaffold. `MIT`
```

> 각 리포의 `CONTRIBUTING.md` 또는 README 상단의 "How to contribute"를 먼저 읽고 **마침표/대문자/순서**를 그 리포 규칙에 맞춰 조정하세요. (예: 알파벳 순 유지, 한 문장에 마침표 금지 등)

### 3-3. PR 보내기 — 처음부터 끝까지

대상 리포가 `Hannibal046/Awesome-LLM`이라고 가정합니다. 다른 리포도 같은 흐름.

#### 3-3-1. fork

1. 브라우저에서 `https://github.com/Hannibal046/Awesome-LLM` 접속.
2. 우상단 **Fork** 버튼 클릭 → "Create fork" → 본인 계정으로 fork 생성.
3. 본인 계정의 fork URL 메모. 예: `https://github.com/<your-username>/Awesome-LLM`

#### 3-3-2. 로컬에 클론하고 브랜치 만들기

본인의 작업 디렉터리(예: `~/work`)에서:

```bash
cd ~/work
git clone https://github.com/<your-username>/Awesome-LLM.git
cd Awesome-LLM
git checkout -b add-james-rag-evol
```

> 브랜치 이름은 `add-<프로젝트>` 컨벤션이 가장 무난.

#### 3-3-3. 파일 편집

1. README.md 또는 (대형 리포는) 카테고리별 파일을 엽니다.
2. 알맞은 섹션(예: "RAG", "Open-Source Frameworks")을 찾습니다.
3. **알파벳 순서**가 규칙이면 J 위치에 끼워 넣고, 그렇지 않으면 섹션 마지막 줄에 추가.
4. 위 3-2의 한 줄 엔트리를 그대로 붙여 넣습니다.
5. 저장.

#### 3-3-4. 커밋 + 푸시

```bash
git add README.md
git commit -m "Add JAMES — security-first Graph-RAG engine"
git push -u origin add-james-rag-evol
```

#### 3-3-5. PR 열기

1. push 후 터미널에 출력되는 GitHub URL을 클릭하거나, 브라우저에서 본인 fork 페이지로 이동.
2. "Compare & pull request" 노란 배너 클릭.
3. 폼이 열리면:
   - **Base**: 원본 리포(예: `Hannibal046/Awesome-LLM`)의 `main` 또는 `master`.
   - **Compare**: 본인 fork의 `add-james-rag-evol`.
   - **Title**: `Add JAMES — security-first Graph-RAG engine`
   - **Body**: 아래 템플릿 복붙.
4. "Create pull request" 클릭.

#### 3-3-6. PR 본문 템플릿

```markdown
Hi maintainers, this PR adds **JAMES**, an open-source (MIT) Graph-RAG knowledge engine.

- Repository: https://github.com/Hashevolution/James-RAG-Evol
- License: MIT
- Status: v0.1.0-alpha (research stage; honestly disclosed in README)

Why I think it fits this list:
- Built around RAG with a graph + ontology layer (12 relation types).
- Security model is explicit: RBAC + ABAC + instruction isolation + audit log.
- 100% locally runnable via Ollama.

I followed the contributing guide:
- [ ] Alphabetical order respected
- [ ] One-line description, no marketing language
- [ ] License tag included
- [ ] Link verified

Thanks for maintaining this list!
```

### 3-4. PR 후 흐름

- 자동 CI(링크 체크 등)가 돌면 통과 확인.
- 메인테이너 코멘트는 보통 **수일 ~ 수 주**. 재촉 금지.
- 수정 요청이 오면 같은 브랜치에 새 커밋을 push → PR이 자동 갱신.
- 머지되면 본 문서 하단 "공개 결과"에 PR URL 기록.

### Phase 3 완료 조건
- 최소 1개 PR이 머지되고, 추가로 2~4개 PR이 진행 중.

---

## Phase 4 — OpenSSF Best Practices Badge (passing)

OpenSSF Best Practices Badge는 오픈소스 프로젝트가 **최소한의 보안·품질 모범사례**를 따르는지 자가 평가해 받는 뱃지입니다. URL은 `https://www.bestpractices.dev/` (구 bestpractices.coreinfrastructure.org).

세 등급(passing → silver → gold)이 있고, **passing부터 노립니다**. passing은 약 60~80개 항목이지만 대부분 "이미 README/SECURITY.md/CONTRIBUTING.md에 적혀 있으면 통과"입니다.

### 4-1. 가입 + 프로젝트 등록

1. `https://www.bestpractices.dev/` 접속.
2. 우상단 **Login** 또는 **Sign up** 클릭.
3. **GitHub OAuth** 사용 권장 — 본인 GitHub 계정으로 로그인 → 권한 허용.
4. 로그인 후 우상단 **"Get your project's badge"** 또는 **"+ Add"** 클릭.
5. 폼:
   - **Project home page URL**: `https://github.com/Hashevolution/James-RAG-Evol`
   - **Project repository URL**: 같은 값.
   - **Description**: 영문 한 줄(=Phase 1-2의 영문 한 줄 그대로).
6. "Submit" 클릭.

### 4-2. 자가 평가 — passing 핵심 항목과 현재 상태

> 각 질문에 `Met / Unmet / Not applicable / ?` 중 하나를 선택. 가능하면 **각 답변 옆 "URL/explanation" 칸에 GitHub 링크를 붙여 증빙**해야 통과율이 높습니다.

#### Basics

| # | 항목 | 현재 상태(추정) | 증빙 (붙여 넣을 링크) |
|---|------|----------------|--------------------|
| 1 | 프로젝트 웹사이트 존재 | Met | 리포 README |
| 2 | OSS 라이선스 (FSF/OSI 승인) | Met | `LICENSE` (MIT) |
| 3 | 라이선스가 표준 위치에 있음 | Met | `LICENSE` |
| 4 | 문서: 사용자용 / 기여자용 | Met | `README.md`, `CONTRIBUTING.md` |
| 5 | 공개 버전 관리 | Met | GitHub |
| 6 | 변경 이력 / CHANGELOG | Met | `CHANGELOG.md` |
| 7 | 버그 리포팅 절차 공개 | Met | GitHub Issues + `CONTRIBUTING.md` |
| 8 | 취약점 신고 절차 공개 | Met | `SECURITY.md` |

#### Change control / Reporting

| # | 항목 | 보완 필요 여부 |
|---|------|--------------|
| 9 | 공개 이슈 트래커 | Met (GitHub Issues) |
| 10 | 1회 이상의 릴리스 | Met (v0.1.0-alpha) |
| 11 | 릴리스 노트 / changelog | Met |
| 12 | 보안 신고 비공개 채널 (이메일 등) | **확인 필요** — `SECURITY.md`에 이메일 또는 비공개 채널 명시되어 있는지 점검 |

#### Quality

| # | 항목 | 보완 필요 여부 |
|---|------|--------------|
| 13 | 빌드/테스트 절차 문서화 | Met (README의 Quick Start) |
| 14 | 자동화 테스트 존재 | Met (`james_*_test.py`) |
| 15 | 새 기능에 대한 테스트 추가 정책 | **명시 필요** — `CONTRIBUTING.md`에 한 줄 추가 권장 |
| 16 | 경고 없는 빌드 / lint | **확인 필요** |

#### Security

| # | 항목 | 보완 필요 여부 |
|---|------|--------------|
| 17 | 개발자가 보안 안전 코딩을 안다는 증거 | Met (`SECURITY.md` + 보안 모델 문서화) |
| 18 | 표준 암호화 사용 (있다면) | Met (`cryptography` 47.x 사용) |
| 19 | TLS 사용 권장 / HTTPS 디폴트 (있다면) | Roadmap v1.0에 적힘 — 현재는 "applicable when relevant" 처리 |
| 20 | 알려진 취약점 부재 | Met (의존성 최신화 — PR #9 참고) |

> 위 표에서 **"확인 필요"** 표시된 4-5개 항목만 보완하면 passing은 충분히 노릴 수 있는 상태입니다.

### 4-3. 미흡 항목 보완 — 구체 작업

#### A. `SECURITY.md`에 비공개 보안 신고 채널 명시

`SECURITY.md` 상단에 다음 류의 한 단락이 있는지 확인. 없으면 추가:

```markdown
## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security problems.
Instead, email <security-contact@example.com> with:
- A description of the issue and reproduction steps
- The affected version/commit hash
- Your suggested severity

We aim to acknowledge within 72 hours and provide a remediation plan within 14 days.
```

(이메일은 본인이 운영하는 주소로 교체)

#### B. `CONTRIBUTING.md`에 테스트 정책 한 줄

```markdown
## Tests

New features and bug fixes should include or update tests under `test/`
or the `james_*_test.py` suites. PRs without tests may be asked to add them.
```

#### C. CI lint/test 상태 뱃지 (선택, 신뢰도↑)

GitHub Actions 워크플로 1개라도 돌고 있으면 README 상단에 추가:

```markdown
[![CI](https://github.com/Hashevolution/James-RAG-Evol/actions/workflows/<workflow-file>.yml/badge.svg)](https://github.com/Hashevolution/James-RAG-Evol/actions)
```

### 4-4. 제출 절차

1. `https://www.bestpractices.dev/projects/<your-project-id>` 페이지로 이동 (등록 직후 자동 이동).
2. 항목별로 **Met / Unmet / Not applicable / ?** 라디오 클릭.
3. 각 Met 항목 아래 "Justification (URL recommended)" 칸에 **GitHub 영구 링크**(특정 커밋 hash로) 또는 파일 URL 첨부.
4. 페이지 하단 자동 저장됨. 한 번에 다 못 채워도 됩니다.
5. 모든 항목이 Met 또는 N/A가 되면 페이지 상단 진행률 바가 100%가 됩니다.
6. **Submit** (혹은 자동 통과) → 뱃지 마크다운 스니펫이 발급됩니다.

### 4-5. 통과 후 — README에 뱃지 추가

발급된 스니펫(예시 형식)을 README 최상단 뱃지 줄에 추가:

```markdown
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/<id>/badge)](https://www.bestpractices.dev/projects/<id>)
```

> `<id>`는 본인 프로젝트 페이지에 표시되는 정수. 발급된 마크다운을 그대로 복붙하는 게 안전합니다.

### Phase 4 완료 조건
- bestpractices.dev에서 passing(녹색) 표시.
- README 상단 뱃지 라인에 OpenSSF 뱃지 노출.
- 본 문서 "공개 결과"에 프로젝트 ID 기록.

---

## 공개 결과 (진행에 따라 채워 넣기)

| 채널 | 상태 | URL | 비고 |
|-----|------|-----|------|
| GeekNews | (예정) | | 발행일 기록 |
| Hacker News | (예정) | | D+7 이후 |
| r/LocalLLaMA | (예정) | | D+14 이후 |
| Awesome-LLM PR | (예정) | | |
| Awesome-Selfhosted PR | (예정) | | |
| OpenSSF Badge | (예정) | | passing 도달 시 ID |

---

## 부록 — 자주 막히는 지점 FAQ

**Q. fork 후에 원본 리포가 업데이트되면 어떻게 따라가나요?**
A. 본인 fork 디렉터리에서:
```
git remote add upstream https://github.com/<원본>/<리포>.git
git fetch upstream
git checkout main && git merge upstream/main
git push origin main
```

**Q. PR 후 conflict가 났습니다.**
A. 같은 브랜치에서 `git pull --rebase upstream main` → conflict 수동 해결 → `git add .` → `git rebase --continue` → `git push --force-with-lease`. (단, 본인 작업 브랜치만. main에는 절대 force push 금지.)

**Q. GeekNews가 너무 조용한데요?**
A. 평일 오전 9~11시, 또는 오후 8~10시 발행이 노출률이 높습니다. 발행 시간을 바꿔서 1주 후 후속글(예: "1주 후 후기")로 한 번 더 노출하는 패턴이 흔합니다.

**Q. OpenSSF passing이 너무 어렵습니다.**
A. "확인 필요" 4~5개를 한 번에 다 채우려 하지 말고, 항목별로 1~2일에 한 묶음씩 처리. 자가 평가는 저장이 됩니다. 80% 채워두고 나머지를 별도 PR로 진행해도 됩니다.

---

**Last updated**: 2026-05-10
