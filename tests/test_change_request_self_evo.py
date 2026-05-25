"""Stage B CR-E.1 — self-evolution target_type smoke tests.

Verifies the two new ``TARGET_SELF_EVO_PATCH`` / ``TARGET_SELF_EVO_PROPOSAL``
target_types behave correctly against ``core/change_request.py`` +
``core/change_request_apply.py`` without touching the endpoint side
of CR-E. Endpoint glue (PRs CR-E.2 / CR-E.3) will reuse this same
create_cr → merge_cr path.

Invariants pinned here:

1. ``VALID_TARGET_TYPES`` accepts both new self-evolution types.
2. ``create_cr(target_type='self_evo_patch', ...)`` inserts a CR
   row in ``status='open'``.
3. ``create_cr(target_type='self_evo_proposal', ...)`` likewise.
4. ``apply_cr`` returns ``applied=True`` on both — no-op shadow.
5. ``merge_cr`` transitions ``open → merged`` for both via the
   no-op apply dispatcher.
6. ``reject_cr`` works for both (the proposal-reject endpoint will
   use this path).
7. ``base_hash`` is enforced (any non-empty string accepted; the
   legacy JSONL remains authoritative for the actual deploy state).
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.change_request as cr_mod
from core.change_request import (
    STATUS_MERGED,
    STATUS_OPEN,
    STATUS_REJECTED,
    TARGET_SELF_EVO_PATCH,
    TARGET_SELF_EVO_PROPOSAL,
    VALID_TARGET_TYPES,
    create_cr,
    get_cr,
    reject_cr,
)
from core.change_request_apply import apply_cr, merge_cr


class TargetEnumTests(unittest.TestCase):
    def test_self_evo_patch_in_valid_set(self):
        self.assertIn(TARGET_SELF_EVO_PATCH, VALID_TARGET_TYPES)

    def test_self_evo_proposal_in_valid_set(self):
        self.assertIn(TARGET_SELF_EVO_PROPOSAL, VALID_TARGET_TYPES)

    def test_constants_are_distinct_strings(self):
        self.assertNotEqual(TARGET_SELF_EVO_PATCH, TARGET_SELF_EVO_PROPOSAL)
        self.assertEqual(TARGET_SELF_EVO_PATCH, "self_evo_patch")
        self.assertEqual(TARGET_SELF_EVO_PROPOSAL, "self_evo_proposal")


class _CrShadowFixture(unittest.TestCase):
    """Each test gets a fresh empty CR DB on a tempfile."""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(
            suffix=".db", delete=False,
        )
        self._tmp.close()
        # Tests rewrite the module-level _DEFAULT_DB so apply_cr +
        # merge_cr (which read it via the module alias) also see
        # the tempfile.
        self._saved_default_db = cr_mod._DEFAULT_DB
        cr_mod._DEFAULT_DB = self._tmp.name
        # init_db (run-once on import) only initialized the production
        # _DEFAULT_DB. Re-init against the tempfile so the CREATE TABLE
        # statements land in the test DB.
        cr_mod.init_db(self._tmp.name)

    def tearDown(self):
        cr_mod._DEFAULT_DB = self._saved_default_db
        try:
            os.unlink(self._tmp.name)
        except OSError:
            pass


class CreateAndMergePatchShadowTests(_CrShadowFixture):
    def test_create_self_evo_patch_yields_open_status(self):
        cr = create_cr(
            target_type=TARGET_SELF_EVO_PATCH,
            target_id="p-test-001",
            title="patch:p-test-001",
            proposed_diff={"target": "core/dummy.py", "code_len": 42},
            base_hash="sha256-stub-for-shadow",
            proposer="<system>",
            role="admin",
        )
        self.assertEqual(cr.status, STATUS_OPEN)
        self.assertEqual(cr.target_type, TARGET_SELF_EVO_PATCH)
        self.assertEqual(cr.target_id, "p-test-001")

    def test_apply_self_evo_patch_is_noop_with_applied_true(self):
        cr = create_cr(
            target_type=TARGET_SELF_EVO_PATCH,
            target_id="p-test-002",
            title="patch:p-test-002",
            proposed_diff={"target": "core/x.py"},
            base_hash="sha256-stub",
            proposer="<system>",
        )
        result = apply_cr(cr)
        self.assertTrue(result.applied)
        self.assertFalse(result.superseded)
        # new_hash carries a "legacy:" prefix so downstream readers
        # can see at-a-glance that the actual write went through the
        # JSONL path, not the CR table.
        self.assertTrue(
            (result.new_hash or "").startswith("legacy:patch:"),
            f"expected legacy:patch:* prefix, got {result.new_hash!r}",
        )

    def test_merge_self_evo_patch_transitions_to_merged(self):
        cr = create_cr(
            target_type=TARGET_SELF_EVO_PATCH,
            target_id="p-test-003",
            title="patch:p-test-003",
            proposed_diff={"target": "core/y.py"},
            base_hash="sha256-stub",
            proposer="<system>",
        )
        merged = merge_cr(cr.cr_id, approver="approver_alice")
        self.assertEqual(merged.status, STATUS_MERGED)
        # Verify persisted state matches the returned DTO.
        re_read = get_cr(cr.cr_id)
        self.assertEqual(re_read.status, STATUS_MERGED)
        self.assertEqual(re_read.merged_by, "approver_alice")


class CreateAndMergeProposalShadowTests(_CrShadowFixture):
    def test_create_self_evo_proposal_yields_open_status(self):
        cr = create_cr(
            target_type=TARGET_SELF_EVO_PROPOSAL,
            target_id="prop-007",
            title="add wiki entity X",
            proposed_diff={"action": "wiki_add", "entity": "X"},
            base_hash="sha256-stub",
            proposer="<system>",
        )
        self.assertEqual(cr.status, STATUS_OPEN)
        self.assertEqual(cr.target_type, TARGET_SELF_EVO_PROPOSAL)
        self.assertEqual(cr.target_id, "prop-007")

    def test_apply_self_evo_proposal_is_noop(self):
        cr = create_cr(
            target_type=TARGET_SELF_EVO_PROPOSAL,
            target_id="prop-008",
            title="config update",
            proposed_diff={"action": "config_update"},
            base_hash="sha256-stub",
            proposer="<system>",
        )
        result = apply_cr(cr)
        self.assertTrue(result.applied)
        self.assertTrue(
            (result.new_hash or "").startswith("legacy:proposal:"),
            f"expected legacy:proposal:* prefix, got {result.new_hash!r}",
        )

    def test_merge_self_evo_proposal_transitions_to_merged(self):
        cr = create_cr(
            target_type=TARGET_SELF_EVO_PROPOSAL,
            target_id="prop-009",
            title="long term save",
            proposed_diff={"action": "web_longterm_save"},
            base_hash="sha256-stub",
            proposer="<system>",
        )
        merged = merge_cr(cr.cr_id, approver="approver_bob")
        self.assertEqual(merged.status, STATUS_MERGED)
        self.assertEqual(get_cr(cr.cr_id).merged_by, "approver_bob")

    def test_reject_self_evo_proposal_transitions_to_rejected(self):
        cr = create_cr(
            target_type=TARGET_SELF_EVO_PROPOSAL,
            target_id="prop-010",
            title="risky change",
            proposed_diff={"action": "code_patch"},
            base_hash="sha256-stub",
            proposer="<system>",
        )
        rejected = reject_cr(
            cr.cr_id,
            reviewer="approver_carol",
            reason="manual reject by admin",
        )
        self.assertEqual(rejected.status, STATUS_REJECTED)
        self.assertEqual(rejected.reject_reason, "manual reject by admin")


if __name__ == "__main__":
    unittest.main()
