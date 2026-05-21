# JAMES — API ↔ UI Cross-Reference Map

> Cross-reference of every HTTP endpoint against its UI caller(s),
> bucketed into the 5 IA areas defined in `docs/UI_IA.md`.
> Purpose: identify orphans, duplicates, multi-callers, and
> area conflicts so the IA migration knows what to clean up.
>
> Status: investigation snapshot. v0.3.0 Platform Skeleton track.
> Last updated: 2026-05-20.

---

## 1. Headline numbers

- **133 HTTP endpoints** (server_llmwiki.py + routers)
- **6 frontend JS files** call into them: `chat.js`, `admin.js`,
  `workspace.js`, `graph.js`, `graph_editor.js`, `graph_node_editor.js`
- **1 CLI consumer** of HTTP API: `scripts/bench.py` (calls `/query/`)
- **20 orphans** (defined backend, no frontend caller)
- **5 duplicate / overlap pairs** (was 6 — `/admin/metrics` vs
  `/admin/performance/metrics/` retracted as a false duplicate, see §5)
- **7 area-conflict endpoints** (read and write straddle two IA areas)

---

## 2. Area distribution

| Area | Count | Representative endpoints |
|---:|---:|---|
| Ask | 9 | `/query/`, `/history/*`, `/feedback/*` |
| My Work | 12 | `/api-keys/*`, `/artifacts/mine/*`, `/jobs/*` |
| Govern | 24 | `/admin/users/*`, `/admin/patches/*`, `/admin/proposals/*`, `/admin/cr/*`, `/admin/features/*` |
| Observe | 28 | `/admin/dashboard`, `/admin/audit/*`, `/admin/memory`, `/admin/evo-reports/*`, `/admin/performance/*`, `/admin/knowledge/*`, `/admin/entities/*`, `/admin/graph/*`, `/trace/*` |
| Configure | 22 | `/llm/*`, `/admin/web-search-*`, `/admin/character/*`, `/admin/persona`, `/admin/settings`, `/admin/learn/topic/*`, `/hardware/` |
| Non-UI infra | 20 | `/login/`, `/signup/`, `/password/*`, `/upload/`, `/status/`, `/healthz`, HTML routes |
| WIP / advanced | 18 | `/code/*`, `/analyze/*`, `/screen/*`, `/export/`, admin file/wiki/graph writes |
| **Total** | **133** | |

The IA core (Ask + My Work + Govern + Observe + Configure) covers
**95 of 133** endpoints (71%). The remaining 38 are infrastructure
(auth, health, static) or work-in-progress (multimodal, code tools)
not yet bound to an IA area.

---

## 3. Orphan endpoints (20)

Backend exists; no frontend caller. Grouped by disposition.

### 3.1 CLI-only (intentional)

| Endpoint | Caller | Action |
|---|---|---|
| `POST /query/` | `scripts/bench.py:104` | Mark CLI-allowed in API docstring |
| `POST /admin/llm/pull` | (CLI / future) | Tag `cli-only` until UI binds |
| `DELETE /admin/llm/delete` | (CLI / future) | Tag `cli-only` until UI binds |
| `GET /admin/patch/audit` | (CLI / future) | Surface in Observe → Audit |

### 3.2 Backend ready, UI not wired yet

| Endpoint | Intended area | Status |
|---|---|---|
| `GET /admin/llm/selections` | Configure | task→LLM mapping read; **wire into Configure → LLM** |
| `POST /admin/llm/select` | Configure | task→LLM write; **wire into Configure → LLM** |
| `DELETE /admin/llm/select` | Configure | task→LLM clear; **wire into Configure → LLM** |
| `POST /history/sessions/rename/` | Ask | session-rename UX missing in chat |
| `GET /history/long-term/` | Ask / Observe | long-term memory inspector missing |
| `GET /feedback/stats/` | Observe | feedback aggregate not surfaced |

### 3.3 Deprecated or redundant

| Endpoint | Reason | Action |
|---|---|---|
| `GET /admin/web-search-status` | dashboard card removed | delete or restore card |
| `GET /admin/character/correlations` | read-only stat, never surfaced | surface in Observe → Character or delete |

(`/admin/metrics` was listed here in an earlier draft as a duplicate
of `/admin/performance/metrics/`; that was an error — see §5
correction. It serves a distinct latency-histogram purpose and stays.)

### 3.4 WIP / advanced (18 endpoints, holding)

