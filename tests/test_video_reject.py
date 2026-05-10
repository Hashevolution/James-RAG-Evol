"""[video-reject 2026-05-10] W1 진단 §3-C Option C — 영상 업로드 거부.

W1 진단 결과: processors/file_processor.py 의 extract_video 가 stub
("[영상 분석 결과 - 샘플링 기반]")이라 영상 업로드 시 silent failure
→ ChromaDB 노이즈 인덱스 + 사용자에게는 "처리 완료"로 보고.

권고 (Option C → A):
  1. 즉시: 영상 업로드 거부 + UI 안내 (이 PR)
  2. 후속: ffmpeg + Whisper + frame caption 합성 (video-asr PR)

이 테스트는 거부 layering 을 검증한다:
  • Backend layer 1 — server_llmwiki.py /upload/ 가 422 + 친절 메시지
  • Backend layer 2 (defense-in-depth) — file_processor.process_file
    이 직접 호출되어도 silent stub 대신 unsupported placeholder
  • Frontend layer 1 — upload.js addFiles 가 video 필터 + toast
  • Frontend layer 2 — index.html accept attr 에서 video/* 제거,
                       i18n upload.types 라벨에서 "영상" 제거

Run:
    python -m unittest tests.test_video_reject
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent


class BackendUploadRejectionTests(unittest.TestCase):
    """server_llmwiki.py /upload/ — 422 거부 + 친절 메시지."""

    @classmethod
    def setUpClass(cls):
        cls.src = (ROOT / "server_llmwiki.py").read_text(encoding="utf-8")

    def test_video_extensions_constant_defined(self):
        self.assertRegex(
            self.src,
            r"VIDEO_EXTENSIONS\s*=\s*\(\s*\"\.mp4\"\s*,\s*\"\.avi\"\s*,\s*\"\.mov\"\s*,\s*\"\.mkv\"\s*\)",
            "/upload/ 안에 VIDEO_EXTENSIONS 튜플이 없음 — 거부 분기 누락 가능",
        )

    def test_returns_422_for_video(self):
        # 422 + HTTPException 패턴이 video 거부 경로에서 발화되어야.
        m = re.search(
            r"VIDEO_EXTENSIONS.*?HTTPException\s*\(\s*\n?\s*status_code\s*=\s*422",
            self.src, re.DOTALL,
        )
        self.assertIsNotNone(
            m, "video 거부 분기가 422 status_code 로 응답하지 않음")

    def test_message_explains_alternatives(self):
        # 사용자가 무엇을 해야 할지 알려주는 안내 (.mp3/.wav 등) 포함.
        self.assertIn(".mp3", self.src)
        self.assertIn("음성", self.src)

    def test_allowed_ext_no_longer_includes_video(self):
        # 제거 확인 — allowed_ext 튜플 안에 mp4/avi/mov/mkv 가 없어야.
        m = re.search(
            r"allowed_ext\s*=\s*\(([^)]+)\)", self.src, re.DOTALL,
        )
        self.assertIsNotNone(m, "allowed_ext 튜플을 찾지 못함")
        body = m.group(1)
        for ext in (".mp4", ".avi", ".mov", ".mkv"):
            self.assertNotIn(
                ext, body,
                f"allowed_ext 에 {ext} 가 남아있음 — 거부 우회 위험",
            )
        # 음성 파일은 유지 (regression guard).
        for ext in (".mp3", ".wav", ".m4a", ".ogg"):
            self.assertIn(ext, body, f"audio {ext} 가 사라짐 — 회귀")


class FileProcessorDefenseInDepthTests(unittest.TestCase):
    """processors/file_processor.py — extract_video stub 제거."""

    @classmethod
    def setUpClass(cls):
        cls.src = (ROOT / "processors" / "file_processor.py").read_text(
            encoding="utf-8")

    def test_extract_video_method_removed(self):
        # 메서드 정의 자체가 사라져야 함. 주석 안 ("extract_video 는 …")
        # 으로의 언급은 허용 — `def extract_video` 만 차단.
        self.assertNotRegex(
            self.src, r"^\s*def\s+extract_video\b",
            "extract_video method 가 부활하면 silent failure 위험",
        )

    def test_old_stub_text_removed(self):
        # silent failure 의 흔적이었던 stub 문자열이 코드에 더 이상 있으면 안 됨.
        # (주석 안의 역사 언급은 허용 — 실제 반환 경로의 placeholder 만 차단.)
        # 가장 보수적 검증: 정확히 그 stub 텍스트가 TrustedContent text=
        # 인자로 들어가는 경우만 차단.
        self.assertNotRegex(
            self.src,
            r"text\s*=\s*\"\[영상 분석 결과 - 샘플링 기반\]\"",
            "stub TrustedContent 가 아직 남아있음 — silent failure 부활",
        )

    def test_dispatch_video_returns_unsupported(self):
        # mp4/avi/mov/mkv 분기가 unsupported placeholder 텍스트를 돌려주는
        # 코드 경로가 존재해야.
        self.assertIn("지원하지 않는 형식 — 영상 파일", self.src)


class FrontendUploadFilterTests(unittest.TestCase):
    """upload.js — addFiles 에서 video 필터 + toast 안내."""

    @classmethod
    def setUpClass(cls):
        cls.src = (ROOT / "frontend" / "static" / "upload.js").read_text(
            encoding="utf-8")

    def test_video_extensions_list_defined(self):
        self.assertRegex(
            self.src,
            r"VIDEO_EXTS\s*=\s*\[[^\]]*'mp4'[^\]]*'avi'[^\]]*'mov'[^\]]*'mkv'",
            "VIDEO_EXTS 가 정의되지 않음",
        )

    def test_isVideoFile_helper_exists(self):
        self.assertIn("_isVideoFile", self.src,
                      "_isVideoFile 헬퍼가 없음")

    def test_addFiles_filters_video(self):
        # addFiles 함수 안에서 video 가 필터되고 rejected 배열에 모이는 패턴.
        m = re.search(
            r"function\s+addFiles\s*\([^)]*\)\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}",
            self.src, re.DOTALL,
        )
        self.assertIsNotNone(m, "addFiles 함수 본체를 못 찾음")
        body = m.group(1)
        self.assertIn("_isVideoFile", body,
                      "addFiles 에서 _isVideoFile 가 호출되지 않음")
        self.assertIn("rejected", body,
                      "addFiles 에서 거부 리스트 추적 X")

    def test_toast_calls_video_unsupported_key(self):
        self.assertIn("upload.video_unsupported", self.src,
                      "i18n key 'upload.video_unsupported' 가 사용되지 않음")


class I18nLabelTests(unittest.TestCase):
    """i18n.js — upload.types 라벨에서 '영상/Video' 제거 + 신규 toast 키."""

    @classmethod
    def setUpClass(cls):
        cls.src = (ROOT / "frontend" / "static" / "i18n.js").read_text(
            encoding="utf-8")

    def test_video_unsupported_key_present_ko_en(self):
        # 한 번이라도 정의가 있으면 OK (en/ko 둘 다).
        self.assertGreaterEqual(
            self.src.count("'upload.video_unsupported'"), 2,
            "upload.video_unsupported 키가 ko/en 양쪽에 정의되어야",
        )

    def test_upload_types_label_removed_video_word(self):
        # ko: "이미지 · 영상 · 오디오 …" → "영상" 제거
        # en: "Image · Video · Audio …" → "Video" 제거
        m_ko = re.search(
            r"'upload\.types'\s*:\s*'이미지[^']*'", self.src,
        )
        self.assertIsNotNone(m_ko)
        self.assertNotIn("영상", m_ko.group(0))

        m_en = re.search(
            r"'upload\.types'\s*:\s*'Image[^']*'", self.src,
        )
        self.assertIsNotNone(m_en)
        self.assertNotIn("Video", m_en.group(0))


class HtmlAcceptAttrTests(unittest.TestCase):
    """index.html accept 속성에서 video/* 제거."""

    @classmethod
    def setUpClass(cls):
        cls.src = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")

    def test_file_input_accept_no_video(self):
        m = re.search(
            r'<input[^>]*id="file-input"[^>]*accept="([^"]+)"', self.src,
        )
        self.assertIsNotNone(m, "file-input 의 accept 속성을 못 찾음")
        accept = m.group(1)
        self.assertNotIn("video/*", accept,
                         "file-input accept 에 video/* 가 남아있음")
        # 회귀 가드: image/audio/pdf 는 유지.
        self.assertIn("image/*", accept)
        self.assertIn("audio/*", accept)
        self.assertIn(".pdf", accept)


if __name__ == "__main__":
    unittest.main()
