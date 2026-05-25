"""D — entity `name` must be stripped of markdown emphasis tokens.

Surfaced 2026-05-24 Stage E.1 live verification: graph node label
showed `web_general_**추 장치 옵션 검토:**` — the `**` markers from
the LLM extractor's bold wrapping leaked all the way through to the
displayed name, the alias set, and (via the underscore-substitution
in `_normalize_name`) the file path / entity_id derivation.

Root cause: `WikiFrontmatterMixin.create_entity_file` accepted
`entity["name"]` verbatim. The LLM (Gemma / Gemini) occasionally
wraps extracted entity names in `**…**` for emphasis, especially on
web-learning paths where the model is summarizing a snippet.

Fix: strip `**`, `*`, `` ` ``, `~` upstream at the entity entry point
so every downstream consumer (`_normalize_name`, alias expansion,
frontmatter write, filename build) sees a clean name.

These tests pin the contract so the regression can't reappear.

Existing stale on-disk entities are out of scope here — a separate
backlog-rename script will sweep them once cross-reference plumbing
is in place.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml


class _MarkdownStripBase(unittest.TestCase):
    """Same fixture as test_wiki_summary_body_sync — isolate WIKI_DIR,
    bypass memory/verify and vector-store side effects so we can drive
    create_entity_file from a clean tmp dir."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.wiki_dir_patcher = patch("config.WIKI_DIR", self.tmp)
        self.wiki_dir_patcher.start()
        import core.wiki_generator as wg_mod
        self._orig_wiki_dir = wg_mod.WIKI_DIR
        wg_mod.WIKI_DIR = self.tmp

        self.verify_patcher = patch(
            "core.memory.verify_before_write",
            return_value=(True, "ok", 0.99),
        )
        self.verify_patcher.start()
        self.vs_patcher = patch("core.vector_store.VectorStore")
        self.vs_patcher.start()
        self.router_patcher = patch("llm.router.RouterWrapper")
        self.router_patcher.start()

        from core.wiki_generator import WikiGenerator
        self.wg = WikiGenerator(source_type="test")

    def tearDown(self):
        self.wiki_dir_patcher.stop()
        self.verify_patcher.stop()
        self.vs_patcher.stop()
        self.router_patcher.stop()
        import core.wiki_generator as wg_mod
        wg_mod.WIKI_DIR = self._orig_wiki_dir

    def _read_fm(self, path: Path):
        raw = path.read_text(encoding="utf-8")
        parts = raw.split("---", 2)
        return yaml.safe_load(parts[1]) if len(parts) >= 3 else {}


class EntityNameMarkdownStripTests(_MarkdownStripBase):

    def test_bold_wrapped_name_stripped_in_frontmatter_and_filename(self):
        """The exact pattern seen in production — LLM wraps a Korean
        entity name in `**…**`. Both the frontmatter display name and
        the on-disk filename must be clean."""
        entity = {
            "name":       "**경쟁사 대비 AMD 기술적 우위**",
            "type":       "concept",
            "attributes": {},
            "relations":  [],
        }
        out = Path(self.wg.create_entity_file(entity, "src.md", ["c1"]))
        fm = self._read_fm(out)
        # Frontmatter name has no `*` markers.
        self.assertEqual(fm["name"], "경쟁사 대비 AMD 기술적 우위")
        self.assertNotIn("*", fm["name"])
        # Filename (= normalized) has no consecutive underscores from the
        # stripped markers — the leading/trailing `**` would have become
        # `__` runs without this fix.
        self.assertNotIn("**", out.name)
        self.assertFalse(out.name.startswith("__"))
        self.assertFalse(out.stem.endswith("__"))

    def test_clean_name_unchanged(self):
        """Regression guard — a name with no markdown should be
        byte-identical after the strip. Underscores in legitimate names
        (e.g. `gpt_4`, `web_general_foo`) must survive untouched."""
        entity = {
            "name":       "엔비디아",
            "type":       "org",
            "attributes": {},
            "relations":  [],
        }
        out = Path(self.wg.create_entity_file(entity, "src.md", ["c1"]))
        fm = self._read_fm(out)
        self.assertEqual(fm["name"], "엔비디아")

    def test_legitimate_underscore_preserved(self):
        """`gpt_4` is a real entity name shape — strip must NOT touch
        underscores. Only `*`, `` ` ``, `~` are emphasis tokens."""
        entity = {
            "name":       "gpt_4",
            "type":       "concept",
            "attributes": {},
            "relations":  [],
        }
        out = Path(self.wg.create_entity_file(entity, "src.md", ["c1"]))
        fm = self._read_fm(out)
        self.assertEqual(fm["name"], "gpt_4")

    def test_mixed_markdown_tokens_stripped(self):
        """Cover the other emphasis tokens the strip handles —
        ``code``, *italic*, ~~strike~~. All collapse to the inner text."""
        entity = {
            "name":       "`Structured` *CoT* ~~v2~~",
            "type":       "concept",
            "attributes": {},
            "relations":  [],
        }
        out = Path(self.wg.create_entity_file(entity, "src.md", ["c1"]))
        fm = self._read_fm(out)
        # All four tokens gone; inner words preserved with their spacing.
        self.assertNotIn("*", fm["name"])
        self.assertNotIn("`", fm["name"])
        self.assertNotIn("~", fm["name"])
        self.assertIn("Structured", fm["name"])
        self.assertIn("CoT", fm["name"])
        self.assertIn("v2", fm["name"])

    def test_all_markdown_falls_back_to_unknown(self):
        """Edge case — if the name is entirely emphasis tokens (`***`),
        strip yields empty, and we fall back to `"unknown"` instead of
        writing a nameless entity."""
        entity = {
            "name":       "***",
            "type":       "concept",
            "attributes": {},
            "relations":  [],
        }
        out = Path(self.wg.create_entity_file(entity, "src.md", ["c1"]))
        fm = self._read_fm(out)
        self.assertEqual(fm["name"], "unknown")


if __name__ == "__main__":
    unittest.main()
