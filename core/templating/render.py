"""Render formatted text to downloadable output bytes.

Supported formats (v1): ``md`` / ``txt`` / ``html``. The HTML wrapper is
minimal and fully escaped — no inline JavaScript, no external resources —
so an operator can open the output safely. ``docx`` is deferred (would
add a ``python-docx`` dependency). See
``docs/design/v0.6-template-formatting-ui.md`` §6.
"""
from __future__ import annotations

import html as _html

VALID_FORMATS = ("md", "txt", "html")

_EXT = {"md": ".md", "txt": ".txt", "html": ".html"}

_HTML_SHELL = (
    "<!DOCTYPE html>\n"
    "<html lang=\"en\">\n<head>\n<meta charset=\"UTF-8\">\n"
    "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
    "<title>{title}</title>\n"
    "<style>body{{font-family:system-ui,sans-serif;max-width:48rem;"
    "margin:2rem auto;padding:0 1rem;line-height:1.6}}"
    "pre{{white-space:pre-wrap;word-wrap:break-word}}</style>\n"
    "</head>\n<body>\n<pre>{body}</pre>\n</body>\n</html>\n"
)


def extension_for(fmt: str) -> str:
    """Return the file extension (with dot) for ``fmt``."""
    if fmt not in _EXT:
        raise ValueError(f"unsupported format {fmt!r}; valid: {VALID_FORMATS}")
    return _EXT[fmt]


def render(formatted_text: str, fmt: str = "md", *, title: str = "document") -> bytes:
    """Render ``formatted_text`` to UTF-8 bytes in the requested format.

    - ``md`` / ``txt``: the text verbatim, UTF-8 encoded.
    - ``html``: the text HTML-escaped inside a minimal, JS-free shell.
    """
    if fmt not in VALID_FORMATS:
        raise ValueError(f"unsupported format {fmt!r}; valid: {VALID_FORMATS}")
    text = formatted_text or ""
    if fmt == "html":
        doc = _HTML_SHELL.format(
            title=_html.escape(title or "document"),
            body=_html.escape(text),
        )
        return doc.encode("utf-8")
    return text.encode("utf-8")


__all__ = ["VALID_FORMATS", "extension_for", "render"]
