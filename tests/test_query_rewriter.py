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
            out, latency, attempted = rw.rewrite("이것은 테스트 질의입니다")
        self.assertEqual(out, "이것은 테스트 질의입니다")
        self.assertEqual(latency, 0)
        self.assertFalse(attempted,
            "env opt-in unset → backend.complete() must NOT be called "
            "→ attempted MUST be False (caller uses this to decide "
            "whether to emit a trace row)")
        fake.complete.assert_not_called()

    def test_force_bypasses_env_gate(self):
        from core.retrieval.query_rewriter import QueryRewriter
        rw = QueryRewriter()
        fake = MagicMock()
        fake.complete.return_value = _completion(
            text='{"rewritten": "테스트 질의 (시험 검사)"}'
        )
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            out, _, attempted = rw.rewrite("이것은 테스트 질의입니다", force=True)
        self.assertEqual(out, "테스트 질의 (시험 검사)")
        self.assertTrue(attempted,
            "force=True + successful backend call → attempted must be True")
        fake.complete.assert_called_once()


class ShortQueryTests(unittest.TestCase):

    def test_empty_query_identity(self):
        from core.retrieval.query_rewriter import QueryRewriter
        # Short-circuit before backend lookup → attempted=False so the
        # pipeline knows not to emit a "rewrite ran" trace row.
        self.assertEqual(QueryRewriter().rewrite(""), ("", 0, False))

    def test_whitespace_query_identity(self):
        from core.retrieval.query_rewriter import QueryRewriter
        self.assertEqual(QueryRewriter().rewrite("   "), ("   ", 0, False))

    def test_short_query_identity(self):
        from core.retrieval.query_rewriter import QueryRewriter
        # 3-char query is below the rewrite threshold
        self.assertEqual(QueryRewriter().rewrite("RAG"), ("RAG", 0, False))


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
        out, _, attempted = rw.rewrite("이것은 충분히 긴 질의입니다")
        self.assertEqual(out, "이것은 충분히 긴 질의입니다")
        self.assertFalse(attempted,
            "backend lookup miss is a configuration error — the LLM "
            "wasn't called, so attempted must be False (no trace row)")

    def test_backend_raises_returns_identity(self):
        from core.retrieval.query_rewriter import QueryRewriter
        rw = QueryRewriter()
        fake = MagicMock()
        fake.complete.side_effect = RuntimeError("ollama timeout")
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            out, _, attempted = rw.rewrite("긴 한국어 질의 입니다")
        self.assertEqual(out, "긴 한국어 질의 입니다")
        self.assertTrue(attempted,
            "backend.complete() raised — it WAS called, so attempted "
            "must be True (operator wants to see this in the trace)")

    def test_backend_returns_error_string_identity(self):
        from core.retrieval.query_rewriter import QueryRewriter
        rw = QueryRewriter()
        fake = MagicMock()
        fake.complete.return_value = _completion(error="backend reported error")
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            out, _, attempted = rw.rewrite("긴 한국어 질의 입니다")
        self.assertEqual(out, "긴 한국어 질의 입니다")
        self.assertTrue(attempted)

    def test_empty_text_returns_identity(self):
        from core.retrieval.query_rewriter import QueryRewriter
        rw = QueryRewriter()
        fake = MagicMock()
        fake.complete.return_value = _completion(text="")
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            out, _, attempted = rw.rewrite("긴 한국어 질의 입니다")
        self.assertEqual(out, "긴 한국어 질의 입니다")
        self.assertTrue(attempted)


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
        out, _, attempted = self._rewrite_with_text('{"rewritten": "다시 작성된 질의"}')
        self.assertEqual(out, "다시 작성된 질의")
        self.assertTrue(attempted)

    def test_json_with_leading_prose(self):
        # The LLM padded with prose before the JSON despite "JSON only"
        out, _, _ = self._rewrite_with_text(
            "여기 재작성된 질의입니다:\n{\"rewritten\": \"새 질의\"}"
        )
        self.assertEqual(out, "새 질의")

    def test_json_with_trailing_prose(self):
        out, _, _ = self._rewrite_with_text(
            '{"rewritten": "새 질의"}\n위 형태로 다시 작성했습니다.'
        )
        self.assertEqual(out, "새 질의")

    def test_malformed_json_identity(self):
        out, _, attempted = self._rewrite_with_text("not json at all, just prose")
        self.assertEqual(out, "이것은 충분히 긴 한국어 질의입니다")
        self.assertTrue(attempted,
            "JSON parse failed but backend was called — surface this "
            "to the operator via the trace (attempted=True)")

    def test_missing_rewritten_key_identity(self):
        out, _, attempted = self._rewrite_with_text('{"other": "value"}')
        self.assertEqual(out, "이것은 충분히 긴 한국어 질의입니다")
        self.assertTrue(attempted)

    def test_empty_rewritten_value_identity(self):
        out, _, attempted = self._rewrite_with_text('{"rewritten": ""}')
        self.assertEqual(out, "이것은 충분히 긴 한국어 질의입니다")
        self.assertTrue(attempted)

    def test_runaway_expansion_rejected(self):
        # A reply that's > 3× the original length is most likely the
        # LLM explaining instead of rewriting — keep the original.
        long_value = "x" * 200
        out, _, attempted = self._rewrite_with_text(
            f'{{"rewritten": "{long_value}"}}',
            query="짧은 질의",
        )
        self.assertEqual(out, "짧은 질의")
        self.assertTrue(attempted)

    def test_semantically_identical_rewrite_still_attempted(self):
        """[PR-2 시인성 2026-05-18] LLM 이 의미적으로 동일한 문자열을
        반환했더라도 backend.complete() 가 호출됐다면 attempted=True.

        이전엔 pipeline 의 ``if expanded_query != safe_query`` 게이트
        때문에 이런 경우 trace 행이 emit 안 됐다 — 사용자가 옵트인을
        켰는데 trace 가 비어 있으면 env 도달 / LLM 호출 / 의미 동일
        중 어느 것인지 구분 불가했다. 시그니처에 attempted 추가로
        pipeline 이 'rewrite 실행됨, 변화 없음' 행을 그릴 수 있게 됨.
        """
        original = "이것은 충분히 긴 한국어 질의입니다"
        # LLM 이 원본과 동일한 텍스트를 반환 — 의미상 변화 없음 케이스
        out, _, attempted = self._rewrite_with_text(
            f'{{"rewritten": "{original}"}}',
            query=original,
        )
        self.assertEqual(out, original)
        self.assertTrue(attempted,
            "Backend was called and returned a valid rewrite that "
            "happens to equal the input — attempted MUST be True so "
            "the pipeline emits a 'no change' trace row")


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
            out, latency, attempted = rw.rewrite("이것은 충분히 긴 한국어 질의입니다")
        self.assertEqual(out, "이것은 충분히 긴 한국어 질의입니다")
        self.assertGreaterEqual(latency, 15)
        self.assertTrue(attempted)


