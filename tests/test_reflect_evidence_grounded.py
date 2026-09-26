"""Critique judges facts against the evidence, or not at all.

The 2026-09-24 cognitive-stages contrast
(`reports/research-runs/cognitive-stages-contrast-20260924.md` §4.1)
traced this sequence in `audit_log`, arm A, Q14 "GPT-6 모델은 언제 공식
발표됐어?":

  1. synth  → "ANSWER: 2026년 4월 15일 …" — correct and grounded
  2. reflect → critique: "치명적인 사실 오류(Hallucination)"
  3. reflect → revise: "공개된 바가 없습니다" — the fact is deleted
  4. verify  → grounded: false (correct!), but recommendation=annotate,
               so the wrong answer shipped with a note attached

`CRITIQUE_PROMPT_*` was formatted with `{query}` and `{draft}` only, so
the only yardstick the critique had for "명백히 틀린 사실" was the model's
own training data. Evidence newer than the model — the normal case for
an internal knowledge base — therefore reads as a hallucination.

These tests pin both halves of the fix:
  * with evidence → facts are judged against the evidence
  * without evidence → the factual dimension is withdrawn, rather than
    falling back on training data

Run:
  python -m pytest tests/test_reflect_evidence_grounded.py -q
"""
from __future__ import annotations

import ast
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.reasoning.reflect import prompts as P  # noqa: E402

DRAFT = (
    "ANSWER: 2026년 4월 15일. 내부 자료에 따르면 OpenAI 가 해당 일자에 "
    "GPT-6 모델을 공식 발표했습니다."
)
EVIDENCE = "2026-04-15 OpenAI 는 GPT-6 를 공식 발표했다. 추론 정확도 35% 향상."


def _completion(text="", error=""):
    res = MagicMock()
    res.text = text
    res.error = error
    return res


# ─── with evidence ──────────────────────────────────────────────────


class GroundedCritiqueTests(unittest.TestCase):
    def test_evidence_reaches_the_prompt(self):
        for is_ko in (True, False):
            p = P.build_critique_prompt("GPT-6?", DRAFT, EVIDENCE, is_ko=is_ko)
            self.assertIn(EVIDENCE, p)

    def test_evidence_outranks_the_models_own_knowledge(self):
        """The load-bearing instruction. Without it the model still has
        its training data as a yardstick and Q14 recurs."""
        ko = P.build_critique_prompt("GPT-6?", DRAFT, EVIDENCE, is_ko=True)
        self.assertIn("오직 위 [근거 자료] 만을 기준으로", ko)
        self.assertIn("오류가 아니다", ko)
        self.assertIn("학습 시점 이후", ko)
        en = P.build_critique_prompt("GPT-6?", DRAFT, EVIDENCE, is_ko=False)
        self.assertIn("and nothing else", en)
        self.assertIn("NOT an error", en)
        self.assertIn("newer than your training data", en)

    def test_unfamiliarity_is_explicitly_not_grounds_for_hallucination(self):
        ko = P.build_critique_prompt("GPT-6?", DRAFT, EVIDENCE, is_ko=True)
        self.assertIn("환각", ko)
        self.assertIn("낯설다는 것은 근거가 되지 않는다", ko)
        en = P.build_critique_prompt("GPT-6?", DRAFT, EVIDENCE, is_ko=False)
        self.assertIn("hallucination", en)
        self.assertIn("is not grounds for that claim", en)

    def test_a_correct_abstention_is_not_overturned_by_a_wrong_subject(self):
        """The guard the first version of this fix was missing.

        Arm E of the 2026-09-26 paired run, Q17 "Anthropic의 CEO는
        누구야?": retrieval returned Palantir material, synth correctly
        answered "insufficient information", and the newly grounded
        critique called that "factually incorrect ... the provided
        evidence explicitly an[swers it]" — revise then shipped
        "Alex Karp", Palantir's CEO. Telling the model to judge against
        the evidence removed the training-data yardstick that had been
        rejecting the wrong entity; nothing replaced it. (Verify did
        not catch it either: at 9 characters the answer fell under
        MIN_ANSWER_LEN_FOR_VERIFY = 30 and was never checked.)
        """
        ko = P.build_critique_prompt("Q?", DRAFT, EVIDENCE, is_ko=True)
        self.assertIn("질문이 묻는 대상", ko)
        self.assertIn("올바른 답이다", ko)
        self.assertIn("다른 대상", ko)
        self.assertIn("환각이다", ko)
        en = P.build_critique_prompt("Q?", DRAFT, EVIDENCE, is_ko=False)
        self.assertIn("the subject the question asks about", en)
        self.assertIn("the correct answer", en)
        self.assertIn("DIFFERENT subject", en)
        self.assertIn("would be the hallucination", en)

    def test_missing_core_is_scoped_to_the_questions_subject(self):
        """Unscoped, "key information present in the evidence but
        omitted" is what licensed pulling B's CEO into A's answer."""
        ko = P.build_critique_prompt("Q?", DRAFT, EVIDENCE, is_ko=True)
        self.assertIn("**질문의 대상에 대해**", ko)
        en = P.build_critique_prompt("Q?", DRAFT, EVIDENCE, is_ko=False)
        self.assertIn("about the question's subject", en)

    def test_every_placeholder_is_filled(self):
        """A stray {context} would ship the literal brace to the model."""
        for is_ko in (True, False):
            p = P.build_critique_prompt("Q?", DRAFT, EVIDENCE, is_ko=is_ko)
            for ph in ("{query}", "{draft}", "{context}"):
                self.assertNotIn(ph, p)


