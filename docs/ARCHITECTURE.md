# JAMES — Architecture & Design Principles

> Engineering reference for contributors. Describes what JAMES is,
> what it deliberately is not, and the trust boundaries that govern
> all design decisions.
>
> Status: living document. Last updated: **v0.4.4 closure + v0.5 entry** (2026-06-12).
>
> v0.4.4 ships LRB v0.2.3 S3 publication-scale + cycle γ 4-bench infrastructure closure; v0.5 entry declared 2026-06-12 with enterprise document ontology design LOCK (see [`docs/design/v0.5-enterprise-document-ontology.md`](design/v0.5-enterprise-document-ontology.md)). Previous milestones: v0.4.2 (T5 Replayable Audit Graph 2026-06-06), v0.4.1 (T6 Causality Chain 2026-05-28), v0.4.0 (Layer 4 Lifecycle Semantics first bundle 2026-05-27).

---

## 1. Mission

JAMES is a **Replayable RAG** system: a local-first knowledge
reasoning system where every claim is sourced, every reasoning
step is audited, and the system's state at any point in time
can be replayed byte-identically.

The Replayable category is distinct from:

- **Agentic RAG** — which optimises for *what an AI can do*
  (tool use, planning, multi-step action). Replayable RAG asks
  the orthogonal question: *what did the system know at time T,
  and why did it answer that way?*
- **Mem0-style memory layers** — which use an LLM judge to
  update beliefs. Replayable RAG uses a deterministic 4-rule
  decision tree (see §5.6 Change Request flow + the v0.4 T2
  Contradiction Arbitration module
  `core/lifecycle/contradiction_arbiter.py`) and **preserves**
  the old fact alongside the new one (T7 Supersede Chain), so
  the historical state is replayable instead of overwritten.

Mission, expanded:

- explicit reasoning paths (sources + graph trace, audit-log
  replay via `scripts/replay_trace.py <trace_id>`)
- temporal-faithful memory (`reconstruct_view_at(t)` returns
  the edge that was active at any past timestamp, even after
  unrelated CASCADE delete events)
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
| 8 | **NL-throughout pipeline** | Query → retrieval → LLM → answer all carry natural language end-to-end. We deliberately do **not** translate the user query into a formal query language (SPARQL / RDF / SQL) intermediate, and the LLM is not asked to emit formal-language responses. Retrieval is dense embedding + BM25 + keyword + name hybrid (`core/retrieval_engine.py` `hybrid_search`); the graph layer is traversed using those retrieval scores, not by formal-query resolution. KG mutations follow the human-approved Change Request flow (§5.6) — there is no path where an LLM-emitted update statement applies to the KG without an explicit reviewer approval. This is an explicit architectural choice in favor of transparency, local operability, and a single auditable artifact (the NL trace) per query. |

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

## 5.7 Cognitive Middleware Layer (v0.3, 2026-05-14)

> Lives in `core/reasoning/` (new) + `core/retrieval/` (existing,
> expanded). Plan + rationale in
> `docs/handovers/v0.3-cognitive-layer-track.md`.

JAMES is evolving from a retrieve-then-answer pipeline into a
deliberative reasoning system. The cognitive middleware layer sits
**between** the existing retrieval/graph engine and the LLM synthesis
step. The graph / ontology / memory / policy core stays exactly as it
is — middleware is **additive**, never a replacement.

```
        ┌────────────────────────────┐
        │   Retrieval (existing)     │
        └─────────────┬──────────────┘
                      │
        ┌─────────────▼──────────────┐
        │   Cognitive Middleware     │
        │   (this section, new)      │
        │                            │
        │   Planner                  │
        │   Query Rewriter           │
        │   Reflection Engine        │
        │   Verification Engine      │
        │   Tool Router              │
        │   Memory Manager           │
        │   Security Reasoner        │
        │   Context Optimizer        │
        └─────────────┬──────────────┘
                      │
        ┌─────────────▼──────────────┐
        │   LLM Synthesis            │
        └─────────────┬──────────────┘
                      │
        ┌─────────────▼──────────────┐
        │   PolicyEngine.can_emit    │  ← Output filter (unchanged)
        └─────────────┬──────────────┘
                      │
                  Response
```

### 5.7.1 Components

| Component | Module (planned) | Responsibility |
|---|---|---|
| Planner | `core/reasoning/planner.py` | Decompose a question into ordered subtasks; choose retrieval depth |
| Query Rewriter | `core/retrieval/query_rewriter.py` | Transform user intent into retrieval-optimized queries |
| Reranker | `core/retrieval/rerank.py` | Cross-encoder reordering of vector-retrieved top-k |
| Reflection Engine | `core/reasoning/reflect.py` | `draft → self_critique → revised` per subtask |
| Verification Engine | `core/reasoning/verify.py` | `generator → critic → fact_checker → security_validator → final_synthesizer`. Wraps the CR-E (§5.6) primitive — every verifier outcome is a Change Request candidate |
| Tool Router | `core/reasoning/tool_router.py` | Select between chat / web search / wiki edit / graph editor / memory write |
| Memory Manager | `core/memory/manager.py` (existing dir, new module) | Choose which memory layer (episodic / semantic / procedural / working / long-term graph) to consult or write |
| Security Reasoner | `core/reasoning/security_reasoner.py` | Reasons _about the policy graph itself_: prompt injection traces, privilege escalation attempts, relationship-based exposure |
| Context Optimizer | `core/reasoning/context.py` | Bound token budget; drop low-relevance evidence; keep audit-required citations |

