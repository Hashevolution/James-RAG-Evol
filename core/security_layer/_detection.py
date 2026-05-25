"""Security layer — input validation + threat detection + isolation.

The pre-LLM funnel:

- ``validate_input`` — empty / oversized refusal
- ``detect_attack`` — prompt-injection pattern match
- ``detect_risky_coding`` — destructive-command pattern match (#8)
- ``extract_data_only`` — [P4-SEC-1] instruction isolation (neutralize
  in-line directives in untrusted text)
- ``sanitize_document_content`` — backward-compat shim that delegates
  to ``PolicyEngine.sanitize_for_ingestion``

Split out of the monolithic ``core/security_layer.py`` in Stage C.4
(2026-05-24). All names are re-exported from ``core.security_layer``.
"""
from __future__ import annotations

import re
from typing import Tuple

from ._audit import log_system_event
from ._policies import (
    ATTACK_PATTERNS,
    ATTACK_REGEX,
    INSTRUCTION_INJECTION_PATTERNS,
    RISKY_CODING_REGEX,
)


def validate_input(query: str):
    if not query or not query.strip():
        return False, "빈 입력입니다"
    if len(query) > 500:
        return False, "입력 길이 초과"
    return True, None


def detect_attack(query: str) -> bool:
    q = query.lower().strip()
    if any(p in q for p in ATTACK_PATTERNS):
        return True
    for pattern in ATTACK_REGEX:
        if re.search(pattern, q, re.IGNORECASE):
            return True
    return False


def detect_risky_coding(query: str) -> bool:
    """[#8] True if `query` is asking the assistant to produce a
    clearly-destructive shell/SQL/git/file command.

    Distinct from `detect_attack` (prompt-injection). The match set is
    deliberately narrow — see RISKY_CODING_REGEX comment. Block reason
    is identical to the prompt-injection block so q11 / q12 are
    indistinguishable to a downstream caller (one byte-identical
    "차단되었습니다" response across all hard-refuse paths).
    """
    if not query:
        return False
    for pattern in RISKY_CODING_REGEX:
        if re.search(pattern, query, flags=re.IGNORECASE):
            return True
    return False


def extract_data_only(raw_input: str) -> Tuple[str, bool]:
    """
    [P4-SEC-1] 외부 입력에서 명령어 성격 텍스트를 탐지·제거.

    Pipeline: raw_input → detect → neutralize → clean_data
    모든 외부 입력을 untrusted zone으로 처리.

    Returns: (clean_data, was_modified)
    """
    if not raw_input or not isinstance(raw_input, str):
        return raw_input or "", False

    text, modified = raw_input, False

    for pattern in INSTRUCTION_INJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
            text = re.sub(pattern, "[INSTRUCTION_REMOVED]", text,
                          flags=re.IGNORECASE | re.MULTILINE)
            modified = True

    for pattern in ATTACK_PATTERNS:
        if pattern.lower() in text.lower():
            text = re.sub(re.escape(pattern), "[BLOCKED]", text, flags=re.IGNORECASE)
            modified = True

    for pattern in ATTACK_REGEX:
        if re.search(pattern, text, re.IGNORECASE):
            text = re.sub(pattern, "[BLOCKED]", text, flags=re.IGNORECASE)
            modified = True

    if modified:
        print("[ISOLATION] ⚠️ Instruction injection 탐지 — 중립화 완료")
        log_system_event("instruction_isolation",
                         f"원본길이={len(raw_input)} 정제길이={len(text)}", level="WARN")

    return text.strip(), modified


def sanitize_document_content(content: str, source: str = "unknown") -> str:
    """[P4-SEC-1] 문서 저장 전 정제 — poisoned embedding 방지.

    #44 phase 4-C: backwards-compat shim. Delegates to
    `PolicyEngine.sanitize_for_ingestion` so `core/policy_engine.py` is
    the single ingestion-time decision point. Callers passing a raw `str`
    (legacy code path) get wrapped as `TrustedContent(source="doc",
    trust="medium")` — the canonical ingestion default; new callers
    should construct their own `TrustedContent` and call
    `default_engine.sanitize_for_ingestion(tc, source=...)` directly.

    Lazy import avoids a module-load cycle (`policy_engine` lazily
    imports `extract_data_only` / `log_attack` from this module).
    """
    from core.policy_engine import default_engine, TrustedContent
    tc = TrustedContent(text=content, source="doc", trust="medium")
    clean, _ = default_engine.sanitize_for_ingestion(tc, source=source)
    return clean


__all__ = [
    "validate_input",
    "detect_attack",
    "detect_risky_coding",
    "extract_data_only",
    "sanitize_document_content",
]
