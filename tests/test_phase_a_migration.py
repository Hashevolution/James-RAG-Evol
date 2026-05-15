"""Phase A migration script — synthetic-wiki fixture round-trip.

docs/design/v0.3-knowledge-cascade.md §3 / §8 — Knowledge Cascade Phase A.

본 테스트는 ``scripts/migrate_phase_a_sources.py`` 를 임시 wiki/ tree
위에서 직접 실행해서 다음을 검증:

  1. 멱등 — 두 번 돌려도 sources 가 중복 추가되지 않는다
  2. confidence 보존 — 마이그레이션 전후 모든 relation 의 confidence
     값이 그대로 유지된다 (read-path 호환)
  3. weight = 기존 confidence — 새 source 의 weight 가 기존 confidence
     와 같아 compute_confidence_from_sources 가 동일 값을 돌려준다
     (행동 변화 0)
  4. dry-run 은 디스크 미변경
  5. snapshot 생성 + rollback 가 깨끗한 round-trip

production wiki 에 영향 없음 — 모든 테스트는 tempfile.TemporaryDirectory
하에서만 동작.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent

from core.relations_schema import (
    LEGACY_SOURCE_ROLE,
    compute_confidence_from_sources,
)


# Import migration module by path so the test doesn't depend on scripts/
# being on PYTHONPATH (it isn't, by design — scripts are CLI entry points).
def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MIG     = _load_module("migrate_phase_a_sources",
                       ROOT / "scripts" / "migrate_phase_a_sources.py")
ROLLBACK= _load_module("rollback_phase_a_sources",
                       ROOT / "scripts" / "rollback_phase_a_sources.py")


# ─── Synthetic wiki fixture ────────────────────────────────────

_SAMPLE_ENTITY = """\
---
aliases:
- ACI
attributes:
  source_document: 04_Agent_Loop와_ReAct_패턴.pdf
  summary: LLM 친화적 도구 인터페이스 설계 개념
confidence: 1.0
created_at: '2026-05-05T16:39:01.003562'
entity_id: e_concept_2837d929
entity_type: concept
name: ACI
normalized_name: aci
owner: system
relations:
- target: ReAct
  target_id: e_concept_a39b807d
  target_type: concept
  label: 관련
  confidence: 0.7
- target: Agent Loop
  target_id: e_concept_xxxxxxxx
  target_type: concept
  label: 관련
  confidence: 0.9
sensitivity: internal
---

# ACI

LLM 친화적 도구 인터페이스 설계.
"""

_ENTITY_NO_RELATIONS = """\
---
entity_id: e_org_solo
entity_type: org
name: Solo Org
relations: []
---

# Solo Org

