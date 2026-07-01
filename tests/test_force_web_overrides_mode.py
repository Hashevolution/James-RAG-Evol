"""[Bug fix, 2026-05-09] force_web_search must override mode to retrieval.

User feedback:
> "내부 자료로 근거가 부족하여 답변이 추론으로만 나온 경우, 웹검색 추천이
>  뜬다. 그러나 웹검색을 누르면 '내가 원래한 질문'을 토대로 웹검색을 해서
>  추론한 답변을 줘야하는데, 자메스 스스로 내부자료 근거없이 답변한
>  내용을 토대로 검색을 하는 것 같다."

Bug
  The "🌐 웹으로 더 조사" chip (PR #132 #A8-6) sends
  force_web_search=True. But only run_retrieval_pipeline honors that
  flag — chat / meta / wiki_edit / etc. handlers silently drop it.

  When the user has chat mode selected (or QueryRouter routes to chat
  for casual queries), the force_web flag is ignored. handle_chat
  generates a new answer from memory_context (which carries prior
  turns, including the last inference-only answer) → output looks
  almost identical to the previous answer → user perceives "the
  search must be based on James's earlier answer". Reality: no web
  search ran at all.

Fix
  In engine.query, after mode is resolved (via mode_override or
  QueryRouter), if force_web_search is True force the mode to
  "retrieval" so run_retrieval_pipeline actually fires the search
  with the original user question.

  Existing test_force_web_chip.py still asserts the retrieval-pipeline
  parameter forwarding. This new test guards the engine-level
  override behavior so the chip's flag survives any mode routing.

Run:
    python -m unittest tests.test_force_web_overrides_mode
"""
from __future__ import annotations

import inspect
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class EngineModeOverrideTests(unittest.TestCase):
    """engine.query must reroute to retrieval when force_web_search=True."""

    @classmethod
    def setUpClass(cls):
        # The routing block (incl. the force_web override) moved to
        # engine_routing.py in the 2026-07-01 rule #5 split. Concatenate
        # routing BEFORE engine so the ordering assertions below keep
        # their meaning: routing (router → force_web override) runs
        # before the dispatch (`if mode == "chat":`) that stays in
        # engine._query_impl.
        import core.reasoning.engine as eng
        import core.reasoning.engine_routing as eng_routing
        cls.src = inspect.getsource(eng_routing) + "\n" + inspect.getsource(eng)

    def test_force_web_override_block_present(self):
        # Look for the explicit override snippet: when force_web_search
        # is truthy AND mode != "retrieval", reset mode to "retrieval".
        m = re.search(
            r'if\s+kwargs\.get\(\s*[\'"]force_web_search[\'"]\s*\)\s+and\s+mode\s*!=\s*[\'"]retrieval[\'"]',
            self.src,
        )
        self.assertIsNotNone(m,
            "engine.query must contain a guard that overrides mode "
            "to 'retrieval' when force_web_search is True")

    def test_override_happens_after_mode_resolution(self):
        # The override must run AFTER mode_override / QueryRouter so
        # it can rewrite the resolved mode, not before.
        router_idx = self.src.index("QueryRouter().route(")
        force_idx = self.src.index('kwargs.get("force_web_search"')
        self.assertLess(router_idx, force_idx,
            "force_web override must come AFTER QueryRouter — otherwise "
            "the router can re-route back to chat after the override")

    def test_override_happens_before_mode_dispatch(self):
        # And BEFORE the mode dispatch (if mode == "chat": return
        # handle_chat...) so the dispatch sees the corrected mode.
        force_idx = self.src.index('kwargs.get("force_web_search"')
        dispatch_idx = self.src.index('if mode == "chat":')
        self.assertLess(force_idx, dispatch_idx,
            "force_web override must come BEFORE mode dispatch so the "
            "corrected mode actually reaches the retrieval pipeline")

    def test_override_logs_the_reroute(self):
        # An operator-visible log line so the redirect is traceable.
        # Look for [ROUTER] tag near the force_web condition.
        idx = self.src.index('kwargs.get("force_web_search"')
        # Take a 500-char window
        body = self.src[idx:idx + 600]
        self.assertIn("[ROUTER]", body,
            "the override must log a [ROUTER] line so the operator can "
            "see in trace logs that the mode was reassigned")
        self.assertIn("retrieval", body)


class ContractWithExistingTests(unittest.TestCase):
    """Sanity: this fix doesn't break the existing
    test_force_web_chip.py contract (chip → flag → pipeline)."""

    def test_pipeline_still_receives_force_web_search(self):
        import core.reasoning.engine as eng
        src = inspect.getsource(eng)
        # The kwargs.get("force_web_search", False) forward to
        # run_retrieval_pipeline must remain.
        self.assertIn(
            'force_web_search=kwargs.get("force_web_search"',
            src,
            "run_retrieval_pipeline must still receive force_web_search",
        )


if __name__ == "__main__":
    unittest.main()
