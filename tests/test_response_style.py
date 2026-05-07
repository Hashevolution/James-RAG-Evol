"""Response-style preset resolver and call-site contracts.

Coverage:
  - `resolve_style()`: explicit kwarg → env var → `standard` default
    precedence. Unknown values fall through rather than raising.
  - Each preset's max_tokens + force_two_sections fields match the
    documented contract (brief=600/no-split, standard=1200/two-section,
    detailed=2000/two-section).
  - Source-level contract: every LLM call site in core/reasoning/
    derives max_tokens from `resolve_style(...)` rather than hard-
    coding 2000 — a future refactor that re-introduces the literal
    fails the contract test and a reviewer makes a conscious choice.

Run:
  python -m unittest tests.test_response_style
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ResolveStyleTests(unittest.TestCase):
    def setUp(self):
        self._orig_env = os.environ.get("JAMES_RESPONSE_STYLE")

    def tearDown(self):
        if self._orig_env is None:
            os.environ.pop("JAMES_RESPONSE_STYLE", None)
        else:
            os.environ["JAMES_RESPONSE_STYLE"] = self._orig_env

    def test_default_is_standard(self):
        from core.response_style import resolve_style, STANDARD
        os.environ.pop("JAMES_RESPONSE_STYLE", None)
        s = resolve_style()
        self.assertEqual(s.name, STANDARD)
        self.assertEqual(s.max_tokens, 1200)
        self.assertTrue(s.force_two_sections)

    def test_explicit_brief(self):
        from core.response_style import resolve_style, BRIEF
        s = resolve_style("brief")
        self.assertEqual(s.name, BRIEF)
        self.assertEqual(s.max_tokens, 600)
        self.assertFalse(s.force_two_sections,
                         "brief must NOT force the 📚/💡 two-section split")

    def test_explicit_detailed(self):
        from core.response_style import resolve_style, DETAILED
        s = resolve_style("detailed")
        self.assertEqual(s.name, DETAILED)
        self.assertEqual(s.max_tokens, 2000,
                         "detailed preserves the pre-this-PR 2000-token cap")
        self.assertTrue(s.force_two_sections)

    def test_explicit_kwarg_beats_env(self):
        from core.response_style import resolve_style, BRIEF
        os.environ["JAMES_RESPONSE_STYLE"] = "detailed"
        s = resolve_style("brief")
        self.assertEqual(s.name, BRIEF,
                         "explicit kwarg must override env var")

    def test_env_var_used_when_no_explicit(self):
        from core.response_style import resolve_style, BRIEF
        os.environ["JAMES_RESPONSE_STYLE"] = "brief"
        s = resolve_style()
        self.assertEqual(s.name, BRIEF)
        s = resolve_style("")
        self.assertEqual(s.name, BRIEF, "empty string treated as no explicit")

    def test_env_var_case_insensitive(self):
        from core.response_style import resolve_style, BRIEF
        for val in ("BRIEF", "Brief", "  brief  "):
            os.environ["JAMES_RESPONSE_STYLE"] = val
            s = resolve_style()
            self.assertEqual(s.name, BRIEF, f"env value {val!r} should resolve")

    def test_unknown_falls_through_to_default(self):
        from core.response_style import resolve_style, STANDARD
        os.environ.pop("JAMES_RESPONSE_STYLE", None)
        # Unknown explicit AND no env → standard. Defensive: a typo in
        # API call must not raise — this matches the rest of the
        # reasoning pipeline's behavior.
        s = resolve_style("verbose")
        self.assertEqual(s.name, STANDARD)
        s = resolve_style("nonsense-value")
        self.assertEqual(s.name, STANDARD)

    def test_unknown_explicit_falls_to_env_not_default(self):
        from core.response_style import resolve_style, BRIEF
        os.environ["JAMES_RESPONSE_STYLE"] = "brief"
        # Unknown explicit but valid env → env wins (not default).
        s = resolve_style("nonsense")
        self.assertEqual(s.name, BRIEF,
                         "unknown explicit must fall through to env, not skip it")

    def test_rule_text_brief_has_no_emoji_split(self):
        from core.response_style import resolve_style
        s = resolve_style("brief")
        self.assertNotIn("📚", s.rule_text_ko)
        self.assertNotIn("💡", s.rule_text_ko)
        self.assertNotIn("📚", s.rule_text_en)
        self.assertNotIn("💡", s.rule_text_en)

    def test_rule_text_standard_keeps_split_but_compact(self):
        from core.response_style import resolve_style
        s = resolve_style("standard")
        self.assertIn("📚", s.rule_text_ko)
        self.assertIn("💡", s.rule_text_ko)
        # Standard rule text is shorter than detailed — the user-visible
        # difference between them is conciseness.
        s_detailed = resolve_style("detailed")
        self.assertLess(len(s.rule_text_ko), len(s_detailed.rule_text_ko),
                        "standard rule text must be shorter than detailed")


class CallSiteContractTests(unittest.TestCase):
    """Source-level: every LLM call site in core/reasoning/ must derive
    max_tokens from resolve_style — no hard-coded 2000 literal allowed.
    A future refactor that re-introduces 2000 will fail here and a
    reviewer will make a conscious choice."""

    def test_engine_generate_answer_uses_style(self):
        import core.reasoning.engine as eng
        import inspect
        src = inspect.getsource(eng._generate_answer if hasattr(eng, "_generate_answer")
                                else eng.ReasoningEngine._generate_answer)
        self.assertIn("resolve_style", src,
                      "_generate_answer must call resolve_style")
        self.assertIn("style.max_tokens", src,
                      "_generate_answer must use style.max_tokens, not literal")
        self.assertNotIn("max_tokens=2000", src,
                         "literal max_tokens=2000 must be removed from _generate_answer")

    def test_modes_handle_chat_uses_style(self):
        import core.reasoning.modes as modes_mod
        import inspect
        src = inspect.getsource(modes_mod.handle_chat)
        self.assertIn("resolve_style", src,
                      "handle_chat must call resolve_style")
        self.assertIn("style.max_tokens", src,
                      "handle_chat must use style.max_tokens, not literal")
        self.assertNotIn("max_tokens=2000", src,
                         "literal max_tokens=2000 must be removed from handle_chat")

    def test_pipeline_uses_style_for_web_fallback(self):
        import core.reasoning.pipeline as pipeline_mod
        import inspect
        src = inspect.getsource(pipeline_mod.run_retrieval_pipeline)
        self.assertIn("resolve_style", src,
                      "pipeline must call resolve_style for web fallback")
        # Both call_gemma sites in pipeline (web fallback + retry) must
        # use style.max_tokens, not 2000. We accept any style variable
        # name (`_style.max_tokens` / `_style_retry.max_tokens` etc).
        self.assertNotIn("max_tokens=2000", src,
                         "literal max_tokens=2000 must be removed from pipeline")

    def test_query_endpoint_passes_response_style(self):
        import server_llmwiki as srv
        import inspect
        src = inspect.getsource(srv)
        self.assertIn("response_style", src,
                      "/query/ must accept and forward response_style")
        self.assertIn("response_style:   str", src,
                      "QueryRequest must declare response_style field")
        self.assertIn("response_style   = data.response_style", src,
                      "/query/ must forward data.response_style to rag_engine.query")


if __name__ == "__main__":
    unittest.main()
