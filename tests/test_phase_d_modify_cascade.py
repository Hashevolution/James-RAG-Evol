"""Phase D (Knowledge Cascade) — modify cascade 검증.

docs/design/v0.3-knowledge-cascade.md §6 — Phase D.

본 테스트는 ``core/cascade.py`` 의 Phase D 함수 3 종을 cover:

  1. ``load_extraction_sidecar`` — 사이드카 JSON 로드 / 부재 / 손상
  2. ``diff_triples`` — entities + relations 의 added/removed/kept 분류
     (label/name lowercase 정규화로 LLM 비결정성 일부 흡수)
  3. ``cascade_modify_doc`` (통합) — 실제 wiki 재조립 시나리오:
     - 기존 doc 의 source wipe + orphan sweep
     - manual source 보존 (Phase C 와 같은 룰)
     - 새 sidecar 생성
     - 사이드카 없는 경우 (Phase D 이전 업로드) fallback 동작

production wiki 무영향 — tempfile 격리.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml  # noqa: I001

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.console import ensure_utf8_console
ensure_utf8_console()

from core.cascade import (
    cascade_modify_doc,
    diff_triples,
    load_extraction_sidecar,
)
from core.relations_schema import (
    EXTRACT_SOURCE_ROLE,
    INVERSE_SOURCE_ROLE,
    MANUAL_SOURCE_ROLE,
)


# ── 1. load_extraction_sidecar ──────────────────────────────────────

class LoadSidecarTests(unittest.TestCase):
    def test_missing_returns_none(self):
        tmp = Path(tempfile.mkdtemp())
        self.assertIsNone(load_extraction_sidecar("nope.pdf", tmp))

    def test_loads_valid_sidecar(self):
        tmp = Path(tempfile.mkdtemp())
        payload = {
            "filename": "x.pdf",
            "extraction": {"entities": [{"name": "A", "type": "org"}],
                           "relations": []},
        }
        (tmp / "x.pdf.extraction.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        loaded = load_extraction_sidecar("x.pdf", tmp)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["filename"], "x.pdf")
        self.assertEqual(loaded["extraction"]["entities"][0]["name"], "A")

    def test_corrupt_returns_none(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "x.pdf.extraction.json").write_text("{not json", encoding="utf-8")
        self.assertIsNone(load_extraction_sidecar("x.pdf", tmp))


# ── 2. diff_triples ─────────────────────────────────────────────────

class DiffTriplesTests(unittest.TestCase):
    def test_added_entity(self):
        old = {"extraction": {"entities": [{"name": "A", "type": "org"}],
                              "relations": []}}
        new = {"entities": [{"name": "A", "type": "org"},
                            {"name": "B", "type": "concept"}],
               "relations": []}
        d = diff_triples(old, new)
        self.assertEqual(len(d["added_entities"]), 1)
        self.assertEqual(d["added_entities"][0]["name"], "B")
        self.assertEqual(d["removed_entities"], [])

    def test_removed_entity(self):
        old = {"extraction": {"entities": [{"name": "A", "type": "org"},
                                           {"name": "B", "type": "concept"}],
                              "relations": []}}
        new = {"entities": [{"name": "A", "type": "org"}],
               "relations": []}
        d = diff_triples(old, new)
        self.assertEqual(len(d["removed_entities"]), 1)
        self.assertEqual(d["removed_entities"][0]["name"], "B")

    def test_kept_triple(self):
        old = {"extraction": {"entities": [],
                              "relations": [{"source": "A", "target": "B",
                                             "label": "관련", "confidence": 0.7}]}}
        new = {"entities": [],
               "relations": [{"source": "A", "target": "B",
                              "label": "관련", "confidence": 0.8}]}
        d = diff_triples(old, new)
        # weight 만 변한 건 kept
        self.assertEqual(len(d["kept_triples"]), 1)
        self.assertEqual(d["added_triples"], [])
        self.assertEqual(d["removed_triples"], [])

    def test_label_case_insensitive(self):
        """LLM 이 'RELATED_TO' 와 'related_to' 를 섞어 내도 같은 triple."""
        old = {"extraction": {"entities": [],
                              "relations": [{"source": "A", "target": "B",
                                             "label": "RELATED_TO", "confidence": 0.7}]}}
        new = {"entities": [],
               "relations": [{"source": "A", "target": "B",
                              "label": "related_to", "confidence": 0.7}]}
        d = diff_triples(old, new)
        self.assertEqual(len(d["kept_triples"]), 1)

    def test_removed_and_added_triple(self):
        old = {"extraction": {"entities": [],
                              "relations": [{"source": "A", "target": "B", "label": "관련",
                                             "confidence": 0.7},
                                            {"source": "C", "target": "D", "label": "관련",
                                             "confidence": 0.6}]}}
        new = {"entities": [],
               "relations": [{"source": "A", "target": "B", "label": "관련",
                              "confidence": 0.7},
                             {"source": "E", "target": "F", "label": "관련",
                              "confidence": 0.5}]}
        d = diff_triples(old, new)
        self.assertEqual(len(d["kept_triples"]), 1)
        self.assertEqual(len(d["added_triples"]), 1)
        self.assertEqual(len(d["removed_triples"]), 1)
        self.assertEqual(d["added_triples"][0]["source"], "E")
        self.assertEqual(d["removed_triples"][0]["source"], "C")

    def test_old_none_means_all_added(self):
        """사이드카 부재 (None) → 모두 신규."""
        new = {"entities": [{"name": "A", "type": "org"}],
               "relations": [{"source": "A", "target": "B", "label": "관련"}]}
        d = diff_triples(None, new)
        self.assertEqual(len(d["added_entities"]), 1)
        self.assertEqual(len(d["added_triples"]), 1)
        self.assertEqual(d["removed_entities"], [])
        self.assertEqual(d["removed_triples"], [])


# ── 3. cascade_modify_doc — 통합 ────────────────────────────────────

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


class CascadeModifyDocIntegrationTests(unittest.TestCase):
    """전체 cascade_modify_doc 호출 — 기존 doc 의 wiki 가 새 content 의
    추출로 정확히 교체되는지 검증."""

    def setUp(self):
        self.tmp_root = Path(tempfile.mkdtemp())
        self.upload_dir  = self.tmp_root / "uploads"
        self.upload_dir.mkdir()

        # 진짜 WikiGenerator 사용 — WIKI_DIR 만 패치해 격리.
        self.wiki_patcher = patch("config.WIKI_DIR", str(self.tmp_root / "wiki"))
        self.wiki_patcher.start()
        import core.wiki_generator as wg_mod
        self._orig_wiki_dir = wg_mod.WIKI_DIR
        wg_mod.WIKI_DIR = str(self.tmp_root / "wiki")
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
        self.entity_root = self.wg.entity_path

        # 기존 doc + 2 entity 시나리오: report.pdf → Joby, NVIDIA
        doc_id   = self.wg._generate_entity_id("report", "document")
        joby_id  = self.wg._generate_entity_id("Joby", "org")
        nv_id    = self.wg._generate_entity_id("NVIDIA", "org")

        _write_entity(self.entity_root / "document" / "report.md", {
            "entity_id": doc_id, "name": "report",
            "normalized_name": "report", "aliases": ["report"],
            "entity_type": "document",
            "attributes": {"summary": "old"},
            "relations": [
                {"target": "Joby", "target_id": joby_id,
                 "target_type": "org", "type": "RELATED_TO", "label": "관련",
                 "confidence": 0.7,
                 "sources": [{"doc_id": doc_id, "weight": 0.7,
                              "role": EXTRACT_SOURCE_ROLE, "ts": "t"}]},
                {"target": "NVIDIA", "target_id": nv_id,
                 "target_type": "org", "type": "RELATED_TO", "label": "관련",
                 "confidence": 0.7,
                 "sources": [{"doc_id": doc_id, "weight": 0.7,
                              "role": EXTRACT_SOURCE_ROLE, "ts": "t"}]},
            ],
        })
        _write_entity(self.entity_root / "org" / "joby.md", {
            "entity_id": joby_id, "name": "Joby",
            "normalized_name": "joby", "aliases": ["Joby"],
            "entity_type": "org",
            "attributes": {"source_document": "report.pdf"},
            "relations": [{
                "target": "NVIDIA", "target_id": nv_id,
                "target_type": "org", "type": "RELATED_TO", "label": "관련",
                "confidence": 0.8,
                "sources": [{"doc_id": doc_id, "weight": 0.8,
                             "role": EXTRACT_SOURCE_ROLE, "ts": "t"}],
            }],
        })
        _write_entity(self.entity_root / "org" / "nvidia.md", {
            "entity_id": nv_id, "name": "NVIDIA",
            "normalized_name": "nvidia", "aliases": ["NVIDIA"],
            "entity_type": "org",
            "attributes": {"source_document": "report.pdf"},
            "relations": [{
                "target": "Joby", "target_id": joby_id,
                "target_type": "org", "type": "RELATED_TO", "label": "관련",
                "confidence": 0.8,
                "sources": [{"doc_id": doc_id, "weight": 0.8,
                             "role": INVERSE_SOURCE_ROLE, "ts": "t"}],
            }],
        })

        # 물리 파일 + 기존 사이드카
        import uuid as _uuid
        self.physical = f"{_uuid.uuid4()}_report.pdf"
        (self.upload_dir / self.physical).write_text("old text",
                                                     encoding="utf-8")
        old_sidecar = {
            "filename": "report.pdf",
            "extraction": {
                "entities":  [{"name": "Joby", "type": "org"},
                              {"name": "NVIDIA", "type": "org"}],
                "relations": [{"source": "Joby", "target": "NVIDIA",
                               "label": "관련", "confidence": 0.8}],
            },
        }
        (self.upload_dir / (self.physical + ".extraction.json")).write_text(
            json.dumps(old_sidecar, ensure_ascii=False), encoding="utf-8")

        self.wg._build_entity_id_index()

        # LLM 추출 결정적 fixture — 새 content 는 Joby + Anthropic
        # (NVIDIA 빠지고 Anthropic 추가).
        self._new_extraction = {
            "entities": [
                {"name": "Joby",      "type": "org",
                 "description": "eVTOL maker"},
                {"name": "Anthropic", "type": "org",
                 "description": "AI safety lab"},
            ],
            "relations": [
                {"source": "Joby", "target": "Anthropic",
                 "label": "관련", "confidence": 0.7},
            ],
        }
        self.wg._llm_extract_document_entities = (
            lambda *a, **kw: self._new_extraction
        )

        # vector store mock
        self.vs = MagicMock()
        self.vs.delete_by_source.return_value = True

        self.wg._build_entity_id_index()

        self.doc_id  = doc_id
        self.joby_id = joby_id
        self.nv_id   = nv_id

    def tearDown(self):
        self.wiki_patcher.stop()
        self.verify_patcher.stop()
        self.vs_patcher.stop()
        self.router_patcher.stop()
        import core.wiki_generator as wg_mod
        wg_mod.WIKI_DIR = self._orig_wiki_dir

    @patch("core.memory.verify_before_write",
           return_value=(True, "ok", 0.99))
    def test_modify_replaces_doc_sources_and_writes_new_sidecar(self, _mock):
        summary = cascade_modify_doc(
            self.physical,
            "new text — Joby x Anthropic",
            wiki_generator = self.wg,
            vector_store   = self.vs,
            upload_dir     = self.upload_dir,
            new_metadata   = {},
            user_role      = "admin",
        )

        # 1) 물리 파일 = 새 content + .deleted/ 백업 1개
        physical_path = self.upload_dir / self.physical
        self.assertTrue(physical_path.exists())
        self.assertEqual(physical_path.read_text(encoding="utf-8"),
                         "new text — Joby x Anthropic")
        deleted_dir = self.upload_dir / ".deleted"
        self.assertEqual(len(list(deleted_dir.iterdir())), 1)

        # 2) 새 sidecar 가 작성됨 (Anthropic 포함)
        new_sidecar = json.loads(
            (self.upload_dir / (self.physical + ".extraction.json"))
            .read_text(encoding="utf-8")
        )
        names = [e["name"] for e in new_sidecar["extraction"]["entities"]]
        self.assertIn("Anthropic", names)

        # 3) NVIDIA entity 는 orphan 으로 사라짐 (다른 incoming 없음)
        self.assertFalse((self.entity_root / "org" / "nvidia.md").exists())

        # 4) Joby entity 는 살아있고 새 relation (→ Anthropic) 보유
        joby_fm = _read_fm(self.entity_root / "org" / "joby.md")
        joby_rels = joby_fm.get("relations") or []
        targets = [r.get("target") for r in joby_rels]
        self.assertIn("Anthropic", targets)
        # NVIDIA 향한 relation 은 사라져야
        self.assertNotIn("NVIDIA", targets)

        # 5) Anthropic 새 entity 생성됨
        self.assertTrue((self.entity_root / "org" / "anthropic.md").exists())

        # 6) summary 검증
        self.assertEqual(summary["original_filename"], "report.pdf")
        self.assertTrue(summary["sidecar_present"])
        self.assertTrue(summary["vector_replaced"])
        self.assertGreater(summary["orphan_entities_deleted"], 0)
        self.assertEqual(summary["doc_entity_id"], self.doc_id)

        # 7) vector store: delete_by_source 호출 1회
        self.vs.delete_by_source.assert_called_with("report.pdf")

    @patch("core.memory.verify_before_write",
           return_value=(True, "ok", 0.99))
    def test_manual_source_survives_modify(self, _mock):
        """그래프 에디터로 추가한 manual source 가 modify cascade 후에도
        살아남는지 (Phase C 의 cascade_remove 룰 정합)."""
        # Joby → NVIDIA 의 source 에 manual 한 줄 추가
        joby_path = self.entity_root / "org" / "joby.md"
        fm = _read_fm(joby_path)
        fm["relations"][0]["sources"].append({
            "doc_id": None, "weight": 0.9, "role": MANUAL_SOURCE_ROLE,
            "author": "admin", "ts": "t",
        })
        _write_entity(joby_path, fm)

        cascade_modify_doc(
            self.physical,
            "new text",
            wiki_generator = self.wg,
            vector_store   = self.vs,
            upload_dir     = self.upload_dir,
            new_metadata   = {},
            user_role      = "admin",
        )

        # Joby 는 살아있고 NVIDIA 향한 relation 도 manual 덕에 유지.
        # NVIDIA entity 도 incoming 이 있어 orphan 아님 → 유지.
        self.assertTrue((self.entity_root / "org" / "joby.md").exists())
        self.assertTrue((self.entity_root / "org" / "nvidia.md").exists())
        joby_rels = (_read_fm(joby_path).get("relations") or [])
        nv_targets = [r.get("target") for r in joby_rels]
        self.assertIn("NVIDIA", nv_targets)

    @patch("core.memory.verify_before_write",
           return_value=(True, "ok", 0.99))
    def test_no_sidecar_fallback(self, _mock):
        """사이드카 없는 (Phase D 이전) 업로드도 wipe+reingest 로 동작."""
        # 사이드카 파일 삭제
        (self.upload_dir / (self.physical + ".extraction.json")).unlink()

        summary = cascade_modify_doc(
            self.physical,
            "new text",
            wiki_generator = self.wg,
            vector_store   = self.vs,
            upload_dir     = self.upload_dir,
            new_metadata   = {},
            user_role      = "admin",
        )

        self.assertFalse(summary["sidecar_present"])
        # diff 정보는 None (계산하지 않음)
        self.assertIsNone(summary["diff"])
        # cascade 자체는 정상 수행 — Anthropic 새 entity 만들어짐
        self.assertTrue((self.entity_root / "org" / "anthropic.md").exists())
        # 새 sidecar 는 생성됨 (Phase D 이후 정합)
        self.assertTrue(
            (self.upload_dir / (self.physical + ".extraction.json")).exists()
        )

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            cascade_modify_doc(
                "no_such_uuid_x.pdf",
                "new text",
                wiki_generator = self.wg,
                vector_store   = self.vs,
                upload_dir     = self.upload_dir,
            )


if __name__ == "__main__":
    unittest.main()
