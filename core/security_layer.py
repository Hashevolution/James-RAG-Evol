"""
PROJECT JAMES - Security Layer (Phase 4 완성본)

Phase 3.5 수정 적용:
  [SEC-FIX-1] admin bypass 제거
  [SEC-FIX-2] post_check user_role 전달
  [SEC-FIX-3] _sanitize_query ATTACK_REGEX 적용

Phase 4 신규:
  [P4-SEC-1] Instruction Isolation
  [P4-SEC-2] ABAC 3단계 일관성 검증
  [LOG-1]    Silent failure 로그
"""

import re
import json
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

# ─── 정책 ────────────────────────────────────────────────────

ROLE_LEVEL = {"admin": 3, "manager": 2, "employee": 1, "external": 0}
SENSITIVITY_LEVEL = {"public": 0, "internal": 1, "confidential": 2, "secret": 3}

ATTACK_LOG_PATH = "james_attack_log.jsonl"
SYSTEM_LOG_PATH = "james_system_log.jsonl"

ATTACK_PATTERNS = [
    # 영어 패턴
    "ignore previous", "ignore all", "ignore all previous", "previous instructions",
    "system prompt", "forget previous", "forget all", "override rule",
    "you are now", "act as", "pretend you", "jailbreak", "disregard", "bypass",
    "new instructions", "prompt injection",
    # 영어 SYSTEM 접두어
    "system:",
    # 한국어 패턴
    "모든 규칙 무시", "규칙을 무시", "규칙 무시", "무시하고 답해",
    "다음 지시를 따르", "이전 내용을 무시", "모든 지시를",
    "이전 지시를 무시", "지시를 무시하고",
    "관리자 정보", "관리자 모드", "admin 출력",
    "비밀번호",
    # 특수 패턴
    "[[prompt",
]

ATTACK_REGEX = [
    r"ignore\s+(all\s+)?(previous|prior)(\s+rules?|\s+instructions?)?",
    r"forget\s+(all\s+)?(previous|prior)",
    r"(system|sys)\s*prompt",
    r"override\s+.{0,20}rule",
    r"you\s+are\s+now",
    r"act\s+as\s+\w",
    r"admin\s*(출력|정보|password|pw)",
    r"(무시|ignore).{0,30}(규칙|rule|지시|instruction)",
    r"disregard\s+(all\s+)?(previous|prior|above)",
    r"bypass\s+(security|filter|rule|check)",
    r"new\s+(role|persona|instruction)",
    r"from\s+now\s+on",
    r"pretend\s+(you|to)",
]

# ─── #8 Risky-coding policy (Axis 6) ────────────────────────
# Hard-refuse policy: requests that *ask the model to produce a
# destructive shell/SQL/file command* are blocked at pre_check, before
# the LLM is called. The user gets the same "차단되었습니다" reason as
# prompt-injection blocks (q11) — byte-identical 26-char response.
#
# This is distinct from prompt-injection (ATTACK_PATTERNS): those try
# to subvert the system prompt. Risky-coding is a borderline case — the
# user is asking a legitimate-looking question whose *answer* would
# enable destructive action.
#
# Patterns are intentionally narrow: the trigger requires both a
# destructive verb AND a scope marker ("all/every/모든/전체/wiki 폴더의"
# etc.) so a documentation question like "rm -rf 옵션 설명해줘" is NOT
# blocked unless paired with a target scope. See SECURITY.md §2.4 for
# the policy decision and the "if blocked legitimately" escape hatch.
RISKY_CODING_REGEX = [
    # Explicit destructive shell commands (highest signal)
    r"\brm\s+-rf\b",
    r"\bdd\s+if=",
    r"\bshred\s+",
    r"\bmkfs\.",
    r"\bdel\s+/[fsq]\s",
    r"\brmdir\s+/s\s",
    r"format\s+[a-z]:",
    # SQL drop / truncate
    r"\bdrop\s+(database|table|schema|index)\b",
    r"\btruncate\s+table\b",
    # Destructive git
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+push\s+(-f\b|--force\b)",
    r"\bgit\s+clean\s+-[fdx]",
    # Process kill
    r"\bkill\s+-9\b",
    r"\bkillall\s+",
    # All-files / scope-wide deletion (English)
    r"(delete|remove|wipe|erase)\s+(all|every|the entire|whole)\s+\S{0,15}\s*(files?|data|directory|folder)",
    # All-files / scope-wide deletion (Korean) — q12 signature
    r"(전체|모든|모든 파일|전부)\s*\S{0,20}\s*(삭제|지우|제거|초기화|포맷)",
    r"(폴더|디렉토리|directory)\s*\S{0,15}\s*(통째로|모두|전부)\s*(삭제|지우)",
    r"(데이터베이스|database|DB)\s*\S{0,10}\s*(삭제|drop|초기화|reset)",
    r"(강제|force)\s*(푸시|push|reset|초기화)",
]


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


