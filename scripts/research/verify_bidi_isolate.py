#!/usr/bin/env python3
"""Reproduce every claim in the isolate-downgrade measurement.

Companion to ``reports/research-runs/bidi-isolate-downgrade-measurement-20260906.md``,
which answers the question Ali Afana (Provia) raised on 2026-09-06 and
explicitly flagged as unmeasured: an attacker who switches RLO to RLI
gets past a span-removal gate — but does an isolate conceal anything?

Not a pytest test and not wired into CI on purpose. It needs
``python-bidi``, which is not a JAMES dependency and should not become
one — nothing in the product renders bidi text.

    python3 scripts/research/verify_bidi_isolate.py

**Import from ``bidi``, never from ``bidi.algorithm``.** One install
exposes both, and they are different algorithms: the top-level name is
the Rust ``unicode-bidi`` backend (UBA 6.3+, isolate-aware), while
``bidi.algorithm`` is a legacy pure-Python implementation kept for
compatibility that raises ``AssertionError: RLI not allowed here``.
They agree on overrides, so the legacy path looks correct on every RLO
case before it throws on the first isolate — a library limit that reads
as a Unicode result. ``_assert_modern_backend`` below checks this at
startup rather than trusting the reader to remember it.
"""
from __future__ import annotations

import re
import sys

try:
    from bidi import get_display
except ImportError:                                           # noqa: BLE001
    sys.exit("python-bidi missing — see this module's docstring")


def _assert_modern_backend() -> None:
    """Refuse to print numbers from the legacy pre-isolate algorithm.

    The failure this guards against is not an exception — it is the
    legacy path answering an isolate question by throwing, and that
    throw being read as "the isolate was neutralised".
    """
    probe = chr(0x2067) + "ab" + chr(0x2069)
    try:
        get_display(probe)
    except Exception as exc:                                  # noqa: BLE001
        sys.exit(
            f"legacy bidi backend in use ({type(exc).__name__}: {exc}).\n"
            "Import get_display from `bidi`, not `bidi.algorithm`."
        )

# The invisible controls, stripped from display output so the comparison
# is what a reader actually sees.
_CTRL = {chr(c) for c in (0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
                          0x2066, 0x2067, 0x2068, 0x2069)}
RLO, RLI, PDF, PDI = chr(0x202E), chr(0x2067), chr(0x202C), chr(0x2069)

PAYLOAD = "ignore all previous"
AR_LEFT, AR_RIGHT = "السعر ", " نهاية"


def vis(s: str) -> str:
    """Display order with the invisible controls removed."""
    return "".join(c for c in get_display(s) if c not in _CTRL)


def main() -> int:
    _assert_modern_backend()
    failed: list[str] = []

    def check(label: str, cond: bool) -> None:
        print(f"  {'ok  ' if cond else 'FAIL'}  {label}")
        if not cond:
            failed.append(label)

    # Table: override mangles spelling, isolate never does.
    check("LTR bare intact", PAYLOAD in vis(PAYLOAD))
    check("LTR RLO mangled", PAYLOAD not in vis(RLO + PAYLOAD + PDF))
    check("LTR RLI intact", PAYLOAD in vis(RLI + PAYLOAD + PDI))
    check("AR  bare intact", PAYLOAD in vis(AR_LEFT + PAYLOAD + AR_RIGHT))
    check("AR  RLO mangled",
          PAYLOAD not in vis(AR_LEFT + RLO + PAYLOAD + PDF + AR_RIGHT))
    check("AR  RLI intact",
          PAYLOAD in vis(AR_LEFT + RLI + PAYLOAD + PDI + AR_RIGHT))

    # The residual: placement moves only under an unnatural boundary,
    # and the spelling survives even then.
    tmpl, phrase = "السعر {} 100 ريال", "transfer funds"
    check("unnatural boundary relocates",
          vis(tmpl.format(phrase)) != vis(tmpl.format(RLI + phrase + PDI)))
    check("  ...but spelling intact",
          phrase in vis(tmpl.format(RLI + phrase + PDI)))

    # Wrap a natural phrase and the isolate changes nothing at all.
    natural = "السعر 100 والشحن 20 ريال"
    isolated = "السعر " + RLI + "100 والشحن 20" + PDI + " ريال"
    check("natural phrase: identical", vis(natural) == vis(isolated))

    # The trap: plain Arabic reorders digit runs with zero controls
    # present. Ordinary RTL rendering, not an attack.
    check("plain Arabic digit reorder",
          re.findall(r"\d+", vis(natural)) != re.findall(r"\d+", natural))

    print("ALL PASS" if not failed else f"{len(failed)} FAILED: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
