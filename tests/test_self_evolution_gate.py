"""Self-evolution opt-in + approval gate — #48 phase 1 (Axis 5).

Coverage:
  - `record_approval` persists approver_username / approver_role /
    approved_at / approval_method into the patch JSON, sets
    status="APPROVED", and emits a lifecycle log line.
  - `record_approval` rejects bad inputs:
      * unknown approval_method
      * missing approver_username
      * missing patch file
  - Source-level contracts:
      * `/admin/patch/approve` checks `EVOLUTION_ENABLED` and returns
        403 when disabled. Imports + uses `record_approval`.
      * `config.py` raises if `JAMES_AUTO_APPROVE=1` but
        `JAMES_DEV_MODE=0`.
  - `/admin/patch/approve` requires `approver_username` body field
    (source-level — full HTTP integration test runs through the
    operator's bench --check post-merge).

Run:
  python -m unittest tests.test_self_evolution_gate
  python tests/test_self_evolution_gate.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch as _patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _PatchStoreMixin:
    """Each test gets a fresh `./workspace/patches` so the on-disk
    patch JSON written by record_approval doesn't bleed across tests."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._patch_store = Path(self._tmp.name) / "patches"
        self._patch_store.mkdir(parents=True, exist_ok=True)
        # Redirect both PATCH_STORE and PATCH_LOG_PATH at the tmpdir.
        from tools.patch import approval as approval_mod
        self._orig_store    = approval_mod.PATCH_STORE
        self._orig_log_path = approval_mod.PATCH_LOG_PATH
        approval_mod.PATCH_STORE    = str(self._patch_store)
        approval_mod.PATCH_LOG_PATH = str(Path(self._tmp.name) / "james_patch_log.jsonl")

    def tearDown(self):
        from tools.patch import approval as approval_mod
        approval_mod.PATCH_STORE    = self._orig_store
        approval_mod.PATCH_LOG_PATH = self._orig_log_path
        self._tmp.cleanup()

    def _write_patch(self, patch_id: str, **fields) -> Path:
        body = {
            "patch_id":   patch_id,
            "target":     "./workspace/sample.py",
            "diff":       "--- a/sample\n+++ b/sample\n",
            "status":     "PENDING_APPROVAL",
            "confidence": 0.9,
            "created_at": "2026-05-07T12:00:00",
            **fields,
        }
        p = self._patch_store / f"{patch_id}.json"
        p.write_text(json.dumps(body, ensure_ascii=False, indent=2),
                     encoding="utf-8")
        return p


class RecordApprovalTests(_PatchStoreMixin, unittest.TestCase):
    def test_persists_approval_metadata(self):
        from tools.patch.approval import record_approval
        self._write_patch("p001")

        ok, patch = record_approval(
            patch_id="p001",
            approver_username="alice",
            approver_role="admin",
            approval_method="ui",
        )
        self.assertTrue(ok, f"record_approval failed: {patch}")
        self.assertEqual(patch["approver_username"], "alice")
        self.assertEqual(patch["approver_role"],     "admin")
        self.assertEqual(patch["approval_method"],   "ui")
        self.assertEqual(patch["status"],            "APPROVED")
        self.assertIn("approved_at", patch)

        # Round-trip: file on disk has the same metadata.
        on_disk = json.loads((self._patch_store / "p001.json").read_text(encoding="utf-8"))
        self.assertEqual(on_disk["approver_username"], "alice")
        self.assertEqual(on_disk["status"],            "APPROVED")

    def test_rejects_unknown_method(self):
        from tools.patch.approval import record_approval
        self._write_patch("p002")
        ok, err = record_approval("p002", "alice", "admin",
                                  approval_method="auto-by-ai")
        self.assertFalse(ok)
        self.assertIn("invalid approval_method", err["error"])

    def test_rejects_missing_username(self):
        from tools.patch.approval import record_approval
        self._write_patch("p003")
        ok, err = record_approval("p003", "", "admin", approval_method="api")
        self.assertFalse(ok)
        self.assertIn("approver_username required", err["error"])

    def test_rejects_missing_patch(self):
        from tools.patch.approval import record_approval
        # No patch file written — record_approval must refuse.
        ok, err = record_approval("does_not_exist", "alice", "admin")
        self.assertFalse(ok)
        self.assertIn("patch not found", err["error"])

    def test_lifecycle_log_appended(self):
        from tools.patch import approval as approval_mod
        from tools.patch.approval import record_approval
        self._write_patch("p004")

        ok, _ = record_approval("p004", "bob", "admin", "api")
        self.assertTrue(ok)
        log_path = Path(approval_mod.PATCH_LOG_PATH)
        self.assertTrue(log_path.exists(), "lifecycle log not written")
        lines = [json.loads(l) for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["event"],            "APPROVED")
        self.assertEqual(lines[0]["patch_id"],         "p004")
        self.assertEqual(lines[0]["approver_username"], "bob")
        self.assertEqual(lines[0]["approval_method"],  "api")


