"""ID generation + name normalisation — sub-mixin of
``WikiFrontmatterMixin``.

Extracted from the legacy single-file
``core/wiki_generator/_frontmatter.py`` during the v0.6 oversize-module
split (CLAUDE.md rule #5). Behaviour is byte-identical; only the
location moved.
"""
from __future__ import annotations

import hashlib
import re


class WikiIdGenMixin:

    def _generate_entity_id(self, name: str, entity_type: str) -> str:
        normalized = self._normalize_name(name)

        # 보안: SALT 추가
        SALT = "JAMES_SECURE_V1"
        raw = f"{normalized}_{entity_type}_{SALT}"

        # graph_rag_engine 정규식 {8} 일치
        h = hashlib.sha256(raw.encode()).hexdigest()[:8]
        return f"e_{entity_type}_{h}"

    def _normalize_name(self, name: str) -> str:
        return re.sub(r"[^\w가-힣]", "_", name.strip().lower())


__all__ = ["WikiIdGenMixin"]
