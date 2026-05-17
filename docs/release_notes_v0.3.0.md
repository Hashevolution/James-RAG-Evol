# v0.3.0 — Platform Skeleton

After **190 merged PRs** since v0.2.0 (9 days, 129 test files), JAMES
exits the v0.2 Foundation Hardening cycle and enters **v0.3 Platform
Skeleton**. Axis 6's second-user gate cleared on 2026-05-13 — the
v0.2 → v0.3 gate is formally clear.

The original v0.3 plan was a single theme (Plugin API). After the
2026-05-14 user briefing, that plan was rebalanced:

- **Cognitive Layer** becomes the second main track (`docs/ARCHITECTURE.md §5.7`).
- **Knowledge Cascade** (sources-aware graph) lands in v0.3.0 itself
  rather than slipping (Phase A → E all shipped).
- **Plugin API** slips to v0.3.x or v0.4 until external-contributor
  demand actually appears.
- **CR-E** (self-evolution → Change Request wrap) folds into the
  Cognitive Layer Phase 2 verification engine instead of shipping
  standalone.

This is the "platform contract is forming; cognitive depth is being
designed" milestone. Plugin API stability is **not yet promised** —
that gate moves to v0.4.

---

## 한국어 요약

자메스가 **v0.3 Platform Skeleton** 단계에 진입했습니다. v0.2 6축
hardening 의 마지막 게이트 (실데이터 두 번째 사용자) 가 2026-05-13 통과.
v0.2.0 이후 9 일 동안 **190 PR 머지, 129 개 테스트 파일**.

원래 v0.3 의 단일 테마는 Plugin API 였지만, 2026-05-14 사용자 브리핑
후 재조정되었습니다:

- **Cognitive Layer** (`ARCHITECTURE.md §5.7` 신설) 가 두 번째 메인 트랙
- **Knowledge Cascade** (Phase A → E) 가 본 v0.3.0 에 모두 들어감
- **Plugin API** 는 외부 기여자 트리거 발생 전까지 v0.3.x / v0.4 슬립
- **CR-E** (자가-진화 → CR 통합) 은 Cognitive Layer Phase 2 verification
  engine 과 합쳐 진행 (단독 PR 없음)

Plugin API 안정성은 **아직 약속하지 않습니다** — v0.4 로 이동.

---

## What's new (theme-by-theme)

### Change Request primitive (v0.2.x track)

`core/change_request.py` generalises the `approver_username` pattern
that v0.1 hard-coded for self-evolution alone. Every write becomes a
proposal → review → admin approval → atomic apply → audit row.

- Two target types: `wiki_entity` (markdown edits with `base_hash`
  conflict detection) and `run_jobs` (workspace job execution gate).
- Closed enum for `target_type` on purpose — the registration API is
  the v0.3 plugin contract surface.
- Workspace UI panel for proposers / reviewers.
- Trust zone in `docs/ARCHITECTURE.md §5.6`. Cycle plan in
  `docs/handovers/v0.2.x-cr-track.md`.
- **CR-E** (self-evolution wrap) descoped from v0.2.x and folded into
  Cognitive Layer Phase 2 PR-6 (verification engine fuses with CR-E
  end-to-end).

PRs: #237, #243, #239, #240, #247.

### Knowledge Cascade — sources-aware graph (Phase A → E)

The v0.2 single-`confidence` field on relations becomes `sources:
[{doc_id, weight, role, ts}]`. File delete / modify now surgically
updates only the affected derived knowledge.

| Phase | Shipped | PR |
|---|---|---|
| A — schema + migration | 213 entities / 656 relations back-filled. Backup at `wiki.pre-v03-migration/` | #266 |
| B — ingestion writes sources directly | `role=extract` outgoing + `role=inverse` inverse + doc self-source | #269 |
| C — file delete cascade | `DELETE /admin/files` + `core/cascade.py` with strengthened orphan rules | #270 |
| D — file modify cascade | `PUT /admin/files` (multipart replace) + extraction sidecar JSON + diff_triples | #274 |
| E backend — graph editor | `core/graph_editor.py` replace / append / delete + bidirectional sync, behind `JAMES_GRAPH_EDIT=1` | #271 |
| E UI — edge edit modal | `/admin/graph` edit-mode toggle + edge-click modal (sources + manual append + delete) | #273 |

