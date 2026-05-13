"""Phase B (Knowledge Cascade) — ingestion 가 sources 를 직접 쓰는지 검증.

docs/design/v0.3-knowledge-cascade.md §4 / §8 — Phase B.

본 테스트는 다음 3 레이어를 cover:

  1. ``_build_entity_relations`` 단위: doc_id 가 주어졌을 때 outgoing 에
     ``role=extract``, inverse 에 ``role=inverse`` 를 stamp 하는지.
     doc_id 가 ``None`` 이면 (legacy caller) sources 미부착인지.
  2. ``create_entity_file`` 단위: caller 가 ``sources`` 를 채워 보내면
     frontmatter 에 그대로 쓰고 ``confidence`` 를 sources 로부터 derive
     하는지. sources 없으면 기존 ``confidence`` 그대로 통과하는지.
  3. ``process_document_for_entities`` 통합: LLM 추출 결과를 mock 한 뒤
     실제 frontmatter 가 entity / inverse / doc-entity 3 갈래 모두에
     올바른 sources 를 갖는지.

production wiki 에 영향 없음 — WikiGenerator 인스턴스를 ``tempfile``
WIKI_DIR 로 monkey-patch 해서 격리.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import yaml  # noqa: I001

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Windows cp949 console 환경에서 wiki_generator 의 print("[TRUST] ✅ ...")
# 가 UnicodeEncodeError 를 던져 create_entity_file 이 그 자리에서 실패.
# bench.py 와 동일 패턴으로 테스트 시작 시 stdout/stderr 를 UTF-8 로 강제.
from utils.console import ensure_utf8_console
ensure_utf8_console()

from core.relations_schema import (
    EXTRACT_SOURCE_ROLE,
    INVERSE_SOURCE_ROLE,
    compute_confidence_from_sources,
)


# ── 1. _build_entity_relations 단위 ─────────────────────────────────

class BuildEntityRelationsSourcesTests(unittest.TestCase):
    """outgoing/inverse 양쪽 모두 sources 를 stamp 하는지."""

    def setUp(self):
        from core.wiki_generator import WikiGenerator
        # 메서드 자체는 self 만 받으므로 인스턴스 없이 unbound 로 호출 가능.
        # _inverse_label_for 는 staticmethod 라 stub 에 별도 binding 불필요.
        self.fn = WikiGenerator._build_entity_relations
        self.stub = SimpleNamespace()
        # _inverse_label_for 는 static 이므로 클래스 attribute 그대로 사용.
        self.stub._inverse_label_for = WikiGenerator._inverse_label_for

    def _raw_triples(self):
        return [
            {"source": "Joby", "target": "NVIDIA", "label": "관련",
             "confidence": 0.8},
            {"source": "FAA",  "target": "Joby",   "label": "감독",
             "confidence": 0.7},
        ]

    def test_outgoing_gets_role_extract(self):
        rels = self.fn(self.stub, "Joby", self._raw_triples(),
                       doc_id="e_document_abc", ts="2026-05-14T10:00:00")
        out = [r for r in rels if r["target"] == "NVIDIA"]
        self.assertEqual(len(out), 1, "outgoing Joby→NVIDIA 가 1개 있어야")
        sources = out[0].get("sources")
        self.assertIsInstance(sources, list)
        self.assertEqual(len(sources), 1)
        s = sources[0]
        self.assertEqual(s["doc_id"], "e_document_abc")
        self.assertEqual(s["role"], EXTRACT_SOURCE_ROLE)
        self.assertEqual(s["weight"], 0.8)
        self.assertEqual(s["ts"], "2026-05-14T10:00:00")

    def test_inverse_gets_role_inverse(self):
        rels = self.fn(self.stub, "Joby", self._raw_triples(),
                       doc_id="e_document_abc", ts="2026-05-14T10:00:00")
        inv = [r for r in rels if r["target"] == "FAA"]
        self.assertEqual(len(inv), 1, "inverse FAA→Joby 가 Joby 쪽에 1개 있어야")
        sources = inv[0].get("sources")
        self.assertIsInstance(sources, list)
        s = sources[0]
        self.assertEqual(s["doc_id"], "e_document_abc")
        self.assertEqual(s["role"], INVERSE_SOURCE_ROLE,
            "incoming(target=self) 측은 role=inverse 여야")
        self.assertEqual(s["weight"], 0.7)

    def test_no_doc_id_legacy_path_no_sources(self):
        """doc_id=None (구 호출자) → sources 필드 미부착, 기존 동작 보존."""
        rels = self.fn(self.stub, "Joby", self._raw_triples(),
                       doc_id=None, ts=None)
        self.assertGreater(len(rels), 0)
        for r in rels:
            self.assertNotIn("sources", r,
                "doc_id 없이 호출된 경로는 sources 를 추가하면 안 됨")
            self.assertIn("confidence", r)

    def test_dedup_keeps_first_source(self):
        """같은 (target, label) 가 중복 등장하면 첫 번째만 살아남고
        sources 도 그 한 번분만 stamp 된다. 같은 doc 안 중복은 weight
        팽창이 아니라 무시되어야 (관련 LLM 노이즈 방어)."""
        dups = [
            {"source": "Joby", "target": "NVIDIA", "label": "관련",
             "confidence": 0.6},
            {"source": "Joby", "target": "NVIDIA", "label": "관련",
             "confidence": 0.9},
        ]
        rels = self.fn(self.stub, "Joby", dups,
                       doc_id="e_document_xyz", ts="2026-05-14T10:00:00")
        out = [r for r in rels if r["target"] == "NVIDIA"]
        self.assertEqual(len(out), 1)
        self.assertEqual(len(out[0]["sources"]), 1)
        # 첫 번째 (conf=0.6) 가 우선
        self.assertEqual(out[0]["sources"][0]["weight"], 0.6)


# ── 2. create_entity_file 단위 ──────────────────────────────────────

class CreateEntityFileSourcesPropagationTests(unittest.TestCase):
    """caller 가 미리 채운 sources 를 frontmatter 에 그대로 쓰고
    confidence 를 sources 로부터 derive 한다."""

    def setUp(self):
        # WikiGenerator 가 WIKI_DIR 을 통째로 import 하므로 monkey-patch.
        self.tmp = tempfile.mkdtemp()
        self.wiki_dir_patcher = patch("config.WIKI_DIR", self.tmp)
        self.wiki_dir_patcher.start()
        # core.wiki_generator 가 module-load 시 import 한 WIKI_DIR 도 갈아끼움
        import core.wiki_generator as wg_mod
        self._orig_wiki_dir = wg_mod.WIKI_DIR
        wg_mod.WIKI_DIR = self.tmp

        # vector_store / verify_before_write 의 side effect 비활성.
        # (테스트는 frontmatter 만 검증)
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

    def _read_fm(self, name: str, etype: str) -> dict:
        path = self.wg.entity_path / etype / f"{name.lower()}.md"
        text = path.read_text(encoding="utf-8")
        body = text.split("---", 2)[1]
        return yaml.safe_load(body)

    def test_caller_sources_preserved_and_confidence_derived(self):
        sources_in = [{
            "doc_id": "e_document_abc",
            "weight": 0.8,
            "role":   EXTRACT_SOURCE_ROLE,
            "ts":     "2026-05-14T10:00:00",
        }]
        entity = {
            "name": "Joby",
            "type": "org",
            "attributes": {"summary": "test"},
            "relations": [{
                "target": "NVIDIA",
                "target_type": "org",
                "label": "관련",
                "confidence": 0.5,         # 의도적으로 mismatched
                "sources": sources_in,
            }],
            "source_type": "test",
        }
        self.wg.create_entity_file(entity, "joby.md", ["chunk1"])

        fm = self._read_fm("Joby", "org")
        rels = fm.get("relations", [])
        self.assertEqual(len(rels), 1)
        rel = rels[0]
        self.assertEqual(rel.get("sources"), sources_in)
        # confidence 는 derived (caller-given 0.5 가 아니라 weight=0.8 reflect)
        self.assertEqual(rel["confidence"],
                         compute_confidence_from_sources(sources_in))

    def test_no_sources_legacy_confidence_path(self):
        """입력 rel 에 sources 없으면 confidence 그대로 (back-compat)."""
        entity = {
            "name": "Strategy",
            "type": "org",
            "attributes": {"summary": "test"},
            "relations": [{
                "target": "비트코인",
                "target_type": "concept",
                "label": "관련",
                "confidence": 0.42,
            }],
            "source_type": "test",
        }
        self.wg.create_entity_file(entity, "doc.md", ["chunk2"])

        fm = self._read_fm("Strategy", "org")
        rels = fm.get("relations", [])
        self.assertEqual(len(rels), 1)
        self.assertNotIn("sources", rels[0])
        self.assertEqual(rels[0]["confidence"], 0.42)


# ── 3. process_document_for_entities 통합 ───────────────────────────

class ProcessDocumentSourcesIntegrationTests(unittest.TestCase):
    """LLM 추출 mock 후 실제 frontmatter (entity + inverse + doc) 가
    sources 를 갖는지 확인."""

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

        # LLM 추출을 결정적 fixture 로 대체.
        self.extracted = {
            "entities": [
                {"name": "Joby",   "type": "org",
                 "description": "eVTOL maker"},
                {"name": "NVIDIA", "type": "org",
                 "description": "GPU maker"},
            ],
            "relations": [
                {"source": "Joby", "target": "NVIDIA",
                 "label": "관련", "confidence": 0.8},
            ],
        }
        self.wg._llm_extract_document_entities = (
            lambda *a, **kw: self.extracted
        )

    def tearDown(self):
        self.wiki_dir_patcher.stop()
        self.verify_patcher.stop()
        self.vs_patcher.stop()
        self.router_patcher.stop()
        import core.wiki_generator as wg_mod
        wg_mod.WIKI_DIR = self._orig_wiki_dir

    def _read_fm(self, name: str, etype: str) -> dict:
        path = self.wg.entity_path / etype / f"{name.lower()}.md"
        text = path.read_text(encoding="utf-8")
        body = text.split("---", 2)[1]
        return yaml.safe_load(body)

    def test_end_to_end_sources_stamped_all_three_paths(self):
        filename = "joby_nvidia_partnership.md"
        ids = self.wg.process_document_for_entities(
            filename=filename,
            content="Joby and NVIDIA partnership.",
            chunk_ids=["c1"],
            user_role="admin",
            metadata={},
        )
        # entity 2개 + doc 1개 = 3
        self.assertGreaterEqual(len(ids), 2)

        doc_name = os.path.splitext(filename)[0]
        doc_id   = self.wg._generate_entity_id(doc_name, "document")

        # 1) Joby 의 outgoing relation → NVIDIA, role=extract, doc_id 매칭
        joby_fm = self._read_fm("Joby", "org")
        joby_rels = joby_fm.get("relations", [])
        out_to_nvidia = [r for r in joby_rels if r.get("target") == "NVIDIA"]
        self.assertEqual(len(out_to_nvidia), 1)
        srcs = out_to_nvidia[0].get("sources")
        self.assertIsInstance(srcs, list)
        self.assertEqual(srcs[0]["doc_id"], doc_id)
        self.assertEqual(srcs[0]["role"], EXTRACT_SOURCE_ROLE)
        self.assertEqual(srcs[0]["weight"], 0.8)

        # 2) NVIDIA 의 inverse relation → Joby, role=inverse, 같은 doc_id
        nv_fm = self._read_fm("NVIDIA", "org")
        nv_rels = nv_fm.get("relations", [])
        inv_to_joby = [r for r in nv_rels if r.get("target") == "Joby"]
        self.assertEqual(len(inv_to_joby), 1,
            "Phase B: inverse 가 ingestion 시점에 stamp 되어야")
        inv_srcs = inv_to_joby[0].get("sources")
        self.assertIsInstance(inv_srcs, list)
        self.assertEqual(inv_srcs[0]["doc_id"], doc_id)
        self.assertEqual(inv_srcs[0]["role"], INVERSE_SOURCE_ROLE)

        # 3) doc entity 의 outgoing 도 sources 를 가짐 (self-source)
        doc_fm = self._read_fm(doc_name, "document")
        doc_rels = doc_fm.get("relations", [])
        # doc 가 extracted entities 와 RELATED_TO 로 묶인다
        targets = {r.get("target") for r in doc_rels}
        self.assertIn("Joby",   targets)
        self.assertIn("NVIDIA", targets)
        for r in doc_rels:
            srcs = r.get("sources")
            self.assertIsInstance(srcs, list,
                "doc-entity outgoing 도 sources 필수 (Phase C cascade 정합)")
            self.assertEqual(srcs[0]["doc_id"], doc_id)
            self.assertEqual(srcs[0]["role"], EXTRACT_SOURCE_ROLE)

    def test_confidence_consistent_with_sources(self):
        """confidence 는 sources 의 weight 와 compute_confidence_from_sources
        결과가 일치 — derive 가 storage 와 동기화."""
        self.wg.process_document_for_entities(
            filename="x.md",
            content="x",
            chunk_ids=["c1"],
        )
        joby_fm = self._read_fm("Joby", "org")
        for r in joby_fm.get("relations", []):
            srcs = r.get("sources")
            if not srcs:
                continue
            self.assertAlmostEqual(
                r["confidence"],
                compute_confidence_from_sources(srcs),
                places=6,
                msg=f"relation {r} confidence ≠ derive(sources)",
            )


if __name__ == "__main__":
    unittest.main()
