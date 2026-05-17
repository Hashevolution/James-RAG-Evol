"""Shared helper for tests that grep the run_retrieval_pipeline source.

After the chore split, ``pipeline.py`` extracted Loop 0/1/2 step bodies to
``pipeline_loops.py`` and the LLM answer-generation block to
``pipeline_synth.py``. Structural tests that previously did

    src = inspect.getsource(pipeline_mod)

now need to inspect all three modules so an assertion like ``assertIn(
"default_engine.quarantine", src)`` still finds the symbol it depends on.

Usage:

    from tests._pipeline_src import pipeline_source
    src = pipeline_source()
    self.assertIn("low_relevance", src)
"""
from __future__ import annotations

import inspect


def pipeline_source() -> str:
    """Concatenated source of the three modules that together implement
    ``run_retrieval_pipeline``. Use instead of
    ``inspect.getsource(pipeline)`` when the symbol you're grepping for
    may live in any of the three.
    """
    from core.reasoning import pipeline, pipeline_loops, pipeline_synth
    return (
        inspect.getsource(pipeline)
        + "\n"
        + inspect.getsource(pipeline_loops)
        + "\n"
        + inspect.getsource(pipeline_synth)
    )


__all__ = ["pipeline_source"]
