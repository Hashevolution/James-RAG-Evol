"""``core.security_layer`` — Phase 4 통합 보안 레이어.

Originally a single 23 KB module; split in Stage C.4 (2026-05-24)
into a 4-module package so every file respects CLAUDE.md rule #5
(< 20 KB per file). The external surface is unchanged — every
function, class, and constant that callers import from
``core.security_layer`` is re-exported here.

Phase 3.5 + Phase 4 invariants (carried through the split unchanged):

- [SEC-FIX-1] admin bypass 제거
- [SEC-FIX-2] post_check user_role 전달
- [SEC-FIX-3] _sanitize_query ATTACK_REGEX 적용
- [P4-SEC-1] Instruction Isolation
- [P4-SEC-2] ABAC 3단계 일관성 검증
- [LOG-1]    Silent failure 로그 (SQLite audit_log; legacy JSONL
             removed in Stage D.1 / PR #430)

Layout:

- ``_policies.py``  — role tables + attack/risky/instruction-injection
                      pattern lists + output-filter sensitive patterns
- ``_audit.py``     — log_attack / log_system_event (audit_bridge wrappers)
- ``_detection.py`` — validate_input / detect_attack / detect_risky_coding
                      / extract_data_only / sanitize_document_content
- ``_abac.py``      — check_access / filter_graph_by_abac /
                      cross_stage_abac_verify / mask_sensitive /
                      filter_answer_by_role
- this file         — ``SecurityLayer`` class + facade re-exports
"""
from __future__ import annotations

import re
from typing import Dict

from ._abac import (
    check_access,
    cross_stage_abac_verify,
    filter_answer_by_role,
    filter_graph_by_abac,
    mask_sensitive,
)
from ._audit import log_attack, log_system_event
from ._detection import (
    detect_attack,
    detect_risky_coding,
    extract_data_only,
    sanitize_document_content,
    validate_input,
)
from ._policies import (
    ATTACK_PATTERNS,
    ATTACK_REGEX,
    BLOCKED_KEYWORDS_BY_ROLE,
    INSTRUCTION_INJECTION_PATTERNS,
    RISKY_CODING_REGEX,
    ROLE_LEVEL,
    SENSITIVE_ENTITY_TYPES_BY_ROLE,
    SENSITIVE_PATTERNS,
    SENSITIVITY_LEVEL,
)


class SecurityLayer:
    """Phase 4 통합 보안 레이어"""

    def pre_check(self, query: str, user_role: str) -> dict:
        # 1. 입력 유효성
        try:
            ok, reason = validate_input(query)
            if not ok:
                return {"allowed": False, "reason": f"자료에 없음. {reason}", "query": query}
        except Exception as e:
            log_system_event("pre_check.validate", str(e), role=user_role)
            return {"allowed": False, "reason": "입력 검증 오류", "query": query}

        # 2. 공격 탐지 [SEC-FIX-1: admin도 차단]
        try:
            if detect_attack(query):
                log_attack(query, user_role)
                log_system_event("attack_detected", f"query={query[:80]}",
                                 role=user_role, level="WARN")
                print(f"[SECURITY] 🚨 공격 차단 (role={user_role})")
                return {"allowed": False,
                        "reason": "자료에 없음. 보안 정책에 의해 차단되었습니다.",
                        "query": query}
        except Exception as e:
            log_system_event("pre_check.detect", str(e), role=user_role)
            return {"allowed": False, "reason": "보안 검사 실패", "query": query}

        # 2.5. Risky-coding policy [#8 Axis 6] — hard-refuse for queries
        # that ask the model to produce a clearly-destructive command.
        # Distinct from prompt-injection (above): the user isn't trying
        # to subvert the system, but answering would still enable harm.
        # Same block reason as detect_attack so the response is
        # byte-identical for both classes (audit / bench invariants).
        try:
            if detect_risky_coding(query):
                log_attack(query, user_role, attack_type="risky_coding")
                log_system_event("risky_coding_blocked", f"query={query[:80]}",
                                 role=user_role, level="WARN")
                print(f"[SECURITY] 🚨 위험 코딩 요청 차단 (role={user_role})")
                return {"allowed": False,
                        "reason": "자료에 없음. 보안 정책에 의해 차단되었습니다.",
                        "query": query}
        except Exception as e:
            log_system_event("pre_check.risky_coding", str(e), role=user_role)
            return {"allowed": False, "reason": "보안 검사 실패", "query": query}

        # 3. Instruction Isolation [P4-SEC-1]
        try:
            safe_query, was_modified = extract_data_only(query)
            if was_modified:
                log_attack(query, user_role, attack_type="instruction_injection")
        except Exception as e:
            log_system_event("pre_check.isolation", str(e), role=user_role)
            safe_query = query[:500]

        # 4. query 정제 [SEC-FIX-3: regex까지]
        try:
            safe_query = self._sanitize_query(safe_query)
        except Exception as e:
            log_system_event("pre_check.sanitize", str(e), role=user_role)

        return {"allowed": True, "reason": None, "query": safe_query}

    @staticmethod
    def _sanitize_query(text: str) -> str:
        """[SEC-FIX-3] ATTACK_PATTERNS + ATTACK_REGEX 둘 다 치환"""
        for pattern in ATTACK_PATTERNS:
            text = re.sub(re.escape(pattern), "[BLOCKED]", text, flags=re.IGNORECASE)
        for pattern in ATTACK_REGEX:
            text = re.sub(pattern, "[BLOCKED]", text, flags=re.IGNORECASE)
        return text[:500]

    @staticmethod
    def filter_graph(graph_context: list, user_role: str) -> list:
        try:
            return filter_graph_by_abac(graph_context, user_role)
        except Exception as e:
            log_system_event("filter_graph", str(e), role=user_role)
            return []

    @staticmethod
    def post_check(context: str, user_role: str) -> dict:
        """[SEC-FIX-2] user_role 전달"""
        try:
            masked = mask_sensitive(context, user_role)
            return {"allowed": True, "reason": None, "context": masked}
        except Exception as e:
            log_system_event("post_check", str(e), role=user_role)
            return {"allowed": True, "reason": None, "context": context}

    @staticmethod
    def abac_consistency_check(user_role, vector_docs, graph_entities, final_answer) -> Dict:
        """[P4-SEC-2] ABAC 3단계 일관성 검증"""
        return cross_stage_abac_verify(user_role, vector_docs, graph_entities, final_answer)


__all__ = [
    # Class
    "SecurityLayer",
    # Policies
    "ROLE_LEVEL",
    "SENSITIVITY_LEVEL",
    "ATTACK_PATTERNS",
    "ATTACK_REGEX",
    "RISKY_CODING_REGEX",
    "INSTRUCTION_INJECTION_PATTERNS",
    "SENSITIVE_PATTERNS",
    "BLOCKED_KEYWORDS_BY_ROLE",
    "SENSITIVE_ENTITY_TYPES_BY_ROLE",
    # Audit
    "log_attack",
    "log_system_event",
    # Detection
    "validate_input",
    "detect_attack",
    "detect_risky_coding",
    "extract_data_only",
    "sanitize_document_content",
    # ABAC + output filter
    "check_access",
    "filter_graph_by_abac",
    "cross_stage_abac_verify",
    "mask_sensitive",
    "filter_answer_by_role",
]