관계 없는 entity.
"""


def _write_fixture(wiki_root: Path):
    """Minimal wiki tree with the two entity files above."""
    (wiki_root / "entity" / "prod" / "concept").mkdir(parents=True, exist_ok=True)
    (wiki_root / "entity" / "prod" / "org").mkdir(parents=True, exist_ok=True)
    (wiki_root / "entity" / "prod" / "concept" / "aci.md").write_text(
        _SAMPLE_ENTITY, encoding="utf-8",
    )
    (wiki_root / "entity" / "prod" / "org" / "solo.md").write_text(
        _ENTITY_NO_RELATIONS, encoding="utf-8",
    )


def _load_relations(path: Path) -> list:
    text = path.read_text(encoding="utf-8")
    fm, _ = MIG._split_frontmatter(text)
    return list(fm.get("relations") or [])


# ─── Tests ─────────────────────────────────────────────────────

class DryRunTests(unittest.TestCase):

    def test_dry_run_does_not_touch_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            wiki = Path(tmp) / "wiki"
            _write_fixture(wiki)
            aci = wiki / "entity" / "prod" / "concept" / "aci.md"
            before = aci.read_bytes()

            stats = MIG.migrate_wiki(wiki, dry_run=True)

            self.assertEqual(aci.read_bytes(), before,
                "dry-run must not modify files")
            self.assertEqual(stats["mutated"], 0,
                "dry-run reports 0 mutated even when relations would change")
            self.assertEqual(stats["relations_back_filled"], 2,
                "dry-run still counts what *would* be back-filled — "
                "operator sees the impact before committing")


class ApplyTests(unittest.TestCase):

    def test_back_fill_adds_sources_with_legacy_role(self):
        with tempfile.TemporaryDirectory() as tmp:
            wiki = Path(tmp) / "wiki"
            _write_fixture(wiki)
            aci = wiki / "entity" / "prod" / "concept" / "aci.md"

            stats = MIG.migrate_wiki(wiki, dry_run=False)

            self.assertEqual(stats["mutated"], 1,
                "exactly one file (aci.md) gets mutated; solo.md has "
                "no relations so it's skipped")
            self.assertEqual(stats["relations_back_filled"], 2,
                "aci.md has 2 relations; both should be back-filled")
            self.assertEqual(stats["errors"], 0)

            rels = _load_relations(aci)
            self.assertEqual(len(rels), 2)
            for rel in rels:
                self.assertIn("sources", rel,
                    "every relation must now carry a sources list")
                self.assertEqual(len(rel["sources"]), 1,
                    "exactly one back-filled legacy source per relation")
                s = rel["sources"][0]
                self.assertEqual(s["role"], LEGACY_SOURCE_ROLE,
                    "back-fill role must be 'legacy' so the future "
                    "cascade gates skip these")
                self.assertIsNone(s["doc_id"],
                    "design §2: pre-migration backref provenance is not "
                    "recoverable — doc_id stays None")
                self.assertAlmostEqual(s["weight"], rel["confidence"],
                    msg="weight must equal the original confidence so "
                        "compute_confidence_from_sources returns the "
                        "same value (byte-identical reads)")

    def test_confidence_unchanged_after_migration(self):
        # The contract that protects STEP 7 byte-identical: existing
        # `relation['confidence']` reads must continue to see the same
        # number. Phase A only adds a sibling field.
        with tempfile.TemporaryDirectory() as tmp:
            wiki = Path(tmp) / "wiki"
            _write_fixture(wiki)
            aci = wiki / "entity" / "prod" / "concept" / "aci.md"

            before = {r["target_id"]: r["confidence"]
                      for r in _load_relations(aci)}

            MIG.migrate_wiki(wiki, dry_run=False)

            after  = {r["target_id"]: r["confidence"]
                      for r in _load_relations(aci)}
            self.assertEqual(before, after,
                "confidence values must be byte-identical pre/post "
                "migration so existing reads continue to work")

    def test_synthetic_source_yields_same_confidence_via_helper(self):
        # The Phase B/E helper compute_confidence_from_sources must
        # return the same number as the legacy 'confidence' field —
        # otherwise migration introduces drift the moment ingestion
        # switches to sources as the source of truth.
        with tempfile.TemporaryDirectory() as tmp:
            wiki = Path(tmp) / "wiki"
            _write_fixture(wiki)
            aci = wiki / "entity" / "prod" / "concept" / "aci.md"

            MIG.migrate_wiki(wiki, dry_run=False)

            rels = _load_relations(aci)
            for rel in rels:
                derived = compute_confidence_from_sources(rel["sources"])
                self.assertAlmostEqual(derived, rel["confidence"],
                    msg=f"derived confidence {derived} ≠ stored "
                        f"{rel['confidence']} for {rel['target_id']}")


class IdempotencyTests(unittest.TestCase):

    def test_running_twice_is_a_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            wiki = Path(tmp) / "wiki"
            _write_fixture(wiki)

            stats1 = MIG.migrate_wiki(wiki, dry_run=False)
            self.assertEqual(stats1["relations_back_filled"], 2)
            after_first = (wiki / "entity" / "prod" / "concept" / "aci.md").read_bytes()

            stats2 = MIG.migrate_wiki(wiki, dry_run=False)
            # 두 번째 실행: 모든 relation 이 이미 sources 를 가짐.
            self.assertEqual(stats2["relations_back_filled"], 0,
                "second run must not back-fill anything")
            self.assertEqual(stats2["relations_skipped_already_migrated"], 2,
                "second run must report 2 relations as already migrated")
            self.assertEqual(stats2["mutated"], 0,
                "second run must not rewrite any file")
            self.assertEqual(
                (wiki / "entity" / "prod" / "concept" / "aci.md").read_bytes(),
                after_first,
                "second run leaves files byte-identical",
            )


class SnapshotAndRollbackTests(unittest.TestCase):

    def test_snapshot_creates_pre_migration_mirror(self):
        with tempfile.TemporaryDirectory() as tmp:
            wiki = Path(tmp) / "wiki"
            _write_fixture(wiki)

            snap = MIG.snapshot_wiki(wiki)

            self.assertTrue(snap.is_dir())
            self.assertEqual(snap.name, "wiki.pre-v03-migration")
            # Same shape as wiki/.
            self.assertTrue(
                (snap / "entity" / "prod" / "concept" / "aci.md").is_file()
            )

    def test_snapshot_refuses_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            wiki = Path(tmp) / "wiki"
            _write_fixture(wiki)
            MIG.snapshot_wiki(wiki)
            with self.assertRaises(FileExistsError):
                MIG.snapshot_wiki(wiki, force=False)

    def test_rollback_round_trip_restores_pre_migration_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            wiki = Path(tmp) / "wiki"
            _write_fixture(wiki)

            aci_before = (wiki / "entity" / "prod" / "concept" / "aci.md").read_bytes()
            MIG.snapshot_wiki(wiki)
            MIG.migrate_wiki(wiki, dry_run=False)
            aci_after = (wiki / "entity" / "prod" / "concept" / "aci.md").read_bytes()
            self.assertNotEqual(aci_before, aci_after,
                "migration must have changed the file (sanity)")

            rc = ROLLBACK.rollback(wiki)
            self.assertEqual(rc, 0)

            aci_rolled = (wiki / "entity" / "prod" / "concept" / "aci.md").read_bytes()
            self.assertEqual(aci_rolled, aci_before,
                "rollback must restore exact pre-migration bytes")


class WikiWithoutEntityRootTests(unittest.TestCase):

    def test_missing_entity_root_is_safe_noop(self):
        # Defensive — fresh project / partial install.
        with tempfile.TemporaryDirectory() as tmp:
            wiki = Path(tmp) / "wiki"
            wiki.mkdir()
            stats = MIG.migrate_wiki(wiki, dry_run=False)
            self.assertEqual(stats["mutated"], 0)
            self.assertEqual(stats["relations_back_filled"], 0)


if __name__ == "__main__":
    unittest.main()
