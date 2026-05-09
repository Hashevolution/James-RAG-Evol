# JAMES External Promotion Channel Catalog

> Living document. Append-only activity log at the bottom (§10).
> Governed by `docs/handovers/v0.2.1-business-track.md` §12.
> Read §12 first; this file is the catalog, §12 is the discipline.

---

## 0. How to use this file

This file lists every channel JAMES could plausibly use to reach
external audiences, organized by category. Each channel has:

- **Earliest cycle**: when it becomes appropriate to use
- **Effort**: realistic time investment
- **Risk**: trust / framing risk if exercised badly
- **Status** (where applicable): never used / queued / exercised / closed

When a channel is exercised, append an entry to §10 (activity log).
Do not edit historical entries.

When a channel turns out to be wrong for JAMES (e.g. audience
mismatch, competitor saturation), mark its status as "closed" with
rationale. Do not delete the row.

This catalog records the SET of options. Whether to exercise each one
is governed by `v0.2.1-business-track.md` §12 (forbidden categories,
message tier per cycle, approval rules).

---

## 1. Core principle

**Cycle-aligned messaging + radical honesty + gradual expansion.**

JAMES's existing README honesty ("NOT production-ready", "scaffolded
prototypes") is the project's biggest trust asset. Every external
post must match that voice. See business-track §12 for the four
message tiers and forbidden categories.

---

## 2. Global OSS channels (English-primary)

### 2.1 GitHub-native

| Channel | Earliest | Effort | Risk | Status |
|---|---|---|---|---|
| GitHub Topics on repo | v0.2 (now) | 5 min | none | queued |
| GitHub README polish (badges, screenshots) | v0.2 | 1 hr | low | partial |
| GitHub Releases (semantic version notes) | v0.2 | 30 min/release | low | active |
| GitHub Discussions enabled | v0.2 | 5 min | low | unknown |
| OpenSSF Best Practices Badge | v0.2 | 30 min | none | queued |
| GitHub Sponsors enabled | v0.3 | 1 hr | low | not yet |

Recommended GitHub Topics: `graphrag`, `rag`, `local-llm`, `korean`,
`rbac`, `self-hosted`, `audit-log`, `policy-engine`, `ollama`, `ontology`.

### 2.2 Awesome lists

PRs to high-traffic curated lists. Risk is low because each list has
its own gatekeeping; rejection is OK and not visible.

| List | Indicative stars | Section to target | Earliest |
|---|---|---|---|
| Shubhamsaboo/awesome-llm-apps | 100K+ | RAG apps | v0.2 |
| punkpeye/awesome-mcp-servers | 80K+ | "Planned" or community section | v0.3 (after MCP server lands) |
| (current top) awesome-graphrag | varies | main list | v0.2 |
| (current top) awesome-self-hosted-ai | varies | RAG / knowledge | v0.2 |
| (current top) awesome-rag | varies | open source frameworks | v0.2 |
| (current top) awesome-ai-security | varies | RBAC / audit tooling | v0.3 |
| (current top) awesome-korean-llm | varies | Korean-language tooling | v0.2 |
| (current top) awesome-ontology | varies | tooling | v0.3 |

Verify list is still maintained (commit in last 6 months) before
submitting. Stale awesome lists are audience-dead.

### 2.3 Aggregators (high-leverage, single-shot)

| Channel | Earliest | Effort | Risk | Notes |
|---|---|---|---|---|
| Hacker News (Show HN) | post-v0.2 | 4 hr (prep + monitoring) | high | One-shot. Title must include "Show HN:" prefix. Tuesday/Wednesday morning EST. Pre-warm 5 technical responders. |
| Reddit r/LocalLLaMA | post-v0.2 | 1 hr | medium | Local LLM audience direct match |
| Reddit r/selfhosted | post-v0.2 | 1 hr | low | Privacy-conscious audience |
| Reddit r/MachineLearning | post-v0.4 | 1 hr | high | Skeptical/academic; requires benchmarks |
| Twitter/X thread | v0.2 | 1 hr/thread | low | Architecture-decision threads work better than launch announcements |
| LinkedIn (operator account) | v0.2 | 30 min/post | low | Korean B2B audience, useful pre-grant |
| Mastodon (Fosstodon, hachyderm) | v0.2 | 30 min | low | OSS-friendly, lower volume |

