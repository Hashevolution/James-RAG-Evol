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
| Twitter/X (English) | https://x.com/i/status/2054094082067386690 | Global EN | 2026-05-12 |
| Twitter/X (Korean) | _(URL pending — author to record)_ | KR | 2026-05-12 |
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
| **GeekNews** | 2026-05-19 (D+7 from account creation) | New-account post lockout | `reports/promo-assets/geeknews-post.md` ✅ |
| **Show HN** | 2026-05-26 (GeekNews +7) | Stagger to avoid same-week saturation | `reports/promo-assets/hackernews-show-hn.md` ✅ |
| **r/LocalLLaMA** | 2026-06-02 (Show HN +7) | Same | `reports/promo-assets/reddit-locallama.md` ✅ |

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
- [ ] Show HN post is published and URL recorded
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
- [ ] GeekNews D-Day 2026-05-19 — body refresh + image embed + author publish
- [x] **First organic verified-account replies on X received and responded to (2026-05-18)**
- [x] **Ali received the injection-fixtures schema URL via LinkedIn DM (Track 2 trigger)** — followed up with schema v1 refinements (2026-05-18); v1.1 `catalog_context` field added pre-emptively (2026-05-19, PR Track 2c) answering Ali's flagged convention question. Ali confirmed 2026-05-19: "byte_drift_expected is the right escape hatch", "data_exfiltration retrieval-stage insight is architecturally correct framing", `ar_ecommerce.yaml` authoring starts this week, **2026-06-01 deadline holds**.
- [x] **Cross-experiment design (3×3 matrix) pre-registered on main with falsification criteria locked before any cell runs**
- [x] **LLM Provider contract published on main 2–3 weeks ahead of schedule** — external implementers can wire backends now
- [ ] Track 1 — Provider contract **L1 wiring (code)** lands (deadline 2026-06-15)
- [ ] Track 2 — Ali delivers `ar_ecommerce.yaml` (15–20 Arabic fixtures + ≥5 benign, deadline ~2026-06-01)
- [ ] @mfucek_ (X) follow-up — potential second collaboration lead, awaiting their reply
- [ ] Gemma 4 Challenge result decided (2026-06-04)

Append a final "Phase 5 outcomes" section once the above are satisfied, then archive this file under `reports/promo-assets/archive/v0.2.0-launch-tracker.md` and reset for v0.3 cycle.
