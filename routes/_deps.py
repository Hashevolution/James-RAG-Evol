"""Singleton accessors for FastAPI router modules.

Pattern (v0.4.x server-split): server_llmwiki.py creates rag_engine /
file_processor / _rate_limiter as module-level globals at boot. Router
modules in routes/<domain>.py call ``get_<name>()`` here, which
lazy-forwards to ``server_llmwiki.<name>`` at call time.

The forwarder design (rather than a snapshot taken via set_*) preserves
two important behaviours from before the split:

  - Tests that monkeypatch ``server_llmwiki.rag_engine = stub`` to
    inject a fake engine continue to work transparently — the next
    handler invocation reads the patched attribute.
  - There is exactly one source of truth for each singleton. set_*
    snapshots would create two locations that could drift if an
    operator-on-call swapped one and not the other.

Lazy ``import server_llmwiki`` (inside the getter, not at module
top) avoids the circular import: server_llmwiki imports routes/_helpers
and routes/<domain>, those import routes/_deps; if routes/_deps
imported server_llmwiki at module top, server_llmwiki would still be
mid-import and the attribute wouldn't exist yet.

set_* hooks are kept as no-ops so server_llmwiki's boot-time
``set_rag_engine(rag_engine)`` calls (added in PR-A.0) don't need to
be removed — they're free annotation of intent.
"""
from __future__ import annotations


def set_rag_engine(engine) -> None:
    """Kept for back-compat with PR-A.0 boot code. No-op — get_rag_engine
    forwards lazily to server_llmwiki.rag_engine at call time."""


def set_file_processor(fp) -> None:
    """Kept for back-compat. No-op (see set_rag_engine)."""


def set_rate_limiter(rl) -> None:
    """Kept for back-compat. No-op (see set_rag_engine)."""


def get_rag_engine():
    import server_llmwiki
    return server_llmwiki.rag_engine


def get_file_processor():
    import server_llmwiki
    return server_llmwiki.file_processor


def get_rate_limiter():
    import server_llmwiki
    return server_llmwiki._rate_limiter
