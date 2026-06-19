"""v0.6.1 Phase 4 — Privacy gate (query-level PII pre-check).

Detects structured PII patterns in raw query text *before* any
cloud egress decision. Orthogonal to §5.7.12's per-entity mask
(that pass operates inside the cloud call; this one decides
whether the cloud call can happen at all).

Plumb-first: this module is callable but has no consumer yet.
Phase 5 will wire ``check_query_privacy`` into the cloud egress
branch.

Env contract (lazy, resolved at call time for test isolation):
  JAMES_PRIVACY_FORCE_LOCAL=1
    When set, ``check_query_privacy`` returns ``force_local=True``
    on any pattern match. When unset, matches are reported via
    ``PrivacyCheck.reasons`` for operator observation but do NOT
    block — the default-OFF posture lets operators monitor false-
    positive rates before flipping the switch.
  JAMES_PRIVACY_PII_PATTERNS_EXTRA=name1:regex1,name2:regex2
    Operator-extensible patterns appended to the shipped set.
    Invalid regex is logged + skipped; never raises.

Redacted-span policy: matches are returned with first/last 2 chars
of the value preserved and the middle replaced by ``…``. The raw
PII never leaves ``detect_pii`` — even ``PrivacyCheck.matched`` is
safe to log or to surface in the operator dashboard.
"""
from __future__ import annotations

import os
import re
from typing import List, NamedTuple, Pattern, Tuple


class PrivacyCheck(NamedTuple):
    """Outcome of a query-level privacy pre-check.

    force_local : if True, the caller MUST NOT egress this query.
                  Only True when JAMES_PRIVACY_FORCE_LOCAL=1 AND
                  at least one pattern matched.
    reasons     : list of pattern names that matched
                  (e.g. ["korean_rrn", "email"]).
    matched     : list of (pattern_name, redacted_span) — redacted
                  spans are safe to log; never contains raw PII.
    """
    force_local: bool
    reasons:     List[str]
    matched:     List[Tuple[str, str]]


# ─── Shipped patterns ──────────────────────────────────────────────
# Keep these intentionally conservative — false-positives turn into
# refused cloud calls. Operators extend via the env knob.

# Korean Resident Registration Number: 6 digits, hyphen, 7 digits.
# Surrounded by word-boundaries to avoid catching plain phone-like
# digit strings.
_RRN_RE: Pattern[str] = re.compile(r"\b\d{6}-\d{7}\b")

# Korean mobile: 010-XXXX-XXXX (also tolerates +82 10-XXXX-XXXX and
# spaced separators).
_PHONE_KR_RE: Pattern[str] = re.compile(
    r"(?:\+?82[- ]?1[016789]|0?1[016789])[- ]?\d{3,4}[- ]?\d{4}"
)

# RFC-5322-simplified email. Good enough for "is there an address
# in this query?" — not for validation of arbitrary user input.
_EMAIL_RE: Pattern[str] = re.compile(
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"
)

# Payment card: 13–19 digits, optionally separated by space or hyphen
# in groups of four. We do NOT Luhn-validate at this layer — the
# regex catches the shape; the user-intent layer can choose to drop
# false-positives. Boundary chars stop matches inside long ID
# strings.
_CARD_RE: Pattern[str] = re.compile(
    r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)"
)


_BUILTIN: List[Tuple[str, Pattern[str]]] = [
    ("korean_rrn", _RRN_RE),
    ("phone_kr",   _PHONE_KR_RE),
    ("email",      _EMAIL_RE),
    ("card_number", _CARD_RE),
]


def _extra_patterns() -> List[Tuple[str, Pattern[str]]]:
    """Parse JAMES_PRIVACY_PII_PATTERNS_EXTRA at call time.

    Format: ``name1:regex1,name2:regex2``. Invalid entries are
    logged + skipped, never raise. Resolved lazily so tests can
    swap env between calls.
    """
    raw = os.environ.get("JAMES_PRIVACY_PII_PATTERNS_EXTRA", "").strip()
    if not raw:
        return []
    out: List[Tuple[str, Pattern[str]]] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        name, _, pattern = entry.partition(":")
        name = name.strip()
        pattern = pattern.strip()
        if not name or not pattern:
            continue
        try:
            out.append((name, re.compile(pattern)))
        except re.error as exc:
            print(
                f"[routing.privacy] extra pattern '{name}' "
                f"invalid regex, skipped: {exc}"
            )
    return out


def _redact(value: str) -> str:
    """Return a span-safe placeholder for a matched PII value.

    Preserves first/last 2 chars (so the operator can spot which
    record matched) and collapses the middle with ``…``. Values of
    4 chars or fewer collapse to a single ``…``.
    """
    v = value.strip()
    if len(v) <= 4:
        return "…"
    return f"{v[:2]}…{v[-2:]}"


def detect_pii(text: str) -> List[Tuple[str, str]]:
    """Return matched (pattern_name, redacted_span) pairs.

    Each pattern contributes at most one entry per match. The raw
    matched span is never returned; ``_redact`` collapses it before
    return so the caller can log freely.

    Returns ``[]`` for empty / non-str input.
    """
    if not text or not isinstance(text, str):
        return []
    out: List[Tuple[str, str]] = []
    for name, pat in (*_BUILTIN, *_extra_patterns()):
        for m in pat.finditer(text):
            out.append((name, _redact(m.group(0))))
    return out


def check_query_privacy(
    text: str,
    *,
    force_local_flag: bool | None = None,
) -> PrivacyCheck:
    """Query-level PII pre-check (Phase 4 plumb-first).

    Args:
      text: raw query string.
      force_local_flag: override env. ``None`` = read
        ``JAMES_PRIVACY_FORCE_LOCAL`` at call time.

    Returns ``PrivacyCheck``. ``force_local=True`` iff both:
      - the flag (env or explicit) is True, AND
      - at least one pattern matched.

    Report-only mode (flag OFF): ``force_local=False`` even when
    patterns match. ``reasons`` + ``matched`` still populated so
    operators can monitor false-positive rates before flipping
    the flag ON.
    """
    matched = detect_pii(text)
    if force_local_flag is None:
        force_local_flag = (
            os.environ.get("JAMES_PRIVACY_FORCE_LOCAL", "").strip() == "1"
        )
    reasons = sorted({name for name, _ in matched})
    return PrivacyCheck(
        force_local=bool(force_local_flag) and bool(matched),
        reasons=reasons,
        matched=matched,
    )


__all__ = [
    "PrivacyCheck",
    "detect_pii",
    "check_query_privacy",
]
