# Changelog

All notable changes to PROJECT JAMES will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.3.0] — Platform Skeleton (2026-05-17)

After 190 merged PRs since v0.2.0 (9 days, 129 test files), JAMES exits
the v0.2 Foundation Hardening cycle and enters **v0.3 Platform Skeleton**.
Axis 6's second-user gate cleared on 2026-05-13. The original v0.3 plan
(Plugin API as the single theme) was rebalanced after the 2026-05-14
user briefing: **Cognitive Layer** and **Knowledge Cascade** become the
two main tracks, **Plugin API** slips to v0.3.x or v0.4 pending external
contributor demand.

Full release notes: [`docs/release_notes_v0.3.0.md`](docs/release_notes_v0.3.0.md).

### Added

#### Change Request primitive (v0.2.x track)
- **`core/change_request.py`** generalises the `approver_username`
  pattern that v0.1 hard-coded for self-evolution alone. Every write
  becomes a proposal → review → admin approval → atomic apply →
  audit row. Two target types ship: `wiki_entity` (markdown edits with
  `base_hash` conflict detection) and `run_jobs` (workspace job gate).
  Trust zone documented in `docs/ARCHITECTURE.md §5.6`. PRs #237, #243,
  #239, #240, #247.
- Workspace UI panel for proposers / reviewers (`/workspace` Change
  Request tab). PR #239.
- CR-E (self-evolution wrap) deferred to Cognitive Layer Phase 2 PR-6
  per the 2026-05-14 user decision (verification engine fuses with CR-E
  end-to-end).

#### Knowledge Cascade (Phase A → E, sources-aware graph)
- **Phase A** — `sources: [{doc_id, weight, role, ts}]` schema replaces
  the v0.2 single `confidence` field on every relation. Production wiki
  migrated (213 entities / 656 relations back-filled; backup at
  `wiki.pre-v03-migration/`). PR #266.
- **Phase B** — `process_document_for_entities` writes sources directly
  (`role=extract` outgoing + `role=inverse` inverse + doc-entity
  self-source). Legacy callers unaffected. PR #269.
- **Phase C** — `DELETE /admin/files` cascade. New `core/cascade.py`
  with strengthened orphan-detection rules. PR #270.
- **Phase D** — `PUT /admin/files` (multipart replace) cascade. Extraction
  sidecar JSON + diff_triples. PR #274.
- **Phase E backend** — `core/graph_editor.py` (replace / append / delete
  + bidirectional sync + manual metadata). Behind `JAMES_GRAPH_EDIT=1`
  opt-in flag. PR #271.
- **Phase E UI** — `/admin/graph` edit-mode toggle + edge-click modal
  (sources display + manual append + delete relation). PR #273.

#### Cognitive Middleware Layer (architecture only, code in v0.3.x)
- **`docs/ARCHITECTURE.md §5.7`** introduces the Cognitive Middleware
  Layer between retrieval and LLM synthesis. 7 named components
  (Planner / Query Rewriter / Reflection / Verification / Tool Router /
  Memory Manager / Security Reasoner / Context Optimizer), trust zone,
  trace-replay invariant, **5-role multi-agent cap (anti-sprawl)**,
  memory scope layering (system / workspace / session), and deployment
  isolation deferred to v0.4. Code lands across v0.3.x phases. PR #275.
- Cycle plan: `docs/handovers/v0.3-cognitive-layer-track.md`.

#### Operational UX (cycle 12, live usability)
- **PR-O1** — `/admin/entities/<id>` 노드 클릭 요약 403 fix (Bearer
  header). PR #277.
