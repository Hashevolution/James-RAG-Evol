"""v0.5 G2.a — verified approver-principal evidence primitive.

Per `docs/reviews/v0.5-b2-multi-tenant-isolation.md` §4 — first
sub-PR of the G2 SaaS-readiness contract. Mother-platform: ships
the contract surface + the POSIX resolver only. OIDC discovery,
SSH-session evidence, explicit-token verification land in G2.b /
G2.c when the first customer's IdP scoping surfaces.

## The contract

`core/change_request.py` currently requires `approver_username`
(free-form string) in the audit log before a self-evolution patch
can auto-apply. The string is operator-written and unverifiable
after the fact. G2 proposes binding the username to a verifiable
**principal evidence** captured alongside it — so the approval is
forensically attestable.

This module ships:

  * `ApprovalEvidence` — frozen dataclass capturing the bound
    principal, the source of the binding, a stable hash of the
    evidence, and timestamps.
  * `current_approval_evidence(*, allow_posix_fallback=True)` —
    best-effort identity binding. Resolution order:
      (1) explicit override (`JAMES_APPROVAL_PRINCIPAL` +
          `JAMES_APPROVAL_EVIDENCE_B64`), then
      (2) POSIX `getpass.getuser()` floor when permitted.
    Returns ``None`` if no source resolves (and the operator hasn't
    granted the POSIX floor).
  * `require_approval_evidence() → bool` — true iff
    `JAMES_REQUIRE_APPROVAL_EVIDENCE` is set to a recognised
    truthy value. Production SaaS sets this to `1`; local-dev
    leaves it unset (preserves current v0.5 single-tenant
    operator-is-principal pattern byte-identical).

The change-request wire-in (`apply_change_request(..., approval_
evidence=None)`) lands in **G2.b**. This PR ships the primitive only
— the absence of a wire-in is intentional: the operator hasn't yet
chosen which resolution source is canonical in their environment,
and the documented design (`docs/reviews/v0.5-b2-multi-tenant-
isolation.md` §4.4) lists 4 fallback sources whose ordering the
deploy will pick.

## What this module is NOT

- **Not a bundled OIDC verifier.** v0.6 G2.c ships the OIDC
  *resolution surface* — the env-var contract + the pluggable
  validator hook (:func:`register_oidc_validator`) — but no
  built-in JWKS verifier. The signature-checking implementation
  depends on which crypto library the operator's IdP is friendly
  with (``python-jose`` / ``authlib`` / ``PyJWT`` / custom shim),
  so we pin the contract here and the IdP integration ships in
  the deployment layer.
- **Not a credential store.** Evidence is stored as a hash, not
  recoverable plaintext. Key rotation is the IdP's concern.
- **Not an approver-list enforcer.** "Who CAN approve" is RBAC at
  the HTTP layer; G2 binds "who DID approve" to a verifiable
  principal. RBAC + G2 compose at the call site.
- **Not MFA enforcement.** MFA at the IdP is upstream. JAMES
  checks the IdP's signed attestation (G2.c), not the user's 2FA
  state directly.
"""
from __future__ import annotations

import base64
import getpass
import hashlib
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Final, Literal, Mapping, Optional


JAMES_APPROVAL_PRINCIPAL_ENV:       Final[str] = "JAMES_APPROVAL_PRINCIPAL"
JAMES_APPROVAL_EVIDENCE_B64_ENV:    Final[str] = "JAMES_APPROVAL_EVIDENCE_B64"
JAMES_REQUIRE_APPROVAL_EVIDENCE_ENV: Final[str] = (
    "JAMES_REQUIRE_APPROVAL_EVIDENCE"
)

# v0.6 G2.c — OIDC discovery surface env vars. The OIDC validator
# is a pluggable hook (see :func:`register_oidc_validator`) — until
# a customer IdP is in scope, no built-in validator ships and
# `_resolve_oidc` returns None even when these env vars are set.
# That keeps the mother-platform contract free of an IdP dependency
# while documenting the env surface the operator will wire up at
# the first SaaS pilot.
JAMES_OIDC_ISSUER_ENV:    Final[str] = "JAMES_OIDC_ISSUER"
JAMES_OIDC_TOKEN_ENV:     Final[str] = "JAMES_OIDC_TOKEN"
JAMES_OIDC_AUDIENCE_ENV:  Final[str] = "JAMES_OIDC_AUDIENCE"


# Recognised source labels — locked here because the audit-row
# consumer (G2.b) discriminates on these strings.
ApprovalSource = Literal["posix", "explicit", "oidc", "ssh"]


