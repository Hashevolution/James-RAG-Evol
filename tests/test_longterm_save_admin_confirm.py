"""Web → wiki long-term save admin confirm flow (item #A6-3, 2026-05-08).

User feedback (c part 2): "메모리 장기화하여 자료화로 만들 때에는
어드민에게 선택 할 수 있도록 할 것".

Before: pipeline.py auto-saved to wiki when search_count ≥ 2 OR user
said "저장해줘" — operator had no idea external content was being
indexed into their knowledge base.

After: pipeline creates a proposal with type "web_longterm_save" via
_make_proposal + save_proposal. Admin sees it in /admin/proposals/
(existing UI handles it — buttons + executor dispatch). On approve
EvoExecutor._execute_web_longterm_save calls the original
save_as_longterm + KnowledgeTracker boost. On reject, only short-
term knowledge boost stays (already applied above the gate).

Run:
  python -m unittest tests.test_longterm_save_admin_confirm
"""
from __future__ import annotations

import inspect
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent


class PipelineProposalCreationTests(unittest.TestCase):
    """pipeline.py creates a proposal instead of auto-saving."""

    @classmethod
    def setUpClass(cls):
        from core.reasoning import pipeline
        cls.src = inspect.getsource(pipeline)

    def _proposal_block(self) -> str:
        # [#A8-7 update 2026-05-09] Locator changed: gate moved from
        # `should_promote_to_longterm(safe_query) or is_save_command(...)`
        # to a simpler `if always_propose:` branch (always create the
        # proposal so the chat-side save chip can offer it on first
        # search too). Anchor on always_propose now.
        idx = self.src.index("always_propose")
        return self.src[idx:idx + 3000]

    def test_no_direct_save_as_longterm_call(self):
        # The promotion branch must not call save_as_longterm directly
        # — it must persist a proposal for admin (or chat-side) confirm.
        block = self._proposal_block()
        self.assertIn("_make_proposal", block,
            "promotion branch must create a proposal (admin confirm)")
        self.assertIn("save_proposal", block,
            "must persist the proposal via save_proposal")
        self.assertNotIn("save_as_longterm(safe_query, web_results, summary",
            block,
            "promotion branch must not auto-save anymore — admin gate required")

    def test_proposal_type_is_web_longterm_save(self):
        block = self._proposal_block()
        self.assertIn('"web_longterm_save"', block,
            'proposal type must be "web_longterm_save" (registered with executor)')

    def test_proposal_metadata_carries_query_summary_results_role(self):
        block = self._proposal_block()
        for field in ('"query"', '"summary"', '"web_results"', '"user_role"'):
            self.assertIn(field, block,
                f"proposal metadata must include {field} so executor can save")

    def test_short_term_signals_unchanged(self):
        # Short-term update_knowledge_level (single search) and
        # record_search counter must still fire — they're applied above
        # the promotion gate in the same try block.
        # Just check those calls still exist in the file.
        self.assertIn("update_knowledge_level(safe_query, is_longterm=False)",
                      self.src,
            "short-term knowledge level boost must remain (proposal flow only "
            "gates the LONG-term promotion)")
        self.assertIn("record_search(safe_query)", self.src)


class ExecutorHandlesNewTypeTests(unittest.TestCase):
    """EvoExecutor.execute dispatches web_longterm_save."""

    @classmethod
    def setUpClass(cls):
        from tools.self import evo_analyzer
        cls.evo = evo_analyzer
        cls.src = inspect.getsource(evo_analyzer)

    def test_risk_level_registered(self):
        self.assertIn('"web_longterm_save":', self.src,
            "RISK_LEVELS must register web_longterm_save")

    def test_executor_dispatches_new_type(self):
        # Look for the dispatch chain in EvoExecutor.execute().
        idx = self.src.index("class EvoExecutor")
        end = self.src.index("def _execute_wiki_add", idx)
        body = self.src[idx:end]
        self.assertIn('prop_type == "web_longterm_save"', body,
            "execute() must dispatch web_longterm_save proposals")
        self.assertIn("self._execute_web_longterm_save", body,
            "must call the dedicated handler method")

    def test_handler_method_present(self):
        self.assertIn("def _execute_web_longterm_save", self.src,
            "_execute_web_longterm_save method missing")

    def test_handler_validates_metadata(self):
        idx = self.src.index("def _execute_web_longterm_save")
        end = self.src.index("def _execute_wiki_add", idx)
        body = self.src[idx:end]
        # Must check for required metadata fields and return failure
        # gracefully if missing.
        self.assertIn('"query"', body)
        self.assertIn('"summary"', body)
        self.assertIn('"web_results"', body)
        self.assertIn("metadata 누락", body,
            "must produce a clear error when metadata is incomplete")

    def test_handler_calls_save_as_longterm(self):
        idx = self.src.index("def _execute_web_longterm_save")
        end = self.src.index("def _execute_wiki_add", idx)
        body = self.src[idx:end]
        self.assertIn("save_as_longterm(", body,
            "approved proposal must call save_as_longterm to actually save")
        self.assertIn("update_knowledge_level", body,
            "approved save must trigger long-term knowledge boost (+5)")


class ExecutorIntegrationTests(unittest.TestCase):
    """End-to-end via EvoExecutor.execute with a fake proposal."""

    @classmethod
    def setUpClass(cls):
        from tools.self.evo_analyzer import EvoExecutor
        cls.executor = EvoExecutor()

    def _fake_proposal(self, **meta):
        return {
            "proposal_id": "test_proposal_001",
            "type":        "web_longterm_save",
            "title":       "test",
            "description": "test",
            "content":     "test",
            "metadata":    meta,
            "status":      "pending",
        }

    def test_missing_metadata_returns_failure(self):
        proposal = self._fake_proposal(query="", summary="", web_results=[])
        result = self.executor.execute(proposal)
        self.assertFalse(result["success"])
        self.assertIn("metadata", result["message"])

    def test_save_path_invoked_with_complete_metadata(self):
        # Mock save_as_longterm to confirm the executor calls it with
        # the right args.
        proposal = self._fake_proposal(
            query="블랙록 IBIT 운용 자산",
            summary="블랙록 IBIT는 ...",
            web_results=[{"url": "https://example.com", "title": "IBIT"}],
            user_role="admin",
        )
        with patch("tools.web.web_searcher.save_as_longterm",
                   return_value="/wiki/web_blackrock.md") as mock_save, \
             patch("tools.web.web_searcher.update_knowledge_level"):
            result = self.executor.execute(proposal)
        self.assertTrue(result["success"],
            f"approved save should succeed: {result.get('message')}")
        self.assertTrue(mock_save.called,
            "save_as_longterm must be invoked")
        # Args verification — query, results, summary, role.
        args, _ = mock_save.call_args
        self.assertEqual(args[0], "블랙록 IBIT 운용 자산")
        self.assertEqual(args[2], "블랙록 IBIT는 ...")
        self.assertEqual(args[3], "admin")


if __name__ == "__main__":
    unittest.main()
