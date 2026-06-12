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

- **Not an OIDC verifier.** The OIDC resolution path is documented
  in §4.4 of the B.2 memo and lands in G2.c when a customer's IdP
  is in scope. This PR's `current_approval_evidence` returns
  evidence only when an explicit override OR the POSIX floor
  resolves.
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
from typing import Final, Literal, Optional


JAMES_APPROVAL_PRINCIPAL_ENV:       Final[str] = "JAMES_APPROVAL_PRINCIPAL"
JAMES_APPROVAL_EVIDENCE_B64_ENV:    Final[str] = "JAMES_APPROVAL_EVIDENCE_B64"
JAMES_REQUIRE_APPROVAL_EVIDENCE_ENV: Final[str] = (
    "JAMES_REQUIRE_APPROVAL_EVIDENCE"
)


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

      1. **Explicit override** — `JAMES_APPROVAL_PRINCIPAL` + a
         base64-encoded evidence blob in
         `JAMES_APPROVAL_EVIDENCE_B64`. Used by CI / automation /
         service-account approvals where a signed token is the
         evidence carrier.
      2. **POSIX floor** — `getpass.getuser()` when
         `allow_posix_fallback` is True (the default). Used by
         local-dev and single-tenant production where the operator
         is the principal.

    Returns ``None`` if no source resolves (the caller's path —
    typically a hard-rejection in enforce mode — is the
    `require_approval_evidence` gate's responsibility).

    OIDC + SSH resolution paths land in G2.b / G2.c (separate PRs).
    They will slot in as resolution steps 0 / 3 (OIDC ahead of
    explicit; SSH after POSIX) without changing this function's
    signature.
    """
    explicit = _resolve_explicit()
    if explicit is not None:
        return explicit
    return _resolve_posix(allow_posix_fallback=allow_posix_fallback)


__all__ = (
    "JAMES_APPROVAL_PRINCIPAL_ENV",
    "JAMES_APPROVAL_EVIDENCE_B64_ENV",
    "JAMES_REQUIRE_APPROVAL_EVIDENCE_ENV",
    "ApprovalEvidence",
    "ApprovalSource",
    "current_approval_evidence",
    "require_approval_evidence",
)
