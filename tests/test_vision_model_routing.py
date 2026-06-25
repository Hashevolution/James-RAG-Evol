"""v0.6.1 — vision call must use the multimodal model, not the text model.

Regression guard for the bug where `GemmaClient.call_gemma_vision`
posted images to `GEMMA_MODEL` (a text-only model, e.g. gemma4:e4b),
which ignored the image and replied "no image attached" — so every
uploaded image yielded no real text → no entities/relations in the KG.
The fix routes the call to `config.MULTIMODAL_MODEL` (llava:13b default).

Covers:
  * `config.MULTIMODAL_MODEL` exists and defaults to a vision model.
  * `call_gemma_vision` posts with `model == MULTIMODAL_MODEL` (NOT
    `GEMMA_MODEL`) and carries the base64 image in `images`.

Run:
  python -m unittest tests.test_vision_model_routing
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class VisionModelRouting(unittest.TestCase):
    def test_multimodal_model_configured_and_vision_capable(self):
        import config
        self.assertTrue(hasattr(config, "MULTIMODAL_MODEL"),
                        "config.MULTIMODAL_MODEL missing")
        self.assertTrue(config.MULTIMODAL_MODEL.strip(),
                        "MULTIMODAL_MODEL is empty")
        # text-only models must NOT be the multimodal default
        self.assertNotEqual(config.MULTIMODAL_MODEL, config.GEMMA_MODEL,
                            "MULTIMODAL_MODEL must differ from the text GEMMA_MODEL")

    def test_call_gemma_vision_uses_multimodal_model(self):
        import config
        from core.gemma_client.client import GemmaClient

        # a real (tiny) file so the `open(image_path, 'rb')` read succeeds
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
            tf.write(b"\xff\xd8\xff\xe0fake-jpeg-bytes")
            img_path = tf.name

        captured = {}

        class _Resp:
            def raise_for_status(self): pass
            def json(self): return {"response": "보이는 것: 한국어 문서"}

        def _fake_post(url, json=None, timeout=None, **kw):
            captured["url"] = url
            captured["json"] = json
            return _Resp()

        try:
            with mock.patch("core.gemma_client.client.requests.post",
                            side_effect=_fake_post):
                GemmaClient().call_gemma_vision("이 이미지 설명", img_path)
        finally:
            os.unlink(img_path)

        self.assertIn("json", captured, "requests.post was not called")
        payload = captured["json"]
        self.assertEqual(payload.get("model"), config.MULTIMODAL_MODEL,
                         "vision call must use MULTIMODAL_MODEL")
        self.assertNotEqual(payload.get("model"), config.GEMMA_MODEL,
                            "vision call must NOT use the text GEMMA_MODEL (the bug)")
        self.assertTrue(payload.get("images"),
                        "vision call must carry the base64 image in 'images'")


if __name__ == "__main__":
    unittest.main()
