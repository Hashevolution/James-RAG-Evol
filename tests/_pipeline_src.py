"""Shared helpers for tests that grep reasoning-module source.

After the chore splits:

  * ``pipeline.py`` extracted Loop 0/1/2 step bodies to
    ``pipeline_loops.py``, the LLM answer-generation block to
    ``pipeline_synth.py``, and the post-loop context combine +
    sources-header block to ``pipeline_context.py``.
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

import inspect


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
        pipeline_synth,
    )
    return (
        inspect.getsource(pipeline)
        + "\n"
        + inspect.getsource(pipeline_context)
        + "\n"
        + inspect.getsource(pipeline_loops)
        + "\n"
        + inspect.getsource(pipeline_synth)
    )


def engine_source() -> str:
    """Concatenated source of the three modules that together implement
    ``ReasoningEngine.query``. Use instead of
    ``inspect.getsource(engine)`` when the symbol you're grepping for
    may live in the memory-context block or the canonical RAG synth.
    """
    from core.reasoning import engine, engine_memory, engine_synth
    return (
        inspect.getsource(engine)
        + "\n"
        + inspect.getsource(engine_memory)
        + "\n"
        + inspect.getsource(engine_synth)
    )


__all__ = ["pipeline_source", "engine_source"]
