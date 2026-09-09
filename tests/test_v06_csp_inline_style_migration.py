"""v0.6.1 — CSP style-src: HTML inline-style migration guard.

The 5 served HTML pages (index / admin / graph / workspace / intro) had
~600 inline ``style="..."`` attributes relocated into CSS classes
(atoms + verbatim components in ``tokens.css``) by
``scripts/migrate_inline_styles.py``. That was the HTML half of the
``style-src 'self'`` graduation; the JS-injected surface followed in
#1097-#1108, and the directive dropped ``'unsafe-inline'`` once both
were at zero (see ``docs/reviews/v0.5-ui-6-inline-style-audit.md``).

Because the directive no longer permits inline styles, this guard is
now load-bearing rather than advisory: a reintroduced ``style="..."``
would be a broken UI under ``JAMES_CSP_MODE=enforce``, not a future
inconvenience.

This lock-test pins the result so a future edit that reintroduces an
inline ``style="..."`` attribute on a served page is caught in CI
(otherwise it would silently re-block the eventual enforce flip and
break the `style-src` procurement bar without anyone noticing).

Covers:
  * Zero inline ``style="..."`` attributes in each of the 5 pages.
  * Zero inline ``style="..."`` attributes emitted by any frontend JS
    file, and zero ``setAttribute('style', …)`` call sites — that call
    writes the style ATTRIBUTE, so ``style-src`` blocks it exactly like
    one in markup, even though it looks nothing like a tag.
  * No inline ``<style>`` element on a served page: ``style-src 'self'``
    blocks those too, and none of the pages has ever had one.
  * ``tokens.css`` carries the generated migration block (markers).
  * ``.d-none`` is defined WITHOUT ``!important`` so JS that toggles
    ``el.style.display`` can still override it (the migration relies on
    this — see the script docstring + the ``classList.remove('d-none')``
    show-site fixes).

Run:
  python -m unittest tests.test_v06_csp_inline_style_migration
"""
from __future__ import annotations

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

# The same thing inside JS-built markup. The boundary is a quote as well
# as whitespace, because template literals concatenate right up against
# the attribute (`'…surface);' + 'style="…"'`).
_JS_STYLE_ATTR = re.compile(r'''(?<=['"\s])style="[^"]*"''')
_SETATTR_STYLE = re.compile(r'''setAttribute\(\s*['"]style['"]''')
_STYLE_ELEMENT = re.compile(r"<style[\s>]", re.I)

# Comments quote the banned patterns while explaining them, so they are
# removed before scanning. Crude but sufficient here: no frontend file
# contains a string literal holding "//" or "/*" outside a URL, and
# "://" is guarded against explicitly.
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_LINE_COMMENT = re.compile(r"(?<!:)//[^\n]*")


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

    def test_no_inline_style_attrs_emitted_by_frontend_js(self):
        """Every .js under frontend/static, not just the migrated ones.

        The migration tool works from its own ``JS_FILES`` list, which
        for a long time was missing ten files — so a clean report did
        not mean a clean surface. This walks the directory instead.
        """
        offenders = {}
        for js in sorted((FRONTEND / "static").glob("*.js")):
            text = js.read_text(encoding="utf-8")
            # Strip // and /* */ comments first: several of them quote
            # the very pattern being banned while explaining the ban.
            stripped = _BLOCK_COMMENT.sub("", text)
            stripped = _LINE_COMMENT.sub("", stripped)
            hits = _JS_STYLE_ATTR.findall(stripped)
            if hits:
                offenders[js.name] = len(hits)
        self.assertEqual(
            offenders, {},
            "JS emits inline style=\"...\" attribute(s). style-src no "
            "longer carries 'unsafe-inline', so these are blocked at "
            "render: use a class when the value is enumerable, or a "
            "data-* attribute plus a CSSOM write (el.style.x) when it "
            "is genuinely computed. Offenders: " + repr(offenders),
        )

    def test_no_set_attribute_style_call_sites(self):
        offenders = {}
        for js in sorted((FRONTEND / "static").glob("*.js")):
            text = js.read_text(encoding="utf-8")
            stripped = _BLOCK_COMMENT.sub("", text)
            stripped = _LINE_COMMENT.sub("", stripped)
            hits = _SETATTR_STYLE.findall(stripped)
            if hits:
                offenders[js.name] = len(hits)
        self.assertEqual(
            offenders, {},
            "setAttribute('style', ...) writes the style ATTRIBUTE, "
            "which style-src blocks just like an inline one in markup "
            "(el.style.x is CSSOM and is fine). Offenders: "
            + repr(offenders),
        )

    def test_no_inline_style_elements_on_served_pages(self):
        offenders = {}
        for name in PAGES:
            text = (FRONTEND / name).read_text(encoding="utf-8")
            hits = _STYLE_ELEMENT.findall(text)
            if hits:
                offenders[name] = len(hits)
        self.assertEqual(
            offenders, {},
            "Inline <style> element(s) on a served page — style-src "
            "'self' blocks those as well: move the rules into a linked "
            "stylesheet. Offenders: " + repr(offenders),
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
