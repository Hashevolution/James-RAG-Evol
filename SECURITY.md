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
- 24-hour expiration (configurable)
- Rate limiting: 30 requests / 60 seconds per user
- Full audit log in SQLite (every request, decision, denial)

---

## Threat Model

### Defended Against

- **Prompt injection**: 31+ pattern detection + instruction isolation
- **Privilege escalation**: 3-stage check at vector / graph / output
- **Data exfiltration**: PII masking, role-based output filter
- **Brute force**: Rate limiting + audit logging
- **Hardcoded secrets**: All keys via environment variables
- **Replay attacks**: JWT expiration + signature verification

### Partially Defended

- **Tool abuse**: Sandboxed Python execution, but advanced sandbox escape attacks may succeed
- **Memory poisoning**: Source-tagged memory with role-based writes, but adversarial entries can pollute long-term store
- **Web search injection**: Tavily/DDG content is treated as untrusted, but malicious content could still affect downstream LLM responses

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
Use one of the private channels below.

### 1. GitHub Private Vulnerability Reporting (preferred)

1. Open https://github.com/Hashevolution/James-RAG-Evol/security/advisories/new
2. Fill in the form: title, description, affected versions, severity, optional patch
3. Submit — only repository maintainers will see the report

This channel is preferred because it integrates with GitHub Security Advisories
and (when applicable) CVE assignment.

### 2. Backup email

If you cannot use GitHub PVR, email **karu-7@hanmail.net** with:

- Steps to reproduce
- Affected component / version
- Suggested severity (per CVSS if possible)
- Suggested mitigation (if any)

### Response timeline

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
