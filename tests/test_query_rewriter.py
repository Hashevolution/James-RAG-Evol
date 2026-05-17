"""Phase 1 PR-2 — query rewriter unit tests.

ARCHITECTURE.md §5.7.1 Query Rewriter. Uses the Backend registry (Phase
0 L0) so unit tests register a mock backend rather than hitting the
live Ollama. The pipeline integration smoke test (rewriter actually
called from STEP 0.5b) is verified by running the real-server STEP 7
bench post-merge — see PR body.

Coverage:
  * opt-in gate: JAMES_ENABLE_QUERY_REWRITE unset → identity
  * force flag: bypasses the env gate (for tests / debug)
  * short / empty query → identity (rewrite would only add noise)
  * backend lookup failure → identity
  * backend.complete error → identity, latency still recorded
  * malformed JSON → identity
  * tolerant parser: pure JSON / JSON with leading prose / JSON with
    trailing prose all yield the rewritten string
  * runaway expansion (> 3× length) rejected → identity
  * KO vs EN prompt template selection
  * singleton get_query_rewriter() returns the same instance
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


def _completion(text="", error=""):
    """Minimal stand-in for the CompletionResult dataclass."""
    res = MagicMock()
    res.text = text
    res.error = error
    return res


def _make_rewriter_with_backend(mock_backend):
    """Build a QueryRewriter pointing at our mock backend.

    We patch ``core.reasoning.backends.get_backend`` so the rewriter's
    lazy lookup returns our mock without touching the real registry.
    """
    from core.retrieval.query_rewriter import QueryRewriter
    return QueryRewriter()   # backend resolved at .rewrite() time


class OptInGateTests(unittest.TestCase):
    """Default OFF — rewriter must not call the backend without an
    explicit opt-in. Operators choosing not to pay the extra LLM
    round-trip should see byte-identical behaviour to v0.3.0.
    """

    def setUp(self):
        self._saved = os.environ.get("JAMES_ENABLE_QUERY_REWRITE")
        os.environ.pop("JAMES_ENABLE_QUERY_REWRITE", None)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("JAMES_ENABLE_QUERY_REWRITE", None)
        else:
            os.environ["JAMES_ENABLE_QUERY_REWRITE"] = self._saved

    def test_disabled_default_returns_identity_no_backend_call(self):
        from core.retrieval.query_rewriter import QueryRewriter
        rw = QueryRewriter()
        fake = MagicMock()
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            out, latency = rw.rewrite("이것은 테스트 질의입니다")
        self.assertEqual(out, "이것은 테스트 질의입니다")
        self.assertEqual(latency, 0)
        fake.complete.assert_not_called()

    def test_force_bypasses_env_gate(self):
        from core.retrieval.query_rewriter import QueryRewriter
        rw = QueryRewriter()
        fake = MagicMock()
        fake.complete.return_value = _completion(
            text='{"rewritten": "테스트 질의 (시험 검사)"}'
        )
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            out, _ = rw.rewrite("이것은 테스트 질의입니다", force=True)
        self.assertEqual(out, "테스트 질의 (시험 검사)")
        fake.complete.assert_called_once()


class ShortQueryTests(unittest.TestCase):

    def test_empty_query_identity(self):
        from core.retrieval.query_rewriter import QueryRewriter
        self.assertEqual(QueryRewriter().rewrite(""), ("", 0))

    def test_whitespace_query_identity(self):
        from core.retrieval.query_rewriter import QueryRewriter
        self.assertEqual(QueryRewriter().rewrite("   "), ("   ", 0))

    def test_short_query_identity(self):
        from core.retrieval.query_rewriter import QueryRewriter
        # 3-char query is below the rewrite threshold
        self.assertEqual(QueryRewriter().rewrite("RAG"), ("RAG", 0))


class BackendFailureTests(unittest.TestCase):
    """Every failure mode (lookup miss, raise, error string, empty
    response, bad JSON) must fall back to identity. The pipeline
    cannot tolerate a None or exception here.
    """

    def setUp(self):
        self._saved = os.environ.get("JAMES_ENABLE_QUERY_REWRITE")
        os.environ["JAMES_ENABLE_QUERY_REWRITE"] = "1"

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("JAMES_ENABLE_QUERY_REWRITE", None)
        else:
            os.environ["JAMES_ENABLE_QUERY_REWRITE"] = self._saved

    def test_backend_lookup_missing_returns_identity(self):
        from core.retrieval.query_rewriter import QueryRewriter
        rw = QueryRewriter(backend_id="definitely_not_registered")
        out, _ = rw.rewrite("이것은 충분히 긴 질의입니다")
        self.assertEqual(out, "이것은 충분히 긴 질의입니다")

    def test_backend_raises_returns_identity(self):
        from core.retrieval.query_rewriter import QueryRewriter
        rw = QueryRewriter()
        fake = MagicMock()
        fake.complete.side_effect = RuntimeError("ollama timeout")
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            out, _ = rw.rewrite("긴 한국어 질의 입니다")
        self.assertEqual(out, "긴 한국어 질의 입니다")

    def test_backend_returns_error_string_identity(self):
        from core.retrieval.query_rewriter import QueryRewriter
        rw = QueryRewriter()
        fake = MagicMock()
        fake.complete.return_value = _completion(error="backend reported error")
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            out, _ = rw.rewrite("긴 한국어 질의 입니다")
        self.assertEqual(out, "긴 한국어 질의 입니다")

    def test_empty_text_returns_identity(self):
        from core.retrieval.query_rewriter import QueryRewriter
        rw = QueryRewriter()
        fake = MagicMock()
        fake.complete.return_value = _completion(text="")
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            out, _ = rw.rewrite("긴 한국어 질의 입니다")
        self.assertEqual(out, "긴 한국어 질의 입니다")


class JsonParseTests(unittest.TestCase):

    def setUp(self):
        self._saved = os.environ.get("JAMES_ENABLE_QUERY_REWRITE")
        os.environ["JAMES_ENABLE_QUERY_REWRITE"] = "1"

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("JAMES_ENABLE_QUERY_REWRITE", None)
        else:
            os.environ["JAMES_ENABLE_QUERY_REWRITE"] = self._saved

    def _rewrite_with_text(self, llm_text, query="이것은 충분히 긴 한국어 질의입니다"):
        from core.retrieval.query_rewriter import QueryRewriter
        rw = QueryRewriter()
        fake = MagicMock()
        fake.complete.return_value = _completion(text=llm_text)
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            return rw.rewrite(query)

    def test_pure_json_response(self):
        out, _ = self._rewrite_with_text('{"rewritten": "다시 작성된 질의"}')
        self.assertEqual(out, "다시 작성된 질의")

    def test_json_with_leading_prose(self):
        # The LLM padded with prose before the JSON despite "JSON only"
        out, _ = self._rewrite_with_text(
            "여기 재작성된 질의입니다:\n{\"rewritten\": \"새 질의\"}"
        )
        self.assertEqual(out, "새 질의")

    def test_json_with_trailing_prose(self):
        out, _ = self._rewrite_with_text(
            '{"rewritten": "새 질의"}\n위 형태로 다시 작성했습니다.'
        )
        self.assertEqual(out, "새 질의")

    def test_malformed_json_identity(self):
        out, _ = self._rewrite_with_text("not json at all, just prose")
        self.assertEqual(out, "이것은 충분히 긴 한국어 질의입니다")

    def test_missing_rewritten_key_identity(self):
        out, _ = self._rewrite_with_text('{"other": "value"}')
        self.assertEqual(out, "이것은 충분히 긴 한국어 질의입니다")

    def test_empty_rewritten_value_identity(self):
        out, _ = self._rewrite_with_text('{"rewritten": ""}')
        self.assertEqual(out, "이것은 충분히 긴 한국어 질의입니다")

    def test_runaway_expansion_rejected(self):
        # A reply that's > 3× the original length is most likely the
        # LLM explaining instead of rewriting — keep the original.
        long_value = "x" * 200
        out, _ = self._rewrite_with_text(
            f'{{"rewritten": "{long_value}"}}',
            query="짧은 질의",
        )
        self.assertEqual(out, "짧은 질의")


class LanguageDetectionTests(unittest.TestCase):
    """The rewriter picks Korean or English prompt based on character
    ratio. We assert the backend received the right template by
    inspecting the prompt argument.
    """

    def setUp(self):
        self._saved = os.environ.get("JAMES_ENABLE_QUERY_REWRITE")
        os.environ["JAMES_ENABLE_QUERY_REWRITE"] = "1"

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("JAMES_ENABLE_QUERY_REWRITE", None)
        else:
            os.environ["JAMES_ENABLE_QUERY_REWRITE"] = self._saved

    def _capture_prompt(self, query):
        from core.retrieval.query_rewriter import QueryRewriter
        rw = QueryRewriter()
        fake = MagicMock()
        fake.complete.return_value = _completion(
            text='{"rewritten": "ok"}'
        )
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            rw.rewrite(query)
        return fake.complete.call_args.args[0]

    def test_korean_query_uses_korean_prompt(self):
        prompt = self._capture_prompt("RAG가 무엇인지 설명해줘")
        self.assertIn("원본 질의", prompt)
        self.assertNotIn("Original query", prompt)

    def test_english_query_uses_english_prompt(self):
        prompt = self._capture_prompt("Explain what RAG is")
        self.assertIn("Original query", prompt)
        self.assertNotIn("원본 질의", prompt)


class SingletonTests(unittest.TestCase):

    def test_get_query_rewriter_returns_same_instance(self):
        from core.retrieval.query_rewriter import (
            get_query_rewriter, _clear_singleton_for_tests,
        )
        _clear_singleton_for_tests()
        a = get_query_rewriter()
        b = get_query_rewriter()
        self.assertIs(a, b)


class LatencyRecordedTests(unittest.TestCase):
    """Even on failure the helper reports how long the backend took —
    operators want to know what cost a fallback-to-identity path."""

    def setUp(self):
        self._saved = os.environ.get("JAMES_ENABLE_QUERY_REWRITE")
        os.environ["JAMES_ENABLE_QUERY_REWRITE"] = "1"

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("JAMES_ENABLE_QUERY_REWRITE", None)
        else:
            os.environ["JAMES_ENABLE_QUERY_REWRITE"] = self._saved

    def test_failure_latency_recorded(self):
        from core.retrieval.query_rewriter import QueryRewriter
        rw = QueryRewriter()
        fake = MagicMock()
        # simulate a slow backend that ultimately errors
        def slow_error(prompt, **kw):
            import time
            time.sleep(0.02)
            return _completion(error="timeout")
        fake.complete.side_effect = slow_error
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            out, latency = rw.rewrite("이것은 충분히 긴 한국어 질의입니다")
        self.assertEqual(out, "이것은 충분히 긴 한국어 질의입니다")
        self.assertGreaterEqual(latency, 15)


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
