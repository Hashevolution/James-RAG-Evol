"""Capability-token regression tests (#44 phase 3-1).

Coverage:
  - issue_capability: admin allowed, non-admin denied, invalid ttl rejected,
    token_ids are unique.
  - verify_capability: subpath / exact / wildcard scope all pass; scope
    mismatch / partial-prefix bug / action mismatch / expired / None all
    fail with the right applied_rule.

Run:
  python -m unittest tests.test_capability_tokens
  python tests/test_capability_tokens.py
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.policy_engine import (   # noqa: E402
    Capability,
    PolicyEngine,
    _scope_contains,
)


class CapabilityIssueTests(unittest.TestCase):
    def setUp(self):
        self.engine = PolicyEngine()

    def test_admin_can_issue_fs_write(self):
        cap = self.engine.issue_capability("admin", "fs.write", "./workspace/")
        self.assertIsNotNone(cap)
        self.assertIsInstance(cap, Capability)
        self.assertEqual(cap.role, "admin")
        self.assertEqual(cap.action, "fs.write")
        self.assertEqual(cap.scope, "./workspace/")
        self.assertGreater(cap.expires_at, cap.issued_at)
        self.assertEqual(len(cap.token_id), 32)   # uuid4 hex

    def test_non_admin_issuance_denied(self):
        for role in ("employee", "manager", "external", "", "unknown"):
            with self.subTest(role=role):
                cap = self.engine.issue_capability(role, "fs.write", "./workspace/")
                self.assertIsNone(cap)

    def test_invalid_ttl_rejected(self):
        for ttl in (0, -1, -60):
            with self.subTest(ttl=ttl):
                cap = self.engine.issue_capability("admin", "fs.read", "*", ttl_seconds=ttl)
                self.assertIsNone(cap)

    def test_token_ids_unique(self):
        a = self.engine.issue_capability("admin", "fs.write", "./workspace/")
        b = self.engine.issue_capability("admin", "fs.write", "./workspace/")
        self.assertNotEqual(a.token_id, b.token_id)


class CapabilityVerifyTests(unittest.TestCase):
    def setUp(self):
        self.engine = PolicyEngine()
        self.cap = self.engine.issue_capability(
            "admin", "fs.write", "./workspace/", ttl_seconds=60,
        )
        self.assertIsNotNone(self.cap, "fixture issuance must succeed")

    def test_subpath_within_scope_allowed(self):
        d = self.engine.verify_capability(self.cap, "fs.write", "./workspace/app.py")
        self.assertTrue(d.allowed, msg=d)
        self.assertEqual(d.applied_rule, "policy.cap.allow")

    def test_exact_scope_allowed(self):
        d = self.engine.verify_capability(self.cap, "fs.write", "./workspace/")
        self.assertTrue(d.allowed)

    def test_wildcard_scope_covers_anything(self):
        cap = self.engine.issue_capability("admin", "fs.read", "*")
        d = self.engine.verify_capability(cap, "fs.read", "/etc/passwd")
        self.assertTrue(d.allowed)

    def test_scope_mismatch_rejected(self):
        d = self.engine.verify_capability(self.cap, "fs.write", "./other/file.py")
        self.assertFalse(d.allowed)
        self.assertEqual(d.applied_rule, "policy.cap.scope_mismatch")

    def test_partial_prefix_bug_rejected(self):
        # ./workspace/ MUST NOT cover ./workspaceextra/ — guards the
        # trailing-slash normalization in _scope_contains.
        d = self.engine.verify_capability(self.cap, "fs.write", "./workspaceextra/x")
        self.assertFalse(d.allowed)
        self.assertEqual(d.applied_rule, "policy.cap.scope_mismatch")

    def test_action_mismatch_rejected(self):
        d = self.engine.verify_capability(self.cap, "fs.read", "./workspace/app.py")
        self.assertFalse(d.allowed)
        self.assertEqual(d.applied_rule, "policy.cap.action_mismatch")

    def test_expired_rejected(self):
        future = self.cap.expires_at + 1.0
        d = self.engine.verify_capability(
            self.cap, "fs.write", "./workspace/", now=future,
        )
        self.assertFalse(d.allowed)
        self.assertEqual(d.applied_rule, "policy.cap.expired")

    def test_none_rejected(self):
        d = self.engine.verify_capability(None, "fs.write", "./workspace/")
        self.assertFalse(d.allowed)
        self.assertEqual(d.applied_rule, "policy.cap.missing")


class ScopeContainsTests(unittest.TestCase):
    def test_wildcard(self):
        self.assertTrue(_scope_contains("*", "/anywhere"))

    def test_exact(self):
        self.assertTrue(_scope_contains("./a", "./a"))

    def test_directory_prefix(self):
        self.assertTrue(_scope_contains("./workspace/", "./workspace/x.py"))
        self.assertTrue(_scope_contains("./workspace", "./workspace/x.py"))

    def test_partial_prefix_disallowed(self):
        self.assertFalse(_scope_contains("./workspace/", "./workspaceextra/"))
        self.assertFalse(_scope_contains("./workspace", "./workspaceextra/"))


if __name__ == "__main__":
    unittest.main()
