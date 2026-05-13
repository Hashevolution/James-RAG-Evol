"""resolve_pending_relations contract — frontmatter UNRESOLVED 재매칭 (2026-05-13).

Diagnostic context (user session): joby.md 등 PDF 추출 노드들의 frontmatter
relations 가 `target_id: UNRESOLVED` 로 남아있어 그래프 엔진이 두 노드
사이 edge 를 못 그림. wiki/entity/prod/org/faa.md 같은 target entity 가
이미 존재하지만 create_entity_file 호출 시점에는 아직 ingest 되지
않았던 케이스.

Fix in `core/wiki_generator.WikiGenerator`:
  - resolve_pending_relations 가 이전엔 body 의 `## 관계` 섹션만 yaml.load
    하려 했고 (실제 body 는 사람-읽기용 글머리표라 load 실패), frontmatter
    relations 키는 건드리지 않아 실질 동작 안 함.
  - 재작성 후 frontmatter `relations:` 의 UNRESOLVED target_id 를
    _find_existing_entity_id (alias 매칭 포함) 로 재매칭하여 채움.
  - process_document_for_entities 가 refresh_entity_map 직후 자동 호출
    하므로 매 ingest 마다 누적 UNRESOLVED 가 함께 해소됨.

Run:
  python -m unittest tests.test_wiki_resolve_unresolved
"""
from __future__ import annotations

import inspect
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── 1. Functional contract (round-trip with synthetic wiki) ─────────

def _write_entity(path: Path, fm: dict, body: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "---\n"
        + yaml.dump(fm, allow_unicode=True, default_flow_style=False, sort_keys=True)
        + "---\n"
        + body
    )
    path.write_text(content, encoding="utf-8")


