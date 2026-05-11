# GeekNews 게시본 (복붙용)

> 사이트: https://news.hada.io
> 형식: 외부 링크 + 본문 (마크다운)

---

## 제목 (택1)

- (A) JAMES — 보안을 1순위로 설계한 로컬 Graph-RAG 엔진 (오픈소스, alpha)
- (B) 노트북에서 도는 Graph-RAG + 보안 3-stage + 자가진화 스캐폴드 (MIT)

**추천: (A)** — "오픈소스 / alpha"를 제목에 박아 두면 과대광고로 안 읽힙니다.

## 외부 링크 URL

```
https://github.com/Hashevolution/James-RAG-Evol
```

## 본문 (마크다운, 복붙)

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

## 태그

```
RAG, GraphRAG, 오픈소스, 보안, 로컬LLM
```

## 발행 전 체크리스트

- [ ] 로그인 상태 확인
- [ ] 미리보기에서 줄바꿈/링크 정상 표시 확인
- [ ] 태그 5개 이내
- [ ] 평일 오전 9~11시 또는 오후 8~10시 발행 (노출률↑)

## 발행 직후 24시간

- [ ] 댓글 알림 켜기
- [ ] 부정·기술 지적은 2~6시간 내 답변 ("alpha라 그렇습니다", "GitHub 이슈로 받겠습니다")
- [ ] 본문 사후 편집으로 비판 맥락 지우지 않기
- [ ] URL을 `../session-2026-05-09-promotion-readiness.md`의 "공개 결과" 표에 기록
