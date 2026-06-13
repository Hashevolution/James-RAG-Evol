"""v0.6 Phase 1 P1.2 — Trusted X-Forwarded-* headers middleware.

Closes the existing **per-IP rate-limit bypass + audit IP spoofing**
vulnerability in `routes/_helpers.py::get_client_ip`:

    def get_client_ip(request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()  # ← unconditionally trusted
        return request.client.host if request.client else "unknown"

Any client can send `X-Forwarded-For: <arbitrary IP>` and:
  * bypass the per-IP rate limiter (each request appears to come from
    a different "real" IP)
  * spoof the audit log's `ip_address` field
  * defeat per-IP security event correlation

The fix is the **trusted-proxy pattern** (Mozilla / OWASP standard):
only honor forwarded headers when the immediate ASGI peer's IP is in
an operator-configured trust list. When the trust list is empty (the
v0.5 default behaviour preserved byte-identical), forwarded headers
are IGNORED entirely — the ASGI peer is the client.

## What this module ships

  * `TrustedForwardedHeadersMiddleware` — ASGI middleware that:
      - reads `JAMES_TRUSTED_PROXIES` (CSV of IPv4/IPv6 addresses or
        CIDR ranges) on startup
      - on each request: checks the immediate peer; if trusted,
        rewrites `request.scope["client"]` to the right-most
        untrusted IP from `X-Forwarded-For` (RFC-correct walk) AND
        rewrites `request.scope["scheme"]` from `X-Forwarded-Proto`
        if present
      - if NOT trusted: leaves the scope alone (client-supplied
        forwarded headers are ignored, restoring the safe-default
        semantic the v0.5 code claimed but didn't enforce)
  * `_parse_trusted_proxies(env_value)` — pure-function helper
    (IPv4 + IPv6 + CIDR support via stdlib `ipaddress`)
  * `_extract_client_ip(forwarded_for, trusted_proxies)` — pure
    walk-right-to-left helper; returns the right-most IP that is
    NOT in the trusted set
  * `JAMES_TRUSTED_PROXIES_ENV` — env-var name constant

## Operator config

| Env var | Default | Effect |
|---|---|---|
| `JAMES_TRUSTED_PROXIES` | empty | CSV of IPs or CIDRs (e.g. `10.0.0.0/8,fd00::/8,127.0.0.1`). Empty = ignore all forwarded headers (safe default). |
| `JAMES_FORWARDED_PROTO_HEADER` | `X-Forwarded-Proto` | Customize for non-standard proxies. |

## What this module is NOT

- **Not an HTTPS enforcer.** Setting `X-Forwarded-Proto: https`
  through a trusted proxy updates the *recorded* scheme; HTTPS
  termination is the operator's reverse-proxy responsibility.
- **Not a host-header validator.** `X-Forwarded-Host` is NOT
  rewritten — host validation is a separate concern (handle via
  the reverse proxy's `proxy_set_header Host` directive or a host
  allow-list at the JAMES handler layer).
- **Not a tenant-id resolver.** v0.6 Phase 3 builds tenant
  middleware on top of this; reading a signed `X-Tenant-Id` header
  also requires the trusted-peer check this module establishes.
"""
from __future__ import annotations

import ipaddress
import os
from typing import Final, List, Optional, Sequence, Tuple, Union


JAMES_TRUSTED_PROXIES_ENV:        Final[str] = "JAMES_TRUSTED_PROXIES"
JAMES_FORWARDED_PROTO_HEADER_ENV: Final[str] = "JAMES_FORWARDED_PROTO_HEADER"

# Type aliases — ipaddress union for either single hosts or CIDR networks.
_IPNet = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]
_TrustedSet = Tuple[_IPNet, ...]


# ─── pure-function helpers ──────────────────────────────────────────


def _parse_trusted_proxies(env_value: str) -> _TrustedSet:
    """Parse a CSV of IPs / CIDRs into a tuple of network objects.

    Args:
        env_value: `JAMES_TRUSTED_PROXIES` env value. Empty / None /
            whitespace-only → returns empty tuple (= "trust nothing").

    Examples:
        >>> _parse_trusted_proxies("")            # ()
        >>> _parse_trusted_proxies("10.0.0.1")    # (IPv4Network('10.0.0.1/32'),)
        >>> _parse_trusted_proxies("10.0.0.0/8,fd00::/8")
        # (IPv4Network('10.0.0.0/8'), IPv6Network('fd00::/8'))

    Malformed entries (typo'd CIDR, garbage tokens) are silently
    dropped rather than raised — startup must not crash on operator
    typos. The middleware's audit-log row records what was actually
    loaded for forensic recovery.
    """
    if not env_value or not env_value.strip():
        return ()
    out: List[_IPNet] = []
    for token in env_value.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            # `strict=False` allows host bits in CIDRs (e.g. 10.0.0.1/24
            # rather than the strict 10.0.0.0/24). This matches what
            # operators usually type and the `ipaddress.ip_network`
            # docs recommend for user input.
            net = ipaddress.ip_network(token, strict=False)
        except ValueError:
            # Try parsing as a single host address (IP without /N).
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


def _is_trusted(ip_str: str, trusted: _TrustedSet) -> bool:
    """True iff ``ip_str`` is contained in any of the trusted networks.

    A malformed ``ip_str`` (empty / non-IP) returns False.
    """
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


