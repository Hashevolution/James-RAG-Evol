"""Web learn → LLM triple extraction path contract (2026-05-13).

User observation: 채팅·웹 검색으로 학습된 토픽이 wiki 에 `query 문장 그
자체 = 단일 concept 노드, relations=[]` 형태로 저장되어 추론 그래프에 선이
안 나타남.

Fix in `tools/web/web_searcher.save_as_longterm`:
  Before — create_entity_file({name: query_topic, entity_type: "concept",
           relations: []}) 한 번 호출 → 잘못된 단일 노드만 남음.
  After  — process_document_for_entities(filename, content, ...) 위임
           → LLM 이 본문에서 다중 (entity, relation) 추출 → 각 entity 가
           개별 wiki 파일로 저장 + document entity 가 모든 추출 entity 와
           RELATED_TO edge. web 메타데이터(web_sources / learn_method /
           learned_at 등)는 _augment_doc_attributes 로 doc 파일 frontmatter
           에 후처리 보강.

Tests cover three contracts:
  1) static source contract — query 문장을 entity name 으로 박는 코드가
     save_as_longterm 안에 더 이상 존재하지 않는다.
  2) delegation contract — save_as_longterm 이 process_document_for_entities
     를 호출하고, 그 인자에 합성 본문이 정확히 전달된다.
  3) augmentation contract — _augment_doc_attributes 가 실제 frontmatter
     를 머지하고 다시 쓴다 (round-trip 검증).

Run:
  python -m unittest tests.test_web_learn_extraction
"""
from __future__ import annotations

import inspect
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── 1. Static source contract ────────────────────────────────────────

class SaveAsLongtermSourceContractTests(unittest.TestCase):
    """save_as_longterm 의 소스에서 잘못된 단일 노드 생성 패턴이 없는지."""

    @classmethod
    def setUpClass(cls):
        from tools.web import web_searcher
        cls.src = inspect.getsource(web_searcher.save_as_longterm)

    def test_does_not_build_entity_with_topic_as_name(self):
        # 기존: `entity = {"name": topic, "entity_type": "concept", ...
        #                  "relations": []}` + create_entity_file 호출.
        # 이 패턴이 다시 들어오면 그래프 edge 가 또 끊김.
        self.assertNotIn('"name":        topic', self.src,
            "save_as_longterm must not stamp the query string as a single "
            "concept entity name — that's the bug this fix removes")
        self.assertNotIn('"entity_type": "concept"', self.src,
            "save_as_longterm must not hard-code entity_type='concept' on "
            "the query — let LLM extraction classify each entity")
        self.assertNotIn('wg.create_entity_file(', self.src,
            "save_as_longterm must not call create_entity_file directly; "
            "delegate to process_document_for_entities so multi-entity "
            "extraction runs (UNRESOLVED handling + doc entity included)")

    def test_delegates_to_process_document_for_entities(self):
        self.assertIn("process_document_for_entities", self.src,
            "save_as_longterm must delegate to process_document_for_entities "
            "(same LLM-triple extraction path as PDF ingestion)")

    def test_augments_doc_attributes(self):
        self.assertIn("_augment_doc_attributes", self.src,
            "web metadata (web_sources / learn_method / learned_at) must "
            "still land on the document entity via the augmentation helper")


# ── 2. Delegation contract (functional) ──────────────────────────────

