"""v0.5 — security primitives module.

Mother-platform surface for security-related primitives that the
B.1/B.2/B.3 audit cycle identified as enterprise-procurement
check-items:

  * `headers` — HTTP response security headers (CSP, X-Frame-Options,
    Strict-Transport-Security, X-Content-Type-Options,
    Referrer-Policy, Permissions-Policy) with env-driven config
    and a default report-only CSP mode.

Future additions (B.2 design memo):
  * `approval_evidence` — verified-approver-principal binding for
    self-evolution change requests (G2; deferred to v0.6).
"""
from __future__ import annotations

from core.security import headers

__all__ = ["headers"]
