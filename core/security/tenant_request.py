"""v0.6 Phase 3 P3.1 — per-request tenant resolution middleware.

Sits between `TrustedForwardedHeadersMiddleware` (Phase 1 P1.2) and
the rest of the FastAPI stack. Parses a signed ``X-Tenant-Id``
header that an upstream reverse proxy emits per request, verifies
the HMAC-SHA256 signature against an operator-shared secret, and
wraps the rest of the request handling in
:func:`core.lifecycle.tenant.with_tenant_id_async` so every audit
emit downstream stamps the correct tenant.

## Why HMAC over the header value

The naive pattern — proxy sets ``X-Tenant-Id: acme``, JAMES trusts
it — has the same defect that ``X-Forwarded-For`` had pre-P1.2:
any client that can talk to JAMES directly can spoof the header
and pivot into another tenant's audit + replay surface. **P1.2's
trusted-peer gate alone is not enough** — if the reverse proxy is
mis-configured (forgets to strip inbound ``X-Tenant-Id`` from
external clients) the value still reaches JAMES.

The defence is a **proxy-shared HMAC secret**. The proxy computes
``hmac_sha256(secret, tenant_id).hex()`` and sets the header to
``<tenant_id>.<signature>``. JAMES re-computes the signature and
compares constant-time. A client that does not know the secret
cannot mint a valid header even if they bypass the trusted-peer
gate.

## What this module ships

  * ``TenantHeaderMiddleware`` — ASGI middleware (class-based) that:
      - reads ``JAMES_TENANT_HEADER_SECRET`` (base64-encoded HMAC
        key) at instance construction
      - reads ``JAMES_TENANT_HEADER_NAME`` (default ``X-Tenant-Id``)
      - per request: looks up the header, splits on the last ``.``,
        compares signature constant-time
      - on valid + trusted peer: runs the rest of the request inside
        ``async with with_tenant_id_async(tenant_id):`` so
        ``current_tenant_id()`` returns the resolved value for every
        downstream call (including audit emits)
      - on invalid signature OR untrusted peer:
          * if ``is_tenant_isolation_enforced()`` (= JAMES_REQUIRE_
            TENANT_ID is set): returns 403
          * else: pass-through unscoped (preserves single-tenant
            v0.5 behaviour byte-identical)
  * ``sign_tenant_id(secret, tenant_id)`` — utility for reverse-proxy
    operators + integration tests. Returns the canonical header
    value ``<tenant_id>.<signature>``.
  * ``verify_tenant_header(value, secret)`` → ``Optional[str]`` —
    pure-function helper. Returns the validated ``tenant_id`` on
    successful HMAC verification, ``None`` on any failure.

## Operator config

| Env var | Default | Effect |
|---|---|---|
| ``JAMES_TENANT_HEADER_SECRET`` | empty | Base64-encoded HMAC-SHA256 key shared with the reverse proxy. Empty = middleware is a no-op pass-through (preserves single-tenant default). |
| ``JAMES_TENANT_HEADER_NAME`` | ``X-Tenant-Id`` | Customize the header name if the operator's reverse proxy emits a different one (e.g. ``X-Acme-Tenant``). |
| ``JAMES_REQUIRE_TENANT_ID`` | unset | When truthy + secret set: requests with missing or invalid tenant header are REJECTED (403). Default off → unauthenticated requests pass through unscoped (single-tenant mode). |

## Wiring order

`server_llmwiki.py` registers the middlewares LIFO. The desired
inbound order is:

    incoming request
       → `TrustedForwardedHeadersMiddleware` (rewrite scope["client"])
       → `TenantHeaderMiddleware` (resolve tenant from signed header)
       → `@app.middleware("http")` `security_headers_middleware`
       → `@app.middleware("http")` `rate_limit_middleware`
       → handler

So in source order `add_middleware(TenantHeaderMiddleware)` MUST
come AFTER `add_middleware(TrustedForwardedHeadersMiddleware)`
(later `add_middleware` calls become *outer* layers per Starlette
docs).

## What this module is NOT

- **Not a tenant authoriser.** Verifying the signed header proves
  the proxy claimed this tenant; it does NOT prove the *user* in
  the JWT belongs to that tenant. JWT-vs-tenant cross-check is a
  separate concern (handle in the auth layer with a tenant claim
  in the JWT).
- **Not a replay-attack defender.** The signature is over the
  tenant id alone — no timestamp / nonce. Replay within the same
  trusted-peer context is undefined. A trusted-peer that goes
  rogue can replay any captured header against any other tenant
  the rogue peer normally serves; defence is rotating the secret
  + per-tenant secrets (future v0.7+).
- **Not a per-tenant rate limiter.** The rate-limit middleware
  keys off client IP. Per-tenant rate limiting is a separate v1.0
  Dim D deliverable.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import os
from typing import Final, Optional, Tuple

from core.lifecycle.tenant import (
    is_tenant_isolation_enforced,
    with_tenant_id_async,
)


JAMES_TENANT_HEADER_SECRET_ENV: Final[str] = "JAMES_TENANT_HEADER_SECRET"
JAMES_TENANT_HEADER_NAME_ENV:   Final[str] = "JAMES_TENANT_HEADER_NAME"
JAMES_TRUSTED_PROXIES_ENV:      Final[str] = "JAMES_TRUSTED_PROXIES"

_DEFAULT_HEADER_NAME = "X-Tenant-Id"


# ─── pure-function helpers ──────────────────────────────────────────


def _decode_secret(b64_value: str) -> Optional[bytes]:
    """Decode a base64 secret. Returns None on any failure (empty
    value / wrong padding / non-base64). The middleware uses None as
    "no secret configured → no-op pass-through".
    """
    if not b64_value or not b64_value.strip():
        return None
    try:
        return base64.b64decode(b64_value.strip(), validate=True)
    except (ValueError, base64.binascii.Error):
        return None


def sign_tenant_id(secret: bytes, tenant_id: str) -> str:
    """Return the canonical signed-header value for ``tenant_id``.

    Format: ``<tenant_id>.<signature_hex>`` where
    ``signature = hmac_sha256(secret, tenant_id).hexdigest()``.

    Used by:

      * Reverse-proxy operators (translate this signing into nginx /
        Caddy / Traefik config — example in
        ``docs/deployment/v0.6-saas-tenant-isolation.md``)
      * Integration tests (mint valid headers without standing up
        the proxy)
    """
    sig = hmac.new(secret, tenant_id.encode("utf-8"), hashlib.sha256)
    return f"{tenant_id}.{sig.hexdigest()}"


def verify_tenant_header(value: str, secret: bytes) -> Optional[str]:
    """Verify a signed ``X-Tenant-Id`` header value.

    Returns the validated ``tenant_id`` on success, ``None`` on any
    failure (no dot separator / wrong signature length / signature
    mismatch / empty value / corrupted UTF-8).

    Signature comparison uses :func:`hmac.compare_digest` to avoid
    timing leaks of the signature byte-by-byte.
    """
    if not value or "." not in value or not secret:
        return None
    # Split on the LAST dot — tenant_ids may contain dots (e.g.
    # acme.corp). The signature is always the trailing 64 hex chars.
    idx = value.rfind(".")
    tenant_id = value[:idx]
    sig_hex = value[idx + 1 :]
    if not tenant_id or not sig_hex:
        return None
    # HMAC-SHA256 is 32 bytes = 64 hex chars. Reject any other length
    # early — protects compare_digest from comparing wildly different
    # length strings (still constant-time, but cheap shortcut).
    if len(sig_hex) != 64:
        return None
    try:
        sig_bytes = bytes.fromhex(sig_hex)
    except ValueError:
        return None
    expected = hmac.new(secret, tenant_id.encode("utf-8"),
                        hashlib.sha256).digest()
    if not hmac.compare_digest(sig_bytes, expected):
        return None
    return tenant_id


def _parse_trusted_proxies(env_value: str) -> Tuple:
    """Same shape as
    :func:`core.security.forwarded._parse_trusted_proxies` — kept
    inline rather than imported because we only need the peer-trust
    check at request time, and avoiding the cross-module import keeps
    the middleware's behaviour testable in isolation.
    """
    out = []
    if not env_value or not env_value.strip():
        return tuple()
    for token in env_value.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            net = ipaddress.ip_network(token, strict=False)
        except ValueError:
            try:
                addr = ipaddress.ip_address(token)
                if isinstance(addr, ipaddress.IPv4Address):
                    net = ipaddress.IPv4Network(f"{addr}/32")
                else:
                    net = ipaddress.IPv6Network(f"{addr}/128")
            except ValueError:
                continue
        out.append(net)
    return tuple(out)


def _is_trusted(ip_str: str, trusted: Tuple) -> bool:
    if not ip_str or not trusted:
        return False
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    for net in trusted:
        if ip.version != net.version:
            continue
        if ip in net:
            return True
    return False


# ─── ASGI middleware ────────────────────────────────────────────────


class TenantHeaderMiddleware:
    """Resolve the per-request tenant from a signed ``X-Tenant-Id``
    header + wrap the request in :func:`with_tenant_id_async` so
    every audit emit downstream stamps the tenant.

    Construct AFTER ``TrustedForwardedHeadersMiddleware`` in the
    `add_middleware` chain (so it ends up inner-of-forwarded — by
    the time this middleware runs, the trusted-forwarded overlay has
    already rewritten ``scope["client"]`` to the true client IP,
    but the ASGI peer that delivered the request — i.e. the
    reverse proxy — is what we need to check against the trust
    list).

    Because of that interaction we re-parse ``JAMES_TRUSTED_PROXIES``
    here too — the trust check uses the ORIGINAL ASGI peer (the
    proxy), not the rewritten ``scope["client"]`` (the end client).
    A future refactor could share state with
    ``TrustedForwardedHeadersMiddleware`` via a sidecar scope key,
    but the duplication keeps the modules independently testable.

    On a verified header: enters ``async with with_tenant_id_async``
    around the rest of the request lifecycle, so audit emits that
    reach ``core.lifecycle.tenant.current_tenant_id()`` see the
    resolved tenant.

    On a missing / invalid header:
      * if ``JAMES_REQUIRE_TENANT_ID`` is truthy AND a secret is
        configured: returns 403 with a minimal JSON body
      * otherwise: pass-through unscoped (single-tenant default)
    """

    def __init__(
        self,
        app,
        *,
        secret_env: Optional[str] = None,
        header_name_env: Optional[str] = None,
        trusted_proxies_env: Optional[str] = None,
    ):
        self.app = app
        raw_secret = (
            secret_env if secret_env is not None
            else os.environ.get(JAMES_TENANT_HEADER_SECRET_ENV, "")
        )
        self._secret: Optional[bytes] = _decode_secret(raw_secret)
        header_name = (
            header_name_env if header_name_env is not None
            else os.environ.get(JAMES_TENANT_HEADER_NAME_ENV, "")
        )
        if not header_name:
            header_name = _DEFAULT_HEADER_NAME
        self._header_name_bytes = header_name.lower().encode("latin-1")
        # Re-parse the trust list for the peer-IP check (see class
        # docstring rationale).
        raw_trust = (
            trusted_proxies_env if trusted_proxies_env is not None
            else os.environ.get(JAMES_TRUSTED_PROXIES_ENV, "")
        )
        self._trusted = _parse_trusted_proxies(raw_trust)

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        # No secret configured → middleware is a no-op pass-through.
        # Preserves byte-identical pre-Phase-3 behaviour.
        if self._secret is None:
            await self.app(scope, receive, send)
            return

        peer_ip = self._peer_ip(scope)
        peer_trusted = _is_trusted(peer_ip, self._trusted) if self._trusted else False

        header_value = self._header_value(scope)
        tenant_id: Optional[str] = None
        if header_value and peer_trusted:
            tenant_id = verify_tenant_header(header_value, self._secret)

        if tenant_id is None:
            # Missing / invalid / untrusted peer.
            if is_tenant_isolation_enforced():
                await self._send_forbidden(send)
                return
            # Default: pass through unscoped.
            await self.app(scope, receive, send)
            return

        # Valid tenant → wrap the entire downstream call.
        async with with_tenant_id_async(tenant_id):
            await self.app(scope, receive, send)

    @staticmethod
    def _peer_ip(scope) -> str:
        client = scope.get("client")
        if not client:
            return ""
        try:
            return str(client[0])
        except (IndexError, TypeError):
            return ""

    def _header_value(self, scope) -> Optional[str]:
        for raw_name, raw_value in scope.get("headers", []) or []:
            if raw_name.lower() == self._header_name_bytes:
                try:
                    return raw_value.decode("latin-1")
                except Exception:
                    return None
        return None

    @staticmethod
    async def _send_forbidden(send):
        body = json.dumps({
            "detail": "tenant header required (JAMES_REQUIRE_TENANT_ID=1)",
        }).encode("utf-8")
        await send({
            "type":    "http.response.start",
            "status":  403,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("latin-1")),
            ],
        })
        await send({"type": "http.response.body", "body": body})


__all__ = (
    "JAMES_TENANT_HEADER_SECRET_ENV",
    "JAMES_TENANT_HEADER_NAME_ENV",
    "TenantHeaderMiddleware",
    "sign_tenant_id",
    "verify_tenant_header",
)
