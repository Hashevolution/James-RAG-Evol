"""Cycle γ Phase D2 — softener bilingual extension contract tests.

Pins:
  * Default (`JAMES_SOFTENER_BILINGUAL` unset / "0") = Korean-only,
    byte-identical to pre-Phase-D2 production
  * `JAMES_SOFTENER_BILINGUAL=1` adds the English abstention trigger
    set, mirroring the RGB scorer's `_ABSTENTION_EN`
  * Retry prompt scaffold switches Korean → English when (bilingual
    AND query language English)
  * Korean queries keep the Korean retry prompt regardless of
    bilingual env (back-compat)

Path D positioning honoured: this is NOT an NLI verifier (no
HALT-RAG style), just a Korean-only-gap fix for cross-lingual
RAG abstention. See memory/feedback_path_d_james_not_specialty_
verifier.md for the boundary.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class AbstentionTriggersTests(unittest.TestCase):

    def test_default_korean_only(self):
        from core.reasoning.pipeline_synth import (
            _abstention_triggers, _KOREAN_NO_DATA_TRIGGERS,
            _ENGLISH_NO_DATA_TRIGGERS,
        )
        triggers = _abstention_triggers(bilingual=False)
        self.assertEqual(triggers, _KOREAN_NO_DATA_TRIGGERS)
        # All Korean strings preserved
        self.assertIn("자료에 없음. 관련된", triggers)
        self.assertIn("답변 생성에 실패", triggers)
        self.assertIn("LLM 응답 생성 중 오류", triggers)
        # No English additions
        for s in _ENGLISH_NO_DATA_TRIGGERS:
            self.assertNotIn(s, triggers,
                              msg=f"English {s!r} leaked into default")

    def test_bilingual_includes_english(self):
        from core.reasoning.pipeline_synth import (
            _abstention_triggers, _KOREAN_NO_DATA_TRIGGERS,
            _ENGLISH_NO_DATA_TRIGGERS,
        )
        triggers = _abstention_triggers(bilingual=True)
        # Korean preserved (back-compat)
        for s in _KOREAN_NO_DATA_TRIGGERS:
            self.assertIn(s, triggers)
        # English additions present
        for s in _ENGLISH_NO_DATA_TRIGGERS:
            self.assertIn(s, triggers)
        # Specific high-frequency patterns from RGB scorer
        self.assertIn("Insufficient information", triggers)
        self.assertIn("I cannot find", triggers)
        self.assertIn("Unable to answer", triggers)

    def test_no_duplicates(self):
        from core.reasoning.pipeline_synth import _abstention_triggers
        for bilingual in (False, True):
            triggers = _abstention_triggers(bilingual=bilingual)
            self.assertEqual(len(triggers), len(set(triggers)),
                              msg=f"bilingual={bilingual} has duplicates")

    def test_english_mirrors_rgb_scorer_subset(self):
        """The English triggers are a subset (or near-subset) of the
        RGB scorer's _ABSTENTION_EN — keeps end-to-end semantics
        consistent: when JAMES retries on an English 'Insufficient'
        answer, that same answer would be scored as abstention by
        the bench."""
        from core.reasoning.pipeline_synth import _ENGLISH_NO_DATA_TRIGGERS
        from eval.external.rgb_scorer import _ABSTENTION_EN
        # Each Phase-D2 English trigger should have at least one
        # matching prefix in the RGB scorer's pattern set
        # (lower-cased, substring).
        scorer_set_lower = set(p.lower() for p in _ABSTENTION_EN)
        for trig in _ENGLISH_NO_DATA_TRIGGERS:
            trig_lower = trig.lower()
            # Match either exact, or scorer pattern is substring of
            # trigger, or trigger is substring of scorer pattern.
            matched = any(
                p == trig_lower or p in trig_lower or trig_lower in p
                for p in scorer_set_lower
            )
            self.assertTrue(matched,
                             msg=f"trigger {trig!r} has no RGB-scorer "
                                 f"mirror — soft semantic break")


class RetryPromptTests(unittest.TestCase):

    def test_korean_query_bilingual_off_keeps_korean(self):
        from core.reasoning.pipeline_synth import _build_retry_prompt
        out = _build_retry_prompt(
            sys_prefix="", rule_text="rule", query="질문 내용",
            is_korean=True, bilingual=False,
        )
        self.assertIn("질문:", out)
        self.assertIn("답변:", out)
        self.assertIn("내부 자료에는", out)

    def test_korean_query_bilingual_on_keeps_korean(self):
        """Korean queries always get the Korean scaffold (regardless
        of bilingual env) — back-compat guarantee."""
        from core.reasoning.pipeline_synth import _build_retry_prompt
        out = _build_retry_prompt(
            sys_prefix="", rule_text="rule", query="질문 내용",
            is_korean=True, bilingual=True,
        )
        self.assertIn("질문:", out)
        self.assertNotIn("Question:", out)

    def test_english_query_bilingual_off_keeps_korean(self):
        """Back-compat: English query + bilingual OFF = Korean
        prompt (pre-Phase-D2 behaviour byte-identical)."""
        from core.reasoning.pipeline_synth import _build_retry_prompt
        out = _build_retry_prompt(
            sys_prefix="", rule_text="rule", query="What is X?",
            is_korean=False, bilingual=False,
        )
        self.assertIn("질문:", out)
        self.assertIn("답변:", out)

    def test_english_query_bilingual_on_switches_to_english(self):
        """The Phase D2 fix: English query + bilingual ON = English
        prompt scaffold (no Korean 질문/답변)."""
        from core.reasoning.pipeline_synth import _build_retry_prompt
        out = _build_retry_prompt(
            sys_prefix="", rule_text="rule", query="What is X?",
            is_korean=False, bilingual=True,
        )
        self.assertIn("Question:", out)
        self.assertIn("Answer:", out)
        self.assertNotIn("질문:", out)
        self.assertNotIn("답변:", out)
        # Abstention guidance text in English
        self.assertIn("cannot answer", out)

    def test_sys_prefix_prepended(self):
        from core.reasoning.pipeline_synth import _build_retry_prompt
        out = _build_retry_prompt(
            sys_prefix="SYS_PREFIX_TOKEN\n\n", rule_text="rule",
            query="What is X?", is_korean=False, bilingual=True,
        )
        self.assertTrue(out.startswith("SYS_PREFIX_TOKEN\n\n"))

    def test_rule_text_included(self):
        from core.reasoning.pipeline_synth import _build_retry_prompt
        out = _build_retry_prompt(
            sys_prefix="", rule_text="SOME_RULE_TEXT",
            query="What is X?", is_korean=False, bilingual=True,
        )
        self.assertIn("SOME_RULE_TEXT", out)


class IntegrationContractTests(unittest.TestCase):
    """End-to-end contract: env var → triggers + prompt match."""

    def test_env_default_keeps_korean_only(self):
        from core.reasoning.pipeline_synth import _abstention_triggers
        triggers = _abstention_triggers(
            bilingual=(os.environ.get("JAMES_SOFTENER_BILINGUAL")
                      == "1")
        )
        # Without the env, we get Korean only — pre-Phase-D2 contract
        if os.environ.get("JAMES_SOFTENER_BILINGUAL") != "1":
            self.assertNotIn("Insufficient information", triggers)

    def test_phase_b_query_3_would_trigger_under_bilingual(self):
        """The actual Phase B+C+D query #3 R0 answer started with
        'Insufficient information.' — confirm it would now fire the
        softener under bilingual=True."""
        from core.reasoning.pipeline_synth import _abstention_triggers
        phase_c_q3_answer = (
            "Insufficient information. While the context confirms "
            "that Jason Semore spent time at Valdosta State and "
            "returned to Georgia Tech, it does not specify what "
            "position he held while at Valdosta State."
        )
        triggers = _abstention_triggers(bilingual=True)
        matched = any(phase_c_q3_answer.startswith(t) for t in triggers)
        self.assertTrue(matched,
                         msg="Bilingual softener should fire on the "
                             "Phase C query-3 answer pattern")


if __name__ == "__main__":
    unittest.main()
