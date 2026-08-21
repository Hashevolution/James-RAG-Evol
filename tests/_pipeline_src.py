"""Shared helpers for tests that grep reasoning-module source.

After the chore splits:

  * ``pipeline.py`` extracted Loop 0/1/2 step bodies to
    ``pipeline_loops.py``, the LLM answer-generation block to
    ``pipeline_synth.py``, the post-loop context combine +
    sources-header block to ``pipeline_context.py``, and the
    F9.3 entity-anchor STEP 0.5a block to
    ``pipeline_query_expansion.py``.
  * ``engine.py`` extracted the memory-context assembly to
    ``engine_memory.py`` and the canonical RAG synth to
    ``engine_synth.py``.

Structural tests that previously did

    src = inspect.getsource(pipeline_mod)
    src = inspect.getsource(engine_mod)

now need to inspect the split companions too so an assertion like
``assertIn("if hist_ctx:", src)`` still finds the symbol it depends on.

Usage:

    from tests._pipeline_src import pipeline_source, engine_source
    src = pipeline_source()
    self.assertIn("low_relevance", src)

    src = engine_source()
    self.assertIn("if hist_ctx:", src)
"""
from __future__ import annotations

import importlib
import inspect
from pathlib import Path


def _module_source(mod) -> str:
    """Full source of ``mod``, including every submodule if it is a package.

    [2026-08-21] ``pipeline_synth`` grew past the 20 KB module-size gate
    (CLAUDE.md rule 5) and was split into a package
    (``generator`` / ``softener`` / ``result``).
    ``inspect.getsource()`` on a package returns only its
    ``__init__.py``, so every structural assertion that greps for a
    symbol living in the split-out body silently started failing —
    reporting a feature as deleted when it had only moved. Walk the
    package instead, so the next split is absorbed the same way.
    """
    src = inspect.getsource(mod)
    if not hasattr(mod, "__path__"):
        return src
    parts = [src]
    for path in sorted(Path(mod.__file__).parent.glob("*.py")):
        if path.stem == "__init__":
            continue
        parts.append(
            inspect.getsource(
                importlib.import_module(f"{mod.__name__}.{path.stem}")))
    return "\n".join(parts)


def pipeline_source() -> str:
    """Concatenated source of the four modules that together implement
    ``run_retrieval_pipeline``. Use instead of
    ``inspect.getsource(pipeline)`` when the symbol you're grepping for
    may live in any of them.
    """
    from core.reasoning import (
        pipeline,
        pipeline_context,
        pipeline_loops,
        pipeline_query_expansion,
        pipeline_synth,
    )
    return "\n".join(_module_source(m) for m in (
        pipeline,
        pipeline_context,
        pipeline_loops,
        pipeline_query_expansion,
        pipeline_synth,
    ))


def engine_source() -> str:
    """Concatenated source of the three modules that together implement
    ``ReasoningEngine.query``. Use instead of
    ``inspect.getsource(engine)`` when the symbol you're grepping for
    may live in the memory-context block or the canonical RAG synth.
    """
    from core.reasoning import engine, engine_memory, engine_synth
    return "\n".join(
        _module_source(m) for m in (engine, engine_memory, engine_synth))


__all__ = ["pipeline_source", "engine_source"]