`/code/read/`, `/code/analyze/`, `/code/edit/`, `/code/surface/`,
`/analyze/image/`, `/analyze/video/`, `/screen/analyze/`,
`/admin/jobs/list`, `/admin/jobs/{job_id}`, `/admin/artifacts/list`,
`/admin/artifacts/{artifact_id}`, `/admin/files` (DELETE/PUT),
`/admin/scheduler/status`, `/admin/wiki/resolve-relations`,
`/export/`, plus 3 admin graph writes already mediated by
`graph_editor.js` / `graph_node_editor.js`.

**Disposition**: leave as-is, but each must appear on the v0.3 →
v0.4 roadmap with a target IA area, or be removed. No silently-living
endpoints.

---

## 4. Multi-caller endpoints (refactor candidates)

Two or more JS files hit the same endpoint with their own
implementation. Each is a duplication risk.

| Endpoint | Callers | Smell |
|---|---|---|
| `POST /login/` | `chat.js:326`, `admin.js:326`, `graph.js:126`, `workspace.js:99` | 4 independent login modals — extracted to `Auth.login()` (auth.js); modal markup itself still per-page (IA Phase 3) |
| `POST /password/reset/confirm` | `chat.js:909`, `admin.js` (modal) | 2 divergent implementations |
| `POST /llm/install/` | `chat.js:463`, `admin.js:494` | `firstRunInstall()` duplicated near-verbatim |
| `GET /admin/llm/install-progress` | `chat.js` (poll), `admin.js:515` | parallel polling loops |
| `POST /query/` | `chat.js:1112`, `scripts/bench.py:104` | OK — one UI, one CLI; expected |
| `GET /artifacts/mine/list` | `chat.js:788`, `workspace.js` | shared My-Work fetch — promote to util |

**Highest leverage**: collapse `firstRunInstall()` and the login modal
into shared modules. Both are first-run-critical paths where divergence
between chat and admin is a real bug source.

---

## 5. Duplicate / overlap pairs (5)

| # | A | B | Recommendation |
|---|---|---|---|
| 1 | `GET /admin/memory` (whole) | `GET /admin/episodic/{session_id}` (single) | Keep both, document hierarchy (whole vs slice) |
| 2 | `/admin/entities` (entities) | `/admin/artifacts/list` (artifacts) | Clarify concept boundary — entity = graph node, artifact = user upload? document in ARCHITECTURE |
| 3 | `GET /admin/jobs/list` (admin, orphan) | `GET /jobs/list` (user, used) | Confirm admin-wide jobs view need; if yes, wire to Observe; if no, delete |
| 4 | `/admin/files/tree` + `/search` (read, used) | `/admin/files` DELETE/PUT (orphan) | Read OK; writes should go through CR — confirm intent |
| 5 | `/llm/install/` vs `/admin/llm/pull` | both download models | One is first-run, other is admin re-pull; document and stop confusing the two |

> **Correction (post-investigation, Phase 1 cleanup, 2026-05-20)**:
> An earlier draft listed `/admin/metrics` and `/admin/performance/metrics/`
> as a duplicate pair. They are **not** duplicates: `/admin/metrics`
> returns trace-derived per-stage latency histograms (p50/p90/p99 from
> `core/trace_metrics.py`), while `/admin/performance/metrics/` returns
> self-evaluation scores (`tools/self/performance_evaluator` +
> `tools/self/importance_scorer`). Both are intentionally distinct and
> live; do not deprecate either.

---

## 6. Area-conflict endpoints (7)

Endpoints whose read and write halves belong in **different** IA
areas. These are the cases UI_IA.md §3.2 flagged ("mixed-mode tabs").

| Endpoint | Read goes to | Write goes to | Pattern |
|---|---|---|---|
| `/admin/entities` | Observe | Govern (via CR) | entity edit is CR-gated |
| `/admin/character/` (GET vs POST) | Observe | Configure | view current persona vs change it |
| `/admin/persona` (GET vs POST) | Observe | Configure | same |
| `/admin/cr/` (lifecycle) | Observe (audit) | My Work (propose) + Govern (approve) | three-area workflow — needs hand-off links per UI_IA §3.3 |
| `/admin/graph/relation` (GET vs PUT/POST/DELETE) | Observe | Govern (via CR) | graph edits CR-gated |
| `/admin/proposals/` (GET list vs approve/reject) | Observe | Govern | propose-vs-approve split |
| `/admin/patches` (list vs approve/reject) | Observe | Govern | propose-vs-approve split |

**Rule** (proposed for IA implementation): on each page, **read
affordances always present, write affordances guarded by area**.
A user viewing entities in Observe sees data; they cannot edit there —
the edit button deep-links into Govern → CR Propose.

---

## 7. Per-file UI caller load

