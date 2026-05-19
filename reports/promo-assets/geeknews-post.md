# GeekNews 게시본 (복붙용)

> 사이트: https://news.hada.io
> 형식: 외부 링크 + 본문 (마크다운)
> **발행 완료: 2026-05-19 (id=29648)** → https://news.hada.io/topic?id=29648
> 본 아카이브는 발행 본문 시점을 기준으로 보존합니다. 발행 이후 main에 추가로 들어간 항목(예: Track 1 PR #324/#325)은 `launch-tracker.md`에만 기록.

---

## 제목 (택1)

- (A) **JAMES v0.3.0 — Platform Skeleton 도달: 로컬 Graph-RAG + 인지 미들웨어 Phase 2 + 외부 협업 시작 (오픈소스, alpha)** ← 발행본
- (B) 노트북에서 도는 Graph-RAG에 verification engine / planner / tool router를 얹다 — JAMES v0.3.0 (MIT)
- (C) 9일간 190 PR — JAMES v0.3.0 Platform Skeleton 공개 + Gemma 4 Challenge 2종 출품

**발행 시 선택: (A)** — "v0.3.0 / alpha / 오픈소스"를 박아두면 과장 광고로 안 읽힙니다.

## 외부 링크 URL

```
https://github.com/Hashevolution/James-RAG-Evol
```

## 본문 (마크다운, 복붙)

````markdown
## 한 줄 요약
보안을 디자인 원칙으로 다룬 100% 로컬 Graph-RAG 지식 엔진.
**v0.3.0 Platform Skeleton(2026-05-17)** 에 도달하면서, 인지 미들웨어 레이어가
설계가 아니라 **코드로 메인에 올라온 상태**입니다.

- GitHub: https://github.com/Hashevolution/James-RAG-Evol
- 현재 버전: **v0.3.0** (Foundation Hardening 6/6 axes 통과, 2026-05-13 게이트 클리어)
- 라이선스: MIT
- 외부 검증: [OpenSSF Best Practices **passing** 뱃지](https://www.bestpractices.dev/projects/12806) (Tiered 111%, project #12806)
- 별칭: "Mini Palantir" (Palantir는 Palantir Technologies의 상표, JAMES와 직접 관련 없음 — 단지 *typed-graph + audit 흔적 보존* 패턴이 닮았다는 비유)

![JAMES 3D 온톨로지 시각화](https://github.com/Hashevolution/James-RAG-Evol/blob/main/reports/promo-assets/screenshots/06-3d-graph.jpg?raw=true)

## v0.2 → v0.3, 9일간 무엇이 바뀌었나
1. **인지 미들웨어 레이어 Phase 2가 메인에 안착**
   - verification engine (PR #290) / planner·task decomposition (PR #297) / tool router (PR #295)
   - 검증·계획·도구 라우팅이 더 이상 design doc이 아니라 import 가능한 모듈
2. **Knowledge Cascade Phase A → E**: 213 entities / 656 relations 프로덕션 마이그레이션 완료
3. **3-stage 보안 파이프라인 유지**: 입력 `pre_check` → 검색 ABAC → 출력 `post_filter` + PII mask
4. **자가진화 감사 로그**: 모든 패치는 `approver_username` 보유, 우회 불가
5. **bcrypt 비밀번호 + SHA-256 투명 마이그레이션**(PR #173), ruff F-class baseline + GitHub Actions 린트 워크플로(PR #205)

## 외부에서 일어난 일 (혼자 만든 게 아니라는 증거)
- **Ali Afana (Provia 창업자, dev.to Featured)와 첫 외부 협업 진행 중** — LinkedIn DM 6턴 + dev.to 댓글 스레드
  - 공동 작업: 83-item injection regression 스위트 분리, v0.3 Gemma 4 변종 벤치(E4B / 26B MoE / 31B Dense)
  - 공동 산출물: [injection-fixtures schema v1.1](https://github.com/Hashevolution/James-RAG-Evol/blob/main/reports/promo-assets/injection-fixtures-schema-v0.md) (PR #311 → #317 → #322, Ali 제안 normalization 불변식·`expected_block_stage`·`catalog_context` 모두 반영, diff-log에 출처 명시)
  - 사전 등록: [3×3 평가 계획](https://github.com/Hashevolution/James-RAG-Evol/blob/main/docs/design/v0.3-gemma4-variant-3x3-eval-plan.md) (3 변종 × 3 온도 × 1 프롬프트 구조, 4 가설 + decision matrix, 단일 셀이 돌기 전에 PR #315로 잠금)
  - 외부 구현자 접점: [LLM Provider contract](https://github.com/Hashevolution/James-RAG-Evol/blob/main/docs/design/v0.3-llm-provider-contract.md) (PR #316, 6 required behaviors + reserved kwargs/env vars, ~30줄 Gemini API 백엔드 스케치 포함)
- **두 번째 협업 후보** — Matija Fućek(@mfucek_, naumu.ai)이 3D 시각화 트윗에 답글로 자기 프로젝트(plug-and-play 회사 두뇌 앱) 데모 공유, 협업 채널 열림
- **Gemma 4 Challenge 2개 트랙 제출 완료**:
  - Build with Gemma 4: [Building a Mini Palantir on gemma4:e4b](https://dev.to/hashevolution/building-a-mini-palantir-on-gemma4e4b-128k-context-lets-the-graph-actually-be-graph-rag-33fk)
  - Write with Gemma 4: [5 empty responses from gemma4:e4b. 4 hypotheses. 0 root cause.](https://dev.to/hashevolution/5-empty-responses-from-gemma4e4b-4-hypotheses-0-root-cause-1ggd) — fair-witness 형식, 실패를 가공하지 않고 보고

## 솔직한 한계 (alpha 단계, 숨길 게 없음)
- 인지 미들웨어 Phase 2는 메인에 올라왔지만 **다중 사용자·대규모 부하 검증은 v0.4 게이트**
- 멀티모달은 LLaVA·Whisper·ffmpeg까지 와이어드(working prototype). retrieval 통합은 v0.3.x ~ v0.4
- 자가진화 스캐폴드는 단일 사용자 환경 검증, 다중 승인자 워크플로 미검증
- **Gemma 4 E4B는 인지 단계에서 5번의 빈 응답**을 냈고, 4개 가설 모두 root cause를 확정하지 못한 상태(Write 트랙 글에 그대로 공개)

## 어디에 쓸 수 있나
- 사내 위키/노트를 외부 API에 보내지 않고 로컬에서만 다루고 싶을 때
- 추론 경로(`A --[CAUSES]--> X --[REQUIRES]--> Y` 형태의 typed graph_path)가 **응답과 함께 그래프로 노출되어야 하는** RAG 데모/연구
- 보안 RAG 패턴 레퍼런스 (3-stage 파이프라인, instruction isolation, bcrypt 마이그레이션, ruff baseline 모두 PR 단위로 공개)
- Plugin 진입점이 필요한 분 — `JAMES_PLUGINS` 로더와 Backend Protocol이 v0.3.x에서 안정화 중

## 시작하기
```bash
git clone https://github.com/Hashevolution/James-RAG-Evol
cp .env.example .env
pip install -r requirements.txt
ollama pull gemma2:2b      # GPU 없으면 이걸로 시작
python server_llmwiki.py   # http://localhost:8000
```

피드백/이슈 환영합니다. 특히 **(a) 인지 미들웨어 Phase 2의 verification engine 설계 반론, (b) Provider contract의 6 required behaviors 가운데 빠진 케이스, (c) injection-fixtures v1.1의 `catalog_context` 시맨틱 비판** 이 세 가지가 가장 도움이 됩니다.
````

## 태그 (발행 시 사용)

```
RAG, GraphRAG, 오픈소스, 로컬LLM, 보안
```

## 발행 전 체크리스트 (완료됨)

- [x] GeekNews 로그인 상태 확인 (D-Day 7일 락아웃 만료 — 2026-05-12 가입 후 2026-05-19 발행)
- [x] 외부 링크 URL이 GitHub 메인 리포지토리인지 확인
- [x] 본문 내 모든 링크 main 브랜치 영구 URL 확인 (PR #311/#315/#316/#317/#322 + dev.to 2편 + OpenSSF 뱃지)
- [x] 3D 시각화 이미지(`06-3d-graph.jpg?raw=true`) 미리보기에서 정상 로드 확인
- [x] 태그 5개 (RAG / GraphRAG / 오픈소스 / 로컬LLM / 보안)
- [x] 평일 발행 (2026-05-19)

## 발행 직후 24시간 운용 룰

- [ ] 댓글 알림 켜기 (Hada.io 알림 + 메일 둘 다)
- [ ] 기술 지적·반론은 2~6시간 내 답변, "alpha라 그렇습니다" 또는 "GitHub 이슈로 받겠습니다" 둘 중 정직한 쪽으로
- [ ] **본문 사후 편집으로 비판 맥락 지우지 않기** (사후 수정 이력이 GeekNews 컨벤션상 신뢰 손상)
- [x] 발행 URL을 `launch-tracker.md` "Social posts" 표에 K1 GeekNews 행으로 기록 (이번 PR에서 함께 처리)
- [ ] dev.to / LinkedIn / X 로 **자동 cross-post 금지** — K1은 한국어 채널 고유 컨텍스트, EN 채널은 E1 Show HN 본문(별도 D-Day 2026-05-26)이 담당

## 발행 후 main에 추가로 들어간 항목 (참고)

> 본 아카이브 본문에는 포함하지 않습니다. 향후 후속 채널(E1 Show HN 등)에서 별도 반영.

- **Track 1 Provider contract L1 wiring (PR #324 + #325)** — 2026-05-19 같은 날, K1 발행 직후 메인에 안착. 4주 앞당겨 출시. `core/reasoning/pipeline_synth.py` + 4개 모드 어댑터 + 337줄 conformance suite + 220줄 SDK leakage guard.

자세한 진행 상황은 `reports/promo-assets/launch-tracker.md` 참조.
