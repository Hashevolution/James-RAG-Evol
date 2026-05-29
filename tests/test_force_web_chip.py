"""Force-web chip on low-confidence answers (item #A8-6, 2026-05-09).

User feedback: "내부자료가 없을 경우, 대답 말미 대안 제시에 웹검색을
통해 좀더 자세히 조사해볼지 선택 여부 제시".

Backend:
  - QueryRequest gains force_web_search: bool = False
  - /query/ handler forwards data.force_web_search to rag_engine.query
  - core/reasoning/engine.py forwards via kwargs to pipeline
  - core/reasoning/pipeline.py: low_relevance gate now respects the
    flag (force_web_search=True bypasses threshold check)

Frontend:
  - lastUserQuestion module var captures latest user input on each
    sendMessage. The "🌐 웹으로 더 조사" chip carries this question
    in data-question (URI-encoded).
  - askWithForceWeb(btn) reads the question, sets _forceWebOnce flag,
    then calls sendMessage which picks up the flag once.
  - sendMessage POSTs force_web_search: forceWeb (clears the flag
    after read; defaults to false for normal queries).
  - Chip rendered when web_used == false AND unified_score < 0.50.

Run:
  python -m unittest tests.test_force_web_chip
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


class QueryRequestSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests._server_split_helpers import combined_server_source
        cls.src = combined_server_source()

    def test_force_web_search_field_present(self):
        m = re.search(
            r"class QueryRequest\(BaseModel\):(.+?)class\s+\w+\(",
            self.src, re.DOTALL,
        )
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("force_web_search", body,
            "QueryRequest must declare force_web_search field")
        self.assertIn("force_web_search: bool = False", body,
            "field must default to False (back-compat)")

    def test_query_handler_forwards_field(self):
        idx = self.src.index('@app.post("/query/"')
        end = self.src.index('@app.', idx + 10)
        body = self.src[idx:end]
        self.assertIn("force_web_search = data.force_web_search", body,
            "/query/ handler must forward force_web_search to rag_engine.query")


class EnginePropagationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import core.reasoning.engine as eng
        cls.src = inspect.getsource(eng)

    def test_engine_forwards_to_pipeline(self):
        # ReasoningEngine.query passes kwargs.get('force_web_search')
        # to run_retrieval_pipeline.
        self.assertIn('force_web_search=kwargs.get("force_web_search"', self.src,
            "engine.query must forward force_web_search via kwargs")


class PipelineGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests._pipeline_src import pipeline_source
        cls.src = pipeline_source()

    def test_signature_accepts_force_web_search(self):
        # The function declaration must include force_web_search param.
        self.assertIn("force_web_search: bool = False", self.src,
            "run_retrieval_pipeline must accept force_web_search kwarg")

    def test_low_relevance_gate_respects_force(self):
        # The OR-chain in low_relevance must include force_web_search.
        m = re.search(r"low_relevance\s*=\s*\(([^)]+)\)", self.src, re.DOTALL)
        self.assertIsNotNone(m, "couldn't locate low_relevance assignment")
        body = m.group(1)
        self.assertIn("force_web_search", body,
            "force_web_search must be one of the low_relevance triggers")


class FrontendChipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "frontend" / "static" / "chat.js").read_text(encoding="utf-8")

    def test_last_user_question_tracked(self):
        self.assertIn("let lastUserQuestion", self.js,
            "must declare lastUserQuestion module var")
        # sendMessage updates it.
        idx = self.js.index("async function sendMessage")
        body = self.js[idx:idx + 1500]
        self.assertIn("lastUserQuestion = text", body,
            "sendMessage must record the question for chip reuse")

    def test_force_web_once_flag(self):
        self.assertIn("_forceWebOnce", self.js,
            "must declare _forceWebOnce flag")
        # sendMessage reads + clears.
        idx = self.js.index("async function sendMessage")
        body = self.js[idx:idx + 2500]
        self.assertIn("const forceWeb = _forceWebOnce", body,
            "sendMessage must capture _forceWebOnce locally")
        self.assertIn("_forceWebOnce = false", body,
            "sendMessage must clear the flag after capturing")

    def test_request_body_includes_flag(self):
        idx = self.js.index("async function sendMessage")
        m = re.search(r"\nasync function|\nfunction\s+\w+\s*\(", self.js[idx + 1:])
        end = idx + 1 + m.start() if m else idx + 4000
        body = self.js[idx:end]
        self.assertIn("force_web_search:", body,
            "POST body must include force_web_search field")

    def test_ask_with_force_web_helper(self):
        self.assertIn("function askWithForceWeb", self.js,
            "askWithForceWeb helper must exist")
        idx = self.js.index("function askWithForceWeb")
        body = self.js[idx:idx + 1500]
        self.assertIn("dataset.question", body,
            "must read URI-encoded question from chip data attribute")
        self.assertIn("decodeURIComponent", body)
        self.assertIn("_forceWebOnce = true", body,
            "must set _forceWebOnce so the next sendMessage uses it")
        self.assertIn("sendMessage()", body)

    def test_chip_rendered_for_low_score_no_web(self):
        # appendJamesMsg must check web_used + score before showing.
        idx = self.js.index("function appendJamesMsg")
        m = re.search(r"\nfunction\s+\w+\s*\(", self.js[idx + 1:])
        end = idx + 1 + m.start() if m else idx + 12000
        body = self.js[idx:end]
        self.assertIn("force-web-btn", body,
            "chip class missing")
        self.assertIn("data.web_used", body,
            "must check web_used before rendering chip")
        # [§5 migration] inline onclick replaced by data-action;
        # delegate forwards the element to askWithForceWeb so dataset
        # is still readable.
        self.assertIn('data-action="ask-with-force-web"', body,
            "chip must carry data-action=ask-with-force-web")
        self.assertIn("data-question", body,
            "chip must carry the question via data attribute")
        self.assertIn("${forceWebChip}", body,
            "forceWebChip must be interpolated into bubble HTML")

    def test_chip_hidden_when_web_already_used(self):
        idx = self.js.index("let forceWebChip")
        body = self.js[idx:idx + 1500]
        # Default empty + the conditional excludes web_used=true.
        self.assertIn("!data.web_used", body,
            "must skip chip when web search already happened")

    # ─── Axis 6 (2026-05-12) — dual-variant chip ─────────────────
    # The chip used to only fire on low confidence (score < 0.50).
    # User feedback: high-confidence answers should also offer a
    # web option — "check for newer information" — instead of
    # silently hiding the chip when the answer is well-supported.
    # The two thresholds split the score line into three bands:
    #   < 0.50  → "자료 수집" framing
    #   ≥ 0.70  → "최신 정보 보완" framing
    #   between → no chip (deliberate quiet zone)
    # Same data-action / data-question shape — the delegate doesn't
    # care which variant fired.

    def test_two_distinct_thresholds_declared(self):
        idx = self.js.index("let forceWebChip")
        body = self.js[idx:idx + 4000]
        self.assertIn("0.70", body,
            "HIGH-confidence threshold (0.70) missing")
        self.assertIn("0.50", body,
            "LOW-confidence threshold (0.50) missing")

    def test_high_variant_uses_i18n_key(self):
        idx = self.js.index("let forceWebChip")
        body = self.js[idx:idx + 4000]
        self.assertIn("'chat.web_chip_high'", body,
            "high-confidence variant must source its label from "
            "the chat.web_chip_high i18n key, not a literal string")

    def test_low_variant_uses_i18n_key(self):
        idx = self.js.index("let forceWebChip")
        body = self.js[idx:idx + 4000]
        self.assertIn("'chat.web_chip_low'", body,
            "low-confidence variant must source its label from "
            "the chat.web_chip_low i18n key")

    def test_i18n_keys_present_both_locales(self):
        i18n = (Path(__file__).resolve().parent.parent
                / "frontend" / "static" / "i18n.js"
                ).read_text(encoding="utf-8")
        for key in ("chat.web_chip_low", "chat.web_chip_high"):
            with self.subTest(key=key):
                count = len(re.findall(
                    r"'" + re.escape(key) + r"'\s*:", i18n))
                self.assertGreaterEqual(count, 2,
                    f"i18n key {key!r} must be declared in both en + ko")

    def test_variants_use_distinct_classes(self):
        # web-collect-btn (low) vs web-refresh-btn (high) so future
        # CSS / analytics can tell the two apart without parsing copy.
        idx = self.js.index("let forceWebChip")
        body = self.js[idx:idx + 4000]
        self.assertIn("web-collect-btn", body,
            "low-confidence variant must carry the web-collect-btn class")
        self.assertIn("web-refresh-btn", body,
            "high-confidence variant must carry the web-refresh-btn class")


if __name__ == "__main__":
    unittest.main()
