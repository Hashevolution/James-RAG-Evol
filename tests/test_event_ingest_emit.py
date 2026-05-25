"""PR-11b — event entity emit path through WikiGenerator.create_entity_file.

Design memo §5.1: ingest accepts `type: event` but only when the entity
also carries a parseable `occurred_at`. Missing/invalid date triggers a
graceful fallback to `type: concept` rather than refusing the ingest.

This file pins:
  1. happy path — valid occurred_at lands in wiki/entity/test/event/
     with the expected frontmatter (occurred_at, occurred_at_precision,
     entity_id derived from name + date + precision)
  2. graceful fallback — missing/invalid occurred_at downgrades the
     entity_type to concept (file ends up in wiki/entity/test/concept/)
  3. same name on different dates yields distinct ids + coexists
  4. 4-type ingest path unchanged (regression sanity)

setUp mirrors `tests/test_phase_b_ingestion_sources.py` — WIKI_DIR
monkey-patched to tempdir, vector_store / verify_before_write / LLM
router stubbed out so we only exercise the frontmatter writer.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml  # noqa: I001

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


class _EventIngestBase(unittest.TestCase):
    """Common harness — tempdir WIKI_DIR + stubbed vector store / router /
    memory-trust verifier so create_entity_file's side effects are
    isolated to disk."""

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

    def _read_fm(self, path: Path) -> dict:
        text = path.read_text(encoding="utf-8")
        return yaml.safe_load(text.split("---", 2)[1])


# ─── 1. happy path ───────────────────────────────────────────────────


class EventIngestHappyPathTests(_EventIngestBase):

    def test_event_with_occurred_at_lands_in_event_dir(self):
        entity = {
            "name":        "2026 비트코인 ETF 승인",
            "type":        "event",
            "occurred_at": "2026-01-10",
            "attributes":  {"summary": "SEC 첫 spot ETF 승인"},
            "relations":   [],
        }
        out_path = self.wg.create_entity_file(
            entity, "etf_doc.md", ["chunk1"],
        )
        out = Path(out_path)
        # File path under wiki/entity/test/event/...
        self.assertEqual(out.parent.name, "event")
        self.assertTrue(out.exists())

        fm = self._read_fm(out)
        self.assertEqual(fm["entity_type"], "event")
        self.assertEqual(fm["occurred_at"], "2026-01-10")
        self.assertEqual(fm["occurred_at_precision"], "day")
        self.assertTrue(fm["entity_id"].startswith("e_event_"))

    def test_precision_explicit_value_is_preserved(self):
        # Memo §4.1: storage is always full ISO 8601; `precision` is a
        # consumer-side trust hint (year/month/day/hour/minute), not a
        # parse-strictness flag.
        entity = {
            "name":                  "Q1 실적 발표",
            "type":                  "event",
            "occurred_at":           "2026-04-01",
            "occurred_at_precision": "month",
            "attributes":            {},
            "relations":             [],
        }
        out = Path(self.wg.create_entity_file(entity, "ir.md", []))
        fm = self._read_fm(out)
        self.assertEqual(fm["occurred_at_precision"], "month")

    def test_sensitivity_defaults_to_internal_for_events(self):
        entity = {
            "name": "Earnings call", "type": "event",
            "occurred_at": "2026-01-15",
            "attributes": {}, "relations": [],
        }
        out = Path(self.wg.create_entity_file(entity, "x.md", []))
        fm = self._read_fm(out)
        self.assertEqual(fm["sensitivity"], "internal")


# ─── 2. fallback to concept ─────────────────────────────────────────


class EventIngestFallbackTests(_EventIngestBase):

    def test_event_without_occurred_at_falls_back_to_concept(self):
        entity = {
            "name":       "정체 모를 사건",
            "type":       "event",
            "attributes": {"summary": "occurred_at 없음 → concept 으로 강등"},
            "relations":  [],
        }
        out = Path(self.wg.create_entity_file(entity, "x.md", []))
        # Falls to wiki/entity/test/concept/
        self.assertEqual(out.parent.name, "concept")
        fm = self._read_fm(out)
        self.assertEqual(fm["entity_type"], "concept")
        # No occurred_at fields leak into the concept file.
        self.assertNotIn("occurred_at", fm)
        self.assertNotIn("occurred_at_precision", fm)
        # entity_id uses the 4-type derivation (not the event hash).
        self.assertTrue(fm["entity_id"].startswith("e_concept_"))

    def test_event_with_garbage_occurred_at_falls_back_to_concept(self):
        entity = {
            "name":        "Some event",
            "type":        "event",
            "occurred_at": "yesterday",   # not ISO 8601
            "attributes":  {},
            "relations":   [],
        }
        out = Path(self.wg.create_entity_file(entity, "x.md", []))
        self.assertEqual(out.parent.name, "concept")
        fm = self._read_fm(out)
        self.assertEqual(fm["entity_type"], "concept")

    def test_event_with_invalid_precision_falls_back_to_concept(self):
        entity = {
            "name":                  "Some event",
            "type":                  "event",
            "occurred_at":           "2026-01-10",
            "occurred_at_precision": "quarter",  # not in the 5-bucket set
            "attributes":            {},
            "relations":             [],
        }
        out = Path(self.wg.create_entity_file(entity, "x.md", []))
        self.assertEqual(out.parent.name, "concept")


# ─── 3. identity collision (memo §12 q2) ────────────────────────────


class EventIngestCollisionTests(_EventIngestBase):

    def test_same_name_different_dates_coexist(self):
        e1 = {
            "name": "Q1 실적 발표", "type": "event",
            "occurred_at": "2026-04-15",
            "attributes": {}, "relations": [],
        }
        e2 = {
            "name": "Q1 실적 발표", "type": "event",
            "occurred_at": "2027-04-14",
            "attributes": {}, "relations": [],
        }
        p1 = Path(self.wg.create_entity_file(e1, "ir1.md", []))
        p2 = Path(self.wg.create_entity_file(e2, "ir2.md", []))
        self.assertNotEqual(p1, p2)
        self.assertTrue(p1.exists() and p2.exists())
        fm1 = self._read_fm(p1)
        fm2 = self._read_fm(p2)
        self.assertNotEqual(fm1["entity_id"], fm2["entity_id"])


# ─── 4. legacy 4-type path unchanged ────────────────────────────────


class FourTypeRegressionTests(_EventIngestBase):
    """The 4 existing entity types must keep producing the same file
    layout as before PR-11b. Only the wiki/entity/<src>/event/ dir
    being created on init differs."""

    def test_concept_still_lands_in_concept_dir(self):
        entity = {
            "name": "RAG", "type": "concept",
            "attributes": {"summary": "retrieval-augmented generation"},
            "relations": [],
        }
        out = Path(self.wg.create_entity_file(entity, "rag.md", []))
        self.assertEqual(out.parent.name, "concept")
        fm = self._read_fm(out)
        self.assertEqual(fm["entity_type"], "concept")
        self.assertNotIn("occurred_at", fm)

    def test_org_still_lands_in_org_dir(self):
        entity = {
            "name": "Anthropic", "type": "org",
            "attributes": {"summary": "AI safety company"},
            "relations": [],
        }
        out = Path(self.wg.create_entity_file(entity, "anth.md", []))
        self.assertEqual(out.parent.name, "org")
        fm = self._read_fm(out)
        self.assertEqual(fm["entity_type"], "org")
        self.assertNotIn("occurred_at", fm)


# ─── Integration — full process_document_for_entities path ──────────
#
# The 2026-05-21 live-verification round on PR-11b surfaced TWO
# completeness gaps that the unit-level tests above didn't catch:
#
#   (1) `_ALLOWED_EXTRACT_TYPES` was still the 3-element frozenset
#       (person/org/concept) — type=event got silently dropped by
#       `_is_safe_extracted_entity` before reaching create_entity_file.
#
#   (2) `process_document_for_entities` built a payload dict for
#       create_entity_file but did NOT carry occurred_at /
#       occurred_at_precision from the LLM result; create_entity_file's
#       event branch saw empty occurred_at and fell back to concept.
#
# Both gaps are post-extraction (the LLM emitted the right shape;
# the wrapper layer dropped it). This class drives the wrapper
# end-to-end with a mocked LLM so future refactors that re-introduce
# either gap break here.


class ProcessDocumentEventIntegrationTests(_EventIngestBase):
    """End-to-end check: when the LLM returns `type: event` with
    occurred_at, the document goes through `process_document_for_entities`
    and lands as an event entity (not a silently-dropped or
    concept-fallback entity)."""

    def _mock_llm_extract(self, *, with_occurred_at: bool,
                           type_value: str = "event"):
        """Patch the WikiGenerator's LLM-extract helper to return a
        deterministic dict shaped like the real Ollama response."""
        from unittest.mock import patch
        payload = {
            "entities": [
                {
                    "name":        "2026 비트코인 ETF 승인",
                    "type":        type_value,
                    "description": "SEC 첫 spot ETF 승인",
                    **(
                        {"occurred_at": "2026-01-10"}
                        if with_occurred_at
                        else {}
                    ),
                },
                {
                    "name":        "SEC",
                    "type":        "org",
                    "description": "미국 증권거래위원회",
                },
            ],
            "relations": [],
        }
        return patch.object(
            self.wg, "_llm_extract_document_entities",
            return_value=payload,
        )

    def test_event_with_occurred_at_lands_in_event_dir(self):
        with self._mock_llm_extract(with_occurred_at=True):
            ids = self.wg.process_document_for_entities(
                filename="t.txt", content="any", chunk_ids=[],
            )
        # 2 entities (event + org) + 1 document → 3 created.
        # The event one is the regression-critical row.
        event_dir = self.wg.entity_path / "event"
        files = list(event_dir.glob("*.md"))
        self.assertEqual(len(files), 1,
            "process_document_for_entities must land the LLM's "
            "type=event entity in the event/ directory — the 2026-05-21 "
            "live-verify finding (see commit body)")
        fm = self._read_fm(files[0])
        self.assertEqual(fm["entity_type"], "event")
        self.assertEqual(fm["occurred_at"], "2026-01-10",
            "occurred_at from the LLM payload must reach the on-disk "
            "frontmatter — payload carry-over was the second gap")
        self.assertEqual(fm["occurred_at_precision"], "day")
        # And the entity_id reflects the event hash (PR-11a-2 scheme).
        self.assertTrue(fm["entity_id"].startswith("e_event_"))
        self.assertIn(fm["entity_id"], ids,
            "the returned entity_ids must include the event we just wrote")

    def test_event_without_occurred_at_falls_back_to_concept(self):
        # LLM emits type=event but no occurred_at. The post-processor's
        # graceful fallback (memo §5.1: "do not invent a date") should
        # downgrade to concept, NOT silently drop.
        with self._mock_llm_extract(with_occurred_at=False):
            self.wg.process_document_for_entities(
                filename="t.txt", content="any", chunk_ids=[],
            )
        event_dir   = self.wg.entity_path / "event"
        concept_dir = self.wg.entity_path / "concept"
        self.assertEqual(len(list(event_dir.glob("*.md"))), 0,
            "no occurred_at → must not land in event/")
        concept_files = list(concept_dir.glob("*.md"))
        self.assertEqual(len(concept_files), 1,
            "fallback row must land in concept/ (one entity)")
        fm = self._read_fm(concept_files[0])
        self.assertEqual(fm["entity_type"], "concept")
        self.assertNotIn("occurred_at", fm,
            "fallback path must not leak time-axis fields into the "
            "downgraded concept frontmatter")

    def test_allowed_extract_types_still_includes_event(self):
        # Belt + suspenders — guard the 2026-05-21 regression at the
        # constant level so a future refactor cannot drop `event` from
        # the safety gate without breaking this test.
        from core.wiki_generator import _ALLOWED_EXTRACT_TYPES
        self.assertIn("event", _ALLOWED_EXTRACT_TYPES,
            "_ALLOWED_EXTRACT_TYPES must include 'event' — otherwise "
            "_is_safe_extracted_entity silently drops every LLM-emitted "
            "event entity")
        self.assertIn("person",  _ALLOWED_EXTRACT_TYPES)
        self.assertIn("org",     _ALLOWED_EXTRACT_TYPES)
        self.assertIn("concept", _ALLOWED_EXTRACT_TYPES)


if __name__ == "__main__":
    unittest.main()
