"""Phase 1 of the JSONL → SQLite audit migration.

The legacy ``/admin/audit`` endpoint multiplexes four JSONL streams
(james_audit_db / james_audit_tool / james_attack_log / james_system_log).
``/admin/audit/list`` only reads the SQLite ``audit_log`` table, so tool
calls — written by ``tools/router.py`` and ``tools/code/*.py`` — are
invisible to the new admin UI today.

This module is the **bridge**: each tool-side writer keeps its JSONL
write (rollback path stays trivial — delete one line) and adds one
``mirror_to_audit_db(entry)`` call. The bridge normalises the freeform
JSONL dict into a row that matches the existing ``audit_log`` schema:

    audit_log(
        id, timestamp, user_role, endpoint, query, answer,
        graph_paths, blocked, security_event, elapsed_sec, ip_address
    )

Mapping
-------
    timestamp       ← entry["time"]                 (fallback: now())
    user_role       ← entry["role"]                 (fallback: "unknown")
    endpoint        ← "tool:{layer}:{event}"        — Phase 3 filters
                                                     by ``LIKE 'tool:%'``
    query           ← tool_used + target identifier
    answer          ← compact JSON of leftover keys (cap_*, admin_override,
                      protected_block, sandbox_block, detail, operation,
                      analysis_type, lines, success, …)
    blocked         ← 1 if entry["blocked"] truthy else 0
    security_event  ← entry["event"]
    elapsed_sec     ← entry["exec_time_sec"] or entry["elapsed_sec"]
    ip_address      ← NULL  (tool layer has no HTTP request context)

Non-goals
---------
* Schema migration. The bridge writes to today's schema as-is.
* Silencing the JSONL writers. Phase 4 removes them once the operator
  has confirmed coverage in /admin/audit/list.
* Strict typing. Different writers contribute slightly different dicts;
  the bridge is permissive on missing/extra keys and never raises.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, Optional

try:
    from config import BASE_DIR as _BASE_DIR
    _DEFAULT_AUDIT_DB = os.path.join(_BASE_DIR, "james_audit.db")
except ImportError:
    _DEFAULT_AUDIT_DB = "james_audit.db"


# Keys that map to dedicated columns — anything else gets packed into the
# ``answer`` JSON blob so no signal is lost.
_RESERVED_KEYS = {
    "time", "role", "layer", "event", "blocked",
    "exec_time_sec", "elapsed_sec",
    # Identifier-ish fields are folded into ``query`` so the audit list
    # UI's free-text search hits them directly.
    "tool_used", "target_file", "path", "target",
}


def _resolve_query(entry: Dict[str, Any]) -> str:
    """Build a short, searchable identifier for the row.

    Format: ``"<tool>: <target>"`` when both are present; otherwise
    whichever field is. Empty string when neither — the row still
    has security_event + endpoint so it's not orphaned.
    """
    tool = entry.get("tool_used")
    target = (
        entry.get("target_file")
        or entry.get("path")
        or entry.get("target")
        or ""
    )
    if tool and target:
        return f"{tool}: {target}"
    return str(tool or target or "")


def _resolve_endpoint(entry: Dict[str, Any]) -> str:
    """Synthesise a category-friendly endpoint.

    ``tool:<layer>:<event>`` — e.g. ``tool:router:TOOL_EXECUTED``,
    ``tool:code_reader:FILE_READ``. Phase 3 of the migration adds a
    category ``tools`` to ``/admin/audit/list`` that filters on
    ``endpoint LIKE 'tool:%'``; this prefix is the join point.
    """
    layer = entry.get("layer") or "tool"
    event = entry.get("event") or "EVENT"
    return f"tool:{layer}:{event}"


def _resolve_elapsed(entry: Dict[str, Any]) -> Optional[float]:
    v = entry.get("exec_time_sec")
    if v is None:
        v = entry.get("elapsed_sec")
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _resolve_answer(entry: Dict[str, Any]) -> Optional[str]:
    extras = {
        k: v for k, v in entry.items()
        if k not in _RESERVED_KEYS and v not in (None, "", False)
    }
    if not extras:
        return None
    try:
        return json.dumps(extras, ensure_ascii=False, default=str)
    except Exception:
        return None


def mirror_to_audit_db(entry: Dict[str, Any],
                       *,
                       db_path: Optional[str] = None) -> bool:
    """Mirror a JSONL-style audit dict to the SQLite ``audit_log`` table.

    Returns True on insert, False on any failure. **Never raises** —
    audit mirroring must not block the calling tool path.

    ``db_path`` override exists for tests; production callers omit it
    so the module-level resolved path is used.
    """
    if not isinstance(entry, dict):
        return False
    path = db_path or _DEFAULT_AUDIT_DB
    try:
        ts        = entry.get("time") or datetime.now().isoformat()
        user_role = entry.get("role") or "unknown"
        endpoint  = _resolve_endpoint(entry)
        query     = _resolve_query(entry)
        answer    = _resolve_answer(entry)
        blocked   = 1 if entry.get("blocked") else 0
        sec_event = entry.get("event")
        elapsed   = _resolve_elapsed(entry)

        conn = sqlite3.connect(path, check_same_thread=False)
        try:
            conn.execute(
                "INSERT INTO audit_log "
                "(timestamp, user_role, endpoint, query, answer, "
                " graph_paths, blocked, security_event, elapsed_sec, "
                " ip_address) "
                "VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, NULL)",
                (ts, user_role, endpoint, query, answer,
                 blocked, sec_event, elapsed),
            )
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception:
        return False
