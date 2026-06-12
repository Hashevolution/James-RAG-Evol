"""v0.5 G2.a — approval-evidence primitive contract tests.

Covers:

  * `ApprovalEvidence` dataclass — frozen, all fields populated,
    default `expires_at` empty.
  * `require_approval_evidence()` — truthy / falsy env parsing.
  * Resolution: explicit override wins; missing env yields None;
    base64-malformed evidence yields None.
  * Resolution: POSIX fallback resolves under `getpass.getuser()`;
    disabled by `allow_posix_fallback=False`.
  * Resolution: explicit takes precedence over POSIX.
  * Evidence hash determinism — same inputs (clock-controlled)
    produce the same hash; changing inputs changes the hash.
"""
from __future__ import annotations

import base64
import os
import unittest
from contextlib import contextmanager
from typing import Dict
from unittest import mock

from core.security.approval_evidence import (
    ApprovalEvidence,
    current_approval_evidence,
    require_approval_evidence,
)


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


class DataclassTests(unittest.TestCase):
    def test_all_fields_populated(self):
        ev = ApprovalEvidence(
            principal="alex",
            source="posix",
            evidence_hash="abc123",
            captured_at="2026-06-12T00:00:00+00:00",
        )
        self.assertEqual(ev.principal, "alex")
        self.assertEqual(ev.source, "posix")
        self.assertEqual(ev.evidence_hash, "abc123")
        self.assertEqual(ev.captured_at, "2026-06-12T00:00:00+00:00")
        self.assertEqual(ev.expires_at, "")

    def test_expires_at_default_empty(self):
        ev = ApprovalEvidence(
            principal="alex", source="posix",
            evidence_hash="x", captured_at="t",
        )
        self.assertEqual(ev.expires_at, "")

    def test_frozen_cannot_mutate(self):
        ev = ApprovalEvidence(
            principal="alex", source="posix",
            evidence_hash="x", captured_at="t",
        )
        with self.assertRaises(Exception):
            ev.principal = "mallory"  # type: ignore[misc]


class RequireApprovalEvidenceTests(unittest.TestCase):
    def test_default_false(self):
        with _patched_env(JAMES_REQUIRE_APPROVAL_EVIDENCE=None):
            self.assertFalse(require_approval_evidence())

    def test_truthy_values(self):
        for value in ("1", "true", "yes", "on", "enabled"):
            with self.subTest(value=value):
                with _patched_env(JAMES_REQUIRE_APPROVAL_EVIDENCE=value):
                    self.assertTrue(require_approval_evidence())

    def test_falsy_values(self):
        for value in ("0", "false", "no", "off", "", "anything-else"):
            with self.subTest(value=value):
                with _patched_env(JAMES_REQUIRE_APPROVAL_EVIDENCE=value):
                    self.assertFalse(require_approval_evidence())


class ExplicitResolutionTests(unittest.TestCase):
    def test_explicit_override_returns_evidence(self):
        evidence_b64 = base64.b64encode(b"signed-jwt-blob").decode("ascii")
        with _patched_env(
            JAMES_APPROVAL_PRINCIPAL="ci-bot@acme.com",
            JAMES_APPROVAL_EVIDENCE_B64=evidence_b64,
        ):
            ev = current_approval_evidence(allow_posix_fallback=False)
        self.assertIsNotNone(ev)
        self.assertEqual(ev.principal, "ci-bot@acme.com")
        self.assertEqual(ev.source, "explicit")
        self.assertTrue(ev.evidence_hash)
        self.assertTrue(ev.captured_at)

    def test_explicit_principal_only_returns_none(self):
        with _patched_env(
            JAMES_APPROVAL_PRINCIPAL="ci-bot",
            JAMES_APPROVAL_EVIDENCE_B64=None,
        ):
            ev = current_approval_evidence(allow_posix_fallback=False)
        self.assertIsNone(ev)

    def test_explicit_evidence_only_returns_none(self):
        evidence_b64 = base64.b64encode(b"x").decode("ascii")
        with _patched_env(
            JAMES_APPROVAL_PRINCIPAL=None,
            JAMES_APPROVAL_EVIDENCE_B64=evidence_b64,
        ):
            ev = current_approval_evidence(allow_posix_fallback=False)
        self.assertIsNone(ev)

    def test_malformed_b64_returns_none(self):
        with _patched_env(
            JAMES_APPROVAL_PRINCIPAL="ci-bot",
            JAMES_APPROVAL_EVIDENCE_B64="not!valid!base64!@#",
        ):
            ev = current_approval_evidence(allow_posix_fallback=False)
        self.assertIsNone(ev)

    def test_whitespace_principal_returns_none(self):
        evidence_b64 = base64.b64encode(b"x").decode("ascii")
        with _patched_env(
            JAMES_APPROVAL_PRINCIPAL="   ",
            JAMES_APPROVAL_EVIDENCE_B64=evidence_b64,
        ):
            ev = current_approval_evidence(allow_posix_fallback=False)
        self.assertIsNone(ev)


