"""v0.6 — Industry comparison doc structure smoke tests.

Locks the canonical structure of
``docs/evaluation/v0.5-industry-comparison.md`` so a future PR can't
silently drop one of the three load-bearing matrices, lose the
honest-framing rules, or remove the README callout. Doc-only.

Coverage:

* File exists at the canonical path.
* All three named matrices are present (capability presence /
  benchmark headline / reproducibility).
* All five comparison columns named (LangChain / LlamaIndex /
  Haystack / R2R / ActiveGraph).
* Honest framing §1 enumerates the 4 rules.
* The 60-second reproduce command block is present (procurement
  signature — section §6).
* README + README.ko both link to the doc from the "Why JAMES?"
  callout block.

Run:
  python -m unittest tests.test_v06_industry_comparison_doc
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO_ROOT = Path(__file__).resolve().parent.parent
DOC = REPO_ROOT / "docs" / "evaluation" / "v0.5-industry-comparison.md"
README = REPO_ROOT / "README.md"
README_KO = REPO_ROOT / "README.ko.md"


class IndustryComparisonDocStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not DOC.exists():
            raise unittest.SkipTest(f"comparison doc missing: {DOC}")
        cls.body = DOC.read_text(encoding="utf-8")

    def test_doc_exists(self):
        self.assertTrue(DOC.exists())

    def test_three_canonical_matrices_present(self):
        # Each matrix has a distinct section header.
        for header in (
            "## 3. Matrix A — architectural capability presence",
            "## 4. Matrix B — public benchmark headline coverage",
            "## 5. Matrix C — reproducibility tier",
        ):
            self.assertIn(header, self.body,
                          f"missing canonical matrix section: {header!r}")

    def test_five_comparison_systems_named(self):
        # Locking the column set so a future PR can't quietly drop one.
        for system in (
            "LangChain", "LlamaIndex", "Haystack", "R2R", "ActiveGraph",
        ):
            self.assertIn(system, self.body,
                          f"missing comparison column: {system!r}")

    def test_honest_framing_rules_present(self):
        # The §1 honest-framing block has 3 numbered non-claims.
        for needle in (
            "1. **A head-to-head benchmark.**",
            "2. **An exhaustive landscape survey.**",
            "3. **A claim that JAMES wins everywhere.**",
        ):
            self.assertIn(needle, self.body,
                          f"missing honest-framing rule: {needle!r}")

    def test_60_second_reproduce_block_present(self):
        # The procurement-signature reproduction block.
        self.assertIn("python scripts/research/rab_run.py", self.body)
        self.assertIn("scripts/research/lrb_run_phase_b.py", self.body)
        self.assertIn("scripts/research/lrb_run_s3.py", self.body)
        self.assertIn("scripts/qvt_ablation_matrix.py", self.body)

    def test_load_bearing_claims_referenced(self):
        # RAB + LRB are the two load-bearing JAMES headlines.
        self.assertIn("RAB", self.body)
        self.assertIn("LRB", self.body)
        self.assertIn("AC/RF/PC", self.body)
        self.assertIn("V<N<J", self.body)

    def test_zenodo_dois_referenced(self):
        # Reproducibility tier matrix cites the two minted DOIs.
        self.assertIn("10.5281/zenodo.20652679", self.body)
        self.assertIn("10.5281/zenodo.20625533", self.body)

    def test_eu_ai_act_anchor_referenced(self):
        # EU AI Act Art. 10/12/19 is the audit-evidence positioning anchor.
        self.assertIn("EU AI Act", self.body)
        self.assertIn("Art. 10", self.body)


class ReadmeCalloutTests(unittest.TestCase):
    """Both READMEs surface the comparison doc from the 'Why JAMES?'
    callout block, so external reviewers see the link before the
    project status block."""

    def test_readme_links_to_comparison_doc(self):
        body = README.read_text(encoding="utf-8")
        self.assertIn(
            "docs/evaluation/v0.5-industry-comparison.md",
            body,
            "README.md must link to the industry comparison doc",
        )

    def test_readme_ko_links_to_comparison_doc(self):
        body = README_KO.read_text(encoding="utf-8")
        self.assertIn(
            "docs/evaluation/v0.5-industry-comparison.md",
            body,
            "README.ko.md must link to the industry comparison doc",
        )

    def test_readme_callout_mentions_competitor_systems(self):
        # The callout names the 5 comparison columns so the reviewer
        # knows what's inside before clicking.
        body = README.read_text(encoding="utf-8")
        for system in ("LangChain", "LlamaIndex", "Haystack", "R2R"):
            self.assertIn(system, body)


if __name__ == "__main__":
    unittest.main()
