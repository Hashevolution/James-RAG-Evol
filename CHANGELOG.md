# Changelog

All notable changes to PROJECT JAMES will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased] — v0.2 Foundation Hardening

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

## Unreleased

See [ROADMAP.md](ROADMAP.md) for v0.2.0 plan.

---

[0.1.1]: https://github.com/Hashevolution/James-RAG-Evol/releases/tag/v0.1.1
[0.1.0-alpha]: https://github.com/Hashevolution/James-RAG-Evol/releases/tag/v0.1.0-alpha
