"""v0.6.1 — LLM routing unified settings repository.

DB-first, env-fallback. The admin UI writes rows here; every existing
call site that used to read an env var now goes through this module so
the operator has *one* place to set the knob, not nine envs across four
dispatch layers.

See ``docs/design/v0.6-llm-routing-unification.md``.

Public API:

  * :func:`get(key, env_name=None, default="")` — DB → env → default.
  * :func:`set(key, value, *, by)` — admin write, audit-logged at call
    site, NOT here (we don't import routes' audit helper to avoid a
    cycle).
  * :func:`as_dict()` — full snapshot, including the env that would
    take over for cleared rows + the documented default. UI uses this.
  * :data:`SETTINGS_SCHEMA` — the fixed key taxonomy (validated by
    :func:`set` and the admin endpoint).

Concurrency: SQLite WAL is fine — single-row writes, low frequency.
The connection is short-lived per call (no app-wide pool) so a
hung-up admin request can't poison the DB handle.
"""
from __future__ import annotations

import os
import sqlite3
import time
from typing import Any, Dict, Optional, Tuple


# ── DB path (mirrors core/data_artifacts.py resolution) ─────────────

try:
    from config import BASE_DIR
    _DB_PATH = os.path.join(BASE_DIR, "james_data.db")
except ImportError:
    _DB_PATH = "james_data.db"


# ── Schema (the fixed taxonomy) ─────────────────────────────────────

# Each entry: (key, env_var_name, default, type_tag)
# type_tag is informational for the admin UI; validation is per-key
# in `_validate`.
SETTINGS_SCHEMA: Tuple[Tuple[str, str, str, str], ...] = (
    # Models
    ("default_model",        "JAMES_LLM_MODEL",             "gemma4:e4b",                       "string"),
    ("coding_model",         "JAMES_CODING_MODEL",          "qwen2.5-coder:32b",                "string"),
    ("vision_model",         "JAMES_VISION_MODEL",          "llava:13b",                        "string"),
    # Auto-routing
    ("auto_router",          "JAMES_AUTO_ROUTER",           "1",                                "bool"),
    ("auto_style",           "JAMES_AUTO_STYLE",            "1",                                "bool"),
    # Backend tier
    ("backend_tier",         "JAMES_BACKEND_TIER",          "local",                            "enum:local,claude,hybrid"),
    ("backend_synth",        "JAMES_BACKEND_SYNTH",         "",                                 "string"),
    # Agent backend (v0.6.1 Phase C, #920)
    ("agent_backend",        "JAMES_AGENT_BACKEND",         "ollama",                           "enum:ollama,anthropic"),
    ("agent_ollama_model",   "JAMES_AGENT_OLLAMA_MODEL",    "mxtral:latest",                    "string"),
    ("agent_anthropic_model","JAMES_AGENT_ANTHROPIC_MODEL", "claude-haiku-4-5-20251001",        "string"),
)

_KEYS = {entry[0]: entry for entry in SETTINGS_SCHEMA}


# ── DB connection + schema bootstrap ────────────────────────────────

_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS llm_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL
);
"""


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False, timeout=10)
    conn.executescript(_SCHEMA_DDL)
    return conn


# ── Validation ──────────────────────────────────────────────────────

def _validate(key: str, value: str) -> str:
    """Return the normalised value or raise ``ValueError``."""
    if key not in _KEYS:
        raise ValueError(f"unknown setting key: {key!r}")
    if not isinstance(value, str):
        raise ValueError(f"value for {key!r} must be a string")
    type_tag = _KEYS[key][3]
    if type_tag == "bool":
        if value not in ("0", "1"):
            raise ValueError(f"{key!r} expects '0' or '1', got {value!r}")
    elif type_tag.startswith("enum:"):
        allowed = type_tag.split(":", 1)[1].split(",")
        if value not in allowed:
            raise ValueError(
                f"{key!r} expects one of {allowed}, got {value!r}"
            )
    # string: any non-empty UTF-8 string with no NUL bytes
    if "\x00" in value:
        raise ValueError(f"{key!r}: NUL byte forbidden")
    if len(value) > 256:
        raise ValueError(f"{key!r}: value too long (>256 chars)")
    return value


# ── Public API ──────────────────────────────────────────────────────

def get(key: str, env_name: Optional[str] = None, default: str = "") -> str:
    """DB → env → default resolution.

    Both ``env_name`` and ``default`` can be omitted when ``key`` is in
    the canonical schema (the schema entry is consulted as a fallback).
    """
    if key in _KEYS:
        schema = _KEYS[key]
        env_name = env_name or schema[1]
        default = default or schema[2]
    try:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT value FROM llm_settings WHERE key = ?", (key,)
            ).fetchone()
        if row and row[0]:
            return row[0]
    except sqlite3.Error:
        # DB unavailable — fall through to env.
        pass
    env_val = os.environ.get(env_name or "", "").strip() if env_name else ""
    if env_val:
        return env_val
    return default


def get_bool(key: str, env_name: Optional[str] = None,
             default: str = "1") -> bool:
    """``get`` with bool coercion. ``"1"`` / ``"true"`` / ``"yes"`` →
    True; everything else → False."""
    raw = get(key, env_name, default).strip().lower()
    return raw in ("1", "true", "yes", "on", "enabled")


def set(key: str, value: str, *, by: str) -> None:  # noqa: A001 — match Python builtin name intentionally
    """Write a single setting. Raises ``ValueError`` on invalid key or
    value. The caller (admin endpoint) is responsible for writing the
    audit_log row; this module stays free of route imports."""
    value = _validate(key, value)
    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO llm_settings(key, value, updated_at, updated_by) "
            "VALUES(?, ?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET "
            "value=excluded.value, updated_at=excluded.updated_at, "
            "updated_by=excluded.updated_by",
            (key, value, ts, by or "admin"),
        )
        conn.commit()


def clear(key: str) -> None:
    """Delete a row so the env fallback takes over again."""
    if key not in _KEYS:
        raise ValueError(f"unknown setting key: {key!r}")
    with _get_conn() as conn:
        conn.execute("DELETE FROM llm_settings WHERE key = ?", (key,))
        conn.commit()


def as_dict() -> Dict[str, Any]:
    """Return the full snapshot the admin UI needs:

      {
        "settings": {key: current_effective_value},
        "db":       {key: db_value or ""},
        "env":      {key: env_value or ""},
        "defaults": {key: documented_default},
        "schema":   [{key, env, default, type}],
      }
    """
    db_rows: Dict[str, str] = {}
    try:
        with _get_conn() as conn:
            for k, v in conn.execute(
                "SELECT key, value FROM llm_settings"
            ).fetchall():
                db_rows[k] = v or ""
    except sqlite3.Error:
        pass

    settings: Dict[str, str] = {}
    env_vals: Dict[str, str] = {}
    defaults: Dict[str, str] = {}
    schema_pub = []
    for key, env_name, default, type_tag in SETTINGS_SCHEMA:
        env_val = os.environ.get(env_name, "").strip()
        env_vals[key] = env_val
        defaults[key] = default
        if db_rows.get(key):
            settings[key] = db_rows[key]
        elif env_val:
            settings[key] = env_val
        else:
            settings[key] = default
        schema_pub.append({
            "key": key, "env": env_name,
            "default": default, "type": type_tag,
        })
    return {
        "settings": settings,
        "db": db_rows,
        "env": env_vals,
        "defaults": defaults,
        "schema": schema_pub,
    }


__all__ = [
    "SETTINGS_SCHEMA",
    "get",
    "get_bool",
    "set",
    "clear",
    "as_dict",
]
