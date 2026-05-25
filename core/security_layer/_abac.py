"""Security layer — ABAC + output filtering.

The retrieval-side and answer-side decisions:

- ``check_access`` / ``filter_graph_by_abac`` — single-stage ABAC,
  routed through ``PolicyEngine`` per #44 phase 2-B
- ``cross_stage_abac_verify`` — [P4-SEC-2] 3-stage consistency check
  (Vector → Graph → Output) so an ABAC bypass at any layer is caught
- ``mask_sensitive`` — PII regex + role-keyword masking
- ``filter_answer_by_role`` — answer-level filter; layers
  graph-context entity masking + wiki person-name masking +
  ``mask_sensitive``

Split out of the monolithic ``core/security_layer.py`` in Stage C.4
(2026-05-24). All names are re-exported from ``core.security_layer``.
"""
from __future__ import annotations

import re
from typing import Dict

from ._audit import log_system_event
from ._policies import (
    BLOCKED_KEYWORDS_BY_ROLE,
    ROLE_LEVEL,
    SENSITIVE_ENTITY_TYPES_BY_ROLE,
    SENSITIVE_PATTERNS,
    SENSITIVITY_LEVEL,
)


def check_access(user_role: str, entity: dict) -> bool:
    sensitivity = entity.get("sensitivity", "public")
    return ROLE_LEVEL.get(user_role, 0) >= SENSITIVITY_LEVEL.get(sensitivity, 0)


def filter_graph_by_abac(graph_context: list, user_role: str) -> list:
    # #44 phase 2-B: graph ABAC routes through PolicyEngine.can_walk so future
    # graph-specific policy (depth caps, relation-type guards) lands in one
    # place. PolicyEngine.can_walk currently delegates back to check_access
    # bit-for-bit (#50). Lazy import avoids module-load cycle.
    from core.policy_engine import default_engine as _policy
    return [e for e in graph_context if _policy.can_walk(user_role, e).allowed]


def cross_stage_abac_verify(
    user_role: str,
    vector_docs: list,
    graph_entities: list,
    final_answer: str,
) -> Dict:
    """
    [P4-SEC-2] Vector → Graph → Output 3단계 동일 ABAC 정책 검증.
    external이 confidential을 어느 단계에서도 볼 수 없도록 보장.

    #44 phase 2-C: Stage 1/2 route through PolicyEngine so the cross-stage
    invariant is checked against the same source of policy as live retrieval
    and graph traversal. Lazy import avoids module-load cycle.
    """
    from core.policy_engine import default_engine as _policy

    violations, stage_results = [], {}

    # Stage 1: Vector
    v_pass = v_fail = 0
    for doc in vector_docs:
        meta = doc.get("metadata", {"sensitivity": "public"})
        if _policy.can_retrieve(user_role, meta).allowed:
            v_pass += 1
        else:
            v_fail += 1
            violations.append(
                f"Vector 우회: role={user_role} sensitivity={meta.get('sensitivity')}"
            )
    stage_results["vector"] = {"pass": v_pass, "fail": v_fail}

    # Stage 2: Graph
    g_pass = g_fail = 0
    for entity in graph_entities:
        if _policy.can_walk(user_role, entity).allowed:
            g_pass += 1
        else:
            g_fail += 1
            violations.append(
                f"Graph 우회: entity={entity.get('name','?')} "
                f"sensitivity={entity.get('sensitivity','?')}"
            )
    stage_results["graph"] = {"pass": g_pass, "fail": g_fail}

    # Stage 3: Output 키워드 누출 검사 (external만)
    out_violations = 0
    if user_role == "external" and final_answer:
        blocked = ["비밀", "confidential", "기밀", "salary", "급여", "주민번호", "secret"]
        for kw in blocked:
            if kw.lower() in final_answer.lower():
                violations.append(f"Output 누출: 민감 키워드 '{kw}' → external 노출")
                out_violations += 1
    stage_results["output"] = {"violations": out_violations}

    consistent = len(violations) == 0
    if not consistent:
        log_system_event("abac_violation",
                         f"role={user_role} violations={violations[:3]}",
                         role=user_role, level="WARN")

    return {"consistent": consistent, "violations": violations,
            "stage_results": stage_results, "role": user_role}


def mask_sensitive(text: str, user_role: str = "external") -> str:
    """
    3단계 Output Filter.
    [BUG1-FIX] 키워드 뒤따르는 값까지 마스킹:
      기존: '급여' → '[REDACTED]' (': 5000만원' 잔존)
      수정: '급여: 5000만원' → '[REDACTED]' (값까지 제거)
    """
    if not isinstance(text, str):
        return str(text) if text else ""
    for pattern, label in SENSITIVE_PATTERNS:
        text = re.sub(pattern, f"[{label} REDACTED]", text, flags=re.IGNORECASE)
    for keyword in BLOCKED_KEYWORDS_BY_ROLE.get(user_role, []):
        if keyword.lower() in text.lower():
            # [BUG1-FIX] 키워드 + 구분자 + 뒤따르는 값까지 마스킹
            # 예: 급여: 5000만원, 연봉=8000만원, salary 8000
            value_pattern = re.escape(keyword) + r"[\s:=]*[\w가-힣\d,.\-+만원달러%]+"
            new_text = re.sub(value_pattern, "[REDACTED]", text, flags=re.IGNORECASE)
            if new_text != text:
                text = new_text   # 값까지 포함 치환 성공
            else:
                # 값 패턴 미매칭 시 키워드만 치환 (안전 fallback)
                text = re.sub(re.escape(keyword), "[REDACTED]", text, flags=re.IGNORECASE)
    return text


def filter_answer_by_role(
    answer: str,
    user_role: str,
    graph_context: list = None,
    wiki_person_names: list = None,   # [BUG3-FIX] wiki에서 가져온 person 이름 목록
) -> str:
    """
    Answer-level 필터.

    [BUG3-FIX] external role에서 person 이름 마스킹 범위 확장:
      기존: graph_context에 포함된 person만 마스킹
            → Vector 결과에서 나온 person 이름은 미마스킹
      수정: wiki_person_names 파라미터로 전체 person 이름 목록 받아 마스킹
            graph_context 없어도 answer 내 person명 직접 스캔
    """
    if not isinstance(answer, str):
        return answer

    sensitive_types = SENSITIVE_ENTITY_TYPES_BY_ROLE.get(user_role, set())

    # 1단계: graph_context 기반 마스킹 (기존)
    if graph_context and sensitive_types:
        for entity in graph_context:
            if not isinstance(entity, dict):
                continue
            if entity.get("entity_type") in sensitive_types:
                name = entity.get("name", "")
                if name and name in answer:
                    answer = answer.replace(name, "[인물명 REDACTED]")

    # 2단계: [BUG3-FIX] wiki_person_names 기반 추가 마스킹
    # external이 Vector 결과를 통해 person 이름이 노출되는 경우 방어
    if "person" in sensitive_types and wiki_person_names:
        for name in wiki_person_names:
            if name and len(name) >= 2 and name in answer:
                answer = answer.replace(name, "[인물명 REDACTED]")

    # 3단계: PII + 키워드 마스킹
    answer = mask_sensitive(answer, user_role)
    return answer


__all__ = [
    "check_access",
    "filter_graph_by_abac",
    "cross_stage_abac_verify",
    "mask_sensitive",
    "filter_answer_by_role",
]
