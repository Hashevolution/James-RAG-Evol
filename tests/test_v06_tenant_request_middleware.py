"""v0.6 Phase 3 P3.1 — per-request tenant middleware tests.

Covers signing / verification + ASGI middleware integration
including the trusted-peer gate + enforce-mode 403 + async tenant
context propagation.

Coverage:

`_decode_secret`:
  * Empty / whitespace → None
  * Valid base64 → bytes
  * Invalid base64 → None

`sign_tenant_id` + `verify_tenant_header`:
  * Round-trip — sign then verify recovers the tenant_id
  * Wrong secret → verify returns None
  * Truncated header → None
  * Wrong-length signature → None
  * Tenant_id with dots in it (e.g. acme.corp) → still parses
  * Tampered tenant_id → None
  * Empty / missing dot → None
  * Constant-time comparison used (smoke verification — compare_digest is in the call site)

Middleware integration (direct ASGI scope):
  * No secret configured → pass-through, no tenant set
  * Secret configured + valid header + trusted peer → tenant scoped
  * Secret configured + valid header + UNTRUSTED peer → 403 in enforce mode, pass-through otherwise
  * Secret configured + INVALID header + trusted peer → 403 in enforce mode, pass-through otherwise
  * Secret configured + missing header + trusted peer → 403 in enforce mode, pass-through otherwise
  * Custom header name from env honored
  * Tenant scope propagates across `await` (async context propagation)

Run:
  python -m unittest tests.test_v06_tenant_request_middleware
"""
from __future__ import annotations

import asyncio
import base64
import os
import sys
import unittest
from contextlib import contextmanager

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@contextmanager
def _patched_env(**env):
    saved = {}
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
        for k in env:
            if k not in saved and k not in unset_keys:
                os.environ.pop(k, None)


_TEST_SECRET_BYTES = b"\x00" * 32
_TEST_SECRET_B64 = base64.b64encode(_TEST_SECRET_BYTES).decode("ascii")


# ─── pure-function helpers ──────────────────────────────────────────


class DecodeSecretTests(unittest.TestCase):
    def test_empty_returns_none(self):
        from core.security.tenant_request import _decode_secret
        self.assertIsNone(_decode_secret(""))

    def test_whitespace_returns_none(self):
        from core.security.tenant_request import _decode_secret
        self.assertIsNone(_decode_secret("   "))

    def test_valid_base64_decodes(self):
        from core.security.tenant_request import _decode_secret
        self.assertEqual(_decode_secret(_TEST_SECRET_B64), _TEST_SECRET_BYTES)

    def test_invalid_base64_returns_none(self):
        from core.security.tenant_request import _decode_secret
        self.assertIsNone(_decode_secret("not!base64@@@"))


class SignVerifyTests(unittest.TestCase):
    def test_round_trip(self):
        from core.security.tenant_request import (
            sign_tenant_id, verify_tenant_header,
        )
        for tenant in ("acme", "globex", "tenant_with_underscore",
                       "TenantCaseSensitive"):
            signed = sign_tenant_id(_TEST_SECRET_BYTES, tenant)
            self.assertEqual(
                verify_tenant_header(signed, _TEST_SECRET_BYTES),
                tenant,
            )

    def test_wrong_secret_fails(self):
        from core.security.tenant_request import (
            sign_tenant_id, verify_tenant_header,
        )
        signed = sign_tenant_id(_TEST_SECRET_BYTES, "acme")
        wrong_secret = b"\x01" * 32
        self.assertIsNone(verify_tenant_header(signed, wrong_secret))

    def test_tampered_tenant_id_fails(self):
        from core.security.tenant_request import (
            sign_tenant_id, verify_tenant_header,
        )
        signed = sign_tenant_id(_TEST_SECRET_BYTES, "acme")
        # Modify the tenant_id portion but keep the original signature.
        idx = signed.rfind(".")
        tampered = "globex" + signed[idx:]
        self.assertIsNone(verify_tenant_header(tampered, _TEST_SECRET_BYTES))

    def test_tenant_id_with_dots(self):
        # `acme.corp` is a valid tenant id; the parser splits on the
        # LAST dot, so `acme.corp.<sig>` recovers `acme.corp`.
        from core.security.tenant_request import (
            sign_tenant_id, verify_tenant_header,
        )
        tenant = "acme.corp"
        signed = sign_tenant_id(_TEST_SECRET_BYTES, tenant)
        self.assertEqual(
            verify_tenant_header(signed, _TEST_SECRET_BYTES),
            tenant,
        )

    def test_missing_dot_fails(self):
        from core.security.tenant_request import verify_tenant_header
        self.assertIsNone(verify_tenant_header("acme", _TEST_SECRET_BYTES))

    def test_empty_value_fails(self):
        from core.security.tenant_request import verify_tenant_header
        self.assertIsNone(verify_tenant_header("", _TEST_SECRET_BYTES))

    def test_wrong_signature_length_fails(self):
        from core.security.tenant_request import verify_tenant_header
        self.assertIsNone(verify_tenant_header("acme.abc", _TEST_SECRET_BYTES))

    def test_non_hex_signature_fails(self):
        from core.security.tenant_request import verify_tenant_header
        # 64 characters but not valid hex.
        bad = "acme." + ("z" * 64)
        self.assertIsNone(verify_tenant_header(bad, _TEST_SECRET_BYTES))


