"""Answer "🌐 웹 검색 사용됨" badge + source URLs (item #A6-2, 2026-05-08).

User feedback (c part 1): "답변에 '웹 검색 사용됨' 명시하고, (현재는
source URL만)". The answer bubble used to silently mix internal +
web evidence. The user wants explicit visibility — a distinct badge
+ clickable source URLs so the reader can self-assess trust.

Backend:
  - core/reasoning/pipeline.py — web_results lifted to outer scope so
    web_used + web_sources can be returned in the result dict even
    when low_relevance branch returns early (or is skipped).
  - server_llmwiki.py:
    - QueryResponse model gains web_used: bool / web_sources: list
    - /query/ handler propagates result.web_used + result.web_sources

Frontend (chat.js):
  - appendJamesMsg renders <details> badge with engine name + count
    and a list of clickable URLs (target=_blank, rel=noopener).
  - Hidden when web_used is false (internal-only answers stay clean).

Run:
  python -m unittest tests.test_web_used_badge
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


class PipelineReturnShapeTests(unittest.TestCase):
    """run_retrieval_pipeline must include web_used + web_sources."""

    @classmethod
    def setUpClass(cls):
        from tests._pipeline_src import pipeline_source
        cls.src = pipeline_source()

    def test_web_used_in_return(self):
        # Locate the final return dict (last `return {` in the module).
        # Just check the keys are present.
        self.assertIn('"web_used"', self.src,
            "pipeline result must expose web_used boolean")
        self.assertIn('"web_sources"', self.src,
            "pipeline result must expose web_sources list")

    def test_web_results_lifted_to_outer_scope(self):
        # Post-split (chore PR): web_results is a field on the
        # AnswerBlock dataclass in pipeline_synth.py with a
        # default_factory=list — guaranteed bound at AnswerBlock()
        # construction time, which is the first line of generate_answer
        # (before any try / branching). Equivalent contract to the
        # pre-split "init before the if low_relevance branch" pattern.
        self.assertIn("class AnswerBlock", self.src)
        self.assertIn("web_results:", self.src)
        self.assertIn("field(default_factory=list)", self.src,
            "web_results must default to [] via dataclass field factory "
            "so it is bound before generate_answer's try block can fail")

    def test_web_results_declared_outside_try(self):
        # [hotfix preserved across split] AnswerBlock() is constructed
        # at line 1 of generate_answer's body, before ``try:`` — so
        # ``out.web_results`` is bound even if every line inside try
        # raises. The pre-split version used a top-level ``web_results:
        # list = []`` for the same purpose; the dataclass default
        # encodes the invariant in the type.
        gen_idx = self.src.index("def generate_answer(")
        try_idx = self.src.index("\n    try:\n        sys_prefix = ", gen_idx)
        init_idx = self.src.index("out = AnswerBlock()", gen_idx)
        self.assertLess(init_idx, try_idx,
            "AnswerBlock() must be constructed BEFORE the try: block — "
            "otherwise any exception before that line leaves out.web_results "
            "unbound and the caller's `bool(web_results)` raises UnboundLocalError")

    def test_web_sources_format_url_title(self):
        # Each entry: {"title": ..., "url": ..., "engine": ...}
        return_idx = self.src.rindex("return {")
        body = self.src[return_idx - 600:return_idx + 800]
        self.assertIn('"title"', body)
        self.assertIn('"url"', body)
        self.assertIn('"engine"', body)


class QueryResponseShapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server_llmwiki as srv
        cls.src = inspect.getsource(srv)

    def test_response_model_has_fields(self):
        m = re.search(
            r"class QueryResponse\(BaseModel\):(.+?)class\s+\w+\(",
            self.src, re.DOTALL,
        )
        self.assertIsNotNone(m, "couldn't locate QueryResponse model")
        body = m.group(1)
        self.assertIn("web_used", body,
            "QueryResponse must declare web_used field")
        self.assertIn("web_sources", body,
            "QueryResponse must declare web_sources field")

    def test_query_handler_propagates_fields(self):
        # The /query/ handler builds a `response` dict — must include
        # web_used + web_sources from result.
        idx = self.src.index('@app.post("/query/"')
        end = self.src.index('@app.', idx + 10)
        body = self.src[idx:end]
        self.assertIn('"web_used"', body,
            "/query/ handler must include web_used in response")
        self.assertIn('"web_sources"', body,
            "/query/ handler must include web_sources in response")
        self.assertIn('result.get("web_used"', body,
            "must read web_used from pipeline result")


class FrontendBadgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "frontend" / "static" / "chat.js").read_text(encoding="utf-8")

    def test_badge_renders_when_web_used(self):
        # appendJamesMsg must check data.web_used and emit the badge.
        idx = self.js.index("function appendJamesMsg")
        m = re.search(r"\nfunction\s+\w+\s*\(", self.js[idx + 1:])
        end = idx + 1 + m.start() if m else idx + 8000
        body = self.js[idx:end]
        self.assertIn("data.web_used", body,
            "appendJamesMsg must inspect data.web_used flag")
        self.assertIn("🌐 웹 검색 사용됨", body,
            "badge label must contain 🌐 웹 검색 사용됨")

    def test_engine_label_humanized(self):
        idx = self.js.index("function appendJamesMsg")
        body = self.js[idx:idx + 8000]
        # tavily → Tavily, duckduckgo → DuckDuckGo
        self.assertIn("Tavily", body,
            "engine label must humanize 'tavily' → 'Tavily'")
        self.assertIn("DuckDuckGo", body,
            "engine label must humanize 'duckduckgo' → 'DuckDuckGo'")

    def test_url_list_in_details(self):
        idx = self.js.index("function appendJamesMsg")
        body = self.js[idx:idx + 8000]
        self.assertIn("<details", body,
            "source list should be wrapped in <details> for collapsibility")
        self.assertIn('target="_blank"', body,
            "URLs must open in new tab")
        self.assertIn('rel="noopener noreferrer"', body,
            "external links must use noopener noreferrer for security")
        self.assertIn("web_sources", body,
            "must read web_sources array")

    def test_badge_inserted_into_bubble_html(self):
        # The webBadge variable must be templated into the div innerHTML.
        # Use next-function bound so we get the full body even when it
        # exceeds 8000 chars.
        idx = self.js.index("function appendJamesMsg")
        m = re.search(r"\nfunction\s+\w+\s*\(", self.js[idx + 1:])
        end = idx + 1 + m.start() if m else idx + 12000
        body = self.js[idx:end]
        # Look for ${webBadge} in the innerHTML literal.
        self.assertIn("${webBadge}", body,
            "webBadge must be interpolated into the message HTML")


class BackwardCompatTests(unittest.TestCase):
    """Internal-only responses (web_used=false) must render unchanged."""

    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "frontend" / "static" / "chat.js").read_text(encoding="utf-8")

    def test_no_badge_when_web_used_false(self):
        # The webBadge starts as empty string, only set when web_used is true.
        idx = self.js.index("let webBadge = ''")
        # Make sure badge is empty by default.
        body = self.js[idx:idx + 100]
        self.assertIn("''", body,
            "webBadge default must be empty so no chrome on internal answers")


if __name__ == "__main__":
    unittest.main()
