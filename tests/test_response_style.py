"""Response-style — natural-flow answer prompt.

v2 redesign (2026-05-08): the v1 brief/standard/detailed presets
were rejected by user feedback ("글자수를 짧게 하기 위해 자르는게
아니고 문단을 나눠서 핵심 답변, 근거, 대안제시"). v2 collapses to
one NATURAL_PRESET that teaches a Claude-style flow without rigid
emoji-section template; max_tokens stays generous and the model
picks length from the prompt.

Coverage:
  - All public ids (brief / standard / detailed) and explicit "" /
    None / unknown values resolve to NATURAL_PRESET (one preset only).
  - NATURAL preset properties: max_tokens=2000, force_two_sections
    is False (legacy field — kept for API compat), rule_text mentions
    the 핵심/근거/대안 flow and explicitly forbids 📚/💡 labels.
  - Source-level contracts:
      * engine._generate_answer / modes.handle_chat / pipeline web
        fallback all derive max_tokens from resolve_style (no literal).
      * No call site retains the literal "📚 자료 기반" or "💡 추론"
        as a forced template (v1 had these baked in; v2 must not).

Run:
  python -m unittest tests.test_response_style
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class NaturalFlowResolverTests(unittest.TestCase):
    def setUp(self):
        self._orig_env = os.environ.get("JAMES_RESPONSE_STYLE")

    def tearDown(self):
        if self._orig_env is None:
            os.environ.pop("JAMES_RESPONSE_STYLE", None)
        else:
            os.environ["JAMES_RESPONSE_STYLE"] = self._orig_env

    def test_default_resolves_to_natural(self):
        from core.response_style import resolve_style, NATURAL_PRESET
        os.environ.pop("JAMES_RESPONSE_STYLE", None)
        self.assertIs(resolve_style(), NATURAL_PRESET)

    def test_all_legacy_ids_resolve_to_natural(self):
        from core.response_style import resolve_style, NATURAL_PRESET
        for legacy in ("brief", "standard", "detailed",
                       "BRIEF", "Standard", "  detailed  "):
            self.assertIs(resolve_style(legacy), NATURAL_PRESET,
                          f"legacy id {legacy!r} must resolve to NATURAL")

    def test_unknown_values_resolve_to_natural(self):
        from core.response_style import resolve_style, NATURAL_PRESET
        for val in ("verbose", "nonsense", "", "  "):
            self.assertIs(resolve_style(val), NATURAL_PRESET)

    def test_env_var_does_not_change_outcome_in_v2(self):
        from core.response_style import resolve_style, NATURAL_PRESET
        for val in ("brief", "detailed", "anything"):
            os.environ["JAMES_RESPONSE_STYLE"] = val
            self.assertIs(resolve_style(), NATURAL_PRESET,
                          f"env={val!r} must still return NATURAL in v2")

    def test_natural_preset_properties(self):
        from core.response_style import NATURAL_PRESET
        self.assertEqual(NATURAL_PRESET.name, "natural")
        # [#A8-5 2026-05-09] 2000 → 8192 — 사용자 요청 "글자수 잘림 방지".
        self.assertGreaterEqual(NATURAL_PRESET.max_tokens, 4096,
                                "v3+: max_tokens must be ≥ 4096 to avoid "
                                "truncating multi-section report answers")
        self.assertFalse(NATURAL_PRESET.force_two_sections,
                         "v2 must NOT force the rigid 📚/💡 template")

    def test_rule_text_teaches_flow_not_rigid_template(self):
        from core.response_style import NATURAL_PRESET
        ko = NATURAL_PRESET.rule_text_ko
        en = NATURAL_PRESET.rule_text_en
        # Core flow elements (v2 baseline)
        self.assertIn("핵심 답", ko)
        self.assertIn("근거", ko)
        self.assertIn("Direct answer", en)
        self.assertIn("evidence", en.lower())
        # Explicit ban on the v1 emoji template
        self.assertIn("📚", ko, "rule must mention the forbidden label so it's clear what NOT to use")
        self.assertIn("📚", en)
        # Explicit "no character-count limit" — user said 글자수 상관없다
        self.assertIn("글자수 제약 없음", ko)
        self.assertIn("character-count limit", en)

    def test_rule_text_v3_intent_verify_and_next_actions(self):
        # v3 (item #2 user feedback): intent verification step (for
        # accuracy) + next-actions block (numbered options the user
        # can pick) must be present in the prose guide.
        from core.response_style import NATURAL_PRESET
        ko = NATURAL_PRESET.rule_text_ko
        en = NATURAL_PRESET.rule_text_en
        # KO — intent check phrase
        self.assertIn("의도 확인", ko,
                      "v3: intent verification must be in the rule")
        self.assertIn("정확성", ko,
                      "v3: intent check rationale must mention 정확성 — "
                      "user said the purpose is accuracy, not tone")
        # KO — next-actions block
        self.assertIn("다음 작업", ko,
                      "v3: closing 'next actions' block must be in the rule")
        self.assertIn("(1)", ko,
                      "v3: numbered options example must show (1)..(2)..(3) form")
        # EN — same elements
        self.assertIn("Intent check", en)
        self.assertIn("accuracy", en.lower())
        self.assertIn("Next actions", en)
        self.assertIn("(1)", en)


class CallSiteContractTests(unittest.TestCase):
    """Source-level: every LLM call site in core/reasoning/ derives
    max_tokens from resolve_style. No literal `max_tokens=2000` and
    no literal forced "📚 자료 기반" / "💡 추론" label injection
    survives in v2."""

    def test_engine_uses_resolve_style(self):
        # Post engine split (chore PR): _generate_answer is a thin
        # delegator; the actual prompt assembly + LLM call lives in
        # core/reasoning/engine_synth.generate_rag_answer.
        import core.reasoning.engine_synth as engsynth
        import inspect
        src = inspect.getsource(engsynth.generate_rag_answer)
        self.assertIn("resolve_style", src)
        self.assertIn("style.max_tokens", src)
        self.assertNotIn("max_tokens=2000", src)

    def test_modes_handle_chat_uses_style_and_flow(self):
        import core.reasoning.modes as modes_mod
        import inspect
        src = inspect.getsource(modes_mod.handle_chat)
        self.assertIn("resolve_style", src)
        self.assertIn("style.max_tokens", src)
        self.assertNotIn("max_tokens=2000", src)
        # Flow guide injected into the chat prompt — pre-v2 chat had no rule.
        self.assertIn("rule_txt", src,
                      "handle_chat must inject the natural-flow rule_text "
                      "into the prompt (pre-v2 it didn't)")

    def test_pipeline_uses_style(self):
        from tests._pipeline_src import pipeline_source
        src = pipeline_source()
        self.assertIn("resolve_style", src)
        self.assertNotIn("max_tokens=2000", src)
        # No retry-path forced "📚 자료 기반: 관련 내부 자료 없음" prefix.
        # The v1 retry concatenated this string verbatim into the answer
        # — v2 lets the model phrase it naturally.
        self.assertNotIn(
            '"📚 자료 기반: 관련 내부 자료 없음\\n💡 추론: " + retry',
            src,
            "v2 must not force the 📚/💡 template into the retry path",
        )


class ChatParagraphPreservationTests(unittest.TestCase):
    """User feedback explicitly said 문단을 나눠서. The pre-v2
    handle_chat post-processed `\\n\\n` → space, killing paragraph
    breaks. v2 must preserve them."""

    def test_handle_chat_preserves_paragraph_breaks(self):
        import core.reasoning.modes as modes_mod
        import inspect
        src = inspect.getsource(modes_mod.handle_chat)
        # The v1 regex `r'\n{2,}'` → ' ' must be gone.
        self.assertNotIn(r"r'\n{2,}'", src,
                         "v1 paragraph-collapse regex must be removed")
        self.assertNotIn(r'r"\n{2,}"', src)
        # v2 collapses 3+ newlines to exactly 2 — preserves \n\n.
        self.assertIn(r'r"\n{3,}"', src,
                      "v2 must collapse 3+ newlines to 2, preserving paragraphs")


if __name__ == "__main__":
    unittest.main()
