"""Error response identification + system-event logging for the
Gemma client.

Extracted from the legacy single-file ``core/gemma_client.py``
during the v0.6 oversize-module split (CLAUDE.md rule #5). Behaviour
is byte-identical to the pre-split file; only the location moved.

External callers (`routes/evolution.py`, `scripts/recover_gemma_*`,
tests) import these directly:

    from core.gemma_client import ERROR_PREFIXES, is_cacheable_response

The re-export façade in ``core.gemma_client.__init__`` preserves
that import shape so the split is a no-op for callers.
"""
from __future__ import annotations

from datetime import datetime


# ─── 에러 응답 식별자 ────────────────────────────────────────

ERROR_PREFIXES = (
    "[Gemma 응답 없음]",
    "[Gemma 오류]",
    "[Gemma Vision 오류]",
    "[Gemma Vision 응답 없음]",
)


def is_cacheable_response(result: str) -> bool:
    """[CACHE-BUG-FIX] 캐시 저장 가능 여부 판단.
    에러/빈 응답은 캐시 금지.
    """
    if not result or not isinstance(result, str):
        return False
    if result.startswith(ERROR_PREFIXES):
        return False
    if len(result.strip()) < 5:
        return False
    return True


def log_system_event(step: str, detail: str, level: str = "ERROR"):
    """시스템 이벤트 기록"""
    entry = {
        "time":   datetime.now().isoformat(),
        "level":  level,
        "step":   step,
        "detail": str(detail)[:300],
    }
    try:
        from core.audit_bridge import mirror_system_event
        mirror_system_event(entry)
    except Exception:
        pass


__all__ = [
    "ERROR_PREFIXES",
    "is_cacheable_response",
    "log_system_event",
]
