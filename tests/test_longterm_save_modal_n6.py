"""Long-term save modal — replace native confirm() with 6c-glass dialog (N-6).

User feedback (Axis 6 follow-up, 2026-05-13):

  > 장기기억으로 저장할까요? 묻는 창이 뜨는것 ui 개선

The "위키 저장 (장기 기억화)" chip in chat.js (approveWikiSave) used to
pop the native browser ``confirm()`` dialog — which breaks the cyber
surface's typography on Windows/Linux and never picks up the cyber 6c
glassmorphism (backdrop-filter + mint inset glow) from tokens.css.

Fix:
  - New ``jamesConfirm(opts)`` helper in chat.js returns Promise<boolean>
    and builds a ``.modal-overlay`` + ``.modal`` DOM tree that tokens.css
    automatically picks up via ``@supports (backdrop-filter)``.
  - ``approveWikiSave`` switches from ``confirm(...)`` to
    ``await jamesConfirm({...})``.
  - The dialog has the ARIA shape (``role=dialog`` / ``aria-modal=true``
    / ``aria-labelledby``) and the ``.modal-btn.cancel`` button that
    a11y-modal.js relies on for focus trap + Escape close.

Out of scope: session-reset confirm at chat.js L588 (different flow —
""현재 대화를 초기화할까요?", not the long-term-save question).

Run:
  python -m unittest tests.test_longterm_save_modal_n6
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
JS   = ROOT / "frontend" / "static" / "chat.js"


class JamesConfirmHelperTests(unittest.TestCase):
    """The new in-page confirm helper exists, returns a Promise, builds
    a .modal-overlay / .modal DOM that tokens.css can decorate, and
    carries the ARIA shape a11y-modal.js needs."""

    @classmethod
    def setUpClass(cls):
        cls.src = JS.read_text(encoding="utf-8")

    def test_jamesConfirm_function_defined(self):
        self.assertRegex(
            self.src,
            r"function\s+jamesConfirm\s*\(\s*opts\s*\)",
            "jamesConfirm(opts) must be defined as a top-level function",
        )

    def test_jamesConfirm_returns_promise(self):
        # Implementation must wrap resolve in a Promise so callers can
        # await — the whole point of replacing native confirm().
        body = self._helper_body()
        self.assertIn("return new Promise", body,
            "jamesConfirm must return new Promise so callers can await it")

    def _helper_body(self) -> str:
        idx = self.src.index("function jamesConfirm")
        # Find the matching close brace by counting — but a flat 3000-char
        # window is enough for the helper itself.
        return self.src[idx:idx + 3000]

    def test_modal_uses_canonical_classes(self):
        # tokens.css's @supports (backdrop-filter) block targets
        # exactly ``.modal-overlay`` and ``.modal`` — using those class
        # names is what makes the 6c glass + mint pickup automatic.
        body = self._helper_body() + self._ensure_body()
        self.assertIn("modal-overlay", body,
            "modal must use class 'modal-overlay' so tokens.css "
            "backdrop-filter rule applies")
        self.assertIn('class="modal"', body,
            "inner card must use class 'modal' so tokens.css "
            "mint inset glow + heavier blur applies")

    def _ensure_body(self) -> str:
        idx = self.src.index("function _ensureJamesConfirmEl")
        return self.src[idx:idx + 2500]

    def test_modal_carries_aria_attributes(self):
        body = self._ensure_body()
        # WCAG dialog pattern + what a11y-modal.js's [role="dialog"]
        # observer relies on.
        for attr in ('role',
                     'aria-modal',
                     'aria-labelledby'):
            self.assertIn(attr, body,
                f"modal must declare {attr} so a11y-modal.js traps focus "
                "and Escape-closes correctly")

    def test_cancel_button_has_modal_btn_cancel_class(self):
        # a11y-modal.js fires Escape close by clicking
        # ``.modal-btn.cancel`` — without this class Escape won't close
        # the dialog.
        body = self._ensure_body()
        self.assertIn('class="modal-btn cancel"', body,
            "Cancel button must carry class 'modal-btn cancel' so "
            "a11y-modal.js Escape handler can find it")

    def test_helper_resolves_false_on_cancel_and_backdrop(self):
        body = self._helper_body()
        # The contract: cancel and backdrop both resolve(false); only
        # the confirm button resolves(true). Hard to assert directly,
        # but we can pin the close(false) calls.
        self.assertGreaterEqual(
            body.count("close(false)"), 2,
            "Cancel button click AND backdrop click must both resolve "
            "false — they are the two non-confirm exit paths")
        self.assertIn("close(true)", body,
            "Confirm button click must resolve true")


class ApproveWikiSaveCallsiteTests(unittest.TestCase):
    """approveWikiSave now uses jamesConfirm instead of native confirm()."""

    @classmethod
    def setUpClass(cls):
        cls.src = JS.read_text(encoding="utf-8")

    def _approveWikiSave_body(self) -> str:
        idx = self.src.index("async function approveWikiSave")
        end = self.src.index("\nfunction ", idx + 1)
        return self.src[idx:end]

    def test_native_confirm_gone(self):
        # The native call used to be:
        #   if (!confirm('이 검색 결과를 wiki entity로 ...')) return;
        body = self._approveWikiSave_body()
        self.assertNotIn(
            "confirm('이 검색 결과를 wiki entity",
            body,
            "approveWikiSave must no longer use native confirm() — N-6 "
            "replaces it with the in-page jamesConfirm modal")

    def test_uses_jamesConfirm_with_await(self):
        body = self._approveWikiSave_body()
        self.assertIn("await jamesConfirm(", body,
            "approveWikiSave must await jamesConfirm so the user's "
            "choice gates the network call")

    def test_modal_message_mentions_longterm_save(self):
        # The user-facing string still has to say 장기 기억 / wiki / 영구
        # so the operator understands what they're approving — same
        # information that the old confirm() carried.
        body = self._approveWikiSave_body()
        self.assertRegex(body, r"장기 기억|wiki|영구",
            "modal message must still describe what's being saved")


if __name__ == "__main__":
    unittest.main()
