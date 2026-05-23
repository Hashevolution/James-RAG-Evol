"""Security layer — policy constants.

Role / sensitivity tables, prompt-injection patterns, risky-coding
patterns, instruction-isolation patterns, and the output-filter
sensitive-pattern table. Pure data — no functions.

Split out of the monolithic ``core/security_layer.py`` in Stage C.4
(2026-05-24) so the package respects CLAUDE.md rule #5 (< 20 KB per
file). All names are re-exported from ``core.security_layer`` so
external imports (``ROLE_LEVEL`` etc.) keep working byte-identical.
"""
from __future__ import annotations

from typing import Dict, List, Set


ROLE_LEVEL = {"admin": 3, "manager": 2, "employee": 1, "external": 0}
SENSITIVITY_LEVEL = {"public": 0, "internal": 1, "confidential": 2, "secret": 3}

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


__all__ = [
    "ROLE_LEVEL",
    "SENSITIVITY_LEVEL",
    "ATTACK_PATTERNS",
    "ATTACK_REGEX",
    "RISKY_CODING_REGEX",
    "INSTRUCTION_INJECTION_PATTERNS",
    "SENSITIVE_PATTERNS",
    "BLOCKED_KEYWORDS_BY_ROLE",
    "SENSITIVE_ENTITY_TYPES_BY_ROLE",
]
