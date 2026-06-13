"""Safety filter for LLM-extracted entities.

Extracted from the legacy single-file ``core/wiki_generator/_ingestion.py``
during the v0.6 oversize-module split (CLAUDE.md rule #5). Behaviour is
byte-identical; only the location moved.
"""
from __future__ import annotations

from typing import Any

from core.wiki_generator._aliases import (
    _ALLOWED_EXTRACT_TYPES,
    _SAFE_ENTITY_NAME_RE,
)


def is_safe_extracted_entity(ent: Any) -> bool:
    """Schema + 보안 검증. injection-safe + 길이/타입 화이트리스트."""
    if not isinstance(ent, dict):
        return False
    name = ent.get("name", "")
    if not isinstance(name, str):
        return False
    name = name.strip()
    if len(name) < 2 or len(name) > 80:
        return False
    if not _SAFE_ENTITY_NAME_RE.match(name):
        return False
    if ent.get("type") not in _ALLOWED_EXTRACT_TYPES:
        return False
    return True


__all__ = ["is_safe_extracted_entity"]
