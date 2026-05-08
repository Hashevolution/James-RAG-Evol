"""Folder drop + folder-picker upload (item #8, 2026-05-08).

User feedback: "파일 업로드 창에도 폴더 전체도 드롭 하고 업로드
가능하게 개선 검토".

Two ways to upload a folder:
  (A) Drag a folder onto the dropzone — webkitGetAsEntry traversal
      recursively walks the directory tree.
  (B) Click "📁 폴더 선택" button — <input type="file" webkitdirectory>
      opens the OS folder picker.

In both cases each File gets a `relPath` attribute reflecting the
folder structure ("folder/sub/file.ext"). Existing addFiles() queue
treats these as ordinary files; relPath is opt-in metadata for
future per-folder routing.

Source-level contracts:
  - upload.js exports _filesFromEntry / _filesFromDataTransfer
    helpers for tests.
  - Both drop sites (sidebar #drop-zone + window-level chat overlay)
    use _filesFromDataTransfer instead of dataTransfer.files
    directly.
  - readEntries loop until empty (handles batch limit).
  - <input id="folder-input" webkitdirectory> exists in chat HTML.
  - "📁 폴더 선택" button onclick → folder-input.click().
  - file-input change handler captures webkitRelativePath into
    f.relPath via _captureRelPath helper.

Run:
  python -m unittest tests.test_folder_upload
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
JS   = ROOT / "frontend" / "static" / "upload.js"
HTML = ROOT / "frontend" / "index.html"


class JsHelpersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_filesfromentry_function_exists(self):
        self.assertIn("async function _filesFromEntry", self.js,
                      "_filesFromEntry helper missing")

    def test_filesfromdatatransfer_function_exists(self):
        self.assertIn("async function _filesFromDataTransfer", self.js,
                      "_filesFromDataTransfer helper missing")

    def test_uses_webkit_get_as_entry(self):
        self.assertIn("webkitGetAsEntry", self.js,
                      "must use webkitGetAsEntry for folder traversal")

    def test_recursive_directory_handling(self):
        idx = self.js.index("async function _filesFromEntry")
        body = self.js[idx:idx + 2000]
        self.assertIn("entry.isDirectory", body)
        self.assertIn("entry.createReader", body)
        # readEntries returns batches — must loop until empty.
        self.assertIn("readEntries", body)
        self.assertIn("while (true)", body,
                      "readEntries batch loop must continue until empty")

    def test_falls_back_to_dataTransfer_files(self):
        # When items / entries API unavailable, fall back to
        # dataTransfer.files (top-level only — best we can do).
        self.assertIn("dataTransfer.files", self.js,
                      "fallback to dataTransfer.files when entries API is unavailable")

    def test_capture_rel_path_helper(self):
        self.assertIn("function _captureRelPath", self.js,
                      "_captureRelPath helper missing — needed to copy "
                      "webkitRelativePath into f.relPath")
        self.assertIn("webkitRelativePath", self.js,
                      "webkitRelativePath must be read by file picker handler")


class DropHandlersUseHelperTests(unittest.TestCase):
    """Both drop handlers (sidebar + chat-page) must use the new
    _filesFromDataTransfer helper, NOT raw dataTransfer.files."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_sidebar_drop_uses_helper(self):
        # Sidebar dropZone.addEventListener('drop', ...) handler.
        idx = self.js.index("dropZone.addEventListener('drop'")
        body = self.js[idx:idx + 500]
        self.assertIn("_filesFromDataTransfer", body,
                      "sidebar drop handler must use _filesFromDataTransfer "
                      "(not raw dataTransfer.files) so folders are walked")

    def test_chat_window_drop_uses_helper(self):
        # window-level drop handler (item #7).
        idx = self.js.index("window.addEventListener('drop'")
        body = self.js[idx:idx + 1500]
        self.assertIn("_filesFromDataTransfer", body,
                      "chat window drop handler must use _filesFromDataTransfer")


class HtmlFolderInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")

    def test_folder_input_present(self):
        self.assertIn('id="folder-input"', self.html,
                      "folder-input <input> missing")
        self.assertIn("webkitdirectory", self.html,
                      "folder-input must have webkitdirectory attribute")

    def test_folder_select_button_present(self):
        # Visible "폴더 선택" button.
        self.assertIn("폴더 선택", self.html)
        # Triggering folder-input click via JS onclick.
        self.assertIn("folder-input').click()", self.html,
                      "polder button must trigger folder-input.click()")

    def test_dropzone_label_mentions_folder_support(self):
        # Affordance text — user should know folder-drop works too.
        self.assertIn("폴더 통째로 드래그", self.html,
                      "dropzone label should mention folder drag support")


class FolderInputJsHandlerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_folder_input_change_handler(self):
        # The folder-input listener must exist and call addFiles.
        self.assertIn("getElementById('folder-input')", self.js,
                      "folder-input handler missing")
        idx = self.js.index("getElementById('folder-input')")
        body = self.js[idx:idx + 800]
        self.assertIn("addFiles(", body,
                      "folder-input change must call addFiles")
        self.assertIn("_captureRelPath", body,
                      "folder-input handler must capture relPath via helper")


if __name__ == "__main__":
    unittest.main()
