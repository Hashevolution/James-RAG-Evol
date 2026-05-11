# PROJECT JAMES

> 보안 중심, 로컬 실행 AI 지식 추론 엔진
> 명시적 추론 경로와 자기진화 스캐폴딩 포함

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-v0.1.0--alpha-orange.svg)]()
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)]()
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/12806/badge)](https://www.bestpractices.dev/projects/12806)

> **🚀 처음 시작하시는 분?** 컴퓨터 잘 모르셔도 따라하실 수 있는
> [**비기너 가이드**](README.beginner.ko.md) 를 먼저 보세요.

---

## 프로젝트 상태: v0.1.0 (알파 / 연구 단계)

현재 **활발한 연구 프로젝트** 초기 단계입니다.
핵심 엔진은 작동하지만:

- 보안 우선 원칙으로 설계되고 테스트됨
- **프로덕션 준비 안 됨** — [SECURITY.md](SECURITY.md) 참조
- 많은 기능이 스캐폴딩 상태 — 실데이터 테스트 진행 예정
- 협업과 피드백 환영

---

## 무엇이 다른가

JAMES는 함께 찾기 드문 5가지 아이디어를 결합합니다:

1. **온톨로지가 있는 Graph-RAG** — 관계에 임베딩 이상의 의미를 부여
2. **내장 보안 레이어** — RBAC + ABAC + 지시어 격리
3. **자기진화 스캐폴드** — 피드백 신호 → 패치 제안
4. **성향 시스템** — 11개 조정 가능한 트레잇이 응답에 영향
5. **100% 로컬** — Ollama로 노트북에서 실행 가능

> 솔직한 고지: 각 기능은 완성된 제품이 아닌 *작동하는 프로토타입*입니다. 실데이터 조정이 진행 중입니다.

---

## 빠른 시작

### 사전 요구사항

- Python 3.11+
- [Ollama](https://ollama.ai) 설치 및 실행
- 최소 16GB RAM (32GB+ 권장)
- (선택) NVIDIA GPU — 빠른 추론
- (선택) Tavily API 키 — 웹 검색 ([무료 1k/월](https://tavily.com))

### 설치

```bash
git clone https://github.com/Hashevolution/James-RAG-Evol
cd James-RAG-Evol

# 환경 설정
cp .env.example .env
# .env 편집 — JAMES_API_KEY, JAMES_JWT_SECRET 설정

# 의존성 설치
pip install -r requirements.txt

# 소형 LLM 다운로드
ollama pull gemma2:2b

# 서버 시작
python server_llmwiki.py
```

`http://localhost:8000` 접속

---

## 아키텍처

```
[사용자 쿼리]
     ↓
[보안 필터]        ← 31+ 인젝션 패턴
     ↓
[쿼리 라우터]      ← chat / coding / retrieval / web_search
     ↓
[하이브리드 검색]  ← Vector(60%) + BM25(20%) + keyword(20%)
     ↓
[그래프 엔진]      ← DFS + 신뢰도 + 민감도 게이팅
     ↓
[추론 루프]        ← retrieve → expand → verify
     ↓
[출력 필터]        ← PII 마스킹 + 역할 기반 필터
     ↓
[답변 + 추론 경로]
```

---

## 폴더 구조

```
James-RAG-Evol/
├── core/             사용자 인터페이스 레이어 + LLM 클라이언트
├── llm/              LLM 추상화 (providers/)
├── tools/            기능 모듈 (8개 서브폴더)
├── frontend/         웹 UI (HTML + JS)
├── processors/       파일 전처리
├── utils/            유틸리티
├── wiki/             지식 그래프 (마크다운 기반)
├── memory/           장기 기억 DB
├── workspace/        런타임 데이터 (백업, 패치, 제안)
├── scripts/          운영 스크립트
├── reports/          테스트 결과
└── server_llmwiki.py 메인 서버 진입점
```

---

## 보안 접근법

JAMES는 보안을 **기능이 아닌 설계 원칙**으로 다룹니다:

- **3단계 접근 제어**: Vector → Graph → Output
- **RBAC** (4가지 역할) + **ABAC** (4가지 민감도)
- **지시어 격리**: 명령과 데이터 분리
- **JWT 인증** + 속도 제한 + 전체 감사 로그
- **샌드박스 실행** (툴 호출용)

> 현실적 고지: 합성 데이터 테스트는 적대적 프로덕션 테스트와 다릅니다. [SECURITY.md](SECURITY.md) 참조.

---

## 현재 기능

| 기능 | 상태 |
|------|------|
| 하이브리드 검색 (Vector + BM25) | 작동 |
| 온톨로지가 있는 Graph-RAG | 작동 |
| 보안 레이어 (RBAC/ABAC) | 작동 |
| 멀티모달 (이미지/영상) | 스캐폴딩 |
| 자기진화 | 스캐폴딩 (데이터 필요) |
| 웹 검색 통합 | 작동 (Tavily/DDG) |
| 멀티 LLM 라우팅 | 작동 |
| 실데이터 검증 | 진행 예정 |

---

## 기술 스택

- **백엔드**: FastAPI + Uvicorn
- **LLM**: Ollama (Gemma, DeepSeek-Coder, LLaVA)
- **벡터 DB**: ChromaDB
- **임베딩**: Sentence-Transformers (MiniLM)
- **검색**: BM25 + Vector 하이브리드
- **웹 검색**: Tavily (1순위) + DuckDuckGo (fallback)
- **인증**: JWT (python-jose)
- **저장소**: SQLite + 마크다운 위키

---

## 로드맵

[ROADMAP.md](ROADMAP.md) 참조. 요약:

- **v0.1** (현재): 핵심 엔진 + 스캐폴딩
- **v0.2**: 실데이터 검증 + 완성도 향상
- **v0.3**: 멀티에이전트 + Neo4j 옵션
- **v1.0**: 프로덕션 강화

---

## 기여

환영합니다! [CONTRIBUTING.md](CONTRIBUTING.md) 참조.

우선 영역:
- 문서, 예시, 번역
- 버그 수정, 테스트 커버리지
- 새 툴 및 LLM 제공자 통합

---

## 라이선스

MIT 라이선스 — [LICENSE](LICENSE) 참조

---

## 감사

다음에서 영감을 받았습니다:
- [Microsoft GraphRAG](https://github.com/microsoft/graphrag)
- [LightRAG](https://github.com/HKUDS/LightRAG)
- [Graphiti](https://github.com/getzep/graphiti)
- Palantir 스타일 온톨로지 접근법

---

## 면책 조항

**본인 책임 하에 사용하세요.** 이것은 연구 코드입니다. 추가 강화 없이 민감한 데이터 처리나 프로덕션 보안에 대한 어떠한 보증도 없습니다.
