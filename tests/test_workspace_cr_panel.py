"""[PR-CR-C, 2026-05-12] Workspace Change Request panel.

Step C of the v0.2.x CR cycle. The backend ships in PR-CR-B1+B2;
this PR adds the UI in ``frontend/workspace.html`` +
``frontend/static/workspace.js`` so an operator can review CRs in a
browser instead of curling the endpoints.

Scope of this contract test:

  HTML — the new "변경 요청" tab is wired into the existing
  three-tab nav, the list table has the right columns, the detail
  panel and propose form carry every id the JS reads, and every
  action button has an inline ``onclick`` handler (the workspace
  page hasn't graduated to ``data-action`` delegation yet — §5 PR-B
  handles that sweep separately).

  JS — workspace.js declares the seven CR functions the UI calls
  (``reloadCrs`` / ``openCr`` / ``closeCrDetail`` /
  ``toggleCrPropose`` / ``submitCrPropose`` / ``submitCrApprove`` /
  ``submitCrReject`` / ``submitCrComment``), they call the six
  ``/admin/cr/...`` endpoints, ``selectTab`` knows about the
  ``cr`` tab, and the detail renderer respects the admin-only gate
  on approve / reject.

  i18n — every ``data-i18n`` key the new markup uses is declared
  in both ``en`` and ``ko`` blocks of i18n.js so a fresh user with
  the default locale doesn't see ``workspace.cr_xxx`` literals.

Run:
    python -m unittest tests.test_workspace_cr_panel
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_HTML = ROOT / "frontend" / "workspace.html"
WORKSPACE_JS   = ROOT / "frontend" / "static" / "workspace.js"
I18N_JS        = ROOT / "frontend" / "static" / "i18n.js"


# ─── HTML — tab nav + structural ids ─────────────────────────────
class HtmlTabAndPanelTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.html = WORKSPACE_HTML.read_text(encoding="utf-8")

    def test_cr_nav_item_present(self):
        # 4th nav-item with data-tab="cr" + data-action="select-tab"
        # so workspace.js's _bindFrontendEvents click delegate
        # routes the tab change (§5 PR-B migrated workspace.html to
        # the data-action pattern; CR-C adheres to that contract).
        self.assertRegex(
            self.html,
            r'<div\s+class="nav-item"\s+data-tab="cr"[^>]*data-action="select-tab"',
            "CR tab must be wired via data-action='select-tab' "
            "(workspace.html graduated to delegation in §5 PR-B)",
        )

    def test_cr_panel_section_present(self):
        self.assertIn('id="tab-cr"', self.html,
            "CR tab content section must exist with id='tab-cr'")
        # Starts hidden — selectTab toggles it visible.
        # [2026-08-26] The inline `style="display:none"` became the
        # `d-none` utility class when inline styles were extracted;
        # tokens.css declares `.d-none{display:none}`. Same behaviour,
        # different spelling.
        self.assertRegex(
            self.html,
            r'<div[^>]*class="[^"]*\bd-none\b[^"]*"[^>]*id="tab-cr"',
            "CR tab section must start hidden",
        )

    def test_filter_controls_present(self):
        for control_id in (
            "cr-filter-status",
            "cr-filter-target",
            "cr-counter",
            "cr-propose-toggle",
        ):
            with self.subTest(id=control_id):
                self.assertIn(f'id="{control_id}"', self.html)

    def test_list_table_columns(self):
        # tbody + 5-column header so JS innerHTML can stamp <tr> with
        # 5 <td>s without a column-count mismatch.
        self.assertIn('id="cr-body"', self.html)
        for col_key in (
            "workspace.cr_col_status", "workspace.cr_col_target",
            "workspace.cr_col_title",  "workspace.cr_col_proposer",
            "workspace.cr_col_created",
        ):
            with self.subTest(col=col_key):
                self.assertIn(col_key, self.html)

    def test_detail_panel_ids_present(self):
        # Every id the JS detail renderer writes into.
        for elem_id in (
            "cr-detail-panel",
            "cr-detail-status-badge", "cr-detail-title",
            "cr-detail-id", "cr-detail-target", "cr-detail-proposer",
            "cr-detail-created",
            "cr-detail-merged-row",    "cr-detail-merged",
            "cr-detail-reject-row",    "cr-detail-reject",
            "cr-detail-description",   "cr-detail-diff",
            "cr-detail-reviews",
            "cr-comment-body",
            "cr-approve-btn", "cr-reject-btn",
            "cr-detail-msg",
        ):
            with self.subTest(id=elem_id):
                self.assertIn(f'id="{elem_id}"', self.html,
                    f"detail panel must have id={elem_id} for the JS "
                    "renderer to populate")

    def test_propose_form_ids_present(self):
        for elem_id in (
            "cr-propose-form",
            "cr-form-target-type", "cr-form-target-id",
            "cr-form-title", "cr-form-description",
            "cr-form-base-hash", "cr-form-body",
            "cr-propose-msg",
        ):
            with self.subTest(id=elem_id):
                self.assertIn(f'id="{elem_id}"', self.html)

    def test_action_buttons_wired_to_handlers(self):
        # workspace.html graduated to data-action delegation in §5
        # PR-B, so every CR action surfaces as a data-action="cr-*"
        # attribute. The matching switch arms live in workspace.js
        # _bindFrontendEvents and route to the named JS function.
        for action in (
            "cr-submit-propose",  "cr-cancel-propose",
            "cr-submit-approve",  "cr-submit-reject",
            "cr-submit-comment",  "cr-toggle-propose",
            "cr-close-detail",    "cr-reload",
        ):
            with self.subTest(action=action):
                self.assertIn(
                    f'data-action="{action}"', self.html,
                    f"workspace.html must carry data-action={action!r} "
                    "for the click delegate to find",
                )


# ─── JS — selectTab knows about cr; CR functions exist ───────────
class JsContractTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.js = WORKSPACE_JS.read_text(encoding="utf-8")

    def test_select_tab_handles_cr(self):
        # selectTab('cr') must (1) include 'tab-cr' in the visibility
        # rotation and (2) call reloadCrs.
        idx = self.js.index("function selectTab(")
        body = self.js[idx:idx + 1200]
        self.assertIn("'tab-cr'", body,
            "selectTab must include 'tab-cr' in the panel rotation")
        self.assertIn("reloadCrs", body,
            "selectTab must call reloadCrs when tab='cr'")

    def test_top_level_cr_functions_defined(self):
        for fn in (
            "async function reloadCrs",
            "async function openCr",
            "function closeCrDetail",
            "function toggleCrPropose",
            "function cancelCrPropose",
            "async function submitCrPropose",
            "async function submitCrApprove",
            "async function submitCrReject",
            "async function submitCrComment",
        ):
            with self.subTest(fn=fn):
                self.assertIn(fn, self.js, f"workspace.js must declare {fn}")

    def test_propose_payload_shape(self):
        # The body POSTed to /admin/cr/ must include target_type,
        # target_id, title, description, proposed_diff, base_hash,
        # labels — the FastAPI route signature requires every field.
        idx = self.js.index("async function submitCrPropose")
        body = self.js[idx:idx + 2000]
        for field in (
            "target_type", "target_id", "title", "description",
            "proposed_diff", "base_hash", "labels",
        ):
            with self.subTest(field=field):
                self.assertIn(field, body,
                    f"submitCrPropose must build a body with {field}")

    def test_propose_diff_is_replace_op(self):
        # v0.2.x apply path supports only ``{"op":"replace","body":..}``
        # — submitting anything else trips the apply layer's check.
        idx = self.js.index("async function submitCrPropose")
        body = self.js[idx:idx + 2000]
        self.assertIn("'replace'", body,
            "submitCrPropose must build the 'replace' op diff for v0.2.x")

    def test_render_detail_gates_admin_actions(self):
        # The approve / reject buttons must be visible only when the
        # caller is admin AND the CR is open. Anything looser is a
        # privilege regression.
        idx = self.js.index("function _renderCrDetail(")
        body = self.js[idx:idx + 4000]
        self.assertIn("_isAdmin()", body,
            "_renderCrDetail must consult _isAdmin() before showing approve/reject")
        self.assertIn("'open'", body,
            "_renderCrDetail must compare cr.status to 'open' before "
            "exposing approve/reject")

    def test_uses_existing_apifetch_for_reads(self):
        # GET path → existing _apiFetch (auth + clean error 401 →
        # showLogin). Hand-rolled fetches for reads would skip that.
        for fn in (
            "async function reloadCrs",
            "async function openCr",
        ):
            with self.subTest(fn=fn):
                idx = self.js.index(fn)
                body = self.js[idx:idx + 1500]
                self.assertIn("_apiFetch", body,
                    f"{fn} must reuse _apiFetch for the GET")

    def test_post_helper_handles_401(self):
        # _crPost must clear stored token and reopen the login modal
        # on 401, same posture as _apiFetch.
        idx = self.js.index("async function _crPost(")
        body = self.js[idx:idx + 1500]
        self.assertIn("_clearStored()", body)
        self.assertIn("showLogin()", body)


# ─── i18n — every new key declared in both en and ko ─────────────
class I18nKeysTests(unittest.TestCase):

    _NEW_KEYS = (
        "workspace.tab_cr",
        "workspace.cr_title",
        "workspace.cr_scope_admin",
        "workspace.cr_hint",
        "workspace.cr_status_all",
        "workspace.cr_status_open",
        "workspace.cr_status_merged",
        "workspace.cr_status_rejected",
        "workspace.cr_status_superseded",
        "workspace.cr_target_all",
        "workspace.cr_target_wiki",
        "workspace.cr_target_jobs",
        "workspace.cr_new",
        "workspace.cr_submit",
        "workspace.cr_form_target_type",
        "workspace.cr_form_target_id",
        "workspace.cr_form_target_id_ph",
        "workspace.cr_form_title",
        "workspace.cr_form_title_ph",
        "workspace.cr_form_description",
        "workspace.cr_form_description_ph",
        "workspace.cr_form_base_hash",
        "workspace.cr_form_body",
        "workspace.cr_form_body_ph",
        "workspace.cr_empty",
        "workspace.cr_no_reviews",
        "workspace.cr_col_status",
        "workspace.cr_col_target",
        "workspace.cr_col_title",
        "workspace.cr_col_proposer",
        "workspace.cr_col_created",
        "workspace.cr_detail_target",
        "workspace.cr_detail_proposer",
        "workspace.cr_detail_created",
        "workspace.cr_detail_merged",
        "workspace.cr_detail_reject_reason",
        "workspace.cr_detail_description",
        "workspace.cr_detail_diff",
        "workspace.cr_detail_reviews",
        "workspace.cr_comment_ph",
        "workspace.cr_comment_submit",
        "workspace.cr_reject",
        "workspace.cr_approve",
    )

    @classmethod
    def setUpClass(cls):
        cls.i18n = I18N_JS.read_text(encoding="utf-8")

    def _key_count(self, key: str) -> int:
        # Each key should appear at least twice — once in the en
        # block and once in the ko block. Match the dict-literal
        # form ``'key':`` so substring collisions don't confuse us.
        return len(re.findall(
            r"'" + re.escape(key) + r"'\s*:", self.i18n,
        ))

    def test_every_new_key_present_in_both_locales(self):
        for key in self._NEW_KEYS:
            with self.subTest(key=key):
                count = self._key_count(key)
                self.assertGreaterEqual(
                    count, 2,
                    f"i18n key {key!r} declared {count}× — needs entries "
                    "in BOTH the en and ko maps",
                )


if __name__ == "__main__":
    unittest.main()
