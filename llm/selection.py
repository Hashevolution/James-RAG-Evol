"""
PROJECT JAMES — LLM model selection persistence (Issue #15).

Issue #13 (router 통합) made every production call site declare its
``task_type``. This module is the half that closes the loop: a small
JSON file at ``workspace/llm_selection.json`` maps ``task_type ->
model_name``, so the admin can pick which model handles ``classify``,
``extract``, ``general``, ``coding``, ``vision`` independently —
without editing ``.env`` and restarting.

Resolution order at call time:
  1. ``llm.selection.get_model_for_task(task_type)`` if mapped
  2. otherwise, the provider's default (currently
     ``config.GEMMA_MODEL`` for the Ollama backend)

The selection file is operator data — kept out of git via the
existing ``workspace/`` gitignore. In-process cache reloads from
disk only on ``clear_cache()`` (called by the admin endpoint after a
write, so other in-flight calls keep working without a server
restart).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict, Optional

_ROOT           = Path(__file__).resolve().parent.parent
SELECTION_FILE  = _ROOT / "workspace" / "llm_selection.json"

_lock: threading.Lock = threading.Lock()
_cache: Optional[Dict[str, str]] = None


def _load_locked() -> Dict[str, str]:
    """Read selection from disk into the cache (caller holds the lock)."""
    global _cache
    if _cache is not None:
        return _cache
    if SELECTION_FILE.exists():
        try:
            data = json.loads(SELECTION_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
    else:
        data = {}
    _cache = {str(k): str(v) for k, v in data.items() if v}
    return _cache


def get_model_for_task(task_type: str) -> Optional[str]:
    """Return the operator-selected model for ``task_type``, or None."""
    if not task_type:
        return None
    with _lock:
        sel = _load_locked()
        return sel.get(task_type)


def set_model_for_task(task_type: str, model: str) -> None:
    """Persist ``task_type -> model`` and refresh in-process cache."""
    if not task_type or not model:
        raise ValueError("task_type and model must both be non-empty")
    with _lock:
        sel = _load_locked()
        sel[task_type] = model
        SELECTION_FILE.parent.mkdir(parents=True, exist_ok=True)
        SELECTION_FILE.write_text(
            json.dumps(sel, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def remove_model_for_task(task_type: str) -> bool:
    """Remove a per-task selection. Returns True if a row was removed."""
    with _lock:
        sel = _load_locked()
        if task_type not in sel:
            return False
        del sel[task_type]
        SELECTION_FILE.parent.mkdir(parents=True, exist_ok=True)
        SELECTION_FILE.write_text(
            json.dumps(sel, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True


def get_all_selections() -> Dict[str, str]:
    """Return a snapshot copy of the current task -> model map."""
    with _lock:
        return dict(_load_locked())


def clear_cache() -> None:
    """Drop the in-process cache; next call re-reads from disk.
    Useful in tests or when the file has been edited externally."""
    global _cache
    with _lock:
        _cache = None
