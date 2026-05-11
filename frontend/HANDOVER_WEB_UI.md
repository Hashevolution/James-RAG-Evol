# Web UI — Dark Concept Refresh 핸드오버

**최종 업데이트**: 2026-05-11
**브랜치**: `claude/review-dark-ui-concept-Aydvd`
**원격**: `origin/claude/review-dark-ui-concept-Aydvd` (push 완료)
**커밋**: `e686844` (토큰 통합), `508f880` (브랜드 라벨 교체)
**대상**: 다른 세션에서 작업을 이어갈 Claude (또는 본인)

---

## 0. TL;DR

- v0.1 시절의 dark 컨셉을 점검하고, **공통 디자인 토큰 단일화** + **UI 브랜드 라벨 교체** 두 PR을 한 브랜치에 쌓았다.
- 코드네임 **JAMES는 내부에만 존속**하고, UI 표면은 모두
  **"Secure Enterprise Knowledge Operating System"** 으로 표시한다.
- 아직 main으로 머지되지 않았다. 머지 전 시각 검증 필요.

---

## 1. 이번 브랜치에서 끝난 일

### 1-1. 커밋 `e686844` — `refactor(frontend): unify dark-UI tokens into static/tokens.css`

배경: `index.html` 만 최신 `#A8-9` 폴리시(deeper navy bg, deeper
indigo accent, intelligence-cyan brand-2, shadow-card)를 가지고
있었고 `admin / workspace / graph` 는 옛 neutral-dark 팔레트에
멈춰 있어서 페이지 이동 시 톤이 미세하게 흔들렸다.

변경:

- 신규 파일 `frontend/static/tokens.css` — 디자인 토큰 단일 출처
  - Google Fonts `@import`, 유니버설 box-sizing 리셋, `:root` 토큰
  - 통합 팔레트(`#A8-9` 기반): `--bg #0a0c11`, `--surface #131620`,
    `--accent #5258e6`, `--brand-2 #4fc3f7`, `--shadow-card …` 외
- 4개 HTML(`index / admin / workspace / graph`)의 인라인 `:root`
  블록 제거, `<link rel="stylesheet" href="/static/tokens.css">` 연결
- `<meta name="theme-color">` 4페이지 모두 `#0a0c11` 통일
- `graph.html` 은 그래프 전용 `--t-person / --t-org / --t-concept /
  --t-document` 4개 토큰만 인라인으로 보존(도메인-중립이라 두어도 됨)
- 순변경: **+69 / −112** 라인

### 1-2. 커밋 `508f880` — `refactor(brand): replace UI "JAMES" labels with full positioning line`

배경: 사용자 지시 — UI 표면에서 "제임스"를 빼고
"Secure Enterprise Knowledge Operating System" 을
표시한다.

변경:

- 4페이지 `<title>` — 풀 문구 + 페이지명 접미사
  (`— Admin / — Workspace / — Reasoning Graph`)
- 4페이지 `.logo` 헤더 — `tokens.css` 에 `.brand` 컴포넌트 추가
  (메인 라인 + muted 톤 "Operating System" tail, 900/640px 반응형)
- 챗 환영 타이틀(`welcome-title`)
- admin / graph 로그인 모달 상단의 `▸ JAMES ADMIN` / `▸ JAMES GRAPH`
  배너 → 풀 문구로 교체
- i18n 키 갱신
  - `app.name` → 풀 문구 (en / ko 양쪽)
  - `chat.title` → "Secure …, Operating System — Security Reasoning Engine"
  - `auth.login_title` → `Login` / `로그인`
  - `auth.signup_title` → `▸ Signup` / `▸ 회원가입`
- admin 페르소나 이름 입력의 `data-i18n-placeholder="app.name"` 제거
  (그대로 두면 이름 필드 placeholder 에 풀 문구가 들어가 깨짐).
  static `placeholder="JAMES"` 만 남겨 페르소나 기본값 보존.

---

## 2. 의도적으로 그대로 둔 JAMES 참조

다음은 **브랜드 라벨이 아닌** 영역이라 손대지 않았다. 다른 세션이
"덜 지운 거 아닌가?" 싶을 때 이걸 보면 된다.

