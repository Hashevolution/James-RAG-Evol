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

    def resolve_pending_relations(self):
        # Phase 2 back-fill sweep — no-op in the unit test (no entity index).
        return 0


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

    def test_added_relation_materialised(self):
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
        added = {r["target"] for r in out["added"]}
        self.assertIn("Delta", added)
        # Phase 2 DOES add it to the frontmatter graph as a MANUAL edge.
        fm, _ = _read_frontmatter(path)
        delta = {r["target"]: r for r in fm["relations"]}.get("Delta")
        self.assertIsNotNone(delta)
        self.assertEqual(delta["status"]["active"], True)
        self.assertEqual(delta["sources"][0]["role"], "manual")

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


class _InboundStubGen:
    """Stub with an entity index so the inverse-edge sweep can resolve the
    target entity file. _llm_extract returns NO relations → Alpha→Beta is
    invalidated, which must also invalidate the inverse Beta→Alpha."""
    def __init__(self, entity_id_index, entity_path):
        self.entity_id_index = entity_id_index
        self.entity_path = entity_path

    def _llm_extract_document_entities(self, name, body, meta):
        return {"entities": [], "relations": []}   # nothing survives

    def resolve_pending_relations(self):
        return 0


A_MD = """---
name: Alpha
type: concept
relations:
  - target: Beta
    target_id: e_concept_bbbb000001
    label: 관련
    status: {active: true}
    mutation_type: active
---
Alpha body (the Beta link is no longer stated here).
"""

B_MD = """---
name: Beta
type: concept
relations:
  - target: Alpha
    target_id: e_concept_aaaa000001
    label: 관련
    status: {active: true}
    mutation_type: active
---
Beta body.
"""


class InboundT6Tests(unittest.TestCase):
    """Phase 3 — invalidating A→B must also invalidate the inverse B→A on
    the target entity (bidirectional graph consistency)."""
    def setUp(self):
        os.environ.pop("JAMES_DISABLE_EDIT_CASCADE", None)
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def test_inverse_edge_invalidated_on_target(self):
        a = self.tmp / "Alpha.md"; a.write_text(A_MD, encoding="utf-8")
        b = self.tmp / "Beta.md";  b.write_text(B_MD, encoding="utf-8")
        gen = _InboundStubGen({"e_concept_bbbb000001": str(b)}, self.tmp)

        out = cascade_modify_entity(a, "Alpha", wiki_generator=gen)
        self.assertTrue(out["ok"])
        # A→Beta invalidated on Alpha
        self.assertIn("Beta", {r["target"] for r in out["invalidated"]})
        # inverse Beta→Alpha invalidated on Beta (Phase 3)
        self.assertTrue(out["inverse_invalidated"])
        fmb, _ = _read_frontmatter(b)
        beta_to_alpha = {r["target"]: r for r in fmb["relations"]}["Alpha"]
        self.assertFalse(beta_to_alpha["status"]["active"])
        self.assertEqual(beta_to_alpha["mutation_type"], "invalidated")


if __name__ == "__main__":
    unittest.main()