# ─── without evidence ───────────────────────────────────────────────


class UngroundedCritiqueTests(unittest.TestCase):
    """A reviewer that cannot see the evidence is not in a position to
    call any fact wrong. The dimension is withdrawn, not guessed."""

    def test_factual_dimension_is_withdrawn(self):
        ko = P.build_critique_prompt("Q?", DRAFT, "", is_ko=True)
        self.assertIn("사실 오류·환각 지적을 하지 마라", ko)
        self.assertIn("근거 자료가 주어지지 않았다", ko)
        en = P.build_critique_prompt("Q?", DRAFT, "", is_ko=False)
        self.assertIn("Do NOT raise factual errors or hallucinations", en)

    def test_contradiction_is_scoped_to_inside_the_answer(self):
        """Self-contradiction is visible in the draft alone, so it stays
        — but it must not be read as "disagrees with what I know"."""
        ko = P.build_critique_prompt("Q?", DRAFT, "", is_ko=True)
        self.assertIn("답변 내부의 자기모순만", ko)
        en = P.build_critique_prompt("Q?", DRAFT, "", is_ko=False)
        self.assertIn("self-contradiction only", en)

    def test_blank_and_whitespace_context_take_the_ungrounded_path(self):
        for ctx in ("", "   ", "\n\t "):
            p = P.build_critique_prompt("Q?", DRAFT, ctx, is_ko=False)
            self.assertNotIn("[Evidence]", p)
            self.assertIn("no evidence was provided", p)

    def test_legacy_prompt_constants_still_carry_their_pinned_tokens(self):
        # tests/test_v06_reflect_module_size.py asserts these; keep the
        # coupling visible from this side too.
        self.assertIn("Contradiction", P.CRITIQUE_PROMPT_EN)
        self.assertIn("모순", P.CRITIQUE_PROMPT_KO)


# ─── evidence budget ────────────────────────────────────────────────


class ContextBudgetTests(unittest.TestCase):
    """The critique must see at least as much evidence as synth did.

    Otherwise a fact supported only by the tail synth saw, and the
    critique did not, reads as unsupported — the same defect one layer
    down. Same failure shape as the 1000-char synth cap
    (`feedback_synth_context_1000_truncation_rootcause`)."""

    def setUp(self):
        self._saved = os.environ.get("JAMES_SYNTH_CONTEXT_CHARS")
        os.environ.pop("JAMES_SYNTH_CONTEXT_CHARS", None)

    def tearDown(self):
        os.environ.pop("JAMES_SYNTH_CONTEXT_CHARS", None)
        if self._saved is not None:
            os.environ["JAMES_SYNTH_CONTEXT_CHARS"] = self._saved

    def test_default_matches_the_synth_default(self):
        self.assertEqual(P.resolve_critique_context_chars(), 8000)
        src = (REPO_ROOT / "core" / "reasoning" / "engine_synth.py").read_text(
            encoding="utf-8")
        self.assertIn('os.environ.get("JAMES_SYNTH_CONTEXT_CHARS", "8000")', src)

    def test_budget_follows_the_synth_env_var(self):
        """Anti-drift: raising synth's window raises the critique's."""
        os.environ["JAMES_SYNTH_CONTEXT_CHARS"] = "12000"
        self.assertEqual(P.resolve_critique_context_chars(), 12000)
        long_ctx = "E" * 11000
        p = P.build_critique_prompt("Q?", DRAFT, long_ctx, is_ko=False)
        self.assertIn(long_ctx, p)

    def test_garbage_and_nonpositive_values_fall_back(self):
        for bad in ("", "  ", "abc", "0", "-5", "8.5"):
            os.environ["JAMES_SYNTH_CONTEXT_CHARS"] = bad
            self.assertEqual(P.resolve_critique_context_chars(), 8000, bad)

    def test_truncation_is_stated_not_silent(self):
        """Silent truncation is the trap: absent evidence would read as
        absent support."""
        os.environ["JAMES_SYNTH_CONTEXT_CHARS"] = "100"
        ko = P.build_critique_prompt("Q?", DRAFT, "E" * 500, is_ko=True)
        self.assertIn("생략됨", ko)
        self.assertIn("'자료 미근거' 라고 하지 마라", ko)
        en = P.build_critique_prompt("Q?", DRAFT, "E" * 500, is_ko=False)
        self.assertIn("evidence truncated", en)
        self.assertIn("do NOT call a claim unsupported", en)

    def test_no_notice_when_nothing_was_cut(self):
        os.environ["JAMES_SYNTH_CONTEXT_CHARS"] = "100"
        p = P.build_critique_prompt("Q?", DRAFT, "E" * 100, is_ko=False)
        self.assertNotIn("evidence truncated", p)


