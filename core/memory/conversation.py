"""
PROJECT JAMES — Conversation history operations (split from store.py)

대화 턴 / 세션 목록 / 세션 이름 / 세션 삭제. 모두 모듈 함수로 노출하며
`MemoryStore` 메서드가 위임자(thin delegator) 역할만 한다. CLAUDE.md
rule #5 (module size 20 KB) 충족을 위해 store.py 에서 분리.
"""

from datetime import datetime

from core.memory.db import _connect


def save_turn(session_id: str, question: str,
              answer: str, mode: str = "") -> bool:
    """대화 한 턴(질문+답변) 저장.

    [Axis 6 user feedback, 2026-05-12] per-turn cap widened
    from 500 → 2000 chars. The previous cap chopped long
    Q&A so anaphora ("위와 관련", "이것") in follow-ups lost
    their referent. 2000 chars holds a typical 2-3 paragraph
    response without blowing up the SQLite row size.
    """
    now = datetime.now().isoformat()
    try:
        with _connect() as conn:
            conn.executemany(
                "INSERT INTO conversation_history "
                "(session_id, role, content, mode, created_at) VALUES (?,?,?,?,?)",
                [
                    (session_id, "user",      question[:2000], mode, now),
                    (session_id, "assistant", answer[:2000],   mode, now),
                ]
            )
        return True
    except Exception as e:
        print(f"[MEMORY_STORE] 대화 저장 실패: {e}")
        return False


def get_recent_turns(session_id: str = "", limit: int = 10) -> list:
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


def get_history_context(session_id: str = "", limit: int = 5) -> str:
    """최근 대화를 LLM 주입용 텍스트로 변환.

    [Axis 6 user feedback, 2026-05-12] per-turn slice widened
    from 200 → 800 chars. The previous slice chopped any
    non-trivial answer, so when a user said "위와 관련" the
    LLM only saw the first sentence of the previous reply.
    800 chars is roughly one paragraph — enough to anchor
    anaphora without ballooning the prompt.
    """
    turns = get_recent_turns(session_id, limit)
    if not turns:
        return ""
    lines = ["[이전 대화]"]
    for t in turns:
        role = "User" if t["role"] == "user" else "자메스"
        lines.append(f"{role}: {t['content'][:800]}")
    return "\n".join(lines)


def get_all_sessions() -> list:
    """
    [3-D] 세션 목록 조회 — 이름 + 첫 질문 + 마지막 질문 포함.
    세션 이름은 preferences 테이블의 'session_name:{session_id}' 키에서 조회.
    """
    try:
        with _connect() as conn:
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

                first = conn.execute(
                    "SELECT content FROM conversation_history "
                    "WHERE session_id=? AND role='user' "
                    "ORDER BY created_at ASC LIMIT 1",
                    (sid,)
                ).fetchone()
                info["first_question"] = (
                    first["content"][:50] if first else ""
                )

                last_q = conn.execute(
                    "SELECT content FROM conversation_history "
                    "WHERE session_id=? AND role='user' "
                    "ORDER BY created_at DESC LIMIT 1",
                    (sid,)
                ).fetchone()
                info["last_question"] = (
                    last_q["content"][:50] if last_q else ""
                )

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


def set_session_name(session_id: str, name: str) -> bool:
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


def delete_session(session_id: str) -> bool:
    """
    [3-D] 특정 세션 삭제.
    - conversation_history 삭제
    - session_name 삭제
    - session_summary 삭제
    """
    try:
        with _connect() as conn:
            conn.execute(
                "DELETE FROM conversation_history WHERE session_id=?",
                (session_id,)
            )
            conn.execute(
                "DELETE FROM preferences WHERE key=?",
                (f"session_name:{session_id}",)
            )
            conn.execute(
                "DELETE FROM preferences WHERE key LIKE ?",
                (f"session_summary:{session_id[:12]}%",)
            )
        print(f"[SESSION] 삭제 완료: {session_id[:12]}")
        return True
    except Exception as e:
        print(f"[SESSION] 삭제 실패: {e}")
        return False
