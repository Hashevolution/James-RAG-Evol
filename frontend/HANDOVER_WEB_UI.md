# Web UI 디자인 — 작업 인수인계 (PC 세션 이전용)

**작성일**: 2026-05-06
**브랜치**: `claude/design-web-ui-6NQaQ`
**작성 환경**: Claude Code on the web (Opus 4.7)
**대상**: PC 로컬 세션의 Claude (또는 본인)
**상태**: 평가 완료, 구현 미착수

---

## 1. 작업 목적

현재 `frontend/index.html` (779줄) + `frontend/admin.html` (700줄) 구조의
Web UI를 평가하고, 개선 방향을 정하기 위한 사전 검토 단계.

브랜치 이름이 `design-web-ui`이지만, 사용자 의도는 **전면 재설계가 아닌
"평가 후 우선순위 결정"**. 사용자가 "평가가 어때?"라고 물어 평가만
수행한 상태로 PC 이전.

---

## 2. 현재 UI 구조 (요약)

```
frontend/
├── index.html      779줄 — 채팅 메인 (인라인 <style> 615줄까지)
├── admin.html      700줄 — 어드민 대시보드 (인라인 <style>)
└── static/
    ├── chat.js     채팅 로직 + 세션 패널 + 로그인
    ├── admin.js    어드민 동적 텍스트 t() 적용
    ├── upload.js   드래그앤드롭 업로드
    └── i18n.js     286 키 × en/ko
```

### 디자인 토큰 (양 파일 중복)

```css
--bg:        #0a0a0f
--surface:   #111118
--border:    #1e1e2e
--accent:    #7c6af7   (보라)
--accent2:   #4fc3f7   (시안)
--text:      #e8e8f0
--muted:     #555570
--success:   #4caf7d
--danger:    #f06292
--font-mono: 'JetBrains Mono', 'Fira Code'
--font-ui:   'Sora', 'Pretendard'
```

### 갖춰진 기능

- 접이식 사이드바 (드래그앤드롭 업로드)
- 챗 영역 + 자동 리사이즈 textarea + 타이핑 인디케이터
- 메시지별 메타 (`mode-badge`, `graph-badge`)
- 그래프 경로 표시 영역 (`.graph-paths`, 좌측 보더 강조)
- 세션 선택 패널 (이전 대화 불러오기)
- 로그인 모달 + 역할 배지 (RBAC 표시)
- PROD/TEST 소스 토글
- 언어 토글 (한/영) + i18n 286 키
- 환영 칩 (예제 쿼리 4개)

---

## 3. 평가 결과

### 좋은 점

- 비주얼 정체성이 일관됨 (보안 + 추론 엔진 컨셉에 맞음)
- 주요 기능 모두 자리잡음 (업로드/세션/로그인/i18n/소스토글)
- 디테일 양호 (드래그앤드롭, 자동 리사이즈, 사이드바 접이)
- Admin: 카드 + 테이블 + RBAC 배지 색 구분 깔끔

### 약점 (우선순위 높은 순)

1. **CSS 인라인** — `index.html` 615줄까지 `<style>` 박혀 있음.
   `admin.html`도 동일 변수 중복 정의. → `static/styles.css`로 추출 필요.
2. **반응형 부재** — 미디어 쿼리 0개. 모바일에서 사이드바 280px가
   화면 점유. → 768px 이하 브레이크포인트 + 사이드바 오버레이 모드.
3. **접근성 약함** — `aria-label` 없음, 모달에 `role="dialog"` /
   focus trap 없음, `--muted #555570` on `--bg #0a0a0f` 대비 WCAG AA
   미달 가능. 키보드 내비게이션 미검증.
4. **인라인 핸들러 다수** — `onclick="..."` 다수. CSP 강화 시 깨짐.
   보안 중심 프로젝트로서 이벤트 위임으로 전환 권장.
5. **Graph-RAG 강점이 안 드러남** — `.graph-paths`는 작은 좌측
   보더 표시뿐. 추론 단계(retrieve→expand→verify), 신뢰도, 출처 노드를
   더 시각적으로 보여줄 패널이 없음.
6. **i18n 누락 placeholder 혼재** — `placeholder="e.g., Save to 2026
   reports folder"` 같은 영문 하드코딩 + 한국어 title 혼재.
7. **welcome chips 하드코딩** — 동적 추천 (최근/인기) 없음.

---

## 4. 사용자에게 제시한 우선순위

