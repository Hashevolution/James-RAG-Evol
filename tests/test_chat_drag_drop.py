"""Chat-page drag-drop file upload (item #7, 2026-05-08).

User feedback: "이미지나 문서 파일을 대화창에도 업로드 드롭 가능하게".

Source-level contracts on frontend/static/upload.js:

  - The chat page (detected via #messages presence) registers
    window-level dragenter/dragover/dragleave/drop handlers.
  - drop calls addFiles(...) so the file enters the same upload
    queue as the sidebar dropzone.
  - dragover preventDefault is present (else browser opens the
    file in a new tab when the user misses the dropzone).
  - Files-only filter — dragenter ignores text/link drags so a
    word-drag-select doesn't show the overlay.
  - Visual overlay (#chat-drop-overlay) created once and toggled.
  - Drop-counter pattern (dragDepth) so child-element dragenter
    doesn't cause overlay flicker.
  - Sidebar auto-opens on drop so the user sees the upload queue.

Run:
  python -m unittest tests.test_chat_drag_drop
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

JS = Path(__file__).resolve().parent.parent / "frontend" / "static" / "upload.js"


class ChatDropzoneContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_setup_function_exists(self):
        self.assertIn("setupChatDropzone", self.js,
                      "setupChatDropzone IIFE missing")

    def test_chat_page_detection(self):
        # Should bail out if #messages doesn't exist (not chat page).
        self.assertIn("getElementById('messages')", self.js)

    def test_window_listeners_registered(self):
        # All four drag events on window scope.
        for ev in ("dragenter", "dragover", "dragleave", "drop"):
            self.assertIn(f"window.addEventListener('{ev}'", self.js,
                          f"window.addEventListener('{ev}') missing")

    def test_dragover_prevent_default(self):
        # Critical: without preventDefault on dragover, drop never fires
        # AND missed-target drops open the file in a new tab.
        idx = self.js.index("window.addEventListener('dragover'")
        body = self.js[idx:idx + 600]
        self.assertIn("e.preventDefault()", body,
                      "dragover handler must call e.preventDefault()")

    def test_files_only_filter(self):
        # Should ignore text drags / link drags via dataTransfer.types check.
        self.assertIn("includes('Files')", self.js,
                      "must filter to file drags only — text drags should "
                      "not trigger the overlay")

    def test_drop_calls_add_files(self):
        idx = self.js.index("window.addEventListener('drop'")
        body = self.js[idx:idx + 800]
        self.assertIn("addFiles(files)", body,
                      "drop handler must call addFiles(files) to enter "
                      "the same queue as the sidebar dropzone")

    def test_drop_counter_pattern(self):
        # Without a counter, child-element dragenter causes overlay flicker.
        self.assertIn("dragDepth", self.js,
                      "drop-counter pattern (dragDepth) missing — overlay "
                      "will flicker when dragging across child elements")

    def test_visual_overlay_created(self):
        self.assertIn("chat-drop-overlay", self.js,
                      "visual overlay element missing")
        # Overlay should have user-visible affordance text.
        self.assertIn("여기에 놓으면", self.js,
                      "overlay must show user-visible drop hint")

    def test_sidebar_auto_open_on_drop(self):
        # User wants to see queue progress after dropping.
        idx = self.js.index("window.addEventListener('drop'")
        body = self.js[idx:idx + 1200]
        self.assertIn("toggleSidebar", body,
                      "drop handler should auto-open sidebar so user sees "
                      "the upload queue")


if __name__ == "__main__":
    unittest.main()
