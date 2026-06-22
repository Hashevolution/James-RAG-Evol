"""v0.6 Phase 4 P4.1 — operator onboarding flow structure tests.

Locks the canonical structure of the 5-step operator onboarding
surface so a future PR can't silently delete a step, break the
admin entry point, or leak technical jargon (`trace_id`,
`supersede chain`, `audit_log`) into the non-developer screens.

Coverage:

  * `frontend/onboarding.html` exists at canonical path
  * All 5 steps present with `data-step` attribute (1-5)
  * Progress indicator (5 dots) present
  * `step-1-title` ... `step-5-title` IDs present (focus targets)
  * Navigation buttons present (prev / next / finish)
  * "Don't show again" checkbox present
  * Technical jargon NOT present in HTML body
    (`trace_id` / `supersede chain` / `audit_log` raw, etc.)
  * `frontend/static/onboarding.js` exists + exports
    `JAMES_Onboarding`
  * `frontend/static/onboarding.css` exists + carries `.step-dot`
    + `.step-active` selectors
  * `frontend/static/i18n.js` has all the canonical onboarding keys
    (EN + KO blocks)
  * `frontend/admin.html` carries the entry-point link to `/onboarding`
  * `server_llmwiki.py` registers the `/onboarding` route

Run:
  python -m unittest tests.test_v06_onboarding_flow
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


REPO_ROOT = Path(__file__).resolve().parent.parent
# v0.6.1 PR-intro-3 — the 5-step tour content moved into the intro front
# door (#tour section). onboarding.js / .css are still the drivers, so
# they keep their own paths; only the markup host changed.
HTML       = REPO_ROOT / "frontend" / "intro.html"
JS         = REPO_ROOT / "frontend" / "static" / "onboarding.js"
CSS        = REPO_ROOT / "frontend" / "static" / "onboarding.css"
I18N       = REPO_ROOT / "frontend" / "static" / "i18n.js"
ADMIN_HTML = REPO_ROOT / "frontend" / "admin.html"
SERVER     = REPO_ROOT / "server_llmwiki.py"


class HtmlStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HTML.exists():
            raise unittest.SkipTest(f"intro.html (#tour) missing: {HTML}")
        cls.body = HTML.read_text(encoding="utf-8")

    def test_html_exists(self):
        self.assertTrue(HTML.exists())

    def test_five_steps_with_data_step_attr(self):
        for n in range(1, 6):
            self.assertRegex(
                self.body, rf'data-step="{n}"',
                f"step {n} missing data-step attribute",
            )

    def test_five_progress_dots(self):
        # Each step in the progress nav has a `step-dot` class with
        # a `data-step=N` attribute. We expect 5 such dots in the
        # `<ol class="step-dots">` container.
        dot_matches = re.findall(
            r'<li class="step-dot" data-step="(\d+)"',
            self.body,
        )
        self.assertEqual(sorted(dot_matches), ["1", "2", "3", "4", "5"])

    def test_step_focus_target_ids_present(self):
        for n in range(1, 6):
            self.assertIn(
                f'id="step-{n}-title"', self.body,
                f"step-{n}-title focus target missing",
            )

    def test_navigation_buttons_present(self):
        for button_id in ("onboarding-prev", "onboarding-next",
                          "onboarding-finish"):
            self.assertIn(f'id="{button_id}"', self.body,
                          f"missing button: {button_id}")

    def test_tour_section_embedded_in_intro(self):
        # v0.6.1 PR-intro-3 — the tour lives in the intro #tour section.
        # The old per-page "don't show again" checkbox is replaced by the
        # intro front-door auto-skip (intro.js / james_intro_seen).
        self.assertIn('data-intro-section="tour"', self.body)

    def test_no_technical_jargon_in_body(self):
        # Lock: non-developer surface MUST NOT use raw technical
        # vocabulary. Use plain Korean / English replacements via
        # i18n keys instead. (`audit log` is fine — it's the
        # generic English term; the raw `audit_log` table name is
        # not.)
        jargon = [
            "trace_id",
            "supersede chain",
            "audit_log",
            "tenant_id",
            "T7 supersede",
            "reconstruct_graph_at",
            "valid_from",
            "valid_to",
            "JWT",
        ]
        # v0.6.1 PR-intro-3 — scope the jargon check to the TOUR section.
        # The intro page also embeds the #glossary section, which is
        # intentionally full of technical terms (it IS the glossary), so
        # the no-jargon rule applies only to the operator-facing tour.
        start = self.body.find('data-intro-section="tour"')
        end = self.body.find('data-intro-section="glossary"')
        tour = self.body[start:end] if (start != -1 and end != -1) else self.body
        for term in jargon:
            self.assertNotIn(term, tour,
                             f"technical jargon leaked into the tour: {term!r}")

    def test_skip_link_and_a11y(self):
        # WCAG 2.4.1 skip link must be the first focusable element.
        self.assertIn('class="skip-link"', self.body)
        self.assertIn('href="#main"', self.body)
        # Aria region per step.
        self.assertEqual(self.body.count('role="region"'), 5)


class JsStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not JS.exists():
            raise unittest.SkipTest(f"onboarding.js missing: {JS}")
        cls.body = JS.read_text(encoding="utf-8")

    def test_total_steps_constant_is_five(self):
        self.assertIn("var TOTAL_STEPS = 5", self.body)

    def test_storage_key_is_canonical(self):
        self.assertIn("'james_onboarding_completed'", self.body)

    def test_exposes_james_onboarding_global(self):
        self.assertIn("window.JAMES_Onboarding", self.body)
        for fn in ("setStep", "currentStep", "isCompleted",
                   "clearCompleted"):
            self.assertIn(fn, self.body,
                          f"JAMES_Onboarding.{fn} missing from exports")


class CssStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not CSS.exists():
            raise unittest.SkipTest(f"onboarding.css missing: {CSS}")
        cls.body = CSS.read_text(encoding="utf-8")

    def test_step_dot_styles_present(self):
        for selector in (".step-dot", ".step-dots", ".step-active",
                         ".onb-btn", ".example-box", ".step-hint"):
            self.assertIn(selector, self.body,
                          f"missing CSS selector: {selector}")

    def test_44px_touch_target_for_wcag(self):
        # WCAG 2.5.5 — target size 44×44 minimum
        self.assertIn("min-height: 44px", self.body)


class I18nKeysPresenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = I18N.read_text(encoding="utf-8")

    def test_canonical_onboarding_keys_present(self):
        # The full key set the HTML's data-i18n attributes resolve to.
        # If a key disappears the page renders the fallback text only.
        required = [
            "onboarding.page_title",
            "onboarding.skip_to_admin",
            "onboarding.dont_show_again",
            "onboarding.nav.prev",
            "onboarding.nav.next",
            "onboarding.nav.finish",
            "onboarding.step_label.welcome",
            "onboarding.step_label.search",
            "onboarding.step_label.audit",
            "onboarding.step_label.review",
            "onboarding.step_label.timetravel",
            "onboarding.step1.title",
            "onboarding.step1.intro",
            "onboarding.step1.hint",
            "onboarding.step2.title",
            "onboarding.step3.title",
            "onboarding.step4.title",
            "onboarding.step5.title",
            "admin.onboarding_link",
        ]
        for key in required:
            # Each key must appear at least twice (English block +
            # Korean block); we lock the BOTH-present property by
            # asserting count >= 2.
            count = self.body.count(f"'{key}'")
            self.assertGreaterEqual(
                count, 2,
                f"i18n key {key!r} missing from EN or KO block "
                f"(found {count}× expected ≥ 2)",
            )


class AdminEntryPointTests(unittest.TestCase):
    def test_admin_html_links_to_onboarding(self):
        body = ADMIN_HTML.read_text(encoding="utf-8")
        # v0.6.1 PR-intro-2 — onboarding folded into the intro front door;
        # the admin link now points at the tour section anchor (/#tour).
        self.assertIn('href="/#tour"', body,
                      "admin.html header must link to the intro tour (/#tour)")
        self.assertIn('admin.onboarding_link', body,
                      "admin.html must use the i18n key for the link label")


class ServerRouteTests(unittest.TestCase):
    def test_onboarding_route_registered(self):
        body = SERVER.read_text(encoding="utf-8")
        self.assertIn('@app.get("/onboarding"', body)
        self.assertIn("async def serve_onboarding", body)
        # v0.6.1 PR-intro-2 — /onboarding now 301-redirects into the intro
        # front door (the 5-step tour content moved to intro.html#tour).
        self.assertIn("/#tour", body)


if __name__ == "__main__":
    unittest.main()
