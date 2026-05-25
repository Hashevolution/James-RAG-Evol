# JAMES — Security Assurance Case

> **Purpose.** This document is the project's **security assurance case**:
> a structured, evidence-backed argument for *why* JAMES's stated security
> requirements are met by its implementation. It exists to satisfy
> OpenSSF Best Practices criterion `assurance_case` (silver tier) and to
> give external reviewers — pentesters, auditors, plugin authors
> evaluating the trust contract — a single entry point.
>
> **What this document is not.**
> - It is **not** a substitute for `SECURITY.md` (vulnerability reporting,
>   user-facing security model). Read that first if you are a user.
> - It is **not** a substitute for `docs/ARCHITECTURE.md §5` (the
>   normative description of trust zones and PolicyEngine). The
>   assurance case *references* the architecture; the architecture
>   defines it.
> - It is **not** a guarantee. JAMES is pre-v1.0 mother-platform code
>   (see `CLAUDE.md`). Section 6 of this document enumerates the gaps
>   honestly.
>
> Last reviewed: 2026-05-20 (v0.3.0 entry).
> Next scheduled review: at every v0.x → v0.(x+1) gate (per `ROADMAP.md`).

---

## 0. How to read this document

Each requirement in §1 has a matching argument in §4 with the *same
identifier* (R1, R2, …). Arguments cite **file paths and line ranges**
in the form `path/to/file.py:L<start>–L<end>`. CI gates are cited as
workflow filenames under `.github/workflows/`. Where a claim depends on
runtime behavior, the corresponding test is cited under `tests/`.

If a citation breaks (file moved or renamed), that is a documentation
bug — open an issue with label `assurance-case`. The argument itself is
not invalidated by a stale line number, but the evidence trail is.

---

## 1. Security requirements

JAMES makes the following normative security claims. Each claim is
labeled R<n>. Arguments for each appear in §4.

| ID | Requirement |
|----|-------------|
| **R1** | Every retrieval, graph traversal, tool invocation, and feature endpoint is gated by the **PolicyEngine**. There is no documented bypass path. |
| **R2** | Self-evolution (any code change applied to the running system by JAMES itself) requires a recorded human approver. The system fails closed if the opt-in env var is unset, the approver's role does not match, or the approver username field is empty. |
| **R3** | Tool execution touching the host filesystem or shell passes through the **sandbox** (`tools/code/sandbox.py`). The sandbox enforces a command allowlist, a path allowlist, role-based path scope, and a hard subprocess timeout. The admin role does **not** exempt the command allowlist. |
| **R4** | The server **refuses to start** without `JAMES_API_KEY` and a `JAMES_JWT_SECRET` of at least 32 characters. There is no insecure-default mode. |
| **R5** | Security-relevant events (attacks blocked, sandbox actions, patch approvals, role changes) are written to an append-only audit trail. Patch-approval events specifically record the approver's username, role, and method *before* the patch is applied, so the audit record survives an apply failure. |
| **R6** | Content originating from low-trust sources (web search, OCR/ASR/vision extraction, user-tagged memory, raw user input) is passed through `extract_data_only()` before it can join an LLM prompt, neutralizing known prompt-injection patterns. |
| **R7** | Every pull request merged to `main` is gated by automated CI: lint (ruff, F-class), SAST (bandit, high-severity), tests (pytest), and the contributor license check (CLA Assistant). |
| **R8** | Output returned to external (unauthenticated or low-role) users is filtered to redact PII and role-restricted keywords (`mask_sensitive()` / `filter_answer_by_role()`). |

These requirements are derived from the threat model in §2 and from the
public security model documented in `SECURITY.md`. They are intentionally
narrow: JAMES is a research-grade local-first system, not a hardened
multi-tenant SaaS. The honest gaps are in §6.

---

## 2. Threat model

A more user-facing version of this section lives in `SECURITY.md`
§"Threat Model". The version here is structured for the assurance case.

### 2.1 Assets

| Asset | Why it matters |
|-------|----------------|
| The knowledge graph + vector store (`memory/`, ChromaDB) | The product. Corrupting it (poisoned ingestion, untracked deletes) destroys answer quality. |
| User credentials (bcrypt password hashes, JWT secret, API keys) | Account takeover would let an attacker bypass every downstream gate. |
| The patch pipeline + audit log | If the audit trail is forgeable, the human-approval requirement on self-evolution is hollow. |
| Host filesystem outside `./workspace` | Sandbox escape would let a tool call exfiltrate or destroy data on the host. |
| LLM context window (per request) | Indirect prompt injection (poisoned doc, poisoned web result) can steer answers; the request-scoped context is the injection surface. |

