"""Memory subsystem: persistent store, LLM extraction, trust scoring, long-term consolidation.

Public API re-exports the symbols call sites use across the codebase. Internal
helpers (underscore-prefixed names like `_connect`, `DB_PATH`, `_query_history`)
remain accessible only via deep imports from the submodule, e.g.
`from core.memory.store import _connect`.
"""

from core.memory.store import MemoryStore, DB_PATH
from core.memory.extractor import (
    extract_memory,
    validate_memory,
    is_persona_command,
    extract_persona_command,
)
from core.memory.loom import (
    MemoryLoom,
    store_result,
    MAX_WRITES_PER_SESSION,
    MEMORY_CONFIDENCE_TH,
    MEMORY_DEDUP_WINDOW,
)
from core.memory.trust import verify_before_write

__all__ = [
    "MemoryStore",
    "DB_PATH",
    "extract_memory",
    "validate_memory",
    "is_persona_command",
    "extract_persona_command",
    "MemoryLoom",
    "store_result",
    "MAX_WRITES_PER_SESSION",
    "MEMORY_CONFIDENCE_TH",
    "MEMORY_DEDUP_WINDOW",
    "verify_before_write",
]
