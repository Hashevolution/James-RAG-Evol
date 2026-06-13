"""Wiki generator — frontmatter, indexing, single-entity write path.

Holds the ``WikiFrontmatterMixin`` (Layers 0–2 in the dependency
graph): instance state via ``__init__``, the entity-id index build,
ID generation, name normalization, frontmatter read, duplicate
detection, and the single-file ``create_entity_file`` writer.

## v0.6 package split (CLAUDE.md rule #5)

This package was a single ``core/wiki_generator/_frontmatter.py``
file (21.4 KB, over the 20 KB cap) until the v0.6 oversize-module
split. The public import surface is byte-identical — every caller
(``core/wiki_generator/__init__.py`` → ``WikiFrontmatterMixin``)
keeps working through this façade.

``WikiFrontmatterMixin`` is composed via MRO from 4 sub-mixins. Each
sub-mixin holds one logical layer of the original file; no method-
name collisions exist so the MRO is documentation-driven (top-down by
layer), not load-bearing:

  * :mod:`core.wiki_generator._frontmatter.init_state` —
    ``WikiInitStateMixin`` (``__init__`` + ``_create_index_template``;
    holds the late-binding ``WIKI_DIR`` import that the test
    monkey-patch pattern depends on)
  * :mod:`core.wiki_generator._frontmatter.id_gen` —
    ``WikiIdGenMixin`` (``_generate_entity_id`` + ``_normalize_name``)
  * :mod:`core.wiki_generator._frontmatter.read` —
    ``WikiReadMixin`` (``_build_entity_id_index``,
    ``refresh_entity_map``, ``_register_entity_id``,
    ``_build_overlap_snapshot``, ``_find_existing_entity_id``,
    ``_read_frontmatter``, ``_default_sensitivity``,
    ``find_duplicate_entities``)
  * :mod:`core.wiki_generator._frontmatter.create` —
    ``WikiCreateMixin`` (``create_entity_file`` — the big one)
"""
from __future__ import annotations

from core.wiki_generator._frontmatter.create import WikiCreateMixin
from core.wiki_generator._frontmatter.id_gen import WikiIdGenMixin
from core.wiki_generator._frontmatter.init_state import WikiInitStateMixin
from core.wiki_generator._frontmatter.read import WikiReadMixin


class WikiFrontmatterMixin(
    WikiCreateMixin,
    WikiReadMixin,
    WikiIdGenMixin,
    WikiInitStateMixin,
):
    """Frontmatter / index / single-entity write mixin.

    MRO (left → right): Create → Read → IdGen → InitState → object.
    No method-name collisions, so the order is documentation-driven
    only.
    """
    pass


__all__ = ["WikiFrontmatterMixin"]
