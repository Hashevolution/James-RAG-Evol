"""Entity-edit lifecycle cascade (Phase 1) — invalidate stale relations.

When a wiki entity's content is edited so a relation it asserted is no
longer supported, cascade_modify_entity must mark that frontmatter
relation inactive (preserved, not deleted) so graph reasoning stops
citing it — while leaving still-supported relations active.

Design: docs/design/v0.6.1-entity-edit-cascade.md.
Run: python -m unittest tests.test_entity_edit_cascade
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.cascade import cascade_modify_entity
from core.cascade._helpers import _read_frontmatter


ENTITY_MD = """---
name: Alpha
type: concept
relations:
  - target: Beta
    label: 관련
  - target: Gamma
    label: 포함
---
Alpha is related to Beta. (the Gamma link has been removed from this text)
"""


class _StubGen:
    """Stub wiki_generator: returns a fixed extraction. Only Alpha→Beta
    survives; Alpha→Gamma is gone."""
    def __init__(self, relations, raise_on_call=False):
        self._relations = relations
        self._raise = raise_on_call

    def _llm_extract_document_entities(self, name, body, meta):
        if self._raise:
            raise RuntimeError("extractor down")
        return {"entities": [], "relations": self._relations}


def _write(tmp: Path, text: str) -> Path:
    p = tmp / "Alpha.md"
    p.write_text(text, encoding="utf-8")
    return p


class CascadeInvalidateTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("JAMES_DISABLE_EDIT_CASCADE", None)
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_stale_relation_invalidated_supported_kept(self):
        path = _write(self.tmp, ENTITY_MD)
        gen = _StubGen([{"source": "Alpha", "target": "Beta", "label": "관련"}])
        out = cascade_modify_entity(path, "Alpha", wiki_generator=gen)
        self.assertTrue(out["ok"])
        self.assertTrue(out["extracted"])
        # Gamma/포함 dropped → invalidated; Beta/관련 kept.
        inv_targets = {r["target"] for r in out["invalidated"]}
        self.assertIn("Gamma", inv_targets)
        self.assertNotIn("Beta", inv_targets)
        # frontmatter reflects it: Gamma inactive, Beta active.
        fm, _body = _read_frontmatter(path)
        rels = {r["target"]: r for r in fm["relations"]}
        self.assertFalse(rels["Gamma"]["status"]["active"])
        self.assertEqual(rels["Gamma"]["mutation_type"], "invalidated")
        self.assertNotEqual(rels["Beta"].get("status", {}).get("active"), False)

    def test_added_relation_detected_not_materialised(self):
        path = _write(self.tmp, ENTITY_MD)
        # new text now also asserts Alpha→Delta (not in frontmatter)
        gen = _StubGen([
            {"source": "Alpha", "target": "Beta", "label": "관련"},
            {"source": "Alpha", "target": "Gamma", "label": "포함"},
            {"source": "Alpha", "target": "Delta", "label": "관련"},
        ])
        out = cascade_modify_entity(path, "Alpha", wiki_generator=gen)
        self.assertTrue(out["ok"])
        self.assertEqual(out["invalidated"], [])  # all kept
        added = {r["target"] for r in out["added_detected"]}
        self.assertIn("Delta", added)
        # Phase 1 does NOT add it to the frontmatter graph.
        fm, _ = _read_frontmatter(path)
        self.assertNotIn("Delta", {r["target"] for r in fm["relations"]})

    def test_extractor_failure_is_safe_noop(self):
        path = _write(self.tmp, ENTITY_MD)
        before = path.read_text(encoding="utf-8")
        gen = _StubGen([], raise_on_call=True)
        out = cascade_modify_entity(path, "Alpha", wiki_generator=gen)
        self.assertFalse(out["ok"])
        self.assertIn("extract_failed", out["skipped_reason"])
        self.assertEqual(path.read_text(encoding="utf-8"), before)  # untouched

    def test_kill_switch_skips(self):
        os.environ["JAMES_DISABLE_EDIT_CASCADE"] = "1"
        try:
            path = _write(self.tmp, ENTITY_MD)
            before = path.read_text(encoding="utf-8")
            gen = _StubGen([{"source": "Alpha", "target": "Beta", "label": "관련"}])
            out = cascade_modify_entity(path, "Alpha", wiki_generator=gen)
            self.assertFalse(out["ok"])
            self.assertEqual(out["skipped_reason"], "disabled")
            self.assertEqual(path.read_text(encoding="utf-8"), before)
        finally:
            os.environ.pop("JAMES_DISABLE_EDIT_CASCADE", None)


if __name__ == "__main__":
    unittest.main()
