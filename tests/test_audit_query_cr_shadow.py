"""Stage B / CR-E.4 — unified audit query (legacy JSONL + CR-shadow).

Verifies `tools.patch.audit_query.query_patch_audit` correctly merges
projected CR-shadow rows (self_evo_patch + self_evo_proposal) with
legacy JSONL rows when ``include_shadow=True``. The projection map
(_CR_STATUS_TO_EVENT / _CR_STATUS_TO_OUTCOME) is pinned here so a
schema drift on either side fails this file rather than silently
producing a malformed audit feed.

Invariants pinned:

1. ``include_shadow=False`` (default) → byte-identical to the
   pre-CR-E read path. Legacy callers see no change.
2. ``include_shadow=True`` merges CR rows with legacy JSONL rows
   before the sort + limit.
3. Projected rows carry ``_source='cr_shadow'`` + ``_cr_id`` +
   ``_target_type`` so UIs can distinguish.
4. CR status → event mapping: open=APPROVED, merged=DEPLOYED,
   rejected=ROLLED_BACK.
5. CR status → outcome mapping: open=None, merged=deployed,
   rejected=rolled_back.
6. The since / approver / outcome filters apply uniformly to both
   legacy rows AND CR-shadow rows.
7. ``cr_db_path`` test seam works — the projection reads from the
   supplied path, not the production CR DB.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.change_request as cr_mod
from core.change_request import (
    TARGET_SELF_EVO_PATCH, TARGET_SELF_EVO_PROPOSAL,
    create_cr, reject_cr,
)
from core.change_request_apply import merge_cr
from tools.patch.audit_query import (
    _CR_STATUS_TO_EVENT,
    _CR_STATUS_TO_OUTCOME,
    _cr_row_to_audit_entry,
    query_patch_audit,
)


def _write_log(path: Path, entries: list) -> None:
    with path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


class ProjectionMapTests(unittest.TestCase):
    """Pin the CR status → JSONL event/outcome mapping."""

    def test_event_map_covers_all_status_values(self):
        self.assertEqual(_CR_STATUS_TO_EVENT["open"], "APPROVED")
        self.assertEqual(_CR_STATUS_TO_EVENT["merged"], "DEPLOYED")
        self.assertEqual(_CR_STATUS_TO_EVENT["rejected"], "ROLLED_BACK")

    def test_outcome_map_aligns_with_legacy_jsonl(self):
        self.assertIsNone(_CR_STATUS_TO_OUTCOME["open"])
        self.assertEqual(_CR_STATUS_TO_OUTCOME["merged"], "deployed")
        self.assertEqual(_CR_STATUS_TO_OUTCOME["rejected"], "rolled_back")


class _CrShadowFixture(unittest.TestCase):
    """Each test gets a fresh empty CR DB on a tempfile."""

    def setUp(self):
        self._tmp_cr = tempfile.NamedTemporaryFile(
            suffix=".db", delete=False,
        )
        self._tmp_cr.close()
        cr_mod.init_db(self._tmp_cr.name)
        self._saved_default = cr_mod._DEFAULT_DB
        cr_mod._DEFAULT_DB = self._tmp_cr.name

        self._tmp_log = tempfile.NamedTemporaryFile(
            suffix=".jsonl", delete=False, mode="w", encoding="utf-8",
        )
        self._tmp_log.close()

    def tearDown(self):
        cr_mod._DEFAULT_DB = self._saved_default
        for p in (self._tmp_cr.name, self._tmp_log.name):
            try:
                os.unlink(p)
            except OSError:
                pass


class CrRowProjectionTests(_CrShadowFixture):
    def test_open_status_projects_to_approved_event(self):
        cr = create_cr(
            target_type=TARGET_SELF_EVO_PATCH, target_id="p-open-1",
            title="patch:p-open-1", proposed_diff={}, base_hash="h",
            proposer="alice", role="admin",
            db_path=self._tmp_cr.name,
        )
        entry = _cr_row_to_audit_entry(cr)
        self.assertEqual(entry["event"], "APPROVED")
        self.assertIsNone(entry["outcome"])
        self.assertEqual(entry["patch_id"], "p-open-1")
        self.assertEqual(entry["approver_username"], "alice")
        self.assertEqual(entry["_source"], "cr_shadow")
        self.assertEqual(entry["_target_type"], TARGET_SELF_EVO_PATCH)
        self.assertEqual(entry["approver_role"], "from_cr_shadow")
        self.assertEqual(entry["approval_method"], "shadow_cr")

    def test_merged_status_projects_to_deployed(self):
        cr = create_cr(
            target_type=TARGET_SELF_EVO_PATCH, target_id="p-merged-1",
            title="t", proposed_diff={}, base_hash="h",
            proposer="alice", db_path=self._tmp_cr.name,
        )
        merged = merge_cr(cr.cr_id, approver="bob")
        entry = _cr_row_to_audit_entry(merged)
        self.assertEqual(entry["event"], "DEPLOYED")
        self.assertEqual(entry["outcome"], "deployed")
        self.assertEqual(entry["approver_username"], "bob")  # merged_by wins

    def test_rejected_status_projects_to_rolled_back(self):
        cr = create_cr(
            target_type=TARGET_SELF_EVO_PROPOSAL, target_id="prop-rej-1",
            title="t", proposed_diff={}, base_hash="h",
            proposer="alice", db_path=self._tmp_cr.name,
        )
        rejected = reject_cr(cr.cr_id, reviewer="carol",
                             reason="bench_regression: outcome=rolled_back: …")
        entry = _cr_row_to_audit_entry(rejected)
        self.assertEqual(entry["event"], "ROLLED_BACK")
        self.assertEqual(entry["outcome"], "rolled_back")
        self.assertIn("bench_regression", entry["detail"])
        self.assertEqual(entry["_target_type"], TARGET_SELF_EVO_PROPOSAL)


class IncludeShadowToggleTests(_CrShadowFixture):
    def test_include_shadow_false_is_byte_identical_to_legacy(self):
        # 2 legacy lines
        _write_log(Path(self._tmp_log.name), [
            {"time": "2026-05-08T09:00:00", "event": "APPROVED",
             "patch_id": "p1", "approver_username": "alice"},
            {"time": "2026-05-08T09:01:00", "event": "DEPLOYED",
             "patch_id": "p1", "outcome": "deployed"},
        ])
        # 1 CR shadow row (must not appear)
        create_cr(
            target_type=TARGET_SELF_EVO_PATCH, target_id="p-shadow",
            title="t", proposed_diff={}, base_hash="h",
            proposer="alice", db_path=self._tmp_cr.name,
        )
        rows = query_patch_audit(
            log_path=self._tmp_log.name,
            include_shadow=False,
        )
        self.assertEqual(len(rows), 2)
        self.assertTrue(all("_source" not in r for r in rows))

    def test_include_shadow_true_merges_cr_rows(self):
        _write_log(Path(self._tmp_log.name), [
            {"time": "2026-05-08T09:00:00", "event": "APPROVED",
             "patch_id": "p1", "approver_username": "alice"},
        ])
        create_cr(
            target_type=TARGET_SELF_EVO_PATCH, target_id="p-shadow",
            title="t", proposed_diff={}, base_hash="h",
            proposer="alice", db_path=self._tmp_cr.name,
        )
        rows = query_patch_audit(
            log_path=self._tmp_log.name,
            include_shadow=True,
            cr_db_path=self._tmp_cr.name,
        )
        # 1 legacy + 1 shadow
        self.assertEqual(len(rows), 2)
        sources = [r.get("_source") for r in rows]
        self.assertIn("cr_shadow", sources)
        self.assertIn(None, sources)

    def test_filters_apply_uniformly_to_legacy_and_shadow(self):
        _write_log(Path(self._tmp_log.name), [
            {"time": "2026-05-08T09:00:00", "event": "APPROVED",
             "patch_id": "p1", "approver_username": "alice"},
            {"time": "2026-05-08T10:00:00", "event": "DEPLOYED",
             "patch_id": "p1", "approver_username": "alice",
             "outcome": "deployed"},
        ])
        # Two shadow rows.
        #   - cr_a: proposer=bob, merged_by=alice → projection
        #           approver_username=alice (merged_by wins) → caught by filter
        #   - cr_b: proposer=bob, status=open    → projection
        #           approver_username=bob (proposer) → excluded by filter
        # merge_cr enforces approver != proposer (invariant #7), so the
        # cross-user pair is the natural shape for testing the filter.
        cr_a = create_cr(
            target_type=TARGET_SELF_EVO_PATCH, target_id="p-shadow-a",
            title="t", proposed_diff={}, base_hash="h",
            proposer="bob", db_path=self._tmp_cr.name,
        )
        merge_cr(cr_a.cr_id, approver="alice")
        create_cr(
            target_type=TARGET_SELF_EVO_PATCH, target_id="p-shadow-b",
            title="t", proposed_diff={}, base_hash="h",
            proposer="bob", db_path=self._tmp_cr.name,
        )
        # approver="alice" filter must catch both legacy AND the
        # merged-by-alice shadow, while excluding bob's open shadow.
        rows = query_patch_audit(
            approver="alice",
            log_path=self._tmp_log.name,
            include_shadow=True,
            cr_db_path=self._tmp_cr.name,
        )
        approver_set = {r.get("approver_username") for r in rows}
        self.assertEqual(approver_set, {"alice"},
                         f"approver filter should constrain both sources; got {rows}")
        # Sanity — expect exactly 3: 2 legacy alice rows + 1 alice-merged shadow.
        self.assertEqual(len(rows), 3, f"unexpected row count: {rows}")

    def test_no_shadow_rows_in_empty_cr_db(self):
        # Pre-CR-E feed — legacy lines only, CR DB never written to.
        _write_log(Path(self._tmp_log.name), [
            {"time": "2026-05-08T09:00:00", "event": "APPROVED",
             "patch_id": "p1", "approver_username": "alice"},
        ])
        rows = query_patch_audit(
            log_path=self._tmp_log.name,
            include_shadow=True,
            cr_db_path=self._tmp_cr.name,
        )
        self.assertEqual(len(rows), 1)
        self.assertNotIn("_source", rows[0])


if __name__ == "__main__":
    unittest.main()
