# JAMES — Architecture & Design Principles

> Engineering reference for contributors. Describes what JAMES is,
> what it deliberately is not, and the trust boundaries that govern
> all design decisions.
>
> Status: living document. Last updated: v0.2.0-dev.

---

## 1. Mission

A **local-first, auditable knowledge reasoning system** that answers
questions over a private knowledge base with:

- explicit reasoning paths (sources + graph trace)
- role-based access at every stage
- human-supervised improvement loop

JAMES sits **alongside** systems of record (ERP, DMS, CMS) — never
replaces them.

---

## 2. Non-goals

JAMES is deliberately **not**:

- a general-purpose AGI or fully autonomous agent
- a replacement for ERP, accounting, inventory, or booking systems
- a cloud-only SaaS (cloud is opt-in, not default)
- a self-modifying system without human approval
- a real-time transactional database
- a legal advisor (analytical assistance only; final review by qualified professionals)

If a feature request implies any of the above, it belongs in a
**downstream product** built on top of JAMES, not in JAMES itself.

---

## 3. Design Principles

| # | Principle | Operational meaning |
|---|---|---|
| 1 | **Local-first** | Default deployment is single-machine, no external network calls required for core path. |
| 2 | **Evidence-based reasoning** | Every answer must cite source documents and graph paths; ungrounded answers are flagged. |
| 3 | **Policy-aware retrieval** | RBAC + ABAC checks fire at retrieval, graph, and output stages — not just at the API edge. |
| 4 | **Auditability over performance** | When in doubt, log more. Audit log is append-only and never silently dropped. |
| 5 | **Human-supervised evolution** | Self-evolution **proposes**; humans **approve**. Deploy without approval is a bug. |
| 6 | **Sandboxed multimodality** | Image, audio, web content are untrusted inputs by default; extraction does not bypass policy. |
| 7 | **Composable boundaries** | Components communicate over typed interfaces, not shared globals. |

---

## 4. Component Layers

```
                ┌──────────────────────────────────────────┐
                │              Frontend / API              │
                └────────────────────┬─────────────────────┘
                                     │
                ┌────────────────────▼─────────────────────┐
                │         Auth + Policy Engine             │  ← RBAC/ABAC
                └────────────────────┬─────────────────────┘
                                     │
        ┌────────────────────────────┼────────────────────────────┐
        │                            │                            │
   ┌────▼─────┐               ┌──────▼────┐              ┌────────▼─────┐
   │  Query   │               │ Retrieval │              │     Tool     │
   │  Router  │               │ (Hybrid)  │              │    Router    │
   └────┬─────┘               └──────┬────┘              └────────┬─────┘
        │                            │                            │
        │                      ┌─────▼─────┐               ┌──────▼─────┐
        │                      │   Graph   │               │  Sandbox   │
        │                      │   Engine  │               │  (FS/Web)  │
        │                      └─────┬─────┘               └──────┬─────┘
        │                            │                            │
        └────────────┬───────────────┴────────────────────────────┘
                     │
              ┌──────▼──────┐                  ┌──────────────┐
              │  Reasoning  │                  │    Memory    │
              │    Loop     │ ◀──────────────▶ │ (Trust-gated)│
              └──────┬──────┘                  └──────────────┘
                     │
              ┌──────▼──────┐
              │   Output    │  ← PII + role mask
              │   Filter    │
              └──────┬──────┘
                     │
              ┌──────▼──────┐
              │  Audit Log  │  (append-only, every decision)
              └─────────────┘
```

Each box is a **module with a typed interface**. No box reaches into
another's internals.

---

## 5. Trust Zones

| Zone | Source | Default trust | Hardening |
|---|---|---|---|
| User input (authenticated) | UI / API | **low** | sanitize, instruction-isolate |
| Internal documents | uploaded files, wiki | medium | content scan on ingest |
| Memory (system-tagged) | reasoning loop, system events | medium | role-locked writes |
| Memory (user-tagged) | feedback, comments | **low** until validated | trust score gate |
| Multimodal extraction | OCR, ASR, vision | **low** | content scan + isolate |
| Web search results | Tavily, DDG | **low** | content scan + isolate |
| Tool output | sandbox | medium | path/command allowlist |

