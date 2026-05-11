"""[PR plan-4, 2026-05-09] Chat picker recommend link + defensive resolution.

Two contracts asserted here:

1. **call_gemma defensive resolution**: when the caller passes a
   specific tag (model=picked) but the tag isn't installed, the
   resolver should still fall through to the preference list rather
   than 404. This protects the picker selection path which had a
   gap — `selected_model` was validated against the catalog
   (PR #136) but the catalog only checks "is this tag listed", not
   "is this tag actually installed in Ollama right now".

2. **chat picker UI**: index.html surfaces a 🎯 추천 link next to
   the install button so users can self-route to the admin first-run
   wizard for hardware-aware recommendations.

Run:
    python -m unittest tests.test_chat_recommend_link
"""
from __future__ import annotations

import inspect
import os
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent


class CallGemmaDefensiveResolutionTests(unittest.TestCase):
    """call_gemma must fall through to resolver even when the caller
    passes a specific tag — if that tag isn't installed."""

    @classmethod
    def setUpClass(cls):
        from core import gemma_client
        cls.src = inspect.getsource(gemma_client)

    def test_truthy_model_path_checks_installed(self):
        # The 'if model:' branch must consult installed_models() and
        # only use the tag directly if it's actually present.
        idx = self.src.index("if model:")
        body = self.src[idx:idx + 1200]
        self.assertIn("installed_models", body,
            "call_gemma's truthy-model branch must verify the tag is "
            "actually installed in Ollama before hitting it")

    def test_truthy_model_falls_through_resolver(self):
        idx = self.src.index("if model:")
        body = self.src[idx:idx + 1200]
        self.assertIn("resolve_for_mode", body,
            "missing tag must trigger resolver fallback "
            "(not just call ollama and 404)")


class ChatRecommendLinkTests(unittest.TestCase):
    """index.html must surface a 🎯 추천 link next to the install button."""

    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")

    def test_recommend_link_present(self):
        self.assertIn('id="mode-recommend-link"', self.html,
            "🎯 추천 link must exist next to install button")

    def test_recommend_link_targets_admin(self):
        idx = self.html.index('id="mode-recommend-link"')
        body = self.html[idx:idx + 600]
        self.assertIn('href="/admin"', body,
            "recommend link should route to /admin (first-run wizard lives there)")
        # New tab so user doesn't lose chat context.
        self.assertIn('target="_blank"', body)

    def test_recommend_link_visible_to_all_roles(self):
        # Unlike the install button (admin-only), the recommend link
        # is visible to all — non-admin can SEE recommendations even
        # if they can't install. The link doesn't have role-based hide.
        # Bound the body at the </a> tag so we don't pick up sibling
        # elements that may have their own display:none.
        idx = self.html.index('id="mode-recommend-link"')
        end = self.html.index("</a>", idx)
        body = self.html[idx:end]
        self.assertNotIn("display:none", body,
            "recommend link must be visible by default — non-admin "
            "should at least see what models exist")


if __name__ == "__main__":
    unittest.main()