### 2.4 AI/LLM ecosystem registries

| Registry | Earliest | Notes |
|---|---|---|
| modelcontextprotocol.io (MCP server registry) | v0.3 | After Plugin API + first MCP server land |
| LangChain Hub (community retriever) | v0.3 | PR to LangChain core repo with retriever class |
| LlamaIndex Hub | v0.3 | Similar mechanism |
| HuggingFace Spaces (live demo) | v0.3 | After v0.3 stabilizes |
| HuggingFace OpenRAG leaderboard | v0.3 | After RAGAS lands (Axis 2-B) |
| MTEB (embedding leaderboard) | optional | If JAMES exposes its embedder |
| LegalBench leaderboard | optional / v1.0 | Domain-specific; only if relevant pack ships |

---

## 3. Korean dev community channels

### 3.1 Aggregators

| Channel | URL | Earliest | Effort | Notes |
|---|---|---|---|---|
| GeekNews (긱뉴스) | news.hada.io | v0.2 | 30 min | Korean Hacker News equivalent, 1-person OSS friendly |
| Disquiet | disquiet.io | v0.2 | 30 min | Side-project + 1-person dev community |
| OKKY | okky.kr | v0.2 | 1 hr | High-traffic Korean dev board |
| 디스코드 / 오픈채팅 (모두의연구소, AI 마법학교 등) | varies | v0.2 | ongoing | Direct feedback channel |
| velog.io | velog.io | v0.2 | 1 hr/post | Korean dev blog platform |
| brunch.co.kr | brunch.co.kr | v0.2 | 1 hr/post | Long-form Korean writing platform |

### 3.2 Facebook / Slack groups

| Group | Indicative members | Earliest | Notes |
|---|---|---|---|
| Generative AI Korea (FB) | ~100K+ | v0.2 | AI-only Korean audience |
| 한국 머신러닝/딥러닝 (FB) | varies | v0.2 | Broader ML audience |
| 모두의연구소 Slack/Discord | varies | v0.2 | Direct AI practitioners |

### 3.3 Korean tech media (operator outreach, no PR needed)

| Outlet | Format | Earliest |
|---|---|---|
| 플래텀 (Platum) | startup interview | v0.4 (post-PoC) |
| 더브이씨 (theVC) | startup database + article | v0.4 |
| 벤처스퀘어 | startup interview | v0.4 |
| AI 타임스 | AI vertical media | v0.3 |
| 디지털타임스 IT | 산업 섹션 | v0.4 |
| 전자신문 AI | 산업 섹션 | v0.4 |
| 바이라인네트워크 | 인터뷰 | v0.4 |

### 3.4 Korean conferences

| Event | Format | Submission window | Earliest |
|---|---|---|---|
| PyCon Korea | lightning talk (5 min) or talk (30 min) | varies | v0.2 close |
| 모두콘 (Modulabs) | community AI conf | varies | v0.2 close |
| GDG DevFest Korea | community track | annual | v0.2 close |
| FOSSASIA Summit | OSS track | annual | v0.3 |
| DEVIEW (Naver) | major industry conf | invite + CFP | v0.4+ |
| ifkakao | major industry conf | invite + CFP | v0.4+ |
| KCC 한국컴퓨터종합학술대회 | academic | annual | v0.4 (with paper) |
| 한국정보과학회 학술발표회 | academic | annual | v0.4 |

---

## 4. Content marketing (long-term assets)

### 4.1 Technical blog series

| Topic | Language | Earliest | Notes |
|---|---|---|---|
| "Why we built Graph-RAG with built-in RBAC" | EN | v0.2 | Architecture decision narrative |
| "왜 우리는 한국어 보안 RAG를 처음부터 다시 만들었나" | KO | v0.2 | Korean translation/adaptation |
| "Mother platform vs vertical product: a 22-month decision" | EN | v0.2 | Strategic frame, references mother-platform contract |
| "Self-evolution scaffolding: what we built, what we deliberately don't auto-deploy" | EN | v0.3 | Axis 5 narrative |
| "Why JAMES will not become an agent framework" | EN | v0.3 | Anti-feature narrative |
| "1인 + Claude로 대형 객체를 분해한 회고" | KO | v0.2 | Existing decomposition story |