@dataclass(frozen=True)
class ApprovalEvidence:
    """Forensically-attestable evidence binding an approver to a
    self-evolution change.

    Fields:
        principal:     canonical principal name (e.g. ``alex`` for
                       POSIX, ``alex@acme.com`` for OIDC).
        source:        one of ``"posix"`` / ``"explicit"`` / ``"oidc"``
                       / ``"ssh"`` — the resolution path.
        evidence_hash: hex sha256 digest of the source-specific
                       evidence blob (see :func:`current_approval_
                       evidence` for what each source hashes).
        captured_at:   ISO-8601 UTC timestamp string of when the
                       evidence was captured.
        expires_at:    ISO-8601 UTC string OR empty. Non-empty only
                       for time-limited tokens (OIDC tokens carrying
                       an ``exp`` claim). POSIX + explicit + SSH
                       evidence does not expire (operator-side
                       session lifecycle owns expiry).

    The dataclass is frozen so callers cannot mutate evidence after
    capture — the only valid way to "update" evidence is to call
    :func:`current_approval_evidence` again and produce a fresh
    instance.
    """
    principal:     str
    source:        ApprovalSource
    evidence_hash: str
    captured_at:   str
    expires_at:    str = field(default="")


def _utc_now_iso() -> str:
    """Timezone-aware now in canonical ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _truthy(value: str) -> bool:
    if not value:
        return False
    return value.strip().lower() in ("1", "true", "yes", "on", "enabled")


def require_approval_evidence() -> bool:
    """True iff `JAMES_REQUIRE_APPROVAL_EVIDENCE` is set + truthy.

    Production SaaS sets this to `1`; local-dev leaves it unset.
    The change-request gate (G2.b) consults this — when True AND
    `current_approval_evidence()` returns None, the gate rejects
    the apply.
    """
    return _truthy(os.environ.get(JAMES_REQUIRE_APPROVAL_EVIDENCE_ENV, ""))


# ─── Resolvers ────────────────────────────────────────────────────────


# ─── OIDC validator hook (G2.c) ─────────────────────────────────────
#
# `OIDCValidator` receives ``(token, issuer, audience)`` and returns
# the validated claims dict (carrying at least ``sub`` and optionally
# ``exp``) when verification succeeds, or ``None`` on any failure
# (signature mismatch, expired token, audience mismatch, JWKS fetch
# error). Implementations vary by IdP — Auth0, Okta, Google Workspace
# all expose ``/.well-known/openid-configuration`` but the JWKS
# format + claim shape diverges slightly. We pin the contract surface
# here and ship NO built-in validator until a customer IdP is in
# scope (per the v0.5 G2.a docstring + B.2 §4.4 design memo). Setting
# the env vars without registering a validator returns None — the
# mother-platform contract stays free of an IdP dependency.

OIDCValidator = Callable[[str, str, str], Optional[Mapping[str, Any]]]

_oidc_validator: Optional[OIDCValidator] = None


def register_oidc_validator(validator: Optional[OIDCValidator]) -> None:
    """Install (or remove with ``None``) the OIDC token validator.

    The validator's contract:

        ``validator(token, issuer, audience)`` →
            ``None`` on any failure
            ``Mapping[str, Any]`` carrying at minimum ``sub`` (str)
            and optionally ``exp`` (int — seconds since epoch) on
            success.

    Why pluggable: the validator MUST do JWKS discovery + signature
    verification + audience matching, and the implementation depends
    on which crypto library the operator is willing to install
    (``python-jose``, ``authlib``, ``PyJWT``, a custom shim for an
    in-house IdP, ...). Bundling one would force a dependency the
    mother-platform contract refuses to take until a customer
    specifies their IdP.

    Default: no validator. ``_resolve_oidc`` returns None until a
    validator is registered.

    Test/fake validators: pass any callable that returns the right
    shape. The test suite uses an in-memory fake to exercise the
    resolution path without HTTP / crypto.
    """
    global _oidc_validator
    _oidc_validator = validator


def _resolve_oidc() -> Optional[ApprovalEvidence]:
    """Resolve from `JAMES_OIDC_ISSUER` + `_TOKEN` + `_AUDIENCE` env.

    Requires (a) all three env vars set, and (b) an OIDC validator
    registered via :func:`register_oidc_validator`. Without (b),
    returns None even if (a) is satisfied — see the validator hook
    docstring for why.

    On success the evidence carries:
      * principal: the ``sub`` claim
      * source: ``"oidc"``
      * evidence_hash: sha256 over the token's signature segment
        (the third dot-separated segment of a JWS). The token's
        header + payload are recoverable from the audit log if
        operators wish; the signature alone is the irrecoverable
        proof.
      * captured_at: ISO-8601 now (UTC)
      * expires_at: ISO-8601 of the ``exp`` claim if present (UTC)
    """
    issuer = (os.environ.get(JAMES_OIDC_ISSUER_ENV) or "").strip()
    token = (os.environ.get(JAMES_OIDC_TOKEN_ENV) or "").strip()
    audience = (os.environ.get(JAMES_OIDC_AUDIENCE_ENV) or "").strip()
    if not (issuer and token and audience):
        return None
    validator = _oidc_validator
    if validator is None:
        return None

    try:
        claims = validator(token, issuer, audience)
    except Exception:
        # Validators may raise on transient JWKS failures. We treat
        # any exception as "no evidence resolved" — matching the
        # other resolvers' contract. The caller's enforce-mode gate
        # decides whether absence is fatal.
        return None
    if not isinstance(claims, Mapping):
        return None
    principal = claims.get("sub")
    if not isinstance(principal, str) or not principal:
        return None

    # Hash the token's signature segment (the third part of a JWS).
    # When the token isn't dot-segmented in the standard shape, hash
    # the entire token as a safe fallback.
    parts = token.split(".")
    if len(parts) >= 3 and parts[2]:
        sig_blob = parts[2].encode("utf-8")
    else:
        sig_blob = token.encode("utf-8")

    expires_at = ""
    exp = claims.get("exp")
    if isinstance(exp, (int, float)) and exp > 0:
        try:
            expires_at = datetime.fromtimestamp(
                float(exp), tz=timezone.utc,
            ).isoformat()
        except (OverflowError, OSError, ValueError):
            expires_at = ""

    return ApprovalEvidence(
        principal=principal,
        source="oidc",
        evidence_hash=_sha256_hex(sig_blob),
        captured_at=_utc_now_iso(),
        expires_at=expires_at,
    )


def _resolve_explicit() -> Optional[ApprovalEvidence]:
    """Resolve from `JAMES_APPROVAL_PRINCIPAL` + `_EVIDENCE_B64`.

    Returns ``None`` if either is missing. The evidence blob is
    base64-decoded and sha256'd; callers (and auditors) verify by
    re-decoding + re-hashing. Used by CI / automation that holds
    a service-token whose principal is the bot account.
    """
    principal = (
        os.environ.get(JAMES_APPROVAL_PRINCIPAL_ENV) or ""
    ).strip()
    raw_evidence = (
        os.environ.get(JAMES_APPROVAL_EVIDENCE_B64_ENV) or ""
    ).strip()
    if not principal or not raw_evidence:
        return None
    try:
        decoded = base64.b64decode(raw_evidence, validate=True)
    except (ValueError, base64.binascii.Error):
        return None
    return ApprovalEvidence(
        principal=principal,
        source="explicit",
        evidence_hash=_sha256_hex(decoded),
        captured_at=_utc_now_iso(),
    )


def _resolve_posix(*, allow_posix_fallback: bool) -> Optional[ApprovalEvidence]:
    """Resolve from POSIX `getpass.getuser()` when permitted.

    The hash is sha256 over the username bytes + the canonical
    string "posix" + the captured-at timestamp. The username alone
    would be replayable; the timestamp + label binds the hash to
    this specific capture event.

    `allow_posix_fallback=False` (passed by callers that want the
    explicit path only) returns None instead of probing POSIX. The
    default `True` matches v0.5 single-tenant operator-is-principal
    behaviour.
    """
    if not allow_posix_fallback:
        return None
    try:
        username = getpass.getuser()
    except Exception:
        return None
    if not username:
        return None
    captured_at = _utc_now_iso()
    blob = ("posix" + ":" + username + ":" + captured_at).encode("utf-8")
    return ApprovalEvidence(
        principal=username,
        source="posix",
        evidence_hash=_sha256_hex(blob),
        captured_at=captured_at,
    )


def current_approval_evidence(
    *,
    allow_posix_fallback: bool = True,
) -> Optional[ApprovalEvidence]:
    """Best-effort identity binding from the current process.

    Resolution order (first match wins):

      1. **OIDC** (v0.6 G2.c) — requires `JAMES_OIDC_ISSUER` +
         `_TOKEN` + `_AUDIENCE` env vars set AND a validator
         registered via :func:`register_oidc_validator`. Used by
         SaaS deployments fronted by an enterprise IdP.
      2. **Explicit override** — `JAMES_APPROVAL_PRINCIPAL` + a
         base64-encoded evidence blob in
         `JAMES_APPROVAL_EVIDENCE_B64`. Used by CI / automation /
         service-account approvals where a signed token is the
         evidence carrier.
      3. **POSIX floor** — `getpass.getuser()` when
         `allow_posix_fallback` is True (the default). Used by
         local-dev and single-tenant production where the operator
         is the principal.

    Returns ``None`` if no source resolves (the caller's path —
    typically a hard-rejection in enforce mode — is the
    `require_approval_evidence` gate's responsibility).

    SSH-evidence resolution will slot in as resolution step 4 (after
    POSIX) when a customer's bastion-host workflow is in scope.
    """
    oidc = _resolve_oidc()
    if oidc is not None:
        return oidc
    explicit = _resolve_explicit()
    if explicit is not None:
        return explicit
    return _resolve_posix(allow_posix_fallback=allow_posix_fallback)


__all__ = (
    "JAMES_APPROVAL_PRINCIPAL_ENV",
    "JAMES_APPROVAL_EVIDENCE_B64_ENV",
    "JAMES_REQUIRE_APPROVAL_EVIDENCE_ENV",
    "JAMES_OIDC_ISSUER_ENV",
    "JAMES_OIDC_TOKEN_ENV",
    "JAMES_OIDC_AUDIENCE_ENV",
    "ApprovalEvidence",
    "ApprovalSource",
    "OIDCValidator",
    "current_approval_evidence",
    "register_oidc_validator",
    "require_approval_evidence",
)
