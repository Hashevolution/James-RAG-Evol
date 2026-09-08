"""EasyOCR must not lose a Korean-named upload.

`reader.readtext(path)` makes EasyOCR decode the file with `cv2.imread`,
which cannot open a non-ASCII filename on Windows — it returns None, and
EasyOCR trips on the empty array ("!ssize.empty()" on older builds,
"'NoneType' object has no attribute 'shape'" on 1.7.2). The OCR pass was
silently lost for every Korean-named file.

Reproduced 2026-09-08: the same 12 MP photo reads fine as
`photo_12mp.jpg` and fails as `사진_12메가.jpg`, so the trigger is the
filename, not the megapixels the 2026-06-26 note attributed it to.

These tests use a stub reader, so they run without the EasyOCR models
(~100 MB) and without a GPU. What they pin is the contract that fixes it:
the extractor decodes the image itself and hands EasyOCR an array.

Run:
    python -m unittest tests.test_easyocr_unicode_path
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _StubReader:
    """Records what it was handed instead of running a model."""

    def __init__(self):
        self.received = None

    def readtext(self, image, detail=1, paragraph=False):
        self.received = image
        return [([[0, 0], [1, 0], [1, 1], [0, 1]], "OPERATING STANDARD", 0.99)]


def _write_image(directory: Path, name: str, size=(400, 300)) -> Path:
    from PIL import Image

    p = directory / name
    Image.new("RGB", size, (245, 245, 240)).save(p, quality=90)
    return p


class EasyOcrUnicodePathTests(unittest.TestCase):
    def setUp(self):
        from processors.file_processor import FileProcessor

        # __init__ builds a RouterWrapper and a MetadataGenerator; neither
        # is used by the extractor under test.
        self.fp = FileProcessor.__new__(FileProcessor)
        self.reader = _StubReader()
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _extract(self, path):
        with patch.object(type(self.fp), "get_easyocr_reader",
                          lambda _self: self.reader):
            return self.fp._extract_with_easyocr(str(path))

    def test_korean_filename_still_reaches_the_reader(self):
        import numpy as np

        p = _write_image(self.tmp, "사진_12메가.jpg")
        text = self._extract(p)
        self.assertIsInstance(
            self.reader.received, np.ndarray,
            "EasyOCR must be handed a decoded array, not a path — a path "
            "sends it through cv2.imread, which returns None for a "
            "non-ASCII filename on Windows")
        self.assertIn("OPERATING STANDARD", text)

    def test_ascii_and_korean_filenames_agree(self):
        a = _write_image(self.tmp, "photo.jpg")
        k = _write_image(self.tmp, "사진.jpg")
        self.assertEqual(self._extract(a), self._extract(k),
                         "the filename must not change the OCR result")

    def test_oversized_image_is_bounded(self):
        from processors.file_processor import FileProcessor

        cap = FileProcessor._EASYOCR_MAX_EDGE
        p = _write_image(self.tmp, "big.jpg", size=(cap * 2, cap))
        self._extract(p)
        h, w = self.reader.received.shape[:2]
        self.assertEqual(max(w, h), cap,
                         f"long edge must be capped at {cap}px before the "
                         f"detector sees it")
        self.assertAlmostEqual(w / h, 2.0, places=1,
                               msg="aspect ratio must be preserved")

    def test_small_image_is_not_upscaled(self):
        p = _write_image(self.tmp, "small.jpg", size=(400, 300))
        self._extract(p)
        h, w = self.reader.received.shape[:2]
        self.assertEqual((w, h), (400, 300),
                         "an image already under the cap must pass through "
                         "untouched — upscaling only multiplies photo noise")

    def test_unreadable_file_returns_empty_not_raises(self):
        p = self.tmp / "not-an-image.jpg"
        p.write_bytes(b"this is not a JPEG")
        self.assertEqual(self._extract(p), "",
                         "a corrupt upload must degrade to no-OCR, not "
                         "propagate an exception into the ingest path")
        self.assertIsNone(self.reader.received,
                          "the reader must not be called at all when the "
                          "image cannot be decoded")


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
