"""vision-wire — engine dispatch + /query image plumbing for vision mode.

Builds on the plumb-first vision handler (tests/test_vision_mode.py):
this guards the WIRE that makes an attached image route through the
unified mode dispatch to handle_vision.

Coverage:
  - engine: image_path in kwargs forces mode="vision" (analogous to the
    force_web_search→retrieval override); the override runs AFTER mode
    resolution and BEFORE dispatch; "vision" dispatch branch + import +
    VALID_OVERRIDES entry are present.
  - intent_classifier: "vision" is an ACTIVE_MODE; admin/manager/employee
    are vision-allowed, external is NOT (chat-only policy).
  - route: _safe_image_path enforces UPLOAD_DIR containment (path-
    traversal guard) and existence; QueryRequest carries image_path.

Run:
  python -m unittest tests.test_vision_wire
"""
from __future__ import annotations

import inspect
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env (populates JAMES_JWT_SECRET) BEFORE any test imports
# routes.query → core.auth, which raises at import time if the secret
# is unset. Without this, SafeImagePathTests is order-dependent in a
# multi-module unittest run.
import config  # noqa: E402,F401


class EngineWireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The routing block (incl. the image_path → vision override)
        # moved to engine_routing.py in the 2026-07-01 rule #5 split.
        # Concatenate routing BEFORE engine so the ordering assertions
        # (override after router, before the dispatch that stays in
        # engine._query_impl) keep their meaning.
        import core.reasoning.engine as eng
        import core.reasoning.engine_routing as eng_routing
        cls.src = inspect.getsource(eng_routing) + "\n" + inspect.getsource(eng)

    def test_image_override_block_present(self):
        m = re.search(
            r'if\s+kwargs\.get\(\s*[\'"]image_path[\'"]\s*\).*?mode\s*=\s*[\'"]vision[\'"]',
            self.src, re.DOTALL,
        )
        self.assertIsNotNone(
            m, "engine must force mode='vision' when image_path is attached")

    def test_override_after_router_before_dispatch(self):
        router_idx = self.src.index("QueryRouter().route(")
        img_idx = self.src.index('kwargs.get("image_path")')
        dispatch_idx = self.src.index('if mode == "vision":')
        self.assertLess(router_idx, img_idx,
                        "image override must run AFTER QueryRouter")
        self.assertLess(img_idx, dispatch_idx,
                        "image override must run BEFORE mode dispatch")

    def test_vision_dispatch_branch_present(self):
        self.assertIn('if mode == "vision":', self.src)
        self.assertIn("return handle_vision(", self.src)

    def test_handle_vision_imported(self):
        self.assertIn("handle_vision", self.src)

    def test_vision_in_valid_overrides(self):
        # The VALID_OVERRIDES set literal must include "vision" so an
        # explicit client mode_override="vision" is recognised.
        m = re.search(r"VALID_OVERRIDES\s*=\s*\{(.+?)\}", self.src, re.DOTALL)
        self.assertIsNotNone(m)
        self.assertIn('"vision"', m.group(1))

    def test_role_gate_on_image_override(self):
        # The override must consult ROLE_ALLOWED so external can't reach
        # vision via an attached image.
        idx = self.src.index('kwargs.get("image_path")')
        window = self.src[idx:idx + 250]
        self.assertIn("ROLE_ALLOWED", window)


class IntentTaxonomyTests(unittest.TestCase):
    def test_vision_is_active_mode(self):
        from core.intent_classifier import ACTIVE_MODES
        self.assertIn("vision", ACTIVE_MODES)

    def test_role_allowed_matrix(self):
        from core.intent_classifier import ROLE_ALLOWED
        self.assertIn("vision", ROLE_ALLOWED["admin"])
        self.assertIn("vision", ROLE_ALLOWED["manager"])
        self.assertIn("vision", ROLE_ALLOWED["employee"])
        self.assertNotIn("vision", ROLE_ALLOWED["external"],
                         "external is chat-only — must NOT reach vision")


class SafeImagePathTests(unittest.TestCase):
    def setUp(self):
        from config import UPLOAD_DIR
        self.upload_dir = UPLOAD_DIR
        os.makedirs(UPLOAD_DIR, exist_ok=True)

    def test_empty_returns_empty(self):
        from routes.query import _safe_image_path
        self.assertEqual(_safe_image_path(""), "")
        self.assertEqual(_safe_image_path("   "), "")

    def test_outside_upload_dir_rejected(self):
        from routes.query import _safe_image_path
        # __file__ exists but lives in tests/, not UPLOAD_DIR
        self.assertEqual(_safe_image_path(__file__), "")

    def test_traversal_attempt_rejected(self):
        from routes.query import _safe_image_path
        evil = os.path.join(self.upload_dir, "..", "..", "config.py")
        self.assertEqual(_safe_image_path(evil), "")

    def test_nonexistent_inside_upload_dir_rejected(self):
        from routes.query import _safe_image_path
        ghost = os.path.join(self.upload_dir, "does_not_exist_zzz.png")
        self.assertEqual(_safe_image_path(ghost), "")

    def test_valid_file_inside_upload_dir_accepted(self):
        from routes.query import _safe_image_path
        p = os.path.join(self.upload_dir, "_vision_wire_test.png")
        with open(p, "wb") as f:
            f.write(b"\x89PNG\r\n")
        try:
            got = _safe_image_path(p)
            self.assertEqual(os.path.realpath(got), os.path.realpath(p))
        finally:
            os.remove(p)

    def test_query_request_has_image_path_field(self):
        from routes.query import QueryRequest
        f = QueryRequest.model_fields
        self.assertIn("image_path", f)
        self.assertEqual(f["image_path"].default, "")


if __name__ == "__main__":
    unittest.main()
