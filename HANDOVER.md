# PROJECT JAMES — 인수인계서

**작성일**: 2026년 5월 (초기) / 2026-08-21 header refresh
**작성자**: Hashevolution
**대상**: 다음 세션의 Claude (또는 본인 참조용)
**현재 상태**: v0.5 closed (2026-06-13) + 미릴리스 v0.6 / v0.6.1 제품 하드닝 스트림 (#886–#1078). **최신 태그 릴리스는 v0.4.4**, DOI [`10.5281/zenodo.20652679`](https://doi.org/10.5281/zenodo.20652679). v0.6 정식 미진입 (Dim F 게이트 미통과).

> ⚠️ **이 문서의 본문 (§1 이하 ~700 줄) 은 초기 v0.1.x 시점의 인수인계 기록 보존본**입니다. 현재 상태와 다음 작업은 아래를 보세요:
>
> - **신규 세션 진입 시 첫 의무 reading**: **`docs/handovers/v0.6.2-restart-roadmap-2026-08-21.md`** (재개 로드맵 Phase 1–7 + 현재 상태 사실 확인 + 🔴 CI 빨간불)
> - **CLAUDE.md "Where to look next" 표 첫 행** 도 동일 doc 으로 pinned (가드 테스트가 recency 를 강제)
> - **직전 기능 세션**: `docs/handovers/v0.6.1-session-close-2026-06-26.md`
> - **자세한 한국어 narrative**: `README.ko.md` § "프로젝트 상태 (2026-08-21 기준)"
> - **External evaluator first read**: `SUMMARY.md`
> - **Per-version release narrative**: `docs/release_notes_v0.4.4.md` (최신 태그 릴리스), `docs/release_notes_v0.4.3.md` (RAB 출시), 그리고 그 이전 chain

본문 (§1 이하) 은 프로젝트 출범 시점의 정체성 / 인수인계 맥락 의 historical 기록. 변경하지 않고 보존.

---

## 📌 1. 프로젝트 정체성

### 1-1. 한 줄 정의

> **PROJECT JAMES**: 보안 중심으로 설계된, 로컬 환경에서 동작하는 Graph-RAG 기반 지식 추론 엔진

### 1-2. 4가지 동시 역할 (개발 철학)

```
1. 시스템 아키텍트
2. 보안 엔지니어 (Red Team 포함)
3. Graph / Ontology 연구자
4. 제품 책임자 (Startup CTO)
```

### 1-3. 핵심 철학

```
원칙 1: RAG는 불완전하다
  - 단순 Vector 검색은 hallucination을 막지 못함
  - 반드시 Graph + Ontology 기반 추론 필요

원칙 2: 보안은 기능이 아니라 전제다
  - 모든 설계는 공격을 전제로 시작
  - "동작한다"보다 "유출되지 않는다"가 우선

원칙 3: Graph 없으면 실패
  - Graph 약하면 그냥 느린 검색 엔진
  - 관계 추론 + 경로 기반 reasoning + explainable output 필수

원칙 4: 항상 실패를 가정
  - LLM 실패, 네트워크 끊김, 데이터 깨짐
  - 모든 로직은 fallback 필수
```

### 1-4. 의사결정 우선순위

```
1. 보안
2. 데이터 정합성
3. Graph 정확성
4. 안정성
5. 성능
6. 기능 확장
```

### 1-5. 최종 한 줄 목표

> "이 시스템은 단순한 AI가 아니라 보안이 보장된 지식 추론 엔진이어야 한다."

---

## 🏗️ 2. 기술 스택

```
백엔드:        Python 3.11+ / FastAPI / Uvicorn
LLM:           Ollama (Gemma2:2b 기본, DeepSeek-Coder, LLaVA)
Vector DB:     ChromaDB
임베딩:         Sentence-Transformers (MiniLM-L12)
검색:          BM25 + Vector 하이브리드 + keyword
웹 검색:        Tavily (1순위) + DuckDuckGo (fallback)
인증:          JWT (HS256) + Rate Limiting
저장소:        SQLite + 마크다운 위키
환경:          Windows / macOS / Linux 크로스 플랫폼
```

### 핵심 LLM 설정

```
MAX_DEPTH=4 (Graph DFS)
DFS_SCORE_THRESHOLD=0.05
DEPTH_DECAY=0.7
num_predict=동적
num_ctx=2048
temperature=0
```

---

## 📦 3. GitHub 공개 정보

```
저장소:        https://github.com/Hashevolution/James-RAG-Evol
사용자명:       Hashevolution
라이선스:       MIT
공개일:        2026년 5월
현재 버전:      v0.1.1 (Path Auto-Detection Patch)
이전 버전:      v0.1.0-alpha (Initial Public Release)

릴리즈:
  v0.1.0-alpha  최초 공개 (Pre-release, 보안 경고 추가됨)
  v0.1.1        보안/이식성 패치 (Pre-release, 최신)
```

### 저장소 설정

```
Topics:        rag, graph-rag, knowledge-graph, ollama, local-llm,
               local-ai, fastapi, python, security, ai-agent, self-evolution

Features:
  ✅ Issues 활성
  ✅ Dependabot alerts 활성
  ✅ Dependabot security updates 활성
  ☐ Wiki, Discussions, Projects, Sponsorships 비활성

Pull Requests:
  ✅ Automatically delete head branches
```

---

## 🗂️ 4. 프로젝트 구조

### 4-1. 로컬 개발 환경

```
경로:          C:\Project\James-RAG-Evol-v010\ (사용자 PC)
GitHub 폴더명:  James-RAG-Evol (저장소 이름)
```

### 4-2. 폴더 구조

```
James-RAG-Evol/
├── core/                       사용자 인터페이스 + LLM 클라이언트
│   ├── auth.py                JWT 인증
│   ├── cache_manager.py
│   ├── character_profile.py   11 트레잇 정의 (영어화 완료)
│   ├── feedback_engine.py     피드백 → 제안 생성
│   ├── gemma_client.py
│   ├── graph_engine.py        Graph DFS 핵심
│   ├── graph_rag_engine.py    backward-compat wrapper
│   ├── intent_classifier.py
│   ├── jepa_adapter.py
│   ├── knowledge_tracker.py   8 능력 + 6 도메인 (영어화 완료)
│   ├── memory_extractor.py
│   ├── memory_loom.py
│   ├── memory_store.py
│   ├── memory_trust.py
│   ├── ontology.py            12 relation types
│   ├── orchestrator.py
│   ├── query_router.py
│   ├── rag_engine.py
│   ├── reasoning_engine.py    추론 루프 (언어 자동 감지 포함)
│   ├── retrieval_engine.py
│   ├── security_layer.py      31+ injection patterns
│   ├── vector_store.py        ChromaDB + 임베딩 (BASE_DIR 자동 감지)
│   └── wiki_generator.py
│
├── llm/                        LLM 추상화
│   ├── base.py
│   ├── router.py
│   └── providers/
│       ├── deepseek_client.py
│       ├── llava_client.py
│       └── ollama_client.py
│
├── tools/                      기능 모듈
│   ├── admin/                 (seed_data, upload_simulator, wiki_reset)
│   ├── code/                  (analyzer, editor, reader, sandbox)
│   ├── multimodal/            (image, media, video)
│   ├── patch/                 (4-Gate Patch Pipeline)
│   ├── screen/                (screen_agent)
│   ├── self/                  (evo_analyzer, performance, self_learner)
│   ├── system/                (hardware_inspector — 영어화 완료)
│   ├── web/                   (web_searcher — Tavily/DDG)
│   └── wiki/                  (wiki_editor)
│
├── frontend/
│   ├── admin.html             156 data-i18n 적용
│   ├── index.html             28 data-i18n 적용
│   └── static/
│       ├── admin.js           동적 텍스트 t() 적용 완료
│       ├── chat.js            UI 토글 + session_lang 동기화
│       ├── i18n.js            286 키 (영/한)
│       └── upload.js
│
├── processors/
│   └── file_processor.py
│
├── utils/
│   ├── metadata.py
│   └── tokenizer.py
│
├── wiki/                       지식 그래프 (마크다운)
│   ├── entity/
│   │   ├── prod/              운영 데이터
│   │   │   ├── concept/       (Graph-RAG, 보안추론, ollama_en 등)
│   │   │   ├── person/        (김민준, 박지훈, 이서연, john_smith_en)
│   │   │   └── org/           (자메스연구소, james_research_lab_en 등)
│   │   └── test/              테스트 데이터
│   └── index.md
│
├── memory/                     장기 기억 DB (.gitignore 제외)
├── chroma_db/                  ChromaDB (.gitignore 제외)
├── workspace/                  런타임 데이터 (.gitignore 제외)
├── uploads/                    업로드 (.gitignore 제외)
├── models/miniLM/              임베딩 모델 (.gitignore 제외)
│
├── scripts/
│   ├── create_james_self_wiki.py
│   ├── reset_for_production.py
│   ├── test_ollama_speed.py
│   └── legacy/                옛 패치 스크립트
│
├── reports/                    테스트 결과 (.gitignore 제외)
│
├── 테스트 파일들 (루트):
│   ├── james_diagnostic.py    65 항목, 8 섹션
│   ├── james_security_test.py 83 항목
│   ├── james_e2e_test.py
│   ├── james_phase5_test.py
│   ├── james_phase55_test.py
│   ├── james_phase6_test.py
│   ├── james_phase6_gate.py
│   └── james_phase7_test.py
│
├── 설정 파일:
│   ├── config.py              자동 감지 + 크로스 플랫폼
│   ├── .env                   (.gitignore, 로컬 전용)
│   ├── .env.example
│   ├── .gitignore
│   └── requirements.txt       26개 패키지
│
├── 문서 (루트):
│   ├── README.md              영어 (Hashevolution 적용)
│   ├── README.ko.md           한국어
│   ├── SECURITY.md
│   ├── ROADMAP.md
│   ├── CONTRIBUTING.md
│   ├── CHANGELOG.md
│   └── LICENSE                MIT
│
└── server_llmwiki.py           메인 서버 진입점
```

---

## 🛡️ 5. 보안 모델 (3-stage Access Control)

```
┌──────────────────────────────────────────────────────┐
│  [User Query]                                         │
│       ↓                                               │
│  ① 입력 필터  ← 31+ injection patterns               │
│       ↓                                               │
│  ② 쿼리 라우터 ← chat / coding / retrieval / web    │
│       ↓                                               │
│  ③ 하이브리드 검색  ← Vector(60%) + BM25(20%) + kw  │
│       ↓                                               │
│  ④ Graph 엔진  ← DFS + confidence + sensitivity     │
│       ↓                                               │
│  ⑤ 추론 루프  ← retrieve → expand → verify          │
│       ↓                                               │
│  ⑥ 출력 필터  ← PII 마스킹 + role-based 필터        │
│       ↓                                               │
│  [답변 + 추론 경로]                                  │
└──────────────────────────────────────────────────────┘

RBAC (4 roles):
  admin     모든 sensitivity 접근, 모든 조작
  manager   public→confidential, 대부분
  employee  public→internal, 읽기+표준
  external  public 전용

ABAC (4 sensitivity):
  public          모두 접근
  internal        employee+
  confidential    manager+
  secret          admin 전용

Instruction Isolation:
  명령과 데이터 분리
  31+ injection 패턴 감지 (.{0,15} flexible matching)

JWT 인증:
  HS256 서명, 24시간 만료
  Rate Limiting: 30 req / 60s

Audit Log:
  SQLite, 모든 요청/결정/거부 기록
```

---

## ✅ 6. 완료된 작업 (Timeline)

### Phase 1~7 (이전 완료)

```
✅ 핵심 엔진
   - Hybrid Search (Vector 60% + BM25 20% + keyword 20%)
   - Graph-RAG with Ontology (12 relation types)
   - DFS 탐색 (depth ≤ 4, confidence threshold)

✅ 보안 레이어
   - RBAC (4 roles)
   - ABAC 3-stage (4 sensitivity levels)
   - Instruction Isolation (31+ patterns)
   - JWT + Rate Limiting
   - SQLite audit log

✅ 자기진화 (Scaffold)
   - Patch Pipeline 4-Gate
   - 11-trait Character
   - Knowledge Tracker (8 능력 + 6 도메인)
   - Feedback Engine (👍/👎 → 제안 자동 생성)

✅ 멀티모달 + Web Search
   - LLaVA (이미지/영상)
   - Whisper (오디오)
   - Tavily + DuckDuckGo
```

### STEP 4 — 자기진화 강화 (완료)

```
✅ 4-A 사고과정 UI 3단계 (2.5초 간격) + jamesNotify 토스트
✅ 4-B hardware_inspector.py LLM_CATALOG (10개)
       → /admin/llm/{installed,recommend,pull,delete} API
       → 어드민 LLM 추천 카드 + 자동 설치
✅ 4-C feedback_engine.py 부정피드백 → web_learn proposal
       → 거부사유 → memory_store 장기기억 저장
       → executeWebLearnProposal()
```

### 단계 A — 정리 (완료)

```
✅ A-1 루트 청소
       reports/, scripts/, scripts/legacy/ 폴더 생성
       테스트결과 .json 6개 격리
       patch_*.py 격리
       운영스크립트 이동

✅ A-2 보안/문서
       .gitignore (260 bytes)
       .env.example (170 bytes)
       LICENSE MIT (673 bytes)
       tokenizer.py 중복 제거 (utils/ 정식)
       security.py → security_layer.py 통합

✅ A-3 5개 문서 작성
       README.md / SECURITY.md / ROADMAP.md
       CONTRIBUTING.md / CHANGELOG.md
```

### STEP 5 — 글로벌화 (완료)

```
✅ 5-A UI 완전 영어화
       i18n.js: 286개 키 × 2언어 (en/ko)
       기본 언어: 영어 (글로벌 호환)
       양 언어 토글 (KO | EN 동시 표시)
       index.html: 28 data-i18n
       admin.html: 156 data-i18n
       chat.js / admin.js: t() 동적 번역
       
       Python 데이터 영어화:
       - character_profile.py (11 트레잇)
         Curiosity / Focus / Caution / Boldness / Analytical /
         Intuitive / Independent / Collaborative / Security /
         Creativity / Empathy
       - knowledge_tracker.py (8 능력 + 6 도메인)
         Knowledge Retrieval / Relation Reasoning /
         Security Judgment / Conversation Understanding /
         Answer Accuracy / Image-Video Analysis /
         Self-Evolution / Agent Capability
         Security / Coding / Business / Science-AI / General / Personal
       - hardware_inspector.py (무기/역할/랭크)
         Wooden Sword~Legendary Holy Sword
         Leather Shield~Immortal Shield
         Apprentice Staff~Divine Wand
         Small Pouch~Infinite Warehouse
         Trainee~Legendary Wizard

✅ 5-B 영어 시드 데이터 5개
       wiki/entity/test/concept/graph_rag_en.md
       wiki/entity/test/concept/security_reasoning_en.md
       wiki/entity/test/concept/ollama_en.md
       wiki/entity/test/person/john_smith_en.md
       wiki/entity/test/org/james_research_lab_en.md

✅ 5-C 시스템 프롬프트 동적 언어 전환
       reasoning_engine.py:
         쿼리 자동 감지 (한국어 ≥ 20% → Korean)
         페르소나 우선, 없으면 자동 감지
         Korean / English / Bilingual 지시어
       chat.js:
         UI 토글 → session_language 자동 동기화
         초기값: English

✅ 5-D README.ko.md 작성 (5,508 bytes)

✅ 5-E 버그 수정
       LLM 컨텍스트 초과 (한국어 1500자 = 4000토큰 초과) 해결
       → snippet[:150] × 3 + 짧은 지시문 = 약 650자
       save_as_longterm 예외 격리 (try-except)
       웹검색 카드 제거 (혼란 방지)
       requirements.txt 정리 (6개 패키지 추가)
```

### STEP 6 — GitHub 공개 (완료)

```
✅ v0.1.0-alpha 첫 공개
       125 files / 32,257 lines
       9개 핵심 문서
       영어/한국어 i18n
       시드 데이터 (영어 5 + 한국어 7)

✅ v0.1.1 패치 (보안/이식성)
       config.py: BASE_DIR 자동 감지
       config.py: 사용자명 노출 제거 (hyunn)
       config.py: 크로스 플랫폼 (Win/macOS/Linux)
       vector_store.py: LOCAL_MODEL_PATH 자동 감지
       patch_abac_fields.py: fallback 안전화
       seed_data.py / wiki_reset.py: fallback 안전화
       v0.1.0-alpha 페이지에 보안 경고 추가
```

### 환경변수 (요약)

```
JAMES_API_KEY              API 인증 키 (필수)
JAMES_JWT_SECRET           JWT 시그니처 (필수, 32자+)
TAVILY_API_KEY             웹 검색 (선택, 무료 1k/월)
TESSERACT_PATH             Tesseract OCR (선택, 자동 감지)
JAMES_POPPLER_PATH         Poppler (선택, 자동 감지)
OLLAMA_PATH                Ollama (선택, PATH 사용)
JAMES_MODEL_PATH           임베딩 모델 (선택)
JAMES_LLM_MODEL            기본 LLM (default: gemma2:2b)
OLLAMA_API_URL             Ollama API endpoint
JAMES_MAX_UPLOAD_MB        업로드 한계 (default: 100)
JAMES_PROTECTED_FILES      보호 파일 목록 (쉼표 구분)
```

---

## 🐛 7. 발견된 주요 버그 + 해결 (참고)

```
1. 민감 값 마스킹 누락
   → 키워드 라벨만 치환, 숫자값 노출
   → 값 패턴 정규식 추가

2. Instruction Isolation 경직성
   → 의역된 인젝션 감지 실패 (엄격한 인접성)
   → .{0,15} flexible matching

3. RBAC 벡터 누출
   → Vector 검색이 graph 마스킹 우회
   → wiki_person_names 파라미터로 해결

4. Windows 인코딩 충돌
   → CP949/UTF-8 충돌 (config.py에 한국어 시 발생)
   → 한국어 제거 + 명시 인코딩 fallback

5. LLM 0자 응답 + 500 에러 (자기학습)
   → 한국어 1500자 = 4000토큰 → num_ctx=2048 초과
   → snippet 축소 + body 제외 + LLM 응답 fallback
   → save_as_longterm 예외 격리

6. 웹검색 "미설치" 표시
   → tavily_key만 체크하던 버그
   → tavily_installed + tavily_key + !exhausted 모두 체크
   → API에 _require_admin 제거 (api_key만으로 충분)
   → 결국 카드 자체 제거 (혼란 방지)

7. 폴더 이름 변경 시 외부 모델 다운로드
   → vector_store.py LOCAL_MODEL_PATH 절대경로
   → BASE_DIR 기준 자동 감지로 수정
```

---

## 🛣️ 8. 다음 작업 + 로드맵

### STEP 7 — 실데이터 검증 (다음 즉시 작업)

```
목표: 30개 이상 실 entity로 v0.2.0 준비

세부 작업:
  □ 사용자 본인 도메인의 실 문서 30개+ 업로드
  □ 다양한 entity 타입 (concept, person, org)
  □ 한국어 + 영어 데이터 혼합
  □ 실 사용 시나리오로 쿼리 100회+ 테스트
  □ 발견된 한계점/버그를 GitHub Issues로 등록
  □ Patch Pipeline 자기진화 end-to-end 검증
  □ 성능 프로파일링 (응답 시간, 정확도)

기간: 1~2주
산출물:
  - v0.2.0 release notes 데이터
  - 실 사용 사례 README 추가
  - 성능 벤치마크 수치
```

### v0.2.0 — 실데이터 검증 + 완성도 향상 (~2~3개월)

```
테마: 합성 데이터 → 실 데이터, 약점 강화

우선순위:
  - 30+ 실 entity 검증
  - 멀티모달 파이프라인 완성
    (LLaVA full integration, Whisper, PDF 표 추출)
  - 자기진화 end-to-end 증명
    (피드백 → 제안 → 패치 → 배포)
  - 성능 최적화 (p50/p99 응답 시간)
  - 임베딩 캐시 개선
  - 튜토리얼 문서 (3종)
    1. 커스텀 도메인 만들기
    2. 온톨로지 확장
    3. 아키텍처 심층
  - 동영상 워크스루 (선택)
```

### v0.3.0 — Multi-Agent + Graph DB (~6개월)

```
테마: 단일 사용자 넘어서기, 옵션 그래프 DB

우선순위:
  - Optional Neo4j 백엔드
    (마크다운 wiki ↔ 그래프 DB 마이그레이션, Cypher)
  - Multi-agent system
    (researcher, coder, security 전문 에이전트)
    (에이전트 간 통신, 작업 분해)
  - 자동 벤치마킹
  - API 개선
    (OpenAI 호환 API, 스트리밍, Webhook)
```

### v1.0.0 — Production Hardening (~12개월)

```
테마: 엔터프라이즈 준비

우선순위:
  - Multi-tenancy
    (테넌트별 데이터 격리, 모델 선택, 쿼터)
  - HTTPS 기본 + Docker 배포 가이드 + Helm Charts
  - 컴플라이언스 준비
    (GDPR 데이터 삭제, SOC 2 audit log, 데이터 residency)
  - 고급 보안
    (역할/엔드포인트별 rate limit, 이상 탐지, 옵션 2FA)
  - 운영 도구
    (백업/복원 CLI, 마이그레이션, health check, Prometheus)
```

### v1.0+ Speculative

```
- Federation (다중 JAMES 인스턴스 연결)
- On-device fine-tuning (사용자별 LoRA)
- Edge deployment (소형 모델)
- Plugin marketplace
- Visual graph editor (web UI)
- Voice interface (ASR + TTS)
```

---

## 🎯 9. 다음 세션 시작 시 해야 할 일

### 9-1. 컨텍스트 복원

```
1. 이 인수인계서 읽기
2. README.md 한 번 훑기
3. CHANGELOG.md로 v0.1.1 변경사항 확인
4. ROADMAP.md로 v0.2.0 목표 확인
```

### 9-2. 즉시 시작할 수 있는 작업

```
[Option A] STEP 7 실데이터 검증 (가장 큰 다음 단계)
  → 사용자가 실제 문서 30개+ 준비하면 시작
  → 업로드 → 검색 → 추론 정확도 검증
  → 버그 발견 → Issues 등록 → 즉시 패치

[Option B] STEP 8 사용자 피드백 채널 보강
  → Issue 템플릿 추가
  → 짧은 데모 GIF 만들기
  → FAQ 문서 작성
  → README 상단에 데모 영상 임베드

[Option C] 작은 개선 작업
  → 발견된 버그 수정
  → 특정 모듈 리팩토링
  → 새 LLM provider 추가
  → i18n 새 언어 추가 (일본어, 중국어 등)

[Option D] 마케팅/확산 (선택)
  → Hacker News / Reddit r/LocalLLaMA 공유
  → Twitter/X 게시
  → Dev.to 또는 Medium 블로그 글
```

### 9-3. 주의사항

```
⚠️ 절대 잊지 말 것:
  - JWT_SECRET을 .env에 설정해야 함 (없으면 dev 시크릿 경고)
  - 폴더 이름은 자유롭게 변경 가능 (v0.1.1 패치 후)
  - 모든 절대경로/사용자명 노출 검증 필수 (커밋 전)
  - 한국어 컨텍스트는 토큰 2~3배 → num_ctx 주의

⚠️ 코드 수정 시:
  - 항상 보안 영향 검토
  - fallback 항상 구현
  - 명시적 타입/이름
  - 변경사항 CHANGELOG.md에 기록
```

### 9-4. 작업 스타일 (사용자 선호)

```
- 명확한 단계별 진행 (한 번에 하나씩)
- 각 단계 결과 확인 후 다음 진행
- 문제 발생 시 즉시 진단 명령 제공
- PowerShell 명령어 직접 제공 (사용자 환경)
- 한국어로 소통 (코드 주석은 영어 OK)
- 보안/이식성 우선
```

---

## 📍 10. 핵심 정보 요약 카드

```
┌─────────────────────────────────────────────────────┐
│  PROJECT JAMES — Quick Reference                     │
├─────────────────────────────────────────────────────┤
│                                                      │
│  GitHub:    Hashevolution/James-RAG-Evol            │
│  Version:   v0.1.1 (Pre-release)                    │
│  License:   MIT                                      │
│                                                      │
│  Local:     C:\Project\James-RAG-Evol-v010\         │
│  Server:    python server_llmwiki.py → :8000        │
│  Admin:     http://localhost:8000/admin             │
│                                                      │
│  현재 상태:                                          │
│    공개됨, 보안 깨끗함, 작동함                       │
│    실데이터 검증 대기 중                             │
│                                                      │
│  다음 단계:                                          │
│    STEP 7 — 실데이터 30개+ 투입                      │
│                                                      │
│  핵심 철학:                                          │
│    보안이 보장된 지식 추론 엔진                      │
│                                                      │
└─────────────────────────────────────────────────────┘
```

---

## 🤝 11. 다음 Claude에게

```
이 프로젝트는 단순한 RAG 시스템이 아닙니다.
보안을 가장 중요한 설계 원칙으로 삼고,
Graph-RAG로 hallucination을 줄이며,
explainable output을 추구합니다.

사용자는:
  - 보안과 정확성을 매우 중요하게 봅니다
  - 명확한 단계별 진행을 선호합니다
  - 실패할 가능성을 항상 고려합니다
  - 한국어로 소통하지만, 코드는 영어/글로벌 기준입니다

작업 시 항상:
  1. 보안 영향 먼저 검토
  2. fallback 구현
  3. 절대경로/하드코딩 회피
  4. 변경사항 문서화
  5. 사용자 환경 (Windows + PowerShell) 고려
  6. 단계별로 진행, 각 단계 확인 후 다음

수고하세요. 좋은 프로젝트입니다.
```

---

**문서 끝**

작성: v0.1.1 릴리즈 직후
다음 세션에서 이 문서를 첫 메시지에 첨부하면 즉시 컨텍스트 복원 가능합니다.
