"""[video-asr 2026-05-11] processors/file_processor.extract_video.

Replaces tests/test_video_reject.py from W1 §3-C. The reject path is
gone; the new contract is:

  /upload/ accepts video files (mp4/avi/mov/mkv/webm).
  file_processor.process_file → extract_video → ffmpeg subprocess
    pulls the audio track → Whisper transcribes → TrustedContent
    (source="asr", trust="low").
  Missing ffmpeg surfaces as a RuntimeError with a friendly install
    hint, not a silent stub or a NameError.

Live ffmpeg + Whisper is NOT exercised in CI — both are heavyweight
dependencies and Whisper model download is ~140 MB for "base". The
behavioural tests below either monkey-patch the helpers or assert
the documented error path.
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent


class UploadAcceptsVideoExtensionsTests(unittest.TestCase):
    """The /upload/ endpoint no longer rejects video extensions."""

    @classmethod
    def setUpClass(cls):
        # The /upload/ handler moved to routes/auth.py in v0.4.x PR-A.1
        # (server-split). Test scans both locations so a future move
        # back, or splitting upload into a separate router, does not
        # silently regress this invariant.
        candidates = [
            ROOT / "routes" / "auth.py",
            ROOT / "server_llmwiki.py",
        ]
        cls.src = "\n".join(
            p.read_text(encoding="utf-8") for p in candidates if p.exists()
        )

    def test_video_extensions_constant_removed(self):
        self.assertNotIn(
            "VIDEO_EXTENSIONS", self.src,
            "VIDEO_EXTENSIONS constant should be gone — video reject "
            "is no longer the policy (W1 §3-C Option A landed).",
        )

    def test_allowed_ext_includes_mp4(self):
        # Locate the allowed_ext tuple and confirm video extensions
        # are present.
        m = re.search(r"allowed_ext\s*=\s*\((.+?)\)", self.src, re.DOTALL)
        self.assertIsNotNone(m, "allowed_ext tuple not found in /upload/")
        body = m.group(1)
        for ext in (".mp4", ".avi", ".mov", ".mkv", ".webm"):
            self.assertIn(ext, body,
                          f"{ext} should be in allowed_ext for video-asr")

    def test_no_422_video_reject_branch(self):
        self.assertNotRegex(
            self.src,
            r"현재 영상 파일은 미지원입니다",
            "Friendly 422 video-reject message should be gone — the "
            "new path runs extract_video instead.",
        )


class ExtractVideoDispatchTests(unittest.TestCase):
    """file_processor.process_file dispatches video to extract_video."""

    def test_dispatch_table_routes_video(self):
        src = (ROOT / "processors" / "file_processor.py").read_text(encoding="utf-8")
        self.assertIn(
            'elif ext in ["mp4", "avi", "mov", "mkv", "webm"]', src,
            "dispatch should branch to video path for the 5 extensions",
        )
        # And the branch calls self.extract_video — not a placeholder.
        # ``re.DOTALL`` so ``.*?`` spans newlines between the elif
        # header and the inner = … line.
        m = re.search(
            r'elif ext in \["mp4", "avi", "mov", "mkv", "webm"\]:.*?'
            r'inner\s*=\s*self\.extract_video\(filepath\)',
            src, re.DOTALL,
        )
        self.assertIsNotNone(
            m,
            "video branch should invoke self.extract_video — current "
            "dispatch body does not match the expected wiring",
        )


class ExtractVideoMissingFfmpegTests(unittest.TestCase):
    """When ffmpeg is not on PATH, extract_video raises RuntimeError
    with a friendly install hint — never returns a silent stub."""

    def test_missing_ffmpeg_raises_with_install_hint(self):
        from processors.file_processor import FileProcessor
        from unittest.mock import patch
        fp = FileProcessor()
        # Force shutil.which to return None — simulate missing ffmpeg
        # in the subprocess module the handler imports locally.
        with patch("shutil.which", return_value=None):
            with self.assertRaises(RuntimeError) as cm:
                fp.extract_video("anything.mp4")
        msg = str(cm.exception)
        self.assertIn("ffmpeg", msg.lower())
        self.assertIn("winget install", msg.lower()
                                       + "  " + msg.lower(),  # tolerate case
                      f"missing-ffmpeg error should hint Windows install: {msg}")


class ExtractVideoFailedExtractionTests(unittest.TestCase):
    """ffmpeg present but the audio extraction fails (corrupt file,
    no audio track, etc.) — extract_video should raise a RuntimeError
    naming the failure mode, not a silent empty TrustedContent."""

    def test_ffmpeg_nonzero_returncode_raises(self):
        from processors.file_processor import FileProcessor
        from unittest.mock import patch, MagicMock
        fp = FileProcessor()
        with patch("shutil.which", return_value="/fake/ffmpeg"):
            mock_proc = MagicMock(returncode=1, stderr=b"corrupt input")
            with patch("subprocess.run", return_value=mock_proc):
                with self.assertRaises(RuntimeError) as cm:
                    fp.extract_video("anything.mp4")
        self.assertIn("ffmpeg 추출 실패", str(cm.exception))
        self.assertIn("corrupt input", str(cm.exception))

    def test_zero_byte_audio_output_raises(self):
        # ffmpeg returned 0 (success) but produced an empty wav file —
        # typical for "video has no audio track".
        from processors.file_processor import FileProcessor
        from unittest.mock import patch, MagicMock
        import tempfile
        fp = FileProcessor()
        # Create a real empty temp file so getsize works.
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        try:
            with patch("shutil.which", return_value="/fake/ffmpeg"):
                mock_proc = MagicMock(returncode=0, stderr=b"")
                # NamedTemporaryFile re-call inside extract_video would
                # create a different path; instead monkey-patch
                # tempfile.NamedTemporaryFile to return our zero-byte one.
                with patch("subprocess.run", return_value=mock_proc), \
                     patch("tempfile.NamedTemporaryFile") as mock_tf:
                    mock_tf.return_value = MagicMock(
                        name=tmp.name, close=lambda: None,
                    )
                    mock_tf.return_value.__enter__ = lambda s: s
                    mock_tf.return_value.__exit__  = lambda *a: None
                    # Make .name attribute work as a property.
                    mock_tf.return_value.name = tmp.name
                    with self.assertRaises(RuntimeError) as cm:
                        fp.extract_video("input.mp4")
            self.assertIn("오디오", str(cm.exception))
        finally:
            try: os.unlink(tmp.name)
            except OSError: pass


class ExtractVideoHappyPathTests(unittest.TestCase):
    """ffmpeg present + non-empty audio + Whisper monkey-patch →
    TrustedContent with source='asr', trust='low'."""

    def test_returns_trusted_content_with_asr_provenance(self):
        from processors.file_processor import FileProcessor
        from core.policy_engine import TrustedContent
        from unittest.mock import patch, MagicMock
        import tempfile, os

        fp = FileProcessor()
        # Stub the audio extractor so we never touch real Whisper.
        fp.extract_audio = MagicMock(return_value=TrustedContent(
            text="[음성 변환]\n안녕하세요 회의록입니다",
            source="asr", trust="low",
        ))

        # Real temp file with > 1000 bytes so the size guard passes.
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.write(b"x" * 2000)
        tmp.close()
        try:
            with patch("shutil.which", return_value="/fake/ffmpeg"):
                mock_proc = MagicMock(returncode=0, stderr=b"")
                with patch("subprocess.run", return_value=mock_proc), \
                     patch("tempfile.NamedTemporaryFile") as mock_tf:
                    holder = MagicMock(name=tmp.name)
                    holder.name = tmp.name
                    holder.close = lambda: None
                    mock_tf.return_value = holder
                    out = fp.extract_video("input.mp4")
        finally:
            try: os.unlink(tmp.name)
            except OSError: pass

        self.assertIsInstance(out, TrustedContent)
        self.assertEqual(out.source, "asr")
        self.assertEqual(out.trust,  "low")
        # The "[음성 변환]" prefix is stripped and replaced with
        # "[영상 음성 변환]" so the operator can tell apart audio-only
        # uploads from video transcriptions.
        self.assertIn("[영상 음성 변환]", out.text)
        self.assertIn("안녕하세요 회의록입니다", out.text)


if __name__ == "__main__":
    unittest.main()
