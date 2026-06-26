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

    def test_brief_standard_resolve_to_natural(self):
        # brief / standard still collapse to NATURAL (v1 token-cut presets
        # not resurrected). "detailed" is now a real preset — see
        # test_detailed_resolves_to_detailed_preset.
        from core.response_style import resolve_style, NATURAL_PRESET
        for legacy in ("brief", "standard", "BRIEF", "Standard"):
            self.assertIs(resolve_style(legacy), NATURAL_PRESET,
                          f"legacy id {legacy!r} must resolve to NATURAL")

    def test_detailed_resolves_to_detailed_preset(self):
        # 2026-06-26: "detailed" now resolves to the real DETAILED_PRESET
        # (reproduce source detail) instead of NATURAL.
        from core.response_style import (
            resolve_style, DETAILED_PRESET, NATURAL_PRESET,
        )
        for v in ("detailed", "DETAILED", "  detailed  "):
            self.assertIs(resolve_style(v), DETAILED_PRESET,
                          f"{v!r} must resolve to DETAILED_PRESET")
        self.assertIsNot(DETAILED_PRESET, NATURAL_PRESET)
        self.assertEqual(DETAILED_PRESET.name, "detailed")

    def test_unknown_values_resolve_to_natural(self):
        from core.response_style import resolve_style, NATURAL_PRESET
        for val in ("verbose", "nonsense", "", "  "):
            self.assertIs(resolve_style(val), NATURAL_PRESET)

    def test_env_var_brief_and_unknown_still_natural(self):
        from core.response_style import resolve_style, NATURAL_PRESET
        for val in ("brief", "standard", "anything"):
            os.environ["JAMES_RESPONSE_STYLE"] = val
            self.assertIs(resolve_style(), NATURAL_PRESET,
                          f"env={val!r} must still return NATURAL")

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