Each module exports a typed interface. Direct dependency goes one way
only: cognitive middleware imports retrieval / memory / policy, never
the reverse.

### 5.7.2 Trust zone

| Edge | Trust | Hardening |
|---|---|---|
| Cognitive middleware → LLM | medium | every reflection / verification step emits one audit row (`reason_stage` + `applied_rule`) |
| Cognitive middleware → PolicyEngine | enforced | `Planner` and `Tool Router` must ask `can_call_tool` before dispatch; bypass is a regression |
| Verification → CR-E | enforced | a verifier flagging a self-modifying outcome (memory write, ontology edit, evolution patch) must route through `core/change_request.py` — direct apply is a CLAUDE.md rule #3 violation |
| Reflection state | working memory only | not persisted by default; episodic memory captures only the **final** verified answer trace |

#### Reasoning backends + trace schema

LLM 호출은 `core/reasoning/backends/` 의 명명된 어댑터
(`claude_code_cli`, `ollama_local`, …) 를 통해서만 발생한다. 미들웨어는
모델 SDK 를 직접 import 하지 않는다. 모든 백엔드는 동일 row 형태로
`audit_bridge` 에 기록하며, 그 형태는 `core/reasoning/trace_schema.py`
의 frozen dataclass (`stage`, `parent_step_id`, `backend_id`,
`inputs_hash`, `output_summary`, `applied_rule`) 로 고정된다. 새 백엔드는
**registry 만** 확장하고 **schema 는** 확장하지 않는다 — replay 도구는
transport 와 무관하게 한 가지 row 형태만 읽는다.

#### Trace replay invariant

Every reasoning step — planner decisions, reranker scores, reflection
revisions, verification verdicts, tool router dispatches — emits a
single row to the existing `audit_bridge` table. The **full reasoning
trace must be reconstructable from `audit_bridge` rows alone**. No
ephemeral in-memory state may carry decision rationale that audit
cannot replay.

This makes "why did the system answer X?" answerable post-hoc, which is
one of JAMES's strongest differentiators (security-aware forensic
reasoning, 2026-05-14 brief). The invariant is testable: a future
"replay tool" reads `audit_bridge` for one question_id and reproduces
the answer's decision tree. Any column the trace needs but cannot find
is a regression.

#### Graph replay invariant (v0.4.2 T5 extension)

The trace replay invariant above answers "why did the system answer
X?" against the *reasoning round*. The graph state that the round was
answered on top of is governed by a parallel invariant (`core/lifecycle/
replay_graph.py`):

> ∀ t. `reconstruct_graph_at(t)` = replay of every lifecycle event
> row in `audit_log` whose timestamp ≤ t.

Lifecycle mutations (T1 expiration, T2 dispatch, T2.D ingest dispatch,
T6 cascade invalidate, T7 supersede edge_created / chain_extended) each
emit one `audit_log` row with `event_type` in `LIFECYCLE_EVENT_TYPES`
(`core/lifecycle/replay_audit.py`). The read-side primitive
`reconstruct_graph_at(t)` folds the event stream into a deterministic
`GraphSnapshot`. The fold is a **pure function** of the audit_log
events — no wiki file read, no graph engine state access. That is the
"audit-only invariant": an operator can ship the audit_log JSON to a
third party and the third party can reproduce the graph state at any
past `t` with no other artifact.

Cross-chain integration: `view_from_snapshot(snap, head_id, t)` is the
audit-only equivalent of `core/lifecycle/supersede_chain.
reconstruct_view_at` (the v0.4.0 single-chain primitive). Cross-chain
consistency is pinned by
`tests/test_t5_cross_chain_consistency.py` — every edge the view
helper returns is in the snapshot's edges dict.