### 2.2 Threat actors

| Actor | Capabilities assumed | Out of scope? |
|-------|----------------------|---------------|
| **Unauthenticated user** | Can hit public endpoints (`/login`, `/signup`, public health checks). Subject to rate limiting. | No — must be defended. |
| **Authenticated low-role user** (`external`, `employee`) | Has a valid JWT or API key. Can query, but not approve patches, not exec shell, not write to admin-only entities. | No — must be defended. |
| **Authenticated admin** | Can approve patches, can call admin endpoints, can exceed the default path allowlist (logged). | Partially in scope: admin is trusted to *authorize* but not to *override the command allowlist*. |
| **Malicious plugin author** (post-v0.3) | Ships code that runs inside the JAMES process. | Currently mitigated by **not freezing the plugin API until v0.3**. Plugins must opt-in to the same PolicyEngine contract. |
| **Compromised supply chain** (PyPI, GitHub) | Could inject code via dependency update. | Partially defended: `requirements_pinned.txt` + bandit + dependency-update PRs reviewed manually. Not fully defended (no SBOM signing yet). |
| **Operator of the host machine** | Has root on the box JAMES runs on. | **Out of scope.** Local-first systems trust their host. |

### 2.3 Threats (numbered, mapped to requirements)

| T# | Threat | Mitigated by |
|----|--------|--------------|
| T1 | Unauthorized data exfiltration via retrieval | R1 (PolicyEngine.can_retrieve), R8 (output filter) |
| T2 | Unauthorized data exfiltration via graph walk | R1 (PolicyEngine.can_walk) |
| T3 | Privilege escalation via self-evolution | R2 (approver_username mandatory + role check + opt-in env) |
| T4 | Host filesystem damage via tool call | R3 (sandbox command + path allowlist) |
| T5 | Server boot with no auth | R4 (fail-fast at config import) |
| T6 | Tampering with the audit trail to hide an approval | R5 (record *before* apply; JSONL append-only on disk) |
| T7 | Direct prompt injection (user types "ignore previous") | R6 (`detect_attack` + `extract_data_only`) |
| T8 | Indirect prompt injection (poisoned web/OCR content) | R6 (`PolicyEngine.quarantine`) |
| T9 | Regression of a defense by a future PR | R7 (CI gates: ruff F-class, bandit HIGH, pytest, CLA) |
| T10 | PII leakage to low-role users | R8 (`mask_sensitive`, `filter_answer_by_role`) |

The matrix is *not* claimed to be exhaustive — §6 enumerates known
gaps (T11+).

---

## 3. Trust boundaries

The normative trust-zone table is in **`docs/ARCHITECTURE.md` §5** (lines
101–114). It is **not duplicated here** — duplication is a maintenance
hazard. The assurance case treats that table as authoritative.

Summary for orientation:

- Seven zones: user input, internal docs, system-tagged memory,
  user-tagged memory, multimodal extraction, web search, tool output.
- Three trust levels: low / medium / high.
- Anything labeled **low** must pass `extract_data_only()` before
  joining LLM context (`docs/ARCHITECTURE.md:113–114`).

The boundary between **mother platform (`core/`) and plugins** is also
a trust boundary in spirit, but the plugin API is not yet frozen
(`docs/PLATFORM_READINESS.md` gates v0.2 → v0.3 → v0.4 → v1.0). Until
the API freezes, plugins are *not* a supported trust boundary — they
run with the same privileges as the host process. **This is the single
most important "argument" the assurance case is currently making about
the future**: §6 marks it as a tracked gap.

---

## 4. Arguments

Each subsection argues that the named requirement is met. Citations are
to file paths and line ranges in the repository at the time of writing.

### R1 — Every gated action passes PolicyEngine

**Evidence.**
- `PolicyEngine` is defined in `core/policy_engine.py:L1–L456`. Public
  decision API: `can_retrieve()` (L138), `can_walk()` (L153),
  `can_call_tool()` (L168), `can_emit()` (L305), `can_use_feature()`
  (L320).
- The action minimum-role table at `core/policy_engine.py:L102–L106`
  pins shell exec, fs.write, and fs.read to specific minimum roles.
  This is a single source of truth; tools cannot loosen it locally.
