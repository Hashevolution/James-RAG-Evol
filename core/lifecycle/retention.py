"""v0.5 G4 — retention-policy metadata for audit-log rows.

Per `docs/reviews/v0.5-b1-ontology-surface-audit.md` G4
(strongly recommended for enterprise pilots): audit rows are append-
only and never deleted (the correct semantic for replay-safety),
but enterprise deployments routinely have legal retention windows
(e.g., 7 years per a typical data-retention policy).

This module adds a **machine-readable retention class** that callers
attach to emitted audit rows, plus a **`pending_retention_review`**
predicate that surfaces row IDs past their window — so the operator
can run the (approval-gated, manual) decision to actually archive
them. The module does NOT auto-delete; the only way to remove a row
is still a separate change-request flow that preserves the
audit-replay-safety invariant.

## Retention class values

  - ``"permanent"``   — keep indefinitely; never returned by the
                        pending-review predicate. The default for
                        load-bearing audit rows.
  - ``"7y"``          — 7 years from row timestamp (typical legal
                        retention floor for enterprise records).
  - ``"3y"``          — 3 years from row timestamp.
  - ``"pilot"``       — 90 days from row timestamp (short pilot
                        window so pilot data doesn't accumulate
                        indefinitely in production-style stores).
  - ``"custom:<ISO>"`` — custom expiry timestamp; the suffix MUST be
                        a parseable ISO-8601 datetime string.

## Integration with emit

The retention class is stored INSIDE the row's `event_payload` JSON
column (under the key ``retention_class``), so adding it required
zero schema migration. Callers pass ``retention_class`` to
:func:`emit_lifecycle_event` (added there) and read it back via
:func:`row_retention_class`.

## What this module is NOT

- **Not an auto-delete path.** :func:`pending_retention_review`
  returns row IDs; the operator decides whether to invoke an
  archive flow.
- **Not a TTL.** Rows past their window remain visible to replay
  until explicitly archived. The retention metadata only signals
  eligibility.
- **Not GDPR Art. 17 ready out of the box.** Customers needing
  erasure-on-request must implement an archive flow that preserves
  the replay-safety invariant — typically by writing a "tombstone"
  row that the replay layer respects without exposing the original
  PII. That work is downstream of this primitive.
"""
from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Final, List, Optional


# ─── Retention class constants ────────────────────────────────────────

RETENTION_PERMANENT: Final[str] = "permanent"
RETENTION_7Y:        Final[str] = "7y"
RETENTION_3Y:        Final[str] = "3y"
RETENTION_PILOT:     Final[str] = "pilot"
RETENTION_CUSTOM_PREFIX: Final[str] = "custom:"

_FIXED_RETENTION_DELTAS = {
    RETENTION_7Y:    timedelta(days=365 * 7),
    RETENTION_3Y:    timedelta(days=365 * 3),
    RETENTION_PILOT: timedelta(days=90),
}

VALID_RETENTION_FIXED: Final[frozenset[str]] = frozenset({
    RETENTION_PERMANENT,
    RETENTION_7Y,
    RETENTION_3Y,
    RETENTION_PILOT,
})


# ─── Validation ───────────────────────────────────────────────────────


def validate_retention_class(value: str) -> bool:
    """True iff ``value`` is a recognised retention class.

    Recognised forms:
      * Any of the four fixed classes (``permanent``, ``7y``, ``3y``,
        ``pilot``).
      * ``custom:<ISO-8601>`` where the suffix parses as a
        timezone-aware datetime.

    Returns ``False`` (does not raise) on ``None``, non-str, empty,
    or malformed values — callers that need a strict assertion can
    wrap with their own raise.
    """
    if not isinstance(value, str) or not value:
        return False
    if value in VALID_RETENTION_FIXED:
        return True
    if value.startswith(RETENTION_CUSTOM_PREFIX):
        suffix = value[len(RETENTION_CUSTOM_PREFIX):]
        return _parse_iso(suffix) is not None
    return False


