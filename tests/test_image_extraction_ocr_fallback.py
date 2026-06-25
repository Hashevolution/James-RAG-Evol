"""v0.6.1 — image extraction: vision→OCR fallback + noise gate.

Guards the fix for "uploaded images formed no entities, and a naive OCR
fallback would dump garbage into the KG":

  * The old `len(text) < 10` gate could not tell a real transcription
    from the vision model's verbose "too blurry to read" apology, so the
    OCR fallback never fired. Now the vision prompt emits a `<NO_TEXT>`
    sentinel and `extract_image` routes to OCR on it.
  * OCR output is confidence-filtered (`_OCR_MIN_CONF`) and must pass
    `_looks_like_text`, so a blurry/textless photo (observed: 296k
    garbage chars) is discarded — `extract_image` then keeps an honest,
    NON-garbage marker instead of fabricated text.

These tests mock the vision + OCR calls (no model / Tesseract needed) so
they run fast and deterministically.

Run:
  python -m unittest tests.test_image_extraction_ocr_fallback
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _make_processor():
    """FileProcessor without running its heavy __init__ (vision client,
    metadata gen). We only exercise the pure extraction logic."""
    from processors.file_processor import FileProcessor
    fp = FileProcessor.__new__(FileProcessor)
    return fp


class LooksLikeText(unittest.TestCase):
    def setUp(self):
        self.fp = _make_processor()

    def test_real_text_passes(self):
        self.assertTrue(self.fp._looks_like_text(
            "미국 증권거래위원회(SEC)가 비트코인 spot ETF 11종을 일괄 승인했다."))
        self.assertTrue(self.fp._looks_like_text(
            "The quarterly report shows revenue of 12 million dollars."))
        # short-but-real caption (an actual qwen2.5vl read of a notice
        # photo) must NOT be rejected by the fragmentation guard.
        self.assertTrue(self.fp._looks_like_text("전장연, 7.1.08시 혜화R 버스타기"))

    def test_noise_and_empty_fail(self):
        self.assertFalse(self.fp._looks_like_text(""))
        self.assertFalse(self.fp._looks_like_text("안녕"))           # too short
        self.assertFalse(self.fp._looks_like_text("▒█▒█ ░░ █▒ ▓▓"))  # block noise
        self.assertFalse(self.fp._looks_like_text("!@#$ %^&* ()[] {}|\\"))
        # fragmented single-char garbage — the real confidence-passed
        # Tesseract output on an unreadable photo (de-binarized path). Has
        # many valid Hangul/digit chars but no real words → must be rejected.
        self.assertFalse(self.fp._looks_like_text(
            "y | ® Fo 160 > 이 고 il Ki 10, K | 1< | = RO | = 7) Oo 더 38 "
            "= 해 a As <| ~ = ie Hot = ms @ = Mel 기 고 야 OH 20 = oF 여 시 주"))


class ExtractImageFlow(unittest.TestCase):
    def setUp(self):
        self.fp = _make_processor()

    def test_vision_transcription_used_directly(self):
        good = "제목: 2026 1분기 보고서\n매출 120억원, 영업이익 30억원."
        with mock.patch.object(self.fp, "_extract_with_vision_tiling", return_value=good), \
             mock.patch.object(self.fp, "_extract_with_tesseract") as tess, \
             mock.patch.object(self.fp, "_extract_with_easyocr") as easy:
            tc = self.fp.extract_image("x.jpg")
        self.assertIn("2026 1분기 보고서", tc.text)
        self.assertEqual(tc.source, "vision")
        tess.assert_not_called()   # no need to fall through to OCR
        easy.assert_not_called()

    def test_no_text_sentinel_falls_through_to_ocr(self):
        # EasyOCR (the neural #1 fallback) returns good text → Tesseract
        # is not even reached.
        sentinel = "<NO_TEXT>: 흐릿한 한국어 공지 문서 사진"
        ocr_good = "공지사항\n2026년 6월 25일 전 직원 교육 일정 안내드립니다."
        with mock.patch.object(self.fp, "_extract_with_vision_tiling", return_value=sentinel), \
             mock.patch.object(self.fp, "_extract_with_easyocr", return_value=ocr_good), \
             mock.patch.object(self.fp, "_extract_with_tesseract") as tess, \
             mock.patch("processors.file_processor.Image.open", return_value=object()):
            tc = self.fp.extract_image("x.jpg")
        self.assertIn("교육 일정", tc.text)
        self.assertEqual(tc.source, "ocr")
        tess.assert_not_called()   # EasyOCR succeeded first

    def test_garbage_ocr_discarded_no_fabricated_text(self):
        # vision says no-text; OCR returns confidence-passed-but-still-noise
        # block chars → _looks_like_text rejects → honest marker, NO garbage.
        sentinel = "<NO_TEXT>: 흐릿한 문서 사진"
        garbage = "▒█▒█ ░░░ █▒▓ ▒░█▓ ░▒█"
        with mock.patch.object(self.fp, "_extract_with_vision_tiling", return_value=sentinel), \
             mock.patch.object(self.fp, "_extract_with_tesseract", return_value=garbage), \
             mock.patch.object(self.fp, "_extract_with_easyocr", return_value=garbage), \
             mock.patch("processors.file_processor.Image.open", return_value=object()):
            tc = self.fp.extract_image("x.jpg")
        self.assertNotIn("▒", tc.text)            # no garbage ingested
        self.assertIn("흐릿한 문서 사진", tc.text)  # honest hint kept
        self.assertNotIn("이미지 텍스트", tc.text)  # not labelled as real text


if __name__ == "__main__":
    unittest.main()