- Sandbox invokes the PolicyEngine before any filesystem decision:
  `tools/code/sandbox.py:L165–L218` (`policy_validate_path()`) issues
  and verifies a short-lived capability *before* the existing
  allowlist check. This is intentional defense-in-depth: the sandbox
  is the second gate, not the first.
- `core/security_layer.py:L256, L275, L283, L395` delegates ABAC
  decisions to PolicyEngine rather than re-implementing them.
- The server's patch-approval and audit endpoints (`server_llmwiki.py`
  around L3630, L3715–L3731) lazy-import PolicyEngine — the trust
  decision is computed at request time, not cached.

**Argument.** PolicyEngine has six narrowly-typed public methods and
no "permit all" backdoor. Every retrieval / graph / tool / feature
callsite documented above goes through one of them. The capability
mechanism (`issue_capability` at L212, `verify_capability` at L256)
short-circuits any future code that needs scoped privilege without
adding a new method.

**Negative evidence.** Any new endpoint that does *not* call into
PolicyEngine would be a regression. The architecture-label PR
requirement (`CLAUDE.md` rule 4) is the social check; the bench/test
suite is the technical check (regression tests for ABAC live in
`tests/test_security_layer.py`, `tests/test_policy_quarantine.py`).

### R2 — Self-evolution requires a human approver

**Evidence.**
- The single approval endpoint is
  `POST /admin/patch/approve` in `server_llmwiki.py:L3621–L3734`.
- Opt-in env var check: `L3642–L3646` — if `JAMES_ENABLE_EVOLUTION` is
  not `"1"`, return 403.
- Role check: `L3648–L3651` — caller's role must equal
  `JAMES_EVOLUTION_APPROVER_ROLE` (default `"admin"`).
- `approver_username` mandatory: `L3655–L3661` — empty field returns
  400 with message `"approver_username required (#48 audit)"`.
- Approval recorded **before** apply: `L3680–L3687` calls
  `record_approval(patch_id, approver_username, approver_role,
  approval_method)`. Apply happens at `L3693`. If apply fails, the
  approval record stays — the audit trail is the source of truth, not
  the patch state.
- The `JAMES_AUTO_APPROVE` shortcut in `config.py:L207–L226` is
  guarded by *both* `JAMES_DEV_MODE=1` *and* an explicit flag, and
  the server refuses to start if the combination is inconsistent.
- Post-apply bench gate: `L3697, L3714` — auto-rollback on regression.

**Argument.** The four conditions (opt-in env, role, username,
bench-pass) are checked in sequence with no shared early-exit. The
single sentence `record_approval(...)` is called *before* the
single sentence `patch_apply(...)`. There is no other code path that
reaches `patch_apply()` with `validated=True` outside this endpoint.

**Negative evidence.** A grep for `patch_apply(` (or whatever the
function is named at audit time) finds exactly one call inside
`server_llmwiki.py`. Adding a second call would land in a PR and
would require an architecture review per `CLAUDE.md` rule 4.

### R3 — Sandbox confines tool execution

**Evidence.**
- `tools/code/sandbox.py:L223–L256` — `validate_action(command, path,
  role)`. Logs to `AUDIT_LOG_PATH` and `SYSTEM_LOG_PATH`.
- Command allowlist + 5 regex danger patterns at
  `tools/code/sandbox.py:L149–L158`. **Admin role is not exempt** —
  this is verified by the same code reading `validate_command()`
  before any role check.
- Path allowlist: `L115–L121` (`BLOCKED_PATH_PATTERNS`) — admin
  bypasses `ALLOWED_PATHS` but **cannot** bypass blocked patterns
  (system paths, `core/`, etc.). The admin override is *logged* at
  `L250–L254` to the audit log so the bypass is auditable.
- Public execution entry: `safe_execute()` at `L261–L293`. Validates,
  runs `subprocess.run(...)` with `shell=True`, applies a hard
  timeout (default 10s, line 41).
- The `shell=True` call at `tools/code/sandbox.py:L276` is annotated
  `# nosec B602` with the rationale that `validate_action()` *is* the
  security gate. This is enforced in CI: bandit will flag any new
  unguarded `shell=True` (see R7).

**Argument.** `safe_execute()` is the only function that runs
subprocesses on behalf of tool calls. Any tool that wants shell
access has to go through it (or be reviewed against §6 gap T12). The
allowlist is centralized in one file, easy to audit, and protected by
both bandit (`shell=True` flag) and the architecture-label review
rule.

### R4 — No insecure-default boot