class AdaptiveBudgetWiringTests(unittest.TestCase):
    """D1.B — TaskBudget wiring at the query_rewriter call site.

    Pins the cap actually passed to backend.complete() against the
    TaskBudget tier matching the user's query. Legacy max_tokens=int
    override path also pinned so callers with explicit budget reasons
    (e.g. STEP 7 bench A/B runs) still get a fixed cap.
    """

    def setUp(self):
        self._saved = os.environ.get("JAMES_ENABLE_QUERY_REWRITE")
        os.environ["JAMES_ENABLE_QUERY_REWRITE"] = "1"

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("JAMES_ENABLE_QUERY_REWRITE", None)
        else:
            os.environ["JAMES_ENABLE_QUERY_REWRITE"] = self._saved

    def _capture_cap(self, query):
        """Run rewrite, return the max_tokens kwarg backend.complete saw."""
        from core.retrieval.query_rewriter import QueryRewriter
        rw = QueryRewriter()  # max_tokens=None → dynamic budget path
        fake = MagicMock()
        fake.complete.return_value = _completion(text='{"rewritten":"x"}')
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            rw.rewrite(query)
        # backend.complete was called once with a max_tokens kwarg
        _, kwargs = fake.complete.call_args
        return kwargs.get("max_tokens")

    def test_substitution_query_routes_to_cap_substitution(self):
        from core.reasoning.budget import CAP_SUBSTITUTION
        # Korean substitution pattern
        cap = self._capture_cap("환불 정책 그대로 알려주세요")
        self.assertEqual(cap, CAP_SUBSTITUTION,
            "substitution-pattern query must request CAP_SUBSTITUTION (200) "
            "from the backend, not the legacy 4096 default")

    def test_substitution_english_routes_to_cap_substitution(self):
        from core.reasoning.budget import CAP_SUBSTITUTION
        cap = self._capture_cap("Return the exact refund policy verbatim")
        self.assertEqual(cap, CAP_SUBSTITUTION)

    def test_heavy_query_routes_to_cap_heavy(self):
        from core.reasoning.budget import CAP_HEAVY
        cap = self._capture_cap("한국 RAG 시장을 4단계로 분석해주세요")
        self.assertEqual(cap, CAP_HEAVY,
            "heavy-synthesis marker must escalate to CAP_HEAVY (4096) "
            "— matches the pre-D1.B safe default for these queries")

    def test_default_query_routes_to_cap_light(self):
        from core.reasoning.budget import CAP_LIGHT
        cap = self._capture_cap("RAG가 무엇인가요?")
        self.assertEqual(cap, CAP_LIGHT,
            "default query without markers must request CAP_LIGHT (800) "
            "— the 5x token reduction vs the legacy 4096 cap")

    def test_legacy_explicit_max_tokens_bypasses_budget(self):
        """A caller passing max_tokens=4096 explicitly gets the legacy
        path — backend.complete sees exactly 4096 regardless of query
        content. Important for STEP 7 bench A/B runs that need cap
        invariance across queries to isolate non-cap effects."""
        from core.retrieval.query_rewriter import QueryRewriter
        rw = QueryRewriter(max_tokens=4096)
        fake = MagicMock()
        fake.complete.return_value = _completion(text='{"rewritten":"x"}')
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            # Use a substitution query — would normally trip CAP_SUBSTITUTION
            rw.rewrite("환불 정책 그대로 알려주세요")
        _, kwargs = fake.complete.call_args
        self.assertEqual(kwargs.get("max_tokens"), 4096,
            "explicit max_tokens=4096 must override TaskBudget")


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
