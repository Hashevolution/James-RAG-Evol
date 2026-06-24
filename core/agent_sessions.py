"""v0.6.1 — Agent chat session persistence.

Server-side store so the agent-chat UI can keep multiple, separate
conversations (each with its own history) that survive a restart and are
auditable — the operator-chosen storage for the UX overhaul.

SQLite in ``james_data.db`` (same DB the rest of v0.6.1 uses). One row
per session; the message history is a JSON array of ``{role, content}``
turns (the same shape the ``/agent/chat/`` endpoint sends/receives).

Public API:

  * :func:`list_sessions` — newest-first summaries (no message bodies).
  * :func:`get_session` — one session incl. messages.
  * :func:`create_session` — new empty session, returns it.
  * :func:`update_session` — set title and/or replace messages.
  * :func:`delete_session` — remove one; returns whether it existed.

Concurrency: short-lived connection per call (mirrors
``core/llm_settings.py``); single-operator admin tool, low frequency.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional

try:
    from config import BASE_DIR
    _DB_PATH = os.path.join(BASE_DIR, "james_data.db")
except ImportError:
    _DB_PATH = "james_data.db"

_MAX_TITLE = 120
_MAX_MESSAGES = 400        # hard cap so one session can't grow unbounded

_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS agent_sessions (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    messages   TEXT NOT NULL,
    msg_count  INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False, timeout=10)
    conn.executescript(_SCHEMA_DDL)
    return conn


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _coerce_messages(messages: Any) -> List[Dict[str, str]]:
    """Validate/normalise an incoming message list. Keeps only
    ``{role, content}`` with string fields; caps the count."""
    out: List[Dict[str, str]] = []
    if not isinstance(messages, list):
        return out
    for m in messages[:_MAX_MESSAGES]:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        content = m.get("content")
        if not isinstance(role, str):
            continue
        if content is None:
            continue
        if not isinstance(content, str):
            # tolerate structured content (e.g. Anthropic tool_use blocks)
            # by JSON-stringifying lists/dicts; drop anything else.
            if not isinstance(content, (list, dict)):
                continue
            try:
                content = json.dumps(content, ensure_ascii=False)
            except Exception:
                continue
        out.append({"role": role, "content": content})
    return out


def list_sessions() -> List[Dict[str, Any]]:
    """Newest-first summaries: ``{id, title, msg_count, updated_at,
    created_at}`` — no message bodies (keeps the list call cheap)."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, title, msg_count, created_at, updated_at "
            "FROM agent_sessions ORDER BY updated_at DESC"
        ).fetchall()
    return [
        {"id": r[0], "title": r[1], "msg_count": r[2],
         "created_at": r[3], "updated_at": r[4]}
        for r in rows
    ]


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Return one session incl. its message list, or ``None``."""
    if not session_id or not isinstance(session_id, str):
        return None
    with _conn() as conn:
        row = conn.execute(
            "SELECT id, title, messages, msg_count, created_at, updated_at "
            "FROM agent_sessions WHERE id = ?", (session_id,)
        ).fetchone()
    if not row:
        return None
    try:
        messages = json.loads(row[2]) or []
    except Exception:
        messages = []
    return {
        "id": row[0], "title": row[1], "messages": messages,
        "msg_count": row[3], "created_at": row[4], "updated_at": row[5],
    }


def create_session(title: Optional[str] = None) -> Dict[str, Any]:
    """Create a new empty session and return it (incl. empty messages)."""
    sid = uuid.uuid4().hex
    title = (title or "새 대화").strip()[:_MAX_TITLE] or "새 대화"
    ts = _now()
    with _conn() as conn:
        conn.execute(
            "INSERT INTO agent_sessions(id, title, messages, msg_count, "
            "created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?)",
            (sid, title, "[]", 0, ts, ts),
        )
        conn.commit()
    return {"id": sid, "title": title, "messages": [],
            "msg_count": 0, "created_at": ts, "updated_at": ts}


def update_session(
    session_id: str,
    *,
    title: Optional[str] = None,
    messages: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """Set ``title`` and/or replace ``messages`` on a session. Returns
    the updated session, or ``None`` if it doesn't exist."""
    existing = get_session(session_id)
    if existing is None:
        return None
    new_title = existing["title"]
    if title is not None:
        new_title = title.strip()[:_MAX_TITLE] or existing["title"]
    new_messages = existing["messages"]
    if messages is not None:
        new_messages = _coerce_messages(messages)
    ts = _now()
    with _conn() as conn:
        conn.execute(
            "UPDATE agent_sessions SET title = ?, messages = ?, "
            "msg_count = ?, updated_at = ? WHERE id = ?",
            (new_title, json.dumps(new_messages, ensure_ascii=False),
             len(new_messages), ts, session_id),
        )
        conn.commit()
    return {"id": session_id, "title": new_title, "messages": new_messages,
            "msg_count": len(new_messages),
            "created_at": existing["created_at"], "updated_at": ts}


def delete_session(session_id: str) -> bool:
    """Delete one session. Returns True if a row was removed."""
    if not session_id or not isinstance(session_id, str):
        return False
    with _conn() as conn:
        cur = conn.execute(
            "DELETE FROM agent_sessions WHERE id = ?", (session_id,))
        conn.commit()
        return cur.rowcount > 0


__all__ = [
    "list_sessions",
    "get_session",
    "create_session",
    "update_session",
    "delete_session",
]