class StyleOverrideTests(unittest.TestCase):
    """2026-06-04 — restore user/operator style override (v2 hardcode
    blocked it = platform defect). default stays NATURAL byte-identical;
    explicit/env 'terse' diverges to TERSE_PRESET."""

    def setUp(self):
        from core import response_style
        self.rs = response_style
        self._saved_env = os.environ.get("JAMES_RESPONSE_STYLE")
        os.environ.pop("JAMES_RESPONSE_STYLE", None)

    def tearDown(self):
        if self._saved_env is None:
            os.environ.pop("JAMES_RESPONSE_STYLE", None)
        else:
            os.environ["JAMES_RESPONSE_STYLE"] = self._saved_env

    def test_default_is_natural_byte_identical(self):
        # No explicit, no env → NATURAL (production unchanged).
        self.assertIs(self.rs.resolve_style(), self.rs.NATURAL_PRESET)
        self.assertIs(self.rs.resolve_style(""), self.rs.NATURAL_PRESET)
        self.assertIs(self.rs.resolve_style(None or ""), self.rs.NATURAL_PRESET)

    def test_explicit_terse_resolves_terse(self):
        self.assertIs(self.rs.resolve_style("terse"), self.rs.TERSE_PRESET)
        self.assertIs(self.rs.resolve_style("TERSE"), self.rs.TERSE_PRESET)
        self.assertIs(self.rs.resolve_style(" terse "), self.rs.TERSE_PRESET)

    def test_env_terse_resolves_terse(self):
        os.environ["JAMES_RESPONSE_STYLE"] = "terse"
        self.assertIs(self.rs.resolve_style(), self.rs.TERSE_PRESET)

    def test_explicit_overrides_env(self):
        os.environ["JAMES_RESPONSE_STYLE"] = "natural"
        # explicit terse wins over env natural
        self.assertIs(self.rs.resolve_style("terse"), self.rs.TERSE_PRESET)

    def test_brief_standard_still_natural(self):
        # brief/standard NOT resurrected (no token-cut) → NATURAL.
        # "detailed" is a real preset now (2026-06-26).
        for s in ("brief", "standard"):
            self.assertIs(self.rs.resolve_style(s), self.rs.NATURAL_PRESET)
        self.assertIs(self.rs.resolve_style("detailed"), self.rs.DETAILED_PRESET)

    def test_unknown_falls_back_to_natural(self):
        self.assertIs(self.rs.resolve_style("nonsense-style"), self.rs.NATURAL_PRESET)

    def test_terse_preset_rule_text_v4_structural_only(self):
        # v4 (cycle β #2, 2026-06-06) — TERSE rule_text drops the
        # *quantitative* caps that v3 kept ("MAXIMUM 60 words" /
        # "1-2 short evidence sentences") after a user catch:
        # those quantitative gates are the same measurement-fitting
        # pattern v2 was just rolled back for. The fixture scorer
        # hits on entity match regardless of length, so any
        # quantitative cap clamps the very answer the rule asks for.
        #
        # v4 keeps only the *structural* contract:
        #   - First line: ANSWER: <answer>           (lead)
        #   - Then a brief grounded explanation if helpful  (free form)
        #   - Avoid multi-paragraph synthesis, ## headers, bullet
        #     lists, preamble before ANSWER:         (structural bans)
        # No word count, no sentence count.
        for rt in (self.rs.TERSE_PRESET.rule_text_ko, self.rs.TERSE_PRESET.rule_text_en):
            self.assertIn("ANSWER:", rt)
            self.assertNotIn("Reason freely", rt,
                             "v4 must not regress to v1 license phrase")
            self.assertNotIn("EXACTLY one line", rt,
                             "v4 must not regress to v2 single-line clamp")
            self.assertNotIn("no follow-up sentences", rt,
                             "v4 must not regress to v2 sentence ban")
        # v4 specifically drops quantitative caps from v3
        self.assertNotIn("MAXIMUM 60 words", self.rs.TERSE_PRESET.rule_text_en,
                         "v4 must drop the v3 word-count cap")
        self.assertNotIn("최대 60단어", self.rs.TERSE_PRESET.rule_text_ko,
                         "v4 must drop the v3 word-count cap (KO)")
        self.assertNotIn("1-2", self.rs.TERSE_PRESET.rule_text_en,
                         "v4 must drop the v3 sentence-count cap")
        # Structural bans must still be present (these are what
        # actually stop the synthesis regression)
        self.assertIn("First line", self.rs.TERSE_PRESET.rule_text_en)
        self.assertIn("Avoid", self.rs.TERSE_PRESET.rule_text_en)
        for ban in ("## headers", "bullet lists", "multi-paragraph"):
            self.assertIn(ban, self.rs.TERSE_PRESET.rule_text_en,
                          f"structural ban '{ban}' must stay")
        self.assertIn("첫 줄", self.rs.TERSE_PRESET.rule_text_ko)
        for ban in ("## 헤더", "불릿 리스트", "다단락"):
            self.assertIn(ban, self.rs.TERSE_PRESET.rule_text_ko,
                          f"structural ban '{ban}' must stay (KO)")

    def test_terse_preset_keeps_max_tokens_at_natural_parity(self):
        # v2 — TERSE keeps max_tokens=8192 (NATURAL parity). An initial
        # Phase B draft capped it at 150 (~75-90 words) to hard-enforce
        # the 30-word rule at decoding, but the PM-19 e4b length analysis
        # showed legitimate "short reasoning + ANSWER: insufficient
        # information" answers run 200-430 chars (~60-100 words) and
        # would be cut mid-conclusion under a 150-token cap, losing the
        # ANSWER: line itself. rule_text v2 stays strict as a prompt-side
        # instruction; the decoding ceiling stays generous so the model
        # is never forced to truncate the conclusion the rule just asked
        # it to write.
        self.assertEqual(self.rs.TERSE_PRESET.max_tokens, 8192,
                         "TERSE max_tokens must stay at 8192 (no hard truncation)")
        self.assertEqual(self.rs.NATURAL_PRESET.max_tokens, 8192,
                         "NATURAL must keep 8192 (production byte-identical)")


