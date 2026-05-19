# Hacker News — Show HN 본문 (복붙용)

> 사이트: https://news.ycombinator.com/submit
> 형식: 제목 + URL + 본문(text)
> 발행 시점 권장: 한국 시간 23:00~01:00 (PST 오전 6~8시), 평일
> **D-Day: 2026-05-26 (E1)**
> **v0.3.0 refresh: 2026-05-19** — v0.1.0-alpha → v0.3.0 / Cognitive Middleware Phase 2 코드 안착 / Track 1 (Provider contract L1 wiring + conformance + plugin loader) 안착 / Ali Afana 외부 협업 / OpenSSF passing 뱃지 반영

---

## 제목 (택1, HN 규칙: 마케팅 형용사 금지, 사실 위주)

- (A) **Show HN: JAMES v0.3.0 – a laptop-runnable Graph-RAG engine with typed ontology, 3-stage security, and a swappable LLM provider contract** ← 추천
- (B) Show HN: JAMES – a local Graph-RAG engine with verification engine, planner, and tool router shipping on main
- (C) Show HN: JAMES v0.3.0 – Graph-RAG + cognitive middleware (verification / planner / tool router) running on Ollama

**추천: (A)** — "v0.3.0"으로 vaporware 의심 차단, "laptop-runnable" + "swappable LLM provider"가 HN audience의 두 가지 trigger.

## URL

```
https://github.com/Hashevolution/James-RAG-Evol
```

## 본문 (복붙)

```
Hi HN,

I've been building JAMES, a local-first Graph-RAG knowledge engine that runs
on a single laptop. v0.3.0 (Platform Skeleton) shipped on 2026-05-17 after
v0.2 closed all 6 Foundation Hardening axes.

What's in v0.3.0 that I think is interesting enough for Show HN:

- A cognitive middleware layer that's no longer a design doc — it's code
  on main: verification engine (#290), planner / task decomposition (#297),
  tool router (#295). The reasoning pipeline now goes through these as
  callable modules, not future work.
- An LLM provider contract (docs/design/v0.3-llm-provider-contract.md)
  with 6 required behaviors, reserved kwargs, reserved env vars, and a
  337-line conformance test suite + a 220-line SDK-leakage guard. External
  implementers (Gemini API backend, anyone else's) can wire against the
  contract today; the synth call-sites and 4 mode adapters all go through
  it (PRs #324 / #325 / #326).
- A plugin loader (JAMES_PLUGINS env) with a 204-line loader test suite
  (PR #326), so third-party reasoning backends and tools are an entry-point
  surface, not a fork.
- A 3-stage security pipeline: input pre_check → retrieval-stage ABAC →
  output post_filter + PII mask. RBAC + ABAC + instruction isolation. All
  self-evolution patches carry an approver_username in the audit log; the
  human gate cannot be bypassed.
- 12-type typed ontology, not embedding-similarity edges. Graph paths
  surface in the UI as A --[CAUSES]--> X --[REQUIRES]--> Y form alongside
  the response.
- A Knowledge Cascade (Phase A → E) production-migrated 213 entities /
  656 relations.
- 100% local via Ollama. ollama pull gemma2:2b and you have a working
  starting point. Larger models (gemma4:e4b 128k context, llama3.1, etc.)
  all swap in by env var.

External validation (so this isn't just my own claims):

- OpenSSF Best Practices passing badge, Tiered 111%, project #12806
  (https://www.bestpractices.dev/projects/12806)
- First external collaboration in progress: Ali Afana (Provia founder,
  dev.to Featured author) — co-authored injection-fixtures schema v1.1
  (normalization invariants, expected_block_stage enum, catalog_context
  field for catalog poisoning), pre-registered 3×3 Gemma 4 variant
  evaluation plan (3 variants × 3 temperatures, 4 hypotheses + decision
  matrix locked before any cell runs).
- Two Gemma 4 Challenge submissions in progress: a Build-track article
  on running it on E4B at 128k context, and a Write-track fair-witness
  field report on 5 cognitive-stage empty responses where 4 hypotheses
  failed to identify a root cause (the writeup leaves the failure on the
  table rather than fitting a story).

Honest limitations (this is still alpha):

- Multi-user / large-scale load: not yet validated. That's the v0.4 gate.
- Multimodal: LLaVA / Whisper / ffmpeg are wired as working prototypes;
  retrieval integration is v0.3.x ~ v0.4.
- Self-evolution: validated single-user only. Multi-approver workflow
  is not yet built.
- Gemma 4 E4B currently returns empty responses on the cognitive stage
  in ways I haven't fully diagnosed. Published as a Write-track article
  rather than hidden.

What I'd value feedback on, in priority order:

1. Holes in the LLM provider contract — the 6 required behaviors are the
   surface that everyone else's backend has to honor. If you've shipped
   a backend abstraction before and one of these would have bitten you,
   I want to hear it before someone wires a real Gemini / Claude / vLLM
   backend against it.
2. The 3-stage security pipeline — is input pre_check + retrieval ABAC +
   output post_filter the right partitioning, or does data_exfiltration
   need the protective surface earlier than output stage?
3. The 12 ontology relation types — too few / too many / wrong shape for
   typical RAG workloads you've actually run?
4. The injection-fixtures schema (v1.1 just merged) — does catalog_context
   as list[string] capture the 1-of-N-poisoned signal cleanly?

Architecture doc: docs/ARCHITECTURE.md
Provider contract: docs/design/v0.3-llm-provider-contract.md
3×3 evaluation plan: docs/design/v0.3-gemma4-variant-3x3-eval-plan.md
Injection fixtures schema: reports/promo-assets/injection-fixtures-schema-v0.md

Repo: https://github.com/Hashevolution/James-RAG-Evol
License: MIT
v0.3.0 release: 2026-05-17
Maintainer: Jiwon (solo; Korea-based; first external collaborator joined
2026-05-16)

Happy to answer technical questions. Will be in the thread the next ~24
hours.
```

