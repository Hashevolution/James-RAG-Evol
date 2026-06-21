"""Non-RAG mode handlers — package facade.

Pre-split (v0.3.x), all 5 handlers lived in a single 30 KB
``core/reasoning/modes.py``. CLAUDE.md rule #5 (no ``core/`` file
exceeds 20 KB) made that an open piece of debt — the closure handover
(``docs/handovers/v0.3.x-session-2026-05-17-closure.md`` §5) flagged
the split as the natural next chore.

The split is **purely structural**: every handler body is byte-identical
to the pre-split version. The package is shaped so existing call sites
continue to work without modification:

    # engine.py — unchanged after split
    from core.reasoning.modes import (
        handle_chat, handle_meta, handle_wiki_edit,
        handle_self_evolve, handle_coding,
    )

    # tests — `import core.reasoning.modes as md` still gives you
    # md.handle_chat / md.CONTINUITY_DIRECTIVE_KO etc.

Why free functions in submodules instead of methods on a Mixin:
- Composition is more explicit than inheritance for "engine plus side
  capabilities" semantics. The dispatch in query() reads as
  ``return handle_chat(self, ...)`` rather than ``return self.handle_chat(...)``,
  making it visually obvious where the body lives.
- Method-resolution order, mocking, and ``inspect.getsource()`` all stay
  simple — and now ``inspect.getsource(modes.chat)`` returns a tight
  100-line file rather than a 700-line monolith.

Permission gating (admin-only for wiki_edit / self_evolve) lives inside
each handler so the dispatch in query() stays uniform.
"""
from __future__ import annotations

from .chat         import handle_chat
from .meta         import handle_meta
from .wiki_edit    import handle_wiki_edit
from .self_evolve  import handle_self_evolve
from .coding       import handle_coding
from .vision       import handle_vision

# Shared constants (originally module-level in the monolith). Kept in
# ``_common`` so any future handler can re-use them — re-exported here
# for backwards compat with tests that probe
# ``core.reasoning.modes.CONTINUITY_DIRECTIVE_KO`` via hasattr.
from ._common import (
    CONTINUITY_DIRECTIVE_KO,
    CONTINUITY_DIRECTIVE_EN,
)


__all__ = [
    "handle_chat",
    "handle_meta",
    "handle_wiki_edit",
    "handle_self_evolve",
    "handle_coding",
    "handle_vision",
    "CONTINUITY_DIRECTIVE_KO",
    "CONTINUITY_DIRECTIVE_EN",
]
