"""Slice a JS function body without guessing how long it is.

Structural tests routinely do::

    idx  = js.index("function appendTyping")
    body = js[idx:idx + 1500]

and that window silently goes stale. `appendTyping` grew to ~12,000
characters, so a 1,500-char slice stopped containing the markup the test
was asserting on — and the test reported the feature as missing when it
had only moved further down the same function.

`function_body` bounds the slice at the next top-level ``function``
declaration instead, so it tracks the real function however it grows.
"""
from __future__ import annotations

import re


def function_body(js: str, name: str, *, max_chars: int = 40_000) -> str:
    """Return the source of top-level ``function <name>`` in ``js``.

    Bounded at the next top-level function declaration. ``max_chars`` is
    a backstop for the last function in a file, not a window to tune.

    Raises ValueError when the function is absent, so a rename fails
    loudly rather than silently asserting against an empty string.
    """
    m = re.search(r"^(?:async\s+)?function\s+%s\s*\(" % re.escape(name),
                  js, re.M)
    if m is None:
        raise ValueError(f"top-level `function {name}` not found")
    start = m.start()
    nxt = re.search(r"\n(?:async\s+)?function\s+\w+\s*\(", js[start + 1:])
    end = start + 1 + nxt.start() if nxt else start + max_chars
    return js[start:end]


__all__ = ["function_body"]
