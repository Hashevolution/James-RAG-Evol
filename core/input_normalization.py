"""User-input normalization gate — runtime defence against Unicode
bidirectional/invisible control character injection.

Triggered by the Track 2c X3 cross-stack finding (Ali Afana / Provia,
2026-06-01 ``ar_ecommerce-REPORT-provia.md``) confirmed at JAMES via
the 2026-06-02 audit
(``reports/research-runs/bidi-normalization-audit-20260602.md``):
JAMES had **zero** bidi normalization in any layer. U+202E
(RIGHT-TO-LEFT OVERRIDE) and other directional formatting controls
flowed through unchanged from HTTP request body through
``data.question.strip()`` (whitespace-only) through ``rag_engine`` to
the LLM prompt. Provia's empirical observation (``bidi_03``) — *"the
concealed instruction reached the model's reasoning"* — held the same
way at JAMES.

This module is the **runtime input gate**. It strips a small,
explicit set of Unicode bidi formatting + zero-width characters from
user input and applies NFC canonicalisation. The strip is *logged*
per request when any characters are dropped, so an audit trail exists
for forensic review.

⚠️ **Scope discipline** (cross-reference: audit doc §7.2):
- This is a **runtime defence** against user input. It does NOT touch
  the test fixture path. ``eval/adversarial/ar_ecommerce-*.yaml``
  preserve U+202E byte-exact because those characters are the payload
  the test cases exercise.
- The Track 2c adversarial sweep runner
  (``scripts/adversarial_sweep.py:_post_query``) carries a parallel
  warning comment: do NOT normalize input in the runner. The fixture
  → server boundary is exactly what's under test.
- Confusing the runtime gate with test fixture normalization would
  silently break the ``bidi_01``-``bidi_04`` cases.

Stripped characters (per Unicode TR9 + common zero-width set):

| Code point | Name | Class |
|---|---|---|
| U+200E | LEFT-TO-RIGHT MARK (LRM) | bidi |
| U+200F | RIGHT-TO-LEFT MARK (RLM) | bidi |
| U+202A | LEFT-TO-RIGHT EMBEDDING (LRE) | bidi |
| U+202B | RIGHT-TO-LEFT EMBEDDING (RLE) | bidi |
| U+202C | POP DIRECTIONAL FORMATTING (PDF) | bidi |
| U+202D | LEFT-TO-RIGHT OVERRIDE (LRO) | bidi |
| U+202E | RIGHT-TO-LEFT OVERRIDE (RLO) | bidi |
| U+2066 | LEFT-TO-RIGHT ISOLATE (LRI) | bidi |
| U+2067 | RIGHT-TO-LEFT ISOLATE (RLI) | bidi |
| U+2068 | FIRST STRONG ISOLATE (FSI) | bidi |
| U+2069 | POP DIRECTIONAL ISOLATE (PDI) | bidi |
| U+200B | ZERO WIDTH SPACE (ZWSP) | invisible |
| U+200C | ZERO WIDTH NON-JOINER (ZWNJ) | invisible |
| U+200D | ZERO WIDTH JOINER (ZWJ) | invisible |
| U+FEFF | ZERO WIDTH NO-BREAK SPACE (BOM) | invisible |

Out of scope (for this v1 gate; potential follow-up):
- Emoji ZWJ sequences (e.g. 👨‍👩‍👧) are NOT this gate's concern — it
  fires only at ``/query/`` user-text input. Emoji handling at chat /
  wiki edit endpoints is a separate gate.
- Permissive RLM/LRM preservation for Arabic / Hebrew inline number
  direction is a possible cycle-2 refinement (e.g. preserve RLM if
  the surrounding span is > N characters and contains no other bidi
  controls). For v1 the gate is the **strict** version — strip
  unconditionally and log the count.
"""

from __future__ import annotations

import unicodedata
from typing import Dict, Tuple

# Bidirectional formatting characters per Unicode TR9.
_BIDI_CONTROLS: frozenset = frozenset(map(chr, (
    0x200E,  # LRM
    0x200F,  # RLM
    0x202A,  # LRE
    0x202B,  # RLE
    0x202C,  # PDF
    0x202D,  # LRO
    0x202E,  # RLO
    0x2066,  # LRI
    0x2067,  # RLI
    0x2068,  # FSI
    0x2069,  # PDI
)))

# Zero-width / invisible characters worth stripping at user-input layer.
_INVISIBLE: frozenset = frozenset(map(chr, (
    0x200B,  # ZWSP
    0x200C,  # ZWNJ
    0x200D,  # ZWJ
    0xFEFF,  # BOM
)))

_DROP: frozenset = _BIDI_CONTROLS | _INVISIBLE


def normalize_user_input(s: str) -> Tuple[str, Dict[str, object]]:
    """Strip bidi formatting + zero-width controls from ``s`` and apply
    NFC canonicalisation.

    Returns ``(normalized_string, audit_dict)``. The audit dict carries:

        bidi_stripped:      int   number of bidi formatting chars removed
        invisible_stripped: int   number of invisible / ZW chars removed
        chars_dropped:      int   bidi_stripped + invisible_stripped
        nfc_applied:        bool  True if NFC normalization changed the string

    Caller is expected to log the audit dict per request when
    ``chars_dropped > 0`` (so the forensic trail exists without
    polluting normal request logs).

    The function is pure (no side effects, no I/O) — safe to call from
    request handlers without locking, and safe to unit-test exhaustively.

    Idempotence: ``normalize_user_input(normalize_user_input(s)[0])[0]``
    equals ``normalize_user_input(s)[0]`` for any ``s``. The second
    call's audit dict has ``chars_dropped == 0`` and ``nfc_applied ==
    False``.
    """
    if not s:
        return s, {
            "bidi_stripped":      0,
            "invisible_stripped": 0,
            "chars_dropped":      0,
            "nfc_applied":        False,
        }

    bidi_n = sum(1 for c in s if c in _BIDI_CONTROLS)
    invis_n = sum(1 for c in s if c in _INVISIBLE)
    stripped = "".join(c for c in s if c not in _DROP)
    nfc = unicodedata.normalize("NFC", stripped)

    return nfc, {
        "bidi_stripped":      bidi_n,
        "invisible_stripped": invis_n,
        "chars_dropped":      bidi_n + invis_n,
        "nfc_applied":        (nfc != stripped),
    }
