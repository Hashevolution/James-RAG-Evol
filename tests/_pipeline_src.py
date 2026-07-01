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
        pipeline_query_expansion,
        pipeline_synth,
    )
    # pipeline_synth.py became the pipeline_synth/ package in the v0.6
    # module-size splits (#900-#904). ``inspect.getsource`` on a package
    # returns only its ``__init__.py``, which dropped generator.py /
    # softener.py / result.py from this concatenation and silently
    # broke the structural greps that depend on them — include the
    # submodules explicitly.
    from core.reasoning.pipeline_synth import generator, result, softener
    return (
        inspect.getsource(pipeline)
        + "\n"
        + inspect.getsource(pipeline_context)
        + "\n"
        + inspect.getsource(pipeline_loops)
        + "\n"
        + inspect.getsource(pipeline_query_expansion)
        + "\n"
        + inspect.getsource(pipeline_synth)
        + "\n"
        + inspect.getsource(generator)
        + "\n"
        + inspect.getsource(result)
        + "\n"
        + inspect.getsource(softener)
    )


def engine_source() -> str:
    """Concatenated source of the four modules that together implement
    ``ReasoningEngine.query``. Use instead of
    ``inspect.getsource(engine)`` when the symbol you're grepping for
    may live in the memory-context block, the mode/model routing block
    (split out 2026-07-01), or the canonical RAG synth.
    """
    from core.reasoning import (
        engine,
        engine_memory,
        engine_routing,
        engine_synth,
    )
    return (
        inspect.getsource(engine)
        + "\n"
        + inspect.getsource(engine_memory)
        + "\n"
        + inspect.getsource(engine_routing)
        + "\n"
        + inspect.getsource(engine_synth)
    )


__all__ = ["pipeline_source", "engine_source"]
