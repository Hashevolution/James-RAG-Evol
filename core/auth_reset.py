"""W4 P2-B — self-service password change + admin-issued reset tokens.

Why this is a sibling module (not part of core/auth.py):
  CLAUDE.md rule 5 keeps every file under core/ at <20 KB. After
  P1-A/P1-B/P2-A, auth.py crossed that line. The reset workflow has
  no upstream callers inside auth.py, so moving it out costs nothing
  at the call sites and respects the gate.

Dependencies are unidirectional: this module imports auth's helpers;
auth never imports back.

Public surface:
  - RESET_TOKEN_TTL_SEC                  — 1 hour, exposed for tests
  - change_password(user, old, new) -> str       — logged-in flow
  - issue_reset_token(username) -> Optional[str] — admin-issued
  - consume_reset_token(user, tok, new) -> str   — public confirm

Persistence:
  ``password_reset_tokens`` table, created lazily on import. Stores
  SHA256(token) — never the raw token — so a DB read does not yield
  usable reset credentials.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from typing import Optional

from core.auth import (
    _get_conn,
    _get_user,
    hash_password,
    verify_password,
    validate_password_policy,
)


# 1 hour. Long enough that an admin can hand the token to a user
# out-of-band (phone, in-person, internal chat) without rushing;
# short enough that an intercepted token has bounded value.
RESET_TOKEN_TTL_SEC = 3600


def _init_reset_token_table() -> None:
    """Create the password_reset_tokens table if missing.

    The token itself is 32 random URL-safe bytes — well above SHA256's
    pre-image difficulty — so the one-way hash here is purely "don't
    leak the credential at rest", not collision resistance.
    """
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                token_hash  TEXT PRIMARY KEY,
                username    TEXT NOT NULL,
                created_at  INTEGER NOT NULL,
                expires_at  INTEGER NOT NULL,
                used_at     INTEGER
            )
        """)
        conn.commit()
    finally:
        conn.close()


_init_reset_token_table()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def change_password(username: str, old_password: str, new_password: str) -> str:
    """Self-service password change for an authenticated user.

    Returns one of:
      - "ok"             — password updated
      - "invalid_old"    — current password didn't verify
      - "policy:<msg>"   — new password failed validate_password_policy
      - "no_user"        — username does not exist or is inactive

    Side effects on success: bcrypt-rehashes the new password and writes
    one UPDATE. No audit log here — the endpoint handler writes that
    so the caller's IP is captured.
    """
    user = _get_user(username)
    if not user or not user.get("active"):
        return "no_user"
    if not verify_password(old_password, user["password_hash"]):
        return "invalid_old"
    err = validate_password_policy(new_password)
    if err is not None:
        return f"policy:{err}"

    new_hash = hash_password(new_password)
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (new_hash, username),
        )
        conn.commit()
        return "ok"
    finally:
        conn.close()


def issue_reset_token(username: str) -> Optional[str]:
    """Admin-issued password-reset token.

    The plaintext token is returned exactly once — only the hash is
    persisted, so the caller MUST relay the token out-of-band before
    discarding the response. Returns None if the user is unknown or
    inactive (admins should not issue resets for pending or removed
    accounts — those have other workflows).

    Any prior unused tokens for the same username are revoked (DELETE)
    so a previously-issued-but-undelivered token cannot silently
    coexist with a fresh one.
    """
    user = _get_user(username)
    if not user or not user.get("active"):
        return None

    token = secrets.token_urlsafe(32)
    now   = int(time.time())
    exp   = now + RESET_TOKEN_TTL_SEC

    conn = _get_conn()
    try:
        conn.execute(
            "DELETE FROM password_reset_tokens "
            "WHERE username = ? AND used_at IS NULL",
            (username,),
        )
        conn.execute(
            "INSERT INTO password_reset_tokens "
            "(token_hash, username, created_at, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (_token_hash(token), username, now, exp),
        )
        conn.commit()
        return token
    finally:
        conn.close()


def consume_reset_token(username: str, token: str, new_password: str) -> str:
    """One-shot reset using a token from ``issue_reset_token``.

    Returns one of:
      - "ok"                — password updated, token marked used
      - "invalid_token"     — unknown hash, wrong username, or expired
      - "already_used"      — token was previously consumed
      - "policy:<msg>"      — new password failed validation
      - "no_user"           — token was valid but the user row vanished
                              between issue and consume (race / delete)

    The token check + password UPDATE + used_at UPDATE happen under one
    connection, so a concurrent second consume can't succeed: the
    second caller observes used_at != NULL.
    """
    err = validate_password_policy(new_password)
    if err is not None:
        return f"policy:{err}"

    h    = _token_hash(token)
    now  = int(time.time())
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT username, expires_at, used_at "
            "FROM password_reset_tokens WHERE token_hash = ?",
            (h,),
        ).fetchone()
        if row is None:
            return "invalid_token"
        if row["username"] != username:
            # Same hash, different user — only possible under a 256-bit
            # collision, but reject defensively anyway.
            return "invalid_token"
        if row["used_at"] is not None:
            return "already_used"
        if row["expires_at"] < now:
            return "invalid_token"

        user = conn.execute(
            "SELECT active FROM users WHERE username = ?", (username,)
        ).fetchone()
        if user is None or not user["active"]:
            return "no_user"

        conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (hash_password(new_password), username),
        )
        conn.execute(
            "UPDATE password_reset_tokens SET used_at = ? WHERE token_hash = ?",
            (now, h),
        )
        conn.commit()
        return "ok"
    finally:
        conn.close()
