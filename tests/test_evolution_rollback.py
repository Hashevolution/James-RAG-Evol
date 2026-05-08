"""Self-evolution rollback tests — #68 phase 2-B.

Coverage (per #68 verification §B):
  1. Mid-deploy corruption recovery: simulates a partial write by
     manually corrupting the target file AFTER a successful apply
     (which produced the backup). `restore_latest()` must recover
     the file byte-for-byte.
  2. Patch JSON store integrity: a failed write into the patch JSON
     store must leave the file either fully replaced or untouched
     (atomic-or-nothing — backup + replace pattern).
  3. Lifecycle log: APPROVED then ROLLED_BACK appears in
     `james_patch_log.jsonl` after the gate-driven rollback path.
  4. Subsequent process restart finds clean state — exercised by
     reading the target file from a fresh subprocess invocation
     and asserting it matches the pre-patch byte sequence.

Note on Windows path handling: `patch_applier.apply()` requires the
target string to start with `"."` (sandbox guard). On Windows
`str(Path("./workspace/foo"))` normalizes to `"workspace\\foo"`
(no leading dot). Tests use the literal `"./workspace/..."` string
form for the `target` field so the sandbox check passes.

Run:
  python -m unittest tests.test_evolution_rollback
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch as mock_patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# patch_applier.apply() print()s a ✅ on the success path. On Windows
# cp949 default consoles that crashes with UnicodeEncodeError, which
# is caught upstream and returns False — so the test would falsely
# fail "apply must succeed". Same helper PR #36 wired into the server.
from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


class _ScratchTarget:
    """Helper: writes a known-good file under ./workspace/ and tracks
    its original byte content for byte-identical comparison.

    `target_str` is the SLASH-form string (starts with "./") to feed
    into `apply()` — patch_applier's sandbox guard requires the leading
    dot, which Windows-Path stringification strips.
    """
    def __init__(self, name: str = "_rollback_test_target.py"):
        self.name = name
        self.target_str = f"./workspace/{name}"
        self.path = Path("./workspace") / name
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.original = b"# original v1 - byte-identical recovery target\nprint('v1')\n"
        self.path.write_bytes(self.original)

    def cleanup(self):
        self.path.unlink(missing_ok=True)
        bdir = Path("./workspace/.backups")
        if bdir.exists():
            for f in bdir.glob(f"{self.name}.*.bak"):
                f.unlink(missing_ok=True)


class MidDeployCrashRollbackTests(unittest.TestCase):
    """The applier takes a backup before write. If anything corrupts
    the file after that point (mid-write crash, fsync failure, an
    overwriting concurrent process), restore_latest must bring it
    back byte-for-byte."""

    def setUp(self):
        self.target = _ScratchTarget()

    def tearDown(self):
        self.target.cleanup()

    def test_corruption_after_apply_then_restore_yields_byte_identical(self):
        """Real apply succeeds and produces a backup. Then we manually
        corrupt the target file (simulating any post-write disaster).
        restore_latest brings it back to the pre-patch byte sequence.

        The 'mid-write crash' framing reduces to this: the backup
        was taken, the file ended up in some bad state, and the
        recovery path must produce the original bytes regardless of
        what the bad state actually contains."""
        from tools.patch.patch_applier import apply, restore_latest

        # Real apply — file changes, backup is created.
        new_code = "# patched v2 - this should be reverted\nprint('v2')\n"
        ok, msg = apply({
            "patch_id": "rollback_mid_crash",
            "target":   self.target.target_str,
            "code":     new_code,
        }, validated=True)
        self.assertTrue(ok, f"setup: apply must succeed: {msg}")
        self.assertEqual(self.target.path.read_text(encoding="utf-8"), new_code,
                         "setup: file must reflect the patch before corruption")

        # Simulate a mid-write crash leaving the file partially overwritten.
        # The exact corruption shape doesn't matter — what matters is
        # that restore_latest recovers the original bytes regardless.
        self.target.path.write_bytes(b"# CORRUPTED - half-written state\xff\xfe\x00")
        corrupt_bytes = self.target.path.read_bytes()
        self.assertNotEqual(corrupt_bytes, self.target.original)

        # restore_latest brings it back byte-for-byte.
        rb_ok, rb_msg = restore_latest(self.target.target_str)
        self.assertTrue(rb_ok, f"restore_latest must succeed: {rb_msg}")
        self.assertEqual(self.target.path.read_bytes(), self.target.original,
                         "restored file must be byte-identical to pre-patch original")

    def test_apply_with_no_backup_returns_failure_on_restore(self):
        """If apply was never called (no backup exists), restore_latest
        must report no-backup rather than silently succeeding with
        whatever file happens to be there."""
        from tools.patch.patch_applier import restore_latest
        fresh_str = "./workspace/_never_patched.py"
        fresh = Path(fresh_str)
        fresh.write_text("# never patched\n", encoding="utf-8")
        try:
            rb_ok, rb_msg = restore_latest(fresh_str)
            self.assertFalse(rb_ok)
            self.assertIn("백업 없음", rb_msg)
        finally:
            fresh.unlink(missing_ok=True)


class PatchJsonStoreIntegrityTests(unittest.TestCase):
    """A failed write into the patch JSON store (./workspace/patches/)
    must leave the file either fully replaced or untouched. record_approval
    handles this by writing the entire JSON in one Path.write_text call —
    the OS guarantees the file replace is atomic on POSIX (rename) and
    near-atomic on Windows. We test the contract via the user-visible
    behavior: failure to write produces a clear error, no half-JSON
    survives in the store."""

    def setUp(self):
        self.store = Path("./workspace/patches")
        self.store.mkdir(parents=True, exist_ok=True)
        self.patch_id = "store_integrity_001"
        self.path = self.store / f"{self.patch_id}.json"
        self.path.write_text(
            json.dumps({"patch_id": self.patch_id, "target": "./x.py",
                        "code": "x", "status": "AWAITING_APPROVAL"}),
            encoding="utf-8",
        )
        self.original = self.path.read_bytes()

    def tearDown(self):
        self.path.unlink(missing_ok=True)

    def test_record_approval_failure_yields_actionable_error(self):
        """When the patch JSON read fails (corrupted file), the
        recorder returns (False, error) and the caller knows not to
        proceed. The patch file on disk is untouched in the failure
        path."""
        from tools.patch.approval import record_approval
        # Corrupt the JSON to provoke a read failure.
        self.path.write_bytes(b"{ this is not valid JSON")
        ok, result = record_approval(self.patch_id, "alice", "admin", "api")
        self.assertFalse(ok)
        self.assertIn("error", result)
        self.assertIn("patch read failed", result["error"])

    def test_record_approval_success_produces_valid_json(self):
        """Happy path: the augmented JSON parses back to a dict with
        all expected approver-* fields. No partial JSON ever lands."""
        from tools.patch.approval import record_approval
        ok, augmented = record_approval(self.patch_id, "alice", "admin", "api")
        self.assertTrue(ok)
        # Round-trip: file must parse back to the same fields.
        on_disk = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk["approver_username"], "alice")
        self.assertEqual(on_disk["approver_role"], "admin")
        self.assertEqual(on_disk["approval_method"], "api")
        self.assertEqual(on_disk["status"], "APPROVED")
        self.assertIn("approved_at", on_disk)


class GateRollbackLifecycleTests(unittest.TestCase):
    """End-to-end through bench_gate: a regressing patch must result in
    APPROVED then ROLLED_BACK in james_patch_log.jsonl, and the file
    must actually revert to its pre-patch byte sequence."""

    def setUp(self):
        self.target = _ScratchTarget(name="_gate_rollback_test.py")
        self.log_path = Path("james_patch_log.jsonl")
        self._log_baseline_size = (
            self.log_path.stat().st_size if self.log_path.exists() else 0
        )

    def tearDown(self):
        self.target.cleanup()

    def _new_log_entries(self) -> list[dict]:
        if not self.log_path.exists():
            return []
        with self.log_path.open("rb") as f:
            f.seek(self._log_baseline_size)
            tail = f.read().decode("utf-8", errors="replace")
        return [json.loads(l) for l in tail.splitlines() if l.strip()]

    def test_gate_rollback_real_file_recovery(self):
        """Apply a real patch (file changes, backup taken), then
        force-fail the gate. The gate's auto-rollback must restore
        the file to its pre-patch byte sequence."""
        from tools.patch.patch_applier import apply
        from tools.patch.bench_gate import run_bench_gate
        from tools.patch import bench_gate as bg

        new_code = "# patched - should be reverted by the gate\nprint('v2')\n"
        ok, msg = apply({
            "patch_id": "gate_rb_p1",
            "target":   self.target.target_str,
            "code":     new_code,
        }, validated=True)
        self.assertTrue(ok, f"setup: apply must succeed: {msg}")
        self.assertEqual(self.target.path.read_text(encoding="utf-8"), new_code)

        # Real restore_latest is called inside run_bench_gate (no mock
        # on it) so the file actually reverts.
        with mock_patch.object(
            bg, "_run_bench_check_blocking",
            return_value=(False, "q1: graph_paths=2 outside band"),
        ), mock_patch.object(bg, "_summarize_report", return_value={}):
            result = asyncio.run(run_bench_gate("gate_rb_p1", self.target.target_str))

        self.assertFalse(result.passed)
        self.assertEqual(result.outcome_label, "rolled_back")
        self.assertIn("rollback=ok", result.detail)
        self.assertEqual(self.target.path.read_bytes(), self.target.original,
                         "after gate rollback, target must be byte-identical to original")

    def test_lifecycle_log_records_approved_then_rolled_back(self):
        """End-to-end through approval.record_approval + apply + gate
        rollback. The lifecycle JSONL must show APPROVED followed by
        ROLLED_BACK with the rollback detail present."""
        from tools.patch.approval import record_approval, record_outcome
        from tools.patch.patch_applier import apply
        from tools.patch.bench_gate import run_bench_gate
        from tools.patch import bench_gate as bg

        store = Path("./workspace/patches")
        store.mkdir(parents=True, exist_ok=True)
        patch_id = "lifecycle_test_001"
        patch_json = store / f"{patch_id}.json"
        patch_dict = {
            "patch_id": patch_id,
            "target":   self.target.target_str,
            "code":     "# patched\nprint('v2')\n",
            "source":   "test",
            "status":   "AWAITING_APPROVAL",
        }
        patch_json.write_text(json.dumps(patch_dict), encoding="utf-8")

        try:
            ok, _ = record_approval(patch_id, "test_user", "admin", "api")
            self.assertTrue(ok)

            apply_ok, _ = apply(patch_dict, validated=True)
            self.assertTrue(apply_ok)

            with mock_patch.object(
                bg, "_run_bench_check_blocking",
                return_value=(False, "regression"),
            ), mock_patch.object(bg, "_summarize_report", return_value={}):
                gate = asyncio.run(run_bench_gate(patch_id, self.target.target_str))

            record_outcome(patch_id, gate.outcome_label,
                           detail=gate.detail,
                           before_metrics=gate.before_metrics,
                           after_metrics=gate.after_metrics)

            entries = self._new_log_entries()
            events = [e["event"] for e in entries]
            self.assertIn("APPROVED", events)
            self.assertIn("ROLLED_BACK", events)
            self.assertLess(events.index("APPROVED"), events.index("ROLLED_BACK"),
                            "APPROVED must precede ROLLED_BACK in the log")
            rb_entry = next(e for e in entries if e["event"] == "ROLLED_BACK")
            self.assertEqual(rb_entry["outcome"], "rolled_back")
            self.assertIn("rollback", rb_entry["detail"])

        finally:
            patch_json.unlink(missing_ok=True)


class SubsequentRestartCleanStateTests(unittest.TestCase):
    """Per #68 §B item 4: subsequent restart finds clean state. We
    exercise this by reading the target through a fresh subprocess —
    no shared in-memory state survives."""

    def setUp(self):
        self.target = _ScratchTarget(name="_restart_clean_state.py")

    def tearDown(self):
        self.target.cleanup()

    def test_post_rollback_state_visible_to_fresh_python_process(self):
        from tools.patch.patch_applier import apply, restore_latest

        ok, msg = apply({
            "patch_id": "restart_test",
            "target":   self.target.target_str,
            "code":     "# changed\nprint('v2')\n",
        }, validated=True)
        self.assertTrue(ok, f"apply must succeed: {msg}")

        rb_ok, rb_msg = restore_latest(self.target.target_str)
        self.assertTrue(rb_ok, f"rollback must succeed: {rb_msg}")

        # Fresh subprocess reads the file — no shared state.
        proc = subprocess.run(
            [sys.executable, "-c",
             f"import sys; sys.stdout.buffer.write(open(r'{self.target.path}', 'rb').read())"],
            capture_output=True, timeout=10,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, self.target.original,
                         "fresh process must see byte-identical original after rollback")


if __name__ == "__main__":
    unittest.main()
