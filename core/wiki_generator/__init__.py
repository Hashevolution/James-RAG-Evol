"""``core.wiki_generator`` — entity wiki ingest, frontmatter, relation merge.

Originally a single 51 KB module; split in Stage C.1 (2026-05-24) into
a mixin-based package to respect CLAUDE.md rule #5 (< 20 KB per file).
The external surface is unchanged::

  from core.wiki_generator import WikiGenerator

The split is purely textual — no semantic change. Same instance attrs,
same method names, same call signatures. The three mixins (Frontmatter
/ Merge / Ingestion) are composed by ``WikiGenerator`` below.

Re-exports the module-level helpers used by callers outside this
package:

- ``_expand_alias_candidates`` — ``scripts/migrate_aliases.py:33``
- ``_ALLOWED_EXTRACT_TYPES`` — ``tests/test_event_ingest_emit.py:342``

``WIKI_DIR`` is imported here at the package level so tests that do
``import core.wiki_generator as wg_mod; wg_mod.WIKI_DIR = tmp`` reach
every sub-module's lazy import. ``_frontmatter.WikiFrontmatterMixin.
__init__`` and ``_aliases._load_synonyms`` both look up ``WIKI_DIR``
via ``from core.wiki_generator import WIKI_DIR`` so the monkey-patch
is visible at call time.
"""
from __future__ import annotations

# `WIKI_DIR` is exposed at this package level so test monkey-patches
# (`wg_mod.WIKI_DIR = ...`) reach every sub-module's lazy import.
from config import WIKI_DIR  # noqa: F401 — re-export for sub-modules

from ._aliases import (
    _ALLOWED_EXTRACT_TYPES,
    _ONTOLOGY_LABELS_KO,
    _PAREN_ALIAS_RE,
    _SAFE_ENTITY_NAME_RE,
    _expand_alias_candidates,
    _load_synonyms,
)
from ._frontmatter import WikiFrontmatterMixin
from ._index_ops import WikiIndexOpsMixin
from ._ingestion import WikiIngestionMixin
from ._merge import WikiMergeMixin


class WikiGenerator(
    WikiIngestionMixin,
    WikiMergeMixin,
    WikiIndexOpsMixin,
    WikiFrontmatterMixin,
):
    """Entity wiki orchestrator. All behaviour delegated to mixins.

    MRO: Ingestion → Merge → IndexOps → Frontmatter → object. Order
    is documentation-driven (top-down by layer); no method-name
    collisions exist so the MRO is not load-bearing.

    Mixin map:

    - ``_frontmatter.py`` — ``__init__``, ID generation, name
      normalization, frontmatter read, single-entity ``create_entity_
      file`` writer, ``find_duplicate_entities``, the entity-id index
      build.
    - ``_index_ops.py`` — wiki-wide sweep operations (``update_index``,
      ``resolve_pending_relations``, ``get_entity_statistics``).
    - ``_merge.py`` — cross-doc relation aggregation
      (``_merge_relations_into_existing_entity``,
      ``_build_entity_relations``, ``_inverse_label_for``).
    - ``_ingestion.py`` — ``process_document_for_entities`` orchestrator
      and the LLM extractor.
    """
    pass


__all__ = [
    "WikiGenerator",
    "WIKI_DIR",
    "_ALLOWED_EXTRACT_TYPES",
    "_ONTOLOGY_LABELS_KO",
    "_PAREN_ALIAS_RE",
    "_SAFE_ENTITY_NAME_RE",
    "_expand_alias_candidates",
    "_load_synonyms",
]