- **PR-O2** — chat suggestion chips: 3 natural-language patterns added
  ("혹시 ~궁금하신가요?", "~에 대해 더 알고 싶으시면", "관련된
  질문으로는"), threshold relaxed `>=2 → >=1`. PR #279.
- **PR-O3** — long-term wiki save chip in-place spinner → ✓/✗ transition
  with mint accent ring, 1.4 s failure restore. PR #280.
- Remaining PR-O4 (N-3 long_ctx isolation) / PR-O5 (external matrix
  tightening) / PR-O6 (node editing + Korean labels) / PR-O7 (drag +
  click-to-connect) deferred to v0.3.0.x. Track:
  `docs/handovers/v0.3-operational-ux-track.md`.

#### Cyber UI — mono-cyber palette (6a → 6d)
- Mono-cyber palette migration: single `--accent` (mint) on dark
  background, replacing the v0.2 multi-hue gradient. PRs #222–#224.
- **6a** background texture (grid + corner radials). PR #223.
- **6b** single-accent glow on primary surfaces. PR #224.
- **6c** modal glassmorphism (`@supports (backdrop-filter)`). PR #225.
- **6d** live indicators (pulse dot + scan line, 4-page rollout). PRs
  #226 / #228.
- Token consolidation into `frontend/static/tokens.css`. PRs #214 / #221.
- WCAG dialog pattern on every modal (focus trap + ESC + ARIA roles).
  PR #216. `aria-label` on icon-only and JS-populated buttons. PR #217.
  `--muted-2` lifted above WCAG AA. PR #218.
- Inline-handler → `data-action` event delegation across all 4 pages.
  PRs #230, #232, #233, #241.

#### Audit pipeline — JSONL → SQLite mirror (Phase 1 → 4)
- **Phase 1** — tool JSONL events mirrored to SQLite `audit_log`. PR #206.
- **Phase 2** — attack + system JSONL events mirrored. PR #207.
- **Phase 3** — `/admin/audit/list` categories (`tools` / `attack` /
  `system`). PR #208.
- **Phase 4a** — legacy `/admin/audit` dropped; dashboard reads SQLite.
  PR #210.
- **Phase 4b-1** — `/code/surface/` reader migrated to SQLite. PR #211.
- **Phase 4b-2 (writer removal)** intentionally deferred 2–4 weeks of
  production mirror-reliability monitoring. ROADMAP "Deferred follow-ups".

#### Workspace + Scheduler (W7 / W8)
- **W7-A** — `data_artifacts` table + lifecycle (uploaded → extracted →
  indexed / failed). `wiki_links` records doc → entity derivation. PR #191.
- **W7-B** — standalone `/workspace` data-explorer page. PR #192.
- **W8-A** — generic job execution backbone + 3 handlers
  (`excel_build` / `doc_combine` / `entity_export`). PR #193.
- **W8-B** — chat-sidebar workspace tab. PR #194.
- **W8-C** — `wiki_links` populated on upload. PR #195.
- **W8-D** — scheduler with small cron DSL (`every:N` / `hourly` /
  `daily:HH:MM` / `weekly:DOW:HH:MM`) + 90-day result retention. PR #197.
- **W8-D follow-up** — `/admin/scheduler/status` + `/jobs/unschedule`. PR #204.

#### Auth + Policy matrix (W4 P3 / Q1-Q3)
- **W4 P3-2** — request authentication accepts `X-API-Key` header or
  `?api_key=` query parameter; system key resolves to `employee` role
  (no implicit admin authority). PRs #179 / #180.
- **W4 P5** — chat-page password-reset modal. PR #182.
- **W4 P6** — admin audit log page (category filter + search + paging).
  PR #183.
- **W4 Q1** — feature capability registry (`core/feature_registry.py`
  + `feature_overrides` table + `PolicyEngine.can_use_feature`). PR #184.
- **W4 Q2-a** — wire 17 admin endpoints onto `_require_feature`. PR #187.
- **W4 Q2-b** — catalog extension + remaining 38 endpoints. PR #188.
- **W4 Q2-c** — user-facing feature gates on `/query` / `/upload` /
  `/password` / `/api-keys`. Behaviour change: `/upload` denied for
  `employee` / `external` by default (previously any valid api_key).
  PR #189.
- **W4 Q3** — admin permission matrix UI (feature × role grid).
  PR #190.

#### License Track A + OpenSSF passing badge
- License Track A cleanup: `THIRD_PARTY_LICENSES.md` (one-shot via
  `pip-licenses`), README license-line unification, first-quarter
  trigger monitoring entry in `docs/LICENSE_PLAN.md §8`. PR #259.
- **OpenSSF Best Practices passing badge** achieved (2026-05-11,
  Tiered 111%). Badge displayed in `README.md` / `README.ko.md`.
  Project page: https://www.bestpractices.dev/projects/12806.

#### v0.2 axes 6 closure + Axis 6 user-feedback follow-ups
- **N-1** — `/admin/graph` snapshot now reflects entity files written
  by other engines (cache invalidation). PR #256.
- **N-3** — new-session greeting + cross-session leak (partial fix;
  full isolation in v0.3.0.x PR-O4). PR #257.
- **Web learn fix** — `/web learn` routes through proper LLM triple
  extraction (no more query-as-node). PR #252.
- **2-pass UNRESOLVED sweep** — every ingest resolves UNRESOLVED
  target_id references on a second pass. PR #253. Manual grand-sweep
  trigger: `POST /admin/wiki/resolve-relations`. PR #261.
- **One-shot cleanup script** for pre-#252 web-learn noise concepts.
  PR #254 (user runs `--apply` after dry-run review).
- **Workspace continuity** — `core/reasoning/modes.py` conversation
  continuity (Axis 6 item 1). PR #249.
- **Clean answer + dual web-search chip** (Axis 6 items 2-3). PR #248.
- **Reasoning panel** — retrieve → expand → verify phase grouping in
  `/admin/dashboard`. PR #235.
- **Citation chips** — `graph_paths` rendered as mint citation chips
  in chat answers. PR #229.

#### Chat UX (cycle 5)
- **N-4** — suggestion chip header with mint accent + uppercase. PR #263.
- **N-5** — mid-band web-search chip when retrieval below the
  configurable threshold. PR #263.
- **N-6** — in-page long-term save modal (`jamesConfirm()` replaces
  native `confirm()`, 6c glass + mint, WCAG dialog ARIA). PR #264.

#### Multimodal + extras
- **Video ASR** — ffmpeg + Whisper pipeline (`W1 §3-C Option A`). PR #198.
- **Chat file drag-drop + clipboard paste** with mini-thumbnails and
  sidebar auto-switch (W5 / W6). PRs #185 / #186.

### Changed

- **`core/memory/store.py` split** — 24 KB → 12 KB across natural
  boundaries (`db.py` / `conversation.py` / `summaries.py` +
  `store.py` facade). Public API preserved. CLAUDE.md rule #5 module
  size gate restored. PR #260.
- **Mono-cyber palette migration** — every page repainted; legacy CSS
  token aliases removed. PR #220.
- **`urllib3 >= 2.7.0` + `python-multipart >= 0.0.27`** floors
  raised to close 6 Dependabot high-severity alerts. PR #244.

### Security

- **`python-multipart >= 0.0.18`** floor raised earlier in the cycle
  for GHSA-59g5-xgcq-4qw3 (DoS via unbounded multipart part headers).
  PR #213.
- **`/upload/` feature gate** — `employee` / `external` denied by
  default (W4 Q2-c). A leaked `JAMES_API_KEY` alone (resolves to
  `employee`) no longer ingests documents.
- **Multimodal trust quarantine** continues from v0.2 Axis 4; web
  results pass `PolicyEngine.quarantine()` before joining the LLM
  context. Codified in `core/policy_engine.py` + `TrustedContent`.

### Fixed

- **F541 / F401 lint cleanup** — main CI green restored after Phase A
  migration residuals. PR #278.
- Several smaller live-usage fixes folded into the cycle 12 quick-fix
  bundle (PRs #277 / #279 / #280).

### Deprecated / Removed

- **Legacy `/admin/audit` endpoint** removed in Audit Phase 4a (#210).
  Operators migrate to `/admin/audit/list?category=…`.
- **Legacy CSS token aliases** removed. PR #220.

### Migration

```bash
git pull origin main
git checkout v0.3.0
pip install -r requirements.txt   # urllib3 >= 2.7.0, python-multipart >= 0.0.27

# new opt-in env knobs:
export JAMES_GRAPH_EDIT=1            # enable Phase E graph editor
export JAMES_ENABLE_EVOLUTION=0      # self-evolution opt-in (unchanged)
export JAMES_TRACE_STDOUT=0          # silence per-stage console mirror (unchanged)

# verify:
python -m unittest discover -s tests
python scripts/bench.py --suite=step7
```

If you ran v0.2.0 with a populated wiki, the Phase A migration ran
automatically on first boot under v0.3 — verify backup at
`wiki.pre-v03-migration/` before deleting it.

### Pending live validation (shipped, will follow up if regressions)

- Phase D file-modify cascade (#274) — end-to-end live verification
  with diverse formats
- Phase E graph editor UI (#273) — full edit-mode UX flow
- Cycle 12 PR-O1 / PR-O2 / PR-O3 — admin-UI / chat live spot-check
- Phase A migration (#266) `bench step7 --check` byte-identical
  verification on the user's production corpus

---

## [0.2.0] — Foundation Hardening (released 2026-05-08)

### Security

- **`python-multipart` spec floor raised to `>=0.0.18`** (GHSA-59g5-xgcq-4qw3
  — Denial of Service via unbounded multipart part headers). The pinned
  install (`requirements_pinned.txt`) was already on 0.0.26, so no
  upgrade-side risk; this change aligns `requirements.txt`'s spec with
  the safe minimum and closes Dependabot alerts #5 and #6 (both High).

### Added

#### OpenSSF Best Practices passing badge
- Achieved the **OpenSSF Best Practices passing badge** (2026-05-11,
  Tiered 111%). Badge is now displayed in `README.md` and
  `README.ko.md`. Project page:
  https://www.bestpractices.dev/projects/12806
- The submission documents the project's posture on bug-reporting,
  vulnerability disclosure (GitHub PVR + backup email), licensing
  (MIT), versioning (SemVer + 7 GitHub Releases), test suite
  (`james_*_test.py` and `tests/`), bcrypt password storage
  (PR #173, W4 P1-A), and static analysis baseline
  (PR #196 — ruff F821 enforcement with phased plan).

#### Reasoning Graph Visualizer (Axis 3 Observability/Explainability)
- **`/admin/graph`** — new admin-only 3D page that renders every wiki
  entity as a point in a soft-ball sphere and every ontology relation
  as a connecting line. Drag to rotate 360°, scroll to zoom, click to
  focus. Force-directed layout with link strength ∝ `min(deg(s), deg(t))`
  so densely-connected nodes drift together; a custom radial spring
  pulls the layout toward a sphere shell.
- **`/admin/graph/snapshot`** — new admin-gated read-only data endpoint
  (`source_type=prod|test`) that materializes the full entity + edge
  set as JSON. Cached by `(source_type, max_mtime)`; gzip-friendly
  short keys (`s`/`t`).
- **Pulse animation** — when a query is asked from the page's bottom
  query bar, the response's `graph_paths` strings are parsed
  client-side and a cyan additive sprite tweens along each traversed
  edge in chronological order, leaving a 4 s afterglow.
- **Sensitivity-aware**: nodes with `sensitivity == "sensitive"` and
  edges whose ontology entry is `sensitive=True` (HAS_SECRET,
  KNOWS_PASSWORD, HAS_CREDENTIAL, OWNS_PRIVATE) are filtered out
  server-side by default. `include_sensitive=1` is locked off until a
  dedicated elevated role lands.

### Implementation notes
- New module `core/graph_snapshot.py` (~8.4 KB) sits alongside
  `core/graph_engine.py` (15.8 KB) so the latter stays well under the
  20 KB module-size gate. No retrieval / pipeline / ontology code was
  modified — the visualizer is pure observability over data that
  already exists.
- 3D libs (Three.js 0.160, 3d-force-graph 1.73, d3-force-3d 3) are
  loaded from CDN; matches the project's no-bundler vanilla-JS
  posture. Vendoring for air-gapped deploys is tracked separately.
- Tests in `tests/test_graph_snapshot.py` cover the snapshot shape,
  sensitivity filter, mtime-based cache invalidation, server route
  registration, and frontend artifact contract.

---

## [0.1.1] — Path Auto-Detection (Patch)

### Fixed

#### Critical: Hardcoded Paths Removed
- **config.py**: `BASE_DIR` was hardcoded. Now auto-detected from `config.py`'s own location.
- **config.py**: Removed hardcoded user paths exposing the developer's Windows username.
- **vector_store.py**: `LOCAL_MODEL_PATH` was hardcoded. Now derives from `BASE_DIR`. Fixes the issue where renaming the project folder caused the embedding model to be re-downloaded externally.
- **patch_abac_fields.py / tools/admin/seed_data.py / tools/admin/wiki_reset.py**: Replaced hardcoded fallback paths with location-relative detection.

#### Cross-Platform Support
- Tesseract OCR path: auto-detected for Windows / macOS / Linux
- Poppler path: auto-detected for Windows; uses system PATH on macOS / Linux
- Ollama path: uses system PATH (no hardcoded location)

### Added
- Environment variable overrides for all binary paths:
  - `TESSERACT_PATH` — Tesseract binary
  - `JAMES_POPPLER_PATH` — Poppler bin directory
  - `OLLAMA_PATH` — Ollama binary
  - `JAMES_MODEL_PATH` — Sentence-Transformer model location
  - `JAMES_LLM_MODEL` — Default LLM model name (default: `gemma2:2b`)
  - `OLLAMA_API_URL` — Ollama API endpoint
  - `JAMES_MAX_UPLOAD_MB` — Upload size limit (default: 100)

### Security
- **CRITICAL**: Previous version (v0.1.0) included paths revealing the developer's local Windows username. Anyone cloning the repository could see this information. Now removed.
- Project folder can be renamed/moved freely without breaking functionality.
- Anyone cloning the repository can run `python server_llmwiki.py` immediately without editing paths.

### Migration from v0.1.0
No migration steps needed. The fix is backward compatible:
- Existing installations will continue to work
- Folder rename now safe
- No database / data changes required

---

## [0.1.0-alpha] — Initial Release

### Added

#### Core Engine
- Hybrid Search (Vector 60% + BM25 20% + keyword 20%)
- Graph-RAG with 12 ontology relation types
- DFS traversal with confidence-based pruning
- ChromaDB vector store with Sentence-Transformers embeddings
- Ollama-based local LLM execution

#### Security
- 3-stage access control (Vector / Graph / Output)
- RBAC with 4 roles
- ABAC with 4 sensitivity levels
- 31+ prompt injection pattern detection
- Instruction Isolation framework
- JWT authentication
- Rate limiting (30 req/60s)
- Full audit log in SQLite

#### Knowledge Management
- Markdown-based wiki as knowledge graph
- File ingestion (PDF, DOCX, images, video, audio)
- Automatic entity extraction and linking
- Relations stored in YAML frontmatter

#### Self-Evolution Scaffolding
- Patch Pipeline with 4-Gate validation
- 11-trait personality system
- Knowledge tracker (8 abilities + 6 domains)
- Feedback engine

#### Multimodal & Tools
- LLaVA, Whisper, ffmpeg, pytesseract, easyocr integrations
- Sandboxed Python execution
- File upload pipeline

#### Web Search
- Tavily (primary) + DuckDuckGo (fallback)

#### User Interface
- Web-based chat UI + Admin dashboard
- Session management
- Reasoning path visualization
- Confidence badges

#### Internationalization
- 286 i18n keys (English / Korean)
- Default language: English
- Live toggle (KO / EN)

#### Documentation
- README.md, README.ko.md
- SECURITY.md, ROADMAP.md, CONTRIBUTING.md, CHANGELOG.md
- .env.example

---

[0.3.0]: https://github.com/Hashevolution/James-RAG-Evol/releases/tag/v0.3.0
[0.2.0]: https://github.com/Hashevolution/James-RAG-Evol/releases/tag/v0.2.0
[0.1.1]: https://github.com/Hashevolution/James-RAG-Evol/releases/tag/v0.1.1
[0.1.0-alpha]: https://github.com/Hashevolution/James-RAG-Evol/releases/tag/v0.1.0-alpha