Manual grand-sweep trigger after large imports:
`POST /admin/wiki/resolve-relations` (PR #261).

### Cognitive Middleware Layer (architecture only, code in v0.3.x)

`docs/ARCHITECTURE.md §5.7` introduces the cognitive middleware layer
between retrieval and LLM synthesis:

- 7 named components (Planner / Query Rewriter / Reflection /
  Verification / Tool Router / Memory Manager / Security Reasoner /
  Context Optimizer)
- Trust zone + **trace-replay invariant** (full reasoning trace must
  be reconstructable from `audit_bridge` rows alone)
- **5-role multi-agent cap (anti-sprawl)** — Orchestrator + Domain
  Specialist + Verification Agent + Security Validator + Final
  Synthesizer. Roles vs workers distinction codified.
- Memory scope layering (system / workspace / session) with read-only
  downward inheritance; promotion is never automatic
- Deployment isolation deferred to v0.4 (policy-based isolation
  already covers the threats container isolation usually addresses)

Code lands across v0.3.x phases. Cycle plan in
`docs/handovers/v0.3-cognitive-layer-track.md`.

PR: #275.

### Operational UX (cycle 12, live usability)

| PR | Item | Detail |
|---|---|---|
| #277 | Node-click 403 | `/admin/entities/<id>` fetch gains `Authorization` Bearer header (`admin.data` gate satisfied) |
| #279 | Suggestion-chip NL patterns | 3 natural-language regex added; threshold `>=2 → >=1` |
| #280 | Save-chip spinner | In-place `<span>` swap to mint accent ring → ✓/✗ on response, 1.4 s failure restore |

PR-O4 (N-3 long_ctx isolation) / PR-O5 (external matrix tightening) /
PR-O6 (node editing + Korean labels) / PR-O7 (drag + click-to-connect)
deferred to v0.3.0.x. Track: `docs/handovers/v0.3-operational-ux-track.md`.

### Cyber UI — mono-cyber palette (6a → 6d)

Single `--accent` (mint) on dark background, replacing the v0.2
multi-hue gradient.

- **6a** background texture (grid + corner radials) — PR #223
- **6b** single-accent glow on primary surfaces — PR #224
- **6c** modal glassmorphism (`@supports (backdrop-filter)`) — PR #225
- **6d** live indicators (pulse dot + scan line, 4-page rollout) — PRs #226, #228
- Token consolidation into `frontend/static/tokens.css` — PRs #214, #221
- **WCAG dialog pattern** on every modal (focus trap + ESC + ARIA roles) — PR #216
- `aria-label` on icon-only / JS-populated buttons — PR #217
- `--muted-2` lifted above WCAG AA + contract test — PR #218
- Inline-handler → `data-action` event delegation across all 4 pages —
  PRs #230, #232, #233, #241

### Audit pipeline — JSONL → SQLite mirror

| Phase | Scope | PR |
|---|---|---|
| 1 | tool JSONL events mirrored to `audit_log` | #206 |
| 2 | attack + system JSONL events mirrored | #207 |
| 3 | `/admin/audit/list` categories (tools / attack / system) | #208 |
| 4a | legacy `/admin/audit` dropped; dashboard reads SQLite | #210 |
| 4b-1 | `/code/surface/` reader migrated | #211 |
| 4b-2 | JSONL writer removal | **deferred** — 2–4 weeks of mirror-reliability monitoring first |

### Workspace + Scheduler (W7 / W8)

- **W7-A** — `data_artifacts` lifecycle table (uploaded → extracted →
  indexed / failed) + `wiki_links` doc↔entity derivation (#191)
- **W7-B** — standalone `/workspace` data-explorer page (#192)
- **W8-A** — generic job execution backbone + 3 handlers
  (`excel_build` / `doc_combine` / `entity_export`) (#193)
- **W8-B** — chat-sidebar workspace tab (#194)
- **W8-C** — `wiki_links` populated on upload (#195)
- **W8-D** — scheduler with small cron DSL (`every:N` / `hourly` /
  `daily:HH:MM` / `weekly:DOW:HH:MM`) + 90-day result retention (#197)
- **W8-D follow-up** — `/admin/scheduler/status` +
  `/jobs/unschedule` (#204)

### Auth + Policy matrix (W4 P3 / Q1 → Q3)

- **W4 P3-2** — request authentication accepts `X-API-Key` header or
  `?api_key=` query parameter; system key resolves to `employee` role
  (no implicit admin authority). PRs #179 / #180
- **W4 P5** — chat-page password-reset modal (#182)
- **W4 P6** — admin audit log page (category filter + search + paging) (#183)
- **W4 Q1** — feature capability registry
  (`core/feature_registry.py` + `feature_overrides` table +
  `PolicyEngine.can_use_feature`) (#184)
- **W4 Q2-a** — wire 17 admin endpoints onto `_require_feature` (#187)
- **W4 Q2-b** — catalog extension + remaining 38 endpoints (#188)
- **W4 Q2-c** — user-facing feature gates on `/query` / `/upload` /
  `/password` / `/api-keys`. **Behaviour change**: `/upload` denied
  for `employee` / `external` by default (#189)
- **W4 Q3** — admin permission matrix UI (feature × role grid) (#190)

### Governance — License Track A + OpenSSF

- License Track A cleanup: `THIRD_PARTY_LICENSES.md` (one-shot via
  `pip-licenses`), README license-line unification, first-quarter
  trigger monitoring entry in `docs/LICENSE_PLAN.md §8` (#259)
- **OpenSSF Best Practices passing badge** achieved (2026-05-11,
  Tiered 111%). Badge displayed in `README.md` / `README.ko.md`.
  Project page: https://www.bestpractices.dev/projects/12806

### v0.2 closure + Axis 6 user-feedback follow-ups

- **N-1** — `/admin/graph` snapshot now reflects entity files written
  by other engines (cache invalidation) (#256)
- **N-3** — new-session greeting + cross-session leak (partial fix;
  full isolation in v0.3.0.x PR-O4) (#257)
- **Web learn fix** — `/web learn` routes through proper LLM triple
  extraction (no more query-as-node) (#252)
- **2-pass UNRESOLVED sweep** — every ingest resolves UNRESOLVED
  target_id references on a second pass (#253)
- **One-shot cleanup script** for pre-#252 web-learn noise concepts
  (#254 — user runs `--apply` after dry-run review)
- **Workspace continuity** — `core/reasoning/modes.py` conversation
  continuity (Axis 6 item 1) (#249)
- **Clean answer + dual web-search chip** (Axis 6 items 2-3) (#248)
- **Reasoning panel** — retrieve → expand → verify phase grouping
  in `/admin/dashboard` (#235)
- **Citation chips** — `graph_paths` rendered as mint citation chips
  in chat answers (#229)

### Chat UX (cycle 5)

- **N-4** — suggestion chip header (mint accent + uppercase) (#263)
- **N-5** — mid-band web-search chip when retrieval below threshold (#263)
- **N-6** — in-page long-term save modal (`jamesConfirm()` replaces
  native `confirm()`, 6c glass + mint, WCAG dialog ARIA) (#264)

### Multimodal + extras

- **Video ASR** — ffmpeg + Whisper pipeline (W1 §3-C Option A) (#198)
- **Chat file drag-drop + clipboard paste** with mini-thumbnails and
  sidebar auto-switch (W5 / W6) (PRs #185 / #186)

---

## Breaking / behavior changes

- **`/upload/` feature gate** — `employee` / `external` denied by
  default (W4 Q2-c, PR #189). A leaked `JAMES_API_KEY` alone
  (resolves to `employee`) no longer ingests documents. Admins who
  want to permit employee uploads add an override row in the W4 Q3
  matrix.
- **Legacy `/admin/audit` endpoint** removed (Audit Phase 4a, PR
  #210). Operators migrate to `/admin/audit/list?category=…`.
- **Legacy CSS token aliases** removed (PR #220). Custom CSS targeting
  removed aliases must update to current tokens.
- **`JAMES_GRAPH_EDIT=1`** is the opt-in flag for the Phase E graph
  editor (#271). Off by default — admin UI shows read-only.
- **Phase A migration** runs automatically on first boot under v0.3
  for any wiki populated under v0.2. Backup at
  `wiki.pre-v03-migration/` — verify before deleting.
- **`urllib3 >= 2.7.0` + `python-multipart >= 0.0.27`** floors raised
  (closes 6 Dependabot high-severity alerts, PR #244).

---

## How to upgrade

```bash
git pull origin main
git checkout v0.3.0
pip install -r requirements.txt   # urllib3 >= 2.7.0, python-multipart >= 0.0.27

# new opt-in env knobs:
export JAMES_GRAPH_EDIT=1            # enable Phase E graph editor (off by default)

# unchanged from v0.2:
export JAMES_ENABLE_EVOLUTION=0      # self-evolution opt-in
export JAMES_TRACE_STDOUT=0          # silence per-stage console mirror
export JAMES_TRACE_RETENTION_DAYS=14 # keep 2 weeks of traces

# verify:
python -m unittest discover -s tests
python scripts/bench.py --suite=step7
```

If you ran v0.2.0 with a populated wiki, the Phase A migration runs
automatically on first boot under v0.3 — verify backup at
`wiki.pre-v03-migration/` before deleting it.

---

## Pending live validation

Shipped but not yet fully verified on diverse production corpora.
Follow-up patches will land in v0.3.0.x if regressions surface:

- Phase D file-modify cascade (#274) — end-to-end live verification
  across diverse formats
- Phase E graph editor UI (#273) — full edit-mode UX flow
- Cycle 12 PR-O1 / PR-O2 / PR-O3 — admin-UI / chat live spot-check
- Phase A migration (#266) — `bench step7 --check` byte-identical
  verification on the user's production corpus

---

## What's next

**v0.3.x — Cognitive Layer (cycle 11, main track)**

| Phase | Scope |
|---|---|
| **0** Reasoning infrastructure | `core/reasoning/backends/` + `trace_schema.py` MVP, pipeline wiring, replay tool |
| **1** Retrieval Intelligence | Reranker (cross-encoder ms-marco-MiniLM) / Query rewriter / Hybrid search / Adaptive retrieval |
| **2** Cognitive Middleware | Reflection loop / Verification engine (fuses CR-E) / Planner / Tool router |
| **3** Memory Expansion | Episodic / Working / Long-term graph events (codifies §5.7.6 scopes) |
| **4** Controlled Multi-Agent | Orchestrator + 4 specialist roles only (anti-sprawl invariant) |

**v0.3.x — Operational UX (cycle 12, side track)**

PR-O4 (N-3 long_ctx isolation) / PR-O5 (external feature matrix
tightening with `query.internal_rag`) / PR-O6 (node attribute editing
+ Korean labels) / PR-O7 (drag + click-to-connect, candidate for a
separate cycle).

**Sleeping (re-entry on trigger)**

- Plugin API (cycle 7) — re-enters when an external contributor opens
  a real plugin PR or a domain-pack candidate appears
- CLA Track B (cycle 4) — re-enters on first external PR
- Multilingual matching (cycle 10) — absorbed into Cognitive Phase 1
  `alias_pump`
- Audit Phase 4b-2 writer removal — after 2–4 weeks of mirror
  reliability

See `ROADMAP.md` for the full v0.3 → v0.4 → v1.0 gate definitions and
`docs/PLATFORM_READINESS.md` for the 6-dimension readiness framework.

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)