```
1. CSS 추출 + 공통 토큰 파일                    (1~2시간, 위험 낮음)
2. 반응형 (모바일 ≤768px) + 사이드바 오버레이
3. 추론 패널 강화 — 메시지 클릭 시 우측에
   retrieve → expand → verify 단계 + 인용 노드 펼치기
4. 접근성 패스 — aria, 대비, 키보드
5. 인라인 핸들러 → 이벤트 위임 (CSP 대비)
```

**사용자 응답 대기 중**: 어디부터 손댈지 미결정.

---

## 5. 다음 세션 (PC) 시작 시 해야 할 일

### 5-1. 컨텍스트 복원

```
1. 이 문서 (frontend/HANDOVER_WEB_UI.md) 읽기
2. HANDOVER.md 4-2 폴더 구조 확인 (frontend 부분)
3. frontend/index.html + admin.html 훑어보기
4. 현재 브랜치 확인:
   git branch --show-current
   → claude/design-web-ui-6NQaQ 이어야 함
```

### 5-2. 사용자에게 확인할 첫 질문

```
"웹 세션에서 평가까지 마쳤습니다. 5가지 우선순위 중 어디부터
시작할까요?

  1. CSS 추출 (가장 안전, 빠름)
  2. 반응형 (사용성 큼)
  3. 추론 패널 강화 (Graph-RAG 차별점 부각)
  4. 접근성 (보안 프로젝트 기본기)
  5. 인라인 핸들러 제거 (CSP 대비)

또는 다른 방향이 있으면 알려주세요."
```

### 5-3. 작업 원칙 (HANDOVER.md 9-3, 9-4 재확인)

```
- 보안 영향 먼저 검토
- fallback 항상 구현
- 절대경로/하드코딩 회피
- 변경사항 CHANGELOG.md에 기록
- 사용자 환경 (Windows + PowerShell) 고려
- 단계별 진행, 각 단계 확인 후 다음
- 한국어 소통, 코드 주석은 영어 OK
- 반응형 / 추론 패널 작업 시 i18n.js 키 신규 추가 가능성 → 검토
```

### 5-4. 추론 패널 강화 시 참고

```
관련 백엔드:
  - core/reasoning_engine.py    추론 루프 (retrieve→expand→verify)
  - core/graph_engine.py        Graph DFS
  - core/retrieval_engine.py    하이브리드 검색

서버 응답에 이미 포함된 메타:
  - mode (chat / coding / retrieval / web_search)
  - graph paths
  - confidence
  - sensitivity

UI에서 표시할 것:
  - 단계별 timeline (3단계 스피너 — 이미 STEP 4-A에 있음)
  - 인용된 entity 노드 (클릭 시 위키로)
  - 신뢰도 bar
  - sensitivity 배지 (public/internal/confidential/secret)
```

---

## 6. 주의사항

```
⚠️ 인라인 핸들러 제거 시:
   - chat.js / admin.js / upload.js 의 함수 export 검토
   - window.func = func 패턴이 많을 수 있음
   - 이벤트 위임 시 data-action 속성 도입 권장

⚠️ CSS 추출 시:
   - index.html / admin.html 양쪽 변수 중복 → :root 한 곳에 통합
   - 기존 클래스명 그대로 보존 (chat.js 의존성)
   - @import url(...) 위치 주의 (CSS 파일 최상단으로)

⚠️ 반응형 시:
   - 사이드바 280px → 모바일에서 overlay 전환
   - 챗 입력창이 모바일 하단 고정 시 keyboard 가림 방지
   - 메시지 max-width: 800px 모바일에서 100% 조정

⚠️ 접근성 시:
   - --muted 색을 어둠 배경에서 끌어올리거나 별도 변수 분리
   - 모달 focus trap (login-modal)
   - 키보드 ESC 닫기 추가
```

---

## 7. 핵심 정보 요약 카드

```
┌─────────────────────────────────────────────────┐
│  Web UI Design — Quick Resume Card              │
├─────────────────────────────────────────────────┤
│                                                  │
│  Branch:       claude/design-web-ui-6NQaQ       │
│  Status:       평가 완료, 구현 미착수           │
│                                                  │
│  Files:                                          │
│    frontend/index.html      779줄               │
│    frontend/admin.html      700줄               │
│    frontend/static/*.js     i18n + chat + admin │
│                                                  │
│  다음 단계:                                      │
│    사용자에게 우선순위 1~5 중 선택 받기         │
│                                                  │
│  추천 시작점:                                    │
│    1번 (CSS 추출) — 안전, 빠름, 후속 작업 기반  │
│                                                  │
└─────────────────────────────────────────────────┘
```

---

**문서 끝**

PC 세션 시작 시 첫 메시지에 이 문서를 첨부하거나
"frontend/HANDOVER_WEB_UI.md 읽고 이어가자" 라고 지시하면 됩니다.
