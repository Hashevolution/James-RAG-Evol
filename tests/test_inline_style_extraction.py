"""[v0.2.x #8, 2026-05-12] Inline ``<style>`` block extraction.

HANDOVER_WEB_UI.md §4 priority 8 — the chat (index.html) and admin
(admin.html) pages used to inline 800+ and 400+ lines of CSS each
in a single ``<style>`` block at the top of every HTML payload.
This module pins the post-extraction contract so the cleanup
doesn't regress:

  - The chat + admin pages MUST link the extracted stylesheets
    AFTER tokens.css and BEFORE mobile.css (cascade order).
  - The extracted files MUST exist with a sensible byte size.
  - The remaining inline ``<style>`` block on each page MUST be
    materially smaller than the old footprint — a sanity guard
    against someone reintroducing a big inline block during a
    later cleanup.
  - workspace.html and graph.html are NOT yet migrated (see § Out
    of scope in the PR description); the contract carries them as
    legacy entries so a future PR-#8b can flip them by adding
    files + names here.

Run:
    python -m unittest tests.test_inline_style_extraction
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
STATIC = FRONTEND / "static"


# Pages that completed the §4 #8 extraction. Each entry pairs the
# HTML page with the dedicated CSS file the inline block moved to.
# [PR-#8b, 2026-05-13] workspace + graph followed the chat/admin
# pattern; all four page-level HTML files now link a sibling CSS
# file instead of carrying an inline ``<style>`` block.
_EXTRACTED = {
    "index.html": "chat.css",
    "admin.html": "admin.css",
    "workspace.html": "workspace.css",
    "graph.html": "graph.css",
}

# Pages that were BORN with external CSS rather than extracted from an
# inline block. [2026-08-26] intro.html is the first: zero inline
# styles, links tokens → intro → mobile in order. It belongs in the
# cascade-order and accounted-for checks, but not in the ≥8 KB size
# floor — that floor encodes "~600 lines were moved out of this page",
# which was never true here (intro.css is 4.9 KB and complete).
_EXTERNAL_FROM_BIRTH = {
    "intro.html": "intro.css",
}

# Every page that links a per-page stylesheet, however it got one.
_ALL_PAGE_CSS = {**_EXTRACTED, **_EXTERNAL_FROM_BIRTH}

# Pages that intentionally keep their inline ``<style>`` block.
# Empty after PR-#8b — the rollout is complete. The set stays as a
# named hook so any future page can declare itself opt-out by name
# (and the rollout-complete guard below still catches drift).
_STILL_INLINE: set[str] = set()

# Cap (in bytes) on residual inline ``<style>`` content for an
# extracted page. A bit of inline CSS is sometimes unavoidable
# (page-local :root token overrides, single-element tweaks), but
# the bulk must live in the linked file.
_RESIDUAL_INLINE_CAP_BYTES = 2_000


def _inline_style_body(html: str) -> str:
    """Concatenate every ``<style>...</style>`` body found in
    ``html``. Returns '' if the page has no inline block."""
    chunks = re.findall(r"<style>([\s\S]*?)</style>", html)
    return "\n".join(chunks)


class ExtractedFilesExistTests(unittest.TestCase):

    def test_each_extracted_css_file_exists(self):
        for html_name, css_name in _EXTRACTED.items():
            with self.subTest(page=html_name):
                path = STATIC / css_name
                self.assertTrue(
                    path.exists(),
                    f"{path.relative_to(ROOT)} must exist — it's the "
                    f"extraction target for {html_name}",
                )

    def test_extracted_css_files_are_substantial(self):
        # Sanity check — the extraction moved ~600+ lines of CSS;
        # an empty/trivial file would be a regression.
        for html_name, css_name in _EXTRACTED.items():
            with self.subTest(page=html_name):
                size = (STATIC / css_name).stat().st_size
                self.assertGreater(
                    size, 8_000,
                    f"{css_name} is only {size}B; extraction looks "
                    "incomplete (expected ≥ 8 KB of rules)",
                )


class CascadeOrderTests(unittest.TestCase):
    """Each extracted page must link its CSS files in the order:
    tokens.css → page.css → mobile.css. CSS resolves equal-
    specificity rules in source order; mobile.css must come last
    so narrow-viewport overrides win at break-points without
    needing ``!important`` on every line."""

    @staticmethod
    def _link_indexes(html: str, filenames):
        """Return a list of (filename, position) tuples — position
        is the byte offset of the ``<link>`` tag in ``html``, or
        -1 if missing."""
        out = []
        for name in filenames:
            # [2026-08-26] The links carry a cache-buster query string
            # (`?v=v21-20260625-csp`), so an exact-quote match found
            # nothing and every page reported all three stylesheets
            # missing. Allow the query, still anchored on the filename.
            m = re.search(
                r'<link[^>]+href="/static/' + re.escape(name) + r'(?:\?[^"]*)?"',
                html,
            )
            out.append((name, m.start() if m else -1))
        return out

    def test_every_extracted_page_link_order(self):
        # Drives off ``_EXTRACTED`` so adding a new page (or removing
        # one) updates the rollout in one place. Each page must link
        # ``tokens.css → <page>.css → mobile.css`` strictly in that
        # source order.
        for html_name, css_name in _ALL_PAGE_CSS.items():
            with self.subTest(page=html_name):
                html = (FRONTEND / html_name).read_text(encoding="utf-8")
                rows = self._link_indexes(html,
                    ["tokens.css", css_name, "mobile.css"])
                for fname, pos in rows:
                    with self.subTest(file=fname):
                        self.assertGreater(pos, 0,
                            f"{html_name} must link /static/{fname}")
                positions = [p for _, p in rows]
                self.assertEqual(positions, sorted(positions),
                    f"{html_name} links must appear in "
                    f"tokens → {css_name} → mobile order, "
                    f"got positions {positions}")


class InlineResidualTests(unittest.TestCase):
    """The point of the extraction is to shrink the inline block,
    not to merely add a sibling file. After extraction the
    remaining inline ``<style>`` content on each migrated page must
    be small."""

    def test_extracted_pages_have_small_residual_inline(self):
        for html_name in _EXTRACTED:
            with self.subTest(page=html_name):
                html = (FRONTEND / html_name).read_text(encoding="utf-8")
                residual = _inline_style_body(html)
                self.assertLessEqual(
                    len(residual),
                    _RESIDUAL_INLINE_CAP_BYTES,
                    f"{html_name} still inlines {len(residual)}B of "
                    f"CSS; cap is {_RESIDUAL_INLINE_CAP_BYTES}B for "
                    "extracted pages",
                )

    def test_legacy_pages_still_inline(self):
        # Guardrail — if a future PR silently extracts workspace or
        # graph without updating _EXTRACTED, this catches the drift.
        for html_name in _STILL_INLINE:
            with self.subTest(page=html_name):
                html = (FRONTEND / html_name).read_text(encoding="utf-8")
                residual = _inline_style_body(html)
                self.assertGreater(
                    len(residual), _RESIDUAL_INLINE_CAP_BYTES,
                    f"{html_name} has shrunk past the inline cap; "
                    "promote it to _EXTRACTED in this test and add "
                    "the matching CSS file",
                )


class RolloutCompleteTests(unittest.TestCase):
    """Every page-level *.html under frontend/ must be accounted
    for — either extracted or knowingly legacy. New pages will
    trip this guard until they're added to one of the two sets."""

    def test_every_page_accounted_for(self):
        names = {
            p.name for p in FRONTEND.glob("*.html") if p.is_file()
        }
        accounted = set(_ALL_PAGE_CSS) | _STILL_INLINE
        missing = names - accounted
        self.assertEqual(
            missing, set(),
            "new page-level HTML file(s) without an entry in either "
            "_EXTRACTED / _EXTERNAL_FROM_BIRTH / _STILL_INLINE: " + ", ".join(sorted(missing)),
        )


if __name__ == "__main__":
    unittest.main()
