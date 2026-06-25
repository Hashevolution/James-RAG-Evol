"""v0.6.1 — CSP style-src: HTML inline-style migration guard.

The 5 served HTML pages (index / admin / graph / workspace / intro) had
~600 inline ``style="..."`` attributes relocated into CSS classes
(atoms + verbatim components in ``tokens.css``) by
``scripts/migrate_inline_styles.py``. This is the HTML half of the
``style-src 'self'`` graduation (the JS-injected inline-style surface
remains, so CSP is NOT yet flipped to enforce — see
``docs/reviews/v0.5-ui-6-inline-style-audit.md``).

This lock-test pins the result so a future edit that reintroduces an
inline ``style="..."`` attribute on a served page is caught in CI
(otherwise it would silently re-block the eventual enforce flip and
break the `style-src` procurement bar without anyone noticing).

Covers:
  * Zero inline ``style="..."`` attributes in each of the 5 pages.
  * ``tokens.css`` carries the generated migration block (markers).
  * ``.d-none`` is defined WITHOUT ``!important`` so JS that toggles
    ``el.style.display`` can still override it (the migration relies on
    this — see the script docstring + the ``classList.remove('d-none')``
    show-site fixes).

Run:
  python -m unittest tests.test_v06_csp_inline_style_migration
"""
from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FRONTEND = REPO / "frontend"
TOKENS_CSS = FRONTEND / "static" / "tokens.css"

PAGES = [
    "index.html",
    "admin.html",
    "graph.html",
    "workspace.html",
    "intro.html",
]

# An inline style attribute on an HTML tag: ``<... style="...">``.
_STYLE_ATTR = re.compile(r'\sstyle="[^"]*"')


class InlineStyleMigrationGuard(unittest.TestCase):
    def test_no_inline_style_attrs_on_served_pages(self):
        offenders = {}
        for name in PAGES:
            text = (FRONTEND / name).read_text(encoding="utf-8")
            hits = _STYLE_ATTR.findall(text)
            if hits:
                offenders[name] = len(hits)
        self.assertEqual(
            offenders, {},
            "Inline style=\"...\" attributes reintroduced on served "
            "page(s) — relocate them to a class (run "
            "scripts/migrate_inline_styles.py --apply) so the CSP "
            "style-src migration stays intact: " + repr(offenders),
        )

    def test_tokens_css_has_generated_migration_block(self):
        css = TOKENS_CSS.read_text(encoding="utf-8")
        self.assertIn(
            "BEGIN generated inline-style migration", css,
            "tokens.css is missing the generated migration block "
            "(scripts/migrate_inline_styles.py --apply writes it).",
        )
        self.assertIn("END generated inline-style migration", css)

    def test_d_none_is_not_important(self):
        css = TOKENS_CSS.read_text(encoding="utf-8")
        m = re.search(r"\.d-none\s*\{([^}]*)\}", css)
        self.assertIsNotNone(m, ".d-none atom missing from tokens.css")
        body = m.group(1)
        self.assertIn("display:none", body.replace(" ", ""))
        self.assertNotIn(
            "!important", body,
            ".d-none must NOT be !important — JS toggling "
            "el.style.display must be able to override it (see "
            "scripts/migrate_inline_styles.py docstring).",
        )

    def test_migration_script_is_present_and_re_runnable(self):
        # The script is the single source of truth for the mapping; keep
        # it in the tree so the block can be regenerated deterministically.
        self.assertTrue(
            (REPO / "scripts" / "migrate_inline_styles.py").exists(),
            "scripts/migrate_inline_styles.py was removed — it is the "
            "regeneration source for the tokens.css migration block.",
        )


if __name__ == "__main__":
    unittest.main()