Platform: dev.to + Medium for English; velog.io + brunch.co.kr for Korean.
Cadence: biweekly (1 EN + 1 KO every 2 weeks is sustainable for solo+Claude).

### 4.2 Video / YouTube

| Format | Earliest | Effort | Notes |
|---|---|---|---|
| 5-min product demo | v0.2 close | 4-8 hr | Vision + differentiation |
| Architecture deep-dive (15 min) | v0.3 | 8 hr | For senior engineers |
| Live coding stream | v0.2 (recurring) | 2 hr/session | Trust signal via process visibility |
| 1-min Korean shorts (YouTube Shorts / TikTok) | v0.3 | 1 hr each | Korean dev-curious audience |

### 4.3 Podcast / interview

| Show | Audience | Earliest |
|---|---|---|
| Practical AI (EN) | global ML practitioners | v0.4 |
| Latent Space podcast (EN) | LLM developers | v0.4 |
| 코딩가이 / 나는개발자 (KO) | Korean devs | v0.3 |
| 디일레마, 빅데이터 잡탕밥 등 | Korean tech podcasts | v0.4 |

---

## 5. Capital channels

### 5.1 Non-dilutive (Korean government)

| Program | Indicative size | Cycle | Earliest |
|---|---|---|---|
| 예비창업패키지 (창업진흥원) | ~1억 | annual Feb-Mar | start drafting v0.2 |
| NIPA AI 바우처 | 1-3억 | rolling | v0.3 |
| K-Global 300 | 3-5천만 + mentoring | annual | v0.3 |
| 청년창업사관학교 (만 39 이하) | ~1억 | annual | v0.2 |
| 산학연 컨소시엄 | varies | varies | v0.4 |
| KISA 정보보호 R&D | varies | annual | v0.3 (after RBAC matures) |

### 5.2 Dilutive

| Source | Indicative size | Earliest |
|---|---|---|
| Korean VC seed (본엔젤스, 매쉬업, 카카오벤처스, 네이버 D2SF, 알토스) | 3-10억 | post-v0.4 PoC |
| TIPS 추천 | 10억 + mentoring | post-seed |
| Series A | 30억+ | post-pilot |

Detailed contact strategy lives in operator's private notes per
business-track §7. This file records the channel categories only.

---

## 6. OSS integrations (high-leverage, low-cost)

### 6.1 Direct integrations

| Target project | Integration form | Earliest |
|---|---|---|
| LangChain | community retriever class | v0.3 |
| LlamaIndex | retriever / vector store hub entry | v0.3 |
| Onyx (formerly Danswer) | plugin | v0.3 |
| AnythingLLM | compatibility test + recipe | v0.3 |
| Open WebUI | tool / function | v0.3 |
| Ollama | example in community examples | v0.3 |
| LiteLLM | provider compatibility | v0.3 |

### 6.2 Standard / spec contributions

| Body | Activity | Earliest |
|---|---|---|
| OWASP RAG Security Project | observer / contributor | v0.3 |
| W3C AI WG | observer | v0.4 |
| OpenSSF | already targeted via Best Practices Badge | v0.2 |
| MCP working group (Anthropic) | observer/contributor | v0.3 |

---

## 7. Academic / research

| Venue | Format | Earliest |
|---|---|---|
| arXiv preprint | 5-10 page architecture paper | v0.4 |
| NeurIPS Workshop (DCAI / FL / etc.) | workshop paper | v0.4 |
| ACL Workshop | workshop paper | v0.4 |
| EMNLP Demo track | system demo | v0.4 |
| KCC 한국컴퓨터종합학술대회 | full paper | v0.4 |
| ACM CIKM / EMNLP main | possible if benchmark scores compete | v1.0+ |

---

## 8. Cycle-aligned timeline

