"""B-2-A — wiki body `## 요약` section must reflect the entity summary.

Surfaced 2026-05-24 Stage E.1 live verification (B-2 graph): the node
side-panel showed an empty `## 요약` section even though the
frontmatter `summary` field was populated. Root cause: the ingest path
stored the LLM description at `attributes.summary`, but the wiki body
builder only read top-level `summary` / `description`. Result: every
newly-ingested entity had a blank body section on disk.

These tests pin the contract so the regression can't reappear:

1. When the caller passes `attributes.summary`, the body's `## 요약`
   section must contain that value (back-compat for callers that
   haven't been updated to mirror).
2. When the caller passes top-level `summary`, the body must contain
   it (preferred path).
3. Top-level `summary` wins when both are set (canonical).
4. Frontmatter top-level `summary` is *always* populated (even when
   the caller only provided `attributes.summary`) so resync /
   downstream readers have a single source of truth.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml


class _WikiSummaryBodyBase(unittest.TestCase):
    """Same setup pattern as test_event_ingest_emit — isolate WIKI_DIR,
    bypass memory/verify and vector-store side effects so we can drive
    create_entity_file from a clean tmp dir."""

    # Class-level patches + WikiGenerator (sibling of PR #592 canary).
    # See conftest.py docstring + PR #582 / PR #592 history.

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls._patchers = [
            patch("config.WIKI_DIR", cls.tmp),
            patch(
                "core.memory.verify_before_write",
                return_value=(True, "ok", 0.99),
            ),
            patch("core.vector_store.VectorStore"),
            patch("llm.router.RouterWrapper"),
        ]
        for p in cls._patchers:
            p.start()
        import core.wiki_generator as wg_mod
        cls._orig_wiki_dir = wg_mod.WIKI_DIR
        wg_mod.WIKI_DIR = cls.tmp
        from core.wiki_generator import WikiGenerator
        cls.wg = WikiGenerator(source_type="test")

    @classmethod
    def tearDownClass(cls):
        for p in cls._patchers:
            p.stop()
        import core.wiki_generator as wg_mod
        wg_mod.WIKI_DIR = cls._orig_wiki_dir

    def _read(self, path: Path):
        raw = path.read_text(encoding="utf-8")
        parts = raw.split("---", 2)
        fm = yaml.safe_load(parts[1]) if len(parts) >= 3 else {}
        body = parts[2] if len(parts) >= 3 else ""
        return fm, body


class WikiSummaryBodyTests(_WikiSummaryBodyBase):

    def test_attributes_summary_populates_body(self):
        """Legacy caller passing `attributes.summary` only — body must
        still get filled (the bug we just fixed)."""
        entity = {
            "name":        "엔비디아",
            "type":        "org",
            "attributes":  {"summary": "AI 칩 시장의 주요 기업"},
            "relations":   [],
        }
        out = Path(self.wg.create_entity_file(entity, "src.md", ["c1"]))
        fm, body = self._read(out)
        self.assertIn("## 요약\nAI 칩 시장의 주요 기업\n", body)
        # And the canonical top-level summary is populated.
        self.assertEqual(fm["summary"], "AI 칩 시장의 주요 기업")

    def test_top_level_summary_populates_body(self):
        """Updated caller passing top-level `summary` directly."""
        entity = {
            "name":        "엔비디아",
            "type":        "org",
            "summary":     "GPU 제조 기업",
            "attributes":  {},
            "relations":   [],
        }
        out = Path(self.wg.create_entity_file(entity, "src.md", ["c1"]))
        fm, body = self._read(out)
        self.assertIn("## 요약\nGPU 제조 기업\n", body)
        self.assertEqual(fm["summary"], "GPU 제조 기업")

    def test_top_level_wins_when_both_set(self):
        """Disagreement between top-level and attributes — top-level is
        canonical (matches the resync script's resolution order)."""
        entity = {
            "name":        "엔비디아",
            "type":        "org",
            "summary":     "GPU 제조 기업",
            "attributes":  {"summary": "AI 칩 시장의 주요 기업"},
            "relations":   [],
        }
        out = Path(self.wg.create_entity_file(entity, "src.md", ["c1"]))
        fm, body = self._read(out)
        self.assertIn("## 요약\nGPU 제조 기업\n", body)
        self.assertNotIn("AI 칩 시장의 주요 기업", body)
        self.assertEqual(fm["summary"], "GPU 제조 기업")

    def test_no_summary_anywhere_yields_empty_body_section(self):
        """When no summary is supplied at all, the body section is
        present but empty — not crashing, not duplicating, just blank.
        This matches the pre-fix shape for entities ingested without a
        description and keeps the section header stable for the resync
        script's regex window."""
        entity = {
            "name":        "이름만있음",
            "type":        "concept",
            "attributes":  {},
            "relations":   [],
        }
        out = Path(self.wg.create_entity_file(entity, "src.md", ["c1"]))
        _fm, body = self._read(out)
        # Header present + content empty + ## 관계 follows immediately.
        self.assertIn("## 요약\n\n", body)
        self.assertIn("## 관계", body)


if __name__ == "__main__":
    unittest.main()
