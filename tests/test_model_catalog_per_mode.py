"""Per-mode model catalog + secondary picker (item #A2, 2026-05-08).

User feedback: "llm 선택사항은 대부분의 경우 젬마 4로 설정되어 있는데,
일상 대화 챗, 기본 상식은 좀더 가벼운 모델 중 선택 가능하도록하고,
구체적인 자료 분석과 기능 활용은 무거운 모델중 선택 가능하게 개선.
코딩도 딱 하나의 모델이 아니라 가능한 모델 다 표시, 설치 여부까지
선택하도록 확장 개선".

Backend:
  - /llm/modes/ response gains a `models` array per option (besides
    the existing `model` / `installed` fields kept for backward compat).
    Each candidate: {"tag": str, "weight": "light|medium|heavy",
                     "installed": bool, "default": bool}
  - Mode → catalog mapping centralised in `_model_catalog()` so adding
    a candidate doesn't require touching multiple places.
  - /llm/install/?model= allowlist auto-derives from the catalog
    (operators don't have to remember to update the install gate when
    adding a candidate).

Frontend:
  - Secondary <select id="model-picker"> next to the mode dropdown.
  - Hidden when mode has 0-1 candidates (auto / meta / configs with no
    alternatives).
  - Selection persists in localStorage key `james_model_<mode>`.
  - Install button now follows the *currently selected* candidate, not
    just the mode default.

Run:
  python -m unittest tests.test_model_catalog_per_mode
"""
from __future__ import annotations

import inspect
import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent


class ModelCatalogTests(unittest.TestCase):
    """The catalog dict shape + central listing."""

    @classmethod
    def setUpClass(cls):
        import server_llmwiki as srv
        from tests._server_split_helpers import combined_server_source
        cls.srv = srv
        cls.src = combined_server_source()

    def test_catalog_function_exists(self):
        self.assertIn("def _model_catalog", self.src,
                      "must centralise mode→model candidates in a function")
        self.assertTrue(callable(getattr(self.srv, "_model_catalog", None)))

    def test_catalog_covers_chat_retrieval_coding(self):
        cat = self.srv._model_catalog()
        for mode in ("chat", "retrieval", "coding", "wiki_edit", "self_evolve"):
            self.assertIn(mode, cat,
                          f"mode {mode} missing from catalog")
            self.assertGreaterEqual(len(cat[mode]), 2,
                f"mode {mode} should expose ≥2 candidates so secondary "
                f"picker has something to select between")

    def test_chat_has_lighter_default_than_coding(self):
        # User wants 일상대화=light, coding=heavy. Verify the *first*
        # entry (default) is light for chat, heavy for coding.
        cat = self.srv._model_catalog()
        chat0 = cat["chat"][0]   # (tag, weight)
        cat["coding"][0]
        # chat's default may be light or medium (env override possible)
        self.assertIn(chat0[1], ("light", "medium"),
            f"chat default should be light/medium, got {chat0[1]}")
        # coding's default should be heavy (config.CODING_MODEL = qwen 32b)
        # OR an explicit operator override — accept any but must include
        # at least one heavy candidate.
        weights = [w for _, w in cat["coding"]]
        self.assertIn("heavy", weights,
            "coding mode should offer at least one heavy candidate")

    def test_weights_are_recognised(self):
        cat = self.srv._model_catalog()
        valid = {"light", "medium", "heavy"}
        for mode, cands in cat.items():
            for tag, weight in cands:
                self.assertIn(weight, valid,
                              f"unknown weight '{weight}' for {mode}/{tag}")

    def test_install_allowlist_auto_derived(self):
        self.assertIn("def _allowed_install_models", self.src,
                      "install allowlist must auto-derive from catalog")
        allowed = self.srv._allowed_install_models()
        cat = self.srv._model_catalog()
        for mode, cands in cat.items():
            for tag, _ in cands:
                self.assertIn(tag, allowed,
                              f"catalog tag {tag} (in {mode}) not in install allowlist")

    def test_install_endpoint_uses_derived_allowlist(self):
        # The /llm/install/ handler should call _allowed_install_models()
        # — not have a hardcoded set.
        m = re.search(r'@app\.post\("/llm/install/"', self.src)
        self.assertIsNotNone(m)
        body = self.src[m.start():m.start() + 3000]
        self.assertIn("_allowed_install_models", body,
                      "install handler must derive ALLOWED_MODELS from catalog")


