# PROJECT JAMES

> **로컬 우선, 감사 가능한 지식 추론 시스템**
> — 명시적 추론 경로 + 출처 인식 지식 그래프 + 인간 승인 게이트
> 기반 자기진화.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-v0.3.1-blue.svg)](docs/release_notes_v0.3.1.md)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)]()
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/12806/badge)](https://www.bestpractices.dev/projects/12806)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20363998.svg)](https://doi.org/10.5281/zenodo.20363998)

![PROJECT JAMES — 3D 온톨로지 그래프 시각화](reports/promo-assets/screenshots/06-3d-graph.jpg)

> **🚀 처음 시작하시는 분?** 컴퓨터 잘 모르셔도 따라하실 수 있는
> [**비기너 가이드**](README.beginner.ko.md) 를 먼저 보세요.

---

## 프로젝트 상태: v0.3.0 — Platform Skeleton

**2026-05-17 정식 릴리스** (v0.2.0 이후 9일간 190 PR, 1800+ tests).
v0.2 → v0.3 게이트 통과 — 6축 Foundation Hardening
(아키텍처 / 평가 / 관찰성 / 보안 / 통제 진화 / 실데이터 검증) 모두
완료. 두 번째 사용자 게이트는 2026-05-13 마감.

- **프로덕션 준비 안 됨** — 운영 성숙도 (HTTPS / SSO / 멀티테넌시 /
  백업 CLI) 는 v1.0 산출물. [SECURITY.md](SECURITY.md) 참조
- 보안 우선 원칙으로 end-to-end 설계
- 협업 환영 — 외부 기여자는 첫 PR 시 1회 클릭 CLA 서명
  ([라이선스](#라이선스) 참조)

---

## 전략 프레임: 단일 제품이 아닌 모체 플랫폼

JAMES 는 **하나의 버티컬**을 만드는 것이 아닙니다. 법률·식품·유통·
여행 등의 도메인 팩이 **v1.0 이후에만** 분기할 수 있는 "모체
플랫폼"으로 강화 중입니다. 그 전까지는:

- 도메인 특화 기능은 `core/` 에 들어가지 않음
- 모든 변경이 동일한 6 차원 readiness 프레임워크로 측정
  (아키텍처 / 확장 API / 평가 계약 / 운영 성숙도 / 보안 경계 /
  프로덕션 검증)
- 미래의 팩이 의존할 플러그인 계약을 설계 + 스트레스 테스트 중

6 차원 / 4 게이트 (v0.2 / v0.3 / v0.4 / v1.0) / 3 분기 형태
(Domain Pack / Distribution / Vertical Product) 전체 설명은
[`docs/PLATFORM_READINESS.md`](docs/PLATFORM_READINESS.md) 참조.

---

## 무엇이 다른가

JAMES 는 함께 찾기 드문 아이디어를 결합합니다:

1. **출처 인식 Graph-RAG** — 12 typed relation 이 임베딩 이상의
   의미를 부여하고, 모든 relation 에 `sources: [{doc_id, weight,
   role, ts}]` 가 부착되어 문서 삭제/수정 시 영향받은 파생 지식만
   외과적으로 갱신 (Knowledge Cascade A→E, v0.3.0)
2. **Cognitive Layer** — cross-encoder reranker (디폴트 ON),
   LLM query rewriter, reflection loop (draft → critique → revise),
   verification engine (security + fact check), tool router.
   하나의 `trace_id` 로 8 단계 추론 시퀀스를
   `scripts/replay_trace.py` 로 재구성 가능
3. **PolicyEngine — sprinkle 아닌 layer** — 역할/민감도 결정의
   단일 진입점이 retrieval / graph / output / tools 모두에 연결.
   제거하면 6+ 모듈이 깨짐 (v0.2 Axis 4)
4. **Change Request 프리미티브** — 모든 쓰기 (위키 편집, 워크스페이스
   잡, 자가-진화 패치) 가 propose → review → admin 승인 →
   atomic apply → audit 행으로 라우팅. silent write 없음.
5. **인간 게이트 뒤 자가-진화** — 피드백 → 후보 → bench eval →
   인간 승인 → 배포 → 회귀 시 auto-rollback. 배포된 모든 패치는
   `approver_username` 감사 행을 보유 (v0.2 Axis 5)
6. **100% 로컬** — Ollama 로 노트북에서 실행 가능

> 모든 기능은 STEP 7 13-query baseline + RAGAS 메트릭으로 회귀
> 테스트. `core/{retrieval,graph,reasoning}` 을 건드리는 PR 은
> bench 숫자 없이 머지 불가.

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

# 서버 시작 (첫 로그인 시 admin wizard 가 모델을 자동 추천)
python server_llmwiki.py
```

`http://localhost:8000/admin` 접속 — admin wizard 가 하드웨어를
측정하고 적합한 Ollama 모델을 한 번 클릭으로 설치합니다. 이후
`http://localhost:8000` 에서 채팅 UI 사용.

---

## 아키텍처

```
[사용자 쿼리]
     ↓
[보안 필터]              ← 인젝션 패턴 + PolicyEngine pre-check
     ↓
[쿼리 라우터]            ← chat / coding / retrieval / web_search
     ↓
[Query Rewriter]         ← LLM 재작성 (opt-in, JAMES_ENABLE_QUERY_REWRITE)
     ↓
[하이브리드 검색]        ← Vector(60%) + BM25(20%) + keyword(10%) + name(10%)
     ↓
[Cross-Encoder Rerank]   ← MiniLM-L-6-v2 (디폴트 ON; JAMES_DISABLE_RERANK=1 끄기)
     ↓
[그래프 엔진]            ← DFS + 출처 인식 + 민감도 게이팅
     ↓
[추론 루프]              ← retrieve → expand → reflect (opt-in) → verify (opt-in)
     ↓
[Tool Router]            ← read 툴 직접; write 툴 → Change Request
     ↓
[출력 필터]              ← PII 마스킹 + 역할 기반 필터
     ↓
[답변 + 추론 경로 + trace_id]
```

모든 단계가 하나의 `trace_id` 에 연결된 행을 남깁니다.
`scripts/replay_trace.py <trace_id>` 로 `audit_log` 에서 전체
시퀀스를 재구성. Cognitive Layer 설계는
[`docs/ARCHITECTURE.md §5.7`](docs/ARCHITECTURE.md) 참조.

---

## 폴더 구조

```
James-RAG-Evol/
├── core/
│   ├── reasoning/        retrieval / reflection / verification / tool router
│   ├── retrieval/        하이브리드 검색 + cross-encoder reranker + query rewriter
│   ├── memory/           장기 기억 (db / conversation / summaries)
│   ├── plugins/          플러그인 계약 표면 (Provider Protocol)
│   ├── policy_engine.py  역할/민감도 결정의 단일 진입점
│   ├── change_request.py propose/review/approve 쓰기 프리미티브
│   ├── cascade.py        파일 삭제/수정 → 그래프 외과적 갱신
│   ├── graph_editor.py   edge 편집 (replace/append/delete) + 양방향 동기화
│   └── ...
├── eval/                 STEP 7 회귀 baseline + RAGAS suite
├── llm/                  LLM provider 추상화
├── tools/                capability token 게이팅 툴 모듈
├── frontend/             웹 UI (HTML + JS)
├── processors/           파일 전처리
├── wiki/                 지식 그래프 (마크다운 + sources)
├── memory/               장기 기억 DB
├── workspace/            Change request, 패치, 제안
├── scripts/              bench.py / replay_trace.py / 운영 스크립트
├── reports/              평가 결과 + 홍보 자료
├── docs/                 ARCHITECTURE / PLATFORM_READINESS / ROADMAP / handovers
└── server_llmwiki.py     메인 서버 진입점
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
| 하이브리드 검색 (Vector + BM25 + keyword + name) | 작동 |
| Cross-encoder reranker (MiniLM-L-6-v2) | 작동 — 디폴트 ON (v0.3) |
| LLM query rewriter | Opt-in (v0.3) |
| 출처 인식 Graph-RAG (Knowledge Cascade A→E) | 작동 (v0.3) |
| PolicyEngine (RBAC + ABAC + capability token) | 작동 (v0.2 Axis 4) |
| Reflection loop (draft → critique → revise) | Opt-in (v0.3) |
| Verification engine (security + fact check) | Opt-in (v0.3) |
| Tool router (read 직접, write → Change Request) | 작동 (v0.3) |
| Change Request 프리미티브 (위키 + 잡 + 패치) | 작동 (v0.2.x + v0.3) |
| 자가-진화 (인간 승인 + auto-rollback) | 작동 (v0.2 Axis 5) |
| Trace replay (하나의 `trace_id` → 전체 추론 시퀀스) | 작동 (v0.3) |
| 멀티모달 (이미지/영상/오디오 + OCR-poison 격리) | 작동 (v0.2 Axis 4) |
| 웹 검색 (Tavily / DuckDuckGo fallback) | 작동 |
| 멀티 LLM 라우팅 (Ollama + Claude CLI 백엔드) | 작동 |
| STEP 7 회귀 baseline + RAGAS | 작동 (v0.2 Axis 2) |
| 실데이터 검증 (두 번째 사용자 게이트) | 통과 2026-05-13 |

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

[ROADMAP.md](ROADMAP.md) 와
[`docs/PLATFORM_READINESS.md`](docs/PLATFORM_READINESS.md) 참조.
요약:

- **v0.1**: 핵심 엔진 + 스캐폴딩 (릴리스)
- **v0.2**: Foundation Hardening — 6축 (2026-05-13 마감)
- **v0.3**: Platform Skeleton — Cognitive Layer + Knowledge Cascade
  + Change Request 프리미티브 (현재; 2026-05-17 릴리스)
- **v0.4**: First Domain Pilot — 팩 1개 + 외부 고객 1명, 6개월
  무회귀
- **v1.0**: Production-Grade Mother — HTTPS / SSO / 멀티테넌시 /
  SOC2 준비; 외부 개발자가 자체 팩 출판 가능

멀티에이전트 specialist, optional Neo4j 백엔드, OpenAI 호환 API,
streaming, federation 은 Beyond v1.0 으로 재배치 (speculative) —
[`ROADMAP.md` §Beyond v1.0](ROADMAP.md) 참조.

---

## 기여

환영합니다! [CONTRIBUTING.md](CONTRIBUTING.md) 참조.

우선 영역:
- 문서, 예시, 번역
- 버그 수정, 테스트 커버리지
- 새 툴 및 LLM 제공자 통합

---

## 라이선스

**MIT 라이선스로 배포됩니다.** 자유롭게 사용하세요. [LICENSE](LICENSE) 참조.

외부 기여자는 첫 PR 시 [Contributor License Agreement](docs/legal/CLA.md)
한 번에 서명 (CLA Assistant 봇이 자동 안내). 1회 서명으로 이후 모든 기여
커버. 자세한 안내는 [CONTRIBUTING.md](CONTRIBUTING.md#license--contributor-license-agreement-cla)
§License & CLA 섹션, 서명 없이 기여하는 경로는
[docs/legal/non-cla-contributions.md](docs/legal/non-cla-contributions.md) 참조.

외부 의존성의 라이선스 전체 목록은
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) 참조.

---

## 감사

다음에서 영감을 받았습니다:
- [Microsoft GraphRAG](https://github.com/microsoft/graphrag)
- [LightRAG](https://github.com/HKUDS/LightRAG)
- [Graphiti](https://github.com/getzep/graphiti)
- Palantir 스타일 온톨로지 접근법
- YoungHu 실사용 피드백, 방향성 논의 기여

---

## 면책 조항

**본인 책임 하에 사용하세요.** 이것은 연구 코드입니다. 추가 강화 없이 민감한 데이터 처리나 프로덕션 보안에 대한 어떠한 보증도 없습니다.
