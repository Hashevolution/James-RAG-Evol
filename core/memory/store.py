"""
PROJECT JAMES — Memory Store (Phase 6 Step 1~3 + Persona)

SQLite 기반 선별적 Memory 저장.
Persona: admin이 설정하는 시스템 이름/성향/방식
"""

import sqlite3
import json
import os
from datetime import datetime
from pathlib import Path

try:
    from config import BASE_DIR
    DB_PATH = os.path.join(BASE_DIR, "memory", "james_memory.db")
except ImportError:
    DB_PATH = "./memory/james_memory.db"

Path(os.path.dirname(DB_PATH)).mkdir(parents=True, exist_ok=True)

# [P4 unified UX 2026-05-10] persona.style / persona.custom 의 LLM 주입은
# P4 에서 끊었지만, DB 에 옛 값이 남아 있으면 사용자에게 1회 알림.
# 매 호출마다 로깅하면 콘솔이 시끄럽기 때문에 모듈 단위 플래그 사용.
_PERSONA_DEPRECATION_LOGGED = {"done": False}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """DB 초기화 — 테이블 생성 (기존 DB에도 안전하게 추가)"""
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS preferences (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                key        TEXT NOT NULL,
                value      TEXT NOT NULL,
                raw        TEXT,
                confidence REAL DEFAULT 0.85,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS patterns (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern    TEXT NOT NULL,
                count      INTEGER DEFAULT 1,
                raw        TEXT,
                confidence REAL DEFAULT 0.80,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS goals (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                goal       TEXT NOT NULL,
                confidence REAL DEFAULT 0.80,
                raw        TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS persona (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS conversation_history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role       TEXT NOT NULL,
                content    TEXT NOT NULL,
                mode       TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_conv_session
                ON conversation_history(session_id, created_at);
        """)
        # 기본 persona 초기화 (없을 때만)
        defaults = [
            ("name",    "자메스"),
            ("style",   "친절하고 보안을 중시하는 AI 어시스턴트"),
            ("language","한국어"),
            ("custom",  ""),
        ]
        for k, v in defaults:
            conn.execute(
                "INSERT OR IGNORE INTO persona (key, value, updated_at) VALUES (?,?,?)",
                (k, v, datetime.now().isoformat())
            )
    print(f"[MEMORY_STORE] DB 초기화: {DB_PATH}")


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
                # Step 1: preferences
                prefs = conn.execute(
                    "SELECT key, value FROM preferences ORDER BY updated_at DESC LIMIT 10"
                ).fetchall()
                if prefs:
                    lines.append("[사용자 설정]")
                    for p in prefs:
                        lines.append(f"  - {p['key']}: {p['value']}")

                # Step 2: patterns (count >= 2)
                patterns = conn.execute(
                    "SELECT pattern FROM patterns WHERE count >= 2 ORDER BY count DESC LIMIT 5"
                ).fetchall()
                if patterns:
                    lines.append("[반복 패턴]")
                    for p in patterns:
                        lines.append(f"  - {p['pattern']}")

                # Step 3: goals (최근 3개)
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

    def get_stats(self) -> dict:
        try:
            with _connect() as conn:
                return {
                    "preferences": conn.execute("SELECT COUNT(*) FROM preferences").fetchone()[0],
                    "patterns":    conn.execute("SELECT COUNT(*) FROM patterns").fetchone()[0],
                    "goals":       conn.execute("SELECT COUNT(*) FROM goals").fetchone()[0],
                    "db_path":     DB_PATH,
                }
        except Exception:
            return {"preferences": 0, "patterns": 0, "goals": 0}

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

        # 옛 row 가 DB 에 남아 있으면 1회 deprecation 경고 (per-process).
        # 빈번한 호출이므로 모듈 변수로 1회만 로깅.
        if not _PERSONA_DEPRECATION_LOGGED["done"] and (
            persona.get("style") or persona.get("custom")
        ):
            # [Windows cp949 안전] 이모지 사용 금지 — 콘솔 인코딩 크래시.
            print("[PERSONA] (deprecated) persona.style / persona.custom 은 더 "
                  "이상 LLM 프롬프트에 주입되지 않습니다. 성향은 [성향 캐릭터] "
                  "페이지의 radar 로 조정하세요.")
            _PERSONA_DEPRECATION_LOGGED["done"] = True

        return " ".join(lines)

    # ─── 대화 히스토리 ──────────────────────────────────────────

    def save_turn(self, session_id: str, question: str,
                  answer: str, mode: str = "") -> bool:
        """대화 한 턴(질문+답변) 저장."""
        now = datetime.now().isoformat()
        try:
            with _connect() as conn:
                conn.executemany(
                    "INSERT INTO conversation_history "
                    "(session_id, role, content, mode, created_at) VALUES (?,?,?,?,?)",
                    [
                        (session_id, "user",      question[:500], mode, now),
                        (session_id, "assistant", answer[:500],   mode, now),
                    ]
                )
            return True
        except Exception as e:
            print(f"[MEMORY_STORE] 대화 저장 실패: {e}")
            return False

    def get_recent_turns(self, session_id: str = "", limit: int = 10) -> list:
        """최근 대화 조회."""
        try:
            with _connect() as conn:
                if session_id:
                    rows = conn.execute(
                        "SELECT role, content, mode, created_at "
                        "FROM conversation_history WHERE session_id=? "
                        "ORDER BY created_at DESC LIMIT ?",
                        (session_id, limit * 2)
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT role, content, mode, created_at "
                        "FROM conversation_history "
                        "ORDER BY created_at DESC LIMIT ?",
                        (limit * 2,)
                    ).fetchall()
                return [dict(r) for r in reversed(rows)]
        except Exception:
            return []

    def get_history_context(self, session_id: str = "", limit: int = 5) -> str:
        """최근 대화를 LLM 주입용 텍스트로 변환."""
        turns = self.get_recent_turns(session_id, limit)
        if not turns:
            return ""
        lines = ["[이전 대화]"]
        for t in turns:
            role = "User" if t["role"] == "user" else "자메스"
            lines.append(f"{role}: {t['content'][:200]}")
        return "\n".join(lines)

    def get_all_sessions(self) -> list:
        """
        [3-D] 세션 목록 조회 — 이름 + 첫 질문 + 마지막 질문 포함.
        세션 이름은 preferences 테이블의 'session_name:{session_id}' 키에서 조회.
        """
        try:
            with _connect() as conn:
                # 세션 기본 정보
                rows = conn.execute(
                    "SELECT session_id, COUNT(*)/2 as turn_count, "
                    "MIN(created_at) as started, MAX(created_at) as last "
                    "FROM conversation_history "
                    "GROUP BY session_id ORDER BY last DESC LIMIT 50"
                ).fetchall()

                sessions = []
                for r in rows:
                    sid = r["session_id"]
                    info = dict(r)

                    # 첫 user 질문
                    first = conn.execute(
                        "SELECT content FROM conversation_history "
                        "WHERE session_id=? AND role='user' "
                        "ORDER BY created_at ASC LIMIT 1",
                        (sid,)
                    ).fetchone()
                    info["first_question"] = (
                        first["content"][:50] if first else ""
                    )

                    # 마지막 user 질문 (현재 주제 파악용)
                    last_q = conn.execute(
                        "SELECT content FROM conversation_history "
                        "WHERE session_id=? AND role='user' "
                        "ORDER BY created_at DESC LIMIT 1",
                        (sid,)
                    ).fetchone()
                    info["last_question"] = (
                        last_q["content"][:50] if last_q else ""
                    )

                    # 사용자 지정 세션 이름
                    name_row = conn.execute(
                        "SELECT value FROM preferences "
                        "WHERE key=? LIMIT 1",
                        (f"session_name:{sid}",)
                    ).fetchone()
                    info["name"] = name_row["value"] if name_row else ""

                    sessions.append(info)

                return sessions
        except Exception as e:
            print(f"[MEMORY] get_all_sessions 실패: {e}")
            return []

    def set_session_name(self, session_id: str, name: str) -> bool:
        """[3-D] 세션에 사용자 지정 이름 부여."""
        if not name or not session_id:
            return False
        now = datetime.now().isoformat()
        try:
            with _connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO preferences "
                    "(key, value, raw, confidence, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (f"session_name:{session_id}", name[:60], "", 1.0, now, now)
                )
            print(f"[SESSION] 이름 설정: {session_id[:12]} → '{name[:30]}'")
            return True
        except Exception as e:
            print(f"[SESSION] 이름 저장 실패: {e}")
            return False

    def delete_session(self, session_id: str) -> bool:
        """
        [3-D] 특정 세션 삭제.
        - conversation_history 삭제
        - session_name 삭제
        - session_summary 삭제
        """
        try:
            with _connect() as conn:
                # 대화 기록 삭제
                conn.execute(
                    "DELETE FROM conversation_history WHERE session_id=?",
                    (session_id,)
                )
                # 세션 이름 삭제
                conn.execute(
                    "DELETE FROM preferences WHERE key=?",
                    (f"session_name:{session_id}",)
                )
                # 세션 요약 삭제
                conn.execute(
                    "DELETE FROM preferences WHERE key LIKE ?",
                    (f"session_summary:{session_id[:12]}%",)
                )
            print(f"[SESSION] 삭제 완료: {session_id[:12]}")
            return True
        except Exception as e:
            print(f"[SESSION] 삭제 실패: {e}")
            return False

    # ─── 장기 기억 (세션 요약) ──────────────────────────────────

    def save_session_summary(self, session_id: str,
                             summary: str, topic: str = "") -> bool:
        """
        세션 대화 요약 저장.
        preferences 테이블에 session_summary:{session_id} 키로 저장.
        → 장기 기억으로 영구 보관.
        """
        now = datetime.now().isoformat()
        key = f"session_summary:{session_id[:12]}"
        val = json.dumps(
            {"summary": summary, "topic": topic,
             "session_id": session_id, "saved_at": now},
            ensure_ascii=False
        )
        try:
            with _connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO preferences "
                    "(key, value, raw, confidence, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (key, summary[:300], val, 0.9, now, now)
                )
            print(f"[MEMORY_STORE] 세션 요약 저장: {key}")
            return True
        except Exception as e:
            print(f"[MEMORY_STORE] 요약 저장 실패: {e}")
            return False

    def get_session_summaries(self, limit: int = 5) -> list:
        """
        최근 세션 요약 목록 조회.
        새 세션 시작 시 이전 대화 맥락으로 주입.
        """
        try:
            with _connect() as conn:
                rows = conn.execute(
                    "SELECT key, value, raw, updated_at FROM preferences "
                    "WHERE key LIKE 'session_summary:%' "
                    "ORDER BY updated_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
                results = []
                for r in rows:
                    try:
                        raw = json.loads(r["raw"] or "{}")
                    except Exception:
                        raw = {}
                    results.append({
                        "key":        r["key"],
                        "summary":    r["value"],
                        "topic":      raw.get("topic", ""),
                        "session_id": raw.get("session_id", ""),
                        "saved_at":   r["updated_at"],
                    })
                return results
        except Exception:
            return []

    def get_long_term_context(self, current_session_id: str = "",
                               limit: int = 3) -> str:
        """
        장기 기억 컨텍스트 생성.
        이전 세션 요약들을 LLM 주입용 텍스트로 변환.
        """
        summaries = self.get_session_summaries(limit)
        # 현재 세션 제외
        summaries = [
            s for s in summaries
            if s.get("session_id", "") != current_session_id
        ]
        if not summaries:
            return ""

        lines = ["[이전 대화 기억]"]
        for s in summaries:
            when = s["saved_at"][:10] if s.get("saved_at") else ""
            topic = f" ({s['topic']})" if s.get("topic") else ""
            lines.append(f"• {when}{topic}: {s['summary'][:150]}")

        return "\n".join(lines)

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
