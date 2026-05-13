"""
PROJECT JAMES — Session summaries / long-term context (split from store.py)

세션 요약은 `preferences` 테이블에 `session_summary:{session_id}` 키로 저장되어
세션 경계를 넘어 보존되는 장기기억 역할을 한다. CLAUDE.md rule #5
(module size 20 KB) 충족을 위해 store.py 에서 분리.
"""

import json
from datetime import datetime

from core.memory.db import _connect


def save_session_summary(session_id: str,
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


def get_session_summaries(limit: int = 5) -> list:
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


def get_long_term_context(current_session_id: str = "",
                           limit: int = 3) -> str:
    """
    장기 기억 컨텍스트 생성.
    이전 세션 요약들을 LLM 주입용 텍스트로 변환.
    """
    summaries = get_session_summaries(limit)
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
