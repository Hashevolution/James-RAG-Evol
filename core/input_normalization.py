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

Span removal vs character stripping (v2, 2026-08-19)
-----------------------------------------------------

The v1 gate stripped every control character and kept the surrounding
text. Ali Afana (Provia) walked that recommendation back after measuring
the difference on his own stack: *"Stripping bidi control characters
removes the concealment but not the concealed text; removing the whole
marked span is a different operation with a different result."* He is
right, and the weaker version was our implementation choice, not his
advice — under v1 the payload of an RLO attack survived as cleartext and
went to the model as an instruction.

v2 splits the treatment by what the control actually does:

- **Override characters — LRO (U+202D) and RLO (U+202E) — remove the
  whole span**, opener and contents and terminating PDF together. An
  override forces direction regardless of the characters' own
  properties: that is the concealment primitive, and it has no
  legitimate use inside a user's question. The span runs to the matching
  PDF (U+202C) or, if unterminated, to end of input. Nesting is tracked,
  so an inner embedding's PDF cannot close an outer override.
- **Everything else is stripped, contents kept.** Embeddings (LRE/RLE)
  and isolates (LRI/RLI/FSI/PDI) are the legitimate way to carry a
  directional run — an English product name inside an Arabic sentence —
  and deleting their contents would destroy real text. Marks (LRM/RLM)
  and the zero-width set are single characters with no span at all.

This is deliberately destructive for override spans: a numeric spoof
built out of per-digit overrides loses its digits rather than yielding a
mis-parsed number. A validator that sees no number asks again; one that
sees the wrong number does not. Both counts land in the audit dict, so
the removal is forensically visible.

Arabic orthographic variants (v2.1, 2026-08-19)
-----------------------------------------------

Ali Afana's third finding: *"Keyword gates over Arabic break on ordinary
orthography — tatweel, alef maqsura, presentation forms — variants real
keyboards produce every day. Where a check is gated behind such
matching, ordinary traffic goes unchecked and nothing is logged."*

JAMES has no Arabic keyword gate today — ``ATTACK_PATTERNS`` is English
and Korean only — so there is no bypass to close here. What the gate can
do is stop the same word arriving in several byte forms, which is what
makes such a bypass possible in the first place:

- **Tatweel (U+0640)** is a display-only elongation (``جاكيـــت``). It
  survives *both* NFC and NFKC, so it has to be removed explicitly.
- **Arabic presentation forms** (U+FB50-FDFF, U+FE70-FEFF) are
  positional/ligature variants that fold to their base letters only
  under NFKC (``ﻛﺘﺎﺏ`` → ``كتاب``, ``ﻻ`` → ``لا``).

NFKC is applied **only to characters in those two Arabic blocks**, not
globally: a global NFKC would also rewrite ``①②③`` → ``123``, ``ﬁ`` →
``fi`` and full-width forms → half-width, which is a behaviour change a
Korean-first system should not take on for an Arabic fix.

What this gate deliberately does **not** do is fold letters — alef
maqsura ``ى`` → ``ي``, the alef family ``أ إ آ`` → ``ا``, teh marbuta
``ة`` → ``ه``, or the harakat. Those change what the user actually
wrote, and some pairs are distinct letters rather than variants. They
belong at *matching* time, against a keyword list, not in the text that
gets forwarded to the model — see ``scripts/adversarial_sweep.py``
``_fold_for_match``.

Out of scope (for this gate; potential follow-up):
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

# Direction *overrides* — the concealment primitive. Their spans are
# removed whole (see module docstring §"Span removal vs character
# stripping").
_OVERRIDES: frozenset = frozenset((chr(0x202D), chr(0x202E)))

# Anything that opens a PDF-terminated run. Needed for depth tracking so
# an inner embedding's PDF does not close an outer override span.
_PDF_OPENERS: frozenset = _OVERRIDES | frozenset((chr(0x202A), chr(0x202B)))

_PDF: str = chr(0x202C)

# Arabic display-only elongation. Survives NFC *and* NFKC.
_TATWEEL: str = chr(0x0640)

