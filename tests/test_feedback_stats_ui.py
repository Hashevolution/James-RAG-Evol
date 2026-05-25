"""Admin Memory tab — feedback-stats card (UI-IA risk #1 last orphan).

Static snapshot pinning for the 4-stat strip that surfaces
`GET /feedback/stats/`. Same pattern as test_cognitive_toggle_ui.py
and test_llm_selection_ui.py.

No browser; pins the wiring contract so a refactor that strips the
card (or renames the endpoint reference) breaks loudly here.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
ADMIN_HTML = ROOT / "frontend" / "admin.html"
ADMIN_JS   = ROOT / "frontend" / "static" / "admin.js"
I18N_JS    = ROOT / "frontend" / "static" / "i18n.js"


class AdminHtmlSectionTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.html = ADMIN_HTML.read_text(encoding="utf-8")

    def test_feedback_section_title_present(self):
        self.assertIn('data-i18n="memory.feedback_title"', self.html,
            "Memory tab must declare the feedback-aggregate section title")

    def test_feedback_card_container_id(self):
        self.assertIn('id="feedback-stats-card"', self.html,
            "admin.js targets `#feedback-stats-card`; renaming this id "
            "without updating the JS would silently break the render")

    def test_section_lives_inside_memory_page(self):
        # The new card lives in page-memory, not stranded elsewhere.
        idx_page = self.html.index('id="page-memory"')
        idx_card = self.html.index('id="feedback-stats-card"')
        # Close the memory page sometime after the card.
        idx_close = self.html.index('id="page-patches"', idx_card)
        self.assertGreater(idx_card, idx_page,
            "feedback card must be inside #page-memory")
        self.assertGreater(idx_close, idx_card,
            "feedback card must close before the next page block")


class AdminJsHandlerTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.js = ADMIN_JS.read_text(encoding="utf-8")

    def test_load_function_defined(self):
        self.assertIn("async function loadFeedbackStats", self.js,
            "loadFeedbackStats must be defined")

    def test_load_hits_feedback_stats_endpoint(self):
        idx = self.js.index("async function loadFeedbackStats")
        body = self.js[idx:idx + 4000]
        self.assertIn("/feedback/stats/", body,
            "loadFeedbackStats must GET the documented endpoint")

    def test_load_is_called_from_load_memory(self):
        # Memory tab loader must trigger the new card so it hydrates
        # without an extra click.
        idx = self.js.index("async function loadMemory")
        m = re.search(r"\nasync function\s+\w+\s*\(", self.js[idx + 1:])
        end = idx + 1 + m.start() if m else idx + 5000
        body = self.js[idx:end]
        self.assertIn("loadFeedbackStats", body,
            "loadMemory must trigger loadFeedbackStats so the card "
            "renders when the operator opens the Memory tab")

    def test_load_handles_error_path(self):
        # The endpoint returns {error: ...} on failure (server side
        # try/except); the render must NOT blank the surrounding UI.
        # We pin the defensive branch + the `_escHtml` usage on the
        # error message.
        idx = self.js.index("async function loadFeedbackStats")
        body = self.js[idx:idx + 4000]
        self.assertIn("data && data.error", body,
            "render must detect the server's {error: ...} shape")
        # Outer try/catch on the api() call itself.
        self.assertIn("catch (e)", body,
            "render must wrap api() in try/catch so a 4xx doesn't "
            "throw uncaught into loadMemory")
        # Both error branches must escape the message.
        self.assertGreaterEqual(body.count("_escHtml"), 2,
            "both error branches and the ratio label must run through "
            "_escHtml (XSS guard)")

    def test_load_failure_does_not_blank_memory_tab(self):
        # loadMemory's caller must wrap loadFeedbackStats so a network
        # failure on /feedback/stats/ doesn't drop the long-term + sessions
        # rows that already rendered.
        idx = self.js.index("async function loadMemory")
        m = re.search(r"\nasync function\s+\w+\s*\(", self.js[idx + 1:])
        end = idx + 1 + m.start() if m else idx + 5000
        body = self.js[idx:end]
        # Defensive try/catch around the feedback call specifically.
        # Form: `try { await loadFeedbackStats(); } catch (e) { ... }`
        feedback_idx = body.index("loadFeedbackStats")
        prelude = body[max(0, feedback_idx - 80):feedback_idx]
        self.assertIn("try", prelude,
            "loadMemory must defensively wrap loadFeedbackStats in "
            "try/catch — a failure here must not blank the surrounding UI")

    def test_render_computes_positive_ratio(self):
        idx = self.js.index("async function loadFeedbackStats")
        body = self.js[idx:idx + 4000]
        # The 5th stat (positive ratio) is derived client-side; the
        # backend only ships total + positive + negative + tracked.
        self.assertIn("pos / total", body,
            "render must derive the positive ratio client-side")
        # Defensive on zero-total to avoid NaN%.
        self.assertIn("total > 0", body,
            "render must guard against divide-by-zero on no-signal state")


class I18nKeysTests(unittest.TestCase):

    REQUIRED_KEYS = [
        "memory.feedback_title",
        "mem.feedback_total",
        "mem.feedback_positive",
        "mem.feedback_negative",
        "mem.feedback_ratio",
        "mem.feedback_tracked",
        "mem.feedback_no_signal",
    ]

    @classmethod
    def setUpClass(cls):
        cls.text = I18N_JS.read_text(encoding="utf-8")
        ko_idx = cls.text.index("  ko: {")
        cls.en_block = cls.text[:ko_idx]
        cls.ko_block = cls.text[ko_idx:]

    def test_every_required_key_in_en(self):
        for k in self.REQUIRED_KEYS:
            with self.subTest(key=k):
                self.assertIn(f"'{k}':", self.en_block,
                    f"{k} missing in en")

    def test_every_required_key_in_ko(self):
        for k in self.REQUIRED_KEYS:
            with self.subTest(key=k):
                self.assertIn(f"'{k}':", self.ko_block,
                    f"{k} missing in ko")

    def test_html_referenced_keys_defined(self):
        html = ADMIN_HTML.read_text(encoding="utf-8")
        refs = re.findall(
            r'data-i18n="(memory\.feedback_[a-z_]+|mem\.feedback_[a-z_]+)"',
            html,
        )
        self.assertGreaterEqual(len(refs), 1,
            "admin.html must reference at least one feedback i18n key")
        for k in set(refs):
            with self.subTest(key=k):
                self.assertIn(f"'{k}':", self.en_block,
                    f"HTML references {k} which is not defined in en")


if __name__ == "__main__":
    unittest.main()
