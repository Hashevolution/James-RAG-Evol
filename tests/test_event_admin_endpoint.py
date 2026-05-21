"""PR-11a-2 — event node creation helper.

Tests `core.graph_node_editor.create_event_node()` at the helper layer.
The HTTP endpoint (`POST /admin/graph/event`) is a thin plumbing
wrapper around this function (`server_llmwiki.py:admin_graph_event_post`)
that adds auth + audit; endpoint-level tests are covered by the
existing admin-endpoint suite pattern when the endpoint is exercised
in a higher-level integration test.

Scope: helper-level guarantees per design memo §5.2 + §12.

production wiki 무영향 — tempfile 격리.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

from core.graph_node_editor import (  # noqa: E402
    _generate_event_entity_id,
    create_event_node,
)
from core.relations_schema import (  # noqa: E402
    EXTRACT_SOURCE_ROLE,
    MANUAL_SOURCE_ROLE,
)


# ─── stub: minimum wiki_generator surface create_event_node needs ────


class _WgStub:
    """Mimics WikiGenerator's entity_path + refresh_entity_map. Mirrors
    the pattern in test_phase_e_graph_editor.py:_WgStub but with the
    `entity_path` attribute that create_event_node writes through.
    """
    def __init__(self, root: Path):
        self.entity_path = root
        self.entity_id_index: dict = {}
        self.refresh_called = 0

    def refresh_entity_map(self):
        self.refresh_called += 1


def _make_root() -> Path:
    root = Path(tempfile.mkdtemp()) / "entity"
    for t in ("person", "concept", "org", "document", "event"):
        (root / t).mkdir(parents=True)
    return root


def _read_fm(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    body = text.split("---", 2)[1]
    return yaml.safe_load(body)


# ─── 1. happy path ──────────────────────────────────────────────────


class CreateEventHappyPathTests(unittest.TestCase):

    def test_creates_file_with_expected_frontmatter(self):
        root = _make_root()
        wg = _WgStub(root)
        result = create_event_node(
            "2026 비트코인 ETF 승인",
            "2026-01-10",
            wiki_generator=wg,
        )
        self.assertTrue(result["entity_id"].startswith("e_event_"))
        self.assertTrue(Path(result["path"]).exists())

        fm = _read_fm(Path(result["path"]))
        self.assertEqual(fm["entity_type"], "event")
        self.assertEqual(fm["occurred_at"], "2026-01-10")
        self.assertEqual(fm["occurred_at_precision"], "day")
        self.assertEqual(fm["name"], "2026 비트코인 ETF 승인")
        self.assertEqual(len(fm["sources"]), 1)
        # source_doc_id omitted → role=manual
        self.assertEqual(fm["sources"][0]["role"], MANUAL_SOURCE_ROLE)

    def test_refreshes_entity_index_after_write(self):
        root = _make_root()
        wg = _WgStub(root)
        create_event_node(
            "Event A", "2026-01-10", wiki_generator=wg,
        )
        self.assertEqual(wg.refresh_called, 1)

    def test_source_doc_id_makes_role_extract(self):
        root = _make_root()
        wg = _WgStub(root)
        result = create_event_node(
            "ingested event", "2026-01-10",
            wiki_generator=wg,
            source_doc_id="d_sec_filing_2026_01",
            source_weight=0.85,
        )
        fm = _read_fm(Path(result["path"]))
        self.assertEqual(fm["sources"][0]["role"], EXTRACT_SOURCE_ROLE)
        self.assertEqual(fm["sources"][0]["doc_id"], "d_sec_filing_2026_01")
        self.assertEqual(fm["sources"][0]["weight"], 0.85)

    def test_aliases_normalized_and_deduped(self):
        root = _make_root()
        wg = _WgStub(root)
        result = create_event_node(
            "Event B", "2026-01-10",
            wiki_generator=wg,
            aliases=["BTC ETF", "", "BTC ETF", "Bitcoin ETF"],
        )
        fm = _read_fm(Path(result["path"]))
        # Empty + dupe stripped; insertion order preserved.
        self.assertEqual(fm["aliases"], ["BTC ETF", "Bitcoin ETF"])


# ─── 2. validation gates ────────────────────────────────────────────


class CreateEventValidationTests(unittest.TestCase):

    def test_empty_name_raises(self):
        root = _make_root()
        wg = _WgStub(root)
        with self.assertRaisesRegex(ValueError, "name"):
            create_event_node("", "2026-01-10", wiki_generator=wg)

    def test_whitespace_name_raises(self):
        root = _make_root()
        wg = _WgStub(root)
        with self.assertRaisesRegex(ValueError, "name"):
            create_event_node("   ", "2026-01-10", wiki_generator=wg)

    def test_occurred_at_garbage_raises(self):
        root = _make_root()
        wg = _WgStub(root)
        with self.assertRaisesRegex(ValueError, "ISO 8601"):
            create_event_node("X", "yesterday", wiki_generator=wg)

    def test_invalid_precision_raises(self):
        root = _make_root()
        wg = _WgStub(root)
        with self.assertRaisesRegex(ValueError, "precision"):
            create_event_node(
                "X", "2026-01-10",
                wiki_generator=wg,
                occurred_at_precision="quarter",
            )

    def test_source_weight_out_of_range_raises(self):
        root = _make_root()
        wg = _WgStub(root)
        with self.assertRaisesRegex(ValueError, "source_weight"):
            create_event_node(
                "X", "2026-01-10",
                wiki_generator=wg,
                source_weight=1.5,
            )

    def test_source_weight_non_numeric_raises(self):
        root = _make_root()
        wg = _WgStub(root)
        with self.assertRaisesRegex(ValueError, "source_weight"):
            create_event_node(
                "X", "2026-01-10",
                wiki_generator=wg,
                source_weight="high",  # type: ignore[arg-type]
            )


# ─── 3. identity / collision (memo §12 q2) ──────────────────────────


class IdentityCollisionTests(unittest.TestCase):

    def test_same_name_different_date_yields_different_ids(self):
        a = _generate_event_entity_id("X", "2026-01-10", "day")
        b = _generate_event_entity_id("X", "2026-01-11", "day")
        self.assertNotEqual(a, b)

    def test_same_name_different_precision_yields_different_ids(self):
        a = _generate_event_entity_id("X", "2026-01-10", "day")
        b = _generate_event_entity_id("X", "2026-01-10", "month")
        self.assertNotEqual(a, b)

    def test_same_inputs_yield_stable_id(self):
        a = _generate_event_entity_id("X", "2026-01-10", "day")
        b = _generate_event_entity_id("X", "2026-01-10", "day")
        self.assertEqual(a, b)

    def test_two_events_same_name_different_dates_coexist(self):
        root = _make_root()
        wg = _WgStub(root)
        r1 = create_event_node(
            "Q1 실적 발표", "2026-04-15", wiki_generator=wg,
        )
        r2 = create_event_node(
            "Q1 실적 발표", "2027-04-14", wiki_generator=wg,
        )
        self.assertNotEqual(r1["entity_id"], r2["entity_id"])
        self.assertNotEqual(r1["path"], r2["path"])
        self.assertTrue(Path(r1["path"]).exists())
        self.assertTrue(Path(r2["path"]).exists())

    def test_duplicate_event_raises(self):
        # Same name + same occurred_at + same precision twice → second
        # call surfaces "event already exists" rather than overwriting.
        root = _make_root()
        wg = _WgStub(root)
        create_event_node(
            "Dup event", "2026-01-10", wiki_generator=wg,
        )
        with self.assertRaisesRegex(ValueError, "already exists"):
            create_event_node(
                "Dup event", "2026-01-10", wiki_generator=wg,
            )


# ─── 4. wiki_generator entity_types includes event (lift) ───────────


class WikiGeneratorLiftTests(unittest.TestCase):
    """Sanity check: after the lift, the production class's entity_types
    starts with the legacy 4 and ends with `event`. This is the contract
    create_event_node relies on (event directory pre-created)."""

    def test_production_entity_types_includes_event_last(self):
        # Import the production class directly. Construction is
        # heavyweight, so just assert the constant at the wire-up site.
        from core.relations_schema import ENTITY_TYPES_CORE
        # This is what wiki_generator.py:132 lifts to (post-PR-11a-2):
        self.assertIn("event", ENTITY_TYPES_CORE)
        self.assertEqual(ENTITY_TYPES_CORE[-1], "event")


if __name__ == "__main__":
    unittest.main()
