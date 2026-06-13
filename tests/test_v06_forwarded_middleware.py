"""v0.6 Phase 1 P1.2 — Trusted forwarded-headers middleware tests.

Covers the security fix for the pre-v0.6 vulnerability:
``routes/_helpers.py::get_client_ip`` blindly trusted any client-
supplied ``X-Forwarded-For`` header, letting attackers bypass the
per-IP rate limiter and spoof audit `ip_address` rows.

Coverage:

`_parse_trusted_proxies`:
  * Empty / whitespace → empty tuple
  * Single IPv4 / IPv6 host → /32 or /128 network
  * IPv4 + IPv6 CIDR mix
  * Malformed tokens silently dropped

`_is_trusted`:
  * IP in network → True
  * IP outside network → False
  * Empty / non-IP → False
  * IPv4 vs IPv6 mismatch → False

`_extract_client_ip`:
  * Single untrusted entry → returns it
  * Right-most untrusted in multi-hop chain → walks correctly
  * All-trusted chain → None (caller falls back to peer)
  * Malformed entries skipped
  * Empty / None → None

`_extract_scheme`:
  * "https" / "http" → returned lowercase
  * Chain like "https, http" → first
  * Unknown / empty → None

Middleware integration (via TestClient):
  * No trust list configured → headers ignored (default safe)
  * Trust list configured + trusted peer → scope rewritten
  * Trust list configured + untrusted peer → scope unchanged
  * X-Forwarded-Proto rewrites `scope["scheme"]`
  * X-Forwarded-For rewrites `scope["client"][0]`
  * Spoofing attempt from untrusted peer ignored
  * CIDR-range trust works
  * Multiple hops with mixed trust → correct client extraction

Run:
  python -m unittest tests.test_v06_forwarded_middleware
"""
from __future__ import annotations

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


# ─── pure-function helpers ──────────────────────────────────────────


class ParseTrustedProxiesTests(unittest.TestCase):
    def test_empty_string_returns_empty(self):
        from core.security.forwarded import _parse_trusted_proxies
        self.assertEqual(_parse_trusted_proxies(""), ())

    def test_whitespace_returns_empty(self):
        from core.security.forwarded import _parse_trusted_proxies
        self.assertEqual(_parse_trusted_proxies("   "), ())

    def test_single_ipv4_host(self):
        from core.security.forwarded import _parse_trusted_proxies
        import ipaddress
        result = _parse_trusted_proxies("10.0.0.1")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], ipaddress.IPv4Network("10.0.0.1/32"))

    def test_single_ipv4_cidr(self):
        from core.security.forwarded import _parse_trusted_proxies
        import ipaddress
        result = _parse_trusted_proxies("10.0.0.0/8")
        self.assertEqual(result[0], ipaddress.IPv4Network("10.0.0.0/8"))

    def test_ipv6_host_and_cidr_mix(self):
        from core.security.forwarded import _parse_trusted_proxies
        import ipaddress
        result = _parse_trusted_proxies("10.0.0.0/8, fd00::/8, ::1")
        nets = set(result)
        self.assertIn(ipaddress.IPv4Network("10.0.0.0/8"), nets)
        self.assertIn(ipaddress.IPv6Network("fd00::/8"), nets)
        self.assertIn(ipaddress.IPv6Network("::1/128"), nets)

    def test_malformed_tokens_silently_dropped(self):
        from core.security.forwarded import _parse_trusted_proxies
        # 'garbage' + '999.999.999.999' silently dropped; valid kept.
        result = _parse_trusted_proxies("10.0.0.1, garbage, 999.999.999.999, fd00::/8")
        self.assertEqual(len(result), 2)


