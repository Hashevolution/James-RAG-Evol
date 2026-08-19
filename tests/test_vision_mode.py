"""vision mode — handle_vision dispatch shell + resolution robustness.

Coverage:
  - handle_vision returns the standard reasoning-engine row dict
    (mode='vision', graph_paths=[], short-circuits before retrieval).
  - No image attached → friendly guidance, not an error/crash.
  - Model resolution priority: explicit pick > kill-switch legacy >
    resolve_for_mode("vision"); empty resolved tag → install hint.
  - Successful analysis surfaces the description + meta bits and tags the
    output trust='low' (#44).
  - analyze_image error is normalised into a user-facing message.
  - Source-level: handler exported from core.reasoning.modes; the reused
    image pipeline (analyze_image / LlavaClient) accepts the threaded
    ``model`` tag with a byte-identical default.

Run:
  python -m unittest tests.test_vision_mode
"""
from __future__ import annotations

import inspect
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _FakeEngine:
    """Minimal stand-in exposing the helpers handle_vision uses."""

    def __init__(self):
        self.logged = []
        self.elapsed = []

    def _log(self, where, exc, role):
        self.logged.append((where, str(exc), role))

    def _elapsed(self, t0, label):
        self.elapsed.append(label)


def _call(query="이 사진 설명해줘", image_path="/tmp/x.png", role="admin",
          selected_model=""):
    from core.reasoning.modes.vision import handle_vision
    import time
    eng = _FakeEngine()
    row = handle_vision(eng, query, image_path, role, time.time(),
                        selected_model=selected_model)
    return eng, row


class RowShapeTests(unittest.TestCase):
    def test_no_image_returns_friendly_guidance(self):
        _, row = _call(image_path="")
        self.assertEqual(row["mode"], "vision")
        self.assertFalse(row["blocked"])
        self.assertEqual(row["sources"], [])
        self.assertIn("이미지", row["answer"])

    def test_row_has_standard_keys(self):
        with mock.patch(
            "tools.multimodal.image_analyzer.analyze_image",
            return_value={"description": "고양이 사진", "tags": ["cat"]},
        ), mock.patch.dict(os.environ,
                            {"JAMES_DISABLE_MODE_AWARE_ROUTING": "1"}):
            _, row = _call()
        for k in ("answer", "mode", "graph_paths", "graph_used", "sources",
                  "blocked", "role_used", "timing_sec", "unified_score",
                  "loop_count"):
            self.assertIn(k, row)
        self.assertEqual(row["mode"], "vision")
        self.assertEqual(row["graph_paths"], [])
        self.assertEqual(row["sources"], ["/tmp/x.png"])


class ResolutionTests(unittest.TestCase):
    def test_explicit_pick_wins(self):
        from core.reasoning.modes.vision import _resolve_vision_model
        tag, source, _ = _resolve_vision_model("llava:34b")
        self.assertEqual(tag, "llava:34b")
        self.assertEqual(source, "requested")

    def test_killswitch_uses_legacy_default(self):
        from core.reasoning.modes.vision import _resolve_vision_model
        with mock.patch.dict(os.environ,
                             {"JAMES_DISABLE_MODE_AWARE_ROUTING": "1"}):
            tag, source, _ = _resolve_vision_model("")
        self.assertEqual(tag, "llava:13b")
        self.assertEqual(source, "legacy_killswitch")

    def test_resolver_consulted_when_no_killswitch(self):
        from core.reasoning.modes import vision as vmod
        fake = mock.Mock()
        fake.tag, fake.source, fake.warning = "llava:13b", "preference", ""
        env = {k: v for k, v in os.environ.items()
               if k != "JAMES_DISABLE_MODE_AWARE_ROUTING"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("core.model_resolver.resolve_for_mode",
                           return_value=fake) as rfm:
            tag, source, _ = vmod._resolve_vision_model("")
        rfm.assert_called_once_with("vision", requested="")
        self.assertEqual((tag, source), ("llava:13b", "preference"))

    def test_no_vision_model_installed_returns_install_hint(self):
        fake = mock.Mock()
        fake.tag, fake.source, fake.warning = "", "none", "nothing installed"
        env = {k: v for k, v in os.environ.items()
               if k != "JAMES_DISABLE_MODE_AWARE_ROUTING"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("core.model_resolver.resolve_for_mode",
                           return_value=fake):
            _, row = _call()
        self.assertIn("ollama pull llava", row["answer"])


class AnalysisTests(unittest.TestCase):
    def test_success_surfaces_description_and_trust_low(self):
        payload = {
            "description": "해변에서 노을을 보는 사람",
            "location": "부산", "date": "2024-01-15",
            "persons": ["미상"], "tags": ["beach", "sunset"],
        }
        with mock.patch("tools.multimodal.image_analyzer.analyze_image",
                        return_value=payload), \
                mock.patch.dict(os.environ,
                                {"JAMES_DISABLE_MODE_AWARE_ROUTING": "1"}):
            _, row = _call()
        self.assertIn("해변", row["answer"])
        self.assertIn("부산", row["answer"])
        self.assertEqual(row["vision_meta"]["trust"], "low")
        self.assertEqual(row["vision_meta"]["source"], "vision")
        self.assertEqual(row["vision_meta"]["model"], "llava:13b")

    def test_analyze_error_normalised(self):
        with mock.patch("tools.multimodal.image_analyzer.analyze_image",
                        return_value={"error": "파일 없음"}), \
                mock.patch.dict(os.environ,
                                {"JAMES_DISABLE_MODE_AWARE_ROUTING": "1"}):
            _, row = _call()
        self.assertIn("실패", row["answer"])
        self.assertEqual(row["mode"], "vision")

    def test_model_tag_threaded_to_analyze_image(self):
        with mock.patch("tools.multimodal.image_analyzer.analyze_image",
                        return_value={"description": "x"}) as ai, \
                mock.patch.dict(os.environ,
                                {"JAMES_DISABLE_MODE_AWARE_ROUTING": "1"}):
            _call(selected_model="llava:34b")
        # explicit pick flows through to the analyzer
        _, kwargs = ai.call_args
        self.assertEqual(kwargs.get("model"), "llava:34b")


class SourceLevelTests(unittest.TestCase):
    def test_handler_exported_from_modes_package(self):
        import core.reasoning.modes as md
        self.assertTrue(hasattr(md, "handle_vision"))
        self.assertIn("handle_vision", md.__all__)

    def test_analyze_image_accepts_model_param(self):
        from tools.multimodal.image_analyzer import analyze_image
        sig = inspect.signature(analyze_image)
        self.assertIn("model", sig.parameters)
        self.assertEqual(sig.parameters["model"].default, "")

    def test_llava_client_accepts_model_param(self):
        from llm.providers.llava_client import LlavaClient
        sig = inspect.signature(LlavaClient.__init__)
        self.assertIn("model", sig.parameters)
        self.assertEqual(sig.parameters["model"].default, "")


if __name__ == "__main__":
    unittest.main()