```
[v0.2 in progress (months 0-4)]
  ✓ GitHub Topics
  ✓ Awesome list PRs (5+ lists)
  ✓ OpenSSF Badge self-assessment
  ✓ Blog series begins (biweekly EN+KO)
  ✓ 예비창업패키지 application drafting (private)
  ✗ Show HN — held
  ✗ Domain marketing — forbidden (per business-track §3)

[v0.2 closes (~month 4)]
  ✓ Show HN (single shot, with RAGAS + STEP 7 numbers from Axis 2-A/B)
  ✓ GeekNews + Reddit r/LocalLLaMA + r/selfhosted
  ✓ PyCon Korea CFP submission
  ✓ Twitter/X architecture thread
  ✓ First benchmark numbers public

[v0.3 (months 4-10)]
  ✓ MCP server registry submission
  ✓ LangChain integration recipe
  ✓ Reference Pack (general) public
  ✓ Korean tech media interviews (AI 타임스, etc.)
  ✓ Conference talks (Modulabs, GDG)
  ✓ Anthropic Cookbooks contribution

[v0.4 (months 10-22)]
  ✓ First domain pack (cafe) public
  ✓ Customer attestation (named with permission)
  ✓ arXiv preprint
  ✓ Workshop paper submission
  ✓ VC seed round
  ✓ Korean tech media interviews (플래텀, 더브이씨)

[v1.0 (months 22+)]
  ✓ HuggingFace Spaces flagship demo
  ✓ Major conference keynote
  ✓ Second domain pack begins
  ✓ Series A
```

Aspirational; 30-50% slip is normal for solo+AI OSS. The discipline
survives the slip; the calendar does not.

---

## 9. Anti-patterns (do NOT)

Reinforces business-track §12.2. Each row is a known way to lose
trust with the developer audience JAMES depends on:

| Anti-pattern | Why it harms JAMES |
|---|---|
| Show HN before v0.2 closes | Wastes single-shot opportunity at alpha quality |
| Buzzword inflation (AGI, autonomous, self-improving) | Audiences read this as sales-mode and discount everything else |
| Domain promises pre-v0.4 | Violates §3 "no parallel domains" rule |
| Pricing disclosure pre-revenue | Locks in a number before market evidence |
| "We / our team" framing | 1-person + Claude is the truth; pretending otherwise loses trust on discovery |
| Competitor disparagement (LangChain, Onyx, etc.) | Korean OSS community small; reputational damage propagates |
| Benchmark claims without RAGAS / STEP 7 | "Synthetic 100% pass" type claims are net-negative |
| English content pretending Korean isn't primary | Inconsistent with project DNA |
| Korean content hiding English assets | Inconsistent with mother-platform reach |
| Repeated channel hits without new substance | Burns audience attention budget |
| Posting same content to every channel same day | Looks automated; audiences notice and discount |

---

## 10. Activity log (append-only)

Each entry: ISO date | channel | summary | result.

| Date | Channel | Summary | Result |
|---|---|---|---|
| 2026-05-09 | (this file) | Catalog established under v0.2 cycle | Adopted via PR adding §12 to business-track |

Append below. Do not delete or edit historical entries.

When a channel is exercised, the entry should include:
- Date (ISO format)
- Channel name (matching §2-§7 row)
- One-line summary of what was posted/submitted
- Result (link, response, audience signal, or "awaiting")

---

## 11. 한국어 핵심 요약

- 외부 홍보는 **사이클 정렬 + 정직성 + 점진 확대** 3원칙
- 현 사이클(v0.2)에서 가능한 채널: GitHub Topics, awesome list 등재, OpenSSF Badge, GeekNews/Disquiet, 블로그, 예비창업패키지 작성
- 보류 채널: Show HN, 컨퍼런스, VC, 도메인 마케팅, 고객 명시
- §10 활동 로그에 행사 시점 append. 삭제·수정 금지
- 채널 가이드는 이 파일, 규율(금지 사항)은 `v0.2.1-business-track.md` §12
- 자세한 영업·재무·투자자 정보는 비공개 노트에 (이 저장소가 아님)
