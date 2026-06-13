"""v0.6 Track C — per-request CSP nonce primitive.

Per `docs/handovers/v0.5-close-2026-06-12.md` §5.3 + UI #6
inline-style audit §4.1 Option A. Mother-platform: ships the nonce
primitive + the directive-composition seam in
`core.security.headers.build_security_headers`. The default
behaviour is **unchanged** — generating a per-request nonce by
itself doesn't alter any response header. An operator graduates to
nonce-bound CSP by setting one of the new env flags below.

## What this module ships

  * `new_nonce()` — cryptographically secure per-request nonce
    (16 bytes from ``secrets.token_urlsafe``). Returns a
    base64url-encoded ASCII string suitable for direct
    interpolation into a CSP directive (`nonce-<value>`) or a
    ``<style nonce="X">`` / ``<script nonce="X">`` HTML attribute.
  * `JAMES_CSP_USE_NONCE_SCRIPT_ENV` / `JAMES_CSP_USE_NONCE_STYLE_ENV`
    — operator-facing env-var names. When truthy, the
    corresponding directive will receive a `nonce-<value>` token
    composed by ``build_security_headers``.
  * `csp_use_nonce_for_scripts()` / `csp_use_nonce_for_styles()` —
    boolean predicates the middleware consults.

## Why two flags

The two directives have very different readiness states (per the
UI #6 audit §4):

  * **`script-src`** is already `'self'` only (zero inline scripts
    in any page after UI #4 PR #855). Adding `'nonce-<value>'` is
    **additive and safe** — modern browsers prefer the nonce, older
    ones see the unchanged `'self'`. Operators can set the flag
    today without any HTML rewrite.

  * **`style-src`** contains `'unsafe-inline'` because 409 inline
    ``style="..."`` attributes remain across the 4 HTML pages.
    Adding `'nonce-<value>'` triggers CSP3 §6.6.2.4: modern
    browsers ignore `'unsafe-inline'` when ANY nonce is present →
    every inline attribute becomes a violation. Setting this flag
    BEFORE the inline-style mass conversion **WILL break the UI**.
    The flag exists to graduate cleanly once the migration lands.

The split lets the operator graduate `script-src` to strict-mode
nonce binding TODAY while leaving `style-src` for a later cycle
that picks Option A (per-style nonce injection) or Option B (mass
conversion to utility classes) from the UI #6 audit.

## Integration

Wire-in lives in
`server_llmwiki.py::security_headers_middleware`:

    nonce = new_nonce()
    request.state.csp_nonce = nonce
    headers = build_security_headers(
        script_nonce=(nonce if csp_use_nonce_for_scripts() else None),
        style_nonce=(nonce if csp_use_nonce_for_styles() else None),
    )

The nonce stays available on ``request.state.csp_nonce`` for any
downstream template renderer that wants to mint a
``<style nonce="X">`` block or a ``<script nonce="X">`` block.

## What this module is NOT

- **Not an HTML rewriter.** Inline ``style="..."`` attributes
  cannot be nonce-bound — CSP nonces only apply to ``<style>`` and
  ``<script>`` BLOCK elements (CSP3 §6.6). Mass attribute conversion
  is Option B in the UI #6 audit and is out of scope for this
  primitive.
- **Not a per-request middleware.** The middleware wire-in lives in
  `server_llmwiki.py` (one place); this module is the pure-function
  primitive that the middleware composes with.
- **Not coupled to enforce mode.** A nonce generates whether the
  CSP header is `report-only`, `enforce`, or absent. The flags
  decide whether the nonce token appears in the CSP directive.
"""
from __future__ import annotations

import os
import secrets
from typing import Final


# Number of random bytes for the nonce. 16 bytes → 22 ASCII
# characters after base64url encoding. CSP3 doesn't mandate a
# specific length; browsers accept anything from a few characters
# upward. 16 bytes is the recommended minimum for replay-attack
# resistance (matches Mozilla's CSP-nonce guidance).
_NONCE_BYTES: Final[int] = 16


JAMES_CSP_USE_NONCE_SCRIPT_ENV: Final[str] = "JAMES_CSP_USE_NONCE_SCRIPT"
JAMES_CSP_USE_NONCE_STYLE_ENV:  Final[str] = "JAMES_CSP_USE_NONCE_STYLE"


def new_nonce() -> str:
    """Generate a fresh per-request CSP nonce.

    Returns a base64url-encoded string with no padding (the
    ``=`` characters are stripped). Suitable for direct
    interpolation into a CSP directive and into HTML attributes
    without further escaping.

    Each call returns an independent value backed by
    :func:`secrets.token_urlsafe`. The function is pure: no global
    state, no module-level cache.
    """
    return secrets.token_urlsafe(_NONCE_BYTES)


def _truthy(value: str) -> bool:
    if not value:
        return False
    return value.strip().lower() in ("1", "true", "yes", "on", "enabled")


def csp_use_nonce_for_scripts() -> bool:
    """True iff ``JAMES_CSP_USE_NONCE_SCRIPT`` is set + truthy.

    When True, the middleware passes a fresh nonce to
    ``build_security_headers(script_nonce=...)`` so the
    ``script-src`` directive carries ``'nonce-<value>'``.

    Safe to set today: ``script-src`` is already ``'self'``-only
    (zero inline scripts after UI #4 PR #855), so adding a nonce
    is additive — modern browsers see + accept the nonce; older
    browsers see the unchanged ``'self'``. No HTML rewrite required.
    """
    return _truthy(os.environ.get(JAMES_CSP_USE_NONCE_SCRIPT_ENV, ""))


def csp_use_nonce_for_styles() -> bool:
    """True iff ``JAMES_CSP_USE_NONCE_STYLE`` is set + truthy.

    When True, the middleware passes a fresh nonce to
    ``build_security_headers(style_nonce=...)`` so the
    ``style-src`` directive REPLACES ``'unsafe-inline'`` with
    ``'nonce-<value>'``.

    **Setting this BEFORE the inline-style mass conversion lands
    will break the UI** — 409 inline ``style="..."`` attributes
    become CSP violations under modern browsers' CSP3 §6.6.2.4
    rule (any nonce in the directive disables ``'unsafe-inline'``
    fallback). Reserved for operators who have completed the
    Option A or Option B migration from
    ``docs/reviews/v0.5-ui-6-inline-style-audit.md`` §4.
    """
    return _truthy(os.environ.get(JAMES_CSP_USE_NONCE_STYLE_ENV, ""))


__all__ = (
    "JAMES_CSP_USE_NONCE_SCRIPT_ENV",
    "JAMES_CSP_USE_NONCE_STYLE_ENV",
    "csp_use_nonce_for_scripts",
    "csp_use_nonce_for_styles",
    "new_nonce",
)
