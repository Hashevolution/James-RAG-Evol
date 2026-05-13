"""
PROJECT JAMES — Memory Store (Phase 6 Step 1~3 + Persona)

SQLite 기반 선별적 Memory 저장.
Persona: admin이 설정하는 시스템 이름/성향/방식

[Module size split, 2026-05-13]
CLAUDE.md rule #5 (20 KB) 충족을 위해 다음 헬퍼 모듈로 분리:
  - core/memory/db.py          : DB_PATH / _connect / init_db
  - core/memory/conversation.py: 대화 히스토리 + 세션 관리
  - core/memory/summaries.py   : 세션 요약 + 장기기억 context
공개 API (`MemoryStore`, `DB_PATH`, `_connect`) 는 변함없이
이 모듈에서 re-export 되므로 호출 측 변경 불필요.
"""

from datetime import datetime

from core.memory.db import (
    DB_PATH,
    _PERSONA_DEPRECATION_LOGGED,
    _connect,
    init_db,
)
from core.memory.conversation import (
    delete_session as _conv_delete_session,
    get_all_sessions as _conv_get_all_sessions,
    get_history_context as _conv_get_history_context,
    get_recent_turns as _conv_get_recent_turns,
    save_turn as _conv_save_turn,
    set_session_name as _conv_set_session_name,
)
from core.memory.summaries import (
    get_long_term_context as _sum_get_long_term_context,
    get_session_summaries as _sum_get_session_summaries,
    save_session_summary as _sum_save_session_summary,
)

# Backward-compat re-exports — call sites still do
# `from core.memory.store import DB_PATH, _connect, init_db`.
__all__ = ["MemoryStore", "DB_PATH", "_connect", "init_db"]


