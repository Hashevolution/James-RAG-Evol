"""v0.5 — HTTP security headers builder.

Pure-function module that builds the security-header dict applied
by `server_llmwiki.py`'s `security_headers_middleware`. Each header
is the answer to a specific enterprise procurement / OWASP /
EN-301-549 check-item:

  * **Content-Security-Policy** — XSS / injection defense
    (CSP Level 3). Three modes: `off`, `report-only`, `enforce`.
    Default = `report-only` (ships the policy as a Report-Only
    header so the browser logs violations without breaking the
    existing inline-style usage; operator graduates to `enforce`
    once `docs/reviews/v0.5-ui-6-inline-style-audit.md` Option A
    nonce middleware OR Option B mass conversion lands).
  * **X-Frame-Options: DENY** — clickjacking defense.
    Belt-and-suspenders with CSP `frame-ancestors 'none'`.
  * **X-Content-Type-Options: nosniff** — MIME-sniffing defense.
  * **Referrer-Policy: strict-origin-when-cross-origin** — limits
    leaked referrer URLs while keeping same-origin Refer for
    legitimate analytics.
  * **Permissions-Policy** — disables sensors (geolocation,
    camera, microphone, payment, USB) that JAMES does not use.
  * **Strict-Transport-Security** — HSTS preload-ready when
    operator opts in via `JAMES_HSTS_MAX_AGE` env. Default unset
    so a non-HTTPS dev/local deploy isn't poisoned by a stuck
    HSTS pin.

## Env-driven config

| Env var | Default | Effect |
|---|---|---|
| `JAMES_CSP_MODE` | `report-only` | One of `off`, `report-only`, `enforce`. `off` omits the CSP header entirely (local-dev). |
| `JAMES_CSP_REPORT_URI` | `""` | Optional. URL the browser POSTs CSP violation reports to. Empty = no `report-uri` directive. |
| `JAMES_HSTS_MAX_AGE` | `0` | Seconds. `0` = HSTS header omitted (default for dev / non-HTTPS). Production sets `31536000` (1 year) or `63072000` (2 years for preload). |
| `JAMES_HSTS_INCLUDE_SUBDOMAINS` | `0` | `1` to add `includeSubDomains` directive. |
| `JAMES_HSTS_PRELOAD` | `0` | `1` to add `preload` directive (operator must register with hstspreload.org separately). |

## What this module is NOT

- **Not a CSP nonce generator.** Nonces are a separate primitive
  (`docs/reviews/v0.5-ui-6-inline-style-audit.md` §4.1 Option A);
  this module ships the policy headers, the nonce middleware
  lands as a separate PR when operator scopes the SaaS-pilot CSP.
- **Not a request-bound state machine.** Headers are response-
  scoped only. The middleware applies them per-response without
  reading any request state beyond the path (for static-file
  caching alignment).
- **Not a CSRF protector.** CSRF is a request-side defense (token
  validation in routes), orthogonal to response headers.
"""
from __future__ import annotations

import os
from typing import Dict, Final, Literal, Optional


# ─── CSP policy (report-only by default) ──────────────────────────────
#
# Source-list rationale:
#
#   default-src 'self'      — local-first floor
#   script-src 'self'       — v0.5 UI #4 PR #855 extracted last inline
#                             script → strict mode safe
#   style-src 'self'
#     'unsafe-inline'       — 409 inline `style="..."` attributes still
#                             remain; report-only mode lets us SEE
#                             violations without breaking the UI.
#                             Removed once nonce middleware OR mass
#                             conversion lands.
#   img-src 'self' data:    — `data:` for inline SVG icons + brand-pulse
#                             icons (chat.js `brainPulseSvg`)
#   font-src 'self'
#     https://fonts.gstatic.com — Inter + JetBrains Mono loaded by
#                                  tokens.css from Google Fonts CDN
#   connect-src 'self'      — XHR + fetch to same-origin only
#   frame-ancestors 'none'  — clickjacking defense (belt-and-suspenders
#                             with X-Frame-Options: DENY)
#   base-uri 'self'         — limit <base href> abuse
#   form-action 'self'      — limit form post targets
#   object-src 'none'       — disable <object> / <embed> / <applet>
#   upgrade-insecure-requests — auto-upgrade http → https on browsers
#                               that support it; safe when served over
#                               HTTPS, no-op on HTTP

