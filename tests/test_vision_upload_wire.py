"""vision-wire end-to-end plumbing — /vision/upload/ route + chat UI.

Completes the "실사용 가능" arm: a chat user attaches an image, the
client uploads it to /vision/upload/ (lightweight save → server path),
then the next /query/ carries image_path → engine routes to vision.

This guards the WIRE at source level (the project's pattern for route +
frontend plumbing, cf. tests/test_chat_mode_picker.py) so the chain
can't silently break:

  backend:  POST /vision/upload/ exists, role-gated (ROLE_ALLOWED vision,
            external blocked), ext-validated, returns image_path under
            UPLOAD_DIR.
  frontend: index.html has the attach button + hidden file input +
            preview; chat.js uploads on select, forwards image_path in
            /query/, and treats the attachment as single-use.

Functional containment of the returned path is covered by
tests/test_vision_wire.py::SafeImagePathTests.

Run:
  python -m unittest tests.test_vision_upload_wire
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402,F401 — load .env before routes.* → core.auth import

ROOT = Path(__file__).resolve().parent.parent


class BackendUploadRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests._server_split_helpers import combined_server_source
        cls.src = combined_server_source()

    def test_route_registered(self):
        self.assertIn('"/vision/upload/"', self.src,
                      "POST /vision/upload/ must be registered")

    def test_role_gated_against_role_allowed(self):
        # Must consult ROLE_ALLOWED so external (chat-only) is blocked.
        idx = self.src.index('"/vision/upload/"')
        body = self.src[idx:idx + 1600]
        self.assertIn("ROLE_ALLOWED", body)
        self.assertRegex(body, r'"vision"\s+not\s+in\s+ROLE_ALLOWED',
                         "upload must 403 when role lacks vision")
        self.assertIn("403", body)

    def test_extension_allowlist(self):
        idx = self.src.index('"/vision/upload/"')
        body = self.src[idx:idx + 1600]
        for ext in (".jpg", ".png", ".webp"):
            self.assertIn(ext, body, f"{ext} must be in the allowlist")

    def test_returns_image_path(self):
        idx = self.src.index('"/vision/upload/"')
        body = self.src[idx:idx + 1600]
        self.assertIn("image_path", body,
                      "upload response must carry image_path for /query/")
        self.assertIn("UPLOAD_DIR", body)

    def test_size_cap_enforced(self):
        idx = self.src.index('"/vision/upload/"')
        body = self.src[idx:idx + 1600]
        self.assertIn("413", body, "oversize upload must be rejected (413)")


class BackendUploadFunctionalTests(unittest.TestCase):
    """Exercise vision_upload() directly (no full app boot): it must
    save under UPLOAD_DIR, return a containment-valid path, gate role,
    and reject bad extensions."""

    def _upload_file(self, name: str, data: bytes):
        import io
        from starlette.datastructures import UploadFile, Headers
        # Construct across Starlette versions: filename + file are stable.
        try:
            return UploadFile(filename=name, file=io.BytesIO(data),
                              headers=Headers({}))
        except TypeError:
            return UploadFile(filename=name, file=io.BytesIO(data))

    def setUp(self):
        from unittest import mock
        import routes.multimodal as mm
        # verify_api_key hits the key store; stub it for the unit.
        self._patch = mock.patch.object(mm, "verify_api_key", lambda k: None)
        self._patch.start()
        self.mm = mm

    def tearDown(self):
        self._patch.stop()

    def test_happy_path_saves_and_returns_contained_path(self):
        import asyncio
        from routes.query import _safe_image_path
        uf = self._upload_file("photo.png", b"\x89PNG\r\n\x1a\n" + b"x" * 32)
        res = asyncio.run(self.mm.vision_upload(
            file=uf, api_key="k", role="admin"))
        path = res["image_path"]
        try:
            self.assertTrue(os.path.isfile(path))
            # The very guard /query/ uses must accept this path.
            self.assertEqual(os.path.realpath(_safe_image_path(path)),
                             os.path.realpath(path))
        finally:
            if os.path.isfile(path):
                os.remove(path)

    def test_external_role_forbidden(self):
        import asyncio
        from fastapi import HTTPException
        uf = self._upload_file("photo.png", b"\x89PNG\r\n")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(self.mm.vision_upload(
                file=uf, api_key="k", role="external"))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_bad_extension_rejected(self):
        import asyncio
        from fastapi import HTTPException
        uf = self._upload_file("evil.txt", b"not an image")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(self.mm.vision_upload(
                file=uf, api_key="k", role="admin"))
        self.assertEqual(ctx.exception.status_code, 400)


class FrontendIndexHtmlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")

    def test_attach_button_present(self):
        self.assertIn('data-action="attach-image"', self.html)

    def test_file_input_present(self):
        self.assertIn('id="vision-file-input"', self.html)
        self.assertIn('accept="image/*"', self.html)

    def test_preview_and_clear_present(self):
        self.assertIn('id="vision-preview"', self.html)
        self.assertIn('data-action="clear-vision-image"', self.html)

    def test_no_emoji_icon(self):
        # Operator catch (2026-06-16): chat page uses SVG/text, no emoji.
        # The attach button must use an inline <svg>, not an emoji glyph.
        idx = self.html.index('data-action="attach-image"')
        btn = self.html[idx:idx + 600]
        self.assertIn("<svg", btn, "attach button must use an SVG icon")


class FrontendChatJsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "frontend" / "static" / "chat.js").read_text(encoding="utf-8")

    def test_upload_handler_posts_to_vision_upload(self):
        self.assertIn("handleVisionFileChange", self.js)
        self.assertIn("/vision/upload/", self.js)
        self.assertIn("FormData", self.js)

    def test_query_body_forwards_image_path(self):
        idx = self.js.index("`${API}/query/`")
        body = self.js[idx:idx + 1500]
        self.assertRegex(body, r"image_path:\s*visImg",
                         "/query/ body must forward the attached image_path")

    def test_attachment_is_single_use(self):
        # Captured + cleared each send (force_web-style), so a stale image
        # can't ride along on the next text-only turn.
        self.assertIn("_pendingVisionImage = null", self.js)
        self.assertIn("clearVisionImage", self.js)

    def test_empty_text_allowed_with_image(self):
        self.assertRegex(
            self.js, r"if\s*\(!text\s*&&\s*!_pendingVisionImage\)\s*return;",
            "an image-only turn (no text) must still send")

    def test_multipart_omits_json_content_type(self):
        # The upload fetch must NOT set Content-Type: application/json
        # (browser sets the multipart boundary). Guard: the upload block
        # builds a bare headers obj, not getAuthHeaders().
        idx = self.js.index("handleVisionFileChange")
        block = self.js[idx:idx + 1200]
        self.assertNotIn("getAuthHeaders()", block,
                         "multipart upload must not reuse the JSON headers")


if __name__ == "__main__":
    unittest.main()
