"""Security layer — audit log helpers.

Thin wrappers around ``core.audit_bridge`` for the two security-side
event streams: attack refusals (prompt-injection + risky-coding) and
internal system events (silent-failure logging, ABAC violations).

Phase 4 (Stage D.1, 2026-05-24) made the SQLite audit_log the sole
sink; the legacy JSONL writers were removed and these helpers now
just build the entry dict and forward it to the bridge.

Split out of the monolithic ``core/security_layer.py`` in Stage C.4
(2026-05-24).
"""
from __future__ import annotations

from datetime import datetime


def log_attack(query: str, role: str, attack_type: str = "injection"):
    """Audit-log an attempted prompt-injection / risky-coding refusal.

    Accessible via ``/admin/audit/list`` with ``endpoint LIKE 'attack:%'``.
    """
    entry = {"time": datetime.now().isoformat(), "role": role,
             "attack_type": attack_type, "query": query[:200]}
    try:
        from core.audit_bridge import mirror_attack_event
        mirror_attack_event(entry, attack_type=attack_type)
    except Exception:
        pass


def log_system_event(step: str, detail: str, role: str = "unknown", level: str = "ERROR"):
    """[LOG-1] Audit-log a system event.

    Accessible via ``/admin/audit/list`` with ``endpoint LIKE 'system:%'``.
    """
    entry = {"time": datetime.now().isoformat(), "level": level,
             "step": step, "detail": str(detail)[:300], "role": role}
    try:
        from core.audit_bridge import mirror_system_event
        mirror_system_event(entry)
    except Exception:
        pass


__all__ = ["log_attack", "log_system_event"]