CSP_DIRECTIVES_DEFAULT: Final[Dict[str, str]] = {
    "default-src":     "'self'",
    "script-src":      "'self'",
    "style-src":       "'self' 'unsafe-inline' "
                       "https://fonts.googleapis.com",
    "img-src":         "'self' data:",
    "font-src":        "'self' https://fonts.gstatic.com",
    "connect-src":     "'self'",
    "frame-ancestors": "'none'",
    "base-uri":        "'self'",
    "form-action":     "'self'",
    "object-src":      "'none'",
}


CspMode = Literal["off", "report-only", "enforce"]


def _read_csp_mode() -> CspMode:
    """Resolve `JAMES_CSP_MODE` to one of three modes."""
    raw = (os.environ.get("JAMES_CSP_MODE") or "report-only").strip().lower()
    if raw in ("off", "disable", "disabled", "0", "false", "no"):
        return "off"
    if raw in ("enforce", "enforced", "strict", "on", "1", "true", "yes"):
        return "enforce"
    return "report-only"


def _compose_directive(
    base: str,
    nonce: str,
    replace_unsafe_inline: bool,
) -> str:
    """Append a ``'nonce-<value>'`` token to a CSP source list.

    Per v0.6 Track C (CSP nonce middleware).

    * ``script-src`` callers pass ``replace_unsafe_inline=False`` —
      the directive doesn't carry ``'unsafe-inline'`` today, so the
      nonce is purely additive.
    * ``style-src`` callers pass ``replace_unsafe_inline=True`` so
      ``'unsafe-inline'`` is stripped (modern browsers ignore it
      when a nonce is present anyway, per CSP3 §6.6.2.4; stripping
      it makes the intent explicit + keeps older browsers from
      falling back to inline-anything).
    """
    if replace_unsafe_inline:
        # Drop the `'unsafe-inline'` token. The split-rejoin keeps
        # whitespace tidy and is robust to single / double quotes.
        kept = [tok for tok in base.split() if tok != "'unsafe-inline'"]
    else:
        kept = base.split()
    kept.append(f"'nonce-{nonce}'")
    return " ".join(kept)


def _build_csp_value(
    report_uri: str = "",
    *,
    script_nonce: Optional[str] = None,
    style_nonce: Optional[str] = None,
) -> str:
    """Compose the CSP directive string from `CSP_DIRECTIVES_DEFAULT`.

    Directives are joined `key value; key value; ...`. Trailing
    `upgrade-insecure-requests` is appended (it has no source list).
    If `report_uri` is non-empty, a `report-uri <uri>` directive is
    appended too.

    v0.6 Track C — per-request nonce composition:
      * ``script_nonce`` (when set): adds ``'nonce-<value>'`` to
        ``script-src``. ``script-src`` is already ``'self'``-only,
        so this is additive and safe to enable today.
      * ``style_nonce`` (when set): REPLACES ``'unsafe-inline'`` in
        ``style-src`` with ``'nonce-<value>'``. Operator must
        complete the inline-style migration first or the UI breaks.
    """
    parts = []
    for key, value in CSP_DIRECTIVES_DEFAULT.items():
        if key == "script-src" and script_nonce:
            value = _compose_directive(
                value, script_nonce, replace_unsafe_inline=False,
            )
        elif key == "style-src" and style_nonce:
            value = _compose_directive(
                value, style_nonce, replace_unsafe_inline=True,
            )
        parts.append(f"{key} {value}")
    parts.append("upgrade-insecure-requests")
    if report_uri:
        parts.append(f"report-uri {report_uri}")
    return "; ".join(parts)


def _csp_header_name(mode: CspMode) -> str:
    """Resolve the header name for the active CSP mode.

    Report-only mode uses `Content-Security-Policy-Report-Only` so
    the browser emits violation reports without enforcing the policy
    (the UI keeps working through any current inline-style usage).
    """
    if mode == "enforce":
        return "Content-Security-Policy"
    return "Content-Security-Policy-Report-Only"


