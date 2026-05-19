# Velog — JAMES 소개 (한국어 cross-post 본문)

> 사이트: https://velog.io
> 형식: 마크다운 (Velog 웹 UI에 복붙)
> 원본: https://dev.to/hashevolution/building-a-mini-palantir-a-local-graph-rag-engine-with-ontology-security-and-self-evolution-1914
> canonical_url: 위 dev.to URL (Velog는 Series 설정 옵션에 canonical 박스 있음)
> 발행 시점 권장: K1 GeekNews 발행 후 24~72시간 (K1 검색 트래픽 흡수 + Velog SEO 누적)

---

## 제목

```
JAMES — 노트북에서 도는 보안 중심 Graph-RAG 엔진 만들기 (alpha, v0.3.0)
```

## 시리즈 / 태그

- 시리즈: `JAMES Graph-RAG`
- 태그: `RAG`, `GraphRAG`, `오픈소스`, `로컬LLM`, `Python`

## 커버 이미지

`reports/promo-assets/screenshots/06-3d-graph.jpg` (3D 온톨로지 시각화) — Velog 업로드 후 cover로 지정

## 본문 (복붙)

````markdown
> **TL;DR**
> [PROJECT JAMES](https://github.com/Hashevolution/James-RAG-Evol)는 보안을 디자인 원칙으로 다룬, 100% 로컬에서 도는 Python 기반 Graph-RAG 지식 엔진입니다. 12-type 명시 온톨로지, 3-stage 접근제어(RBAC + ABAC + Instruction Isolation), 감사 로그 기반 자가진화 스캐폴드, Ollama 로컬 실행이 한 저장소에 들어있습니다. MIT, **v0.3.0 alpha**, [OpenSSF Best Practices passing 뱃지](https://www.bestpractices.dev/projects/12806).

![JAMES 3D 온톨로지 시각화](https://github.com/Hashevolution/James-RAG-Evol/blob/main/reports/promo-assets/screenshots/06-3d-graph.jpg?raw=true)

## 왜 만들었나

로컬 LLM에 사내 위키나 코드베이스, 문서 저장소를 물려본 사람이라면 보통 세 가지 벽에 부딪힙니다.

1. **클라우드 RAG 서비스**는 모든 걸 자기네 클라우드로 보내라고 합니다. 프로토타입은 가능하지만 민감한 데이터는 곤란합니다.
2. **셀프호스트 RAG 프레임워크**는 보통 둘 중 하나입니다. (a) 인프라가 너무 무겁거나(Kubernetes급), (b) 보안 프리미티브가 부족하거나(role 분리·감사 로그 부재).
3. **대부분의 Graph-RAG 구현**은 그래프를 벡터 위에 얹은 보조 기능으로 다룹니다. 그래프가 보안 경계나 추론 경로에 **실제로 참여**하는 경우는 드뭅니다.

저는 **Palantir Foundry 식 멘탈 모델** — 명시 온톨로지, capability 토큰 보안, 전체 감사 로그 — 을 노트북에서 한 사람이 굴릴 수 있는 크기로 압축하고 싶었습니다. MIT 라이선스, 클라우드 계정 없이.

그게 PROJECT JAMES입니다.

> Palantir®는 Palantir Technologies Inc.의 등록상표이며, PROJECT JAMES와 직접적인 관련은 없습니다. "Mini Palantir"라는 표현은 *온톨로지와 감사 로그 디자인 패턴*의 비유이지 제품 주장이 아닙니다.

## 무엇이 들어있나

같은 Python 저장소에 잘 같이 들어있지 않은 다섯 가지:

| # | 기능 | 설명 |
|---|---|---|
| 1 | **온톨로지 기반 Graph-RAG** | 12종 관계 타입. 벡터 유사도 너머의 의미를 표현 |
| 2 | **3-stage 보안 파이프라인** | 입력 `pre_check` → 검색 ABAC → 출력 `post_filter` + PII mask |
| 3 | **자가진화 스캐폴드** | 피드백 → 패치 제안 → 4-Gate 검증 → 회귀 시 자동 롤백, 모든 패치는 `approver_username` 감사 |
| 4 | **100% 로컬** | Ollama 기반, `gemma2:2b`면 노트북에서 돕니다 |
| 5 | **명시적 추론 경로** | 모든 응답이 traversal한 graph_path를 함께 노출 |

## 한 줄 쿼리 라이프사이클

```python
def answer(query: str, user: User) -> Response:
    # 1. 입력 검사 — 31개 이상 injection 패턴 + 파괴 명령 hard-refuse
    if security_layer.pre_check(query) == BLOCK:
        return RESPONSE_BLOCKED  # byte-identical block message

    # 2. 하이브리드 검색 — Vector + BM25 + keyword + name match
    candidates = hybrid_search(query, top_k=10)

    # 3. 그래프 확장 — 사용자가 읽을 수 있는 엔티티만 traversal
    paths = graph_engine.expand(
        seed_entities=candidates,
        role=user.role,                # RBAC
        sensitivity_ceiling=user.tier, # ABAC
        max_depth=3,
    )

    # 4. LLM 추론 (router 경유)
    answer, reasoning_trace = llm.reason(query, paths)

    # 5. 출력 필터 — PII mask, role 기반 redact
    return output_filter.apply(answer, user.role)
```

핵심은 step 3. **그래프 traversal 자체가 접근제어 대상**입니다. 최종 출력만 가리는 게 아닙니다. `confidential` 엔티티는 `employee` 사용자에게는 *애초에 traversal되지 않습니다*. 어떤 jailbreak 프롬프트도 모델이 한 번도 본 적 없는 컨텍스트를 흘리게 만들 수는 없습니다.

## 자가진화 스캐폴드 — 정확히 무엇을 하고 무엇을 하지 않나

이 부분을 설명하면 사람들이 가장 긴장하므로 정확히:

**하는 것:**

1. `/query/` 응답에서 피드백 신호 수집 (thumbs, latency, hallucination flag)
2. 후보 패치 제안 생성 (LLM 보조)
3. 4-Gate 파이프라인으로 검증:
   - **Gate 1**: syntactic — 파싱, import, 즉시 폭발 없는지
   - **Gate 2**: 테스트 — 기존 테스트 통과
   - **Gate 3**: 벤치 — STEP 7 regression 허용 범위 내
   - **Gate 4**: 인간 승인 — `approver_username` 필수
4. known-good 백업과 함께 패치 적용
5. 적용 후 회귀 감지 시 **자동 롤백**

**하지 않는 것:**

- `approver_username` 없는 자동 배포는 절대 없습니다. `JAMES_AUTO_APPROVE=1` 설정해도 `JAMES_DEV_MODE=1`이 함께 없으면 서버가 시작 자체를 거부합니다.
- 신뢰 경계(auth, policy, sandbox)는 `architecture` 라벨 PR 없이 수정되지 않습니다.
- `core/security_layer.py`, `core/policy_engine.py` 같은 보안 critical 파일은 자동 패치 대상이 아닙니다.

기본 배포는 `JAMES_ENABLE_EVOLUTION=0`입니다. opt-in.

## 솔직한 한계

alpha입니다. 안 되는 것들:

- **다중 사용자 / 대규모 부하**: 검증 안 됨, v0.4 게이트.
- **멀티모달 retrieval**: Whisper / Tesseract 인덱싱은 작동, retrieval 1급 시민화는 v0.3.x ~ v0.4.
- **자가진화**: 단일 사용자 환경 검증만. 다중 승인자 워크플로 미구현.
- **Plugin API**: v0.3에서 안착(아래 업데이트 박스 참조). 도메인 팩은 v1.0까지 의도적으로 차단.

## 신뢰 신호 (자기 평가가 아닌 외부 검증)

- **[OpenSSF Best Practices passing 뱃지](https://www.bestpractices.dev/projects/12806)** (Tiered 111%, 2026-05-11)
- **GitHub Releases 8개** (v0.1.0 → v0.3.0)
- **정적 분석** — ruff F-class (F821 + F541 + F401 + F841)가 모든 PR에 GitHub Actions로 강제
- **보안 테스트** — 83항목 적대 regression suite, 17항목 패스워드 regression
- **취약점 공개** — GitHub Private Vulnerability Reporting 활성화, 백업 채널은 `SECURITY.md`
- **MIT 라이선스** + `CONTRIBUTING.md` 테스트 정책 게이트

## 시작하기

```bash
git clone https://github.com/Hashevolution/James-RAG-Evol
cd James-RAG-Evol

# 환경 설정
cp .env.example .env
# .env 편집 — JAMES_API_KEY, JAMES_JWT_SECRET (32자 랜덤) 설정

# 설치 (Python 3.11+)
pip install -r requirements.txt

# 모델 풀
ollama pull gemma2:2b   # 1.6 GB, 노트북에서 돌아갑니다

# 시작
python server_llmwiki.py
```

`http://localhost:8000`로 접속.

---

## 📦 Update — v0.3.0 Platform Skeleton (2026-05-17 발행)

본 글은 원래 v0.2.0 시점(2026-05-12) 작성본의 한국어 번역입니다. 그 사이 메인 저장소가 다음 단계로 넘어갔으므로 핵심 변화만 압축해서 덧붙입니다.

| 항목 | v0.2.0 (원본 발행 시) | v0.3.0 (현재 main) |
|---|---|---|
| Foundation Hardening | 5/6 axes engineering-complete | **6/6 axes 통과, gate clear** |
| 인지 미들웨어 레이어 | 설계 문서 | **코드로 main 안착** — verification engine (#290), planner (#297), tool router (#295) |
| Knowledge Cascade | Phase A | **Phase A → E**, 213 entities / 656 relations 프로덕션 마이그레이션 |
| Plugin API | "v0.3 예정" | **`JAMES_PLUGINS` 로더 + 204-line 테스트 슈트** (#326) — entry-point 기반, 포크 불필요 |
| LLM Backend 추상화 | 단일 Ollama 하드코딩 | **Provider Contract + 337-line conformance suite + 220-line SDK leakage guard** (#316/#324/#325) — Gemini API, Claude, vLLM 등 swap 가능 |
| 외부 협업 | 0 | **Ali Afana (Provia 창업자, dev.to Featured)** 와 6턴 LinkedIn DM + injection-fixtures schema v1.1 공동 산출 (#311 → #317 → #322) |
| 사전 등록 실험 설계 | 없음 | **3×3 Gemma 4 변종 평가 계획** (3 variants × 3 temperatures, 4 가설 + decision matrix 단일 셀 실행 전 lock, #315) |
| Gemma 4 Challenge | — | **Build + Write 양 트랙 제출 완료** |
| 시각 자산 | README 텍스트 only | **6장 스크린샷 + 3D 온톨로지 hero 이미지** (#304) |

### 한 줄 요약

> v0.2.0이 "보안 RAG가 진짜로 구현 가능한가" 였다면, v0.3.0은 **"이 보안 RAG를 다른 사람이 backend / plugin 단위로 교체하며 쓸 수 있게 만들었나"** 입니다. 인지 미들웨어 레이어 + Provider Contract + Plugin Loader + 외부 협업이 그 답입니다.

### 더 보기

- v0.3.0 GeekNews 게시본: https://news.hada.io/topic?id=29648
- Architecture: [`docs/ARCHITECTURE.md`](https://github.com/Hashevolution/James-RAG-Evol/blob/main/docs/ARCHITECTURE.md)
- Provider Contract: [`docs/design/v0.3-llm-provider-contract.md`](https://github.com/Hashevolution/James-RAG-Evol/blob/main/docs/design/v0.3-llm-provider-contract.md)
- 3×3 평가 계획: [`docs/design/v0.3-gemma4-variant-3x3-eval-plan.md`](https://github.com/Hashevolution/James-RAG-Evol/blob/main/docs/design/v0.3-gemma4-variant-3x3-eval-plan.md)
- Gemma 4 Build 트랙: https://dev.to/hashevolution/building-a-mini-palantir-on-gemma4e4b-128k-context-lets-the-graph-actually-be-graph-rag-33fk
- Gemma 4 Write 트랙: https://dev.to/hashevolution/5-empty-responses-from-gemma4e4b-4-hypotheses-0-root-cause-1ggd

## 피드백 환영합니다

특히 다음 세 가지에 대한 비판이 가장 도움이 됩니다:

1. **보안 모델의 적대적 리뷰** — 경계, 감사 로그, hard-refuse 정책. role 분리를 깰 수 있다면 Private Advisory로 제보 부탁드립니다.
2. **두 번째 사용자 corpus** — 자체 위키/문서 저장소에 `scripts/bench.py --suite=step7 --check`를 돌려볼 수 있는 분.
3. **자가진화 스캐폴드 critique** — 4-Gate가 *충분한* 게이팅인지, Gate 4 앞에 한 단계 더 필요한지.

저장소: https://github.com/Hashevolution/James-RAG-Evol
이슈: GitHub Issues
보안 보고: GitHub Private Vulnerability Reporting (선호), `karu-7@hanmail.net` (백업)

위에 무언가 만들어 보신다면 듣고 싶습니다.

---

🤖 honest disclosure: 본 글은 AI 보조로 초안 작성 후 저자가 검토·수정했습니다. 코드베이스, 디자인 결정, 한계 서술은 모두 링크된 저장소에서 검증 가능합니다.
````

## 발행 직전 체크리스트

- [ ] Velog 로그인 + 시리즈 `JAMES Graph-RAG` 미리 생성
- [ ] **canonical URL 박스에 dev.to 원본 입력** (Velog 글 설정 → 외부 글 캐노니컬) — Google duplicate content 패널티 회피
- [ ] 커버 이미지 업로드 (`06-3d-graph.jpg`)
- [ ] 태그 5개 (RAG / GraphRAG / 오픈소스 / 로컬LLM / Python) — Velog 상단 검색 노출에 유리한 태그 우선
- [ ] **발행 시점**: K1 GeekNews 발행 후 24~72시간 (현재 K1이 2026-05-19 발행 → 권장 5/20~5/22)
- [ ] 본문 내 라이브 링크 모두 확인 (GitHub raw 이미지 URL + PR 번호 링크 + 외부 dev.to/Hashnode/news.hada.io)

## 발행 직후

- [ ] **K1 GeekNews 본문 댓글로 cross-post 금지** — 한국 커뮤니티 컨벤션상 자기 글 홍보 댓글은 비호감
- [ ] Velog 알림 + Disqus 댓글 켜기
- [ ] 발행 후 첫 48시간 댓글 모니터링 (한국 개발자 critique은 dev.to보다 직설적)
- [ ] URL을 `launch-tracker.md` "Social posts" 표에 K4 Velog 행으로 기록
- [ ] **dev.to 원본 댓글에 Velog 한국어 cross-post 안내 금지** — 채널 audience 다름, Ali가 글을 모니터링하는 채널은 dev.to 댓글이라 우리 promo 신호가 working dialogue를 흐림

## 발행 후 6~12개월

- [ ] Velog 글 조회수 추이 기록 (월 1회) — Google SEO 누적 효과 측정
- [ ] 동일 글에 v0.4.0 / v1.0 시점 업데이트 박스 추가 (in-place 갱신 패턴, K1 GeekNews 아카이브와 동일 원칙)
