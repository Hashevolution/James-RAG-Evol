"""Reasoning stream UI animations — item #1 (2026-05-08).

User wanted "움직이는 아이콘" + "자연스럽게 반짝이는 글자" instead
of static text. PR #97 wired real per-stage events; this PR adds the
visual polish — spinner on the icon for active stages, shimmer on
the label, fade for done stages.

Source-level contracts only (CSS animation behavior can't be
unit-tested cheaply without a headless browser):

  - mobile.css defines @keyframes james-spin / james-pulse-dot /
    james-shimmer.
  - mobile.css has .thinking-line.thinking-active / .thinking-done
    selectors with the documented CSS variable hook (--stage-color).
  - chat.js appendTyping creates lines with the right class names
    and toggles active → done correctly.

Run:
  python -m unittest tests.test_reasoning_ui_animation
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
CSS  = ROOT / "frontend" / "static" / "mobile.css"
JS   = ROOT / "frontend" / "static" / "chat.js"


class CssAnimationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.css = CSS.read_text(encoding="utf-8")

    def test_three_keyframes_defined(self):
        for name in ("james-spin", "james-pulse-dot", "james-shimmer"):
            self.assertRegex(
                self.css,
                rf"@keyframes\s+{re.escape(name)}\s*\{{",
                f"@keyframes {name} missing",
            )

    def test_active_class_animates_spinner_and_shimmer(self):
        # Active stage: icon spinning + label shimmering.
        self.assertRegex(
            self.css,
            r"\.thinking-line\.thinking-active\s+\.thinking-icon[^{]*\{[^}]*animation\s*:\s*james-spin",
            "active stage icon must run james-spin animation",
        )
        self.assertRegex(
            self.css,
            r"\.thinking-line\.thinking-active\s+\.thinking-label[^{]*\{[^}]*animation\s*:\s*james-shimmer",
            "active stage label must run james-shimmer animation",
        )

    def test_done_class_stops_animations(self):
        # Done stage: animations explicitly disabled.
        m = re.search(
            r"\.thinking-line\.thinking-done\s+\.thinking-icon[^{]*\{([^}]*)\}",
            self.css,
        )
        self.assertIsNotNone(m, "done-state icon rule missing")
        self.assertIn("animation: none", m.group(1),
                      "done-state must explicitly disable icon animation")

        # Label too — done state should stop shimmer.
        m2 = re.search(
            r"\.thinking-line\.thinking-done\s+\.thinking-label[^{]*\{([^}]*)\}",
            self.css,
        )
        self.assertIsNotNone(m2, "done-state label rule missing")
        self.assertIn("animation: none", m2.group(1))

    def test_stage_color_css_variable(self):
        # Each stage's color is injected via --stage-color so chat.js
        # can write the per-stage tint without inline styles.
        self.assertIn("--stage-color", self.css,
                      "CSS must use a --stage-color variable for "
                      "per-stage tinting")
        # Used in label gradient + drop-shadow.
        self.assertIn("var(--stage-color", self.css)


class ChatJsContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_appendtyping_uses_thinking_line_classes(self):
        idx = self.js.index("function appendTyping(traceId)")
        body = self.js[idx:idx + 4500]
        # Must add `thinking-active` for in-progress stages and
        # `thinking-done` for the final-state ones.
        self.assertIn("thinking-active", body,
                      "appendTyping must apply thinking-active class "
                      "to in-progress stages")
        self.assertIn("thinking-done", body,
                      "appendTyping must apply thinking-done class "
                      "to completed stages")

    def test_active_to_done_transition_present(self):
        idx = self.js.index("function appendTyping(traceId)")
        body = self.js[idx:idx + 4500]
        # markActiveAsDone should remove the active class and add
        # the done class — that's how each new stage's arrival
        # closes out the previous stage.
        self.assertIn("classList.remove('thinking-active')", body,
                      "markActiveAsDone must remove the active class")
        self.assertIn("classList.add('thinking-done')", body,
                      "markActiveAsDone must add the done class")

    def test_stage_color_set_via_css_variable(self):
        idx = self.js.index("function appendTyping(traceId)")
        body = self.js[idx:idx + 4500]
        self.assertIn("setProperty('--stage-color'", body,
                      "appendTyping must set --stage-color CSS variable "
                      "on each line so the CSS shimmer/spinner picks "
                      "up the per-stage tint")

    def test_complete_stage_marks_active_as_done(self):
        idx = self.js.index("function appendTyping(traceId)")
        body = self.js[idx:idx + 4500]
        # When data.complete arrives, the current active line must
        # be closed out — otherwise it keeps spinning forever.
        self.assertIn("markActiveAsDone()", body,
                      "complete-handler must call markActiveAsDone()")

    def test_no_static_old_thinking_search_label(self):
        # The v0.2.0 fake "Searching internal documents..." labels
        # were replaced by the polling stream in PR #97. They must
        # not have come back.
        body = self.js
        self.assertNotIn("chat.thinking_search", body,
                         "old i18n key chat.thinking_search must not be "
                         "referenced from chat.js — it was the fake "
                         "static label that PR #97 removed")


if __name__ == "__main__":
    unittest.main()