| 항목 | 이유 |
|---|---|
| `JAMES_API_KEY` env-var + `auth.api_key_hint/prompt` | 환경변수명 |
| `placeholder="JAMES"` (admin 페르소나 이름) | 에이전트 자기소개 기본값 |
| `set.persona_*`, `char.identity_name_desc` | 페르소나(별개 개념) |
| `hw.description` ("Hardware running JAMES intelligence") | 시스템 설명 |
| `msg.summary_failed / done` ("[JAMES] …") | 시스템 메시지 prefix |
| `graph.query.ph` ("Ask JAMES…") | 챗 에이전트 호칭 |
| HTML 주석, 코드 식별자, 파일명 | 코드베이스 정체성은 JAMES 그대로 |

> CLAUDE.md 원칙: **저장소 코드네임은 JAMES, 공개 UI 라벨만 교체.**

---

## 3. 결정사항 / 디자인 규칙 메모

1. **단일 토큰 출처**: 새 디자인 토큰은 `frontend/static/tokens.css`
   에만 정의한다. 페이지별 인라인 `:root` 재정의 금지. 페이지 전용
   토큰은 `graph.html` 의 `--t-*` 처럼 그 페이지에 인라인 augment.
2. **브랜드 표기**: `.brand` 컴포넌트(`Operating System` tail muted 톤)
   사용. 새 화면을 만들 때는 같은 클래스 재사용. 새 텍스트 추가 시
   직접 "JAMES" 라고 쓰지 말 것.
3. **i18n**: `app.name` 은 풀 문구. 좁은 영역(placeholder 등)에 풀
   문구가 들어가지 않도록 신규 키를 만들 것 — `app.name` 재사용 금지.
