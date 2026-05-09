# PROJECT JAMES

> 보안 중심, 로컬 실행 AI 지식 추론 엔진
> 명시적 추론 경로와 자기진화 스캐폴딩 포함

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-v0.1.4--alpha-orange.svg)]()
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)]()
[![Last Commit](https://img.shields.io/github/last-commit/Hashevolution/James-RAG-Evol)](https://github.com/Hashevolution/James-RAG-Evol/commits/main)
[![GitHub Stars](https://img.shields.io/github/stars/Hashevolution/James-RAG-Evol?style=social)](https://github.com/Hashevolution/James-RAG-Evol)
[![Contributor Covenant](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg)](CODE_OF_CONDUCT.md)
[![OpenSSF Best Practices](https://img.shields.io/badge/OpenSSF-pending-lightgrey.svg)](https://www.bestpractices.dev/)

> **🚀 처음 시작하시는 분?** 컴퓨터 잘 모르셔도 따라하실 수 있는
> [**비기너 가이드**](README.beginner.ko.md) 를 먼저 보세요.

---

## 프로젝트 상태: v0.1.4 (알파 / 연구 단계)

현재 **활발한 연구 프로젝트** 초기 단계입니다.
핵심 엔진은 작동하지만:

- 보안 우선 원칙으로 설계되고 테스트됨
- **프로덕션 준비 안 됨** — [SECURITY.md](SECURITY.md) 참조
- 많은 기능이 스캐폴딩 상태 — 실데이터 테스트 진행 예정
- 협업과 피드백 환영

현재 사이클: **v0.2 Foundation Hardening** (eval/test/docs 성숙도, 새 도메인 없음). [ROADMAP.md](ROADMAP.md) · [docs/PLATFORM_READINESS.md](docs/PLATFORM_READINESS.md) 참조.

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

JAMES는 보안을 **기능이 아닌 설계 원칙**으로 다릍니다:

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

- **v0.1** (완료): 핵심 엔진 + 스캐폴딩
- **v0.2** (현 사이클, 0–4개월): Foundation Hardening — eval/test/docs 성숙도, Axes 1–6
- **v0.3** (4–10개월): Platform Skeleton — plugin API + 일반 reference pack
- **v0.4** (10–22개월): First Pilot — 첫 비-일반 도메인 팭 + 고객 PoC
- **v1.0** (22+개월): Mother Complete — 운영 규율 + 다중 도메인 준비

6축 readiness 게이트는 [docs/PLATFORM_READINESS.md](docs/PLATFORM_READINESS.md)에서 추적합니다. 현 사이클 핸드오버는 [docs/handovers/v0.2.0-platform-track.md](docs/handovers/v0.2.0-platform-track.md)에 있습니다.

---

## 기여

환영합니다! [CONTRIBUTING.md](CONTRIBUTING.md) 참조 (사이클 제약: v1.0 전까지 새 도메인 추가 금지, v0.2–v0.4 기간 고객 특정 기능 금지). 코드 기여는 [Contributor License Agreement](.github/CLA.md) 하에 수락됩니다.

우선 영역:
- 문서, 예시, 번역
- 버그 수정, 테스트 커버리지
- 새 툴 및 LLM 제공자 통합

---

## 함께하기

- ⭐ 이 저장소가 유용하다면 Star를 눌러주세요 — 비슷한 문제를 풀고 있는 다른 개발자에게 닿는 가장 강한 신호입니다
- 💬 질문은 [Discussions](https://github.com/Hashevolution/James-RAG-Evol/discussions)에서
- 🐛 버그는 [Issue 등록](https://github.com/Hashevolution/James-RAG-Evol/issues/new/choose)
- 🔒 보안 취약점은 [비공개 보안 권고](https://github.com/Hashevolution/James-RAG-Evol/security/advisories/new)로

---

## 상용 사용

PROJECT JAMES는 현재 MIT 라이선스로 배포됩니다 ([LICENSE](LICENSE) 참조). MIT 조건 하에서는 누구나 상업적 사용·수정·배포가 가능합니다.

운영자는 **향후 도메인 특화 확장** (예: 호스피탈리티, 정부, 여행 등 — 총칭 "도메인 팭")을 v0.4 마일스톤부터 별도 저장소에서 별도 상용 라이선스로 출시할 권리를 유지합니다. mother 플랫폼 (이 저장소)은 v1.0까지 MIT 라이선스를 유지할 예정입니다.

외부 코드 기여는 [Contributor License Agreement](.github/CLA.md) 하에 수락되며, 이는 운영자에게 운영 모델이 진화할 때 (예: open core, dual license) 프로젝트 전체를 relicense할 권리를 부여합니다. 기존 MIT 배포본은 영향을 받지 않습니다.

상용 라이선스 문의 — 도메인 팭 라이선스, 커스텀 기능, 대안 조건 등 — 는 [Discussions](https://github.com/Hashevolution/James-RAG-Evol/discussions)를 열거나 SECURITY.md의 운영자 연락처로 문의해주세요. 가격은 아직 공개되지 않았습니다.

분석 프레임워크는 [docs/strategy/license-and-monetization.md](docs/strategy/license-and-monetization.md), mother/팭 경계 명세는 [docs/strategy/ip-boundary.md](docs/strategy/ip-boundary.md) 참조.

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
