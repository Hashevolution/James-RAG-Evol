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
# [Cognitive Phase 3 PR-9a, 2026-05-19] session-scoped tier (§5.7.6).
# Wiring lands in PR-9b; this re-export keeps consumers using
# `from core.memory import EpisodicMemory` consistent with the
# MemoryStore / MemoryLoom pattern.
from core.memory.episodic import (
    EpisodicEvent,
    EpisodicMemory,
    KNOWN_STAGES as EPISODIC_STAGES,
    MAX_SUMMARY_CHARS as EPISODIC_MAX_SUMMARY_CHARS,
)

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
    "EpisodicEvent",
    "EpisodicMemory",
    "EPISODIC_STAGES",
    "EPISODIC_MAX_SUMMARY_CHARS",
]
