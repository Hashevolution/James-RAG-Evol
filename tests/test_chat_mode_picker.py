"""Chat-page model/mode picker + auto-recommendation (item #6).

User feedback (2026-05-08): "모델변경 및 설치를 챗 웹페이지의 대화창에
붙여주고, 어떤 질문에 어떤 모델이 적용하는것이 좋은지 추천".

Architecture:
  Backend
    - QueryRequest gains `mode_override: str = ""`.
    - /query/ forwards it to rag_engine.query as mode_override.
    - engine.query: when override is non-empty + valid +
      role-allowed, bypasses QueryRouter and dispatches directly.
      Otherwise (empty or unauthorised), falls back to the normal
      intent_classifier path.
    - New non-admin endpoint GET /llm/modes/?api_key=... returns
      role-filtered options for the picker dropdown.

  Frontend
    - Dropdown (#mode-picker) above the input area, populated
      from /llm/modes/ on page load.
    - Recommendation badge (#mode-recommend) shown when:
        selectedMode === 'auto'
        AND user input matches another mode's keywords
      Click → selectedMode flips to the recommended one.
    - sendMessage sends `mode_override` field to /query/.

Run:
  python -m unittest tests.test_chat_mode_picker
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


class BackendModeOverrideTests(unittest.TestCase):
    """QueryRequest accepts mode_override; /query/ forwards it;
    engine.query bypasses router when override is valid + allowed."""

    @classmethod
    def setUpClass(cls):
        import server_llmwiki as srv
        cls.srv_src = inspect.getsource(srv)
        import core.reasoning.engine as eng
        cls.eng_src = inspect.getsource(eng)

    def test_query_request_field(self):
        m = re.search(
            r"class QueryRequest\(BaseModel\):(.+?)(?=\nclass |\n@app\.|\nasync def )",
            self.srv_src, re.DOTALL,
        )
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("mode_override", body)
        self.assertTrue(re.search(r'mode_override\s*:\s*str\s*=\s*""', body),
                        "mode_override default must be empty string for back-compat")

    def test_query_endpoint_forwards_field(self):
        idx = self.srv_src.index('@app.post("/query/"')
        body = self.srv_src[idx:idx + 2500]
        self.assertIn("mode_override", body,
                      "/query/ must forward data.mode_override into rag_engine.query")
        self.assertIn("data.mode_override", body)

    def test_engine_query_signature_has_param(self):
        self.assertRegex(
            self.eng_src,
            r"mode_override\s*:\s*str\s*=\s*[\"']{2}",
            "engine.query must declare mode_override: str = '' kwarg",
        )

    def test_engine_query_validates_override(self):
        # Engine must check the override is a known mode AND role-allowed.
        # PR-10b split the request lifecycle: ``query()`` is now a thin
        # try/finally wrapper that delegates to ``_query_impl`` where
        # the override validation actually lives. Scan whichever
        # method's body holds the override logic.
        for fn_name in ("_query_impl", "query"):
            try:
                idx = self.eng_src.index(f"def {fn_name}(")
            except ValueError:
                continue
            m = re.search(r"\n    def\s+\w+\(", self.eng_src[idx + 1:])
            end = idx + 1 + m.start() if m else idx + 12000
            body = self.eng_src[idx:end]
            if "VALID_OVERRIDES" in body:
                break
        else:
            self.fail("no engine method body contains VALID_OVERRIDES — "
                      "override whitelist must live in query() or "
                      "_query_impl")
        self.assertIn("VALID_OVERRIDES", body,
                      "engine must whitelist valid override modes")
        self.assertIn("ROLE_ALLOWED", body,
                      "engine must enforce role gate on the override "
                      "(client cannot escalate via mode picker)")
        # Fallback to router when override is empty / invalid.
        self.assertIn("QueryRouter", body)


class LlmModesEndpointTests(unittest.TestCase):
    """Non-admin GET /llm/modes/ returns role-filtered picker options."""

    @classmethod
    def setUpClass(cls):
        import server_llmwiki as srv
        cls.src = inspect.getsource(srv)

    def _endpoint_body(self) -> str:
        # Bound to ONLY this endpoint's body — next @app. is end.
        idx = self.src.index('@app.get("/llm/modes/"')
        rest = self.src[idx + 1:]
        m = re.search(r"\n@app\.", rest)
        end = idx + 1 + m.start() if m else idx + 4000
        return self.src[idx:end]

    def test_endpoint_registered(self):
        self.assertIn('@app.get("/llm/modes/"', self.src,
                      "/llm/modes/ endpoint missing")

    def test_endpoint_uses_api_key_not_admin(self):
        body = self._endpoint_body()
        self.assertIn("verify_api_key(api_key)", body,
                      "/llm/modes/ must validate api_key")
        self.assertNotIn("_require_admin(", body,
                         "/llm/modes/ must NOT require admin — chat users need it")

    def test_endpoint_returns_role_filtered_options(self):
        body = self._endpoint_body()
        self.assertIn("ROLE_ALLOWED", body,
                      "endpoint must filter options by role")
        self.assertIn('"auto"', body,
                      "auto option must always be present")
        self.assertIn("keywords", body,
                      "each option must include keywords for client-side recommendation")


class FrontendChatJsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "frontend" / "static" / "chat.js").read_text(encoding="utf-8")

    def test_load_mode_picker_options_function(self):
        self.assertIn("async function loadModePickerOptions", self.js)
        self.assertIn("/llm/modes/", self.js,
                      "loadModePickerOptions must fetch /llm/modes/")

    def test_send_message_includes_mode_override(self):
        idx = self.js.index("async function sendMessage()")
        body = self.js[idx:idx + 3000]
        self.assertIn("mode_override:", body,
                      "sendMessage body must include mode_override field")

    def test_check_recommendation_function(self):
        self.assertIn("function checkModeRecommendation", self.js)
        self.assertIn("recommendedMode", self.js,
                      "module-scope recommendedMode variable missing")

    def test_recommendation_only_when_auto_selected(self):
        # Spec: don't pop recommendation if user explicitly picked a mode.
        idx = self.js.index("function checkModeRecommendation")
        body = self.js[idx:idx + 2000]
        self.assertIn("selectedMode !== 'auto'", body,
                      "recommendation should be suppressed when user has "
                      "explicitly picked a non-auto mode")

    def test_accept_recommend_function(self):
        self.assertIn("function acceptModeRecommend", self.js)


class FrontendChatHtmlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")

    def test_mode_picker_select_present(self):
        self.assertIn('id="mode-picker"', self.html,
                      "<select id='mode-picker'> missing in chat HTML")
        # [§5 migration] inline onchange replaced by id-bound listener
        # registered in _bindStableInputs (chat.js).
        chat = (ROOT / "frontend" / "static" / "chat.js").read_text(
            encoding="utf-8")
        self.assertIn("onModePickerChange", chat,
            "chat.js must wire onModePickerChange via _bindStableInputs")

    def test_recommend_badge_present(self):
        self.assertIn('id="mode-recommend"', self.html,
                      "recommendation badge element missing")
        # [§5 migration] inline onclick replaced by data-action.
        self.assertIn('data-action="accept-mode-recommend"', self.html)


if __name__ == "__main__":
    unittest.main()
