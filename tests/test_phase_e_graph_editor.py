"""Phase E (Knowledge Cascade) — graph editor backend 검증.

docs/design/v0.3-knowledge-cascade.md §7 — Phase E.

본 테스트는 ``core/graph_editor.py`` 의 3 mutation API 와 env flag
helper 를 cover. UI 는 별도 PR 이라 frontend wiring 은 검증 대상 아님.

검증 시나리오:
  1. replace_relation_sources (PUT)
     - 기존 relation 의 sources 교체 + confidence derive
     - 양방향 동기화 (forward + inverse)
     - 매칭 relation 없을 때 신규 생성
     - target entity 없을 때 forward 만 반영
     - 빈 sources → ValueError (use DELETE)
  2. append_relation_source (POST)
     - 한 줄 append, 기존 sources 보존
     - 양쪽 동시 append
     - 신규 relation 자동 생성
     - manual role 의 author/note 보존
  3. delete_relation (DELETE)
     - 양쪽 relation 제거
     - 없으면 no-op
  4. graph_edit_enabled — env flag 기본 off, "1"/"true"/"on" 등 허용
  5. cascade(Phase C) 와의 정합: PUT 으로 추가한 manual source 가
     cascade_remove_doc_from_sources 후에도 살아남아 entity 가
     orphan 으로 잘못 분류되지 않음

production wiki 무영향 — tempfile 격리.
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

from utils.console import ensure_utf8_console
ensure_utf8_console()

from core.graph_editor import (
    append_relation_source,
    delete_relation,
    graph_edit_enabled,
    read_relation,
    replace_relation_sources,
)
from core.graph_node_editor import (
    NODE_ALLOWED_ENTITY_TYPES,
    NODE_ALLOWED_SENSITIVITY,
    NODE_EDITABLE_FIELDS,
    update_node_attributes,
)
from core.relations_schema import (
    EXTRACT_SOURCE_ROLE,
    MANUAL_SOURCE_ROLE,
    compute_confidence_from_sources,
)


# ── 0. fixture helpers ─────────────────────────────────────────────

def _write_entity(path: Path, fm: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        "---\n"
        + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False,
                         default_flow_style=False)
        + "---\n# body\n"
    )
    path.write_text(text, encoding="utf-8")


def _read_fm(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    body = text.split("---", 2)[1]
    return yaml.safe_load(body)


class _WgStub:
    """WikiGenerator 의 entity_id_index + refresh_entity_map 만 모의."""
    def __init__(self, entity_id_index: dict):
        self.entity_id_index = entity_id_index

    def refresh_entity_map(self):
        pass


def _two_entities_with_relation(role: str = EXTRACT_SOURCE_ROLE):
    """Joby (org) ↔ NVIDIA (org) 1 relation 시나리오. 양쪽 다 sources
    1 항목 보유. 반환: (root, wg_stub, joby_path, nv_path, ids)"""
    root = Path(tempfile.mkdtemp()) / "entity"
    for t in ("person", "org", "concept", "document"):
        (root / t).mkdir(parents=True)
    joby_id = "e_org_joby"
    nv_id   = "e_org_nvidia"
    joby_p = root / "org" / "joby.md"
    nv_p   = root / "org" / "nvidia.md"
    _write_entity(joby_p, {
        "entity_id":   joby_id,
        "name":        "Joby",
        "entity_type": "org",
        "relations": [{
            "target": "NVIDIA", "target_id": nv_id,
            "target_type": "org", "type": "RELATED_TO", "label": "관련",
            "confidence": 0.7,
            "sources": [{"doc_id": "e_doc_old", "weight": 0.7,
                         "role": role, "ts": "2026-05-14"}],
        }],
    })
    _write_entity(nv_p, {
        "entity_id":   nv_id,
        "name":        "NVIDIA",
        "entity_type": "org",
        "relations": [{
            "target": "Joby", "target_id": joby_id,
            "target_type": "org", "type": "RELATED_TO", "label": "관련",
            "confidence": 0.7,
            "sources": [{"doc_id": "e_doc_old", "weight": 0.7,
                         "role": role, "ts": "2026-05-14"}],
        }],
    })
    wg = _WgStub({joby_id: joby_p, nv_id: nv_p})
    return root, wg, joby_p, nv_p, (joby_id, nv_id)


# ── 1. replace_relation_sources (PUT) ──────────────────────────────

class ReplaceRelationSourcesTests(unittest.TestCase):
    def test_replaces_both_sides_and_derives_confidence(self):
        _, wg, joby_p, nv_p, (joby_id, nv_id) = _two_entities_with_relation()
        new_sources = [
            {"doc_id": None, "weight": 0.9, "role": MANUAL_SOURCE_ROLE,
             "author": "admin", "note": "verified manually"},
        ]
        result = replace_relation_sources(
            joby_id, nv_id, "RELATED_TO", new_sources,
            wiki_generator=wg,
        )

        # forward
        fm = _read_fm(joby_p)
        rel = fm["relations"][0]
        self.assertEqual(len(rel["sources"]), 1)
        self.assertEqual(rel["sources"][0]["role"], MANUAL_SOURCE_ROLE)
        self.assertEqual(rel["sources"][0]["author"], "admin")
        self.assertEqual(rel["sources"][0]["note"], "verified manually")
        self.assertEqual(rel["confidence"],
                         compute_confidence_from_sources(rel["sources"]))

        # inverse
        fm_inv = _read_fm(nv_p)
        rel_inv = fm_inv["relations"][0]
        self.assertEqual(len(rel_inv["sources"]), 1)
        self.assertEqual(rel_inv["sources"][0]["role"], MANUAL_SOURCE_ROLE)
        self.assertEqual(rel_inv["confidence"], rel["confidence"])

        self.assertEqual(result["forward"]["after"][0]["role"],
                         MANUAL_SOURCE_ROLE)
        self.assertIsNotNone(result["inverse"])

    def test_creates_relation_if_missing(self):
        root = Path(tempfile.mkdtemp()) / "entity"
        for t in ("person", "org", "concept", "document"):
            (root / t).mkdir(parents=True)
        a_id, b_id = "e_org_a", "e_org_b"
        a_p = root / "org" / "a.md"
        b_p = root / "org" / "b.md"
        _write_entity(a_p, {"entity_id": a_id, "name": "A",
                            "entity_type": "org", "relations": []})
        _write_entity(b_p, {"entity_id": b_id, "name": "B",
                            "entity_type": "org", "relations": []})
        wg = _WgStub({a_id: a_p, b_id: b_p})

        replace_relation_sources(
            a_id, b_id, "RELATED_TO",
            [{"doc_id": None, "weight": 0.5, "role": MANUAL_SOURCE_ROLE}],
            wiki_generator=wg,
        )
        fm_a = _read_fm(a_p)
        self.assertEqual(len(fm_a["relations"]), 1)
        self.assertEqual(fm_a["relations"][0]["target_id"], b_id)
        self.assertEqual(fm_a["relations"][0]["target"], "B")
        self.assertEqual(fm_a["relations"][0]["target_type"], "org")
        fm_b = _read_fm(b_p)
        self.assertEqual(len(fm_b["relations"]), 1)
        self.assertEqual(fm_b["relations"][0]["target_id"], a_id)

    def test_inverse_skipped_when_target_missing(self):
        root = Path(tempfile.mkdtemp()) / "entity"
        for t in ("person", "org", "concept", "document"):
            (root / t).mkdir(parents=True)
        a_id = "e_org_a"
        a_p = root / "org" / "a.md"
        _write_entity(a_p, {"entity_id": a_id, "name": "A",
                            "entity_type": "org", "relations": []})
        wg = _WgStub({a_id: a_p})
        result = replace_relation_sources(
            a_id, "e_org_missing", "RELATED_TO",
            [{"doc_id": None, "weight": 0.5, "role": MANUAL_SOURCE_ROLE}],
            wiki_generator=wg,
        )
        fm = _read_fm(a_p)
        self.assertEqual(len(fm["relations"]), 1)
        self.assertIsNone(result["inverse"])

    def test_empty_sources_raises(self):
        _, wg, _, _, (joby_id, nv_id) = _two_entities_with_relation()
        with self.assertRaises(ValueError):
            replace_relation_sources(
                joby_id, nv_id, "RELATED_TO", [],
                wiki_generator=wg,
            )

    def test_invalid_role_raises(self):
        _, wg, _, _, (joby_id, nv_id) = _two_entities_with_relation()
        with self.assertRaises(ValueError):
            replace_relation_sources(
                joby_id, nv_id, "RELATED_TO",
                [{"doc_id": None, "weight": 0.5, "role": "bogus_role"}],
                wiki_generator=wg,
            )

    def test_src_entity_missing_raises(self):
        _, wg, _, _, (_, nv_id) = _two_entities_with_relation()
        with self.assertRaises(ValueError):
            replace_relation_sources(
                "e_org_nonexistent", nv_id, "RELATED_TO",
                [{"doc_id": None, "weight": 0.5, "role": MANUAL_SOURCE_ROLE}],
                wiki_generator=wg,
            )


# ── 2. append_relation_source (POST) ───────────────────────────────

class AppendRelationSourceTests(unittest.TestCase):
    def test_appends_to_both_sides_preserving_existing(self):
        _, wg, joby_p, nv_p, (joby_id, nv_id) = _two_entities_with_relation()
        result = append_relation_source(
            joby_id, nv_id, "RELATED_TO",
            {"doc_id": None, "weight": 0.5, "role": MANUAL_SOURCE_ROLE,
             "note": "additional evidence"},
            wiki_generator=wg,
        )
        fm = _read_fm(joby_p)
        rel = fm["relations"][0]
        self.assertEqual(len(rel["sources"]), 2)
        # 첫 번째는 기존 extract source 보존
        self.assertEqual(rel["sources"][0]["role"], EXTRACT_SOURCE_ROLE)
        self.assertEqual(rel["sources"][1]["role"], MANUAL_SOURCE_ROLE)
        # confidence 는 두 source 의 noisy-OR — 헬퍼로 검증.
        self.assertEqual(rel["confidence"],
                         compute_confidence_from_sources(rel["sources"]))

        fm_inv = _read_fm(nv_p)
        self.assertEqual(len(fm_inv["relations"][0]["sources"]), 2)
        self.assertIsNotNone(result["inverse"])

    def test_creates_relation_when_missing(self):
        root = Path(tempfile.mkdtemp()) / "entity"
        for t in ("person", "org", "concept", "document"):
            (root / t).mkdir(parents=True)
        a_id, b_id = "e_org_a", "e_org_b"
        a_p = root / "org" / "a.md"
        b_p = root / "org" / "b.md"
        _write_entity(a_p, {"entity_id": a_id, "name": "A",
                            "entity_type": "org", "relations": []})
        _write_entity(b_p, {"entity_id": b_id, "name": "B",
                            "entity_type": "org", "relations": []})
        wg = _WgStub({a_id: a_p, b_id: b_p})

        append_relation_source(
            a_id, b_id, "RELATED_TO",
            {"doc_id": None, "weight": 0.6, "role": MANUAL_SOURCE_ROLE},
            wiki_generator=wg,
        )
        fm_a = _read_fm(a_p)
        fm_b = _read_fm(b_p)
        self.assertEqual(len(fm_a["relations"]), 1)
        self.assertEqual(len(fm_b["relations"]), 1)
        self.assertEqual(fm_a["relations"][0]["sources"][0]["role"],
                         MANUAL_SOURCE_ROLE)

    def test_manual_metadata_preserved(self):
        _, wg, joby_p, _, (joby_id, nv_id) = _two_entities_with_relation()
        append_relation_source(
            joby_id, nv_id, "RELATED_TO",
            {"doc_id": None, "weight": 0.7, "role": MANUAL_SOURCE_ROLE,
             "author": "alice", "note": "x" * 500},   # over-cap note
            wiki_generator=wg,
        )
        fm = _read_fm(joby_p)
        s = fm["relations"][0]["sources"][-1]
        self.assertEqual(s["author"], "alice")
        self.assertEqual(len(s["note"]), 300)   # truncated


# ── 3. delete_relation (DELETE) ────────────────────────────────────

class DeleteRelationTests(unittest.TestCase):
    def test_removes_both_sides(self):
        _, wg, joby_p, nv_p, (joby_id, nv_id) = _two_entities_with_relation()
        result = delete_relation(
            joby_id, nv_id, "RELATED_TO",
            wiki_generator=wg,
        )
        self.assertTrue(result["forward"]["removed"])
        self.assertTrue(result["inverse"]["removed"])
        self.assertEqual(_read_fm(joby_p).get("relations") or [], [])
        self.assertEqual(_read_fm(nv_p).get("relations") or [], [])

    def test_noop_when_relation_missing(self):
        root = Path(tempfile.mkdtemp()) / "entity"
        for t in ("person", "org", "concept", "document"):
            (root / t).mkdir(parents=True)
        a_id, b_id = "e_org_a", "e_org_b"
        a_p = root / "org" / "a.md"
        b_p = root / "org" / "b.md"
        _write_entity(a_p, {"entity_id": a_id, "name": "A",
                            "entity_type": "org", "relations": []})
        _write_entity(b_p, {"entity_id": b_id, "name": "B",
                            "entity_type": "org", "relations": []})
        wg = _WgStub({a_id: a_p, b_id: b_p})
        result = delete_relation(
            a_id, b_id, "RELATED_TO",
            wiki_generator=wg,
        )
        self.assertFalse(result["forward"]["removed"])
        self.assertFalse(result["inverse"]["removed"])


# ── 4. env flag ────────────────────────────────────────────────────

class GraphEditEnabledTests(unittest.TestCase):
    def test_default_off(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("JAMES_GRAPH_EDIT", None)
            self.assertFalse(graph_edit_enabled())

    def test_one_enables(self):
        with patch.dict(os.environ, {"JAMES_GRAPH_EDIT": "1"}):
            self.assertTrue(graph_edit_enabled())

    def test_other_truthy_values(self):
        for v in ("true", "TRUE", "yes", "on"):
            with patch.dict(os.environ, {"JAMES_GRAPH_EDIT": v}):
                self.assertTrue(graph_edit_enabled(), f"value {v!r}")

    def test_falsy_values(self):
        for v in ("0", "false", "no", "off", "", "random"):
            with patch.dict(os.environ, {"JAMES_GRAPH_EDIT": v}):
                self.assertFalse(graph_edit_enabled(), f"value {v!r}")


# ── 4b. read_relation (GET) ────────────────────────────────────────

class ReadRelationTests(unittest.TestCase):
    def test_returns_relation_with_sources(self):
        _, wg, _, _, (joby_id, nv_id) = _two_entities_with_relation()
        rel = read_relation(joby_id, nv_id, "RELATED_TO", wiki_generator=wg)
        self.assertIsNotNone(rel)
        self.assertEqual(rel["target_id"], nv_id)
        self.assertEqual(len(rel["sources"]), 1)
        self.assertEqual(rel["sources"][0]["role"], EXTRACT_SOURCE_ROLE)

    def test_missing_relation_returns_none(self):
        _, wg, _, _, (joby_id, _) = _two_entities_with_relation()
        self.assertIsNone(read_relation(
            joby_id, "e_org_nonexistent", "RELATED_TO",
            wiki_generator=wg,
        ))

    def test_missing_src_entity_raises(self):
        _, wg, _, _, (_, nv_id) = _two_entities_with_relation()
        with self.assertRaises(ValueError):
            read_relation(
                "e_org_nonexistent", nv_id, "RELATED_TO",
                wiki_generator=wg,
            )


# ── 5. Phase C cascade 와의 정합 ───────────────────────────────────

class PhaseC_CascadeIntegrationTests(unittest.TestCase):
    """그래프 에디터로 추가한 manual source 가 doc 삭제 cascade 후에도
    살아남아 entity 가 orphan 으로 잘못 분류되지 않는지."""

    def test_manual_source_survives_cascade(self):
        from core.cascade import (
            cascade_remove_doc_from_sources,
            find_orphan_entities,
        )
        _, wg, joby_p, nv_p, (joby_id, nv_id) = _two_entities_with_relation()
        # 시작 sources 는 doc=e_doc_old, role=extract.
        # 그래프 에디터로 manual 한 줄 append.
        append_relation_source(
            joby_id, nv_id, "RELATED_TO",
            {"doc_id": None, "weight": 0.9, "role": MANUAL_SOURCE_ROLE,
             "author": "admin"},
            wiki_generator=wg,
        )
        # joby/nvidia 둘 다 source_document=old.pdf 라고 마킹 (orphan
        # 후보가 되도록).
        for p in (joby_p, nv_p):
            fm = _read_fm(p)
            fm["attributes"] = {"source_document": "old.pdf"}
            _write_entity(p, fm)

        # cascade — e_doc_old 의 source 제거
        counts = cascade_remove_doc_from_sources(
            "e_doc_old", joby_p.parent.parent,
        )
        # extract source 만 사라지고 manual 은 남아 relation 유지
        self.assertEqual(counts["relations_dropped"], 0)
        self.assertEqual(counts["relations_recomputed"], 2)
        fm_after = _read_fm(joby_p)
        rel = fm_after["relations"][0]
        self.assertEqual(len(rel["sources"]), 1)
        self.assertEqual(rel["sources"][0]["role"], MANUAL_SOURCE_ROLE)

        # orphan sweep — manual relation 살아있어 둘 다 orphan 아님
        orphans = find_orphan_entities(
            "old.pdf", "e_doc_old", joby_p.parent.parent,
        )
        self.assertEqual(orphans, [])


# ── 6. update_node_attributes (PR-O6 cycle 12) ────────────────────


def _single_entity(entity_type: str = "org"):
    """Build a single-entity fixture for node-attribute tests.
    Returns (root, wg_stub, entity_path, entity_id)."""
    root = Path(tempfile.mkdtemp()) / "entity"
    for t in NODE_ALLOWED_ENTITY_TYPES:
        (root / t).mkdir(parents=True)
    eid = f"e_{entity_type}_anthropic"
    p = root / entity_type / "anthropic.md"
    _write_entity(p, {
        "entity_id":   eid,
        "name":        "Anthropic",
        "entity_type": entity_type,
        "aliases":     ["Anthropic PBC"],
        "summary":     "AI lab",
        "sensitivity": "normal",
    })
    return root, _WgStub({eid: p}), p, eid


class UpdateNodeAttributesTests(unittest.TestCase):
    """PR-O6 — node attribute editor.

    Pins immutability + allowlist + per-field validation + audit-diff
    shape. UI wiring is a separate concern (PR-O6b frontend).
    """

    def test_happy_path_updates_name_and_summary(self):
        _, wg, p, eid = _single_entity()
        result = update_node_attributes(
            eid,
            {"name": "Anthropic, PBC", "summary": "AI safety company"},
            wiki_generator=wg,
        )
        self.assertEqual(result["entity_id"], eid)
        self.assertEqual(sorted(result["changed_fields"]),
                         ["name", "summary"])
        self.assertEqual(result["before"]["name"], "Anthropic")
        self.assertEqual(result["after"]["name"], "Anthropic, PBC")
        fm = _read_fm(p)
        self.assertEqual(fm["name"], "Anthropic, PBC")
        self.assertEqual(fm["summary"], "AI safety company")
        self.assertIn("updated_at", fm,
            "successful write must stamp updated_at")

    def test_empty_patch_raises(self):
        _, wg, _, eid = _single_entity()
        with self.assertRaises(ValueError):
            update_node_attributes(eid, {}, wiki_generator=wg)

    def test_patch_with_only_unknown_fields_raises(self):
        _, wg, _, eid = _single_entity()
        with self.assertRaises(ValueError) as ctx:
            update_node_attributes(
                eid,
                {"entity_id": "hacked", "relations": [], "random": 1},
                wiki_generator=wg,
            )
        self.assertIn("no editable fields", str(ctx.exception))

    def test_unknown_fields_silently_dropped_when_one_known_field_present(self):
        # Mixed payload: a typo / smuggled relations key must NOT
        # reach the frontmatter; the known field still writes.
        _, wg, p, eid = _single_entity()
        result = update_node_attributes(
            eid,
            {
                "name":      "New Name",
                "entity_id": "hacked-id",   # immutability invariant
                "relations": [{"forged": True}],  # use relation API
                "random":    "ignored",
            },
            wiki_generator=wg,
        )
        self.assertEqual(result["changed_fields"], ["name"])
        fm = _read_fm(p)
        self.assertEqual(fm["entity_id"], eid,
            "entity_id must remain unchanged across patches")
        # _single_entity fixture has no relations field; the forged
        # payload must NOT cause one to appear.
        self.assertNotIn("relations", fm,
            "relations must not be added by node-attribute writes")

    def test_invalid_entity_type_raises(self):
        _, wg, _, eid = _single_entity()
        with self.assertRaises(ValueError) as ctx:
            update_node_attributes(
                eid, {"entity_type": "alien"}, wiki_generator=wg,
            )
        self.assertIn("entity_type", str(ctx.exception))

    def test_invalid_sensitivity_raises(self):
        _, wg, _, eid = _single_entity()
        with self.assertRaises(ValueError):
            update_node_attributes(
                eid, {"sensitivity": "ultra"}, wiki_generator=wg,
            )
        self.assertEqual(sorted(NODE_ALLOWED_SENSITIVITY),
                         ["normal", "sensitive"])

    def test_empty_name_raises(self):
        _, wg, _, eid = _single_entity()
        with self.assertRaises(ValueError):
            update_node_attributes(
                eid, {"name": "   "}, wiki_generator=wg,
            )

    def test_aliases_normalized(self):
        """Whitespace, dedup, per-alias cap, total cap."""
        _, wg, p, eid = _single_entity()
        many = [f"alias-{i}" for i in range(30)]  # > limit 20
        many.append("alias-0")                     # dup
        many.append("  alias-extra  ")             # whitespace
        many.append("")                             # empty
        many.append(123)                            # type
        update_node_attributes(
            eid, {"aliases": many}, wiki_generator=wg,
        )
        fm = _read_fm(p)
        aliases = fm["aliases"]
        self.assertEqual(len(aliases), 20,
            "alias list must be capped at 20 entries")
        self.assertEqual(aliases[0], "alias-0")
        self.assertNotIn("", aliases)
        self.assertNotIn(123, aliases)
        # alias-0 only once even though sent twice
        self.assertEqual(aliases.count("alias-0"), 1)

    def test_summary_truncated_at_4000(self):
        _, wg, p, eid = _single_entity()
        big = "x" * 5000
        update_node_attributes(
            eid, {"summary": big}, wiki_generator=wg,
        )
        fm = _read_fm(p)
        self.assertEqual(len(fm["summary"]), 4000,
            "summary must cap at 4000 chars")

    def test_summary_null_clears(self):
        _, wg, p, eid = _single_entity()
        update_node_attributes(
            eid, {"summary": None}, wiki_generator=wg,
        )
        fm = _read_fm(p)
        self.assertEqual(fm["summary"], "")

    def test_no_op_patch_returns_empty_changed_fields(self):
        # Re-applying current values should yield no diff and no write
        # — but the function still returns the expected shape for the
        # audit log.
        _, wg, _, eid = _single_entity()
        result = update_node_attributes(
            eid,
            {"name": "Anthropic", "entity_type": "org"},
            wiki_generator=wg,
        )
        self.assertEqual(result["changed_fields"], [])
        self.assertEqual(result["before"], {})
        self.assertEqual(result["after"], {})

    def test_missing_entity_id_raises(self):
        _, wg, _, _ = _single_entity()
        with self.assertRaises(ValueError) as ctx:
            update_node_attributes(
                "e_org_nonexistent", {"name": "X"}, wiki_generator=wg,
            )
        self.assertIn("entity_id not found", str(ctx.exception))

    def test_relations_array_preserved_across_patch(self):
        # The handler must not nuke or rewrite the relations array even
        # when the patch payload doesn't mention it.
        _, wg, joby_p, _, (joby_id, _) = _two_entities_with_relation()
        # Use the joby fixture for this — it has 1 relation.
        update_node_attributes(
            joby_id, {"summary": "Joby Aviation update"},
            wiki_generator=wg,
        )
        fm = _read_fm(joby_p)
        self.assertEqual(len(fm["relations"]), 1,
            "node-attribute write must leave relations untouched")
        self.assertEqual(fm["relations"][0]["target"], "NVIDIA")

    def test_editable_field_allowlist_matches_doc(self):
        # Pinned for future code reviewers: any change here must be
        # paired with a doc/handover update because external callers
        # (admin matrix UI) gate on this list.
        self.assertEqual(
            sorted(NODE_EDITABLE_FIELDS),
            ["aliases", "entity_type", "name", "sensitivity", "summary"],
        )


if __name__ == "__main__":
    unittest.main()