# ─── HSTS ─────────────────────────────────────────────────────────────


def _build_hsts() -> str:
    """Build the Strict-Transport-Security value from env.

    Returns the empty string when `JAMES_HSTS_MAX_AGE` is `0` or
    unset — the caller then omits the header entirely (the right
    behaviour for dev / non-HTTPS deploys).
    """
    max_age = (os.environ.get("JAMES_HSTS_MAX_AGE") or "0").strip()
    try:
        max_age_int = int(max_age)
    except ValueError:
        return ""
    if max_age_int <= 0:
        return ""
    parts = [f"max-age={max_age_int}"]
    if _truthy(os.environ.get("JAMES_HSTS_INCLUDE_SUBDOMAINS")):
        parts.append("includeSubDomains")
    if _truthy(os.environ.get("JAMES_HSTS_PRELOAD")):
        parts.append("preload")
    return "; ".join(parts)


def _truthy(value: str) -> bool:
    """True iff value is a recognised truthy env-flag string."""
    if not value:
        return False
    return value.strip().lower() in ("1", "true", "yes", "on", "enabled")


# ─── Permissions-Policy ───────────────────────────────────────────────
#
# JAMES does not use any of these sensor / device APIs — explicitly
# denying them shrinks the attack surface and signals to enterprise
# evaluators that sensor-leak is not a JAMES concern. Permissions-
# Policy syntax: `feature=()` blocks the feature on this origin.

_PERMISSIONS_POLICY: Final[str] = ", ".join([
    "accelerometer=()",
    "camera=()",
    "geolocation=()",
    "gyroscope=()",
    "magnetometer=()",
    "microphone=()",
    "payment=()",
    "usb=()",
])


# ─── Public API ───────────────────────────────────────────────────────


def build_security_headers(
    *,
    script_nonce: Optional[str] = None,
    style_nonce: Optional[str] = None,
) -> Dict[str, str]:
    """Return the security-header dict for the current env config.

    Caller (the FastAPI middleware) iterates the dict and writes
    each `(name, value)` pair onto the response. The caller is
    responsible for not overwriting existing headers — but this
    function never returns header names that a route handler would
    legitimately set itself, so collisions are not expected.

    Empty values are returned for headers that env config has
    disabled (e.g., HSTS with `max-age=0`); the caller is expected
    to skip headers whose value is empty.

    v0.6 Track C — per-request CSP nonce kwargs:
      * ``script_nonce`` — when set, ``script-src`` carries
        ``'nonce-<value>'`` (additive; ``script-src`` is already
        strict-mode-clean per UI #4)
      * ``style_nonce`` — when set, ``style-src`` REPLACES
        ``'unsafe-inline'`` with ``'nonce-<value>'`` (operator
        must complete the UI #6 inline-style migration first)

    Both kwargs default to ``None`` → byte-identical pre-v0.6
    behaviour. The middleware decides whether to pass them based
    on ``JAMES_CSP_USE_NONCE_SCRIPT`` / ``_STYLE`` env flags.
    """
    out: Dict[str, str] = {}

    # CSP (default report-only)
    mode = _read_csp_mode()
    if mode != "off":
        report_uri = (os.environ.get("JAMES_CSP_REPORT_URI") or "").strip()
        out[_csp_header_name(mode)] = _build_csp_value(
            report_uri,
            script_nonce=script_nonce,
            style_nonce=style_nonce,
        )

    # Belt-and-suspenders / always-on
    out["X-Frame-Options"] = "DENY"
    out["X-Content-Type-Options"] = "nosniff"
    out["Referrer-Policy"] = "strict-origin-when-cross-origin"
    out["Permissions-Policy"] = _PERMISSIONS_POLICY

    # HSTS — opt-in via env
    hsts = _build_hsts()
    if hsts:
        out["Strict-Transport-Security"] = hsts

    return out


__all__ = (
    "build_security_headers",
    "CSP_DIRECTIVES_DEFAULT",
)
