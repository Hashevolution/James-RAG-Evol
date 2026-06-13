"""Instance state initialiser + index template — sub-mixin of
``WikiFrontmatterMixin``.

Extracted from the legacy single-file
``core/wiki_generator/_frontmatter.py`` during the v0.6 oversize-module
split (CLAUDE.md rule #5). Behaviour is byte-identical to the pre-split
file; only the location moved.

The ``WIKI_DIR`` binding is late-imported from ``core.wiki_generator``
inside ``__init__`` so the test pattern
``import core.wiki_generator as wg_mod; wg_mod.WIKI_DIR = tmp``
keeps working after the Stage C.1 split.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict

from core.relations_schema import ENTITY_TYPES_CORE
from core.vector_store import VectorStore
from llm.router import RouterWrapper
from utils.metadata import MetadataGenerator


class WikiInitStateMixin:

    def __init__(self, source_type: str = "prod"):
        """
        [P4.5-1] source_type 분리
          source_type='prod' → wiki/entity/prod/{type}/
          source_type='test' → wiki/entity/test/{type}/
        """
        # Late-bind WIKI_DIR: tests do ``wg_mod.WIKI_DIR = tmp`` between
        # instantiations, so reading the binding at __init__ time
        # (rather than at module import) is the load-bearing invariant.
        from core.wiki_generator import WIKI_DIR

        self.gemma_client = RouterWrapper("extract")
        self.metadata_gen = MetadataGenerator()
        self.vector_store = VectorStore()

        # [P4.5-1] source_type에 따라 entity 경로 분리
        self.source_type    = source_type if source_type in ("prod", "test") else "prod"
        self.wiki_base_path = Path(WIKI_DIR)
        self.entity_path    = self.wiki_base_path / "entity" / self.source_type

        # ENTITY_TYPES_CORE = 5 types (event 5th, PR-11). LLM extraction
        # prompt below still emits only 3 types (person/org/concept);
        # `document` is post-processor source-attribution; `event` is
        # admin POST path (PR-11a-2). Directory listing / index build /
        # search default to all 5 — empty event/ dir is a no-op until
        # the first admin event creation.
        self.entity_types = list(ENTITY_TYPES_CORE)

        for t in self.entity_types:
            (self.entity_path / t).mkdir(parents=True, exist_ok=True)

        self.index_path = self.wiki_base_path / "index.md"
        if not self.index_path.exists():
            self._create_index_template()

        self.entity_id_index: Dict[str, Path] = {}
        self._build_entity_id_index()

    def _create_index_template(self):
        """index.md 초기 템플릿 생성"""

        content = (
            "---\n"
            f'updated_at: "{datetime.now().isoformat()}"\n'
            "total_entities: 0\n"
            "---\n\n"
            "# 자메스 Wiki Index\n\n"
            "## person (0)\n\n"
            "## concept (0)\n\n"
            "## org (0)\n\n"
            "## document (0)\n\n"
            "## event (0)\n"
        )

        self.index_path.write_text(content, encoding="utf-8")


__all__ = ["WikiInitStateMixin"]