Anything labeled **low** must pass `extract_data_only()` before
joining the LLM context.

### 5.1 Account states (W4 P1-B, 2026-05-11)

Authentication has three identity states. A request's role only
materializes once it reaches **authenticated**; the earlier states
exist so that account creation and admin review have explicit,
auditable transitions.

```
anonymous (no token)
   │  POST /signup/ — public, rate-limited
   ▼
pending (DB row, active=0, role=external)
   │  admin approval + role assignment (W4 P2, upcoming)
   ▼
authenticated (active=1, role ∈ {admin, manager, employee, external})
```

Invariants:

- `authenticate()` returns `None` for any row with `active=0`. A
  pending account cannot be probed by repeated login attempts to
  learn whether the username exists — `/login/` returns 401 in either
  case (no row vs. row-but-pending).
- `/signup/` collapses success and duplicate into the same 200 body.
  An anonymous caller cannot enumerate usernames through it.
- Password policy violations bypass that collapse and return 400 —
  the rule text itself is public and leaks nothing about accounts.
- Pending rows always hold `role=external` regardless of what the
  signer requested. Role assignment happens in the admin approval
  flow, never at signup time.

### 5.2 Credential change paths (W4 P2-B, 2026-05-11)

Once a user is authenticated, two credential-rotation paths exist.
Both run through `core/auth_reset.py` (a sibling of `core/auth.py`
kept separate only to honor the 20 KB module-size gate):

- **Self-service change** (`POST /password/change`): the caller
  supplies the old password plus a new one; the username is read
  from the JWT subject claim, never from the request body. A body
  `username` field, if smuggled in, is ignored — the JWT is the only
  source of identity here.
- **Admin-issued reset** (`POST /admin/users/issue-reset-token`):
  the admin requests a one-shot token for a target user. The
  plaintext token is returned exactly once; the database stores only
  SHA256(token). Tokens expire after 1 hour and are revoked
  automatically if a new token is issued for the same username.
  The user redeems via `POST /password/reset/confirm` with the
  token, their username, and a new password — replay is rejected by
  a `used_at` column updated in the same transaction as the password
  UPDATE.

Both paths apply `validate_password_policy()` from W4 P1-B and
re-hash through `hash_password()` (bcrypt) from W4 P1-A.

### 5.3 User API keys (W4 P3-1, 2026-05-11)

Long-lived credentials for external integrations (CI scripts,
internal tooling). Distinct from the system-wide `JAMES_API_KEY`
env var, which remains the operator's bootstrap secret.

- `core/api_keys.py` (separate module to honor the 20 KB module-size
  gate) issues `jms_<43-char-urlsafe>` tokens. Only SHA256(token) is
  persisted in the `api_keys` table; the plaintext is returned
  exactly once from `POST /api-keys/issue`.
- The first 12 characters (`jms_` + 8 random) form the public
  **prefix** — visible to the owner via `GET /api-keys/list` and
  used as the handle for `POST /api-keys/revoke`. The prefix never
  reveals the body and is not a credential.
- `verify_api_key(plain)` returns the current `(username, role)` —
  the role is read from the users table at call time, so a role
  change on the user row takes effect on the next verify (keys do
  not pin a stale role).
- Revocation is one-way: a revoked key cannot be unrevoked. Issuing
  a fresh key is the rotation path. The `username = ?` filter in
  `revoke_api_key` prevents a caller from revoking another user's
  key via guessed prefix.

**Request-authentication wiring (W4 P3-2)** — the server now
accepts a user API key in two places per request:

- `X-API-Key: jms_...` header (preferred — keeps the credential out
  of URL logs on proxies)
- `?api_key=jms_...` query parameter (back-compat with the legacy
  call shape used by the admin UI and existing scripts)

JWT still wins when both are present. With only a user key, the
caller's role comes from the owning user's row — so a key issued to
an `admin` user passes the `_require_admin` gate, and a key issued
to an `employee` does not. The system `JAMES_API_KEY` is
**deliberately not granted admin authority** by itself — pairing it
with an admin JWT remains required for admin endpoints. A leaked
`.env` value alone cannot self-elevate.

---

## 5.5 PolicyEngine (single source of policy decisions)