# ─── the loop threads it through ────────────────────────────────────


class ReflectPlumbingTests(unittest.TestCase):
    def setUp(self):
        os.environ["JAMES_ENABLE_REFLECT"] = "1"
        os.environ.pop("JAMES_DISABLE_COGNITIVE_STAGES", None)

    def tearDown(self):
        os.environ.pop("JAMES_ENABLE_REFLECT", None)

    def _first_prompt(self, **kwargs):
        from core.reasoning.reflect import ReflectionLoop
        fake = MagicMock()
        fake.complete.return_value = _completion(text="NO_ISSUES")
        with patch("core.reasoning.backends.get_backend", return_value=fake):
            ReflectionLoop().reflect("GPT-6 발표?", DRAFT, **kwargs)
        return fake.complete.call_args.args[0]

    def test_context_argument_reaches_the_backend_prompt(self):
        prompt = self._first_prompt(context=EVIDENCE)
        self.assertIn(EVIDENCE, prompt)
        self.assertIn("[근거 자료]", prompt)

    def test_without_context_the_call_still_works_and_withdraws_facts(self):
        prompt = self._first_prompt()
        self.assertNotIn("[근거 자료]", prompt)
        self.assertIn("사실 오류·환각 지적을 하지 마라", prompt)

    def test_context_is_keyword_only(self):
        """Positional would collide with `user_role` for old callers."""
        import inspect
        from core.reasoning.reflect import ReflectionLoop
        sig = inspect.signature(ReflectionLoop.reflect)
        self.assertEqual(sig.parameters["context"].kind,
                         inspect.Parameter.KEYWORD_ONLY)
        self.assertEqual(sig.parameters["context"].default, "")

    def test_evidence_does_not_change_backend_routing(self):
        """Routing still keys off the bare template, so this fix cannot
        move a query onto a different backend."""
        from core.reasoning.reflect import ReflectionLoop
        fake = MagicMock()
        fake.complete.return_value = _completion(text="NO_ISSUES")
        seen = []
        with patch("core.reasoning.backends.get_backend", return_value=fake), \
             patch("core.reasoning.router.resolve_backend",
                   side_effect=lambda stage, prompt, **kw: seen.append(prompt)
                   or "ollama_local"):
            ReflectionLoop().reflect("GPT-6 발표?", DRAFT, context=EVIDENCE)
            ReflectionLoop().reflect("GPT-6 발표?", DRAFT)
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[0], seen[1])
        self.assertNotIn(EVIDENCE, seen[0])


# ─── the call site ──────────────────────────────────────────────────


class CallSiteTests(unittest.TestCase):
    """reflect must receive the same evidence the verifier receives.

    Structural rather than textual: the point is that the two stages
    read the same variable, so nobody can rewire one and leave the
    other behind — which is exactly how this defect existed.
    """

    @classmethod
    def setUpClass(cls):
        src = (REPO_ROOT / "core" / "reasoning" / "pipeline_synth"
               / "generator.py").read_text(encoding="utf-8")
        cls.tree = ast.parse(src)

    def _call(self, attr):
        for node in ast.walk(self.tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == attr):
                return node
        self.fail(f"no .{attr}(...) call found in generator.py")

    def test_reflect_and_verify_read_the_same_evidence_variable(self):
        reflect_ctx = {k.arg: k.value for k in self._call("reflect").keywords}
        self.assertIn("context", reflect_ctx,
                      "reflect() is called without evidence again")
        self.assertIsInstance(reflect_ctx["context"], ast.Name)
        verify_args = self._call("verify").args
        self.assertGreaterEqual(len(verify_args), 3)
        self.assertIsInstance(verify_args[2], ast.Name)
        self.assertEqual(reflect_ctx["context"].id, verify_args[2].id)
        self.assertEqual(reflect_ctx["context"].id, "safe_context")


if __name__ == "__main__":
    unittest.main()
