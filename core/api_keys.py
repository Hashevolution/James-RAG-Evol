"""W4 P3-1 — per-user API keys (long-lived) with rotation.

Why this module exists (vs the system-wide JAMES_API_KEY)
---------------------------------------------------------
The legacy ``JAMES_API_KEY`` env var is a single shared secret used by
the server operator for bring-up and admin scripts. It cannot be
rotated without restarting the server, and it does not identify a
user — every call authenticated by it is "the operator".

For external integrations (CI scripts, internal tooling, third-party
clients), users need their own credentials that:
  - can be issued and rotated without operator help,
  - identify *who* is calling so audit logs and policy gates have
    a real subject,
  - can be revoked individually if leaked.

This module is the issuance / verification / revocation backbone.
P3-2 wires it into the authentication middleware so that an
``X-API-Key`` header on any endpoint resolves to a user identity.
P3-1 lands the storage + management layer alone so the changeover
in the middleware can land separately and be audited on its own.

Token shape
-----------
  jms_<43-char-urlsafe>
  └──┘└────────────────┘
   ▲           ▲
   │           └── 32 random bytes, URL-safe base64 (Mr. Robot's bcrypt
   │               equivalent — only the SHA256 is stored)
   └── "jms_" prefix tags the credential by source so a leaked grep
       hit in a log is recognisable at a glance. The first 12 chars
       (``jms_`` + 8 of the random body) form the *display prefix* —
       the only fragment ever shown again after issuance, used as the
       handle for revocation.

DB row
------
``api_keys``:
  key_hash      TEXT PRIMARY KEY    -- SHA256(plaintext), never the key
  key_prefix    TEXT NOT NULL       -- 12 chars, indexed for revocation
  username      TEXT NOT NULL       -- owner
  label         TEXT                -- operator-supplied note (optional)
  created_at    INTEGER NOT NULL    -- unix epoch
  last_used_at  INTEGER             -- bumped on every successful verify
  revoked_at    INTEGER             -- NULL = active

No expiry column: long-lived credentials are the point. Rotation is
explicit (revoke + re-issue), not silent. If a TTL becomes necessary
later we add a column rather than reusing this one.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from typing import Optional, List, Tuple, Dict

from core.auth import _get_conn, _get_user


KEY_PREFIX_LEN = 12  # "jms_" + 8 chars
TOKEN_BODY_BYTES = 32


def _init_api_keys_table() -> None:
    """Create ``api_keys`` if missing. Idempotent."""
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                key_hash      TEXT PRIMARY KEY,
                key_prefix    TEXT NOT NULL,
                username      TEXT NOT NULL,
                label         TEXT,
                created_at    INTEGER NOT NULL,
                last_used_at  INTEGER,
                revoked_at    INTEGER
            )
        """)
        # The prefix gets queried on every revoke call; index keeps it
        # fast even on a fleet of stale keys.
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_api_keys_prefix_user
            ON api_keys (key_prefix, username)
        """)
        conn.commit()
    finally:
        conn.close()


_init_api_keys_table()


def _hash_key(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def _generate_token() -> Tuple[str, str]:
    """Return (plaintext, prefix).

    Plaintext is ``"jms_" + 43-char-urlsafe``. Prefix is the first
    ``KEY_PREFIX_LEN`` characters of the plaintext — enough to identify
    a specific key out of a user's list without revealing the body.
    """
    body  = secrets.token_urlsafe(TOKEN_BODY_BYTES)
    plain = f"jms_{body}"
    return plain, plain[:KEY_PREFIX_LEN]


def issue_api_key(username: str, label: Optional[str] = None
                  ) -> Optional[Tuple[str, str]]:
    """Issue a new API key for an active user.

    Returns ``(plaintext, prefix)`` exactly once. Only the SHA256 hash
    is persisted; the plaintext cannot be recovered from the DB.
    Returns None if the user is unknown or inactive — issuing keys
    for pending/removed accounts is a misuse.
    """
    user = _get_user(username)
    if not user or not user.get("active"):
        return None

    plain, prefix = _generate_token()
    now = int(time.time())
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT INTO api_keys "
            "(key_hash, key_prefix, username, label, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (_hash_key(plain), prefix, username, label, now),
        )
        conn.commit()
        return plain, prefix
    finally:
        conn.close()


def verify_api_key(plain: str) -> Optional[Dict]:
    """Resolve a plaintext key to its owning user, or None.

    Bumps ``last_used_at`` on every successful verify. A revoked key
    (``revoked_at`` is not null) is rejected; the lookup still touches
    the row but does not update the timestamp.

    Returns:
      None on miss / revocation / inactive owner.
      {"username": ..., "role": ...} on success — role is read from
      the users table so a role change takes effect on the next call.
    """
    if not plain or not plain.startswith("jms_"):
        return None
    h    = _hash_key(plain)
    now  = int(time.time())
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT username, revoked_at FROM api_keys WHERE key_hash = ?",
            (h,),
        ).fetchone()
        if row is None or row["revoked_at"] is not None:
            return None
        # Owner must still be an active user — revoking the account
        # invalidates every key transitively.
        user = conn.execute(
            "SELECT role, active FROM users WHERE username = ?",
            (row["username"],),
        ).fetchone()
        if user is None or not user["active"]:
            return None

        conn.execute(
            "UPDATE api_keys SET last_used_at = ? WHERE key_hash = ?",
            (now, h),
        )
        conn.commit()
        return {"username": row["username"], "role": user["role"]}
    finally:
        conn.close()


def revoke_api_key(username: str, key_prefix: str) -> bool:
    """Mark a single key revoked. Only the owning user (or admin —
    enforced at the endpoint, not here) may revoke their keys.

    Idempotent: revoking an already-revoked key returns False rather
    than re-stamping ``revoked_at``, so re-runs are visible to the
    caller without rewriting history.
    """
    if not key_prefix:
        return False
    now  = int(time.time())
    conn = _get_conn()
    try:
        cur = conn.execute(
            "UPDATE api_keys SET revoked_at = ? "
            "WHERE key_prefix = ? AND username = ? AND revoked_at IS NULL",
            (now, key_prefix, username),
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def list_api_keys(username: str) -> List[Dict]:
    """Return one row per key the user owns.

    Each row is keyed by ``key_prefix`` (the user-visible handle)
    rather than the full hash. ``revoked`` is a boolean for the
    caller's convenience; ``revoked_at`` is also included so an
    operator can sort by it.
    """
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT key_prefix, label, created_at, last_used_at, revoked_at "
            "FROM api_keys WHERE username = ? "
            "ORDER BY revoked_at IS NULL DESC, created_at DESC",
            (username,),
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["revoked"] = d["revoked_at"] is not None
            out.append(d)
        return out
    finally:
        conn.close()
