"""Mode picker shows real model names + install button (item #6).

User feedback (2026-05-08): "챗 llm 모델변경 기능에 실제 모델명도
기입 / 모델이 없으면 설치 가능한 버튼도 추가".

Backend changes:
  - GET /llm/modes/ response now includes per-mode `model` (the
    actual Ollama tag from config — e.g. gemma4:e4b) and
    `installed` boolean (queried from Ollama API at request time,
    matched by exact tag OR family prefix).
  - POST /llm/install/?model= triggers `ollama pull <model>` in
    a fire-and-forget subprocess. Admin-gated. Allowlist check on
    `model` param so a chat user can't fill the operator's disk
    by spamming arbitrary model names.

Frontend changes:
  - Mode picker option labels now show "(model_tag)" + "⚠️ 미설치"
    suffix when not installed.
  - "📦 model 설치" button appears when selected mode's model is
    not installed. admin-only — non-admin sees a toast explaining.

Run:
  python -m unittest tests.test_model_names_install
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent


class LlmModesEndpointTests(unittest.TestCase):
    """The /llm/modes/ response shape gains model + installed fields,
    queries Ollama for installed list."""

    @classmethod
    def setUpClass(cls):
        from tests._server_split_helpers import combined_server_source
        cls.src = combined_server_source()

    def _endpoint_body(self) -> str:
        idx = self.src.index('@app.get("/llm/modes/"')
        rest = self.src[idx + 1:]
        m = re.search(r"\n@app\.", rest)
        end = idx + 1 + m.start() if m else idx + 6000
        return self.src[idx:end]

    def test_response_includes_model_field(self):
        body = self._endpoint_body()
        # Each option dict now has `model` and `installed` keys.
        self.assertIn('"model":', body,
                      "options must include `model` field")
        self.assertIn('"installed":', body,
                      "options must include `installed` boolean")

    def test_uses_config_models_not_hardcoded(self):
        body = self._endpoint_body()
        # Don't hardcode "gemma4:e4b" / "qwen2.5-coder:32b" — read from config.
        # If user changes JAMES_LLM_MODEL via env, picker must reflect it.
        self.assertIn("from config import GEMMA_MODEL, CODING_MODEL", body,
                      "must import config models so .env override propagates")
        self.assertIn("GEMMA_MODEL", body)
        self.assertIn("CODING_MODEL", body)

    def test_queries_ollama_for_installed_list(self):
        body = self._endpoint_body()
        # Ollama tags API (port 11434) → set of installed model names.
        self.assertIn("api/tags", body,
                      "must hit Ollama /api/tags to determine installed status")

    def test_installed_match_handles_family_prefix(self):
        body = self._endpoint_body()
        # gemma4:e4b should match if "gemma4" base is installed even
        # under a different tag. Look for the prefix logic.
        self.assertIn('split(":", 1)[0]', body,
                      "installed-match must handle family prefix "
                      "(gemma4:e4b ≈ gemma4)")


class LlmInstallEndpointTests(unittest.TestCase):
    """POST /llm/install/ triggers ollama pull, admin-only,
    allowlist-validated."""

    @classmethod
    def setUpClass(cls):
        from tests._server_split_helpers import combined_server_source
        cls.src = combined_server_source()

    def _endpoint_body(self) -> str:
        idx = self.src.index('@app.post("/llm/install/"')
        rest = self.src[idx + 1:]
        m = re.search(r"\n@app\.", rest)
        end = idx + 1 + m.start() if m else idx + 6000
        return self.src[idx:end]

    def test_endpoint_registered(self):
        self.assertIn('@app.post("/llm/install/"', self.src,
                      "/llm/install/ POST endpoint missing")

    def test_admin_only(self):
        body = self._endpoint_body()
        self.assertTrue("_require_admin(api_key, role)" in body or "_require_feature(api_key, role" in body,
                      "install must be admin-gated — multi-GB downloads "
                      "shouldn't be exposed to chat users")

    def test_model_allowlist(self):
        body = self._endpoint_body()
        self.assertIn("ALLOWED_MODELS", body,
                      "install must validate model name against allowlist — "
                      "arbitrary input could fill the operator's disk")
        self.assertIn("status_code=400", body,
                      "non-allowlisted model must return 400")

    def test_uses_subprocess_popen_fire_and_forget(self):
        body = self._endpoint_body()
        # Don't BLOCK the request thread — `ollama pull` can take
        # several minutes. Subprocess.Popen lets it run in background.
        self.assertIn("subprocess.Popen", body,
                      "must use Popen (not run/check_output) so request "
                      "doesn't block on multi-minute downloads")

    def test_handles_missing_ollama_cli(self):
        body = self._endpoint_body()
        # If ollama isn't in PATH, return 503 with a clear message
        # rather than 500 with stack trace.
        self.assertIn("FileNotFoundError", body)
        self.assertIn("status_code=503", body,
                      "missing ollama CLI must produce a clear 503")


class FrontendInstallButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "frontend" / "static" / "chat.js").read_text(encoding="utf-8")
        cls.html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")

    def test_install_button_in_html(self):
        self.assertIn('id="mode-install-btn"', self.html,
                      "install button missing from index.html")
        # [§5 migration] inline onclick → data-action.
        self.assertIn('data-action="trigger-model-install"', self.html)

    def test_picker_options_show_model_tag_and_status(self):
        # loadModePickerOptions builds option labels with model tag +
        # "⚠️ 미설치" suffix on uninstalled models.
        idx = self.js.index("async function loadModePickerOptions")
        body = self.js[idx:idx + 2000]
        self.assertIn("m.model", body,
                      "option label must include the actual model tag")
        self.assertIn("미설치", body,
                      "uninstalled options must show 미설치 marker")
        self.assertIn("data-installed", body,
                      "option should carry data-installed for client-side check")

    def test_update_install_button_function(self):
        self.assertIn("function updateInstallButton", self.js)
        idx = self.js.index("function updateInstallButton")
        body = self.js[idx:idx + 1500]
        self.assertIn("style.display = 'none'", body,
                      "button hidden when selected mode is installed")
        self.assertIn("style.display = 'inline-block'", body,
                      "button shown when not installed")
        self.assertIn("opt.installed", body,
                      "must check the installed flag")

    def test_trigger_model_install_admin_check(self):
        idx = self.js.index("async function triggerModelInstall")
        body = self.js[idx:idx + 2500]
        # Client-side guard — show message before hitting server. Server
        # also enforces but the toast is faster feedback.
        self.assertIn("userRole !== 'admin'", body,
                      "client must show admin-required message before request")
        # Confirm prompt — multi-GB download is destructive.
        self.assertIn("confirm(", body,
                      "must confirm before triggering — large download")
        # Hits the install endpoint.
        self.assertIn("/llm/install/", body)


if __name__ == "__main__":
    unittest.main()