`core/policy_engine.py` is the only module that may decide whether a
role is allowed to perform an action. Every consumer (retrieval, graph
walk, tool invocation, output emission) takes a `PolicyEngine` instance
and asks one of four typed methods:

| Method | Question answered |
|---|---|
| `can_retrieve(role, doc_meta) -> Decision` | Vector retrieval: may this role see this document? |
| `can_walk(role, entity) -> Decision`        | Graph DFS: may this role traverse to this entity? |
| `can_call_tool(role, tool, args) -> Decision` | Tool execution: may this role invoke this tool? |
| `can_emit(role, content) -> Decision`       | Output gate: may this role receive this content? |
| `can_use_feature(role, feature_id) -> Decision` | Endpoint-level feature gate (W4-Q1, 2026-05-11). Catalog in `core/feature_registry.py`; admin overrides in `feature_overrides` table. |

`Decision` is `(allowed: bool, reason: str, applied_rule: str)` —
frozen dataclass; `applied_rule` is the canonical id used in audit-log
correlation, e.g. `policy.retrieve.abac` or `policy.tool.admin_only`.

### 5.5.1 Feature capability registry (W4-Q1, 2026-05-11)

`core/feature_registry.py` is the catalog of all endpoint-level
capability names the runtime knows about (`upload.file`,
`admin.users`, `query.web_search`, etc.). Adding a feature is a
**code change on purpose** — the operator UI only exposes feature
ids the catalog knows about, so a typo can never silently authorize
anything.

Each `Feature` carries `id`, `description` (Korean label for the UI),
and `default_allowed` (a frozenset of role names). The catalog is
the source of truth at install time; admins override it through the
small `feature_overrides` table:

```
feature_overrides (
  feature_id  TEXT,
  role        TEXT,
  allowed     INTEGER 0|1,
  updated_at  INTEGER,
  updated_by  TEXT,
  PRIMARY KEY (feature_id, role)
)
```

Empty table ⇒ the entire system runs on the catalog's defaults, which
is the pre-Q1 baseline.

`PolicyEngine.can_use_feature(role, feature_id)` resolves a check as:
1. **Unknown feature_id ⇒ deny** (fail-closed; a typo at a call site
   should fail loudly, not silently authorize).
2. **Override row present ⇒ honor it** (`reason="override.allow"` or
   `"override.deny"`).
3. **Otherwise** ⇒ allow iff `role ∈ feature.default_allowed`.

The `applied_rule` of every decision is `policy.feature.<feature_id>`
so audit-log search can find all checks of one feature with a single
LIKE pattern.

**W4-Q1 scope** — storage layer + the can_use_feature method + admin
management endpoints (`/admin/features/list`, `/admin/features/override`,
`/admin/features/reset`).

**W4-Q2 status (2026-05-11)** — runtime wiring completed in three
slices:
- **Q2-a** rewired 17 admin endpoints whose features Q1 already
  covered (admin.users / admin.audit_log / admin.policy_matrix /
  admin.evolution).
- **Q2-b** extended the catalog with 6 admin.* features
  (admin.settings, admin.data, admin.metrics, admin.character,
  admin.knowledge, admin.tools) and rewired the remaining 38
  `_require_admin` call sites onto `_require_feature`.
- **Q2-c** added feature gates on the user-facing endpoints that
  had previously relied on `verify_api_key` alone:
  - `/query/` → `query.basic` (default: all four roles)
  - `/upload/` → `upload.file` (default: admin + manager only)
  - `/password/change` → `password.change_self` (default: all roles)
  - `/api-keys/issue` + `/list` + `/revoke` → `api_keys.issue_self`
    (default: admin + manager + employee)

  **Behavioural change worth noting**: `/upload/` previously allowed
  anyone holding a valid `api_key` (system key included) to ingest
  documents. With Q2-c, callers in the `employee` / `external` roles
  are denied by default, and a leaked `JAMES_API_KEY` on its own
  (resolved to `employee` per P3-2) no longer suffices. Admins who
  want to permit employee uploads add an override row through Q3.

After Q2-c, every endpoint with role-distinguishable behaviour
consults the matrix. Setting `feature_overrides` rows in the DB (or
via the admin UI in Q3) is the operator's only knob — no code
change required to grant or revoke a feature for a role mid-flight.

**W4-Q3** ships the admin matrix UI (feature × role checkbox grid
+ "기본값 복원").