class MemoryStore:
    """
    Memory 저장 / 조회 / LLM 프롬프트 주입용 context 생성.
    RAG VectorStore와 완전 분리.
    """

    def __init__(self):
        init_db()

    # ─── 저장 ────────────────────────────────────────────────

    def save(self, candidate: dict) -> bool:
        """검증된 Memory 저장."""
        mem_type = candidate.get("type")
        now      = datetime.now().isoformat()

        try:
            if mem_type == "preference":
                return self._save_preference(candidate, now)
            elif mem_type == "pattern":
                return self._save_pattern(candidate, now)
            elif mem_type == "goal":
                return self._save_goal(candidate, now)
            return False
        except Exception as e:
            print(f"[MEMORY_STORE] 저장 실패: {e}")
            return False

    def _save_preference(self, c: dict, now: str) -> bool:
        key   = c.get("key", "general")
        value = c.get("value", c.get("raw", ""))[:500]
        with _connect() as conn:
            existing = conn.execute(
                "SELECT id FROM preferences WHERE key=?", (key,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE preferences SET value=?, updated_at=? WHERE key=?",
                    (value, now, key)
                )
            else:
                conn.execute(
                    "INSERT INTO preferences (key, value, raw, confidence, created_at, updated_at)"
                    " VALUES (?,?,?,?,?,?)",
                    (key, value, c.get("raw",""), c.get("confidence",0.85), now, now)
                )
        print(f"[MEMORY_STORE] preference 저장: {key}={value[:40]}")
        return True

    def _save_pattern(self, c: dict, now: str) -> bool:
        pattern = c.get("pattern", c.get("raw",""))[:200]
        with _connect() as conn:
            existing = conn.execute(
                "SELECT id, count FROM patterns WHERE pattern=?", (pattern,)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE patterns SET count=count+1, updated_at=? WHERE pattern=?",
                    (now, pattern)
                )
            else:
                conn.execute(
                    "INSERT INTO patterns (pattern, count, raw, confidence, created_at, updated_at)"
                    " VALUES (?,1,?,?,?,?)",
                    (pattern, c.get("raw",""), c.get("confidence",0.80), now, now)
                )
        print(f"[MEMORY_STORE] pattern 저장: {pattern[:40]}")
        return True

    def _save_goal(self, c: dict, now: str) -> bool:
        goal = c.get("goal", c.get("raw",""))[:300]
        with _connect() as conn:
            conn.execute(
                "INSERT INTO goals (goal, confidence, raw, created_at) VALUES (?,?,?,?)",
                (goal, c.get("confidence",0.80), c.get("raw",""), now)
            )
        print(f"[MEMORY_STORE] goal 저장: {goal[:40]}")
        return True

    # ─── 조회 ────────────────────────────────────────────────

    def get_context(self, user_role: str = "external") -> str:
        """LLM 프롬프트 주입용 context 생성 (Step 1~3 전체)."""
        lines = []
        try:
            with _connect() as conn:
                prefs = conn.execute(
                    "SELECT key, value FROM preferences ORDER BY updated_at DESC LIMIT 10"
                ).fetchall()
                if prefs:
                    lines.append("[사용자 설정]")
                    for p in prefs:
                        lines.append(f"  - {p['key']}: {p['value']}")

                patterns = conn.execute(
                    "SELECT pattern FROM patterns WHERE count >= 2 ORDER BY count DESC LIMIT 5"
                ).fetchall()
                if patterns:
                    lines.append("[반복 패턴]")
                    for p in patterns:
                        lines.append(f"  - {p['pattern']}")

                goals = conn.execute(
                    "SELECT goal FROM goals ORDER BY created_at DESC LIMIT 3"
                ).fetchall()
                if goals:
                    lines.append("[목표]")
                    for g in goals:
                        lines.append(f"  - {g['goal'][:80]}")

        except Exception as e:
            print(f"[MEMORY_STORE] context 조회 실패: {e}")

        return "\n".join(lines) if lines else ""

    def clear(self):
        """테스트용 전체 초기화"""
        with _connect() as conn:
            conn.executescript(
                "DELETE FROM preferences; DELETE FROM patterns; DELETE FROM goals;"
            )

    # ─── Persona 설정 (admin 전용) ───────────────────────────

    def get_persona(self) -> dict:
        """현재 Persona 전체 조회."""
        try:
            with _connect() as conn:
                rows = conn.execute("SELECT key, value FROM persona").fetchall()
                return {r["key"]: r["value"] for r in rows}
        except Exception:
            return {"name": "자메스", "style": "", "language": "한국어"}

    def set_persona(self, key: str, value: str) -> bool:
        """Persona 항목 설정 (admin 전용)."""
        try:
            now = datetime.now().isoformat()
            with _connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO persona (key, value, updated_at) VALUES (?,?,?)",
                    (key, value, now)
                )
            print(f"[MEMORY_STORE] persona 설정: {key}={value[:50]}")
            return True
        except Exception as e:
            print(f"[MEMORY_STORE] persona 설정 실패: {e}")
            return False

    def get_system_prompt(self) -> str:
        """
        LLM 프롬프트 앞에 주입할 System Persona.

        [P4 unified UX 2026-05-10] persona.style / persona.custom 자유텍스트는
        🎭 성향 캐릭터 페이지의 radar 와 의미적으로 충돌하여 P3 에서 UI 제거,
        P4 에서 LLM 프롬프트 주입까지 끊는다. 성격 관련 directives 는
        core/character_profile.get_prompt_modifiers() 가 단독 책임 (engine.py
        가 system_prompt 에 별도 라인으로 추가) — 단일 진실 공급원(SSOT) 유지.

        남은 필드:
          - name     : LLM 자기소개용 이름
          - language : 항상 X로 답변하라 directive
          - greeting : (선택) 첫 인삿말 — 향후 P4 후속에서 expression metadata
                       구조로 정식 지원 가능

        주의: DB 의 기존 persona.style / persona.custom row 는 의도적으로
        삭제하지 않는다. 사용자가 P3 이전 입력한 값이므로 — 보존하되
        LLM 으로의 경로만 끊음. 별도 cleanup 은 사용자가 admin UI 또는
        SQL 로 명시적으로 수행.
        """
        persona = self.get_persona()
        name    = persona.get("name", "자메스")
        lang    = persona.get("language", "한국어")

        lines = [f"당신의 이름은 {name}입니다."]
        if lang:
            lines.append(f"항상 {lang}로 답변하세요.")

        if not _PERSONA_DEPRECATION_LOGGED["done"] and (
            persona.get("style") or persona.get("custom")
        ):
            # [Windows cp949 안전] 이모지 사용 금지 — 콘솔 인코딩 크래시.
            print("[PERSONA] (deprecated) persona.style / persona.custom 은 더 "
                  "이상 LLM 프롬프트에 주입되지 않습니다. 성향은 [성향 캐릭터] "
                  "페이지의 radar 로 조정하세요.")
            _PERSONA_DEPRECATION_LOGGED["done"] = True

        return " ".join(lines)

    # ─── 대화 히스토리 (위임: core.memory.conversation) ─────────

    def save_turn(self, session_id: str, question: str,
                  answer: str, mode: str = "") -> bool:
        return _conv_save_turn(session_id, question, answer, mode)

    def get_recent_turns(self, session_id: str = "", limit: int = 10) -> list:
        return _conv_get_recent_turns(session_id, limit)

    def get_history_context(self, session_id: str = "", limit: int = 5) -> str:
        return _conv_get_history_context(session_id, limit)

    def get_all_sessions(self) -> list:
        return _conv_get_all_sessions()

    def set_session_name(self, session_id: str, name: str) -> bool:
        return _conv_set_session_name(session_id, name)

    def delete_session(self, session_id: str) -> bool:
        return _conv_delete_session(session_id)

    # ─── 장기 기억 (위임: core.memory.summaries) ────────────────

    def save_session_summary(self, session_id: str,
                             summary: str, topic: str = "") -> bool:
        return _sum_save_session_summary(session_id, summary, topic)

    def get_session_summaries(self, limit: int = 5) -> list:
        return _sum_get_session_summaries(limit)

    def get_long_term_context(self, current_session_id: str = "",
                               limit: int = 3) -> str:
        return _sum_get_long_term_context(current_session_id, limit)

    # ─── 통계 ───────────────────────────────────────────────

    def get_stats(self) -> dict:
        try:
            with _connect() as conn:
                conv_count = conn.execute(
                    "SELECT COUNT(*)/2 FROM conversation_history"
                ).fetchone()[0]
                summary_count = conn.execute(
                    "SELECT COUNT(*) FROM preferences "
                    "WHERE key LIKE 'session_summary:%'"
                ).fetchone()[0]
                return {
                    "preferences":    conn.execute("SELECT COUNT(*) FROM preferences WHERE key NOT LIKE 'session_summary:%'").fetchone()[0],
                    "patterns":       conn.execute("SELECT COUNT(*) FROM patterns").fetchone()[0],
                    "goals":          conn.execute("SELECT COUNT(*) FROM goals").fetchone()[0],
                    "conversations":  conv_count,
                    "session_summaries": summary_count,
                    "db_path":        DB_PATH,
                }
        except Exception:
            return {"preferences":0,"patterns":0,"goals":0,"conversations":0,"session_summaries":0}
