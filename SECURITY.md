# Security Policy

## Project Status

PROJECT JAMES is in **alpha (v0.1.0)** — security-focused by design, but **not production-ready**.

This document describes:
- The security model and threat assumptions
- What JAMES protects against today
- Known limitations
- How to report vulnerabilities

---

## Security Model

JAMES implements defense-in-depth across the RAG pipeline.

### 3-Stage Access Control

```
[Input]  → Instruction Isolation Filter (31+ injection patterns)
            ↓
[Search] → Graph-level RBAC + ABAC sensitivity gating
            ↓
[Output] → PII masking + role-based content filter
```

### RBAC (Role-Based Access Control)

4 roles with hierarchical permissions:

| Role     | Sensitivity Access     | Operations          |
|----------|----------------------|---------------------|
| admin    | public→secret         | All (incl. settings) |
| manager  | public→confidential   | Most (no admin)     |
| employee | public→internal       | Read + standard ops |
| external | public only           | Read public only    |

### ABAC (Attribute-Based Access Control)

4 sensitivity levels for every entity:

- `public` — all roles
- `internal` — employee+
- `confidential` — manager+
- `secret` — admin only

### Authentication

- JWT tokens with HS256 signing
- 8-hour expiration (configurable via `JWT_EXPIRE` in `core/auth.py`)
- Passwords stored as **bcrypt** (W4 P1-A, 2026-05-11) with an
  algorithm envelope (`bcrypt$...`). Pre-W4 unsalted SHA256 hex
  digests are accepted on input only and rewritten to bcrypt on the
  next successful login (transparent migration).
- Rate limiting: 30 requests / 60 seconds per IP across
  `/query/`, `/upload/`, `/login/`, `/signup/`,
  `/password/reset/confirm`
- Full audit log in SQLite (every request, decision, denial)

### Account creation (W4 P1-B)

- `POST /signup/` is public and creates a row with `active=0`,
  `role=external`. The account cannot log in until an admin approves
  and assigns a role.
- Success and duplicate produce the same 200 response body — an
  anonymous caller cannot enumerate existing usernames through this
  endpoint. The audit log distinguishes (`signup_pending` vs
  `signup_rejected_duplicate`) for operator review.
- Password policy: 8..72 characters (72 = bcrypt input window),
  must contain at least one letter and one digit. Korean and other
  unicode letters count. The 72-char ceiling is a hard reject rather
  than silent truncation so two long passwords cannot ever collide.
- Username policy: 3..32 characters, lowercase + digits + `_-` only.
  Case-folding collisions (`Admin` vs `admin`) are blocked at signup,
  not at login.

### Credential rotation (W4 P2-B)

- `POST /password/change` lets a logged-in user rotate their own
  password. Identity comes from the JWT subject claim — the request
  body never names a user.
- `POST /admin/users/issue-reset-token` lets an admin mint a one-shot
  reset token for a target user. The plaintext token is returned
  once; only SHA256(token) is persisted. 1-hour TTL. Issuing a new
  token revokes any prior unused token for the same user.
- `POST /password/reset/confirm` accepts `{username, token,
  new_password}`. Replay is blocked by a `used_at` flag written in
  the same transaction as the password UPDATE. Token-validity
  errors (unknown / expired / wrong username / already used) all
  collapse to a single 401 so anonymous callers cannot enumerate.

---

## Threat Model

### Defended Against