class RecordOutcomeTests(_PatchStoreMixin, unittest.TestCase):
    def test_deployed_outcome_logged(self):
        from tools.patch import approval as approval_mod
        from tools.patch.approval import record_outcome

        record_outcome(
            patch_id="p010", outcome="deployed",
            detail="apply ok", before_metrics={"x": 1}, after_metrics={"x": 1},
        )
        lines = [json.loads(l)
                 for l in Path(approval_mod.PATCH_LOG_PATH).read_text(encoding="utf-8").splitlines()
                 if l.strip()]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["event"],   "DEPLOYED")
        self.assertEqual(lines[0]["outcome"], "deployed")

    def test_rolled_back_outcome_logged(self):
        from tools.patch import approval as approval_mod
        from tools.patch.approval import record_outcome

        record_outcome("p011", "rolled_back", detail="apply failed: …")
        lines = [json.loads(l)
                 for l in Path(approval_mod.PATCH_LOG_PATH).read_text(encoding="utf-8").splitlines()
                 if l.strip()]
        self.assertEqual(lines[0]["event"],   "ROLLED_BACK")
        self.assertEqual(lines[0]["outcome"], "rolled_back")


class EndpointGateContractTests(unittest.TestCase):
    """Source-level: the /admin/patch/approve endpoint must enforce
    the env-flag gate and pass approver metadata into record_approval.
    Same chokepoint pattern as test_observability / test_policy_quarantine.
    """

    def test_endpoint_imports_and_checks_evolution_flag(self):
        import server_llmwiki as srv
        import inspect
        src = inspect.getsource(srv)
        # Imports the flag from config.
        self.assertIn("from config import EVOLUTION_ENABLED, APPROVER_ROLE", src,
                      "/admin/patch/approve must read EVOLUTION_ENABLED + APPROVER_ROLE")
        # Returns 403 when flag is off.
        self.assertIn('"evolution_disabled', src,
                      "/admin/patch/approve must return 403 evolution_disabled")
        # Requires approver_username in the body.
        self.assertIn("approver_username required (#48 audit)", src,
                      "/admin/patch/approve must require approver_username")
        # Calls record_approval before patch_apply.
        self.assertIn("from tools.patch.approval        import record_approval", src,
                      "/admin/patch/approve must use record_approval()")
        self.assertIn("record_outcome", src,
                      "/admin/patch/approve must record deploy/rollback outcome")

    def test_config_module_defines_gate_flags(self):
        import config
        # The flags are present and have the right defaults in this
        # environment (JAMES_ENABLE_EVOLUTION not set → False, etc.).
        self.assertTrue(hasattr(config, "EVOLUTION_ENABLED"))
        self.assertTrue(hasattr(config, "AUTO_APPROVE"))
        self.assertTrue(hasattr(config, "APPROVER_ROLE"))
        # Default approver role is admin (per #48 spec).
        self.assertEqual(config.APPROVER_ROLE, "admin")


class AutoApproveSafetyCheckTests(unittest.TestCase):
    """The fail-closed contract: AUTO_APPROVE=1 + DEV_MODE=0 must
    refuse to start. We can't re-import config (singleton), so test
    the equivalent logic directly against the module source.
    """

    def test_config_refuses_auto_approve_in_non_dev(self):
        # Source-level: config.py must contain the explicit
        # AUTO_APPROVE-without-DEV_MODE refuse-to-start clause.
        # If a future refactor moves the check elsewhere, this test
        # fails and the reviewer must update the contract.
        cfg_path = Path(__file__).resolve().parent.parent / "config.py"
        src = cfg_path.read_text(encoding="utf-8")
        self.assertIn("AUTO_APPROVE and not _DEV_MODE_AT_IMPORT", src,
                      "config.py must refuse start if AUTO_APPROVE is set "
                      "without DEV_MODE — see #48 fail-closed contract")
        self.assertIn("Refusing to start", src)


if __name__ == "__main__":
    unittest.main()
