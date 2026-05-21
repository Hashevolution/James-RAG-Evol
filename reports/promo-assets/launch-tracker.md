# Launch tracker — v0.2.0 promotion-readiness cycle

> Active monitoring log for the v0.2.0 promotion cycle. PR URLs, tweet URLs,
> external badges, and channel D-Days live here.
> Update this file whenever a PR is merged, a tweet posts, or a channel goes live.

---

## Status snapshot

| Date | Milestone | Outcome |
|---|---|---|
| 2026-05-11 | OpenSSF Best Practices passing badge | ✅ Awarded (Tiered 111%) |
| 2026-05-11 | python-multipart security fix (PR #213) | ✅ Merged into main |
| 2026-05-11 | GitHub Actions lint workflow (PR #205) | ✅ Merged into main |
| 2026-05-11 | OpenSSF badge + promo asset pack (PR #202) | ✅ Merged into main |
| 2026-05-11 | License / CLA / v0.3 plugin handover (PR #203) | ✅ Merged into main |
| 2026-05-11 | awesome-llm-apps PR #804 | ⏳ Open, awaiting curator |
| 2026-05-12 | Awesome-GraphRAG PR #27 | ⏳ Open, awaiting curator |
| 2026-05-12 | Awesome-LLM PR #563 | ⏳ Open, awaiting curator |
| 2026-05-12 | Twitter/X English thread | ✅ Posted |
| 2026-05-12 | Twitter/X Korean thread | ✅ Posted |
| 2026-05-12 | GitHub Topics + Description refresh | ✅ Applied |
| 2026-05-12 | GeekNews account created | ✅ (D-Day lockout 7 days) |
| 2026-05-12 | dev.to article published | ✅ Live ([URL](https://dev.to/hashevolution/building-a-mini-palantir-a-local-graph-rag-engine-with-ontology-security-and-self-evolution-1914)) |
| 2026-05-12 | dev.to draft + launch tracker (PR #242) | ✅ Merged into main |
| 2026-05-12 | urllib3 + python-multipart secondary advisory bumps (Dependabot #7-#10) | ✅ Merged into main (separate session — `urllib3>=2.7.0`, `python-multipart>=0.0.27`) |
| 2026-05-12 | **Gemma 4 Challenge submission published (Build with Gemma 4 track)** | ✅ Live ([URL](https://dev.to/hashevolution/building-a-mini-palantir-on-gemma4e4b-128k-context-lets-the-graph-actually-be-graph-rag-33fk)) |
| 2026-05-13 | Hashnode cross-post of intro article (`ragllm.hashnode.dev`) | ✅ Live ([URL](https://ragllm.hashnode.dev/building-a-mini-palantir-a-local-graph-rag-engine-with-ontology-security-and-self-evolution-alpha)) |
| 2026-05-16 | awesome-llm-apps PR #804 closed by curator | ❌ Closed (link-only PRs not accepted; full tutorial folder with self-contained runnable code required) |
| 2026-05-16 | **First external technical exchange — Ali Afana (Provia founder, dev.to Featured)** | ✅ Two-way collaboration discussion: 83-item injection regression suite spin-out + v0.3 Gemma 4 variant benchmark (E4B / 26B MoE / 31B Dense on STEP 7 corpus) |
| 2026-05-16 | LinkedIn DM second-turn reply to Ali | ✅ Sent — v0.3.0 release acknowledged, swap-as-benchmark commitment, 83-item suite spin-out task split, temperature-0.3 cap pushback (new ablation lead) |
| 2026-05-16 | dev.to substantive comment on Ali's article (`/alimafana/...refused-1j18`) | ✅ Posted — Scenario 2 white-shirt counterfactual cited as cleanest evidence; typed graph_path framing positioned at the "no ambiguity to resolve" end of Ali's spectrum; cross-link to PROJECT JAMES GitHub |
| 2026-05-17 | **v0.3.0 — Platform Skeleton released on main** | ✅ Axis 6 second-user gate cleared 2026-05-13. Knowledge Cascade Phase A→E + Cognitive Middleware Layer architecture. Plugin API slipped to v0.3.x or v0.4 (per CHANGELOG note) |
| 2026-05-17 | Cognitive Middleware Layer Phase 2 already shipping post-v0.3.0 | ✅ Verification engine (PR #290), planner / task decomposition (PR #297), tool router (PR #295) merged on main. Layer is now code, not architecture-only |
| 2026-05-17 | Author dev.to Gemma 4 article — self-reply with bidirectional cross-reference to Ali's article | 🟡 Comment body drafted (see archive note below); awaiting author publication |
| 2026-05-18 | **6 promo screenshots + README hero image landed on main (PR #304)** | ✅ `reports/promo-assets/screenshots/` — 01 memory-status, 02 intent-engineering, 03 chat-graph-paths, 04 personality-radar, 05 knowledge-tracker, 06 3d-graph. Hero on both `README.md` and `README.ko.md`. Visual-trust gap closed |
| 2026-05-18 | New X post — v0.3.0 3D ontology visualizer with `06-3d-graph.jpg` attached | ✅ Posted by author (URL pending in tracker) — first image-bearing X post in cycle |
| 2026-05-18 | **dev.to Write-track submission published** — fair-witness field report on E4B cognitive-stage failures | ✅ Live ([URL](https://dev.to/hashevolution/5-empty-responses-from-gemma4e4b-4-hypotheses-0-root-cause-1ggd)) — second Gemma 4 Challenge submission (Write track, $100×5 prize), draft archived at `reports/promo-assets/devto-gemma4-write-track.md` |
| 2026-05-18 | **First two organic verified-account replies on X** | ✅ [@simplydt](https://x.com/simplydt) "v0.3.0 is robust, dig the local Graph-RAG security stack" (on v0.3.0 release tweet) + [@mfucek_](https://x.com/mfucek_) "you also using react force graph? Working on a similar project" (on 3D visualizer tweet) — both verified, both technical, latter is a potential second collaboration lead |
| 2026-05-18 | **Ali Collaboration Track handover + injection-fixtures schema v0 (PR #311)** | ✅ Merged on main. 5 commits made in writing converted into 5 coding tracks with deadlines (Track 2 schema 2026-06-01, Track 1 Provider contract 2026-06-15). Schema URL ready for hand-off to Ali via LinkedIn DM |
| 2026-05-18 | Ali 3rd turn (LinkedIn DM) — proposed 3×3 matrix experiment design (3 variants × 3 temperatures × 1 prompt structure per side, 9 cells, 1 run per cell) | ✅ Acknowledged. Provia Arabic-localization milestone aligned with our 2–4 week Provider window |
| 2026-05-18 | **Gemma 4 variant 3×3 evaluation plan published (PR #315)** | ✅ Merged on main. Pre-registers matrix design + 4 hypotheses + result-to-writeup decision matrix BEFORE any cell runs (post-hoc framing drift safeguard). Two-layer measurement-site discipline (synthesis layer only) |
| 2026-05-18 | **LLM Provider contract published (PR #316)** | ✅ Merged on main. Track 1 deliverable shipped 2–3 weeks ahead — external implementers (Ali Gemini API side, anyone else) can wire backends against the stable contract immediately while internal L1 wiring follows separately |
| 2026-05-18 | Our 4th turn LinkedIn DM reply sent | ✅ Sent — 3×3 design accepted with synthesis-layer measurement clarification, Provider contract URL provided, pre-registration plan URL provided, scope-lock note re-acknowledged |
| 2026-05-18 | Ali 4th turn (LinkedIn DM) — schema v0 → v1 refinements proposed | ✅ Two refinements: (a) **Normalization invariant** (byte-exact UTF-8, harness never normalizes, NFKC/U+202E collapse risk for `direction_mark_confusion`); (b) **`expected_block_stage` optional enum** (input/retrieval/output/any, defaults to `any` for backward-compat, multi-stage attack capture for `catalog_poisoning` + `data_exfiltration`) |
| 2026-05-18 | **Injection-fixtures schema v0 → v1 (PR #317)** | ✅ Merged on main. Both Ali refinements accepted and implemented in schema doc. Backward-compatible: v0 fixtures parse under v1 unchanged. URL path preserved (same as v0 publish, only `version` field internal to doc bumped to `1`); diff-log entry records the transition with Ali's DM date and credit ("acting on Ali's LinkedIn DM 2026-05-18 feedback") |
| 2026-05-18 | Our 5th turn LinkedIn DM reply sent | ✅ Sent — v1 refinements accepted as fact (already published), `test_prompt_is_unnormalized` enforcement pattern documented, `expected_block_stage` JAMES + Provia 3-stage mappings worked through with `ar_poi_001` example. Ali's 6/1 timeline unchanged |
| 2026-05-18 | dev.to comment thread — **deliberately NOT cross-posted** from LinkedIn DM contents | ✅ Channel separation decision recorded. Rationale: (1) Ali chose LinkedIn DM as the sustained working channel (4 turns there vs 1 dev.to comment), (2) Ali's specific commits on LinkedIn (15-20 Arabic fixtures, 6/1 deadline, refinement detail) are sustained working-dialogue, not public announcement, (3) dev.to comment thread already has the 2026-05-16 reply with general collaboration-progress signal; next dev.to comment trigger is a milestone (Provider L1 wiring merge / swap experiment result / Part 2 article publication) |
| 2026-05-18 | **Track 2 fixture migration started — `tests/fixtures/injection/baseline_kr_en.yaml` + harness on main** | ✅ Separate session implementation. Validates the Ali Collaboration Track handover (`docs/handovers/v0.3.x-ali-collaboration-track.md`) was picked up by a follow-up session and Track 2 work is in progress on schedule for the 2026-06-01 Ali-side `ar_ecommerce.yaml` integration |
| 2026-05-18 | **Second potential collaboration — Matija Fućek (@mfucek_, Provia-adjacent verified) substantive X reply on graph visualization thread** | ✅ 4-paragraph reply: shares his "two tiers of connections" pattern (root + structural + mesh-via-tiny-force), names his project `@naumu_ai` (product/company brain app, plug-and-play vs Claude Code + Obsidian setups), demo video attached (default LLM `gemma2:2b` via Ollama), invites email DM for naumu_ai platform access since he already imported PROJECT JAMES into his system |
| 2026-05-18 | Our X reply to @mfucek_ posted + X DM with email sent | ✅ Reply credited his two-tiers pattern as cleaner than our link-strength cap, named "plug-and-play as the gap between OSS RAG and someone actually shipping" as the framing we're tracking. Email transferred via DM for follow-up. Channel separation discipline followed: public X reply names the framing, private specifics go to DM |
| 2026-05-19 | Ali 5th turn (LinkedIn DM) — flagged `catalog_poisoning` convention question + confirmed `byte_drift_expected` opt-in + reinforced `data_exfiltration` retrieval-stage framing | ✅ Followed up on our 5th-turn reply with three threads: (a) asked how `catalog_poisoning` fixtures should represent both the legitimate customer query and the poisoned content, (b) confirmed `byte_drift_expected` is the right escape hatch, (c) reinforced that "output-stage PII mask after the model already saw confidential context = wrong protective surface" is the architecturally correct framing |
| 2026-05-19 | **Injection-fixtures schema v1 → v1.1 (PR #322)** | ✅ Merged on main pre-emptively (before our next LinkedIn DM reply, per our own "publish before promise" lesson). New optional field `catalog_context: list[string]` — `prompt` stays the legitimate customer query (must NOT trigger input filter), `catalog_context[0..N]` is the poisoned content the retrieval stage feeds the model. List rather than single string to preserve the "1-of-N poisoned" signal so the test can assert the output filter catches the leak when N-1 of N retrieved docs are clean. New "Catalog context shape (v1.1)" section + worked example on `ar_poi_001`. Backward-compatible: fixtures without `catalog_context` parse unchanged. Diff-log entry credits Ali's flagged convention question |
| 2026-05-19 | Our 6th turn LinkedIn DM reply sent | ✅ Sent — v1.1 `catalog_context` field published as fact (full URL provided), two short acknowledgments back (`byte_drift_expected` agreed as escape-hatch role, `data_exfiltration` retrieval-stage framing acknowledged + committed to follow-up post **"Why output-stage PII mask is the wrong protective surface for data_exfiltration"** in a separate cycle). Provider contract L1 wiring (the actual `core/reasoning/pipeline.py` swap to use the contract) committed on our queue for 2026-06-15, with offer to surface the wiring PR earlier if it helps Ali's Gemini API integration testing |
| 2026-05-19 | **Track 1 PR-A merged — synth call-site backend wiring (PR #324)** | ✅ Merged on main. `core/reasoning/pipeline_synth.py` + `engine_synth.py` + four mode adapters (`chat.py` / `coding.py` / `self_evolve.py` / `wiki_edit.py`) now route through the Provider contract instead of calling Ollama SDK directly. Reasoning trace helpers (`trace_helpers.py`) updated for backend-agnostic capture. Originally queued for 2026-06-15 — shipped ~4 weeks ahead so Ali's Gemini API backend integration testing can start earlier than promised |
| 2026-05-19 | **Track 1 PR-B merged — conformance suite + SDK leakage guard (PR #325)** | ✅ Merged on main. `tests/test_backend_conformance.py` (337 lines) enforces the 6 required behaviors any external Provider implementation must satisfy. `tests/test_no_sdk_leakage.py` (220 lines) guards against accidental Ollama-SDK / vendor-SDK imports leaking back into call sites after the Track 1 PR-A wiring. Together these make the Provider contract executable spec, not just doc |
| 2026-05-19 | **K1 GeekNews published** | ✅ Live ([URL](https://news.hada.io/topic?id=29648)) — title (A) variant ("JAMES v0.3.0 — Platform Skeleton 도달") used. First Korean-language milestone post of the v0.3 cycle. Body synthesized v0.3.0 release + Cognitive Middleware Phase 2 + Ali 6-turn collaboration + Gemma 4 Challenge 2 submissions + Matija second collab + schema v1.1 + Provider contract + 3×3 plan + visual asset library |
| 2026-05-19 | K1-companion X tweet + LinkedIn post published | ✅ Both posted (URLs pending — author to record). Channel separation discipline followed: GeekNews body = full milestone synthesis (Korean IT community), X tweet + LinkedIn = milestone signal pointers (no body content duplicated) |
| 2026-05-19 | **K4 Velog Korean intro cross-post published** | ✅ Live ([URL](https://naver.me/GUTw3kar)) — Naver-shortened. Same-day publish as K1 GeekNews (originally planned for 2026-05-20~22 window, executed early to capture K1 afterglow inside 24h). Body = dev.to intro Korean re-write + v0.3.0 update box (v0.2→v0.3 comparison table). canonical → dev.to original. Cover image: 06-3d-graph.jpg (3D ontology hero, same as K1 GeekNews body image). Tags: RAG / GraphRAG / 오픈소스 / 로컬LLM / Python. Series: JAMES Graph-RAG (created for future v0.4/v1.0 entries). SEO-accumulation channel (google.co.kr long-tail, expected payoff 6-12mo) |
| 2026-05-19 | **HN Show HN restriction notice received from moderator (dang)** | ❌ Show HN attempt blocked. Standard new-account gating: *"We're temporarily restricting Show HNs because of a massive influx, mostly by users who aren't yet familiar with the site or its culture."* — not personal rejection, fleet-wide policy. Links provided: newsguidelines.html / newswelcome.html / showhn.html. Action: E1 D-Day deferred from 2026-05-26 → **2026-06-16** (3-week karma-building window). The Show HN body refresh (PR #328) landed before the deferral notice and remains valid; the asset isn't the blocker, the account is |
| 2026-05-19 | **Show HN retry plan locked — 3-week karma-building program** | 📋 Plan: (Week 1, 5/20-26) read HN front page 15-20min/day, read all 3 dang-linked pages, upvote only; (Week 2, 5/27-6/2) 1-2 substantive comments/day in Python/RAG/local-LLM/security threads, **zero JAMES mentions** (new-account self-promo = shadowban), aim for 4 comment principles (own-experience line + admit potential blindspot + 1-line conclusion + no plug); (Week 3, 6/3-9) comment frequency up + Ask HN attempt (gating weaker than Show HN), target karma 20-30; (Week 4+, 6/10+) Show HN retry at karma 50+ / account ≥30 days / sustained comment trace. D-Day target 2026-06-16 (Tue) KST 23:30 |
| 2026-05-19 | **5/26 slot reassigned — `data_exfiltration` follow-up dev.to article promoted** | 🟡 Originally a "separate cycle deliverable" committed to Ali in 6th-turn DM (2026-05-19), now becomes the 5/26 publish slot to fill the vacated Show HN gravity. Title direction: "Why output-stage PII mask is the wrong protective surface for data_exfiltration." Channel: dev.to (Ali-watched + Joe's existing 3-article archive on that platform). Cross-channel: do NOT cross-post to LinkedIn / X within 24h; the article *is* the signal |
| 2026-05-19 | **5/26 second slot reassigned — Reddit r/LocalLLaMA account-readiness audit** | 🟡 Before submitting E2 r/LocalLLaMA, audit Joe's Reddit account state (karma, account age, recent activity in tech subreddits). r/LocalLLaMA enforces account-age + karma minimums that may mirror HN's gate. If insufficient: same karma-building plan applies on Reddit side, with adjusted timeline |
| 2026-05-19 | **K3 video burst — all 4 demo videos published in single session** | ✅ Live (4 URLs in Social posts table). Videos 1-4: login + main chat / actual chat conversation / character personality control / reasoning graph traversal. Originally planned as 4-day spread (Day 3-6, 5/21-5/24) but executed as single-day burst (Joe's call, 2026-05-19). Trade-off: single-day burst loses daily X algorithm gain but creates "connected pattern" on follower timelines + concentrates visual impact. Day 1 "노트북에서" wording corrected to "로컬 PC에서" for Video 1 (matches demo footage's actual GPU setup; broader laptop framing in published assets stays as gemma2:2b CPU path is technically valid). K3 series cadence revised: Day 3-6 absorbed into today, leaving Day 3 (5/21) for a v0.3.0 follow-up tweet and Day 7 (5/25) for series finale + feedback request |
| 2026-05-21 | **α-experiment + next-experiments plan + validation plan published in docs/research/** | ✅ Three companion docs landed: `gemma4-event-emit-experiment-2026-05-21.md` (n=10 PR-11b extraction, 6/10 empty), `gemma4-next-experiments-plan.md` (5-experiment runbook β/γ/δ/ε/ζ), `gemma4-experiment-validation-plan.md` (methodology overlay + V6/V7/V8 additions + cross-experiment decision tree). Hypothesis space narrowed but no single root cause confirmed |
| 2026-05-21 | **First substantive Reader contribution received — Ali Afana dev.to walk-back** | ✅ Ali published pre-publish draft preview (`/alimafana/i-raised-gemma-4s-token-cap-the-dense-model-stopped-refusing-2gf3`) walking back his earlier "MoE vs Dense architecture" claim — single-variable `max_tokens 400 → 4096` test recovered Gemini 31B Dense 12/12 + 26B MoE 12/12. Walk-back triggered by Robin Converse's sovereign-Ollama uncapped sweep. Two Hashevolution mentions: (1) "Why I Re-Ran It" structural-reframe list, (2) "What's Still Open" temperature critique + mid-June Graph-RAG cross-experiment. **Routed to `gemma4-e4b-cognitive-stages-eval.md` §"Reader contributions" as first entry — hypothesis B-confirming. Maps 1:1 onto JAMES per-stage `DEFAULT_MAX_TOKENS` defaults (200/400/400/400 across query_rewriter / planner / reflect / verify), which are exactly the stages tabled as failing on gemma4:e4b in the 2026-05-18 eval.** Three deployment contexts (Robin's sovereign Ollama / Ali's managed Gemini / JAMES's local Ollama) now point at the same cap pathology before Track 3 swap runs |
| 2026-05-21 | Outgoing LinkedIn DM to Ali — preview review + JAMES-side cap mapping shared + Track 3 calendar reconfirmed | ✅ Sent. Three contents: (a) both mention framings accurate, no edits requested — frees Ali to publish, (b) shared JAMES per-stage `DEFAULT_MAX_TOKENS` mapping (200/400/400/400 = his failing cap) as data point he can incorporate pre-publish if he chooses ("your call" — mirrors his "not as an ask"), (c) V3' replication queued this week with STEP 7 bench, will produce third deployment context for joint piece. Track 3 mid-June calendar reconfirmed + CLA Assistant setup data 2026-05-26 |

---

## External validation badges

| Badge | URL | Status |
|---|---|---|
| OpenSSF Best Practices **passing** | https://www.bestpractices.dev/projects/12806 | Active (Tiered 111%, 2026-05-11) |

---

## Open external PRs (awesome-list submissions)

Three independent curators, three independent review pipelines. One acceptance is sufficient to start drawing traffic.

| Repo | PR | Stars (approx) | Curator | Posted | Notes |
|---|---|---|---|---|---|
| [Shubhamsaboo/awesome-llm-apps](https://github.com/Shubhamsaboo/awesome-llm-apps) | [#804](https://github.com/Shubhamsaboo/awesome-llm-apps/pull/804) | 50k+ | Shubhamsaboo | 2026-05-11 | ❌ **Closed 2026-05-16** — link-only PRs not accepted; sub requires self-contained runnable code under `rag_tutorials/<project_folder>/` with `app.py` + `requirements.txt` + folder README. Refile possible later as a minimal-runnable tutorial folder |
| [DEEP-PolyU/Awesome-GraphRAG](https://github.com/DEEP-PolyU/Awesome-GraphRAG) | [#27](https://github.com/DEEP-PolyU/Awesome-GraphRAG/pull/27) | 1k+ | DEEP-PolyU | 2026-05-12 | 💻 Open-source Project section |
| [Hannibal046/Awesome-LLM](https://github.com/Hannibal046/Awesome-LLM) | [#563](https://github.com/Hannibal046/Awesome-LLM/pull/563) | 25k+ | Hannibal046 | 2026-05-12 | LLM Applications section. Title has minor wording issue (Visualized capitalization) — curator may request rewording |

---

## Social posts

| Channel | URL | Audience | Posted |
|---|---|---|---|
| **GeekNews (K1)** | https://news.hada.io/topic?id=29648 | KR (Hada.io tech community) | 2026-05-19 |
| **Velog (K4) — Korean intro cross-post** | https://naver.me/GUTw3kar | KR (Naver-shortened, full at velog.io/@hashevolution) | 2026-05-19 |
| **X (KO) K3 Video 1 — login + main chat** | https://x.com/i/status/2056628377919128016 | KR (X timeline) | 2026-05-19 |
| **X (KO) K3 Video 2 — actual chat conversation** | https://x.com/i/status/2056628637814702258 | KR (X timeline) | 2026-05-19 |
| **X (KO) K3 Video 3 — character personality control** | https://x.com/i/status/2056632428320710740 | KR (X timeline) | 2026-05-19 |
| **X (KO) K3 Video 4 — reasoning graph traversal** | https://x.com/i/status/2056633087052910792 | KR (X timeline) | 2026-05-19 |
| **LinkedIn — Korean v0.3.0 milestone post** | _(URL pending — author to record)_ | KR/Global professional | 2026-05-19 |
| **Twitter/X (Korean — v0.3.0 K1-companion)** | _(URL pending — author to record)_ | KR | 2026-05-19 |
| Twitter/X (English) | https://x.com/i/status/2054094082067386690 | Global EN | 2026-05-12 |
| Twitter/X (Korean — v0.2.0 cycle) | _(URL pending — author to record)_ | KR | 2026-05-12 |
| dev.to article (intro) | https://dev.to/hashevolution/building-a-mini-palantir-a-local-graph-rag-engine-with-ontology-security-and-self-evolution-1914 | Global EN (technical) | 2026-05-12 |
| dev.to article (Gemma 4 Challenge submission) | https://dev.to/hashevolution/building-a-mini-palantir-on-gemma4e4b-128k-context-lets-the-graph-actually-be-graph-rag-33fk | Global EN (Gemma 4 contestants + judges) | 2026-05-12 |
| Hashnode cross-post (intro article) | https://ragllm.hashnode.dev/building-a-mini-palantir-a-local-graph-rag-engine-with-ontology-security-and-self-evolution-alpha | Global EN (Hashnode algorithm + Google search) | 2026-05-13 |
| X — v0.3.0 visualizer post (with 3D graph image) | _(URL pending — author to record)_ | Global EN | 2026-05-18 |
| dev.to article (Write-track submission — cognitive-stages fair-witness report) | https://dev.to/hashevolution/5-empty-responses-from-gemma4e4b-4-hypotheses-0-root-cause-1ggd | Global EN (Gemma 4 contestants + Ollama operators + local-LLM researchers) | 2026-05-18 |

Monitoring rule: respond to substantive replies within 1-2 hours during the first 24 hours; longer-form responses (e.g. quote threads) get hour-of-day discretion.

### X reply response patterns (after the first organic replies, 2026-05-18)

Three reply shapes observed so far; canonical response template per shape:

| Reply shape | Example | Response template |
|---|---|---|
| **Technical question from a maker** | @mfucek_ — "you also using react force graph?" — replier is working on adjacent project | Precise technical answer + one *interesting* detail we learned + reciprocal curiosity about their project. Door opens for second-collaboration lead if their answer comes back substantive |
| **Short positive endorsement** | @simplydt — "v0.3.0 is robust, dig the local Graph-RAG security stack" | Thank them + name the next stress test (v0.4 multi-tenant) + invitation if they've worked similar boundaries. Short, dignified, no sales tone |
| **Critical push-back** *(none received yet)* | hypothetical | Partial acknowledgement + our reasoning made explicit + reframe with data. Same pattern as the Ali-temperature exchange |

Universal rules:
- Respond within 1–6 hours during the active follow-up window
- Public reply means silent readers see it — depth matters more than brevity
- Verified accounts get priority on response order, but everyone gets a reply if substantive
- Reciprocal curiosity ("what kind of X is your project doing?") is the highest-leverage single line in a maker-to-maker reply

### Cross-channel posting discipline (formalized 2026-05-18 from the Ali Afana exchange)

When a sustained working-dialogue lives on a private channel (LinkedIn DM, email, Discord DM), **do not cross-post the specific commits to public channels** (dev.to comments, X public replies, public Reddit) unless the collaborator explicitly opts in. Cross-posting policy:

| Working channel | Public channel role | What to cross-post |
|---|---|---|
| **LinkedIn DM** (sustained working dialogue) | **dev.to comments / X replies** (public milestone signal) | Public-side gets only milestone announcements (Provider contract live, swap experiment result, joint article published) — never the working-dialogue specifics (deadlines committed in private, percentages of code volume committed by each side, refinement-source attribution beyond what the working artifact itself credits) |
| Email | Same as above | Same as above |
| Discord DM | Same as above | Same as above |

Why: violating this discipline (a) commits the collaborator to public obligations they only made in private, (b) creates the impression that future private commits will be publicly announced — chilling the working dialogue's specificity, (c) leaks competitive timing info that may matter to the collaborator's company (Ali's Provia release schedule, for example).

The intermediate artifacts that *do* go on public main repository (this launch-tracker, the schema docs, the Provider contract, the 3×3 evaluation plan) are different — they are deliberately published designs. The private dialogue *behind* them stays private.

---

## GitHub repo metadata refresh

Applied via the About panel (⚙️) on 2026-05-12:

- **Description**: `🔐 Local-first Graph-RAG with ontology, 3-stage security, self-evolution scaffold. 100% Ollama. MIT.`
- **Website**: `https://www.bestpractices.dev/projects/12806`
- **Topics (10)**: `rag`, `graph-rag`, `ontology`, `ollama`, `local-llm`, `llm`, `python`, `security`, `knowledge-graph`, `retrieval-augmented-generation`

---

## Upcoming channel D-Days

| Channel | D-Day | Lock reason | Asset ready |
|---|---|---|---|
| **dev.to blog post** | ✅ Published 2026-05-12 | None | `reports/promo-assets/devto-post.md` ✅ |
| **GeekNews** | ✅ Published 2026-05-19 | None | `reports/promo-assets/geeknews-post.md` ✅ |
| **Velog (K4 cross-post)** | ✅ Published 2026-05-19 | None | `reports/promo-assets/velog-intro-ko.md` ✅ |
| **Show HN** | ❌ Deferred from 2026-05-26 → **2026-06-16** | HN new-account Show HN restriction received 2026-05-19 from moderator (dang). 3-week karma-building plan in motion (substantive commenting, no self-promo). Asset body remains current — body v0.3.0 refresh PR #328 landed before the deferral notice and stays valid for the 6/16 retry. | `reports/promo-assets/hackernews-show-hn.md` ✅ |
| **r/LocalLLaMA** | 2026-06-02 (independent of Show HN deferral) | Reddit-side new-account threshold check pending — may need similar deferral if r/LocalLLaMA enforces account-age + karma minimums | `reports/promo-assets/reddit-locallama.md` ✅ |
| **dev.to follow-up — `data_exfiltration` why output-stage PII mask is wrong** | Target 2026-05-26 (filling vacated Show HN slot) | Already committed to Ali in 6th-turn LinkedIn DM (2026-05-19); publishing fulfills the promise + provides Show HN-slot content gravity | Not yet drafted |

Recommended hours:
- GeekNews — KST weekday 09–11 or 20–22
- Show HN — US Pacific 06:00–09:00 (front-page algorithm window)
- r/LocalLLaMA — US Eastern 09:00–11:00

---

## Active contests

| Contest | Track | Submission URL | Deadline | Winners announced |
|---|---|---|---|---|
| [Gemma 4 Challenge](https://dev.to/challenges/google-gemma-2026-05-06) | Build with Gemma 4 ($500 × 5) | https://dev.to/hashevolution/building-a-mini-palantir-on-gemma4e4b-128k-context-lets-the-graph-actually-be-graph-rag-33fk | 2026-05-24 23:59 PDT | 2026-06-04 |
| [Gemma 4 Challenge](https://dev.to/challenges/google-gemma-2026-05-06) | Write about Gemma 4 ($100 × 5) | https://dev.to/hashevolution/5-empty-responses-from-gemma4e4b-4-hypotheses-0-root-cause-1ggd | 2026-05-24 23:59 PDT | 2026-06-04 |

Per-judge tie-break is by reaction count, so post-publication actions matter:

1. Seed first comment on the article to lower comment-entry friction
2. Quote-tweet from the English X/Twitter thread with the challenge URL
3. Share in any Ollama / Gemma / RAG Discord servers we're already in
4. Respond to substantive comments within 1-2 hours during the first 48 hours

Asset archive: `reports/promo-assets/devto-gemma4-challenge.md`

---

## Visual asset library (since 2026-05-18)

Six reusable screenshots under `reports/promo-assets/screenshots/`,
each with a stable raw-blob URL on `main`. Drop-in for any external
channel — see `reports/promo-assets/screenshots/README.md` for the
strongest-signal mapping and recommended placement per channel.

| File | Drop-in raw URL |
|---|---|
| Memory status counters | `https://github.com/Hashevolution/James-RAG-Evol/blob/main/reports/promo-assets/screenshots/01-memory-status.jpg?raw=true` |
| Intent Engineering entity + 3D graph | `.../02-intent-engineering.jpg?raw=true` |
| Chat response with 47 graph paths | `.../03-chat-graph-paths.jpg?raw=true` |
| Personality 11-trait radar | `.../04-personality-radar.jpg?raw=true` |
| Knowledge tracker (self-evolution + LV per domain) | `.../05-knowledge-tracker.jpg?raw=true` |
| 3D ontology graph (hero) | `.../06-3d-graph.jpg?raw=true` |

Channel-by-channel application status:

- README.md / README.ko.md — `06-3d-graph.jpg` as hero ✅
- dev.to intro article — cover image refresh planned (`06-3d-graph.jpg`) 🟡
- dev.to Gemma 4 article — cover image refresh planned (`03-chat-graph-paths.jpg`) 🟡
- X visualizer post — `06-3d-graph.jpg` attached ✅
- LinkedIn follow-up — image attachment planned 🟡
- GeekNews body — image embed planned for D-Day 2026-05-19 🟡
- Show HN / Reddit — image embed planned for respective D-Days 🟡

### Pending author-publication actions

The following items are drafted and waiting for the author to publish from
their own account (not automatable from this session):

- **Author-reply on the Gemma 4 dev.to article** (bidirectional cross-reference
  to Ali's MoE-vs-Dense piece). Body cites Ali's hypothesis as a testable
  prediction on Graph-RAG typed-path inputs; commits to running it once the
  Plugin / LLM Provider API lands in v0.3.x. Drafted 2026-05-17.
- **dev.to intro + Gemma 4 article body sweep** — "v0.2.0 alpha" lines could
  be refreshed to "v0.3.0 released 2026-05-17, Cognitive Layer Phase 2 in
  progress" for consistency with current main state. Optional polish, no
  freshness penalty (dev.to does not down-rank edited posts).

---

## OpenSSF criterion auto-promotions (post-merge)

These three criteria flipped from Unmet → Met as a side effect of merges that landed on 2026-05-11:

| Criterion | Trigger | Effect |
|---|---|---|
| `static_analysis_often` | PR #205 (`.github/workflows/lint.yml`) | Lint runs on every PR + every push to main |
| `vulnerabilities_fixed_60_days` | PR #213 (python-multipart spec floor) | Dependabot alerts #5/#6 auto-close on next rescan |
| `static_analysis_fixed` | PR #196 (already in baseline, reinforced by ruff Phase 2/3) | F-class enforcement at 0 violations |

**User action remaining**: update the two criteria above to Met on the bestpractices.dev form. Tiered % expected to climb above 111% — first step toward `silver` tier.

---

## Phase 5 monitoring rule

If the next 7 days (2026-05-12 → 2026-05-19) show no acceptance on any of the three awesome PRs:

1. Check for curator comments — usually a small wording/position request, respond within 24 hours
2. If no comments and PRs sit untouched for 7+ days, ping the curator politely (single comment, no follow-up)
3. After 14 days idle, expand to one additional awesome-list (awesome-self-hosted, awesome-rag, etc.)

If at least one awesome PR merges before 2026-05-19:

- Mention the merge in the GeekNews post body ("Listed in awesome-X")
- Mention in the Show HN post body (D+14)
- Drop a one-line acknowledgement in the next CHANGELOG entry

---

## Cycle close criteria

This launch tracker file is considered complete when all of the following are true:

- [ ] At least one awesome PR is merged
- [ ] GeekNews post is published and URL recorded
- [ ] Show HN post is published and URL recorded — **deferred from 2026-05-26 to 2026-06-16** per HN new-account restriction (2026-05-19 dang notice); 3-week karma-building plan in motion
- [ ] r/LocalLLaMA post is published and URL recorded
- [x] dev.to post is published and URL recorded (2026-05-12)
- [x] dev.to Gemma 4 Challenge submission is published (2026-05-12, deadline 2026-05-24)
- [x] **dev.to Gemma 4 Challenge — second submission (Write track) published (2026-05-18)**
- [ ] OpenSSF Tiered % updated post-merge (target ≥ 115%)
- [x] **Second-user real-data corpus volunteer engaged (v0.2 → v0.3 gate cleared 2026-05-13)**
- [x] **First substantive external technical exchange (Ali Afana / Provia, 2026-05-16)**
- [x] **Two-way exchange formalised (LinkedIn second turn + dev.to substantive comment, 2026-05-16)**
- [ ] Author-reply on Gemma 4 article with bidirectional cross-reference (drafted, awaiting publish)
- [x] **Visual asset library shipped — 6 screenshots + README hero (PR #304, 2026-05-18)**
- [x] **First image-bearing X post (2026-05-18, URL pending)**
- [ ] dev.to two articles refreshed with cover images (planned, drag-drop from screenshots library)
- [x] **GeekNews D-Day 2026-05-19 — body refreshed for v0.3.0 + image embed + author publish complete** (id=29648, 3D ontology image attached, K1-companion X tweet + LinkedIn post sent same day)
- [x] **First organic verified-account replies on X received and responded to (2026-05-18)**
- [x] **Ali received the injection-fixtures schema URL via LinkedIn DM (Track 2 trigger)** — followed up with schema v1 refinements (2026-05-18); v1.1 `catalog_context` field added pre-emptively (2026-05-19, PR Track 2c) answering Ali's flagged convention question. Ali confirmed 2026-05-19: "byte_drift_expected is the right escape hatch", "data_exfiltration retrieval-stage insight is architecturally correct framing", `ar_ecommerce.yaml` authoring starts this week, **2026-06-01 deadline holds**.
- [x] **Cross-experiment design (3×3 matrix) pre-registered on main with falsification criteria locked before any cell runs**
- [x] **LLM Provider contract published on main 2–3 weeks ahead of schedule** — external implementers can wire backends now
- [x] **Track 2 fixture migration in progress on main** — `baseline_kr_en.yaml` + harness shipped 2026-05-18 by a separate session picking up the Ali Collaboration Track handover
- [x] **Second potential collaboration started — @mfucek_ / naumu_ai (X verified)** — independent of the Ali track, complementary skill domain (product/UX vs experimental/academic). Email transferred 2026-05-18
- [x] **Track 1 — Provider contract L1 wiring (code) landed 2026-05-19 (PR #324 PR-A + PR #325 PR-B)** — ~4 weeks ahead of the 2026-06-15 deadline; synth call-sites + conformance suite + SDK leakage guard all in. Remaining sub-tasks: trace-stage backend wiring (separate PR), retrieval-stage backend wiring (separate PR), public surface-the-wiring DM ping to Ali
- [ ] Track 2 — Ali delivers `ar_ecommerce.yaml` (15–20 Arabic fixtures + ≥5 benign, deadline ~2026-06-01)
- [ ] @mfucek_ DM follow-up — naumu_ai platform access + comparison signal
- [ ] **`data_exfiltration` follow-up post — "Why output-stage PII mask is the wrong protective surface for data_exfiltration"** — committed to Ali in 2026-05-19 LinkedIn DM, separate cycle deliverable
- [ ] Gemma 4 Challenge result decided (2026-06-04)

Append a final "Phase 5 outcomes" section once the above are satisfied, then archive this file under `reports/promo-assets/archive/v0.2.0-launch-tracker.md` and reset for v0.3 cycle.
