"""Heuristic security scan over the final answer.

Split out of the single-file ``core/reasoning/verify.py`` on 2026-09-26.
The file had reached 20,008 B against CLAUDE.md rule #5's 20 KB cap —
472 B of headroom — so it could not take another line. Same shape as the
v0.6 ``core/reasoning/reflect/`` split; ``__init__`` re-exports the
pre-split surface, so the move is a no-op for callers.
"""
from __future__ import annotations

import re
from typing import List


def _build_security_flags(answer: str, user_role: str) -> List[str]:
    """Heuristic scan. Reuses the existing INSTRUCTION_INJECTION_PATTERNS
    + SENSITIVE_PATTERNS so the verifier and the v0.2 security layer
    agree on what counts as a leak.
    """
    flags: List[str] = []
    if not answer:
        return flags

    try:
        from core.security_layer import (
            INSTRUCTION_INJECTION_PATTERNS,
            SENSITIVE_PATTERNS,
            BLOCKED_KEYWORDS_BY_ROLE,
        )
    except Exception:
        return flags

    # Injection echo — a low-trust source's instruction text bled into
    # the answer despite ingest-time sanitization. This is the highest-
    # severity signal; triggers "block".
    for pattern in INSTRUCTION_INJECTION_PATTERNS:
        try:
            if re.search(pattern, answer, flags=re.IGNORECASE):
                snippet = pattern[:30] + ("…" if len(pattern) > 30 else "")
                flags.append(f"security.injection_echo:{snippet}")
        except re.error:
            continue

    # Sensitive data leak — the output filter still does the redaction;
    # we just flag for audit.
    for pattern, label in SENSITIVE_PATTERNS:
        try:
            if re.search(pattern, answer):
                flags.append(f"security.sensitive_leak:{label}")
        except re.error:
            continue

    # Role-aware blocked keywords — covers the existing role gating
    # for external / employee viewers.
    role_blocked = BLOCKED_KEYWORDS_BY_ROLE.get(user_role, [])
    for kw in role_blocked:
        if kw and kw.lower() in answer.lower():
            flags.append(f"security.role_blocked:{kw}")

    return flags