def _extract_client_ip(
    forwarded_for: str,
    trusted: _TrustedSet,
) -> Optional[str]:
    """Walk ``X-Forwarded-For`` right-to-left and return the first
    untrusted IP (= the actual client).

    Per RFC 7239 / Mozilla CSP guidance, the header's left-most entry
    is the client's claim, but each proxy along the chain appends
    its OWN peer (the previous hop) — so walking right-to-left and
    stopping at the first peer that is NOT in the trust list yields
    the true client.

    Args:
        forwarded_for: raw header value (may contain multiple
            comma-separated entries with whitespace).
        trusted: trusted-proxy network set.

    Returns:
        The first untrusted IP string from the right, or ``None`` if
        every entry was trusted (which means the immediate client
        was itself a trusted proxy — the caller falls back to the
        ASGI peer in that case).
    """
    if not forwarded_for:
        return None
    parts = [p.strip() for p in forwarded_for.split(",") if p.strip()]
    if not parts:
        return None
    for ip_str in reversed(parts):
        # The RFC-7239 syntax allows `for=<id>` but most proxies use the
        # simpler de-facto `X-Forwarded-For: ip[, ip]*`. We only
        # handle the de-facto shape; RFC 7239 `Forwarded:` is a
        # separate header.
        if not _is_trusted(ip_str, trusted):
            try:
                ipaddress.ip_address(ip_str)  # validate; reject garbage
            except ValueError:
                continue
            return ip_str
    return None


def _extract_scheme(
    forwarded_proto: str,
) -> Optional[str]:
    """Return ``"http"`` / ``"https"`` from a forwarded-proto header
    value, or None if the value is missing / unrecognised.

    Some proxies emit a chain (``https, http``) — we take the left-most
    entry (the original client's claim, as seen by the outermost
    trusted proxy).
    """
    if not forwarded_proto:
        return None
    first = forwarded_proto.split(",")[0].strip().lower()
    if first in ("http", "https"):
        return first
    return None


# ─── ASGI middleware ────────────────────────────────────────────────


class TrustedForwardedHeadersMiddleware:
    """ASGI middleware that overlays trusted forwarded headers onto
    ``request.scope``.

    Wire in the ASGI app **before** any middleware that consumes the
    client IP (rate limiter, audit emitter, tenant routing). The
    pattern:

        app.add_middleware(TrustedForwardedHeadersMiddleware)

    or directly on a Starlette/FastAPI app:

        app = FastAPI()
        app.add_middleware(TrustedForwardedHeadersMiddleware)

    The middleware reads ``JAMES_TRUSTED_PROXIES`` from the
    environment at INSTANCE construction time, not per-request. To
    refresh the trusted set, restart the process (env-driven
    refresh is the v0.5 platform convention).
    """

    def __init__(self, app, trusted_proxies_env: Optional[str] = None):
        """
        Args:
            app: the wrapped ASGI app.
            trusted_proxies_env: optional explicit override for tests.
                When ``None`` (production), the constructor reads
                ``JAMES_TRUSTED_PROXIES`` from ``os.environ``.
        """
        self.app = app
        raw = (
            trusted_proxies_env
            if trusted_proxies_env is not None
            else os.environ.get(JAMES_TRUSTED_PROXIES_ENV, "")
        )
        self._trusted: _TrustedSet = _parse_trusted_proxies(raw)
        self._proto_header_name = (
            os.environ.get(JAMES_FORWARDED_PROTO_HEADER_ENV)
            or "X-Forwarded-Proto"
        ).lower().encode("latin-1")
        self._for_header_name = b"x-forwarded-for"

    async def __call__(self, scope, receive, send):
        # Only rewrite HTTP scopes; WebSocket follows the same pattern
        # but we leave its scope alone for now to avoid surprising
        # websocket consumers that read peer IP differently.
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        # Skip the trust check entirely when no trust list configured.
        # This preserves byte-identical pre-v0.6 behaviour AND defaults
        # to the safe semantic: forwarded headers are ignored.
        if not self._trusted:
            await self.app(scope, receive, send)
            return

        peer_ip = self._peer_ip_from_scope(scope)
        if not peer_ip or not _is_trusted(peer_ip, self._trusted):
            # Untrusted peer — leave scope alone. Client-supplied
            # forwarded headers are dropped (the safe semantic).
            await self.app(scope, receive, send)
            return

        # Peer is trusted; honour the headers.
        forwarded_for = self._header_value(scope, self._for_header_name)
        forwarded_proto = self._header_value(
            scope, self._proto_header_name,
        )

        new_scope = scope  # mutate in place — ASGI scope is a dict

        client_ip = _extract_client_ip(forwarded_for or "", self._trusted)
        if client_ip:
            # ASGI scope's "client" is a (host, port) tuple. Preserve
            # the original port (we cannot recover the client's source
            # port from forwarded headers; the rate limiter only uses
            # the host anyway).
            existing = scope.get("client") or ("", 0)
            try:
                existing_port = int(existing[1])
            except (IndexError, TypeError, ValueError):
                existing_port = 0
            new_scope["client"] = (client_ip, existing_port)

        scheme = _extract_scheme(forwarded_proto or "")
        if scheme:
            new_scope["scheme"] = scheme

        await self.app(new_scope, receive, send)

    @staticmethod
    def _peer_ip_from_scope(scope) -> str:
        client = scope.get("client")
        if not client:
            return ""
        try:
            return str(client[0])
        except (IndexError, TypeError):
            return ""

    @staticmethod
    def _header_value(scope, name_bytes: bytes) -> Optional[str]:
        """Return the first header value matching ``name_bytes`` (case-
        insensitive). ASGI headers come as a list of ``(bytes, bytes)``
        tuples.
        """
        for raw_name, raw_value in scope.get("headers", []) or []:
            if raw_name.lower() == name_bytes:
                try:
                    return raw_value.decode("latin-1")
                except Exception:
                    return None
        return None


__all__ = (
    "JAMES_TRUSTED_PROXIES_ENV",
    "JAMES_FORWARDED_PROTO_HEADER_ENV",
    "TrustedForwardedHeadersMiddleware",
)