Together the two invariants (trace replay + graph replay) make the
**ABAC + replay** claim from the corpus retrieval analysis (PR #712 §6)
externally demonstrable: an operator can pin "this answer was given on
this graph state at this time, ran through these reasoning steps" with
nothing but the audit_log.

### 5.7.3 Multi-agent invariant (anti-sprawl)

The middleware is allowed at most **five named agent roles**:

```
Orchestrator
 ├─ Domain Specialist     (retrieval + synthesis for one subtask)
 ├─ Verification Agent    (the verification engine wrapped as an agent)
 ├─ Security Validator    (security_reasoner wrapped as an agent)
 └─ Final Synthesizer     (writes the answer)
```

Adding a sixth agent role requires an architecture-labelled PR.
Reasoning:

- Agent count drives latency, hallucination compounding, debugging
  surface, and token cost super-linearly. The reasoning literature
  shows steep degradation past ~5 named roles.
- A fixed cap forces architectural discipline. "We need another
  agent" is almost always a hint to split a subtask or refactor an
  existing role.
- Domain-specific specialists (legal / food / retail / travel) are
  still gated by **CLAUDE.md rule #1**: they are pack-level concerns
  for the post-v1.0 plugin API, not platform middleware.

#### Roles vs workers

The five-role cap applies to **concurrent reasoning agents** — roles
that participate simultaneously in answering one question. It does
**not** restrict stateless workers invoked sequentially within a role.
For example, the `Final Synthesizer` may internally call a draft
worker, a citation-formatting worker, and a length-budget worker —
those are functions, not agents.

| Concept | Bound by §5.7.3 cap | Identity | Lifecycle |
|---|---|---|---|
| **Agent role** | Yes (≤ 5) | named, persistent across a question | activated by Orchestrator |
| **Worker function** | No | stateless, no identity | called within one role |
| **Tool** | No (capability allowlist instead — §5.5) | typed interface | invoked via Tool Router |

The "writer / critic / outbound / triage / ..." style task-worker
explosion (common in multi-agent operations frameworks) maps to
**workers**, not agents, in JAMES terms. JAMES optimises for reasoning
depth per role; agent count is the wrong knob.

### 5.7.4 Bench gate

Every PR that touches `core/retrieval/`, `core/reasoning/`, or any
relation/graph traversal must include STEP 7 bench numbers per
CLAUDE.md rule #2. Cognitive middleware additions are *expected* to
improve precision / recall metrics; a PR that flatlines them needs
either a non-quality justification (latency, memory) or a re-think.

### 5.7.5 What this section is **not**

- Not a new memory storage. The Memory Manager **dispatches** to
  existing storage (`core/memory/store.py`, the graph, ChromaDB);
  it does not introduce a competing store.
- Not a replacement for `PolicyEngine`. Security Reasoner *uses* the
  PolicyEngine to make inferences; it does not authorize anything
  on its own.
- Not a domain pack. Legal / food / retail reasoning belongs in
  packs (post-v1.0), not the middleware.

### 5.7.6 Memory scope layering

Cognitive middleware reads and writes memory across **three scopes**.
The layering is policy-aware (every scope crossing goes through the
PolicyEngine) and inheritance is **read-only downward**: a session may
read its workspace's graph, but a session write never automatically
escapes its scope.

```
┌────────────────────────────────────────────────────┐
│  system scope     — ontology, policy, evolutions  │
│       inherited read-only by ↓                     │
├────────────────────────────────────────────────────┤
│  workspace scope  — per-deployment knowledge       │
│       inherited read-only by ↓                     │
├────────────────────────────────────────────────────┤
│  session scope    — single conversation state      │
│       writes never escape upward                   │
└────────────────────────────────────────────────────┘
```

| Scope | Examples | Write path |
|---|---|---|
| **system** | ontology, `PolicyEngine` rules, self-evolution log | CR-E only (CLAUDE.md rule #3) |
| **workspace** | wiki entities, vector store, audit log, scheduled jobs | admin via the existing endpoints; gated by `JAMES_WORKSPACE=<id>` env (currently single-tenant — see 5.7.7) |
| **session** | working memory, intermediate reasoning state, draft answers | the cognitive middleware itself; cleared at conversation end unless promoted |

**Promotion** (lower → higher scope) is **never automatic**. Examples:

- A user's "save as long-term memory" action (chat modal from PR #264)
  promotes a session insight to workspace scope — explicit click.
- A self-evolution patch promotes a workspace-derived pattern to system
  scope — explicit human approval (CR-E + approver_username).

**Why this matters now**: JAMES today has shared-graph contamination
risk (one workspace's noise can pollute retrieval for any session).
The scope hierarchy is the structural fix. v0.3 ships the *namespace
contract* (this section). Code lands as part of Phase 3 (memory
expansion) in the cognitive-layer track.

**Department brains (intelligence / legal / cyber / ops)** that the
2026-05-14 brief described are **workspace-scoped plugins** under
this model, not architectural primitives. They activate only after
v1.0 + Plugin API. Until then, JAMES is mother-hardening (CLAUDE.md
rule #1).

### 5.7.8 Backend auto-routing layer (D5, v0.3.x, 2026-05-25)

`core/reasoning/router.py` sits **above** the Provider Contract
(`core/reasoning/backends/`). It does not change the contract
surface; it decides *which* registered backend gets the call,
leaving the backend invocation path untouched.

**Activation**: `JAMES_AUTO_ROUTER` env (`1` / `true` / `yes` /
`on`) — default OFF. Pre-D5 behavior is byte-identical when
flag is unset: every reasoning call falls back to
`JAMES_LLM_MODEL` env or the stage's constructor-supplied
`backend_id`. Mirrors the D1 `JAMES_ADAPTIVE_BUDGET` pattern.

**Inputs**:
- `stage` ∈ `{query_rewriter, planner, reflect, verify, synth}`
  (D1's `ReasoningStage` taxonomy)
- `prompt` (reserved for D5.D cross-lingual + future prompt-surface
  signals)
- `budget_signal` from `TaskBudget.assess(...)` — passed only
  when D1 `JAMES_ADAPTIVE_BUDGET=1` is also on (otherwise None,
  to avoid the fixed 4096 cap unconditionally triggering CAP_HEAVY)

**Backend metadata** (D5.B): each backend declares `capability:
BackendCapability(tier, provider)`. `tier` ∈
`{small, medium, large}` (model-size class). `provider` ∈
`{local, sovereign, cloud}` (deployment surface). Free-form
strings; plugin backends can declare niche tiers without
modifying core. Undeclared backends → `UNKNOWN_CAPABILITY`,
treated as fallback only.

**Decision tree** (D5.C.1 `_route_policy`, first match wins):

1. `stage == "verify"` → prefer `large` tier → `medium` → legacy
   (grounding-critical, D1 sub-finding: ~12.5% unique = high-clustering)
2. `budget_signal == CAP_SUBSTITUTION` (200) → prefer `small` → legacy
   (Robin 2026-05-23: substitution bypasses sampling, small ≡ large
   bit-for-bit cheaper)
3. `budget_signal == CAP_HEAVY` (4096) → prefer `large` → `medium` → legacy
   (Ali "shortening the path": heavy synth is where the cost asymmetry
   favors a stronger model)
4. Otherwise (CAP_LIGHT / None / unknown) → legacy backend

"prefer tier X → fall back to legacy" means a stock install
(`ollama_local` only) routes everything to `ollama_local` — no
broken decisions when no larger backend is registered. Opt-in
routing.

**Authority**: when `JAMES_AUTO_ROUTER=1`, the router is the
authority — stage-level `self._backend_id` preferences are
intentionally overridden. The stage's backend_id is a D5-OFF
concept; D5 ON means "let the router decide". Per-stage override
mechanism is v0.4 follow-up.

**Audit row** (`reason:route` endpoint in `audit_log`): per
successful resolve, one row records `(stage, prompt_hash[:8],
selected_backend, budget_tier_label, reason)`. `reason` values:
`auto` (D1+D5 both on), `fallback` (D5 on, D1 off), `grounding-critical`
(verify stage escalation), `policy` (helper default). Audit
emission is try/except-wrapped — failure never blocks production.

**Cross-lingual entity resolution** (D5.D `core/entity_alias_pack.py`
+ `graph_engine.build_entity_map_snapshot` augmentation): the
snapshot now merges three sources for the (entity_type,
normalized_name) → entity_id map:
1. Wiki entity frontmatter `name`
2. Wiki entity frontmatter `aliases:` list
3. Cross-lingual alias pack (KO↔EN surface forms for ~30
   common entities — Palantir, Tesla, Nvidia, Apple, etc.).
   Augments only when canonical name matches an existing wiki
   entity (silent skip otherwise — no broken state).

The alias pack pairs with the PR #472 `_SYNONYM_MAP` keyword
expansion at two different pipeline stages: query expander
augments at *vector search input*, alias pack augments at
*graph entity resolution*. Embedding-model swap (bge-m3 /
multilingual-e5-large) for global retrieval quality is v0.4
backlog (BL-9), not addressed at D5.

### 5.7.9 LLM model authority chain (`core/model_resolver.py`)

D5 (§5.7.8) routes between **backends** (`ollama_local`,
`claude_code_cli`, future plugin providers). The `model_resolver`
routes between **model tags** *within* a chosen backend (e.g.
`gemma3:4b` vs `gemma4:e4b` vs `qwen2.5:14b` on `ollama_local`).
The two axes compose: D5 picks the backend → resolver picks the
tag — neither replaces the other.

**Resolution chain** (`core/model_resolver.resolve_for_mode`, first
match wins):

1. **Per-call override** (`selected_model` parameter on the chat
   request) — set by the chat-page model picker (`#model-picker`
   in `frontend/index.html`) or the v0.4.0-alpha.2 chip popover
   (PR #498 + PR #499). Highest priority because the operator
   explicitly typed it for this turn.
2. **Configured tag** (`config.GEMMA_MODEL`, from the
   `JAMES_LLM_MODEL` env var). The "what does the operator
   normally want" default. Honoured when installed; falls through
   to the preference list otherwise with an audit warning.
3. **Per-mode preference list** (`DEFAULT_PREFERENCE["chat"]` and
   `DEFAULT_PREFERENCE["coding"]`, overridable via
   `JAMES_MODEL_PREFERENCE_<MODE>=tag1,tag2,…`). First installed
   wins.
4. **Any installed model** (sorted alphabetically — deterministic
   for replay) with a friendly "consider `ollama pull <preferred>`"
   warning.
5. **None** — returns `ResolvedModel(tag="", source="none")` and
   an install-command hint. Callers see the empty tag and surface
   it as the chat-header chip's "not installed" state (v0.4.0-alpha.2
   `/llm/active` endpoint).

**Why per-call wins over env**: a chat user with no admin role still
needs to compare models for one turn without persisting the choice.
The chip popover writes to `selectedModel` (JS) +
`localStorage["james_model_chip"]`, and the next `/query/` request
carries it as `selected_model`. The resolver short-circuits at
step 1, never consults env — the operator-installed default stays
authoritative for everyone else.

**Why env wins over preference**: an operator who sets
`JAMES_LLM_MODEL=gemma3:12b` has explicit intent. The preference
list is a fleet-wide fallback for boxes that haven't pulled the
operator's preferred model yet — never an authority override.

**Per-call override + D5 routing interaction**: when both D5
(`JAMES_AUTO_ROUTER=1`) and a per-call `selected_model` are
active, D5 picks the backend and the resolver picks the tag *on
that backend*. The two decisions are independent. If the per-call
tag isn't installed on the resolved backend, the resolver still
falls through the chain — but the audit row carries both signals
(`reason:route` from D5 + `model_resolver.source` from the
resolver) so an operator can reconstruct the full decision.

**Surface visibility**: the chat-header chip (`/llm/active`
endpoint, PR #498) reads `resolve_chat().tag` + `source` and tints
its border by `source` value — `requested` (configured won) stays
neutral, `preference` / `any` / `none` get progressively warmer
edges. Operators see fleet-wide which boxes are running the
configured model vs which are falling back.

**Cache** (`installed_models()` set with 60s TTL): the resolver
hits Ollama's `/api/tags` once per minute rather than per chat
turn. `invalidate_cache()` is called from `/admin/llm/install` +
`/admin/llm/delete` handlers so a fresh install is visible
immediately.

### 5.7.7 Deployment isolation (deferred to v0.4)

JAMES's isolation today is **policy-based**: RBAC + ABAC + PolicyEngine
+ Memory Trust + relation-sources cascade. This stack already prevents
the threats that container isolation typically addresses (cross-tenant
data leakage, privilege escalation, retrieval scope bleed).

**Container-level isolation** (one Docker container per agent, or per
workspace) is a v0.4 *operator option*, not a v0.3 requirement:

- v0.3 default: single process, single workspace, all isolation
  enforced at the PolicyEngine layer.
- v0.4 option: `JAMES_WORKSPACE=<id>` env var (already seeded) maps
  one process to one tenant. Multiple processes per host = multiple
  workspaces. Docker is the operator's packaging choice; JAMES itself
  is unaware of containers.
- v0.4 hardening (separate PR, not this track): cross-workspace API
  for federated queries with explicit role + audit gates.

**This is a deliberate non-goal at v0.3** — adding container plumbing
before the cognitive middleware is built would invert priorities. The
brief's "12 containers per VPS" pattern is an *operations topology*, not
an architecture; it sits on top of JAMES, not inside it.

### 5.7.10 Quality Verification Track (QVT, v0.4, 2026-05-28)

The §5.7.4 bench gate measures **cost** (latency, token count, graph
fan-out). The QVT subsystem measures **marginal quality contribution**
of each routing / caching / rewriting layer — the question "should
this layer be ON?" was structurally unanswerable through v0.3 because
`grounded` and `RAGAS` were saturated (1.0 ceiling) and
`answer_relevancy` sat in the noise band. v0.4 adds three orthogonal
non-saturating axes:

| axis | source | what it catches |
|---|---|---|
| **Path Coverage** | `bench.py`'s `path_metrics` block (v4 added Idea-1 path-GT to 5 fixture queries; v5 keeps all 5) | retrieval / extraction regressions on relation queries (q15 zero-recall surfaced this) |
| **Graded Answer Accuracy** | per-query 3 atomic `gold_signals` (term + aliases) matched as case-insensitive substring against the answer | over-shortening or topic drift even when path is correct |
| **Calibrated Abstention F1** | `abstention_truth` (`present` / `absent`) compared with whether the answer triggered an abstention phrase | hallucination on no-evidence queries; over-cautious refusal on present-evidence queries |

The oracle (`eval/qvt/oracle.py`) is deterministic — no LLM judge,
no embedding lookups, just substring + path-set matching — so it is
audit-replay safe by construction (consistent with the Replayable
RAG positioning in §1). The canonical baseline (`eval/qvt/baseline_<sha>.json`,
captured via `scripts/qvt_capture_baseline.py` with N=3 paired
reruns) freezes the v0.4.0 production environment numbers. Every
subsequent PR that touches `core/retrieval/` / `core/graph/` /
`core/reasoning/` pastes a 3-axis Quality Delta Card paired against
this baseline (CLAUDE.md rule 2, extended by α-4).

**Trust zone**: same as §5.7.2 (Cognitive Middleware Layer) — the
oracle reads bench JSON + fixture, produces JSON. It does NOT
authorize anything, does NOT mutate state, does NOT have a network
surface. Its only invariant is that the same `(bench_json, fixture)`
input produces byte-identical output across runs.

**What this subsystem is not**:
- Not a judge / not an evaluator with semantic understanding — the
  matcher is deterministic substring. Paraphrased / negated /
  quantitative-approximate matches are scored low. LLM-judge
  augmentation is a v0.5+ candidate after the deterministic floor
  stabilizes.
- Not a routing decision-maker. The v0.4-end ablation matrix
  (`eval/qvt/baseline_<sha>.json` runs across all 6 routing combos ×
  3 model tiers = 18 cells) produces evidence; the routing policy
  decision that consumes that evidence is a separate PR (α-5).
- Not a domain-pack metric. Path Coverage / Graded Answer /
  Abstention F1 are platform-wide; domain packs at v1.0+ will layer
  their own axes (legal: citation-validity, food: allergen-safety,
  retail: SKU-resolution) without replacing the platform floor.

**Subsystem files**:
- `eval/qvt/oracle.py` — 3-axis scorers + `score_three_axis()` entry
- `eval/qvt/baseline_<sha>.json` — canonical reference (one per
  intentional baseline-environment change; never silently overwrite)
- `scripts/qvt_capture_baseline.py` — operator wrapper (N=3 paired
  reruns + noise band)
- `eval/regression/step7_queries.json` v5 — fixture with
  `gold_signals` + `abstention_truth` (PR #551)
- `docs/design/v0.4-qvt-alpha-non-saturating-oracle.md` — full design

### 5.7.11 User-Input Bidi Normalization Gate (Track 2c follow-up, v0.4, 2026-06-02)

Strips a small explicit set of Unicode bidirectional + zero-width
formatting characters from user input at the `/query/` HTTP edge
before the question reaches retrieval / graph / reasoning / LLM
prompt construction.

Triggered by the Track 2c X3 finding (Ali Afana / Provia 2026-06-01) —
empirically confirmed at JAMES via the 2026-06-02 audit
(`reports/research-runs/bidi-normalization-audit-20260602.md`):
JAMES had **zero** bidi normalization in any layer. U+202E
(RIGHT-TO-LEFT OVERRIDE) and other directional formatting controls
flowed through unchanged. Provia observed in `bidi_03` that the
concealed instruction reached the model's reasoning despite the
visible greeting being benign; the same payload would land
identically at JAMES.

Implementation:

1. **`core/input_normalization.py`** — new module (~5 KB) exposing
   `normalize_user_input(s) -> (normalized, audit_dict)`. Strips 11
   bidi formatting code points (LRM/RLM/LRE/RLE/PDF/LRO/RLO/LRI/RLI/
   FSI/PDI) + 4 invisible / zero-width code points (ZWSP/ZWNJ/ZWJ/BOM),
   then applies NFC canonicalisation. Returns audit dict with per-
   class counts + `nfc_applied` flag. Pure function; no I/O.
2. **`routes/query.py:132`** wire — after `.strip()` (whitespace),
   call `normalize_user_input` and feed the result to `rag_engine`.
   When `audit_dict["chars_dropped"] > 0`, emit a `log_stage(
   "input_normalize", role=role, **audit_dict)` row so the forensic
   trail exists.

Trust zone: this is a defensive input gate. The strip is logged per
request via `core.observability.log_stage` so an audit trail exists
for any future incident.

**Scope discipline** (cross-reference: audit doc §7.2):

- This is a **runtime defence against user input**. It does NOT
  modify the test fixture path.
  `eval/adversarial/ar_ecommerce-*.yaml` preserve U+202E byte-exact
  because those characters are the payload the test cases exercise.
- `scripts/adversarial_sweep.py::_post_query` carries a parallel
  warning comment: do NOT normalize input in the runner. The fixture
  → server boundary is exactly what's under test.
- Confusing the runtime gate with test fixture normalization would
  silently break the `bidi_01-04` cases.

Module size: `core/input_normalization.py` ≈ 5 KB (well under the
20 KB gate). Does **not** extend `core/graph_engine.py` (currently
at 20.4 KB, above the gate — α-7's separate concern).

Pointers:

- Audit doc + recommended PR shape: `reports/research-runs/bidi-normalization-audit-20260602.md`
- Track 2c integration design memo: `docs/design/v0.4-track-2c-arabic-adversarial-integration.md`
- Ali `bidi_01-04` test cases: `eval/adversarial/ar_ecommerce-v1.1-pending.yaml`
- Unit tests (29 cases): `tests/test_input_normalization.py`

### 5.7.12 Cloud Egress Trust Zone (Direction α, v0.4+, design-stage)

> **Status: design-stage, gated.** No cloud egress code has landed. This
> section defines the trust contract any cloud-tier implementation must
> satisfy **before** it ships (CLAUDE.md rule #4). Full design:
> `docs/design/v0.4-direction-alpha-hybrid-cloud-tier.md`.

JAMES is local-first by default (§7). Direction α adds an **opt-in** tier
that routes *only the reasoning step* of a query to a stronger external
model when the local model is judged insufficient — intent
classification, retrieval, and evidence selection always stay local (they
are local-solved; see the α-cycle S4 path-invariance finding). The
external model never sees un-abstracted sensitive content.

**Trust zone**

| Edge | Trust | Hardening |
|---|---|---|
| Router → cloud egress decision | enforced (PolicyEngine) | the per-query "may this egress?" decision routes through `PolicyEngine`; bypass is a regression |
| Selected evidence → external LLM | untrusted boundary | sensitive entities are replaced with typed deterministic placeholders by the abstraction layer **before** egress; the real→placeholder map is local-only and never leaves the machine |
| External LLM → de-abstraction | medium | the reply is unmasked via the local map; a placeholder absent from the map (hallucinated entity) is **flagged, never silently restored** |
| Egress transform → audit | enforced | every mask / egress / unmask emits a row to `audit_bridge` (per §5.7.2 trace schema); "what left the machine" must be replayable |

**Egress masking policy** — per entity, driven by the `sensitivity` tag ×
ontology type × the query's semantic dependence on that entity:

- **mask** — sensitive + *closed-world* (answer derivable from the
  provided documents' structure; identity is just a label) → typed
  placeholder. Relationship structure survives consistent masking, so
  closed-world reasoning is correct over placeholders.
- **pass-through** — not sensitive → real value.
- **keep-local** — sensitive + *open-world* (reasoning needs the entity's
  real-world meaning, e.g. a drug-interaction question) → never egress;
  answer locally or require explicit operator/user consent via
  `PolicyEngine`.

**Invariants**

- Default is **local**. Cloud is opt-in and gated per query; the
  escalate-readiness threshold is an **operator dial**, not a constant.
- **No un-abstracted egress** of `sensitivity`-tagged content, ever.
- The egress decision MUST pass through `PolicyEngine` (no-bypass).
- A cloud-introduced placeholder absent from the local map is flagged,
  never silently de-abstracted.

**Backend**: the cloud tier extends the §5.7.8 D5 backend router + §5.7.9
model authority chain with a cloud-class backend, via a named adapter in
`core/reasoning/backends/` (`claude_code_cli` for research / Max-plan, an
API provider for production) per the §5.7.2 registry-only rule. The
abstraction layer sits between the router and the backend on the cloud
route; on the local route it is a no-op.

Validation to date (design-stage, no production code):
`scripts/research/abstraction_layer_poc.py` (deterministic mask/unmask,
5/5) and `scripts/research/abstraction_e2e_claude.py` (full
mask → real-Claude → unmask loop, no leak).

### 5.7.13 Abstraction Module (Direction α, v0.4+, design-stage)

> **Status: design-stage, gated.** Module-level trust contract for the
> abstraction code that will land at `core/abstraction/`. §5.7.12 defines
> the cloud-egress trust zone (the *boundary*); this section pins down
> what the *module enforcing* that boundary must guarantee, before any
> production code lands (CLAUDE.md rule #4, design memo §8.5b).

The abstraction module is the single place where sensitive entity strings
are deterministically replaced with typed placeholders on the way *out*
to a cloud reasoner, and where the reply is reversed on the way *in*.
Everything in §5.7.12 reduces to "the abstraction module did its job and
the audit log proves it." Promoting it from the design-stage PoC
(`scripts/research/abstraction_*`) into the production path therefore
requires its own architecture contract — not just code review.

**Module location & API surface** — `core/abstraction/`, public API
exposed via `core/abstraction/__init__.py`. Internal modules (mask
implementation, decision policy, audit hook) are private (`_`-prefixed)
and not part of the contract. The public surface is minimal so callers
have a small attack surface to reason about:

| Symbol | Purpose | Notes |
|---|---|---|
| `Decision` (enum) | per-entity outcome: `MASK` / `PASS` / `KEEP_LOCAL` | matches §5.7.12 three-way policy |
| `default_decider(...)` | builds the per-entity decision function (open-world TYPE/NAME sets in, callable out) | swap with a query-conditioned classifier in S7 — module is policy-agnostic |
| `AbstractionMap` | the local-only real↔placeholder mapping for one egress | constructed per-query, never persisted across queries |
| `build_map(entities, decider)` | builds an `AbstractionMap` from typed graph entities | deterministic in declaration order |
| `mask_text(text, amap)` | replaces real names with placeholders before egress | substring-safe (longest-first), Korean-particle-safe |
| `unmask_text(text, amap) → (text, flagged)` | reverses on the reply; returns hallucinated placeholders separately | hallucinated tokens are **never silently restored** |
| `emit_egress_event(stage, prompt, backend_id, amap, *, flagged, reason)` | writes one `reason:egress` row to `audit_log` via `audit_bridge` | no real names leak into the row (only placeholder ids + type histogram + flagged list); never raises |
| `run_cloud_egress(*, backend, prompt, entities, decider, stage, ...)` | orchestrator: `build_map → mask_text → backend.complete → unmask_text → emit_egress_event` in one call | returns `(CompletionResult, flagged)`. Refuses egress if a `keep_local` name appears in the prompt (runner-side defense-in-depth) |

**Module invariants (the trust contract)**

1. **Determinism** — same `(entities, decider)` input → byte-identical
   `AbstractionMap.forward`. Required so audit replay (T7 + §5.7.2 trace
   schema) reproduces exactly what was egressed at time T.
2. **Substring safety** — masking `"김철"` and `"김철수"` in the same
   payload never corrupts either replacement (PoC §5 case). Enforced by
   longest-name-first iteration.
3. **Particle/boundary safety** — placeholder regex uses non-alnum
   lookbehind + not-a-digit lookahead so `PERSON_3의` unmasks correctly
   and `PERSON_12` is never split into `PERSON_1` + `2` (PoC `_PLACEHOLDER_RE`).
4. **Hallucination flagging** — any placeholder token in the cloud's
   reply that is **shaped like ours** (known ontology TYPE + integer)
   but **absent from the local map** is returned in `flagged` and left
   verbatim in the restored string. Silent de-abstraction of an
   unmapped placeholder is a **bug**, not a feature — it would let the
   cloud inject content under a real name.
5. **Local-only map** — `AbstractionMap.reverse` lives in process
   memory for one query and is never persisted, serialized, or sent
   over any wire. The audit row records *what got masked* (entity ids
   + placeholder ids), not the map itself; replay reconstructs the
   map from the same entity set.
6. **No-egress purity** — `mask_text` and `unmask_text` are pure
   functions of `(text, amap)`. They make no network calls and have no
   side effects. The cloud egress is the *caller's* responsibility
   (cloud backend in §5.7.8), not the abstraction module's. This keeps
   the security-critical code easy to audit in isolation.

**Caller obligations** (rules the router/pipeline must follow when
invoking the module)

- The egress decision (whether *to* call cloud at all) MUST pass through
  `PolicyEngine` *before* `build_map` runs. Abstraction is the
  enforcement of the egress, not the authorization for it. Bypassing
  PolicyEngine to call `mask_text` directly is a §5.7.12 invariant
  violation.
- Every `build_map` → `mask_text` → (cloud call) → `unmask_text`
  sequence emits one `reason:egress` row to `audit_bridge` (per §5.7.2
  trace schema): masked-entity ids, placeholder ids, the cloud backend
  id, and the `flagged` list on return. Failure to audit is treated
  the same as a failure to mask — the call MUST NOT proceed.
- `flagged` entries on return are surfaced to the user-facing reply
  (visible "the model referenced an entity we couldn't verify"
  treatment) and are **never** stripped from the response without
  operator review.

**Non-goals (what this module deliberately does NOT do)**

- **Does not classify sensitivity.** That is a property of the entity
  / chunk metadata (`sensitive` flag, chunk `sensitivity` tag), set by
  the ingestion / wiki pipeline. The decider function reads those
  flags; it does not infer them.
- **Does not decide closed-world vs open-world.** The decider takes
  explicit `open_world_types` / `open_world_names` sets (PoC) or, in
  the production path, a query-conditioned classifier passed in by the
  router. The module is policy-agnostic.
- **Does not perform the cloud call.** That is a §5.7.8 backend
  (`core/reasoning/backends/claude_code_cli` etc.). Separation keeps
  the security-critical surface (mask/unmask) testable without a
  cloud dependency.
- **Does not persist the map.** One `AbstractionMap` per query,
  garbage-collected after `unmask_text`. Cross-query consistency is
  not a goal (and would be a privacy liability — same `PERSON_1`
  across queries is a re-identification risk).

**Module-size discipline** (CLAUDE.md rule #5) — the production module
splits into `_mask.py` (mask/unmask + `AbstractionMap`), `_policy.py`
(`Decision` + `default_decider`), `_audit.py` (the `reason:egress`
emit), each well under the 20 KB ceiling. The public façade
(`__init__.py`) re-exports the contracted surface and stays minimal.

**Validation to date (design-stage)** — same as §5.7.12:
`scripts/research/abstraction_layer_poc.py` 5/5 (closed-world reasoning
survives, hallucinated placeholder flagged, open-world keep-local,
determinism, substring safety) and `abstraction_e2e_claude.py` full
mask → real-Claude → unmask loop with no leak. Production promotion is
the next PR (test parity required against the PoC self-tests).

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
- Local-only environments with no acceptable cloud egress (the default;
  an opt-in, abstraction-gated cloud reasoning tier exists per §5.7.12
  for deployments that permit controlled egress)
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
