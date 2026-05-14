"""Phase C (Knowledge Cascade) — file delete cascade 검증.

docs/design/v0.3-knowledge-cascade.md §5 — Phase C.

본 테스트는 ``core/cascade.py`` 의 3 레이어를 단위 / 통합으로 cover:

  1. ``strip_uuid_prefix`` — uploads/ 의 uuid_<original> 패턴 복원
  2. ``cascade_remove_doc_from_sources`` — entity 의 sources 에서 doc
     제거 + manual/legacy 보존 + relation drop / confidence recompute
  3. ``find_orphan_entities`` — source_document 매칭 AND incoming 0
  4. ``cascade_delete_upload`` (통합) — wiki + vector + file backup
     까지 end-to-end

production wiki 에 영향 없음 — 모든 fixture 는 tempfile.TemporaryDirectory
하에서 동작.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import yaml  # noqa: I001

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.console import ensure_utf8_console
ensure_utf8_console()

from core.cascade import (
    backup_upload_file,
    cascade_delete_upload,
    cascade_remove_doc_from_sources,
    find_doc_entity_path,
    find_orphan_entities,
    strip_uuid_prefix,
)
from core.relations_schema import (
    EXTRACT_SOURCE_ROLE,
    INVERSE_SOURCE_ROLE,
    LEGACY_SOURCE_ROLE,
    MANUAL_SOURCE_ROLE,
    compute_confidence_from_sources,
)


# ── 0. uuid prefix strip ────────────────────────────────────────────

class StripUuidPrefixTests(unittest.TestCase):
    def test_strips_full_uuid_prefix(self):
        physical = f"{uuid.uuid4()}_report.pdf"
        self.assertEqual(strip_uuid_prefix(physical), "report.pdf")

    def test_no_prefix_returns_input(self):
        self.assertEqual(strip_uuid_prefix("report.pdf"), "report.pdf")

    def test_uppercase_uuid_accepted(self):
        u = str(uuid.uuid4()).upper()
        self.assertEqual(strip_uuid_prefix(f"{u}_x.md"), "x.md")

    def test_partial_match_does_not_strip(self):
        # 짧은 hex 는 uuid 가 아니므로 그대로
        self.assertEqual(strip_uuid_prefix("abc123_foo.pdf"), "abc123_foo.pdf")


# ── 1. cascade_remove_doc_from_sources ──────────────────────────────

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


class CascadeRemoveDocFromSourcesTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.entity_root = self.root / "entity"
        for t in ("person", "org", "concept", "document"):
            (self.entity_root / t).mkdir(parents=True)

    def test_drops_single_source_relation(self):
        ent_path = self.entity_root / "org" / "joby.md"
        _write_entity(ent_path, {
            "entity_id": "e_org_joby",
            "name": "Joby",
            "entity_type": "org",
            "relations": [{
                "target": "NVIDIA", "target_id": "e_org_nvidia",
                "target_type": "org", "label": "관련", "confidence": 0.8,
                "sources": [{
                    "doc_id": "e_document_X", "weight": 0.8,
                    "role": EXTRACT_SOURCE_ROLE, "ts": "2026-05-14",
                }],
            }],
        })
        counts = cascade_remove_doc_from_sources("e_document_X", self.entity_root)
        self.assertEqual(counts["relations_dropped"], 1)
        self.assertEqual(counts["relations_recomputed"], 0)
        fm = _read_fm(ent_path)
        self.assertEqual(fm.get("relations"), [])

    def test_recomputes_when_other_sources_remain(self):
        ent_path = self.entity_root / "org" / "joby.md"
        _write_entity(ent_path, {
            "entity_id": "e_org_joby",
            "name": "Joby",
            "entity_type": "org",
            "relations": [{
                "target": "NVIDIA", "target_id": "e_org_nvidia",
                "target_type": "org", "label": "관련", "confidence": 0.9,
                "sources": [
                    {"doc_id": "e_document_X", "weight": 0.7,
                     "role": EXTRACT_SOURCE_ROLE, "ts": "2026-05-14"},
                    {"doc_id": "e_document_Y", "weight": 0.5,
                     "role": EXTRACT_SOURCE_ROLE, "ts": "2026-05-14"},
                ],
            }],
        })
        counts = cascade_remove_doc_from_sources("e_document_X", self.entity_root)
        self.assertEqual(counts["relations_dropped"], 0)
        self.assertEqual(counts["relations_recomputed"], 1)
        fm = _read_fm(ent_path)
        rel = fm["relations"][0]
        self.assertEqual(len(rel["sources"]), 1)
        self.assertEqual(rel["sources"][0]["doc_id"], "e_document_Y")
        self.assertEqual(
            rel["confidence"],
            compute_confidence_from_sources(rel["sources"]),
        )

    def test_manual_source_preserved(self):
        """role=manual 인 source 는 doc_id 가 매칭되어도 보존."""
        ent_path = self.entity_root / "org" / "joby.md"
        _write_entity(ent_path, {
            "entity_id": "e_org_joby",
            "name": "Joby",
            "entity_type": "org",
            "relations": [{
                "target": "NVIDIA", "target_id": "e_org_nvidia",
                "target_type": "org", "label": "관련", "confidence": 0.85,
                "sources": [
                    {"doc_id": "e_document_X", "weight": 0.7,
                     "role": EXTRACT_SOURCE_ROLE, "ts": "2026-05-14"},
                    # 같은 doc_id 지만 manual 이라 보존되어야
                    {"doc_id": "e_document_X", "weight": 0.5,
                     "role": MANUAL_SOURCE_ROLE, "ts": "2026-05-14"},
                ],
            }],
        })
        counts = cascade_remove_doc_from_sources("e_document_X", self.entity_root)
        self.assertEqual(counts["relations_dropped"], 0)
        self.assertEqual(counts["relations_recomputed"], 1)
        fm = _read_fm(ent_path)
        rel = fm["relations"][0]
        self.assertEqual(len(rel["sources"]), 1)
        self.assertEqual(rel["sources"][0]["role"], MANUAL_SOURCE_ROLE)

    def test_legacy_source_untouched(self):
        """role=legacy (Phase A back-fill, doc_id=None) 은 어떤 doc 삭제
        에도 영향받지 않는다."""
        ent_path = self.entity_root / "org" / "old.md"
        _write_entity(ent_path, {
            "entity_id": "e_org_old",
            "name": "Old",
            "entity_type": "org",
            "relations": [{
                "target": "Strategy", "target_id": "e_org_strategy",
                "target_type": "org", "label": "관련", "confidence": 0.7,
                "sources": [{
                    "doc_id": None, "weight": 0.7,
                    "role": LEGACY_SOURCE_ROLE, "ts": "2026-05-05",
                }],
            }],
        })
        counts = cascade_remove_doc_from_sources("e_document_X", self.entity_root)
        self.assertEqual(counts["entities_touched"], 0)
        self.assertEqual(counts["relations_dropped"], 0)
        fm = _read_fm(ent_path)
        self.assertEqual(len(fm["relations"]), 1)

    def test_inverse_role_dropped_normally(self):
        """role=inverse 도 일반 extract 처럼 cascade 됨 (manual 만 예외)."""
        ent_path = self.entity_root / "org" / "nvidia.md"
        _write_entity(ent_path, {
            "entity_id": "e_org_nvidia",
            "name": "NVIDIA",
            "entity_type": "org",
            "relations": [{
                "target": "Joby", "target_id": "e_org_joby",
                "target_type": "org", "label": "관련", "confidence": 0.7,
                "sources": [{
                    "doc_id": "e_document_X", "weight": 0.7,
                    "role": INVERSE_SOURCE_ROLE, "ts": "2026-05-14",
                }],
            }],
        })
        counts = cascade_remove_doc_from_sources("e_document_X", self.entity_root)
        self.assertEqual(counts["relations_dropped"], 1)


# ── 2. find_orphan_entities ─────────────────────────────────────────

class FindOrphanEntitiesTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.entity_root = self.root / "entity"
        for t in ("person", "org", "concept", "document"):
            (self.entity_root / t).mkdir(parents=True)

    def test_entity_with_no_incoming_is_orphan(self):
        # joby.md 는 deleted_doc 으로만 생성됨. 다른 누구도 안 가리킴.
        _write_entity(self.entity_root / "org" / "joby.md", {
            "entity_id": "e_org_joby",
            "name": "Joby",
            "entity_type": "org",
            "attributes": {"source_document": "joby.pdf"},
            "relations": [],
        })
        orphans = find_orphan_entities("joby.pdf", "e_document_X", self.entity_root)
        self.assertEqual(len(orphans), 1)
        self.assertEqual(orphans[0].name, "joby.md")

    def test_entity_with_incoming_is_not_orphan(self):
        # nvidia.md 는 joby.pdf 로 만들어졌지만 다른 entity(strategy.md)
        # 가 가리키고 있어 orphan 아님 (다른 doc 의 evidence 가 살아있음).
        _write_entity(self.entity_root / "org" / "nvidia.md", {
            "entity_id": "e_org_nvidia",
            "name": "NVIDIA",
            "entity_type": "org",
            "attributes": {"source_document": "joby.pdf"},
            "relations": [],
        })
        _write_entity(self.entity_root / "org" / "strategy.md", {
            "entity_id": "e_org_strategy",
            "name": "Strategy",
            "entity_type": "org",
            "attributes": {"source_document": "other.pdf"},
            "relations": [{
                "target": "NVIDIA", "target_id": "e_org_nvidia",
                "label": "관련", "confidence": 0.7,
            }],
        })
        orphans = find_orphan_entities("joby.pdf", "e_document_X", self.entity_root)
        self.assertEqual(orphans, [])

    def test_doc_entity_itself_excluded(self):
        # joby.pdf 의 doc-entity (entity_id == deleted_doc_id) 는
        # orphan 후보가 아님 — find_doc_entity_path 가 따로 처리.
        _write_entity(self.entity_root / "document" / "joby.md", {
            "entity_id": "e_document_X",
            "name": "joby",
            "entity_type": "document",
            "attributes": {"source_document": "joby.pdf"},
            "relations": [],
        })
        orphans = find_orphan_entities("joby.pdf", "e_document_X", self.entity_root)
        self.assertEqual(orphans, [])

    def test_other_source_document_ignored(self):
        _write_entity(self.entity_root / "org" / "tesla.md", {
            "entity_id": "e_org_tesla",
            "name": "Tesla",
            "entity_type": "org",
            "attributes": {"source_document": "other.pdf"},
            "relations": [],
        })
        orphans = find_orphan_entities("joby.pdf", "e_document_X", self.entity_root)
        self.assertEqual(orphans, [])


# ── 3. backup_upload_file ───────────────────────────────────────────

class BackupUploadFileTests(unittest.TestCase):
    def test_moves_to_deleted_subdir(self):
        tmp = Path(tempfile.mkdtemp())
        f = tmp / "some_uuid_report.pdf"
        f.write_text("payload", encoding="utf-8")
        dest = backup_upload_file(f, tmp)
        self.assertFalse(f.exists())
        self.assertTrue(dest.exists())
        self.assertEqual(dest.parent.name, ".deleted")
        self.assertIn("some_uuid_report.pdf", dest.name)

    def test_collision_handled(self):
        tmp = Path(tempfile.mkdtemp())
        f1 = tmp / "x.pdf"; f1.write_text("a")
        d1 = backup_upload_file(f1, tmp)
        # 다시 같은 이름 백업 — 충돌 회피
        f2 = tmp / "x.pdf"; f2.write_text("b")
        d2 = backup_upload_file(f2, tmp)
        self.assertNotEqual(d1.name, d2.name)
        self.assertTrue(d1.exists() and d2.exists())


# ── 4. cascade_delete_upload — end-to-end ──────────────────────────

class CascadeDeleteUploadIntegrationTests(unittest.TestCase):
    """uploads/<file> 삭제 → wiki/relation/vector/file 4 갈래 모두 깨끗."""

    def setUp(self):
        self.root         = Path(tempfile.mkdtemp())
        self.entity_root  = self.root / "entity"
        self.upload_dir   = self.root / "uploads"
        for t in ("person", "org", "concept", "document"):
            (self.entity_root / t).mkdir(parents=True)
        self.upload_dir.mkdir()

        # WikiGenerator stub — _generate_entity_id 와 entity_path 만 필요.
        from core.wiki_generator import WikiGenerator
        self.wg = SimpleNamespace(
            entity_path = self.entity_root,
            _generate_entity_id = WikiGenerator._generate_entity_id.__get__(
                SimpleNamespace()
            ),
        )
        # bound method 가 self._normalize_name 을 호출하므로 stub 에도 연결.
        self.wg._normalize_name = WikiGenerator._normalize_name.__get__(self.wg)
        self.wg._generate_entity_id = (
            WikiGenerator._generate_entity_id.__get__(self.wg)
        )

        # vector store stub
        self.vs = MagicMock()
        self.vs.delete_by_source.return_value = True

        # 시나리오: report.pdf 가 만든 doc + 2 extracted (Joby, NVIDIA)
        doc_id   = self.wg._generate_entity_id("report", "document")
        joby_id  = self.wg._generate_entity_id("Joby", "org")
        nv_id    = self.wg._generate_entity_id("NVIDIA", "org")

        _write_entity(self.entity_root / "document" / "report.md", {
            "entity_id": doc_id,
            "name": "report",
            "entity_type": "document",
            "attributes": {"summary": "x"},   # doc 자체는 source_document 없음
            "relations": [
                {"target": "Joby",   "target_id": joby_id,
                 "target_type": "org", "label": "관련", "confidence": 0.7,
                 "sources": [{"doc_id": doc_id, "weight": 0.7,
                              "role": EXTRACT_SOURCE_ROLE, "ts": "t"}]},
                {"target": "NVIDIA", "target_id": nv_id,
                 "target_type": "org", "label": "관련", "confidence": 0.7,
                 "sources": [{"doc_id": doc_id, "weight": 0.7,
                              "role": EXTRACT_SOURCE_ROLE, "ts": "t"}]},
            ],
        })
        _write_entity(self.entity_root / "org" / "joby.md", {
            "entity_id": joby_id,
            "name": "Joby",
            "entity_type": "org",
            "attributes": {"source_document": "report.pdf"},
            "relations": [{
                "target": "NVIDIA", "target_id": nv_id,
                "target_type": "org", "label": "관련", "confidence": 0.8,
                "sources": [{"doc_id": doc_id, "weight": 0.8,
                             "role": EXTRACT_SOURCE_ROLE, "ts": "t"}],
            }],
        })
        _write_entity(self.entity_root / "org" / "nvidia.md", {
            "entity_id": nv_id,
            "name": "NVIDIA",
            "entity_type": "org",
            "attributes": {"source_document": "report.pdf"},
            "relations": [{
                "target": "Joby", "target_id": joby_id,
                "target_type": "org", "label": "관련", "confidence": 0.8,
                "sources": [{"doc_id": doc_id, "weight": 0.8,
                             "role": INVERSE_SOURCE_ROLE, "ts": "t"}],
            }],
        })
        # uploads/{uuid}_report.pdf
        self.physical = f"{uuid.uuid4()}_report.pdf"
        (self.upload_dir / self.physical).write_text("payload",
                                                     encoding="utf-8")

        self.doc_id  = doc_id
        self.joby_id = joby_id
        self.nv_id   = nv_id

    def test_full_cascade_clears_all_artifacts(self):
        summary = cascade_delete_upload(
            self.physical,
            wiki_generator = self.wg,
            vector_store   = self.vs,
            upload_dir     = self.upload_dir,
            user_role      = "admin",
        )

        # 1) 물리 파일이 .deleted/ 로 백업됨
        self.assertFalse((self.upload_dir / self.physical).exists())
        deleted_dir = self.upload_dir / ".deleted"
        self.assertTrue(deleted_dir.exists())
        self.assertEqual(len(list(deleted_dir.iterdir())), 1)

        # 2) vector store 호출 (filename 원본 = report.pdf)
        self.vs.delete_by_source.assert_called_once_with("report.pdf")

        # 3) doc entity 파일 사라짐
        self.assertFalse((self.entity_root / "document" / "report.md").exists())

        # 4) extracted entity 중 incoming 0 인 것은 사라짐.
        #    이 시나리오에서 Joby ↔ NVIDIA 양방향 relation 이 있는데
        #    cascade_remove_doc_from_sources 가 doc_id 매칭 source 를
        #    제거 → relation 도 사라짐 (단일 source 였으므로) → 양쪽 다
        #    incoming 0 → 양쪽 다 orphan.
        self.assertFalse((self.entity_root / "org" / "joby.md").exists())
        self.assertFalse((self.entity_root / "org" / "nvidia.md").exists())

        # 5) summary 값 검증
        self.assertEqual(summary["original_filename"], "report.pdf")
        self.assertEqual(summary["doc_entity_id"], self.doc_id)
        self.assertTrue(summary["doc_entity_deleted"])
        self.assertEqual(summary["orphan_entities_deleted"], 2)
        self.assertTrue(summary["vector_deleted"])
        self.assertIn(".deleted", summary["file_backup"]
                      .replace("\\", "/"))
        # 4 relations 모두 doc_id 매칭 single-source 였으므로 전부 drop:
        #   doc/report.md → Joby
        #   doc/report.md → NVIDIA
        #   org/joby.md   → NVIDIA  (extract)
        #   org/nvidia.md → Joby    (inverse)
        self.assertEqual(summary["counts"]["relations_dropped"], 4)
        self.assertEqual(summary["counts"]["entities_touched"], 3)

    def test_other_doc_with_incoming_keeps_entity(self):
        """별도 doc 이 NVIDIA 를 가리키면 report.pdf 삭제 시 NVIDIA 는 살아남고
        confidence 만 감소 (또는 relation drop) 한다."""
        # 추가 entity: Strategy (other.pdf 출처) → NVIDIA 를 가리킴
        nv_id = self.nv_id
        _write_entity(self.entity_root / "org" / "strategy.md", {
            "entity_id": "e_org_strategy",
            "name": "Strategy",
            "entity_type": "org",
            "attributes": {"source_document": "other.pdf"},
            "relations": [{
                "target": "NVIDIA", "target_id": nv_id,
                "target_type": "org", "label": "관련", "confidence": 0.6,
                "sources": [{"doc_id": "e_document_other", "weight": 0.6,
                             "role": EXTRACT_SOURCE_ROLE, "ts": "t"}],
            }],
        })

        cascade_delete_upload(
            self.physical,
            wiki_generator = self.wg,
            vector_store   = self.vs,
            upload_dir     = self.upload_dir,
            user_role      = "admin",
        )

        # Strategy 는 그대로
        self.assertTrue((self.entity_root / "org" / "strategy.md").exists())
        # NVIDIA 는 incoming 이 있으므로 살아남음
        self.assertTrue((self.entity_root / "org" / "nvidia.md").exists())
        # NVIDIA 의 relation 은 incoming inverse 만 있었고 doc_id 매칭
        # source 였으므로 drop. 남는 relation 0
        fm = _read_fm(self.entity_root / "org" / "nvidia.md")
        self.assertEqual(fm.get("relations") or [], [])
        # Joby 는 incoming 0 → orphan (Strategy 는 NVIDIA 만 가리킴)
        self.assertFalse((self.entity_root / "org" / "joby.md").exists())

    def test_manual_source_survives_doc_delete(self):
        """admin 이 그래프 에디터로 추가한 manual source 는 cascade 무시."""
        # NVIDIA→Joby relation 에 manual source 한 줄 추가
        nv_path = self.entity_root / "org" / "nvidia.md"
        fm = _read_fm(nv_path)
        fm["relations"][0]["sources"].append({
            "doc_id": None, "weight": 0.9,
            "role":   MANUAL_SOURCE_ROLE,
            "author": "admin", "ts": "t",
        })
        _write_entity(nv_path, fm)

        cascade_delete_upload(
            self.physical,
            wiki_generator = self.wg,
            vector_store   = self.vs,
            upload_dir     = self.upload_dir,
            user_role      = "admin",
        )

        # NVIDIA 가 살아있고 (manual source 가 있는 relation 이 남아 incoming
        # Joby 도 살아있어야)
        self.assertTrue(nv_path.exists())
        fm_after = _read_fm(nv_path)
        rels = fm_after.get("relations") or []
        self.assertEqual(len(rels), 1)
        self.assertEqual(rels[0]["sources"][0]["role"], MANUAL_SOURCE_ROLE)
        # Joby 도 incoming(NVIDIA→Joby) 가 살아있어 살아남음
        self.assertTrue((self.entity_root / "org" / "joby.md").exists())

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            cascade_delete_upload(
                "no_such_uuid_report.pdf",
                wiki_generator = self.wg,
                vector_store   = self.vs,
                upload_dir     = self.upload_dir,
            )


# ── 5. find_doc_entity_path ─────────────────────────────────────────

class FindDocEntityPathTests(unittest.TestCase):
    def test_returns_path_for_matching_eid(self):
        root = Path(tempfile.mkdtemp())
        (root / "document").mkdir()
        p = root / "document" / "report.md"
        _write_entity(p, {"entity_id": "e_document_abc", "name": "report"})
        self.assertEqual(find_doc_entity_path("e_document_abc", root), p)

    def test_returns_none_when_missing(self):
        root = Path(tempfile.mkdtemp())
        (root / "document").mkdir()
        self.assertIsNone(find_doc_entity_path("e_document_missing", root))


if __name__ == "__main__":
    unittest.main()
