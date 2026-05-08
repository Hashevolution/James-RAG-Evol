"""Chat-side wiki save chip (item #A8-7, 2026-05-09).

User feedback: "웹 검색 자료 제시한 답변과 자료에 대해서는 해당
대화창에서 장기 기억 자료화 위키 엔티티 추출 하여 데이터베이스화
여부를 사용자에게 물어보고 수행할수 있도록 로직과 ui 만들기".

Flow:
  1. Pipeline always creates a web_longterm_save proposal when web
     search succeeds (#A6-3 had a 2+ search gate; #A8-7 drops it).
  2. Pipeline returns pending_save_proposal_id in result dict.
  3. Server forwards to QueryResponse and /query/ response body.
  4. Chat bubble renders "📥 위키 저장" chip when:
       web_used == true  AND  pending_save_proposal_id  AND  role==admin
  5. Click → confirm dialog → POST /admin/proposals/{id}/approve →
     toast + chip flips to "✓ 저장됨".

Run:
  python -m unittest tests.test_chat_wiki_save
"""
from __future__ import annotations

import inspect
import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent


class PipelineProposalAlwaysCreatedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from core.reasoning import pipeline
        cls.src = inspect.getsource(pipeline)

    def test_pending_save_proposal_id_in_outer_scope(self):
        # Like web_results, pending_save_proposal_id must be initialized
        # before the try: block so it survives early-fail paths.
        try_idx  = self.src.index("\n    try:\n        sys_prefix = ")
        init_idx = self.src.index('pending_save_proposal_id: str = ""')
        self.assertLess(init_idx, try_idx,
            "pending_save_proposal_id must be initialised BEFORE try:")

    def test_proposal_no_longer_gated_on_search_count(self):
        # The old gate `should_promote_to_longterm(safe_query) or
        # is_save_command(safe_query)` is replaced by always_propose=True.
        # The marker variable + the `if always_propose:` branch must be
        # present so chat-side chip can save even on first search.
        self.assertIn("always_propose", self.src,
            "must use always_propose marker to drop the search-count gate")
        self.assertIn("if always_propose:", self.src,
            "branch condition must be `if always_propose:`")

    def test_proposal_id_captured_after_save(self):
        idx = self.src.index("save_proposal(p)")
        body = self.src[idx:idx + 400]
        self.assertIn("pending_save_proposal_id = p['proposal_id']", body,
            "must capture proposal id immediately after save_proposal")

    def test_return_dict_includes_field(self):
        return_idx = self.src.rindex("return {")
        body = self.src[return_idx:return_idx + 1500]
        self.assertIn('"pending_save_proposal_id"', body,
            "return dict must include pending_save_proposal_id")


class ResponseShapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server_llmwiki as srv
        cls.src = inspect.getsource(srv)

    def test_response_model_has_field(self):
        m = re.search(
            r"class QueryResponse\(BaseModel\):(.+?)class\s+\w+\(",
            self.src, re.DOTALL,
        )
        self.assertIsNotNone(m)
        body = m.group(1)
        self.assertIn("pending_save_proposal_id", body,
            "QueryResponse must declare pending_save_proposal_id")
        self.assertIn('pending_save_proposal_id: str = ""', body,
            "field default must be empty string")

    def test_query_handler_propagates_field(self):
        idx = self.src.index('@app.post("/query/"')
        end = self.src.index('@app.', idx + 10)
        body = self.src[idx:end]
        self.assertIn('"pending_save_proposal_id"', body,
            "/query/ handler must include the field in response")
        self.assertIn('result.get("pending_save_proposal_id"', body,
            "must read from pipeline result dict")


class FrontendChipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "frontend" / "static" / "chat.js").read_text(encoding="utf-8")

    def test_chip_rendered_when_web_used_and_admin(self):
        idx = self.js.index("function appendJamesMsg")
        m = re.search(r"\nfunction\s+\w+\s*\(", self.js[idx + 1:])
        end = idx + 1 + m.start() if m else idx + 12000
        body = self.js[idx:end]
        self.assertIn("save-wiki-btn", body,
            "chip class missing")
        self.assertIn("data.web_used", body)
        self.assertIn("pending_save_proposal_id", body,
            "must inspect pending_save_proposal_id")
        self.assertIn("userRole === 'admin'", body,
            "chip must be admin-only (server also rejects non-admin)")
        self.assertIn("approveWikiSave(this)", body,
            "chip onclick must call approveWikiSave")
        self.assertIn("data-proposal-id", body,
            "chip must carry proposal id via data attr")
        self.assertIn("${saveWikiChip}", body,
            "saveWikiChip must be interpolated into bubble HTML")

    def test_approve_helper_exists_and_calls_endpoint(self):
        self.assertIn("async function approveWikiSave", self.js)
        idx = self.js.index("async function approveWikiSave")
        body = self.js[idx:idx + 2500]
        self.assertIn("dataset.proposalId", body,
            "must read proposal id from data attr")
        self.assertIn("/admin/proposals/", body,
            "must POST to admin proposal approve endpoint")
        self.assertIn("/approve", body)
        self.assertIn("confirm(", body,
            "must confirm before saving (destructive — adds to wiki)")
        # Toast on success/failure
        self.assertIn("toast(", body)


if __name__ == "__main__":
    unittest.main()
