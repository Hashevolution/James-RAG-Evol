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
    create_entity_file from a clean tmp dir.

    The 4 patches + WikiGenerator instantiation are class-level setup
    (``setUpClass`` / ``tearDownClass``), not per-test. Earlier the
    same work ran in ``setUp`` for every test, costing ~5-10s of
    patch-resolution + lazy-import warm-up on cold CI runners. Under
    pytest-timeout=30s that put the first test's setUp dangerously
    close to the budget; if it tipped over, ``tearDown`` never ran,
    the started patches leaked, and downstream test files imported
    a ``MagicMock`` instead of the real class — visible as e.g.
    ``test_native_done_reason::test_router_wrapper_call_gemma_meta_dispatches_to_call_router_meta``
    failing with *"Expected 'call_router_meta' to be called once.
    Called 0 times."* See PR #582 for the conftest-level mitigation
    (heavy module pre-import) and the partial-fix history.

    Class-level pollution risk: all 5 tests in the subclass share
    one tmp dir and one WikiGenerator instance. Each test creates
    a distinct entity name (`경쟁사 대비 AMD 기술적 우위`,
    `엔비디아`, `gpt_4`, ``Structured CoT v2``, `unknown`) so the
    written ``.md`` files do not collide. Relations are empty across
    all tests, so ``_find_existing_entity_id`` / overlap-snapshot
    paths are not exercised → no cross-test interference via the
    WikiGenerator's internal lookup caches. If a future test adds
    relations or shared names, revisit the per-test isolation.
    """

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