- **Prompt injection**: 31+ pattern detection + instruction isolation
- **Privilege escalation**: 3-stage check at vector / graph / output
- **Data exfiltration**: PII masking, role-based output filter
- **Brute force**: Rate limiting + audit logging
- **Hardcoded secrets**: All keys via environment variables
- **Replay attacks**: JWT expiration + signature verification
- **Risky-coding requests** (#8 v0.2): hard-refuse policy for queries asking the model to produce destructive shell / SQL / git / file commands — see §2.4 below

### Partially Defended

- **Tool abuse**: Sandboxed Python execution, but advanced sandbox escape attacks may succeed
- **Memory poisoning**: Source-tagged memory with role-based writes, but adversarial entries can pollute long-term store
- **Web search injection**: Tavily/DDG content is treated as untrusted, but malicious content could still affect downstream LLM responses

### 2.4 Risky-coding policy (v0.2, #8)

JAMES applies a **hard-refuse** policy to queries that ask the assistant to produce a clearly destructive command. The trigger fires *before* the LLM is called — no command is ever generated, no warnings-then-answer pattern is shown.

**What is blocked**

| Family | Examples |
|---|---|
| Filesystem-wide deletion | `rm -rf /`, `del /f /s /q`, `dd if=`, `shred`, `mkfs.*`, `format c:` |
| SQL drop / truncate | `drop database`, `drop table`, `truncate table` |
| Destructive git | `git reset --hard`, `git push --force`, `git clean -fdx` |
| Process kill | `kill -9`, `killall` |
| Scope-wide deletion (English) | `delete all files in /home`, `wipe every database` |
| Scope-wide deletion (Korean) | `wiki 폴더의 모든 파일을 삭제하는 명령어`, `데이터베이스 초기화 명령` |

The matched query receives the same `자료에 없음. 보안 정책에 의해 차단되었습니다.` response as a prompt-injection block — the two are byte-identical so an audit consumer cannot distinguish them externally. Patterns live in `core/security_layer.py::RISKY_CODING_REGEX`.

**What is NOT blocked**

The matcher is intentionally narrow. A documentation question about how a destructive command works is generally fine — only its *use* against a target is blocked:

- "rm 명령의 옵션 종류" → allowed (no `-rf` token + no scope marker)
- "git push가 무엇인가요?" → allowed
- "이메일 삭제하는 단축키" → allowed (no `전체` / `모든` scope marker before 삭제)

If a legitimate request is blocked, the operator can:

1. Rephrase without the destructive verb + scope-marker pair (most common fix)
2. Disable the gate temporarily by removing the call site in `core/security_layer.py::pre_check` (admin-only operation, requires git push by the maintainer — this is intentional friction)

**Why hard-refuse instead of warn-and-answer**

The earlier behavior (`mode=coding` answering with a 🚨 prefix) shipped commands paired with warnings. This violates the principle that the assistant should not produce output an operator wouldn't paste from a vendor manual. The block message names the policy; the user can ask again with a non-destructive framing.

### Out of Scope

- **Network-layer attacks** (run JAMES behind reverse proxy / firewall)
- **Physical access** to the host machine
- **Compromised LLM weights** or supply chain (Ollama / dependencies)
- **Side-channel attacks** (timing, cache)
- **Denial of service** beyond basic rate limiting

---

## Known Limitations

### Tested vs Untested

JAMES has been tested with:
- 65-item internal diagnostic (8 sections)
- 83-item adversarial security test (100% pass on synthetic adversarial inputs)

JAMES has **not** been tested against:
- Real adversarial users at scale
- Coordinated multi-vector attacks
- Production-grade red team
- Specific compliance frameworks (SOC2, HIPAA, GDPR)

### Realistic Disclaimer

Synthetic-data testing **does not equal** production security. Before any sensitive deployment:

1. Independent security review
2. Penetration testing
3. Compliance audit (if applicable)
4. Network isolation review
5. Backup and incident response plan

### Specific Caveats

- **JWT secret**: Defaults to a placeholder. **Must be set** via `JAMES_JWT_SECRET` env var with 32+ random characters before any non-development use.
- **API key**: Default value insufficient. Use a strong random key for `JAMES_API_KEY`.
- **HTTPS**: Server runs on plain HTTP by default. Production deployment **requires** reverse proxy with TLS (nginx/caddy).
- **Multi-tenancy**: Not implemented. Single-tenant only in v0.1.
- **LLM hallucination**: Even with Graph-RAG, responses may contain inaccuracies. Always verify critical information.

---

## Reporting a Vulnerability

If you discover a security vulnerability, please **do not** open a public GitHub issue.

Instead:

1. Email the maintainer directly (see GitHub profile)
2. Provide:
   - Steps to reproduce
   - Affected component
   - Suggested severity (per CVSS if possible)
   - Suggested mitigation (if any)

We aim to:
- Acknowledge within 7 days
- Provide initial assessment within 14 days
- Release a fix or workaround within 30 days for high-severity issues

You will receive credit in the security advisory unless you prefer otherwise.

---

## Security-Related Configuration

### Required Environment Variables

```bash
# Strong API key (32+ chars recommended)
JAMES_API_KEY=<random-32-char-string>

# JWT signing secret (NEVER commit, regenerate per environment)
JAMES_JWT_SECRET=<random-32-char-string>

# Generate with:
# python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Recommended Production Configuration

- Run behind reverse proxy (nginx, Caddy)
- Enable TLS / HTTPS
- Restrict origin via CORS
- Set `JAMES_PROTECTED_FILES` to prevent tool access to critical files
- Enable audit log retention (default: SQLite, no auto-rotation)
- Regular backup of `wiki/`, `memory/`, audit DB
- Monitor `[SEC]` log entries for anomalies

---

## Changes Log

- **v0.1.0-alpha** (2026): Initial security model documented

---

## Disclaimer

This software is provided "as is" without warranty of any kind, express or implied. The maintainers are not liable for any damages arising from the use of this software in any context, especially production environments handling sensitive data.

**Use this software at your own risk.**