class AnswerFormatContractTests(unittest.TestCase):
    """2026-06-04 — the StylePreset is the single source of truth for the
    *whole* answer shape across all forcing layers. NATURAL keeps every
    layer ON (byte-identical); TERSE collapses them.

    2026-06-06 cycle β Phase A: L1b (MemoryStore persona name prefix
    "당신의 이름은 JAMES입니다.") added as a separately-gated layer
    after the persona-leak diagnostic measured 68-69% answer leak rate
    on terse-mode runs — character_directives blocked the 16-trait
    block but the persona name prefix lived on a separate path and
    survived the 2026-06-04 fix."""

    def test_natural_keeps_all_layers_on(self):
        from core.response_style import NATURAL_PRESET
        self.assertTrue(NATURAL_PRESET.inject_character_directives,
                        "NATURAL must keep L1 character injection (default)")
        self.assertTrue(NATURAL_PRESET.inject_persona,
                        "NATURAL must keep L1b persona name prefix (default)")
        self.assertTrue(NATURAL_PRESET.inject_sources_header,
                        "NATURAL must keep L3 sources header (default)")

    def test_terse_collapses_all_layers(self):
        from core.response_style import TERSE_PRESET
        self.assertFalse(TERSE_PRESET.inject_character_directives,
                         "TERSE must suppress L1 character persona")
        self.assertFalse(TERSE_PRESET.inject_persona,
                         "TERSE must suppress L1b MemoryStore persona name")
        self.assertFalse(TERSE_PRESET.inject_sources_header,
                         "TERSE must suppress L3 sources header")

    def test_l1_callsite_gates_on_contract(self):
        # build_memory_context must read the resolved style's
        # inject_character_directives flag (not inject unconditionally).
        import core.reasoning.engine_memory as em
        import inspect
        src = inspect.getsource(em.build_memory_context)
        self.assertIn("inject_character_directives", src)
        self.assertIn("response_style", src,
                      "L1 must receive response_style to resolve the style")

    def test_l1b_callsite_gates_on_contract(self):
        # build_memory_context must read the resolved style's
        # inject_persona flag and skip MemoryStore.get_system_prompt()
        # when False (cycle β Phase B, 2026-06-06).
        import core.reasoning.engine_memory as em
        import inspect
        src = inspect.getsource(em.build_memory_context)
        self.assertIn("inject_persona", src,
                      "L1b must gate on the resolved style's inject_persona flag")

    def test_l3_callsite_gates_on_contract(self):
        # apply_post_check_and_sources_header must read the resolved
        # style's inject_sources_header flag.
        import core.reasoning.pipeline_context as pc
        import inspect
        src = inspect.getsource(pc.apply_post_check_and_sources_header)
        self.assertIn("inject_sources_header", src)
        self.assertIn("response_style", src,
                      "L3 must receive response_style to resolve the style")


class PersonaInjectionBehaviorTests(unittest.TestCase):
    """2026-06-06 cycle β Phase B — behavioral guarantee that L1b gate
    actually suppresses the MemoryStore persona name in terse mode while
    keeping NATURAL byte-identical.

    Phase A diagnostic evidence: under the prior code, terse-mode
    English MultiHop-RAG answers leaked 'As JAMES, I have analyzed' /
    'Hello, I am JAMES' prefixes at 68-69% — directly traced to the
    hardcoded 'L3: 당신의 이름은 JAMES입니다.' line in the final
    system_prompt that survived the inject_character_directives gate.
    """

    def _build(self, response_style: str) -> str:
        from core.reasoning.engine_memory import build_memory_context

        class _Stub:
            def _log(self, *a, **kw): pass

        # English query → exercises the persona-name path without the
        # Korean lang_directive being stripped by the regex sweep.
        _, system_prompt, _ = build_memory_context(
            _Stub(),
            safe_query="What was the FTX trial verdict?",
            user_role="admin",
            kwargs={"session_id": f"test-persona-{response_style or 'default'}"},
            response_style=response_style,
        )
        return system_prompt

    def test_terse_strips_persona_name_prefix(self):
        sp = self._build("terse")
        # The exact hardcoded prefix the Phase A diagnostic identified
        # as the dominant leak source. Must be absent under terse.
        self.assertNotIn("당신의 이름은", sp,
                         "terse mode must not inject MemoryStore persona name")
        self.assertNotIn("JAMES입니다", sp,
                         "terse mode must not leak the JAMES introduction")
        # Lang directive may still appear (separately gated) — that's
        # the next investigation, not this one.

    def test_natural_keeps_persona_name_prefix(self):
        sp = self._build("")  # default → NATURAL
        # Production byte-identical: the persona name prefix is the
        # MemoryStore-default `당신의 이름은 <name>입니다.` line.
        self.assertIn("당신의 이름은", sp,
                      "NATURAL must preserve the production persona name path")


if __name__ == "__main__":
    unittest.main()