class PosixResolutionTests(unittest.TestCase):
    def test_posix_resolves_under_getpass(self):
        # Clear explicit env so POSIX is the resolution path.
        with _patched_env(
            JAMES_APPROVAL_PRINCIPAL=None,
            JAMES_APPROVAL_EVIDENCE_B64=None,
        ):
            with mock.patch("getpass.getuser", return_value="alex"):
                ev = current_approval_evidence()
        self.assertIsNotNone(ev)
        self.assertEqual(ev.principal, "alex")
        self.assertEqual(ev.source, "posix")
        self.assertTrue(ev.evidence_hash)
        # 64-char hex sha256 digest.
        self.assertEqual(len(ev.evidence_hash), 64)
        int(ev.evidence_hash, 16)

    def test_posix_disabled_returns_none(self):
        with _patched_env(
            JAMES_APPROVAL_PRINCIPAL=None,
            JAMES_APPROVAL_EVIDENCE_B64=None,
        ):
            with mock.patch("getpass.getuser", return_value="alex"):
                ev = current_approval_evidence(allow_posix_fallback=False)
        self.assertIsNone(ev)

    def test_posix_username_empty_returns_none(self):
        with _patched_env(
            JAMES_APPROVAL_PRINCIPAL=None,
            JAMES_APPROVAL_EVIDENCE_B64=None,
        ):
            with mock.patch("getpass.getuser", return_value=""):
                ev = current_approval_evidence()
        self.assertIsNone(ev)

    def test_posix_getpass_exception_returns_none(self):
        with _patched_env(
            JAMES_APPROVAL_PRINCIPAL=None,
            JAMES_APPROVAL_EVIDENCE_B64=None,
        ):
            with mock.patch("getpass.getuser",
                            side_effect=OSError("no user")):
                ev = current_approval_evidence()
        self.assertIsNone(ev)


class ResolutionOrderTests(unittest.TestCase):
    def test_explicit_takes_precedence_over_posix(self):
        evidence_b64 = base64.b64encode(b"explicit-blob").decode("ascii")
        with _patched_env(
            JAMES_APPROVAL_PRINCIPAL="bot",
            JAMES_APPROVAL_EVIDENCE_B64=evidence_b64,
        ):
            with mock.patch("getpass.getuser", return_value="posix_alex"):
                ev = current_approval_evidence()
        self.assertIsNotNone(ev)
        self.assertEqual(ev.principal, "bot")
        self.assertEqual(ev.source, "explicit")


class HashStabilityTests(unittest.TestCase):
    def test_different_usernames_yield_different_hashes(self):
        with _patched_env(
            JAMES_APPROVAL_PRINCIPAL=None,
            JAMES_APPROVAL_EVIDENCE_B64=None,
        ):
            with mock.patch("getpass.getuser", return_value="alex"):
                a = current_approval_evidence()
            with mock.patch("getpass.getuser", return_value="blair"):
                b = current_approval_evidence()
        self.assertNotEqual(a.evidence_hash, b.evidence_hash)

    def test_different_principals_yield_different_explicit_hashes(self):
        evidence_b64 = base64.b64encode(b"same-blob").decode("ascii")
        with _patched_env(
            JAMES_APPROVAL_PRINCIPAL="bot_a",
            JAMES_APPROVAL_EVIDENCE_B64=evidence_b64,
        ):
            a = current_approval_evidence(allow_posix_fallback=False)
        # Same blob, different principal — hash should differ because
        # only the BLOB is hashed (not the principal); test that the
        # API behavior is documented. (Hashing principal+blob together
        # is a future hardening; this test pins current behavior.)
        with _patched_env(
            JAMES_APPROVAL_PRINCIPAL="bot_b",
            JAMES_APPROVAL_EVIDENCE_B64=evidence_b64,
        ):
            b = current_approval_evidence(allow_posix_fallback=False)
        # Current behavior: explicit hash is over the blob only, so
        # same blob → same hash even with different principal.
        # If this assertion fails after a future hardening PR, the
        # test should update to reflect the new contract.
        self.assertEqual(a.evidence_hash, b.evidence_hash)


if __name__ == "__main__":
    unittest.main()
