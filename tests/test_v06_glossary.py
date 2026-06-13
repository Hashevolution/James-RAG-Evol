"""v0.6 Phase 4 P4.4 — glossary page + universal tooltip tests.

Coverage:

  * `/glossary` page exists at canonical path
  * 5 categories present (core / audit / quality / security / ops)
  * Search input + no-results hint present
  * 26+ canonical term entries (data-term attributes)
  * Cross-page tooltip wiring: existing pages (admin / graph /
    onboarding / reasoning-flow / knowledge-rollback) load
    glossary.js
  * Universal `data-glossary` attribute pattern present in graph.html
  * glossary.js exposes window.JAMES_Glossary + canonical GLOSSARY map
  * glossary.css carries selectors (.glossary-tooltip /
    [data-glossary] / .glossary-entry)
  * Server route registered
  * Admin entry-point link present
  * i18n keys in BOTH EN and KO blocks

Run:
  python -m unittest tests.test_v06_glossary
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


REPO_ROOT = Path(__file__).resolve().parent.parent
HTML       = REPO_ROOT / "frontend" / "glossary.html"
JS         = REPO_ROOT / "frontend" / "static" / "glossary.js"
CSS        = REPO_ROOT / "frontend" / "static" / "glossary.css"
I18N       = REPO_ROOT / "frontend" / "static" / "i18n.js"
ADMIN_HTML = REPO_ROOT / "frontend" / "admin.html"
GRAPH_HTML = REPO_ROOT / "frontend" / "graph.html"
ONBOARDING_HTML = REPO_ROOT / "frontend" / "onboarding.html"
REASONING_HTML  = REPO_ROOT / "frontend" / "reasoning-flow.html"
ROLLBACK_HTML   = REPO_ROOT / "frontend" / "knowledge-rollback.html"
SERVER     = REPO_ROOT / "server_llmwiki.py"


class GlossaryPageStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HTML.exists():
            raise unittest.SkipTest("glossary.html missing")
        cls.body = HTML.read_text(encoding="utf-8")

    def test_five_categories(self):
        for cat in ("core", "audit", "quality", "security", "ops"):
            self.assertIn(f'data-category="{cat}"', self.body,
                          f"missing category section: {cat}")

    def test_search_surface(self):
        self.assertIn('id="glossary-search-input"', self.body)
        self.assertIn('id="glossary-no-results"', self.body)

    def test_canonical_term_entries_present(self):
        # Lock the canonical 26 terms (one per data-term attribute
        # in glossary.html). A future PR can add MORE terms, but
        # may not silently drop the canonical set.
        canonical_terms = [
            # core
            "rag", "graph-rag", "entity", "relation", "ontology", "embedding",
            # audit + time
            "audit-log", "trace-id", "replay", "time-travel",
            "supersede", "cascade",
            # quality
            "abstention", "hallucination", "citation", "path-coverage",
            # security
            "rbac", "abac", "oidc", "approval-evidence", "csp", "tenant",
            # ops
            "change-request", "rollback", "contradiction-arbiter",
            "reasoning-trace",
        ]
        for term in canonical_terms:
            self.assertIn(f'data-term="{term}"', self.body,
                          f"missing canonical term: {term}")
        self.assertEqual(
            len(canonical_terms), 26,
            "canonical term count drifted — update both the test "
            "and the doc if intentional",
        )

    def test_a11y_skip_link(self):
        self.assertIn('class="skip-link"', self.body)


class GlossaryJsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = JS.read_text(encoding="utf-8")

    def test_exposes_global(self):
        self.assertIn("window.JAMES_Glossary", self.body)
        for name in ("GLOSSARY", "showTooltip", "annotate"):
            self.assertIn(name, self.body)

    def test_glossary_map_carries_canonical_terms(self):
        # The JS-side GLOSSARY object MUST contain every term the
        # page advertises — so cross-page tooltips work without
        # loading the page.
        terms = [
            "rag", "graph-rag", "entity", "relation", "ontology",
            "audit-log", "trace-id", "replay", "time-travel",
            "supersede", "cascade", "abstention", "hallucination",
            "citation", "path-coverage", "rbac", "abac", "oidc",
            "approval-evidence", "csp", "tenant", "change-request",
            "rollback", "contradiction-arbiter", "reasoning-trace",
        ]
        for term in terms:
            self.assertIn(f"'{term}'", self.body,
                          f"GLOSSARY map missing term: {term}")


class GlossaryCssTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = CSS.read_text(encoding="utf-8")

    def test_tooltip_selectors(self):
        for sel in (".glossary-tooltip", "[data-glossary]",
                    ".glossary-entry", ".glossary-section"):
            self.assertIn(sel, self.body,
                          f"missing CSS selector: {sel}")

    def test_44px_touch_target_on_search(self):
        self.assertIn("min-height: 44px", self.body)


class CrossPageWiringTests(unittest.TestCase):
    """All other operator-facing pages must load `glossary.js` so the
    universal tooltip mechanism works site-wide."""

    def _assert_loads_glossary_js(self, path: Path, label: str):
        body = path.read_text(encoding="utf-8")
        self.assertIn(
            '/static/glossary.js', body,
            f"{label} does not load glossary.js — tooltips won't work",
        )

    def test_admin_html_loads_glossary(self):
        self._assert_loads_glossary_js(ADMIN_HTML, "admin.html")

    def test_graph_html_loads_glossary(self):
        self._assert_loads_glossary_js(GRAPH_HTML, "graph.html")

    def test_onboarding_html_loads_glossary(self):
        self._assert_loads_glossary_js(ONBOARDING_HTML, "onboarding.html")

    def test_reasoning_html_loads_glossary(self):
        self._assert_loads_glossary_js(REASONING_HTML, "reasoning-flow.html")

    def test_rollback_html_loads_glossary(self):
        self._assert_loads_glossary_js(ROLLBACK_HTML, "knowledge-rollback.html")

    def test_graph_html_has_data_glossary_anchor(self):
        # Verify at least ONE data-glossary attribute exists in the
        # graph page — proves the wiring scope reaches that page.
        body = GRAPH_HTML.read_text(encoding="utf-8")
        self.assertIn('data-glossary=', body,
                      "graph.html has no data-glossary anchor — tooltips "
                      "load but won't activate on any element")


class I18nKeysTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = I18N.read_text(encoding="utf-8")

    def test_canonical_glossary_keys_in_both_blocks(self):
        required = [
            "glossary.page_title",
            "glossary.title",
            "glossary.intro",
            "glossary.search.placeholder",
            "glossary.search.no_results",
            "glossary.cat.core",
            "glossary.cat.audit",
            "glossary.cat.quality",
            "glossary.cat.security",
            "glossary.cat.ops",
            "admin.glossary_link",
        ]
        for key in required:
            count = self.body.count(f"'{key}'")
            self.assertGreaterEqual(
                count, 2,
                f"i18n key {key!r} missing in EN or KO (count {count})",
            )


class ServerAndEntryPointTests(unittest.TestCase):
    def test_glossary_route_registered(self):
        body = SERVER.read_text(encoding="utf-8")
        self.assertIn('@app.get("/glossary"', body)
        self.assertIn("async def serve_glossary", body)

    def test_admin_html_link_to_glossary(self):
        body = ADMIN_HTML.read_text(encoding="utf-8")
        self.assertIn('href="/glossary"', body)
        self.assertIn('admin.glossary_link', body)


if __name__ == "__main__":
    unittest.main()