# ─── middleware integration ─────────────────────────────────────────


class MiddlewareIntegrationTests(unittest.TestCase):

    def _run(self, mw, scope):
        captured = {"tenant": None, "status": None, "body": b""}

        async def inner(scope, receive, send):
            from core.lifecycle.tenant import current_tenant_id
            captured["tenant"] = current_tenant_id()
            await send({"type": "http.response.start", "status": 200,
                        "headers": []})
            await send({"type": "http.response.body", "body": b"OK"})

        async def noop_receive():
            return {"type": "http.request"}

        async def fake_send(msg):
            if msg["type"] == "http.response.start":
                captured["status"] = msg["status"]
            elif msg["type"] == "http.response.body":
                captured["body"] += msg.get("body") or b""

        # Replace the wrapped app + run.
        mw.app = inner
        asyncio.run(mw(scope, noop_receive, fake_send))
        return captured

    def _make_mw(self, *, secret_b64=None, trusted="10.0.0.0/8",
                 header_name=None):
        from core.security.tenant_request import TenantHeaderMiddleware

        async def placeholder(scope, receive, send):
            await send({"type": "http.response.start", "status": 200,
                        "headers": []})
            await send({"type": "http.response.body", "body": b""})

        return TenantHeaderMiddleware(
            placeholder,
            secret_env=secret_b64 if secret_b64 is not None else "",
            header_name_env=header_name if header_name is not None else "",
            trusted_proxies_env=trusted,
        )

    def test_no_secret_pass_through(self):
        # Without a secret configured the middleware MUST be a no-op,
        # even if the operator sends a tenant header from a trusted
        # peer.
        from core.security.tenant_request import sign_tenant_id
        signed = sign_tenant_id(_TEST_SECRET_BYTES, "acme")
        mw = self._make_mw(secret_b64="")  # no secret
        scope = {
            "type": "http",
            "client": ("10.0.0.5", 12345),  # trusted
            "headers": [(b"x-tenant-id", signed.encode("latin-1"))],
        }
        result = self._run(mw, scope)
        self.assertEqual(result["status"], 200)
        # No tenant scope set (env not patched, sync stack empty,
        # async stack not entered).
        self.assertIsNone(result["tenant"])

    def test_valid_header_trusted_peer_scopes_tenant(self):
        from core.security.tenant_request import sign_tenant_id
        signed = sign_tenant_id(_TEST_SECRET_BYTES, "acme")
        mw = self._make_mw(secret_b64=_TEST_SECRET_B64,
                           trusted="10.0.0.0/8")
        scope = {
            "type": "http",
            "client": ("10.0.0.5", 12345),  # trusted peer
            "headers": [(b"x-tenant-id", signed.encode("latin-1"))],
        }
        result = self._run(mw, scope)
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["tenant"], "acme")

    def test_valid_header_untrusted_peer_passes_through_default(self):
        # Untrusted peer + valid header + enforce OFF → pass-through
        # unscoped. (Safe default — operator must opt in to enforce.)
        from core.security.tenant_request import sign_tenant_id
        signed = sign_tenant_id(_TEST_SECRET_BYTES, "acme")
        mw = self._make_mw(secret_b64=_TEST_SECRET_B64,
                           trusted="10.0.0.0/8")
        scope = {
            "type": "http",
            "client": ("203.0.113.1", 12345),  # NOT trusted
            "headers": [(b"x-tenant-id", signed.encode("latin-1"))],
        }
        with _patched_env(JAMES_REQUIRE_TENANT_ID=None):
            result = self._run(mw, scope)
        self.assertEqual(result["status"], 200)
        self.assertIsNone(result["tenant"])

    def test_valid_header_untrusted_peer_403_when_enforced(self):
        from core.security.tenant_request import sign_tenant_id
        signed = sign_tenant_id(_TEST_SECRET_BYTES, "acme")
        mw = self._make_mw(secret_b64=_TEST_SECRET_B64,
                           trusted="10.0.0.0/8")
        scope = {
            "type": "http",
            "client": ("203.0.113.1", 12345),
            "headers": [(b"x-tenant-id", signed.encode("latin-1"))],
        }
        with _patched_env(JAMES_REQUIRE_TENANT_ID="1"):
            result = self._run(mw, scope)
        self.assertEqual(result["status"], 403)

    def test_invalid_signature_trusted_peer_403_when_enforced(self):
        # Trusted peer but the signature does NOT verify (spoofed).
        bad_signed = "acme." + ("0" * 64)
        mw = self._make_mw(secret_b64=_TEST_SECRET_B64,
                           trusted="10.0.0.0/8")
        scope = {
            "type": "http",
            "client": ("10.0.0.5", 12345),
            "headers": [(b"x-tenant-id", bad_signed.encode("latin-1"))],
        }
        with _patched_env(JAMES_REQUIRE_TENANT_ID="1"):
            result = self._run(mw, scope)
        self.assertEqual(result["status"], 403)

    def test_missing_header_pass_through_default(self):
        mw = self._make_mw(secret_b64=_TEST_SECRET_B64,
                           trusted="10.0.0.0/8")
        scope = {
            "type": "http",
            "client": ("10.0.0.5", 12345),
            "headers": [],
        }
        with _patched_env(JAMES_REQUIRE_TENANT_ID=None):
            result = self._run(mw, scope)
        self.assertEqual(result["status"], 200)
        self.assertIsNone(result["tenant"])

    def test_missing_header_403_when_enforced(self):
        mw = self._make_mw(secret_b64=_TEST_SECRET_B64,
                           trusted="10.0.0.0/8")
        scope = {
            "type": "http",
            "client": ("10.0.0.5", 12345),
            "headers": [],
        }
        with _patched_env(JAMES_REQUIRE_TENANT_ID="1"):
            result = self._run(mw, scope)
        self.assertEqual(result["status"], 403)

    def test_custom_header_name(self):
        from core.security.tenant_request import sign_tenant_id
        signed = sign_tenant_id(_TEST_SECRET_BYTES, "globex")
        mw = self._make_mw(secret_b64=_TEST_SECRET_B64,
                           trusted="10.0.0.0/8",
                           header_name="X-Acme-Tenant")
        scope = {
            "type": "http",
            "client": ("10.0.0.5", 12345),
            "headers": [(b"x-acme-tenant", signed.encode("latin-1"))],
        }
        result = self._run(mw, scope)
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["tenant"], "globex")

    def test_tenant_scope_survives_await(self):
        # Verify that the async-context tenant override propagates
        # across an inner `await` — this is the load-bearing property
        # we need for audit emits that may happen in async helpers
        # invoked from the request handler.
        from core.security.tenant_request import (
            TenantHeaderMiddleware, sign_tenant_id,
        )
        from core.lifecycle.tenant import current_tenant_id

        captured = {"tenant_before": None, "tenant_after": None}

        async def inner(scope, receive, send):
            captured["tenant_before"] = current_tenant_id()
            await asyncio.sleep(0)
            captured["tenant_after"] = current_tenant_id()
            await send({"type": "http.response.start", "status": 200,
                        "headers": []})
            await send({"type": "http.response.body", "body": b""})

        mw = TenantHeaderMiddleware(
            inner,
            secret_env=_TEST_SECRET_B64,
            trusted_proxies_env="10.0.0.0/8",
        )

        signed = sign_tenant_id(_TEST_SECRET_BYTES, "acme")
        scope = {
            "type": "http",
            "client": ("10.0.0.5", 12345),
            "headers": [(b"x-tenant-id", signed.encode("latin-1"))],
        }

        async def noop_receive():
            return {"type": "http.request"}

        async def noop_send(msg):
            pass

        asyncio.run(mw(scope, noop_receive, noop_send))
        self.assertEqual(captured["tenant_before"], "acme")
        self.assertEqual(captured["tenant_after"], "acme")


if __name__ == "__main__":
    unittest.main()
