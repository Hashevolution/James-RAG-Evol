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

    def test_fs_write_admin_only(self):
        # Phase 3-2: fs.write stays admin-only.
        for role in ("employee", "manager", "external", "", "unknown"):
            with self.subTest(role=role):
                cap = self.engine.issue_capability(role, "fs.write", "./workspace/")
                self.assertIsNone(cap)

    def test_fs_read_employee_and_above(self):
        # Phase 3-2: fs.read relaxed to employee+ (level >= 1).
        for role in ("employee", "manager", "admin"):
            with self.subTest(role=role):
                cap = self.engine.issue_capability(role, "fs.read", "./workspace/")
                self.assertIsNotNone(cap, msg=f"{role} should issue fs.read")
                self.assertEqual(cap.action, "fs.read")

    def test_fs_read_external_denied(self):
        cap = self.engine.issue_capability("external", "fs.read", "./workspace/")
        self.assertIsNone(cap)

    def test_shell_exec_admin_only(self):
        for role in ("employee", "manager", "external", "unknown"):
            with self.subTest(role=role):
                cap = self.engine.issue_capability(role, "shell.exec", "*")
                self.assertIsNone(cap)
        cap = self.engine.issue_capability("admin", "shell.exec", "*")
        self.assertIsNotNone(cap)

    def test_unknown_action_falls_back_to_admin(self):
        # Fail-closed: anything not in _TOOL_ACTION_MIN_ROLE → admin-only.
        for role in ("employee", "manager", "external"):
            with self.subTest(role=role):
                cap = self.engine.issue_capability(role, "made.up.action", "*")
                self.assertIsNone(cap)
        cap = self.engine.issue_capability("admin", "made.up.action", "*")
        self.assertIsNotNone(cap)

    def test_invalid_ttl_rejected(self):
        for ttl in (0, -1, -60):
            with self.subTest(ttl=ttl):
                cap = self.engine.issue_capability("admin", "fs.read", "*", ttl_seconds=ttl)
                self.assertIsNone(cap)

    def test_token_ids_unique(self):
        a = self.engine.issue_capability("admin", "fs.write", "./workspace/")
        b = self.engine.issue_capability("admin", "fs.write", "./workspace/")
        self.assertNotEqual(a.token_id, b.token_id)


class CanCallToolDecisionTests(unittest.TestCase):
    """Phase 3-2: can_call_tool returns the right applied_rule per action."""

    def setUp(self):
        self.engine = PolicyEngine()

    def test_applied_rule_per_action(self):
        for action in ("fs.read", "fs.write", "shell.exec", "tool.invoke"):
            with self.subTest(action=action):
                d = self.engine.can_call_tool("admin", action)
                self.assertEqual(d.applied_rule, f"policy.tool.{action}")

    def test_fs_read_employee_allowed_decision(self):
        d = self.engine.can_call_tool("employee", "fs.read")
        self.assertTrue(d.allowed)
        self.assertIn("employee_ge_employee", d.reason)

    def test_fs_write_employee_denied_decision(self):
        d = self.engine.can_call_tool("employee", "fs.write")
        self.assertFalse(d.allowed)
        self.assertIn("employee_lt_admin", d.reason)


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
