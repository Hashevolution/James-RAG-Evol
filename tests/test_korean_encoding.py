"""Korean encoding regression guard.

Background: Windows default `open()` encoding is cp949. Korean text
written without an explicit `encoding="utf-8"` lands as cp949 bytes,
which downstream utf-8 readers (ReadFileTool, CodeReader, server
parsers) then mojibake. The visible artifact is `���` replacement
chars in tool output / lifecycle logs / phase reports.

This file exists so a future contributor reintroducing the bug fails
the test rather than discovering it months later in a stray report
file.

Coverage:
  - Source-level: scan the three known-fragile self-test sites and
    `tools/patch/bench_gate.py` subprocess call to assert they keep
    the explicit `encoding="utf-8"` after edits.
  - Behavioral: round-trip a Korean string through write+read using
    the patterns the production code uses, asserting no replacement
    chars survive.

Run:
  python -m unittest tests.test_korean_encoding
"""
from __future__ import annotations

import inspect
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class WriteEncodingExplicitTests(unittest.TestCase):
    """The three self-test files that previously corrupted Korean
    comments must keep `encoding="utf-8"` on their workspace open()
    calls. A regression here means a future edit dropped the kwarg
    and the bug is back."""

    def _assert_open_w_has_utf8(self, source: str, target_substr: str) -> None:
        """Assert that the source contains an `open(..., "w", encoding="utf-8")`
        call whose path argument contains `target_substr`. The path may
        be a longer relative form (e.g. "./workspace/_diag_test.py") —
        the substring just has to appear before `, "w", encoding=`."""
        normalized = " ".join(source.split())
        # The path string ends with target_substr; what follows is
        # `, "w", encoding="utf-8"`. Either quote style is accepted.
        needle_a = f'{target_substr}", "w", encoding="utf-8"'
        needle_b = f"{target_substr}', 'w', encoding=\"utf-8\""
        needle_c = f"{target_substr}\", 'w', encoding=\"utf-8\""  # mixed quotes
        self.assertTrue(
            any(n in normalized for n in (needle_a, needle_b, needle_c)),
            f"open(..., 'w', encoding='utf-8') missing for path containing "
            f"{target_substr!r}; this re-introduces the cp949 corruption bug.",
        )

    def test_phase55_diag_test_uses_utf8(self):
        path = Path(__file__).resolve().parent.parent / "james_phase55_test.py"
        src = path.read_text(encoding="utf-8")
        self._assert_open_w_has_utf8(src, "_diag_test.py")

    def test_phase6_patch_test_uses_utf8(self):
        path = Path(__file__).resolve().parent.parent / "james_phase6_test.py"
        src = path.read_text(encoding="utf-8")
        self._assert_open_w_has_utf8(src, "_patch_test.py")

    def test_code_reader_self_test_uses_utf8(self):
        path = Path(__file__).resolve().parent.parent / "tools" / "code" / "code_reader.py"
        src = path.read_text(encoding="utf-8")
        # code_reader.py self-test path is "./workspace/test.py"
        self._assert_open_w_has_utf8(src, "test.py")


class SubprocessEncodingTests(unittest.TestCase):
    """bench_gate.py runs scripts/bench.py as a subprocess and captures
    stdout/stderr to record_outcome.detail. Without encoding="utf-8"
    on subprocess.run, Korean query strings printed by bench.py decode
    via locale.getpreferredencoding() (cp949 on Korean Windows),
    landing mojibake into the audit log."""

    def test_bench_gate_subprocess_uses_utf8_explicitly(self):
        from tools.patch import bench_gate as bg
        src = inspect.getsource(bg._run_bench_check_blocking)
        self.assertIn('encoding="utf-8"', src,
                      "bench_gate subprocess.run must declare encoding='utf-8' "
                      "to avoid cp949 mojibake on the captured tail")
        self.assertIn('errors="replace"', src,
                      "bench_gate subprocess.run should set errors='replace' "
                      "so an unexpected non-utf-8 byte sequence does not crash")


class WriteRoundtripTests(unittest.TestCase):
    """Behavioral guard: writing Korean with the standard utf-8 pattern
    and reading it back must NOT produce replacement characters.

    The point isn't to test Python's stdlib — it's to demonstrate the
    expected pattern so a contributor copying from this test gets it
    right by default."""

    def test_korean_roundtrip_utf8_no_mojibake(self):
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".py", delete=False
        ) as f:
            payload = "# 진단 테스트 파일\nprint('hello')\n"
            f.write(payload)
            path = Path(f.name)
        try:
            # Read back via the same pattern ReadFileTool / CodeReader use:
            # explicit utf-8 + errors='replace'.
            content = path.read_text(encoding="utf-8", errors="replace")
            self.assertEqual(content, payload,
                             "roundtrip must preserve Korean exactly")
            self.assertNotIn("�", content,
                             "no Unicode replacement char allowed")
        finally:
            path.unlink(missing_ok=True)

    def test_korean_corruption_demo_when_encoding_omitted(self):
        # Demonstrates the bug we're guarding against: writing without
        # encoding on Windows = cp949, reading with utf-8 = replacement
        # chars. On non-Windows this test is a no-op (locale defaults
        # are usually utf-8). The assertion is conditional.
        if sys.platform != "win32":
            self.skipTest("cp949 corruption only manifests on Windows defaults")

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False  # NO encoding kwarg
        ) as f:
            payload = "# 진단 테스트 파일\n"
            try:
                f.write(payload)
                wrote_ok = True
            except UnicodeEncodeError:
                # Some Windows configs reject Korean → cp949 outright.
                # That's a different failure mode but same root cause.
                wrote_ok = False
            path = Path(f.name)

        try:
            if not wrote_ok:
                # Skip the read assertion — Python refused to write.
                # The point (open() without encoding is unsafe) is made.
                return
            corrupted = path.read_text(encoding="utf-8", errors="replace")
            # On cp949 Windows the read produces replacement chars.
            self.assertIn("�", corrupted,
                          "expected replacement chars from cp949→utf-8 misdecode")
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
