"""Upload UI compaction + interruption detection (item #7-A + #7-B, 2026-05-08).

User feedback:
  #7-A: "업로드 UI 재구성 (smaller dropzone, scrollable queue)" —
        the dropzone takes too much vertical space, leaving little
        room to see queued files.
  #7-B: "업로드 중단 감지" — when network drops mid-upload, the
        client used to hang indefinitely. Want explicit detection.

CSS changes (#7-A):
  - .drop-zone padding 24px → 14px, margin 16 → 10/12
  - .drop-icon font-size 24 → 18, margin-bottom 8 → 4
  - .drop-label font-size 13 → 12; .drop-types 11 → 10

JS changes (#7-B):
  - UPLOAD_TIMEOUT_MS = 5min, xhr.timeout + ontimeout listener
  - UPLOAD_STALL_MS = 30s, watchdog interval that aborts on stall
  - beforeunload guard when uploads in flight
  - error labels: 'timeout' / 'stalled' get distinct messages

Run:
  python -m unittest tests.test_upload_compact_resilient
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "frontend" / "index.html"
CSS  = ROOT / "frontend" / "static" / "chat.css"
JS   = ROOT / "frontend" / "static" / "upload.js"


class CompactDropzoneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # [v0.2.x #8] .drop-zone styles moved from index.html's
        # inline <style> to static/chat.css. Combining the two keeps
        # the regex-on-text assertions source-agnostic.
        cls.html = (HTML.read_text(encoding="utf-8")
                    + "\n"
                    + CSS.read_text(encoding="utf-8"))

    def _drop_zone_rule(self):
        m = re.search(r"\.drop-zone\s*\{([^}]+)\}", self.html)
        self.assertIsNotNone(m, ".drop-zone rule missing")
        return m.group(1)

    def test_padding_smaller(self):
        # The dropzone padding should be less than the previous 24px.
        body = self._drop_zone_rule()
        m = re.search(r"padding:\s*(\d+)px", body)
        self.assertIsNotNone(m)
        self.assertLess(int(m.group(1)), 24,
            f"padding still {m.group(1)}px (was 24px) — must shrink for compact UI")

    def test_drop_icon_smaller(self):
        m = re.search(r"\.drop-icon\s*\{[^}]*font-size:\s*(\d+)px", self.html)
        self.assertIsNotNone(m)
        self.assertLess(int(m.group(1)), 24,
            f"drop-icon font-size still {m.group(1)}px — must shrink")

    def test_drop_label_compact(self):
        # Smaller label too.
        m = re.search(r"\.drop-label\s*\{[^}]*font-size:\s*(\d+)px", self.html)
        self.assertIsNotNone(m)
        self.assertLessEqual(int(m.group(1)), 12,
            f"drop-label font-size still {m.group(1)}px — must be ≤ 12 now")


class UploadResilienceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_timeout_constant_defined(self):
        self.assertIn("UPLOAD_TIMEOUT_MS", self.js,
            "must define UPLOAD_TIMEOUT_MS for hard upload cutoff")
        m = re.search(r"UPLOAD_TIMEOUT_MS\s*=\s*([\dE+]+\s*\*\s*\d+\s*\*\s*\d+|\d+)", self.js)
        self.assertIsNotNone(m, "couldn't parse UPLOAD_TIMEOUT_MS literal")

    def test_stall_constant_defined(self):
        self.assertIn("UPLOAD_STALL_MS", self.js,
            "must define UPLOAD_STALL_MS for inactivity watchdog")

    def test_xhr_timeout_set(self):
        # The xhr instance gets timeout + listener.
        self.assertIn("xhr.timeout = UPLOAD_TIMEOUT_MS", self.js,
            "xhr.timeout must be set to the constant")
        self.assertIn("'timeout'", self.js,
            "must emit 'timeout' error message for the rejection")

    def test_stall_watchdog_uses_setInterval(self):
        idx = self.js.index("function uploadOne")
        end = idx + 3500
        body = self.js[idx:end]
        self.assertIn("setInterval", body,
            "stall watchdog should poll via setInterval")
        self.assertIn("'stalled'", body,
            "stall path must reject with 'stalled'")
        self.assertIn("clearInterval", body,
            "must clear the watchdog on success/error/abort")

    def test_lastProgressMs_updated_on_progress(self):
        idx = self.js.index("function uploadOne")
        end = idx + 3500
        body = self.js[idx:end]
        self.assertIn("lastProgressMs", body,
            "watchdog needs a timestamp updated on each progress event")
        # The progress handler must touch the timestamp.
        m = re.search(r"xhr\.upload\.addEventListener\('progress',[^}]+lastProgressMs\s*=\s*Date\.now\(\)",
                      body, re.DOTALL)
        self.assertIsNotNone(m,
            "lastProgressMs must be refreshed inside the progress listener")

    def test_beforeunload_guard(self):
        self.assertIn("'beforeunload'", self.js,
            "must register a beforeunload listener to warn on close during upload")
        idx = self.js.index("'beforeunload'")
        body = self.js[idx:idx + 800]
        self.assertIn("uploadQueue", body,
            "guard must inspect the upload queue")
        self.assertIn("preventDefault", body,
            "must call preventDefault for the standard browser dialog")

    def test_error_labels_for_new_types(self):
        # uploadFiles error branch should distinguish timeout / stalled.
        idx = self.js.index("function uploadFiles")
        end = idx + 4000
        body = self.js[idx:end]
        self.assertIn("'timeout'", body)
        self.assertIn("'stalled'", body)
        self.assertIn("시간 초과", body,
            "timeout label needs Korean copy")
        self.assertIn("연결 끊김", body,
            "stalled label needs Korean copy")


if __name__ == "__main__":
    unittest.main()
