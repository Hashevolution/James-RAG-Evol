"""Singleton getters for FastAPI router modules.

Pattern: server_llmwiki.py creates singletons at boot (rag_engine,
file_processor, _rate_limiter) then calls set_* to register them.
Router modules import the corresponding get_* and call inside handlers.

This decouples routers from server_llmwiki.py — no circular imports —
while keeping the boot order explicit (set_* must precede include_router).
Per the v0.4.x server-split design memo §3.1.
"""
from typing import Any

_rag_engine: Any = None
_file_processor: Any = None
_rate_limiter: Any = None


def set_rag_engine(engine) -> None:
    global _rag_engine
    _rag_engine = engine


def set_file_processor(fp) -> None:
    global _file_processor
    _file_processor = fp


def set_rate_limiter(rl) -> None:
    global _rate_limiter
    _rate_limiter = rl


def get_rag_engine():
    if _rag_engine is None:
        raise RuntimeError(
            "rag_engine not initialized — server boot order violation. "
            "server_llmwiki.py must call set_rag_engine() before include_router()."
        )
    return _rag_engine


def get_file_processor():
    if _file_processor is None:
        raise RuntimeError(
            "file_processor not initialized — server boot order violation."
        )
    return _file_processor


def get_rate_limiter():
    if _rate_limiter is None:
        raise RuntimeError(
            "_rate_limiter not initialized — server boot order violation."
        )
    return _rate_limiter