**Evidence.**
- `config.py:L181–L191` — `API_KEY` read from env; `RuntimeError` if
  empty.
- `core/auth.py:L44–L54` — `JWT_SECRET` read from env; `RuntimeError`
  if missing or shorter than 32 characters.
- `.env.example:L10–L22` — the canonical secret list that operators
  copy. Variables are listed with no defaults to copy-paste.
- CI's test workflow (`/.github/workflows/test.yml`) supplies
  test-only sentinel values (`ci-test-key-not-secret-...`,
  `ci-test-secret-32-chars-padding-padding`) so that the server can
  *import* during pytest collection; these values are documented as
  non-secret and never check against any real key.

**Argument.** Both required env vars raise at *import time*, not at
first-request time. There is no `if os.environ.get(...) else
"insecure-default"` branch. The fail-fast is reachable on `python -c
"import config"` and on `python -c "import core.auth"`. Operators
running with `python server_llmwiki.py` cannot start the server
without these set.

### R5 — Append-only audit trail with approver recorded

**Evidence.**
- Main SQLite schema: `server_llmwiki.py:L72–L84` defines `audit_log`
  table (id, timestamp, user_role, endpoint, query, answer,
  graph_paths, blocked, security_event, elapsed_sec, ip_address).
- Patch-approval audit: `tools/patch/approval.py::record_approval()`
  writes to `james_patch_log.jsonl`. Patch JSON is append-only by
  convention; the JSONL is rotated by `core/audit_bridge.py` (mirror)
  not edited in place.
- Mirroring: `core/security_layer.py:L138–L167` —
  `log_attack()` and `log_system_event()` both call into
  `core.audit_bridge` so a single security event lands in both the
  SQLite log and the JSONL.
- Sandbox events: `tools/code/sandbox.py:L62–L95`
  (`log_security_event`) mirrors to `AUDIT_LOG_PATH`,
  `SYSTEM_LOG_PATH`, and the audit DB.
- Query endpoints: `/admin/audit` (server_llmwiki.py around L3636)
  and `/admin/patch/audit` (L3737) allow filtering by approver and
  outcome.

**Argument.** Every security-relevant event has at least two
storage destinations (SQLite + JSONL). The schemas are stable across
v0.x — schema changes go through a migration in `core/db_init.py`
(not relevant here). Approver username, role, and method are
recorded *before* the patch is applied (see R2), so the trail
survives apply failure.

**Honesty note.** The main `audit_log` SQLite schema does **not**
include an `approver_username` column. Approver identity is stored
in `james_patch_log.jsonl` and in the patch JSON itself, not in the
main table. This is an intentional separation (patch approvals are
not user-query events), but it does mean a future auditor must read
both stores to reconstruct an evolution event. This is tracked as
gap T13 in §6.

### R6 — Low-trust content is neutralized before LLM join

**Evidence.**
- Input-time detection: `core/security_layer.py:L46–L60` defines 17
  compiled regexes + 31+ string patterns covering English and
  Korean prompt-injection phrasings. `detect_attack(query)` at
  `L178–L185` runs them.