| File | API calls | Primary area(s) | Observation |
|---|---:|---|---|
| `admin.js` | 45+ | Observe + Govern + Configure | mirrors 17-tab monolith — biggest split target |
| `chat.js` | 14 | Ask + My Work | first-run install logic duplicated with admin.js |
| `workspace.js` | 12 | My Work + Govern (CR) | CR lifecycle straddles two areas here |
| `graph_editor.js` | 3 | Govern | relation writes |
| `graph.js` | 2 | Observe | snapshot + login |
| `graph_node_editor.js` | 1 | Govern | node writes |

`admin.js` (45+ calls across 3 IA areas) is the single largest
artefact of the IA debt. The Govern / Observe / Configure split
proposed in UI_IA.md §3.2 corresponds to splitting `admin.js` into
roughly 3 modules of ~15 calls each.

---

## 8. Risk signals worth flagging now

1. **Ask area is anemic in practice**: of 9 endpoints, only 3 are
   actively called (`/query/`, `/history/`, `/feedback/`). Session
   rename, long-term memory, feedback aggregate are all wired but
   unused — symptom of a UI that hasn't surfaced what the backend
   can already do.
2. **Configure → LLM is half-wired**: `/admin/llm/installed` is
   called, but `/admin/llm/selections`, `/admin/llm/select` (POST
   and DELETE) are orphans. Task→LLM mapping is the headline feature
   of Configure and it has no UI.
3. **First-run wizard is duplicated in two files**: `firstRunInstall()`
   exists in both `chat.js` and `admin.js`. Any change to onboarding
   has to be made twice. This is a concrete bug-source today, not
   a hypothetical.
4. **Login modal in 3 files**: changing login UX requires touching
   `chat.js`, `admin.js`, `graph.js`. Pre-IA, extract into one shared
   component regardless of the larger split.

---

## 9. Action checklist (derived)

### Phase 1 — Cleanup (no IA changes yet)

- [x] **Not a duplicate**: `/admin/metrics` (trace latency histogram)
      and `/admin/performance/metrics/` (self-eval scores) confirmed
      distinct; doc corrected (this commit). No code change.
- [ ] Decide and execute: keep or delete `/history/sessions/rename/`, `/history/long-term/`, `/feedback/stats/`
- [ ] Each of the 18 WIP endpoints (`/code/*`, `/analyze/*`, ...) gets a roadmap line or a removal
- [ ] `/admin/web-search-status` — restore the card or delete the endpoint

### Phase 2 — Deduplication (no IA changes yet)

- [ ] Extract first-run install (`firstRunInstall()` + progress poll) into a shared module; call from chat **and** admin
- [ ] Extract login modal into a shared component; remove from `chat.js`, `admin.js`, `graph.js`
- [ ] Standardize `/password/reset/confirm` implementation across `chat.js` and `admin.js`

### Phase 3 — IA migration (the big one)

- [ ] Split `admin.js` along Govern / Observe / Configure boundaries
- [ ] Wire `/admin/cr/` hand-off links per UI_IA §3.3 (My Work → Govern → Observe)
- [ ] Implement the read/write area-split rule from §6 of this doc
- [ ] Wire `/admin/llm/selections` + `/admin/llm/select` into Configure → LLM

### Phase 4 — Naming (v0.4 candidate)

- [ ] API endpoint rename to align with `<area>` prefix (optional, deferred)
- [ ] `data-action` mass-rename per UI_IA §4.1

---

## 10. Reconciliation note

The earlier UI inventory in chat reported **119 endpoints**. This
deeper sweep found **133** — the delta is mostly auth/infra
(`/login/`, `/signup/`, `/password/*`, `/healthz`, `/status/`, HTML
routes) and a handful of admin writes that the first pass collapsed.
Use **133** as the canonical number going forward.

---

## 한국어 요약

JAMES의 HTTP 엔드포인트 133개를 UI 5영역과 크로스레퍼런스한 결과:
**고아 20개, 의미상 중복 6쌍, 영역 충돌 7개**가 확인됐습니다. 가장 큰
부채는 ① `admin.js` 한 파일에 Govern·Observe·Configure가 뒤섞여 있다는
것, ② first-run 설치/로그인 모달이 2~3 파일에 복붙되어 있다는 것,
③ Configure → LLM의 task→모델 매핑 API(`/admin/llm/select*`)가 백엔드에만
존재하고 UI가 없다는 것입니다. IA 마이그레이션 전에 Phase 1(고아 정리),
Phase 2(중복 추출)만 먼저 해도 체감 개선이 큽니다. Phase 3에서 `admin.js`
삼분할과 `/admin/cr/` 핸드오프 링크를 구현합니다.