---

## 6. Data Lifecycle (W7-A, 2026-05-11)

Every file uploaded through `/upload/` gets a tracking row in the
new `data_artifacts` table (in a separate `james_data.db`). The
artifact moves through a small explicit lifecycle:

```
uploaded   ← /upload/ saves bytes to disk + register_artifact()
   ↓
extracted  ← (optional, set when a long-running pipeline pulls text)
   ↓
indexed    ← vector + entity steps succeeded → /upload/ returns 200
   ↓                                              (or)
failed     ← any step in /upload/ raised
```

A second table `wiki_links (artifact_id, entity_id)` records which
wiki entities were derived from which upload — the relationship was
previously implicit in the filename UUID prefix and not queryable.

**Population (W8-C, 2026-05-11)** — `/upload/` captures the
`entity_id` list returned by `wiki_generator.process_document_for_entities`
(or the single id from the `create_entity_file` fallback) and calls
`core.data_artifacts.link_entity` for each. Best-effort write — a
failure leaves the upload itself intact (bytes on disk, vector +
wiki .md files all present) but the artifact ↔ entity relation is
not queryable for that specific upload. Subsequent uploads continue
to populate.

**Authority model — own vs all**

Two surfaces consult the matrix:
- `admin.data` (admin only by default) gates `/admin/artifacts/list`
  and `/admin/artifacts/{id}` — sees every uploader's rows.
- `data.view_own` (all four roles by default) gates
  `/artifacts/mine/list` and `/artifacts/mine/{id}` — scoped to the
  JWT subject. The SQL `WHERE uploaded_by = ?` filter runs in the
  helper, so a non-owner attempting another user's id receives a
  404 (not 403 — 403 would leak existence).

