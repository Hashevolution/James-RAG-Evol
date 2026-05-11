# Hacker News — Show HN 본문 (복붙용)

> 사이트: https://news.ycombinator.com/submit
> 형식: 제목 + URL + 본문(text)
> 발행 시점 권장: 한국 시간 23:00~01:00 (PST 오전 6~8시), 평일

---

## 제목

```
Show HN: JAMES – A laptop-runnable Graph-RAG engine with explicit ontology and a security layer
```

> HN 규칙: 제목에 마케팅 형용사("amazing", "revolutionary") 금지. 위 문구는 사실 위주.

## URL

```
https://github.com/Hashevolution/James-RAG-Evol
```

## 본문

```
Hi HN,

I've been building JAMES, a Graph-RAG knowledge engine that runs on a single
laptop and combines five things I usually see in isolation:

- Hybrid retrieval (vector + BM25 + keyword)
- A graph layer with 12 typed relations, not just embedding-similarity edges
- A 3-stage access-control model (RBAC + ABAC + instruction isolation)
- A self-evolution scaffold (feedback → patch proposal → 4-gate review → apply)
- 100% local execution via Ollama

Honest disclosure (so this doesn't read like marketing):
- It's v0.1.0-alpha. Each feature is a working prototype, not a finished
  product.
- Validation so far is synthetic + adversarial (83-item security suite,
  65-item diagnostic). Real-data validation is the focus of v0.2.
- Multimodal hooks exist but aren't fully wired.
- The self-evolution loop has not been stress-tested at scale.

What I'd love feedback on:
- Whether the 3-stage security layout is actually defensible or has obvious
  holes I'm missing
- Whether the 12 ontology relation types are too few / too many for typical
  retrieval workloads
- Bugs and design critique generally

Repo: https://github.com/Hashevolution/James-RAG-Evol
License: MIT

Happy to answer technical questions.
```

## 발행 직전 체크리스트

- [ ] HN 계정 카르마 ≥ 1 (Show HN은 신생 계정 노출이 낮음)
- [ ] 본문 80자 줄바꿈 (HN은 자동 정렬 안 함)
- [ ] 링크 1개만 (외부 GitHub URL은 위 URL 필드로, 본문 내 추가 링크는 최소)
- [ ] 평일 한국 시간 23:00~01:00 발행

## 발행 후

- [ ] 첫 1시간 내 모든 댓글에 답변 (HN 알고리즘은 초반 참여도를 본다)
- [ ] 비판은 정면 인정 ("you're right, that's an open issue, tracked as #...")
- [ ] 자기 글에 self-upvote 금지 (계정 패널티)
- [ ] URL을 `../session-2026-05-09-promotion-readiness.md`의 "공개 결과" 표에 기록
