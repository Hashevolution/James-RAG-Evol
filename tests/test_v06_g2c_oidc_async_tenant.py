"""v0.6 G2.c — OIDC resolver + async-task-aware tenant variant.

Two complementary primitives land in the same PR per v0.5 close
handover §5.1 Track A:

  * ``core.security.approval_evidence._resolve_oidc`` +
    ``register_oidc_validator`` — surface OIDC token validation as a
    pluggable hook. No bundled JWKS verifier yet; the hook is the
    contract the deployment layer fills in.
  * ``core.lifecycle.tenant.with_tenant_id_async`` — contextvars-backed
    async context manager so FastAPI / asyncio handlers can scope a
    tenant_id across ``await`` points + into child tasks created
    inside the block.

Coverage:

OIDC:
  * No env vars → None (resolution doesn't reach the hook)
  * Env vars set but no validator → None (mother-platform contract:
    no IdP dependency by default)
  * Validator returns valid claims → ApprovalEvidence with source=oidc,
    principal=claims["sub"], expires_at derived from exp claim
  * Validator returns None → None
  * Validator raises → None (transient failures don't crash)
  * OIDC ordered ahead of explicit + POSIX in current_approval_evidence
  * Signature segment hashed (JWS shape "h.p.s") vs whole-token
    fallback (non-JWS shape)

Async tenant:
  * with_tenant_id_async overrides on entry, restores on exit
  * Override propagates across an `await asyncio.sleep(0)`
  * Override propagates into a child task created inside the block
  * A sibling task created OUTSIDE the block does NOT inherit it
  * Async stack takes precedence over the sync threading.local stack
  * Nested async overrides — innermost wins

Run:
  python -m unittest tests.test_v06_g2c_oidc_async_tenant
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─── OIDC resolver tests ─────────────────────────────────────────────


class OIDCResolverTests(unittest.TestCase):
    def setUp(self):
        # Snapshot env so each test starts clean. The module-level
        # validator hook is also snapshotted so test pollution doesn't
        # leak across cases.
        from core.security import approval_evidence as ae
        self._ae = ae
        self._env_snapshot = {
            k: os.environ.get(k)
            for k in (
                ae.JAMES_OIDC_ISSUER_ENV,
                ae.JAMES_OIDC_TOKEN_ENV,
                ae.JAMES_OIDC_AUDIENCE_ENV,
                ae.JAMES_APPROVAL_PRINCIPAL_ENV,
                ae.JAMES_APPROVAL_EVIDENCE_B64_ENV,
            )
        }
        for k in self._env_snapshot:
            os.environ.pop(k, None)
        self._validator_snapshot = ae._oidc_validator
        ae.register_oidc_validator(None)

    def tearDown(self):
        for k, v in self._env_snapshot.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._ae.register_oidc_validator(self._validator_snapshot)

    def _set_oidc_env(self, issuer="https://idp.example.com",
                     token="hhh.ppp.sssignature",
                     audience="acme"):
        os.environ[self._ae.JAMES_OIDC_ISSUER_ENV] = issuer
        os.environ[self._ae.JAMES_OIDC_TOKEN_ENV] = token
        os.environ[self._ae.JAMES_OIDC_AUDIENCE_ENV] = audience

    def test_no_env_returns_none(self):
        self.assertIsNone(self._ae._resolve_oidc())

    def test_env_set_but_no_validator_returns_none(self):
        self._set_oidc_env()
        # No validator registered — mother-platform default. Must
        # NOT fall through to the explicit / POSIX resolvers (the
        # caller calls _resolve_oidc directly here).
        self.assertIsNone(self._ae._resolve_oidc())

    def test_validator_returns_claims_yields_oidc_evidence(self):
        self._set_oidc_env()
        captured = {}

        def fake_validator(token, issuer, audience):
            captured["token"] = token
            captured["issuer"] = issuer
            captured["audience"] = audience
            return {"sub": "alice@acme.com", "exp": 9999999999}

        self._ae.register_oidc_validator(fake_validator)
        ev = self._ae._resolve_oidc()
        self.assertIsNotNone(ev)
        self.assertEqual(ev.source, "oidc")
        self.assertEqual(ev.principal, "alice@acme.com")
        # captured: validator received the env values verbatim.
        self.assertEqual(captured["token"], "hhh.ppp.sssignature")
        self.assertEqual(captured["issuer"], "https://idp.example.com")
        self.assertEqual(captured["audience"], "acme")
        # expires_at populated from exp claim.
        self.assertTrue(ev.expires_at)

    def test_validator_returns_none_yields_no_evidence(self):
        self._set_oidc_env()
        self._ae.register_oidc_validator(lambda t, i, a: None)
        self.assertIsNone(self._ae._resolve_oidc())

    def test_validator_raises_yields_no_evidence(self):
        self._set_oidc_env()

        def boom(*_):
            raise RuntimeError("transient JWKS fetch failed")

        self._ae.register_oidc_validator(boom)
        self.assertIsNone(self._ae._resolve_oidc())

    def test_signature_hash_uses_jws_segment_when_dotted(self):
        # JWS shape: header.payload.signature → hash the signature.
        self._set_oidc_env(token="aaa.bbb.SIGSEGMENT")
        self._ae.register_oidc_validator(lambda t, i, a: {"sub": "x"})
        ev = self._ae._resolve_oidc()
        import hashlib
        expected = hashlib.sha256(b"SIGSEGMENT").hexdigest()
        self.assertEqual(ev.evidence_hash, expected)

    def test_signature_hash_falls_back_to_whole_token_for_non_jws(self):
        # Not a JWS — hash the full token bytes.
        self._set_oidc_env(token="opaque-bearer-token")
        self._ae.register_oidc_validator(lambda t, i, a: {"sub": "x"})
        ev = self._ae._resolve_oidc()
        import hashlib
        expected = hashlib.sha256(b"opaque-bearer-token").hexdigest()
        self.assertEqual(ev.evidence_hash, expected)

    def test_resolves_oidc_ahead_of_explicit_and_posix(self):
        # All three sources available — OIDC wins.
        self._set_oidc_env()
        self._ae.register_oidc_validator(
            lambda t, i, a: {"sub": "oidc-principal"}
        )
        os.environ[self._ae.JAMES_APPROVAL_PRINCIPAL_ENV] = "explicit-principal"
        os.environ[self._ae.JAMES_APPROVAL_EVIDENCE_B64_ENV] = "ZXZpZGVuY2U="

        ev = self._ae.current_approval_evidence()
        self.assertIsNotNone(ev)
        self.assertEqual(ev.source, "oidc")
        self.assertEqual(ev.principal, "oidc-principal")

    def test_falls_through_to_explicit_when_oidc_unavailable(self):
        # OIDC env vars unset → resolution moves to explicit.
        os.environ[self._ae.JAMES_APPROVAL_PRINCIPAL_ENV] = "ci-bot"
        os.environ[self._ae.JAMES_APPROVAL_EVIDENCE_B64_ENV] = "ZXZpZGVuY2U="
        ev = self._ae.current_approval_evidence(allow_posix_fallback=False)
        self.assertIsNotNone(ev)
        self.assertEqual(ev.source, "explicit")
        self.assertEqual(ev.principal, "ci-bot")

    def test_invalid_validator_return_shape_is_rejected(self):
        # Validator returns a non-mapping → resolver returns None.
        self._set_oidc_env()
        self._ae.register_oidc_validator(lambda t, i, a: ["sub", "alice"])
        self.assertIsNone(self._ae._resolve_oidc())

    def test_missing_sub_claim_is_rejected(self):
        self._set_oidc_env()
        self._ae.register_oidc_validator(lambda t, i, a: {"aud": "acme"})
        self.assertIsNone(self._ae._resolve_oidc())


# ─── async-aware with_tenant_id tests ────────────────────────────────


class AsyncTenantTests(unittest.TestCase):
    """`with_tenant_id_async` must propagate across awaits + child tasks."""

    def setUp(self):
        from core.lifecycle import tenant
        self._t = tenant
        # Clear ambient state — env var, sync stack, async stack.
        self._env_snapshot = os.environ.get(tenant.JAMES_TENANT_ID_ENV)
        os.environ.pop(tenant.JAMES_TENANT_ID_ENV, None)
        tenant._local.stack = []  # sync stack
        tenant._async_stack.set(None)  # async stack

    def tearDown(self):
        if self._env_snapshot is None:
            os.environ.pop(self._t.JAMES_TENANT_ID_ENV, None)
        else:
            os.environ[self._t.JAMES_TENANT_ID_ENV] = self._env_snapshot

    def _run(self, coro):
        return asyncio.run(coro)

    def test_async_override_visible_inside_block(self):
        async def case():
            self.assertIsNone(self._t.current_tenant_id())
            async with self._t.with_tenant_id_async("acme"):
                self.assertEqual(self._t.current_tenant_id(), "acme")
            self.assertIsNone(self._t.current_tenant_id())
        self._run(case())

    def test_async_override_survives_await(self):
        async def case():
            async with self._t.with_tenant_id_async("acme"):
                await asyncio.sleep(0)
                self.assertEqual(self._t.current_tenant_id(), "acme")
        self._run(case())

    def test_child_task_inherits_override(self):
        async def case():
            seen = []

            async def child():
                seen.append(self._t.current_tenant_id())

            async with self._t.with_tenant_id_async("acme"):
                await asyncio.create_task(child())
            self.assertEqual(seen, ["acme"])
        self._run(case())

    def test_sibling_task_created_outside_does_not_inherit(self):
        async def case():
            seen = []

            async def sibling():
                # Yield once so the parent has time to enter the
                # `async with` block — but the sibling was created
                # before the block opened, so its contextvars
                # snapshot pre-dates the override.
                await asyncio.sleep(0)
                seen.append(self._t.current_tenant_id())

            task = asyncio.create_task(sibling())
            async with self._t.with_tenant_id_async("acme"):
                await asyncio.sleep(0)
            await task
            self.assertEqual(seen, [None])
        self._run(case())

    def test_async_override_takes_precedence_over_sync_stack(self):
        async def case():
            # Mimic an ambient sync override (this is unusual but
            # possible — e.g., a wrapping sync helper called from
            # an async handler via `loop.call_soon`). The async
            # override must win.
            self._t._stack().append("sync-tenant")
            try:
                self.assertEqual(self._t.current_tenant_id(), "sync-tenant")
                async with self._t.with_tenant_id_async("async-tenant"):
                    self.assertEqual(self._t.current_tenant_id(), "async-tenant")
                self.assertEqual(self._t.current_tenant_id(), "sync-tenant")
            finally:
                self._t._stack().pop()
        self._run(case())

    def test_nested_async_overrides_innermost_wins(self):
        async def case():
            async with self._t.with_tenant_id_async("outer"):
                self.assertEqual(self._t.current_tenant_id(), "outer")
                async with self._t.with_tenant_id_async("inner"):
                    self.assertEqual(self._t.current_tenant_id(), "inner")
                self.assertEqual(self._t.current_tenant_id(), "outer")
            self.assertIsNone(self._t.current_tenant_id())
        self._run(case())

    def test_async_override_to_none_blocks_env_fallback(self):
        async def case():
            # Set env var so the unscoped read would resolve.
            os.environ[self._t.JAMES_TENANT_ID_ENV] = "envtenant"
            self.assertEqual(self._t.current_tenant_id(), "envtenant")
            async with self._t.with_tenant_id_async(None):
                # Explicit None override blocks fallback (matches the
                # sync `with_tenant_id(None)` semantic).
                self.assertIsNone(self._t.current_tenant_id())
            # After exit, env fallback restored.
            self.assertEqual(self._t.current_tenant_id(), "envtenant")
        self._run(case())


if __name__ == "__main__":
    unittest.main()