class IsTrustedTests(unittest.TestCase):
    def test_ipv4_inside_network(self):
        from core.security.forwarded import _is_trusted, _parse_trusted_proxies
        trusted = _parse_trusted_proxies("10.0.0.0/8")
        self.assertTrue(_is_trusted("10.255.255.255", trusted))

    def test_ipv4_outside_network(self):
        from core.security.forwarded import _is_trusted, _parse_trusted_proxies
        trusted = _parse_trusted_proxies("10.0.0.0/8")
        self.assertFalse(_is_trusted("192.168.1.1", trusted))

    def test_ipv6_inside_network(self):
        from core.security.forwarded import _is_trusted, _parse_trusted_proxies
        trusted = _parse_trusted_proxies("fd00::/8")
        self.assertTrue(_is_trusted("fd00::1", trusted))

    def test_ipv4_against_ipv6_network_is_false(self):
        from core.security.forwarded import _is_trusted, _parse_trusted_proxies
        trusted = _parse_trusted_proxies("fd00::/8")
        self.assertFalse(_is_trusted("10.0.0.1", trusted))

    def test_empty_ip_is_false(self):
        from core.security.forwarded import _is_trusted, _parse_trusted_proxies
        trusted = _parse_trusted_proxies("10.0.0.0/8")
        self.assertFalse(_is_trusted("", trusted))

    def test_garbage_ip_is_false(self):
        from core.security.forwarded import _is_trusted, _parse_trusted_proxies
        trusted = _parse_trusted_proxies("10.0.0.0/8")
        self.assertFalse(_is_trusted("not-an-ip", trusted))


class ExtractClientIpTests(unittest.TestCase):
    def test_single_untrusted_entry(self):
        from core.security.forwarded import _extract_client_ip, _parse_trusted_proxies
        trusted = _parse_trusted_proxies("10.0.0.0/8")
        self.assertEqual(_extract_client_ip("203.0.113.1", trusted), "203.0.113.1")

    def test_right_most_untrusted_in_chain(self):
        from core.security.forwarded import _extract_client_ip, _parse_trusted_proxies
        trusted = _parse_trusted_proxies("10.0.0.0/8")
        # Client → outermost proxy (10.0.0.1) → inner proxy (10.0.0.2);
        # walking right-to-left: 10.0.0.2 (trusted) → 10.0.0.1 (trusted)
        # → 203.0.113.99 (untrusted; this is the real client).
        chain = "203.0.113.99, 10.0.0.1, 10.0.0.2"
        self.assertEqual(_extract_client_ip(chain, trusted), "203.0.113.99")

    def test_all_trusted_chain_returns_none(self):
        from core.security.forwarded import _extract_client_ip, _parse_trusted_proxies
        trusted = _parse_trusted_proxies("10.0.0.0/8")
        chain = "10.0.0.1, 10.0.0.2"
        self.assertIsNone(_extract_client_ip(chain, trusted))

    def test_empty_returns_none(self):
        from core.security.forwarded import _extract_client_ip, _parse_trusted_proxies
        trusted = _parse_trusted_proxies("10.0.0.0/8")
        self.assertIsNone(_extract_client_ip("", trusted))

    def test_malformed_entries_skipped(self):
        from core.security.forwarded import _extract_client_ip, _parse_trusted_proxies
        trusted = _parse_trusted_proxies("10.0.0.0/8")
        # garbage entries skipped; the real client 203.0.113.99 should
        # still emerge from the right-to-left walk.
        chain = "203.0.113.99, garbage, 10.0.0.1"
        self.assertEqual(_extract_client_ip(chain, trusted), "203.0.113.99")


class ExtractSchemeTests(unittest.TestCase):
    def test_https_returned(self):
        from core.security.forwarded import _extract_scheme
        self.assertEqual(_extract_scheme("https"), "https")

    def test_http_returned(self):
        from core.security.forwarded import _extract_scheme
        self.assertEqual(_extract_scheme("http"), "http")

    def test_chain_picks_first(self):
        from core.security.forwarded import _extract_scheme
        self.assertEqual(_extract_scheme("https, http"), "https")

    def test_unknown_returns_none(self):
        from core.security.forwarded import _extract_scheme
        self.assertIsNone(_extract_scheme("ftp"))

    def test_empty_returns_none(self):
        from core.security.forwarded import _extract_scheme
        self.assertIsNone(_extract_scheme(""))


# ─── middleware integration ─────────────────────────────────────────


