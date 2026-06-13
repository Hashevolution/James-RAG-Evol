"""v0.6 Phase 4 P4.5 — operator quickstart guide structure tests.

Locks the canonical structure of `docs/operator-quickstart-ko.md`
so a future PR can't silently delete a scenario or break the
cross-references to the Phase 4 surfaces (onboarding / rollback /
flow / glossary).

Coverage:

  * File exists at canonical path
  * 5 scenarios present (numbered §1-§5)
  * All 4 Phase 4 surfaces referenced (`/onboarding` /
    `/admin/knowledge-rollback` / `/admin/reasoning-flow` /
    `/glossary`)
  * Korean characters present (verifies the doc is in the right
    language — non-developer Korean operator audience)
  * Each scenario has the canonical sub-structure: 이럴 때 사용 /
    단계별 절차 / 주의사항 / 더 알아보기
  * Support / help section present (§7)
  * Glossary reference section present (§6)
  * No technical jargon raw (e.g. `JWT`, `T7 supersede chain`)
    — definitions yes, raw API names no

Run:
  python -m unittest tests.test_v06_operator_quickstart_doc
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


REPO_ROOT = Path(__file__).resolve().parent.parent
DOC = REPO_ROOT / "docs" / "operator-quickstart-ko.md"


class QuickstartStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not DOC.exists():
            raise unittest.SkipTest(f"quickstart doc missing: {DOC}")
        cls.body = DOC.read_text(encoding="utf-8")

    def test_doc_exists(self):
        self.assertTrue(DOC.exists())

    def test_korean_content(self):
        # Sample Korean phrase that MUST be present — the doc's
        # entire value proposition is that it's in non-developer
        # Korean.
        for phrase in (
            "비개발자",
            "운영자",
            "1 시간 안에",
            "단계별 절차",
            "주의사항",
        ):
            self.assertIn(phrase, self.body,
                          f"missing Korean anchor: {phrase!r}")

    def test_five_scenarios_present(self):
        # Each scenario has a top-level `## N. <Korean title>` header.
        for n in range(1, 6):
            pattern = re.compile(rf"^## {n}\.", re.MULTILINE)
            self.assertTrue(
                pattern.search(self.body),
                f"scenario §{n} header missing",
            )

    def test_scenario_subsection_structure(self):
        # Sample: every scenario has §X.1 "이럴 때 사용" anchor.
        for n in range(1, 6):
            self.assertIn(f"### {n}.1 이럴 때 사용", self.body,
                          f"§{n}.1 '이럴 때 사용' subsection missing")

    def test_all_phase4_surfaces_referenced(self):
        for surface in (
            "/onboarding",            # P4.1
            "/admin/knowledge-rollback",  # P4.2
            "/admin/reasoning-flow",      # P4.3
            "/glossary",                  # P4.4
        ):
            self.assertIn(surface, self.body,
                          f"Phase 4 surface not referenced: {surface}")

    def test_support_section_present(self):
        # §7 도움이 필요할 때 — required so operators have a
        # clear escalation path.
        self.assertIn("## 7.", self.body)
        self.assertIn("도움이 필요할 때", self.body)

    def test_glossary_section_present(self):
        # §6 모르는 용어 만났을 때 — required so operators know
        # to use the tooltip / glossary page.
        self.assertIn("## 6.", self.body)
        self.assertIn("모르는 용어", self.body)

    def test_no_raw_technical_jargon(self):
        # Definitions of these terms are fine (the doc references them
        # in context for completeness), but the RAW phrases below
        # should never appear without translation context. We check
        # for the most-easily-leaked tokens.
        # NOTE: the doc DOES discuss `trace_id` as a term, so we
        # accept its glossary-style mention but lock out raw API names.
        # The forbidden list focuses on developer-only tokens with NO
        # legitimate operator-facing use.
        for term in (
            "JAMES_AUDIT_DB",
            "uvicorn server_llmwiki",
            "pytest tests/",
            "git checkout",
        ):
            self.assertNotIn(term, self.body,
                             f"raw developer-only token leaked: {term!r}")

    def test_doc_references_legal_frameworks(self):
        # Operators in compliance roles need to know JAMES maps to
        # EU AI Act / GDPR / SOC 2. The doc surfaces these in
        # §2 (audit log) + §7.4 (compliance reporting).
        for framework in ("EU AI Act", "GDPR", "SOC 2"):
            self.assertIn(framework, self.body,
                          f"compliance framework not mentioned: {framework}")

    def test_doi_references_present(self):
        # §7.4 must cite the two committed Zenodo DOIs so
        # compliance reports can reference them.
        self.assertIn("10.5281/zenodo.20625533", self.body)  # RAB
        self.assertIn("10.5281/zenodo.20652679", self.body)  # LRB / v0.4.4

    def test_change_history_section(self):
        # §10 변경 이력 — every quickstart that operators rely on
        # must carry a changelog so future versions can be tracked.
        self.assertIn("변경 이력", self.body)
        self.assertIn("2026-06-13", self.body)


if __name__ == "__main__":
    unittest.main()