4. **theme-color**: `#04060a` 으로 통일 (Task #22 mono-cyber bg).
5. **반응형 분기**: `.brand` 가 900px → 11px, 640px → 자동 줄바꿈.
   이 규칙이 부족하면 `tokens.css` 의 `@media` 두 블록만 수정.
6. ~~**legacy 미정의 토큰**: `admin.html` 에 `var(--accent2 / --bg2 /
   --card / --fg)` 호출이 남아 있다.~~ **DONE** (브랜치
   `chore/v0.2-legacy-tokens` 에서 `--accent2 → --brand-2`,
   `--fg → --text`, `--bg2 → --surface-2`, `--card → --surface-2`
   로 일괄 치환).

---

## 4. 다음에 할 일 (우선순위)

이번 브랜치 머지 후 같은 브랜치 또는 별도 브랜치에서 이어갈 수 있는 항목.
`HANDOVER_WEB_UI.md` 이전 버전의 5-우선순위 중 1번이 끝났고, 나머지가 남았다.

| # | 작업 | 예상 | 비고 |
|---|---|---|---|
| 1 | ~~CSS 추출 + 공통 토큰~~ | — | **DONE** (커밋 `e686844`) |
| 2 | 반응형 — `admin / workspace / graph` 용 mobile.css 확장 | 2~3h | 현재 `mobile.css` 는 chat 페이지 전용 |
| 3 | 추론 패널 강화 — retrieve → expand → verify timeline + 인용 노드 + 신뢰도 bar + sensitivity 배지 | 4~6h | Graph-RAG 차별점 시각화 |
| 4 | 접근성 패스 — modal `role="dialog"` + focus trap + ESC, `aria-label`, `--muted-2` 대비 감사 (AA ~3.4:1 미달 가능) | 2h | |
| 5 | 인라인 핸들러(`onclick=…`) → 이벤트 위임 + `data-action` | 3h | CSP 강화 대비 |
| 6 | ~~`admin.html` legacy 미정의 토큰(`--accent2 / --bg2 / --card / --fg`) 정리~~ | — | **DONE** (브랜치 `chore/v0.2-legacy-tokens`) |
| 7 | ~~상단 그라데이션 레일(`body::before`)을 4페이지 공통화~~ | — | **DONE** (브랜치 `feat/v0.2-gradient-rail-common`) |
| 8 | 인라인 `<style>` 블록 완전 분리 — `static/styles.css` | 4h | `index.html` 615줄 / `admin.html` 530줄까지 인라인 |

추천 다음 단계: **#3 (추론 패널 강화)** 또는
**#5 (인라인 onclick 제거)** — 둘 다 mid-risk, 4~6h.
가벼운 작업이 더 필요하면 **#8 (인라인 `<style>` 블록 분리)**
부분 착수.

---

## 5. 다음 세션이 시작할 때 해야 할 일

### 5-1. 컨텍스트 복원

```bash
git fetch origin claude/review-dark-ui-concept-Aydvd
git checkout claude/review-dark-ui-concept-Aydvd
git log --oneline -3   # e686844, 508f880 두 커밋이 보여야 함
```

그리고 이 문서(`frontend/HANDOVER_WEB_UI.md`) 와 `CLAUDE.md` 를 읽는다.

### 5-2. 첫 질문 템플릿

```
"`claude/review-dark-ui-concept-Aydvd` 브랜치를 이어받았습니다.

지금까지 끝난 것:
  - 토큰 단일화 (e686844)
  - UI 브랜드 라벨 → "Secure Enterprise Knowledge
    Operating System" 교체 (508f880, 이후 "Intelligence," 제거 단축)

다음 우선순위 (HANDOVER_WEB_UI.md §4):
  2. 반응형 확장 (admin/workspace/graph 용 mobile.css)
  3. 추론 패널 강화
  4. 접근성 패스
  5. 인라인 핸들러 → 이벤트 위임
  6. legacy 미정의 토큰 정리
  7. 상단 그라데이션 레일 공통화
  8. 인라인 <style> 완전 분리

또는 main 으로 머지하시겠습니까? 머지 전 브라우저로
시각 검증을 권장합니다."
```

### 5-3. 머지 전 시각 검증 체크리스트

웹 세션에서는 브라우저로 못 보므로, 사용자에게 다음을 부탁:

```
1. /         (chat)        — 헤더에 풀 문구 + Operating System tail 회색
2. /admin    (admin)       — "· Admin Console" 접미사 함께 보이는지
3. /workspace               — "Workspace · 데이터 + 작업" 함께
4. /graph                   — "Reasoning Graph" 함께
5. 모달 — 로그인/회원가입 타이틀이 "로그인 / 회원가입" 으로만 나오는지
6. 환영 화면 — "Welcome to Secure Enterprise Knowledge
   Operating System"
7. admin → 캐릭터 → Identity 이름 입력 placeholder 가
   풀 문구가 아니라 "JAMES" 인지 (이게 풀 문구면 페르소나 기본값
   바인딩이 잘못된 것)
8. 화면 폭 < 900px — `.brand` 가 11px 로 줄어드는지
9. 화면 폭 < 640px — `.brand` 가 줄바꿈되는지
10. theme-color — 브라우저 탭 상단 색이 #04060a (mono cyber bg) 인지
```

---

## 6. 주의사항 (Gotchas)

- `tokens.css` 는 단일 출처. 새 토큰 추가 시 여기에만. 페이지에
  중복 정의하지 말 것.
- `.brand` 컴포넌트는 `tokens.css` 안에 있다 — "tokens" 라는
  이름과 살짝 안 맞지만, 브랜드 컴포넌트도 시스템-와이드 primitive
  로 취급. 나중에 `static/brand.css` 로 분리해도 됨.
- 브랜치는 `main` 머지 시 PR description 에 **벤치 숫자**는 필요
  없다(`core/retrieval`, `core/graph`, `core/reasoning` 미수정 — CLAUDE.md §2).
- `Closes #N` 은 PR body 에만 쓰고 commit message 에는 쓰지 말 것
  (CLAUDE.md 운영 규칙).
- 자동 머지 금지(브랜드/UI 변경은 trust boundary 가 아니라서 기술적
  으로는 가능하지만, 시각 검증 전엔 수동 머지 권장).

---

## 7. 빠른 요약 카드

```
┌─────────────────────────────────────────────────────────┐
│  Web UI — Dark Concept Refresh                          │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Branch:   claude/review-dark-ui-concept-Aydvd          │
│  Status:   Pushed, awaiting visual verification & merge │
│                                                          │
│  Commits:                                                │
│    e686844  refactor(frontend): unify dark-UI tokens    │
│    508f880  refactor(brand): replace UI "JAMES" labels  │
│                                                          │
│  Brand line (UI only):                                   │
│    "Secure Enterprise Knowledge Operating System"        │
│  Codename JAMES — kept in env vars / persona / code.    │
│                                                          │
│  Files touched:                                          │
│    frontend/static/tokens.css   (new, 86줄)             │
│    frontend/static/i18n.js                              │
│    frontend/index.html                                   │
│    frontend/admin.html                                   │
│    frontend/workspace.html                               │
│    frontend/graph.html                                   │
│                                                          │
│  Next step (recommended):                                │
│    legacy 미정의 토큰 정리 (admin.html) — 30분          │
│    또는 상단 그라데이션 레일 공통화 — 30분             │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

**문서 끝**

다른 세션 시작 시: 이 파일 경로(`frontend/HANDOVER_WEB_UI.md`) 만
넘기면 컨텍스트가 복원된다.
