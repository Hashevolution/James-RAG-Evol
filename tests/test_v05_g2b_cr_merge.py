"""v0.5 G2.b — CR merge + approval-evidence wire-in tests.

Covers:

  * `merge_cr` happy path — transitions open → merged + writes
    audit row.
  * Required-reviewer + self-merge guard.
  * State-machine invariant — only `open` CRs can merge.
  * Default-off (no enforce env, no evidence) is byte-identical to
    pre-G2.b behaviour.
  * Enforce mode (`JAMES_REQUIRE_APPROVAL_EVIDENCE=1`) rejects
    when evidence is None.
  * Principal-match check — evidence.principal must match reviewer.
  * Audit row carries evidence fingerprint when present.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from contextlib import contextmanager
from typing import Dict

from unittest import mock

from core.change_request import (
    STATUS_MERGED,
    STATUS_OPEN,
    TARGET_WIKI_ENTITY,
    create_cr,
    get_cr,
    init_db,
)
from core.change_request_merge import merge_cr
from core.security.approval_evidence import ApprovalEvidence


@contextmanager
def _patched_env(**env: str):
    saved: Dict[str, str] = {}
    unset_keys = []
    for k, v in env.items():
        if k in os.environ:
            saved[k] = os.environ[k]
        else:
            unset_keys.append(k)
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, v in saved.items():
            os.environ[k] = v
        for k in unset_keys:
            os.environ.pop(k, None)


def _tmp_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".db", prefix="james-cr-")
    os.close(fd)
    init_db(db_path=path)
    return path


def _make_cr(db_path: str, *, proposer: str = "alice") -> str:
    cr = create_cr(
        target_type=TARGET_WIKI_ENTITY,
        target_id="e_test",
        title="Update test entity",
        description="desc",
        proposed_diff='{"op":"set","field":"x","value":"y"}',
        base_hash="0" * 64,
        proposer=proposer,
        labels="",
        db_path=db_path,
    )
    return cr.cr_id


class MergeHappyPathTests(unittest.TestCase):
    def setUp(self):
        self.db_path = _tmp_db()

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except OSError:
            pass

    def test_open_to_merged(self):
        with _patched_env(JAMES_REQUIRE_APPROVAL_EVIDENCE=None):
            cr_id = _make_cr(self.db_path, proposer="alice")
            cr = merge_cr(
                cr_id, reviewer="blair", db_path=self.db_path,
            )
            self.assertEqual(cr.status, STATUS_MERGED)
            self.assertIsNotNone(cr.merged_at)
            self.assertEqual(cr.merged_by, "blair")

    def test_idempotent_re_merge_rejected(self):
        with _patched_env(JAMES_REQUIRE_APPROVAL_EVIDENCE=None):
            cr_id = _make_cr(self.db_path, proposer="alice")
            merge_cr(cr_id, reviewer="blair", db_path=self.db_path)
            with self.assertRaises(ValueError):
                merge_cr(cr_id, reviewer="cam", db_path=self.db_path)


class MergeReviewerInvariantTests(unittest.TestCase):
    def setUp(self):
        self.db_path = _tmp_db()

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except OSError:
            pass

    def test_empty_reviewer_rejected(self):
        cr_id = _make_cr(self.db_path)
        with self.assertRaises(ValueError):
            merge_cr(cr_id, reviewer="", db_path=self.db_path)

    def test_self_merge_rejected(self):
        with _patched_env(JAMES_REQUIRE_APPROVAL_EVIDENCE=None):
            cr_id = _make_cr(self.db_path, proposer="alice")
            with self.assertRaises(ValueError):
                merge_cr(
                    cr_id, reviewer="alice", db_path=self.db_path,
                )

    def test_unknown_cr_rejected(self):
        with self.assertRaises(ValueError):
            merge_cr(
                "does-not-exist", reviewer="blair", db_path=self.db_path,
            )


class MergeEnforceModeTests(unittest.TestCase):
    def setUp(self):
        self.db_path = _tmp_db()

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except OSError:
            pass

    def test_enforce_no_evidence_rejected(self):
        with _patched_env(JAMES_REQUIRE_APPROVAL_EVIDENCE="1"):
            cr_id = _make_cr(self.db_path, proposer="alice")
            with self.assertRaises(ValueError):
                merge_cr(
                    cr_id, reviewer="blair", db_path=self.db_path,
                )
        # CR must still be open (rollback semantic — gate fires
        # before DB transition).
        cr = get_cr(cr_id, db_path=self.db_path)
        self.assertEqual(cr.status, STATUS_OPEN)

    def test_enforce_with_evidence_succeeds(self):
        evidence = ApprovalEvidence(
            principal="blair",
            source="posix",
            evidence_hash="abc123" + "0" * 58,  # 64-hex
            captured_at="2026-06-12T20:00:00+00:00",
        )
        with _patched_env(JAMES_REQUIRE_APPROVAL_EVIDENCE="1"):
            cr_id = _make_cr(self.db_path, proposer="alice")
            cr = merge_cr(
                cr_id,
                reviewer="blair",
                approval_evidence=evidence,
                db_path=self.db_path,
            )
            self.assertEqual(cr.status, STATUS_MERGED)

    def test_default_off_byte_identical(self):
        # Without enforce env, missing evidence is fine.
        with _patched_env(JAMES_REQUIRE_APPROVAL_EVIDENCE=None):
            cr_id = _make_cr(self.db_path, proposer="alice")
            cr = merge_cr(cr_id, reviewer="blair", db_path=self.db_path)
            self.assertEqual(cr.status, STATUS_MERGED)


class MergePrincipalMatchTests(unittest.TestCase):
    def setUp(self):
        self.db_path = _tmp_db()

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except OSError:
            pass

    def test_principal_mismatch_rejected(self):
        evidence = ApprovalEvidence(
            principal="mallory",
            source="posix",
            evidence_hash="x" * 12,
            captured_at="2026-06-12T20:00:00+00:00",
        )
        with _patched_env(JAMES_REQUIRE_APPROVAL_EVIDENCE=None):
            cr_id = _make_cr(self.db_path, proposer="alice")
            with self.assertRaises(ValueError):
                merge_cr(
                    cr_id,
                    reviewer="blair",
                    approval_evidence=evidence,
                    db_path=self.db_path,
                )
        # Rollback — CR still open.
        cr = get_cr(cr_id, db_path=self.db_path)
        self.assertEqual(cr.status, STATUS_OPEN)

    def test_principal_match_succeeds(self):
        evidence = ApprovalEvidence(
            principal="blair",
            source="posix",
            evidence_hash="x" * 12,
            captured_at="2026-06-12T20:00:00+00:00",
        )
        with _patched_env(JAMES_REQUIRE_APPROVAL_EVIDENCE=None):
            cr_id = _make_cr(self.db_path, proposer="alice")
            cr = merge_cr(
                cr_id,
                reviewer="blair",
                approval_evidence=evidence,
                db_path=self.db_path,
            )
            self.assertEqual(cr.status, STATUS_MERGED)


class MergeAuditEventTests(unittest.TestCase):
    """Verify the audit row emitted on merge carries the right
    fingerprint shape — verified by mocking the internal
    `_audit_event` function so the assertion is independent of
    the audit_bridge DB plumbing."""

    def setUp(self):
        self.db_path = _tmp_db()

    def tearDown(self):
        try:
            os.remove(self.db_path)
        except OSError:
            pass

    def test_audit_event_called_with_reviewer_no_evidence(self):
        with _patched_env(JAMES_REQUIRE_APPROVAL_EVIDENCE=None):
            cr_id = _make_cr(self.db_path, proposer="alice")
            with mock.patch("core.change_request_merge._audit_event") as m:
                merge_cr(
                    cr_id, reviewer="blair", db_path=self.db_path,
                )
        m.assert_called_once()
        args, kwargs = m.call_args
        # First positional is event_type, second is cr_id.
        self.assertEqual(args[0], "merge")
        self.assertEqual(args[1], cr_id)
        self.assertEqual(kwargs.get("reviewer"), "blair")
        # No evidence fields when no evidence passed.
        self.assertNotIn("evidence_hash", kwargs)
        self.assertNotIn("evidence_principal", kwargs)

    def test_audit_event_called_with_evidence_fingerprint(self):
        evidence = ApprovalEvidence(
            principal="blair",
            source="posix",
            evidence_hash="evidence-hash-value-xyz",
            captured_at="2026-06-12T20:00:00+00:00",
        )
        with _patched_env(JAMES_REQUIRE_APPROVAL_EVIDENCE=None):
            cr_id = _make_cr(self.db_path, proposer="alice")
            with mock.patch("core.change_request_merge._audit_event") as m:
                merge_cr(
                    cr_id,
                    reviewer="blair",
                    approval_evidence=evidence,
                    db_path=self.db_path,
                )
        m.assert_called_once()
        _, kwargs = m.call_args
        self.assertEqual(kwargs.get("evidence_principal"), "blair")
        self.assertEqual(kwargs.get("evidence_source"), "posix")
        self.assertEqual(
            kwargs.get("evidence_hash"), "evidence-hash-value-xyz",
        )
        self.assertEqual(
            kwargs.get("evidence_captured_at"),
            "2026-06-12T20:00:00+00:00",
        )


if __name__ == "__main__":
    unittest.main()