# Arabic Presentation Forms-A / -B. NFKC folds these to base letters;
# applied per-character so the rest of the string keeps NFC semantics.
_ARABIC_PRESENTATION: tuple = ((0xFB50, 0xFDFF), (0xFE70, 0xFEFF))


def _is_arabic_presentation(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _ARABIC_PRESENTATION)


def _fold_arabic_variants(s: str) -> Tuple[str, int, int]:
    """Remove tatweel and fold Arabic presentation forms.

    Returns ``(text, tatweel_removed, forms_folded)``. Meaning-preserving
    by construction: tatweel carries no semantic content, and the
    presentation blocks are compatibility variants of ordinary letters.
    Letter folding is *not* done here — see the module docstring.
    """
    tatweel_n = s.count(_TATWEEL)
    if tatweel_n:
        s = s.replace(_TATWEEL, "")
    folded_n = 0
    if any(_is_arabic_presentation(c) for c in s):
        out = []
        for c in s:
            if _is_arabic_presentation(c):
                out.append(unicodedata.normalize("NFKC", c))
                folded_n += 1
            else:
                out.append(c)
        s = "".join(out)
    return s, tatweel_n, folded_n


def _remove_override_spans(s: str) -> Tuple[str, int, int]:
    """Delete LRO/RLO spans, contents included.

    Returns ``(text, spans_removed, chars_removed)``. A span runs from
    the override to its matching ``PDF``; an unterminated override
    consumes the rest of the input, which is the conservative reading —
    an attacker who omits the terminator should not get the payload
    through.
    """
    out: list = []
    i, n = 0, len(s)
    spans = chars = 0
    while i < n:
        ch = s[i]
        if ch in _OVERRIDES:
            j, depth = i + 1, 1
            while j < n and depth:
                c = s[j]
                if c in _PDF_OPENERS:
                    depth += 1
                elif c == _PDF:
                    depth -= 1
                j += 1
            spans += 1
            chars += j - i
            i = j
        else:
            out.append(ch)
            i += 1
    return "".join(out), spans, chars


def normalize_user_input(s: str) -> Tuple[str, Dict[str, object]]:
    """Strip bidi formatting + zero-width controls from ``s`` and apply
    NFC canonicalisation.

    Returns ``(normalized_string, audit_dict)``. The audit dict carries:

        bidi_stripped:          int  bidi formatting chars removed by the
                                     strip pass (outside removed spans)
        invisible_stripped:     int  invisible / ZW chars removed
        override_spans_removed: int  LRO/RLO spans deleted whole
        override_span_chars:    int  chars deleted as part of those spans
        tatweel_stripped:       int  U+0640 elongation chars removed
        arabic_forms_folded:    int  presentation-form chars folded
        chars_dropped:          int  bidi + invisible + span + tatweel
        nfc_applied:            bool True if NFC changed the string

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
            "bidi_stripped":          0,
            "invisible_stripped":     0,
            "override_spans_removed": 0,
            "override_span_chars":    0,
            "tatweel_stripped":       0,
            "arabic_forms_folded":    0,
            "chars_dropped":          0,
            "nfc_applied":            False,
        }

    # 1. Override spans go first — their contents must never reach the
    #    strip pass, or the payload survives as cleartext (the v1 bug).
    despanned, spans_n, span_chars = _remove_override_spans(s)

    # 2. Remaining controls are stripped in place, contents kept.
    bidi_n = sum(1 for c in despanned if c in _BIDI_CONTROLS)
    invis_n = sum(1 for c in despanned if c in _INVISIBLE)
    stripped = "".join(c for c in despanned if c not in _DROP)

    # 3. Canonicalise.
    nfc = unicodedata.normalize("NFC", stripped)

    # 4. Arabic orthographic variants — tatweel and presentation forms.
    folded, tatweel_n, forms_n = _fold_arabic_variants(nfc)

    return folded, {
        "bidi_stripped":          bidi_n,
        "invisible_stripped":     invis_n,
        "override_spans_removed": spans_n,
        "override_span_chars":    span_chars,
        "tatweel_stripped":       tatweel_n,
        "arabic_forms_folded":    forms_n,
        "chars_dropped":          bidi_n + invis_n + span_chars + tatweel_n,
        "nfc_applied":            (nfc != stripped),
    }
