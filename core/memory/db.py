"""
PROJECT JAMES — Memory DB primitives (split from store.py)

SQLite 연결 + 스키마 초기화. CLAUDE.md rule #5 (module size 20 KB) 충족을
위해 store.py 에서 분리. `_connect` / `DB_PATH` 는 store.py 가 re-export 하므로
`from core.memory.store import _connect` 는 변함없이 동작.
"""

import sqlite3
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
