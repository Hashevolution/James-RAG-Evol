"""workspace 추론-편집 — load/draft/apply endpoints + modal wiring.

Backend functional (no app boot — endpoints called directly with the
audited primitives mocked): exercises the real source/draft/apply logic
including the optimistic-lock 409 conflict check that prevents two
operators from clobbering each other.

Frontend source-level: launcher + modal markup + chat.js-style wiring
(the project pattern for UI plumbing).

Run:
  python -m unittest tests.test_wiki_edit_ui
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config  # noqa: E402,F401 — load .env before routes.* → core.auth

ROOT = Path(__file__).resolve().parent.parent


class HelperTests(unittest.TestCase):
    def test_entity_hash_deterministic_and_distinct(self):
        from routes.wiki_edit_ui import _entity_hash
        self.assertEqual(_entity_hash("abc"), _entity_hash("abc"))
        self.assertNotEqual(_entity_hash("abc"), _entity_hash("abd"))
        self.assertEqual(len(_entity_hash("x")), 64)

    def test_draft_prompt_includes_instruction_and_selection(self):
        from routes.wiki_edit_ui import _draft_prompt
        p = _draft_prompt("CUR", "지시문", "선택부분")
        for needle in ("CUR", "지시문", "선택부분", "수정된 전체"):
            self.assertIn(needle, p)

    def test_draft_prompt_omits_focus_without_selection(self):
        from routes.wiki_edit_ui import _draft_prompt
        self.assertNotIn("선택한 부분", _draft_prompt("CUR", "지시문", ""))


class _Base(unittest.TestCase):
    def setUp(self):
        import routes.wiki_edit_ui as m
        self.m = m
        self._patches = [
            mock.patch.object(m, "_require_feature", lambda *a, **k: None),
            mock.patch.object(m, "_write_audit", lambda *a, **k: None),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()


class SourceTests(_Base):
    def test_found_returns_body_and_hash(self):
        from routes.wiki_edit_ui import _entity_hash
        with mock.patch("tools.wiki.wiki_editor.read_entity",
                        return_value=(True, "본문내용", "ok")):
            res = asyncio.run(self.m.edit_source(
                name="비트코인", api_key="k", role="admin"))
        self.assertTrue(res["found"])
        self.assertEqual(res["body"], "본문내용")
        self.assertEqual(res["base_hash"], _entity_hash("본문내용"))

    def test_not_found(self):
        with mock.patch("tools.wiki.wiki_editor.read_entity",
                        return_value=(False, "", "없음")):
            res = asyncio.run(self.m.edit_source(
                name="x", api_key="k", role="admin"))
        self.assertFalse(res["found"])
        self.assertEqual(res["base_hash"], "")


class DraftTests(_Base):
    def _req(self, **kw):
        from routes.wiki_edit_ui import _DraftRequest
        base = dict(api_key="k", name="비트코인", instruction="갱신해줘",
                    selected_text="")
        base.update(kw)
        return _DraftRequest(**base)

    def test_happy_path(self):
        from routes.wiki_edit_ui import _entity_hash
        fake = mock.Mock(); fake.tag = "gemma3:12b"
        with mock.patch("tools.wiki.wiki_editor.read_entity",
                        return_value=(True, "CUR", "")), \
             mock.patch("core.model_resolver.resolve_for_mode",
                        return_value=fake), \
             mock.patch("core.reasoning.trace_helpers.trace_synth_call",
                        return_value="NEW BODY"):
            res = asyncio.run(self.m.edit_draft(self._req(), role="admin"))
        self.assertEqual(res["draft_body"], "NEW BODY")
        self.assertEqual(res["base_hash"], _entity_hash("CUR"))
        self.assertEqual(res["model"], "gemma3:12b")

    def test_empty_instruction_400(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(self.m.edit_draft(self._req(instruction="  "),
                                          role="admin"))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_entity_missing_404(self):
        from fastapi import HTTPException
        with mock.patch("tools.wiki.wiki_editor.read_entity",
                        return_value=(False, "", "없음")):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(self.m.edit_draft(self._req(), role="admin"))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_empty_llm_response_502(self):
        from fastapi import HTTPException
        fake = mock.Mock(); fake.tag = "gemma3:12b"
        with mock.patch("tools.wiki.wiki_editor.read_entity",
                        return_value=(True, "CUR", "")), \
             mock.patch("core.model_resolver.resolve_for_mode",
                        return_value=fake), \
             mock.patch("core.reasoning.trace_helpers.trace_synth_call",
                        return_value="   "):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(self.m.edit_draft(self._req(), role="admin"))
        self.assertEqual(ctx.exception.status_code, 502)


class ApplyTests(_Base):
    def _req(self, **kw):
        from routes.wiki_edit_ui import _ApplyRequest, _entity_hash
        base = dict(api_key="k", name="비트코인", new_body="새 본문",
                    base_hash=_entity_hash("CUR"))
        base.update(kw)
        return _ApplyRequest(**base)

    def test_happy_path_applies(self):
        with mock.patch("tools.wiki.wiki_editor.read_entity",
                        return_value=(True, "CUR", "")), \
             mock.patch("tools.wiki.wiki_editor.update_entity",
                        return_value=(True, "✅ 수정 완료")) as upd:
            res = asyncio.run(self.m.edit_apply(self._req(), role="admin"))
        self.assertTrue(res["applied"])
        upd.assert_called_once()

    def test_conflict_409_when_hash_shifted(self):
        from fastapi import HTTPException
        # current is "CHANGED" but the request's base_hash is for "CUR".
        with mock.patch("tools.wiki.wiki_editor.read_entity",
                        return_value=(True, "CHANGED", "")), \
             mock.patch("tools.wiki.wiki_editor.update_entity") as upd:
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(self.m.edit_apply(self._req(), role="admin"))
        self.assertEqual(ctx.exception.status_code, 409)
        upd.assert_not_called()   # must NOT write on conflict

    def test_empty_body_400(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(self.m.edit_apply(self._req(new_body="  "),
                                          role="admin"))
        self.assertEqual(ctx.exception.status_code, 400)


class FrontendWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "frontend" / "workspace.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "frontend" / "static" / "workspace.js").read_text(encoding="utf-8")

    def test_launcher_and_modal_present(self):
        self.assertIn('data-action="wiki-edit-open"', self.html)
        self.assertIn('id="wiki-edit-modal"', self.html)
        for el in ("we-name", "we-body", "we-instruction", "we-draft",
                   "we-apply-btn"):
            self.assertIn(f'id="{el}"', self.html)

    def test_actions_wired(self):
        for act in ("wiki-edit-open", "wiki-edit-load", "wiki-edit-draft",
                    "wiki-edit-apply", "wiki-edit-close"):
            self.assertIn(f"case '{act}'", self.js)

    def test_draft_posts_to_endpoint_with_selection(self):
        idx = self.js.index("async function wikiEditDraft")
        body = self.js[idx:idx + 900]
        self.assertIn("/admin/wiki/edit/draft", body)
        self.assertIn("selected_text", body)
        self.assertIn("_weCaptureSelection", self.js)

    def test_apply_passes_base_hash(self):
        idx = self.js.index("async function wikiEditApply")
        body = self.js[idx:idx + 800]
        self.assertIn("/admin/wiki/edit/apply", body)
        self.assertIn("base_hash", body)

    def test_admin_gated_launcher(self):
        idx = self.js.index("function openWikiEdit")
        self.assertIn("_isAdmin()", self.js[idx:idx + 200])


if __name__ == "__main__":
    unittest.main()