System api_key callers without a JWT cannot reach `/artifacts/mine/*`
(401: there's no "own" to bind). Operators must log in.

**First-boot backfill**

`core.data_artifacts.backfill_from_uploads_dir(UPLOAD_DIR)` runs in
the startup hook. Any file in `uploads/` without a matching row is
inserted with `uploaded_by="legacy"` and `status="indexed"` — the
file is already in the corpus; the row just makes it queryable.
Idempotent on subsequent boots.

**W7-B** ships a standalone `frontend/workspace.html` (not folded
into admin.html — employees can reach it without admin auth) that
renders this layer as a data explorer.
**W8** layers `jobs` + a small scheduler on top so users can run
Excel/document/export jobs against their artifacts.

### 6.1 Jobs (W8-A, 2026-05-11)

`core/workspace.py` adds a `jobs` table (same `james_data.db`) and a
small handler registry. Three generic job types ship with v0.2:

| job_type | what it produces | input_refs |
|---|---|---|
| `excel_build` | `.xlsx` with entity rows (id / name / type / sensitivity / summary) | list of `entity_id` |
| `doc_combine` | single `.md` concatenating entity bodies | list of `entity_id` |
| `entity_export` | `.json` dump of all (or selected category) entities | list of category names; empty = all |

Adding a domain pack's job type is a one-line entry in `HANDLERS` plus
a `run(input_refs, output_dir, options) -> filename` implementation —
Rule #1 keeps that surface intentionally small until v1.0.

**Execution model** — synchronous. `/jobs/run` blocks until the row
reaches `done` or `failed`. Handler runtimes against typical wiki
sizes are well under HTTP timeouts; a real queue + cron scheduler
arrives with W8-A2 once the surface stabilizes.

**Endpoints** (all gate through the matrix):

| endpoint | feature | scope |
|---|---|---|
| `POST /jobs/run` | `workspace.run_jobs` | JWT subject = owner |
| `GET  /jobs/list` | `workspace.view` | own jobs only |
| `GET  /jobs/{id}` | `workspace.view` | own (cross-owner → 404) |
| `GET  /jobs/{id}/download` | `workspace.view` | own |
| `GET  /admin/jobs/list` | `admin.data` | every owner |
| `GET  /admin/jobs/{id}` | `admin.data` | every owner |

Result files land in `workspace/results/<job_id>/<filename>`. The
download endpoint streams via `FileResponse`; the row stores only
the relative path so a future relocation is a no-op DB migration.

### 6.2 Scheduler + retention (W8-D, 2026-05-11)

`core/scheduler.py` adds a polling background thread that re-fires
jobs whose `schedule_cron` column is set, plus a daily sweep of
`workspace/results/` to bound disk usage. No external dependency —
the cron grammar is a small DSL rather than the full crontab format.

**Cron DSL**:

| spec | semantics |
|---|---|
| `every:N` | every N seconds (1 ≤ N ≤ 86400) |
| `hourly` | top of each hour |
| `daily:HH:MM` | every day at HH:MM local time |
| `weekly:DOW:HH:MM` | DOW ∈ mon/tue/wed/thu/fri/sat/sun |

Unknown / malformed spec → `compute_next_run` returns None; the
scheduler pauses the row by setting `next_run_at = NULL`. An
operator typo therefore costs one missed firing, not a runaway loop.

**Endpoint**:

| endpoint | feature | semantics |
|---|---|---|
| `POST /jobs/schedule` | `workspace.schedule` | inserts a row with the chosen spec + first `next_run_at`. Admin-only by default (cron touches shared resources). |

**Loop**: every `poll_interval_sec` (default 60s) the scheduler
selects rows with `schedule_cron IS NOT NULL AND (next_run_at IS
NULL OR next_run_at <= now)`, runs `execute_job` for each, and
writes the recomputed `next_run_at`. Daemon thread; per-tick errors
are logged, never propagate.

**Retention**: `workspace/results/<job_id>/` directories whose
owning job's `finished_at` is older than `RESULT_RETENTION_DAYS`
(default 90) are removed daily. Pending/running jobs are skipped.
Legacy directories with no matching row fall back to filesystem
mtime.

**Disabling**: `JAMES_DISABLE_SCHEDULER=1` keeps the singleton
dormant — useful for one-shot CLI tools and tests.

**TrustedContent** is the wrapper every multimodal extractor (OCR,
ASR, vision, web) returns instead of a raw string. Carries
`(text, source, trust)` so the reasoning pipeline knows whether to run
`extract_data_only()` before joining content into the LLM context.

**Done-when criterion**: removing `core/policy_engine.py` causes ≥ 4
modules to fail import. That is the proof that every policy decision
runs through one chokepoint — the goal of v0.2 ROADMAP Axis 4.

**Migration phases** (#44):

1. Skeleton (this section, lands in v0.2): every method delegates to
   `core/security_layer.py` primitives. No behavior change.
2. Move retrieval / graph / output call sites onto the engine
   (one PR each, with bench numbers per CLAUDE.md rule 2).
3. Sandbox migration to capability tokens (`can_call_tool`).
4. Multimodal extractors return `TrustedContent`; reasoning pipeline
   gates `low`-trust content through `extract_data_only()` at one
   chokepoint.

After all four phases, direct `check_access` imports outside of
`security_layer.py` (the implementation backend) and `policy_engine.py`
become a regression.

---

## 5.6 Change Request primitive (v0.2.x, in progress)

`core/change_request.py` is the single primitive for governing
**write actions** — wiki edits, workspace job runs, ontology
patches, config saves. It generalises the `approver_username`
pattern that v0.1 hard-coded for self-evolution alone: every
write becomes a proposal first, every merge requires an approver,
every transition writes one row to `audit_bridge`.

```
proposer (any authenticated user)
   │ POST /admin/cr/        (target_type + target_id + proposed_diff + base_hash)
   ▼
change_requests row, status='open'
   │ POST /admin/cr/{id}/review     ← any authenticated user; cr_reviews row
   │ POST /admin/cr/{id}/approve    ← admin only
   ▼
apply() under SQLite transaction:
   ├─ target-specific apply (mutates wiki / runs job / ...)
   ├─ change_requests row → status='merged'
   └─ audit_bridge row recording the transition
```

Three properties make this the right shape for the mother platform:

1. **Domain-neutral**. The proposal / review / merge / audit cycle
   is universal — the same object makes sense for clause edits,
   nutrition labels, or single-operator notes. Domain coupling
   enters only at v1.0 (CLAUDE.md rule #1, `docs/PLATFORM_READINESS`).
2. **Append-only audit is the source of truth**. The
   `change_requests` table itself can be reconstructed from
   `audit_bridge` rows. The audit-bridge invariant from §4
   (auditability over performance) extends to the CR primitive.
3. **No external `target_type` registration before v0.3**. The
   dispatcher is a closed enum on purpose — the registration API is
   exactly the v0.3 plugin contract surface and locking it before
   then would force a breaking change later.

### Trust zone

| Edge | Default trust | Hardening |
|---|---|---|
| proposer | **low** | `_require_auth` only; proposal is inert until merged |
| reviewer (comment / request_changes) | **low** | same as proposer |
| reviewer (approve / reject) | requires admin role | `_require_admin` at the endpoint |
| approver ≠ proposer | invariant | enforced at merge time; no self-approval |

### Invariants

1. `merged_at` / `merged_by` NOT NULL ⇔ `status='merged'`.
2. approver ≠ proposer.
3. `base_hash` mismatch at merge → 409 + `status='superseded'`
   (proposal is now stale; user must rebase).
4. merge is a single SQLite transaction across (a) the row update,
   (b) target apply, (c) the audit_bridge insert. apply() raising
   rolls back all three.
5. apply() failure leaves `status='open'`. A reject is an explicit
   reviewer decision, never an apply-side accident.
6. `target_type` unknown to the dispatcher → 400 at propose time
   (fail closed — matches the PolicyEngine `can_use_feature` pattern
   for typos).
7. Every state transition writes one `audit_bridge` row.

### v0.2.x scope

Two target types ship: `wiki_entity` (markdown edits with
`base_hash` conflict detection) and `run_jobs` (gating workspace
job execution). The existing self-evolution gate is folded onto
the same primitive in the same cycle — the `approver_username` /
`approver_role` / `before_metrics` / `after_metrics` fields that
v0.1 introduced for patches become per-CR fields on a CR with
`target_type='self_evolution_patch'`. Behaviour is byte-identical;
the storage and audit shape become uniform.

**Done-when criterion**: every write that today calls
`audit_bridge.write_event(action='approved')` with an approver
field goes through `core/change_request.py`. The bespoke
`/admin/proposals/...` endpoints become thin wrappers over
`/admin/cr/...`.

The full cycle plan lives in
`docs/handovers/v0.2.x-cr-track.md`.

---

## 6. Evolution Boundaries

Self-evolution is **disabled by default**. To enable:

1. Set `JAMES_ENABLE_EVOLUTION=1` (explicit opt-in)
2. Configure `JAMES_EVOLUTION_APPROVER_ROLE` (default: `admin`)
3. Patches flow: `feedback → candidate → 4-gate eval → approval → deploy → rollback-ready`

> **v0.2.x note**: in the Change Request track (§5.6), the
> self-evolution flow is being **wrapped** by the generalised CR
> primitive — the approver field, the eval gate, and the audit-log
> writes preserve byte-for-byte behaviour. CLAUDE.md rule #3
> remains in force; the deploy step still rejects without an
> approver.

A patch reaches `deploy` only after a human with the approver role
explicitly approves it. Auto-approval is a bug, not a feature.

---

## 7. What JAMES is good at (and what it's not)

### Strong fits

- Q&A over private document corpora with role-restricted access
- Auditable reasoning over ontology-rich domains (legal, compliance, internal knowledge)
- Local-only environments with no acceptable cloud egress
- Domains where "why this answer?" matters as much as the answer

### Poor fits

- Real-time transactional systems (booking, POS, ledger)
- Workflow / approval engines (use a BPM; JAMES can be a node inside one)
- Pure summarization at scale (a smaller specialized pipeline is cheaper)
- General-purpose chat (the policy + audit overhead is wasted)

---

## 8. Versioning of this document

Architectural changes (new layer, trust-zone change, removal of
non-goal) require a PR to this file with an `architecture` label.
Module-internal changes do not.

---

## 9. 한국어 요약 (간단)

JAMES는 **로컬에서 실행되며, 추론 근거를 추적하고, 정책에 따라
권한을 검사하며, 사람이 승인한 변경만 적용되는** 지식 추론
시스템입니다. ERP·회계·예약 같은 **시스템 오브 레코드를 대체하지
않으며**, 그 위에 얹는 분석·검색·정책 레이어로 동작합니다.
자세한 영문 본문 참조.
