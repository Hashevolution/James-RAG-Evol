"""Frontmatter read + entity-id index build + search/duplicate detect
+ overlap snapshot + sensitivity default — sub-mixin of
``WikiFrontmatterMixin``.

Extracted from the legacy single-file
``core/wiki_generator/_frontmatter.py`` during the v0.6 oversize-module
split (CLAUDE.md rule #5). Behaviour is byte-identical; only the
location moved.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import yaml


class WikiReadMixin:

    # =========================
    # INDEX BUILD
    # =========================

    def _build_entity_id_index(self):
        self.entity_id_index.clear()

        for t in self.entity_types:
            d = self.entity_path / t
            if not d.exists():
                continue

            for f in d.glob("*.md"):
                fm = self._read_frontmatter(f)
                if fm and fm.get("entity_id"):
                    self.entity_id_index[fm["entity_id"]] = f

        print(f"[INDEX] {len(self.entity_id_index)} entities loaded")

    def refresh_entity_map(self):
        self._build_entity_id_index()

    def _register_entity_id(self, entity_id: str, filepath: Path):
        self.entity_id_index[entity_id] = filepath

    def _build_overlap_snapshot(self):
        """Return `{normalized_name: (canonical_name, entity_id, entity_type)}`
        for every existing wiki entity (any type), aliases included.

        v0.4 Sprint 1 #1 addition — used by ingestion's entity-name
        overlap detection (`_infer_overlap_relations` in `_merge.py`)
        so a newly-ingested event named *"비트코인 spot ETF 11개
        일괄 승인"* automatically gets a RELATED_TO relation to the
        existing "비트코인" concept entity when its normalized name
        appears as a token in the new entity's name.

        First-write-wins: if two entities share a normalized name
        (e.g. one canonical + one alias on a different entity), the
        earlier one in `entity_id_index` iteration order takes
        precedence. Tests pin this — production rarely has the
        collision because aliases that match another canonical name
        would already trip `_find_existing_entity_id` during ingest.
        """
        snapshot = {}
        for eid, filepath in self.entity_id_index.items():
            try:
                fm = self._read_frontmatter(Path(filepath))
            except Exception:
                continue
            if not fm:
                continue
            canonical = fm.get("name", "")
            norm = fm.get("normalized_name", "") or self._normalize_name(canonical)
            etype = fm.get("entity_type", "concept")
            if norm and norm not in snapshot:
                snapshot[norm] = (canonical, eid, etype)
            for alias in fm.get("aliases", []) or []:
                alias_norm = self._normalize_name(alias)
                if alias_norm and alias_norm not in snapshot:
                    snapshot[alias_norm] = (canonical, eid, etype)
        return snapshot

    # =========================
    # ENTITY SEARCH (FIXED)
    # =========================

    def _find_existing_entity_id(
        self,
        name: str,
        entity_type: Optional[str]
    ) -> Optional[str]:

        normalized = self._normalize_name(name)

        # 핵심 FIX: None 대응
        if entity_type:
            search_types = [entity_type]
        else:
            search_types = self.entity_types

        for t in search_types:
            d = self.entity_path / t
            if not d.exists():
                continue

            for f in d.glob("*.md"):
                fm = self._read_frontmatter(f)
                if not fm:
                    continue

                if fm.get("normalized_name") == normalized:
                    return fm.get("entity_id")

                for alias in fm.get("aliases", []):
                    if self._normalize_name(alias) == normalized:
                        return fm.get("entity_id")

        return None

    # =========================
    # FRONTMATTER READ
    # =========================

    def _read_frontmatter(self, path: Path) -> Optional[Dict]:
        try:
            content = path.read_text(encoding="utf-8")
            if not content.startswith("---"):
                return None

            end = content.find("---", 3)
            if end < 0:
                return None

            return yaml.safe_load(content[3:end]) or {}
        except Exception:
            return None

    # =========================
    # SENSITIVITY DEFAULT (ABAC)
    # =========================

    @staticmethod
    def _default_sensitivity(entity_type: str) -> str:
        """entity_type별 기본 민감도 등급 반환"""
        mapping = {
            "person":   "confidential",  # 개인정보 → 기밀
            "org":      "internal",      # 조직정보 → 내부
            "document": "confidential",  # 문서 → 기밀
            "concept":  "public",        # 개념/지식 → 공개
            "event":    "internal",      # 시간 축 사건 → 내부 (PR-11b)
        }
        return mapping.get(entity_type, "internal")

    # =========================
    # DUPLICATE CHECK
    # =========================

    def find_duplicate_entities(self, entity: Dict) -> Optional[str]:

        name = entity.get("name", "")
        normalized = self._normalize_name(name)

        t = entity.get("type", "concept")
        d = self.entity_path / t

        if not d.exists():
            return None

        for f in d.glob("*.md"):
            fm = self._read_frontmatter(f)
            if not fm:
                continue

            if fm.get("normalized_name") == normalized:
                return str(f)

        return None


__all__ = ["WikiReadMixin"]
