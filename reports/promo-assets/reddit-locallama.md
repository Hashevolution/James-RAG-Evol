# r/LocalLLaMA 게시본 (복붙용)

> 서브: https://www.reddit.com/r/LocalLLaMA/
> 보조 서브: r/selfhosted, r/MachineLearning (Project flair)
> 발행 시점 권장: 주중 미국 동부 오전 9~11시 / 한국 시간 22:00~24:00

---

## 사전 확인 (필수)

- [ ] r/LocalLLaMA의 **Self-promotion 규칙** 재확인 (게시 전 sidebar 읽기)
- [ ] 계정 카르마 100+ 권장. 신생 계정은 자동 제거됨
- [ ] **Project / Tutorial flair** 선택
- [ ] 게시 빈도: 같은 프로젝트 30일 1회 권장

## 제목

```
[Project] JAMES: a security-first, locally-runnable Graph-RAG engine with explicit ontology (MIT, v0.1.0-alpha)
```

## 본문

```markdown
Hey r/LocalLLaMA,

I've been working on **JAMES**, an open-source Graph-RAG knowledge engine
that's designed to run entirely on a laptop with Ollama. Sharing because
the design choices might be useful even if you don't use the project.

**What's in it**

- Hybrid retrieval: vector (60%) + BM25 (20%) + keyword (20%)
- Graph layer with **12 typed relation kinds** (not just embedding edges)
- 3-stage access control built in: RBAC + ABAC + instruction isolation
- A self-evolution scaffold (feedback → patch proposal → 4-gate review)
- 11-trait tunable personality system
- Multi-LLM router (default Ollama, easy to add providers)

**Stack**

- FastAPI + Uvicorn / Python 3.11+
- ChromaDB + Sentence-Transformers (MiniLM)
- Ollama (gemma2:2b is enough to start; DeepSeek-Coder / LLaVA for code/vision)
- SQLite for audit + markdown wiki for the knowledge graph

**Honest status**

It's v0.1.0-alpha. Concretely:
- Synthetic + adversarial test suites pass (83-item security, 65-item
  diagnostic), but I have not stress-tested with real users yet.
- Multimodal is scaffolded but not fully wired.
- The self-evolution loop works end-to-end on toy data; needs more abuse.

**Why I'm sharing**

I want feedback before pushing toward v0.2. Specifically:
- Whether the 12-relation ontology is a sane size for real workloads
- Whether the security model has holes I'm not seeing
- Whether anyone wants to try it on their own wiki and report back

Repo: https://github.com/Hashevolution/James-RAG-Evol  
License: MIT

Happy to answer questions in the thread.
```

## 발행 직전 체크리스트

- [ ] Markdown 모드로 게시 (Rich text는 코드 블록이 깨질 수 있음)
- [ ] 스크린샷 1~2장 첨부 (이미지 댓글로 추가 가능)
- [ ] flair 설정 (Project / Tutorial / Discussion 중 선택)
- [ ] 첫 댓글에 본인이 "AMA-style" 한 줄 남기기 — 노출률↑

## 발행 후

- [ ] 모든 질문 24시간 내 답변
- [ ] 다운보트 1~2개는 정상, 본문 수정 금지
- [ ] 다른 서브로 크로스포스트는 24시간 후
- [ ] URL을 `../session-2026-05-09-promotion-readiness.md`의 "공개 결과" 표에 기록