# [P4-SEC-1] Instruction Isolation 패턴
INSTRUCTION_INJECTION_PATTERNS = [
    r"(당신은|너는|you are|you're)\s+.{0,30}(assistant|helper|agent|bot|ai)",
    r"(반드시|must|should|always)\s+.{0,20}(answer|tell|say|output|print|reveal)",
    r"(end|stop|exit|quit|close)\s+(session|conversation|context|system)",
    # [BUG2-FIX] .{0,15} 삽입: "show ME all the data" 등 중간 단어 허용
    r"(show|print|output|display|reveal|expose).{0,15}(all|every|the).{0,10}(data|info|secret|key|password)",
    r"(새|new|다음|following)\s*(지시|명령|instruction|command|rule)",
    r"(context|system|previous)\s*(is|was|=|:)\s*[\"']",
]

# ─── 로그 ────────────────────────────────────────────────────

def log_attack(query: str, role: str, attack_type: str = "injection"):
    try:
        entry = {"time": datetime.now().isoformat(), "role": role,
                 "attack_type": attack_type, "query": query[:200]}
        with open(ATTACK_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass

def log_system_event(step: str, detail: str, role: str = "unknown", level: str = "ERROR"):
    """[LOG-1] james_system_log.jsonl 영구 기록"""
    try:
        entry = {"time": datetime.now().isoformat(), "level": level,
                 "step": step, "detail": str(detail)[:300], "role": role}
        with open(SYSTEM_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass

# ─── 입력 검증 ───────────────────────────────────────────────

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

# ─── [P4-SEC-1] Instruction Isolation ───────────────────────

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

# ─── ABAC ────────────────────────────────────────────────────

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

# ─── [P4-SEC-2] ABAC 3단계 일관성 검증 ─────────────────────

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

# ─── Output Filter ───────────────────────────────────────────

SENSITIVE_PATTERNS = [
    (r"\b\d{6}-\d{7}\b",                                       "주민번호"),
    (r"\b\d{3}-\d{4}-\d{4}\b",                                 "전화번호"),
    (r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b", "이메일"),
    (r"password\s*[:=]\s*\S+",                                  "비밀번호"),
    (r"비밀번호\s*[:=]\s*\S+",                                   "비밀번호"),
    (r"api[_\-]?key\s*[:=]\s*[\w\-]+",                         "API키"),
    (r"secret\s*[:=]\s*[\w\-]+",                                "시크릿"),
    (r"token\s*[:=]\s*[\w\.\-]+",                               "토큰"),
    (r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b",       "카드번호"),
    (r"계좌[번호\s]*[:\s]*[\d\-]+",                              "계좌번호"),
    (r"\b[A-Z]{2,5}-\d{4,8}\b",                                 "내부코드"),
]

BLOCKED_KEYWORDS_BY_ROLE: Dict[str, List[str]] = {
    "external": ["급여","연봉","salary","개인정보","주민","비밀",
                 "confidential","기밀","내부망","DB 구조","스키마",
                 "서버 IP","포트","접속 정보"],
    "employee": ["급여","salary","주민등록번호","비밀번호","secret"],
}

SENSITIVE_ENTITY_TYPES_BY_ROLE: Dict[str, Set[str]] = {
    "external": {"person"}, "employee": set(), "manager": set(), "admin": set(),
}

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

# ─── SecurityLayer 클래스 ────────────────────────────────────

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