class MiddlewareIntegrationTests(unittest.TestCase):
    """Use a Starlette app with the middleware installed; assert that
    `request.client` and `request.url.scheme` reflect the trusted-
    forwarded overlay."""

    def _make_app(self, trusted_env: str):
        from starlette.applications import Starlette
        from starlette.responses import JSONResponse
        from starlette.routing import Route
        from core.security.forwarded import TrustedForwardedHeadersMiddleware

        async def reflect(request):
            return JSONResponse({
                "client_host": request.client.host if request.client else None,
                "scheme": request.url.scheme,
            })

        app = Starlette(routes=[Route("/reflect", reflect)])
        app.add_middleware(
            TrustedForwardedHeadersMiddleware,
            trusted_proxies_env=trusted_env,
        )
        return app

    def _client(self, app, peer_ip: str):
        # TestClient sets the ASGI scope's `client` to ("testclient", 50000)
        # by default. To simulate an arbitrary peer IP we pass the
        # `client` arg.
        from starlette.testclient import TestClient
        return TestClient(app, base_url="http://testserver", raise_server_exceptions=True), peer_ip

    def test_no_trust_list_ignores_forwarded_headers(self):
        # Even when the client sends X-Forwarded-For, an empty trust
        # list means the middleware is a no-op → client.host is the
        # ASGI peer ("testclient"), NOT the spoofed value.
        app = self._make_app("")
        from starlette.testclient import TestClient
        c = TestClient(app)
        r = c.get(
            "/reflect",
            headers={"X-Forwarded-For": "203.0.113.99"},
        )
        body = r.json()
        self.assertNotEqual(body["client_host"], "203.0.113.99",
                            "empty trust list MUST ignore forwarded headers")

    def test_trusted_peer_overlays_x_forwarded_for(self):
        # Set the trust list to the testclient's own peer address
        # ("testclient" — Starlette assigns 'testclient' as the host).
        # In starlette TestClient the peer is "testclient" string,
        # which is not a valid IP — so the safest way to test the
        # positive path is to use 127.0.0.1 in the trust list AND
        # override the client tuple via raw scope. We use the raw
        # `httpx` transport approach instead.
        from starlette.testclient import TestClient
        from starlette.applications import Starlette
        from starlette.responses import JSONResponse
        from starlette.routing import Route
        from core.security.forwarded import TrustedForwardedHeadersMiddleware

        async def reflect(request):
            return JSONResponse({
                "client_host": request.client.host if request.client else None,
                "scheme": request.url.scheme,
            })

        app = Starlette(routes=[Route("/reflect", reflect)])
        # Trust the loopback range so the TestClient peer (which
        # appears as 127.0.0.1 to our ASGI app when wired correctly)
        # is honored. NOTE: starlette's TestClient by default sets
        # client to ("testclient", 50000); we therefore EXPLICITLY
        # trust the literal "testclient" by way of an env-bypass:
        # the middleware first attempts ipaddress.ip_address(peer);
        # "testclient" fails → middleware treats peer as untrusted →
        # forwarded headers ignored. To test the trusted path we
        # need a real IP peer.
        app.add_middleware(
            TrustedForwardedHeadersMiddleware,
            trusted_proxies_env="127.0.0.0/8",
        )
        c = TestClient(app, base_url="http://127.0.0.1")
        # The TestClient sends the request through a synthetic ASGI
        # transport; the resulting scope's `client` defaults to
        # ("testclient", 50000) — NOT 127.0.0.1. So even with the
        # right trust list, the middleware sees peer="testclient",
        # `_is_trusted` returns False, and forwarded headers are
        # ignored. This is the SAFE failure mode: we'd rather drop
        # legitimate forwarded headers than honour spoofed ones.
        # The integration test therefore asserts the SAFE semantic
        # holds; a follow-up integration test (with a real socket
        # in front of uvicorn) would verify the positive trusted-
        # peer path. For coverage of the positive path we use a
        # direct ASGI scope test in the next test below.
        r = c.get(
            "/reflect",
            headers={"X-Forwarded-For": "203.0.113.99"},
        )
        body = r.json()
        self.assertNotEqual(body["client_host"], "203.0.113.99",
                            "TestClient peer 'testclient' is not in any IP "
                            "trust list — safe semantic preserved")

    def test_direct_scope_trusted_peer_path(self):
        """Direct ASGI scope invocation — exercises the positive
        trusted-peer rewrite path that TestClient cannot reach."""
        import asyncio
        from core.security.forwarded import TrustedForwardedHeadersMiddleware

        captured = {}

        async def inner(scope, receive, send):
            captured["client"] = scope.get("client")
            captured["scheme"] = scope.get("scheme")
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        mw = TrustedForwardedHeadersMiddleware(
            inner, trusted_proxies_env="10.0.0.0/8",
        )

        scope = {
            "type": "http",
            "client": ("10.0.0.5", 12345),  # trusted peer
            "scheme": "http",
            "headers": [
                (b"x-forwarded-for", b"203.0.113.99"),
                (b"x-forwarded-proto", b"https"),
            ],
        }

        async def noop_receive():
            return {"type": "http.request"}

        async def noop_send(msg):
            pass

        asyncio.run(mw(scope, noop_receive, noop_send))

        self.assertEqual(captured["client"][0], "203.0.113.99")
        self.assertEqual(captured["scheme"], "https")

    def test_direct_scope_untrusted_peer_drops_forwarded(self):
        """When the peer is NOT in the trust list, forwarded headers
        are silently ignored — the safe default."""
        import asyncio
        from core.security.forwarded import TrustedForwardedHeadersMiddleware

        captured = {}

        async def inner(scope, receive, send):
            captured["client"] = scope.get("client")
            captured["scheme"] = scope.get("scheme")
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        mw = TrustedForwardedHeadersMiddleware(
            inner, trusted_proxies_env="10.0.0.0/8",
        )

        scope = {
            "type": "http",
            "client": ("203.0.113.10", 12345),  # UNTRUSTED peer
            "scheme": "http",
            "headers": [
                (b"x-forwarded-for", b"198.51.100.42"),  # spoof attempt
                (b"x-forwarded-proto", b"https"),
            ],
        }

        async def noop_receive():
            return {"type": "http.request"}

        async def noop_send(msg):
            pass

        asyncio.run(mw(scope, noop_receive, noop_send))

        # Peer untrusted → headers dropped → original values preserved.
        self.assertEqual(captured["client"][0], "203.0.113.10",
                         "untrusted peer's forwarded header MUST be ignored")
        self.assertEqual(captured["scheme"], "http")

    def test_direct_scope_no_trust_list_passthrough(self):
        """Empty trust list = no-op pass-through (byte-identical to
        pre-v0.6 absence of middleware)."""
        import asyncio
        from core.security.forwarded import TrustedForwardedHeadersMiddleware

        captured = {}

        async def inner(scope, receive, send):
            captured["client"] = scope.get("client")
            captured["scheme"] = scope.get("scheme")
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        mw = TrustedForwardedHeadersMiddleware(inner, trusted_proxies_env="")

        scope = {
            "type": "http",
            "client": ("203.0.113.10", 12345),
            "scheme": "http",
            "headers": [
                (b"x-forwarded-for", b"198.51.100.42"),
                (b"x-forwarded-proto", b"https"),
            ],
        }

        async def noop_receive():
            return {"type": "http.request"}

        async def noop_send(msg):
            pass

        asyncio.run(mw(scope, noop_receive, noop_send))

        self.assertEqual(captured["client"][0], "203.0.113.10")
        self.assertEqual(captured["scheme"], "http")

    def test_direct_scope_multi_hop_chain(self):
        """X-Forwarded-For with multiple hops: walk right-to-left
        through trusted proxies to find the actual client."""
        import asyncio
        from core.security.forwarded import TrustedForwardedHeadersMiddleware

        captured = {}

        async def inner(scope, receive, send):
            captured["client"] = scope.get("client")
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        mw = TrustedForwardedHeadersMiddleware(
            inner, trusted_proxies_env="10.0.0.0/8",
        )

        # Two trusted proxies in front of the actual client:
        #   client → outer proxy (10.0.0.5) → inner proxy (10.0.0.6)
        # X-Forwarded-For records left-to-right: client, outer, inner
        scope = {
            "type": "http",
            "client": ("10.0.0.6", 12345),
            "scheme": "http",
            "headers": [
                (b"x-forwarded-for", b"203.0.113.99, 10.0.0.5, 10.0.0.6"),
            ],
        }

        async def noop_receive():
            return {"type": "http.request"}

        async def noop_send(msg):
            pass

        asyncio.run(mw(scope, noop_receive, noop_send))

        self.assertEqual(captured["client"][0], "203.0.113.99",
                         "multi-hop trusted chain must walk right-to-left "
                         "to the first untrusted IP")


if __name__ == "__main__":
    unittest.main()