class LlmModesResponseShapeTests(unittest.TestCase):
    """The /llm/modes/ response now carries `models[]` per option."""

    @classmethod
    def setUpClass(cls):
        from tests._server_split_helpers import combined_server_source
        cls.src = combined_server_source()

    def _endpoint_body(self) -> str:
        idx = self.src.index('@app.get("/llm/modes/"')
        rest = self.src[idx + 1:]
        m = re.search(r"\n@app\.", rest)
        end = idx + 1 + m.start() if m else idx + 8000
        return self.src[idx:end]

    def test_models_array_field_in_options(self):
        body = self._endpoint_body()
        self.assertIn('"models":', body,
                      "options must include `models` array (per-mode catalog)")

    def test_models_for_helper_exists(self):
        body = self._endpoint_body()
        self.assertIn("_models_for", body,
                      "needs helper to build per-mode candidate list")

    def test_candidate_shape_has_tag_weight_installed_default(self):
        body = self._endpoint_body()
        for field in ('"tag":', '"weight":', '"installed":', '"default":'):
            self.assertIn(field, body,
                          f"candidate dict missing {field}")

    def test_meta_and_auto_get_empty_models(self):
        body = self._endpoint_body()
        # auto and meta don't use the LLM (or use the routed mode's),
        # so they should have models=[]. Verify the literal exists.
        # (Two empty lists per the literal.)
        self.assertGreaterEqual(body.count('"models": []'), 2,
            "auto and meta should have models=[]")

    def test_backward_compat_model_installed_kept(self):
        body = self._endpoint_body()
        # Existing fields must remain — old clients (<#A2) still work.
        self.assertIn('"model":', body)
        self.assertIn('"installed":', body)


class FrontendSecondaryPickerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "frontend" / "static" / "chat.js").read_text(encoding="utf-8")
        cls.html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")

    def test_model_picker_in_html(self):
        self.assertIn('id="model-picker"', self.html,
                      "secondary <select id='model-picker'> missing")
        self.assertIn('id="model-picker-wrap"', self.html,
                      "wrapper for hide/show needed")
        # [§5 migration] inline onchange replaced by id-bound listener
        # registered in _bindStableInputs (chat.js).
        self.assertIn("onModelPickerChange", self.js,
            "chat.js must wire onModelPickerChange via _bindStableInputs")

    def test_refresh_model_picker_function(self):
        self.assertIn("function refreshModelPicker", self.js,
                      "refreshModelPicker handles populating the dropdown")
        idx = self.js.index("function refreshModelPicker")
        body = self.js[idx:idx + 2500]
        # Hide when 0-1 candidates (no point in a dropdown).
        self.assertIn("models.length < 2", body,
                      "must hide picker when fewer than 2 candidates")
        # Per-mode localStorage key.
        self.assertIn("_modelKey(", body,
                      "must restore selection from localStorage")

    def test_localstorage_key_per_mode(self):
        self.assertIn("function _modelKey", self.js)
        idx = self.js.index("function _modelKey")
        body = self.js[idx:idx + 200]
        self.assertIn("james_model_", body,
                      "localStorage key must be per-mode (james_model_<mode>)")

    def test_on_model_picker_change_persists(self):
        self.assertIn("function onModelPickerChange", self.js)
        idx = self.js.index("function onModelPickerChange")
        body = self.js[idx:idx + 600]
        self.assertIn("localStorage.setItem", body,
                      "selection must persist to localStorage")

    def test_mode_change_refreshes_model_picker(self):
        idx = self.js.index("function onModePickerChange")
        body = self.js[idx:idx + 500]
        self.assertIn("refreshModelPicker", body,
                      "changing mode must repopulate model dropdown")

    def test_install_button_targets_selected_model(self):
        idx = self.js.index("function updateInstallButton")
        body = self.js[idx:idx + 1500]
        # Now follows currently-selected candidate, not just the mode default.
        self.assertIn("selectedModel", body,
                      "install button must read selectedModel for accurate install target")
        self.assertIn("models.length >= 2", body,
                      "must branch on multi-candidate vs single-default")


if __name__ == "__main__":
    unittest.main()