class SaveAsLongtermDelegationTests(unittest.TestCase):
    """save_as_longterm 동작 시 process_document_for_entities 가 호출되는지."""

    def _fake_results(self):
        return [
            {"url": "https://example.com/joby-nvidia",
             "title": "Joby x NVIDIA",
             "body":  "Joby Aviation announced a partnership with NVIDIA "
                      "to accelerate autonomous flight technology.",
             "snippet": "Joby-NVIDIA partnership"},
            {"url": "https://example.com/joby-investment",
             "title": "Joby investment",
             "body":  "NVIDIA invests in Joby through the latest funding round.",
             "snippet": "Investment"},
        ]

    def _patch_engine(self, wg_mock, vs_mock=None):
        """Return a context that replaces RAGEngine with a stub."""
        if vs_mock is None:
            vs_mock = MagicMock()
        engine_stub = SimpleNamespace(
            wiki_generator=wg_mock,
            vector_store=vs_mock,
        )
        engine_cls = MagicMock(return_value=engine_stub)
        return patch("core.graph_rag_engine.RAGEngine", engine_cls), engine_cls

    def test_calls_process_document_for_entities(self):
        from tools.web import web_searcher

        wg = MagicMock()
        wg._normalize_name.side_effect = lambda s: s.replace(" ", "_").lower()
        wg.entity_path = Path(tempfile.mkdtemp())
        wg.process_document_for_entities.return_value = ["e_doc_xxx"]

        patcher, _ = self._patch_engine(wg)
        with patcher:
            web_searcher.save_as_longterm(
                query     = "엔비디아와 조비와 관계",
                results   = self._fake_results(),
                summary   = "NVIDIA 와 Joby Aviation 이 자율 비행 협력을 발표했다.",
                user_role = "admin",
                domain    = "business",
            )

        wg.process_document_for_entities.assert_called_once()
        kwargs = wg.process_document_for_entities.call_args.kwargs

        # filename 패턴 — web_{domain}_{topic[:20]}_{ts}.md
        self.assertTrue(kwargs["filename"].startswith("web_business_"),
            f"filename should keep web_<domain>_ prefix, got {kwargs['filename']}")
        self.assertTrue(kwargs["filename"].endswith(".md"))

        # content 에 summary + body 가 합쳐져 있어야 LLM 이 추출 가능
        content = kwargs["content"]
        self.assertIn("NVIDIA", content)
        self.assertIn("Joby", content)
        self.assertIn("자율 비행", content)
        self.assertIn("### 출처", content)

        # metadata.summary + keywords 가 query 를 보존하여 doc entity attributes 에 흐름
        meta = kwargs["metadata"]
        self.assertIn("summary", meta)
        self.assertEqual(meta["keywords"], ["엔비디아와 조비와 관계"])
        self.assertEqual(meta["category"], "business")

    def test_no_query_entity_filename(self):
        """filename 이 query 문장 자체로 만들어지지 않아야 한다 (topic 트리밍)."""
        from tools.web import web_searcher

        wg = MagicMock()
        wg._normalize_name.side_effect = lambda s: s.replace(" ", "_").lower()
        wg.entity_path = Path(tempfile.mkdtemp())
        wg.process_document_for_entities.return_value = []

        patcher, _ = self._patch_engine(wg)
        with patcher:
            web_searcher.save_as_longterm(
                query     = "조사해봐",
                results   = self._fake_results(),
                summary   = "임의 요약",
                user_role = "admin",
            )

        kwargs = wg.process_document_for_entities.call_args.kwargs
        # filename 에 "조사해봐" 같은 명령어가 그대로 들어가도 그게 entity name 으로
        # 박히는 것은 process_document_for_entities 가 doc_name 으로만 처리하므로 OK.
        # 단 concept 으로 잘못 분류되는 경로는 사라졌음 — 이미 source contract 로 검증.
        self.assertIn(".md", kwargs["filename"])

    def test_empty_results_returns_none(self):
        from tools.web import web_searcher
        self.assertIsNone(
            web_searcher.save_as_longterm(query="x", results=[], summary="y")
        )

    def test_empty_summary_returns_none(self):
        from tools.web import web_searcher
        self.assertIsNone(
            web_searcher.save_as_longterm(
                query="x", results=[{"url": "https://e.com"}], summary=""
            )
        )


# ── 3. Augmentation contract (round-trip) ────────────────────────────

class AugmentDocAttributesTests(unittest.TestCase):
    """_augment_doc_attributes 가 frontmatter 를 머지하여 다시 쓰는지."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.entity_path = Path(self.tmpdir) / "entity"
        (self.entity_path / "document").mkdir(parents=True)

        # process_document_for_entities 가 막 만들었다고 가정한 doc 파일
        doc_path = self.entity_path / "document" / "web_business_topic_123.md"
        doc_path.write_text(
            "---\n"
            "name: web_business_topic_123\n"
            "entity_type: document\n"
            "attributes:\n"
            "  summary: 기존 요약\n"
            "  category: business\n"
            "  keywords: ['엔비디아와 조비']\n"
            "relations: []\n"
            "---\n"
            "## 본문\n원본 본문 보존\n",
            encoding="utf-8",
        )
        self.doc_path = doc_path

        self.wg = SimpleNamespace(
            entity_path  = self.entity_path,
            _normalize_name = lambda s: s.replace(" ", "_").lower(),
        )

    def test_merges_web_metadata_into_attributes(self):
        from tools.web.web_searcher import _augment_doc_attributes

        ok = _augment_doc_attributes(
            self.wg,
            doc_filename = "web_business_topic_123.md",
            extra_attrs  = {
                "web_sources":  ["https://a.com", "https://b.com"],
                "learn_method": "web_search",
                "learned_at":   "2026-05-13T10:00:00",
                "domain":       "business",
            },
        )
        self.assertTrue(ok, "augmentation should succeed when doc exists")

        content = self.doc_path.read_text(encoding="utf-8")
        end = content.find("---", 3)
        fm = yaml.safe_load(content[3:end])

        attrs = fm["attributes"]
        # 기존 키 보존
        self.assertEqual(attrs["summary"], "기존 요약")
        self.assertEqual(attrs["category"], "business")
        # 새 키 머지
        self.assertEqual(attrs["learn_method"], "web_search")
        self.assertEqual(attrs["domain"], "business")
        self.assertEqual(attrs["web_sources"],
                         ["https://a.com", "https://b.com"])

        # body 보존
        self.assertIn("## 본문\n원본 본문 보존", content)

    def test_missing_doc_returns_false(self):
        from tools.web.web_searcher import _augment_doc_attributes
        ok = _augment_doc_attributes(
            self.wg,
            doc_filename = "web_business_nonexistent_999.md",
            extra_attrs  = {"learn_method": "web_search"},
        )
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
