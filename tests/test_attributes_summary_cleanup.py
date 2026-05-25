"""v0.4 Sprint 3 BL-2 — `attributes.summary` legacy field cleanup.

The wiki body builder (`core/wiki_generator/_frontmatter.py`) used
to dump the caller's full `attributes` dict into the frontmatter,
which carried a duplicate `summary` key alongside the canonical
top-level `summary` field. The two were kept in sync by
`_ingestion.py` mirroring the LLM description into both slots.

Two issues with the legacy shape:

  1. A single value lives in two places — drift was already
     observed once (PR #445 / #446 series), where the body
     `## 요약` section disagreed with `attributes.summary` after
     manual edits to the top-level field.
  2. Resync / migration / verification scripts had to handle
     three lookup paths (`summary` / `attributes.summary` /
     body section) on read, three writes on update.

BL-2 cleanup
  - `_ingestion.py` stops populating `attributes["summary"]` —
    the LLM description goes to top-level `summary` only.
  - `_frontmatter.py` strips any caller-passed `attributes.summary`
    before frontmatter dump — defensive, in case a caller still
    passes it.
  - The `_frontmatter.py` *read fallback* (`attributes.get("summary")`)
    stays so legacy wiki files on disk that still carry the
    duplicate remain readable.

Test contract pinned here
  1. `attributes.summary` is NOT written into new wiki frontmatter
     (even when the caller passes it in).
  2. Read fallback still works — caller passing `attributes.summary`
     only still populates the body's `## 요약` section and the
     top-level `summary` field.
  3. Other `attributes` keys (source_document, custom fields)
     survive the strip — only the legacy `summary` duplicate is
     removed.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

import yaml  # noqa: E402


class _Base(unittest.TestCase):
    """Same pattern as test_wiki_summary_body_sync — isolate WIKI_DIR
    and bypass memory/verify/vector-store side effects."""

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

    def _read_body(self, path: Path):
        raw = path.read_text(encoding="utf-8")
        parts = raw.split("---", 2)
        return parts[2] if len(parts) >= 3 else ""


class AttributesSummaryCleanupTests(_Base):

    def test_new_write_does_not_emit_attributes_summary(self):
        """Top-level summary present → no duplicate at
        attributes.summary even if other attributes keys exist."""
        entity = {
            "name":        "엔비디아",
            "type":        "org",
            "summary":     "GPU 제조 기업",
            "attributes":  {"source_document": "doc1.md"},
            "relations":   [],
        }
        out = Path(self.wg.create_entity_file(entity, "doc1.md", ["c1"]))
        fm = self._read_fm(out)
        self.assertEqual(fm["summary"], "GPU 제조 기업",
            "Canonical top-level summary present")
        self.assertIsInstance(fm.get("attributes"), dict)
        self.assertNotIn("summary", fm["attributes"],
            "BL-2 cleanup: attributes.summary must not appear in new "
            "frontmatter. The duplicate was historically a back-compat "
            "shim; new writes converge on the canonical top-level.")
        self.assertIn("source_document", fm["attributes"],
            "Non-summary attributes keys must survive the strip.")

    def test_caller_passed_attributes_summary_is_stripped(self):
        """Defensive: even if a caller still passes
        `attributes.summary` (older code paths that haven't migrated),
        the frontmatter writer strips it. The top-level summary
        falls back to attributes.summary so the value isn't lost."""
        entity = {
            "name":        "엔비디아",
            "type":        "org",
            # no top-level summary — exercises the read fallback
            "attributes":  {
                "summary":         "AI 칩 시장의 주요 기업",
                "source_document": "doc2.md",
            },
            "relations":   [],
        }
        out = Path(self.wg.create_entity_file(entity, "doc2.md", ["c2"]))
        fm = self._read_fm(out)
        body = self._read_body(out)
        # Top-level summary populated from the legacy attributes.summary
        # via the read fallback in _frontmatter.py.
        self.assertEqual(fm["summary"], "AI 칩 시장의 주요 기업",
            "Read fallback must still resolve attributes.summary → "
            "top-level summary so legacy callers don't regress.")
        # But the frontmatter output omits the duplicate.
        self.assertNotIn("summary", fm["attributes"],
            "Even when input carries attributes.summary, output frontmatter "
            "must not (cleanup).")
        # Body section is still populated.
        self.assertIn("## 요약\nAI 칩 시장의 주요 기업\n", body)
        # Non-summary attributes survive.
        self.assertEqual(fm["attributes"].get("source_document"), "doc2.md")

    def test_legacy_disk_files_unaffected(self):
        """The on-disk format for entities written *before* BL-2 still
        carries `attributes.summary`. That's a read-only concern — we
        don't migrate existing files in this PR. Resync scripts in
        scripts/ handle that. This test just sanity-checks that the
        read fallback path is still wired (otherwise existing wiki
        files would suddenly render blank summaries)."""
        # No top-level summary, only attributes.summary — simulates
        # a legacy disk file. Calling create_entity_file with this
        # shape is identical to legacy ingest, and the resulting
        # frontmatter must still surface the value somewhere.
        entity = {
            "name":        "테슬라",
            "type":        "org",
            "attributes":  {"summary": "전기차 제조사"},
            "relations":   [],
        }
        out = Path(self.wg.create_entity_file(entity, "src3.md", ["c3"]))
        fm = self._read_fm(out)
        # Either way, the value reaches top-level summary so downstream
        # readers (resync script, body builder, graph display) work.
        self.assertEqual(fm["summary"], "전기차 제조사")


if __name__ == "__main__":
    unittest.main()
