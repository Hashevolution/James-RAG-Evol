"""Wiki generator — document → entity LLM ingestion path.

``WikiIngestionMixin`` (Layer 3 in the dependency graph): the
``process_document_for_entities`` orchestrator and its LLM extraction
helper ``_llm_extract_document_entities`` plus the safety filter
``_is_safe_extracted_entity`` (staticmethod, kept on the mixin
because it gates the LLM output before any merge code touches it).

## v0.6 package split (CLAUDE.md rule #5)

This package was a single ``core/wiki_generator/_ingestion.py`` file
(22.5 KB, over the 20 KB cap) until the v0.6 oversize-module split.
The public import surface is byte-identical — every caller
(``core/wiki_generator/__init__.py``,
``tests/test_entity_type_extension.py`` source-text check) keeps
working through this façade:

  * :mod:`core.wiki_generator._ingestion.prompts` — the LLM
    extract prompt builder (carries the 9-type vocabulary the
    ``test_ingest_prompt_lists_9_types`` test source-greps)
  * :mod:`core.wiki_generator._ingestion.safety` — the
    ``is_safe_extracted_entity`` filter (module-level)
  * :mod:`core.wiki_generator._ingestion.llm_extract` — LLM call +
    JSON parse helper (module-level)
  * :mod:`core.wiki_generator._ingestion.mixin` — the
    ``WikiIngestionMixin`` class with the orchestrator + thin
    delegates to the three helpers above
  * this ``__init__.py`` — re-exports the mixin
"""
from __future__ import annotations

from core.wiki_generator._ingestion.mixin import (  # noqa: F401
    WikiIngestionMixin,
)


__all__ = ["WikiIngestionMixin"]