class ResolvePendingRelationsTests(unittest.TestCase):
    """frontmatter relations 의 UNRESOLVED 가 다음 sweep 에서 채워지는지."""

    def setUp(self):
        from core.wiki_generator import WikiGenerator
        self.WG = WikiGenerator

        self.tmpdir = Path(tempfile.mkdtemp())
        self.entity_path = self.tmpdir / "entity"

        # 4 표준 type 디렉토리
        self.entity_types = ["person", "concept", "org", "document"]
        for t in self.entity_types:
            (self.entity_path / t).mkdir(parents=True)

    def _stub(self):
        """WikiGenerator 인스턴스 무거우므로 필요한 attr/method 만 가진 stub."""
        stub = SimpleNamespace(
            entity_types = self.entity_types,
            entity_path  = self.entity_path,
        )
        # _find_existing_entity_id 와 _normalize_name 도 같은 정의를 흉내
        from core.wiki_generator import WikiGenerator
        stub._find_existing_entity_id = WikiGenerator._find_existing_entity_id.__get__(stub)
        stub._normalize_name          = WikiGenerator._normalize_name.__get__(stub)
        stub._read_frontmatter        = WikiGenerator._read_frontmatter.__get__(stub)
        return stub

    def test_resolves_when_target_entity_exists(self):
        # 시나리오: joby.md 는 FAA 를 RELATED_TO 로 가리키지만 UNRESOLVED.
        # faa.md (org) 가 wiki 에 이미 존재 → resolve 가 채워줘야.
        _write_entity(
            self.entity_path / "org" / "faa.md",
            fm={
                "name":        "FAA",
                "normalized_name": "faa",
                "entity_id":   "e_org_aaa11111",
                "entity_type": "org",
                "aliases":     [],
                "relations":   [],
            },
        )
        _write_entity(
            self.entity_path / "org" / "joby.md",
            fm={
                "name":        "Joby",
                "normalized_name": "joby",
                "entity_id":   "e_org_bbb22222",
                "entity_type": "org",
                "aliases":     [],
                "relations": [
                    {
                        "target":      "FAA",
                        "target_id":   "UNRESOLVED",
                        "target_type": "org",
                        "label":       "관련",
                        "confidence":  0.9,
                    }
                ],
            },
        )

        stub = self._stub()
        fixed = self.WG.resolve_pending_relations(stub)

        self.assertEqual(fixed, 1,
            "exactly one UNRESOLVED relation should be filled")

        joby_after = yaml.safe_load(
            (self.entity_path / "org" / "joby.md").read_text(encoding="utf-8")
            .split("---", 2)[1]
        )
        self.assertEqual(joby_after["relations"][0]["target_id"],
                         "e_org_aaa11111",
            "joby's relation should now resolve to FAA's entity_id")

    def test_falls_back_to_other_types_when_target_type_wrong(self):
        # joby.md 가 eVTOL 을 target_type=concept 으로 가리킴.
        # 만약 eVTOL 이 실제로는 다른 type 에 있다면 None fallback 으로 매칭.
        _write_entity(
            self.entity_path / "concept" / "evtol.md",
            fm={
                "name":            "eVTOL",
                "normalized_name": "evtol",
                "entity_id":       "e_concept_ccc33333",
                "entity_type":     "concept",
                "aliases":         [],
                "relations":       [],
            },
        )
        _write_entity(
            self.entity_path / "org" / "joby.md",
            fm={
                "name":            "Joby",
                "normalized_name": "joby",
                "entity_id":       "e_org_bbb22222",
                "entity_type":     "org",
                "aliases":         [],
                "relations": [
                    {
                        "target":      "eVTOL",
                        "target_id":   "UNRESOLVED",
                        "target_type": "org",   # 의도적으로 잘못된 타입
                        "label":       "생산",
                        "confidence":  0.9,
                    }
                ],
            },
        )

        stub = self._stub()
        fixed = self.WG.resolve_pending_relations(stub)
        # 정확 타입(org) 매칭 실패 → None fallback 으로 concept 에서 발견
        self.assertEqual(fixed, 1)

        joby_after = yaml.safe_load(
            (self.entity_path / "org" / "joby.md").read_text(encoding="utf-8")
            .split("---", 2)[1]
        )
        self.assertEqual(joby_after["relations"][0]["target_id"],
                         "e_concept_ccc33333")

    def test_alias_match(self):
        # entity 이름이 alias 로만 매칭되는 케이스 — _find_existing_entity_id
        # 가 alias 도 본다는 사실에 의존.
        _write_entity(
            self.entity_path / "org" / "nvidia.md",
            fm={
                "name":            "NVIDIA",
                "normalized_name": "nvidia",
                "entity_id":       "e_org_ddd44444",
                "entity_type":     "org",
                "aliases":         ["엔비디아"],
                "relations":       [],
            },
        )
        _write_entity(
            self.entity_path / "concept" / "topic.md",
            fm={
                "name":            "topic",
                "normalized_name": "topic",
                "entity_id":       "e_concept_eee55555",
                "entity_type":     "concept",
                "aliases":         [],
                "relations": [
                    {
                        "target":      "엔비디아",     # alias
                        "target_id":   "UNRESOLVED",
                        "target_type": "org",
                        "label":       "관련",
                        "confidence":  0.7,
                    }
                ],
            },
        )

        stub = self._stub()
        fixed = self.WG.resolve_pending_relations(stub)
        self.assertEqual(fixed, 1)

        topic_after = yaml.safe_load(
            (self.entity_path / "concept" / "topic.md").read_text(encoding="utf-8")
            .split("---", 2)[1]
        )
        self.assertEqual(topic_after["relations"][0]["target_id"],
                         "e_org_ddd44444",
            "alias-only match should still fill target_id")

    def test_no_target_keeps_unresolved(self):
        # 매칭되는 target 이 wiki 에 없으면 UNRESOLVED 유지.
        _write_entity(
            self.entity_path / "org" / "joby.md",
            fm={
                "name":            "Joby",
                "normalized_name": "joby",
                "entity_id":       "e_org_bbb22222",
                "entity_type":     "org",
                "aliases":         [],
                "relations": [
                    {
                        "target":      "Nonexistent",
                        "target_id":   "UNRESOLVED",
                        "target_type": "concept",
                        "label":       "관련",
                        "confidence":  0.7,
                    }
                ],
            },
        )

        stub = self._stub()
        fixed = self.WG.resolve_pending_relations(stub)
        self.assertEqual(fixed, 0)

        joby_after = yaml.safe_load(
            (self.entity_path / "org" / "joby.md").read_text(encoding="utf-8")
            .split("---", 2)[1]
        )
        self.assertEqual(joby_after["relations"][0]["target_id"], "UNRESOLVED")

    def test_preserves_other_frontmatter_and_body(self):
        # frontmatter 의 다른 키 + body 보존 검증.
        _write_entity(
            self.entity_path / "org" / "faa.md",
            fm={
                "name":            "FAA",
                "normalized_name": "faa",
                "entity_id":       "e_org_aaa11111",
                "entity_type":     "org",
                "aliases":         [],
                "relations":       [],
            },
        )
        _write_entity(
            self.entity_path / "org" / "joby.md",
            fm={
                "name":            "Joby",
                "normalized_name": "joby",
                "entity_id":       "e_org_bbb22222",
                "entity_type":     "org",
                "aliases":         ["JOBY", "조비"],
                "attributes":      {"summary": "eVTOL maker", "country": "US"},
                "confidence":      1.0,
                "sensitivity":     "internal",
                "relations": [
                    {
                        "target":      "FAA",
                        "target_id":   "UNRESOLVED",
                        "target_type": "org",
                        "label":       "관련",
                        "confidence":  0.9,
                    }
                ],
            },
            body=(
                "## 요약\n"
                "전기 항공 회사\n\n"
                "## 관계\n"
                "- 관련: FAA (conf=0.90)\n"
            ),
        )

        stub = self._stub()
        self.WG.resolve_pending_relations(stub)

        text = (self.entity_path / "org" / "joby.md").read_text(encoding="utf-8")
        end = text.find("---", 3)
        fm_after = yaml.safe_load(text[3:end])

        self.assertEqual(fm_after["aliases"], ["JOBY", "조비"])
        self.assertEqual(fm_after["attributes"]["country"], "US")
        self.assertEqual(fm_after["sensitivity"], "internal")
        # body 보존
        self.assertIn("## 요약\n전기 항공 회사", text)
        self.assertIn("- 관련: FAA (conf=0.90)", text)

    def test_skips_files_without_unresolved(self):
        # 모두 매칭 완료된 파일은 다시 쓰지 않는다 (mtime 변경 없음 검증
        # 까지는 안 가도, fixed=0 + 파일 내용 동일).
        _write_entity(
            self.entity_path / "org" / "anthropic.md",
            fm={
                "name":            "Anthropic",
                "normalized_name": "anthropic",
                "entity_id":       "e_org_fff66666",
                "entity_type":     "org",
                "aliases":         [],
                "relations": [
                    {"target": "Claude", "target_id": "e_concept_xxx",
                     "target_type": "concept", "label": "생산", "confidence": 0.9}
                ],
            },
        )

        path = self.entity_path / "org" / "anthropic.md"
        before = path.read_text(encoding="utf-8")

        stub = self._stub()
        fixed = self.WG.resolve_pending_relations(stub)

        self.assertEqual(fixed, 0)
        self.assertEqual(path.read_text(encoding="utf-8"), before,
            "files with no UNRESOLVED should not be rewritten")


# ── 2. Static contract — process_document_for_entities 자동 호출 ────

class AutoResolveOnIngestTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from core.wiki_generator import WikiGenerator
        cls.src = inspect.getsource(WikiGenerator.process_document_for_entities)

    def test_process_doc_invokes_resolve_pending_relations(self):
        self.assertIn("resolve_pending_relations", self.src,
            "process_document_for_entities must call resolve_pending_relations "
            "after refresh_entity_map so every ingest cycle settles previously "
            "UNRESOLVED relations against the newly-added entities")


if __name__ == "__main__":
    unittest.main()
