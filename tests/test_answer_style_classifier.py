"""AnswerStyleClassifier (cycle β #2, 2026-06-06) — unit tests.

Coverage:
  - FAST_TERSE patterns: who/what/when/which/yes-no/KO 단답 → "terse"
  - FAST_NOT_TERSE patterns: compare/analyze/why/보고서/비교 → "natural"
  - 둘 다 미매치 → None (LLM fallback) or default "natural"
  - JAMES_AUTO_STYLE env gate — "0" → ("natural", "default")
  - module wrapper classify_answer_style — same contract

Wiring contract (separate):
  - engine.py STEP 0.3 must call classify_answer_style when
    response_style is empty; explicit response_style must skip
    auto-selection (override preserved).
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FastPatternTerseTests(unittest.TestCase):
    """FAST_TERSE_PATTERNS — single-answer queries classify as 'terse'."""

    def setUp(self):
        from core.answer_style_classifier import AnswerStyleClassifier
        self.cls = AnswerStyleClassifier()

    def test_detail_requests_classify_detailed(self):
        # 2026-06-26 — explicit "give me the full detail" requests must
        # win over terse/natural so DETAILED_PRESET reproduces source
        # content (e.g. an ingested schedule table) instead of summarising.
        for q in [
            "전장연 일정 상세히 알려줘",
            "이 자료 원문 그대로 보여줘",
            "7월 1일 전체 일정 알려줘",
            "구체적으로 설명해",
            "tell me in detail",
            "show me the full table",
        ]:
            self.assertEqual(self.cls.classify_fast(q), "detailed",
                             f"detail request {q!r} → detailed")

    def test_en_wh_fact_question(self):
        for q in [
            "Who is the CEO of TechCorp?",
            "What year was OpenAI founded?",
            "When did the FTX trial start?",
            "Where is Anthropic headquartered?",
            "Which company acquired DeepMind?",
            "How many employees does Google have?",
            "How old is the company?",
        ]:
            self.assertEqual(self.cls.classify_fast(q), "terse",
                             f"Wh-fact must be terse: {q!r}")

    def test_en_yes_no_question(self):
        for q in [
            "Is Sam Bankman-Fried in jail?",
            "Was the report published on October 7?",
            "Did Trump sell the apartment?",
            "Has the merger closed?",
            "Can the proposal pass?",
        ]:
            self.assertEqual(self.cls.classify_fast(q), "terse",
                             f"Yes/No must be terse: {q!r}")

    def test_ko_wh_fact_question(self):
        for q in [
            "이 회사 CEO는 누구입니까?",
            "이 사건이 언제 일어났나요?",
            "본사는 어디 있어?",
            "직원이 몇 명이죠?",
        ]:
            self.assertEqual(self.cls.classify_fast(q), "terse",
                             f"KO Wh-fact must be terse: {q!r}")


class FastPatternNotTerseTests(unittest.TestCase):
    """FAST_NOT_TERSE_PATTERNS — analytical/report queries classify
    as 'natural' fast (no LLM fallback needed)."""

    def setUp(self):
        from core.answer_style_classifier import AnswerStyleClassifier
        self.cls = AnswerStyleClassifier()

    def test_en_analytical(self):
        for q in [
            "Compare GPT-4 and Claude on reasoning benchmarks",
            "Analyze the impact of the FTX collapse on crypto markets",
            "Evaluate the security posture of this codebase",
            "Why did Sam Altman get fired?",
            "How does retrieval-augmented generation work?",
            "Explain the difference between RAG and fine-tuning",
            "Discuss the long-term effects of monetary tightening",
        ]:
            self.assertEqual(self.cls.classify_fast(q), "natural",
                             f"Analytical must be natural: {q!r}")

    def test_en_report(self):
        for q in [
            "Give me a summary of the Q3 earnings call",
            "Give a breakdown of the technology stack",
            "Give me an overview of recent AI launches",
        ]:
            self.assertEqual(self.cls.classify_fast(q), "natural",
                             f"Report must be natural: {q!r}")

    def test_ko_analytical(self):
        for q in [
            "OpenAI 와 Anthropic 비교해줘",
            "FTX 사태 영향을 분석해줘",
            "이 코드의 보안 평가해줘",
            "왜 Altman 이 해고됐지?",
            "어떤 이유로 매출이 떨어졌나?",
        ]:
            self.assertEqual(self.cls.classify_fast(q), "natural",
                             f"KO analytical must be natural: {q!r}")

    def test_ko_report(self):
        for q in [
            "Q3 실적 요약해줘",
            "사건 정리해 줘",
            "기술 스택 개요 설명",
        ]:
            self.assertEqual(self.cls.classify_fast(q), "natural",
                             f"KO report must be natural: {q!r}")


class FastPatternFallthroughTests(unittest.TestCase):
    """둘 다 매치 안 되는 ambiguous query — None 반환 (LLM 분류 권장)."""

    def setUp(self):
        from core.answer_style_classifier import AnswerStyleClassifier
        self.cls = AnswerStyleClassifier()

    def test_ambiguous_queries_return_none(self):
        for q in [
            "Tell me about NVIDIA",
            "X 에 대해 알려줘",
            "NVIDIA Q3 earnings",
            "최근 기술 동향",
        ]:
            self.assertIsNone(self.cls.classify_fast(q),
                              f"Ambiguous must return None: {q!r}")

    def test_empty_query_returns_natural_default(self):
        # 빈 query 는 안전 default natural
        self.assertEqual(self.cls.classify_fast(""), "natural")
        self.assertEqual(self.cls.classify_fast("   "), "natural")


class HybridClassifyTests(unittest.TestCase):
    """classify() — hybrid (fast + LLM fallback) main entry contract."""

    def setUp(self):
        from core.answer_style_classifier import AnswerStyleClassifier
        self.cls = AnswerStyleClassifier()

    def test_fast_match_returns_method_fast(self):
        style, method = self.cls.classify("Who is the CEO?")
        self.assertEqual(style, "terse")
        self.assertEqual(method, "fast")

    def test_natural_fast_match_returns_method_fast(self):
        style, method = self.cls.classify("Compare X and Y")
        self.assertEqual(style, "natural")
        self.assertEqual(method, "fast")

    def test_llm_fallback_disabled_returns_default(self):
        # LLM 호출 안 함 → 안전 default "natural"
        style, method = self.cls.classify("Tell me about NVIDIA",
                                          llm_fallback=False)
        self.assertEqual(style, "natural")
        self.assertEqual(method, "default")


class ModuleWrapperEnvGateTests(unittest.TestCase):
    """classify_answer_style — JAMES_AUTO_STYLE env-gate behavior."""

    def setUp(self):
        self._orig = os.environ.get("JAMES_AUTO_STYLE")

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("JAMES_AUTO_STYLE", None)
        else:
            os.environ["JAMES_AUTO_STYLE"] = self._orig

    def test_env_disable_returns_natural_default(self):
        from core.answer_style_classifier import classify_answer_style
        os.environ["JAMES_AUTO_STYLE"] = "0"
        style, method = classify_answer_style("Who is the CEO?")
        self.assertEqual(style, "natural")
        self.assertEqual(method, "default")

    def test_env_false_word_disables(self):
        from core.answer_style_classifier import classify_answer_style
        os.environ["JAMES_AUTO_STYLE"] = "false"
        style, method = classify_answer_style("Who is the CEO?")
        self.assertEqual(style, "natural")
        self.assertEqual(method, "default")

    def test_env_default_enabled_returns_fast_terse(self):
        from core.answer_style_classifier import classify_answer_style
        os.environ.pop("JAMES_AUTO_STYLE", None)
        style, method = classify_answer_style("Who is the CEO?")
        self.assertEqual(style, "terse")
        self.assertEqual(method, "fast")


class EngineWiringContractTests(unittest.TestCase):
    """engine.py STEP 0.3 must wire AnswerStyleClassifier when
    response_style is empty (auto-mount), preserve explicit override."""

    def test_engine_wires_classifier_at_step_0_3(self):
        import core.reasoning.engine as eng
        import inspect
        src = inspect.getsource(eng.ReasoningEngine._query_impl)
        self.assertIn("classify_answer_style", src,
                      "engine._query_impl must call classify_answer_style")
        self.assertIn("response_style", src,
                      "engine._query_impl must read response_style for "
                      "explicit-override skip")


if __name__ == "__main__":
    unittest.main()
