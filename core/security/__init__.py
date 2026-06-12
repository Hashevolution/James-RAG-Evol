"""v0.5 — security primitives module.

Mother-platform surface for security-related primitives that the
B.1/B.2/B.3 audit cycle identified as enterprise-procurement
check-items:

  * `headers` — HTTP response security headers (CSP, X-Frame-Options,
    Strict-Transport-Security, X-Content-Type-Options,
    Referrer-Policy, Permissions-Policy) with env-driven config
    and a default report-only CSP mode.
  * `approval_evidence` — verified-approver-principal binding for
    self-evolution change requests (G2.a primitive — POSIX +
    explicit override resolution; OIDC + SSH paths in G2.b/c).
"""
from __future__ import annotations

from core.security import approval_evidence, headers

__all__ = ["approval_evidence", "headers"]