> 본문 글자 수: ~3,400자 (HN 평균 Show HN 본문보다 다소 길지만 사실 밀도가 높아 OK).
> 줄바꿈은 80자 hard-wrap (HN은 자동 정렬 없음, 위 본문은 이미 wrap 완료).
> 본문 내 링크는 외부 1개(OpenSSF) + 리포 1개(맨 아래). 나머지는 repo-relative path 텍스트만 — HN audience가 클릭하지 않고도 어디를 봐야 할지 안다.

## 발행 직전 체크리스트

- [ ] HN 계정 카르마 ≥ 1 (Show HN은 신생 계정 노출이 낮음 — 1점이라도 미리 확보)
- [ ] 본문 80자 hard-wrap 유지 (위 본문은 wrap 완료 상태)
- [ ] 외부 링크 2개 이하 (OpenSSF + repo URL — 다른 PR 번호는 텍스트로만 언급)
- [ ] **평일 한국 시간 23:00~01:00 발행** (PST 오전 6~8시 — HN front-page 사이클의 시작 지점)
- [ ] 발행 직전 1회 더 본문 fact-check (PR 번호 #290/#295/#297/#324/#325/#326 모두 main에 머지된 상태인지)
- [ ] URL 필드는 GitHub repo만 (Hashnode cross-post URL 등 다른 곳 금지 — HN 알고리즘은 GitHub repo direct submission을 선호)

## 발행 직후 1시간

- [ ] **모든 댓글에 1시간 내 답변** (HN 알고리즘은 초반 60분 참여도가 front-page 진입의 결정 변수)
- [ ] 비판은 정면 인정 — "you're right, that's an open issue, tracked as #..." 형식. 방어하지 말 것
- [ ] self-upvote 금지 (계정 패널티)
- [ ] flag 받으면 vouch 요청 금지 (HN 컨벤션상 부적절)
- [ ] 본문 사후 편집 금지 — 비판 맥락 지우는 행위로 인식됨

## 발행 후 24시간

- [ ] front-page 진입 여부 확인 (보통 0~6시간 내 결정)
- [ ] 점수 ≥ 50 / 댓글 ≥ 30 도달 시 별도 X 트윗 + LinkedIn 게시로 social signal 흘림 (단, GeekNews 한국어 채널과는 분리 — channel separation discipline)
- [ ] front-page 진입 못해도 thread에서 받은 substantive critique은 GitHub issue로 변환 (HN audience의 신호 가치는 점수와 무관하게 큼)
- [ ] URL을 `reports/promo-assets/launch-tracker.md` "Social posts" 표에 E1 Show HN 행으로 기록

## 비교: K1 GeekNews 본문과의 의도적 차이

| 항목 | K1 GeekNews (한국어, 2026-05-19) | E1 Show HN (영어, 2026-05-26) |
|---|---|---|
| 길이 | ~2,000자 (한글) | ~3,400자 (영문, 80자 wrap) |
| 톤 | 비유 허용 ("Mini Palantir", 별칭 명시) | 비유 최소화 (HN audience는 marketing 신호 민감) |
| 외부 협업 | Ali / Matija 두 명 다 언급 | Ali 1명 + 사실만 (Matija는 아직 sustained 단계 아님) |
| 한계 섹션 | 4개 항목 | 4개 항목 + Gemma 4 E4B 빈응답 사실 별도 강조 |
| 피드백 요청 | 3가지 (verification engine / Provider contract / schema) | 4가지 우선순위 매김 (priority order 명시 — HN convention) |
| 이미지 | 3D 온톨로지 시각화 1장 | 텍스트 only (HN은 이미지 미지원) |
| 링크 정책 | dev.to / Hashnode / GitHub 다중 OK | repo-relative path만, 외부 클릭 링크 2개로 제한 |