- Instruction-isolation patterns: `L126–L134` — 8 regex patterns for
  indirect control-flow injection ("you are now …", "must always
  answer …", "show all data").
- Neutralizer: `extract_data_only(raw_input)` at `L189–L224` — regex
  substitution with explicit `[INSTRUCTION_REMOVED]` / `[BLOCKED]`
  sentinels. The neutralized output is what reaches the LLM.
- `PolicyEngine.quarantine(content)` at
  `core/policy_engine.py:L409–L449` — routes low-trust sources
  through `extract_data_only()` before they can be concatenated
  into a prompt.
- Ingestion-time choke point:
  `PolicyEngine.sanitize_for_ingestion(content, source)` at
  `core/policy_engine.py:L365–L407` — runs the same neutralizer at
  upload, so poisoned embeddings can't accumulate in the vector
  store across requests.
- Regression test:
  `tests/test_policy_quarantine.py` exercises the call chain on
  web-search-shaped inputs.

**Argument.** Every documented entry path for low-trust content
(direct user input, ingestion, web search result, multimodal
extraction) reaches the LLM only after `extract_data_only()` has
been applied. The neutralizer is regex-based and therefore
deterministic; if a pattern is missed, the *bug* is in the pattern
list, not in the gating.

**Honesty note.** Signal-level injection (Unicode confusables,
homoglyphs, indirect semantic substitution via paraphrase) is not
defended — the system relies on the LLM's own robustness for
those. This is tracked as gap T11 in §6.

### R7 — CI gates every merge

**Evidence.**
- `.github/workflows/lint.yml` — ruff F-class enforced on every PR
  and push to main.
- `.github/workflows/security.yml` — bandit high-severity enforced on
  every PR and push. Added in PR #356, 2026-05-20.
- `.github/workflows/test.yml` — pytest with a documented
  iteration-plan list of currently-skipped tests (external-service
  dependencies; tracked for un-ignoring).
- `.github/workflows/cla.yml` — CLA Assistant check; PRs from
  non-signed contributors are blocked.

**Argument.** All four workflows trigger on `pull_request` to `main`.
Branch protection on `main` (configured outside the repo, in GitHub
settings) requires these checks to pass before merge. Bypassing CI
requires admin-on-the-repo permission and is out of scope per §2.2.

### R8 — Output filtered for PII and role

**Evidence.**
- `core/security_layer.py:L325–L373` — `mask_sensitive(text,
  user_role)`. Redacts phone, email, password fragments, API keys,
  card numbers.
- `core/security_layer.py:L375–L414` — `filter_answer_by_role(text,
  role)`. Adds role-based keyword redaction; external users get
  person-name redaction.

**Argument.** Every reply path that returns generated content to the
client goes through `filter_answer_by_role()` (search server code for
the function name; multiple callsites in the answer-assembly path).
A bypass would require a new endpoint to return raw LLM output, which
is forbidden by the same architecture-label rule that protects R1.

---

## 5. Secure design principles applied

The above arguments lean on a small set of design principles. They are
called out explicitly here to make the assurance case auditable as a
*set of principles* applied consistently, not just as eight unrelated
guards.

### 5.1 Least privilege

- Roles are a four-step ladder: `external < employee < manager <
  admin` (`core/auth.py:L62`).
- Sensitivity levels mirror roles (`core/security_layer.py:L22–L23`).
- Action-to-minimum-role mapping
  (`core/policy_engine.py:L102–L106`) is the canonical least-privilege
  table: e.g., `shell.exec` requires `admin`, `fs.write` requires
  `admin`, `fs.read` requires `employee`. There is no "any role"
  tool.

### 5.2 Defense in depth

- PolicyEngine is the *primary* gate; the sandbox path-allowlist is a
  *secondary* gate; the bandit `shell=True` flag in CI is a *tertiary*
  gate against regressions. Each operates at a different layer.
- Audit records are mirrored to SQLite + JSONL; losing one store
  leaves the other (R5).
- Self-evolution has four independent prerequisites (R2); none of
  them subsumes another.

### 5.3 Fail closed / fail fast

- Missing secrets crash at import (R4).
- Missing `approver_username` returns 400 *before* the patch JSON is
  even read into memory.
- PolicyEngine decisions are `Decision(allowed=False, …)` by
  default — callers must receive an explicit `allowed=True` to act.

### 5.4 Explicit trust boundaries

- The seven trust zones are enumerated in `ARCHITECTURE.md §5`.
  Anything marked **low** is mechanically forced through
  `extract_data_only()` before LLM context (R6).
- Plugin API is **explicitly not yet a trust boundary**
  (`PLATFORM_READINESS.md` gates) — this is documented as an
  in-progress promise, not a current one.

### 5.5 Audit before action

- `record_approval()` is called before `patch_apply()` (R2).
- `log_security_event()` is called before subprocess execution in
  the sandbox path.
- The audit log is the system of record; the action is downstream.

### 5.6 Single source of truth

- One PolicyEngine module (`core/policy_engine.py`) — no local
  re-implementation of ABAC anywhere in the tree.
- One sandbox module (`tools/code/sandbox.py`) — no local subprocess
  wrappers in `tools/*/`.
- One audit log schema per store; mirrors are derived, not divergent.

---

## 6. Known gaps and limitations

Acknowledged honestly. These are *not* mitigated by the arguments
above; they are work tracked elsewhere.

| Gap# | Description | Where tracked |
|------|-------------|---------------|
| **T11** | Signal-level prompt injection (Unicode confusables, homoglyphs, semantic paraphrase) is not detected. We rely on the LLM's robustness. | No issue yet — needs scoping after the v0.3 plugin API freeze. |
| **T12** | The sandbox is the only documented subprocess entry point, but the assurance case has not exhaustively proved there is no *undocumented* subprocess call elsewhere in `tools/`. A `grep -r "subprocess\."` audit is needed before silver-tier landing. | Tracked in `ROADMAP.md` v0.3 axis "Platform Skeleton". |
| **T13** | The main `audit_log` SQLite schema lacks an `approver_username` column. Approver identity for self-evolution events is stored in `james_patch_log.jsonl` and the patch JSON itself, not the main table. A future auditor must consult both stores. | Documented in R5. Schema unification candidate for v0.4. |
| **T14** | Plugin API is not yet a trust boundary — plugins run in-process with the host's privileges. The plan to make this a boundary is in `docs/PLATFORM_READINESS.md`. | Tracked in `PLATFORM_READINESS.md` (v0.3 / v0.4 gates). |
| **T15** | Bandit gates at HIGH severity only. 10 medium and 141 low findings remain (as of PR #356). | Tracked in the follow-up PR mentioned in `.github/workflows/security.yml`'s header comment. |
| **T16** | Some pytest files in `tests/` are excluded from CI pending Ollama service container / DB fixture isolation. The exclusion list is in `.github/workflows/test.yml` lines 49–108. | The exclusion list is itself the tracking artifact; each entry removed is the success signal. |
| **T17** | No SBOM signing / no dependency provenance verification beyond `requirements_pinned.txt`. | Out of scope for v0.3; candidate for v1.0 platform-readiness criterion. |
| **T18** | Operator-of-host is trusted (§2.2). JAMES is local-first; we do not defend against the host root. | Documented in `SECURITY.md` "Realistic Disclaimer". |

If you find a gap not listed here, it is a vulnerability and should be
reported through `SECURITY.md` §"Reporting a Vulnerability".

---

## 7. Maintenance

This document is reviewed at every v0.x → v0.(x+1) gate. The owner is
the maintainer team. PRs that change the assurance case must:

1. Update the relevant requirement (R<n>) and its argument together.
2. Add a row to §6 if a known gap is being introduced (or remove one
   if a gap is being closed).
3. Carry the `architecture` label, per `CLAUDE.md` rule 4.

Citation drift (file moved or renamed) is a documentation bug — open an
issue with label `assurance-case`.

---

## 8. References (code citations)

For quick navigation:

- `core/policy_engine.py` — PolicyEngine; lines 1–456.
- `core/security_layer.py` — ABAC, prompt-injection guards, output
  filters; full file.
- `core/auth.py` — RBAC roles, JWT signing/verifying; lines 1–447.
- `tools/code/sandbox.py` — sandbox + `safe_execute` + capability
  bridge; full file.
- `server_llmwiki.py` — audit DB schema (L72–L127), patch approval
  endpoint (L3621–L3734), role resolution (L411–L456).
- `config.py` — secrets fail-fast (L181–L191), self-evolution opt-in
  guard (L207–L226).
- `docs/ARCHITECTURE.md` — trust zones (§5), PolicyEngine spec (§5.5),
  CR primitive (§5.6).
- `SECURITY.md` — user-facing threat model + reporting.
- `.github/workflows/{lint,security,test,cla}.yml` — CI gates.
- `tests/test_security_layer.py`,
  `tests/test_policy_quarantine.py` — regression tests for ABAC and
  quarantine.

---

## 한국어 요약

본 문서는 JAMES의 **보안 보증 사례 (security assurance case)** 입니다. OpenSSF
Best Practices 의 `assurance_case` 기준을 충족하기 위해 작성되었으며, 외부 감사인 ·
보안 연구자 · 플러그인 작성자가 시스템 신뢰 계약을 한눈에 파악할 수 있는 단일
진입점입니다.

여덟 가지 보안 요구사항(R1–R8)을 정의하고, 각 요구사항이 코드 · CI · 문서의 어느
지점에서 어떻게 충족되는지 파일 경로 · 라인 범위 단위로 인용합니다. 위협 모델(§2)
은 자산 · 위협 행위자 · 위협 항목을 표로 정리하고, §6 에는 현재 시점에서 **방어
하지 못한 정직한 빈틈** (서명형 prompt injection, plugin trust boundary 미동결 등)
을 8개 항목으로 별도 추적합니다.

본 문서는 `SECURITY.md` 와 `docs/ARCHITECTURE.md §5` 를 **대체하지 않으며**, 그
두 문서가 정의한 정책을 인용 · 종합할 뿐입니다. v0.x → v0.(x+1) 게이트마다 재검토
되며, citation drift 는 `assurance-case` 라벨로 이슈 등록해 주세요.
