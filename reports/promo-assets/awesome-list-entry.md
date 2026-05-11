# Awesome List 엔트리 (복붙용)

> 절차 전체는 `../session-2026-05-09-promotion-readiness.md` Phase 3 참고
> 각 리포의 CONTRIBUTING 규칙(알파벳 순/마침표/대문자/라이선스 태그)을 PR 전 반드시 확인

---

## 기본 엔트리 (변형용 베이스)

```
- [JAMES](https://github.com/Hashevolution/James-RAG-Evol) - Security-first, locally-runnable Graph-RAG engine with ontology, 3-stage access control (RBAC+ABAC+instruction isolation), and a self-evolution scaffold. `MIT`
```

## 리포별 변형

### 1. `Hannibal046/Awesome-LLM` (또는 RAG 카테고리)

권장 섹션: "Open-Source RAG" 또는 "Frameworks"

```
- [JAMES](https://github.com/Hashevolution/James-RAG-Evol) - Security-first, locally-runnable Graph-RAG engine with a 12-relation ontology and a self-evolution scaffold. `MIT`
```

### 2. `awesome-selfhosted/awesome-selfhosted`

권장 섹션: "Knowledge Management — Personal" 또는 "AI/ML"
주의: 이 리포는 **반드시 마침표 끝, 라이선스 태그 별도 컬럼** 규칙. CONTRIBUTING.md 재확인.

```
- [JAMES](https://github.com/Hashevolution/James-RAG-Evol) - Security-first, locally-runnable Graph-RAG knowledge engine with explicit ontology and a self-evolution scaffold. (Source Code) `MIT` `Python`
```

### 3. Awesome RAG / Awesome Graph-RAG 류

권장 섹션: "Frameworks" 또는 "Tools"

```
- [JAMES](https://github.com/Hashevolution/James-RAG-Evol) - Graph-RAG engine with 12 typed relations, 3-stage security model (RBAC+ABAC+instruction isolation), and a self-evolution scaffold. 100% local via Ollama. `MIT`
```

### 4. Awesome Self-Hosted AI / Awesome LocalLLaMA 류

```
- [JAMES](https://github.com/Hashevolution/James-RAG-Evol) - Graph-RAG knowledge engine that runs locally on Ollama, with built-in RBAC/ABAC, ontology relations, and a self-evolution scaffold. `MIT`
```

---

## PR 본문 템플릿

```markdown
Hi maintainers, this PR adds **JAMES**, an open-source (MIT) Graph-RAG knowledge engine.

- Repository: https://github.com/Hashevolution/James-RAG-Evol
- License: MIT
- Status: v0.1.0-alpha (research stage; honestly disclosed in README)

Why I think it fits this list:
- Built around RAG with a graph + ontology layer (12 relation types).
- Security model is explicit: RBAC + ABAC + instruction isolation + audit log.
- 100% locally runnable via Ollama.

I followed the contributing guide:
- [ ] Alphabetical order respected
- [ ] One-line description, no marketing language
- [ ] License tag included
- [ ] Link verified

Thanks for maintaining this list!
```

## PR 제출 전 체크리스트

- [ ] fork → 브랜치 `add-james-rag-evol` → 한 줄만 추가
- [ ] 알파벳 순서 유지 (J 위치)
- [ ] 마침표 / 대문자 / 라이선스 태그 형식이 그 리포 컨벤션과 일치
- [ ] PR 1개에 1개 리포만 (여러 리포 동시 추가 금지)
- [ ] 머지 시 URL을 `../session-2026-05-09-promotion-readiness.md`의 "공개 결과" 표에 기록