def _parse_iso(value: str) -> Optional[datetime]:
    """Lenient ISO-8601 parse → tz-aware datetime (UTC if naive)."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


# ─── Expiry computation ───────────────────────────────────────────────


def expiry_for(
    retention_class: str,
    row_timestamp: str,
) -> Optional[datetime]:
    """Return the moment a row passes retention.

    Args:
        retention_class: a value accepted by
            :func:`validate_retention_class`.
        row_timestamp: ISO-8601 timestamp of the audit row.

    Returns:
        Timezone-aware datetime when the row is past its window.
        ``None`` if the row is ``permanent`` (never expires), if
        the retention class is malformed, or if ``row_timestamp``
        cannot be parsed.
    """
    if not validate_retention_class(retention_class):
        return None
    if retention_class == RETENTION_PERMANENT:
        return None
    parsed_ts = _parse_iso(row_timestamp)
    if parsed_ts is None:
        return None
    if retention_class in _FIXED_RETENTION_DELTAS:
        return parsed_ts + _FIXED_RETENTION_DELTAS[retention_class]
    # custom:<ISO> — the suffix IS the expiry timestamp (absolute,
    # not relative to row_timestamp). The custom case is the
    # "legal hold until specific date" pattern.
    suffix = retention_class[len(RETENTION_CUSTOM_PREFIX):]
    return _parse_iso(suffix)


def is_past_retention(
    retention_class: str,
    row_timestamp: str,
    now: datetime,
) -> bool:
    """True iff a row is past its retention window relative to ``now``.

    ``permanent`` and malformed retention classes return ``False``
    (treated as "never review"). ``now`` must be timezone-aware.
    """
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError(
            "now must be a timezone-aware datetime "
            "(UTC recommended)"
        )
    expiry = expiry_for(retention_class, row_timestamp)
    if expiry is None:
        return False
    return now >= expiry


# ─── Audit-log scan ───────────────────────────────────────────────────


_RETENTION_KEY_RE = re.compile(
    r'"retention_class"\s*:\s*"([^"]+)"'
)


def _default_db_path() -> str:
    """Mirror of `replay_audit._default_db_path` so this module
    doesn't introduce a cross-module dependency on a private helper.
    """
    env = (os.environ.get("JAMES_AUDIT_DB") or "").strip()
    if env:
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(here))
    return os.path.join(project_root, "audit.db")


def pending_retention_review(
    now: datetime,
    *,
    db_path: Optional[str] = None,
    limit: int = 1000,
) -> List[int]:
    """Return audit_log row IDs whose retention window has expired.

    Scans the audit_log table for rows whose ``event_payload`` JSON
    contains a ``retention_class`` key. For each such row, computes
    the expiry from the row's ``timestamp`` + retention class, and
    includes the row's ID if ``now >= expiry``.

    Args:
        now: timezone-aware "current" moment for the review.
        db_path: optional override. Defaults to the same path as
            :func:`emit_lifecycle_event` (``JAMES_AUDIT_DB`` env or
            project-root ``audit.db``).
        limit: maximum number of row IDs to return. Default 1000
            — the operator runs the predicate periodically; returning
            millions of IDs in one call is a smell.

    Returns:
        List of integer row IDs, ordered by ID ascending. Empty list
        if no rows past retention, or if the DB is missing /
        unreadable (silent fail matches `emit_lifecycle_event`'s
        "never raises" contract).

    What this does NOT do:
        * Does NOT delete the rows. Caller decides.
        * Does NOT mark rows as reviewed. Stateless scan.
        * Does NOT cross-reference replay invariants. The operator
          must verify archival doesn't break replay before deleting.
    """
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError(
            "now must be a timezone-aware datetime "
            "(UTC recommended)"
        )
    path = db_path or _default_db_path()
    if not os.path.exists(path):
        return []

    out: List[int] = []
    try:
        conn = sqlite3.connect(path, check_same_thread=False)
        try:
            cur = conn.execute(
                "SELECT id, timestamp, event_payload "
                "FROM audit_log "
                "WHERE event_payload LIKE '%retention_class%' "
                "ORDER BY id ASC LIMIT ?",
                (int(limit),),
            )
            for row_id, ts, payload_json in cur:
                if not isinstance(payload_json, str):
                    continue
                match = _RETENTION_KEY_RE.search(payload_json)
                if not match:
                    continue
                rc = match.group(1)
                if is_past_retention(rc, ts or "", now):
                    out.append(int(row_id))
        finally:
            conn.close()
    except Exception:
        return []
    return out


# ─── Row-side accessor ────────────────────────────────────────────────


def row_retention_class(event_payload: str) -> Optional[str]:
    """Extract the ``retention_class`` from a row's payload JSON.

    Returns ``None`` if the key is absent, the payload is not a
    string, or the JSON is malformed. Uses a regex match rather
    than `json.loads` so callers iterating millions of rows pay
    the parse cost only on rows that already match the LIKE filter.
    """
    if not isinstance(event_payload, str):
        return None
    match = _RETENTION_KEY_RE.search(event_payload)
    return match.group(1) if match else None


__all__ = (
    "RETENTION_PERMANENT",
    "RETENTION_7Y",
    "RETENTION_3Y",
    "RETENTION_PILOT",
    "RETENTION_CUSTOM_PREFIX",
    "VALID_RETENTION_FIXED",
    "validate_retention_class",
    "expiry_for",
    "is_past_retention",
    "pending_retention_review",
    "row_retention_class",
)
