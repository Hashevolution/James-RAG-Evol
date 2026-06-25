#!/usr/bin/env python3
"""v0.6.1 — migrate HTML inline ``style="..."`` attributes to CSS classes.

Part of the CSP ``style-src 'self'`` graduation (the inline-style audit
``docs/reviews/v0.5-ui-6-inline-style-audit.md`` Option B). Strict
``style-src`` forbids inline ``style="..."`` attributes; this script
relocates every static HTML inline style into a class so the markup no
longer needs ``'unsafe-inline'`` for the HTML surface.

Scope: the 5 served HTML pages (index / admin / graph / workspace /
intro). It does NOT touch JS-injected inline styles (innerHTML
templates, ``.style.cssText``, ``setAttribute('style')``) — those are a
separate, larger surface and remain ``'unsafe-inline'``-dependent until a
follow-up cycle. Consequently this script does NOT flip CSP to enforce.

## Strategy — hybrid, with a verbatim fallback that guarantees fidelity

For each ``style="..."`` value:

  * If every declaration is in the curated ATOM whitelist → emit one
    atom class per declaration (e.g. ``display:flex;gap:8px`` →
    ``class="d-flex gap-8"``). Atoms are reused across the whole UI.
  * Otherwise → emit ONE verbatim "component" class whose CSS body is
    the original declarations unchanged (``.u-<hash> { ... }``). Identical
    values share one class. This fallback can represent ANY value
    losslessly, so the migration can never silently drop a declaration —
    the atom whitelist is purely an optimisation for readable markup.

``display:none`` maps to ``.d-none`` WITHOUT ``!important`` so that JS
which toggles ``el.style.display = '...'`` still overrides it (an inline
property beats a single class). This is why we don't reuse the existing
``.is-hidden`` (which is ``!important`` for ``classList``-driven toggles).

## Usage

    python scripts/migrate_inline_styles.py --report   # dry-run summary
    python scripts/migrate_inline_styles.py --apply     # rewrite files

``--apply`` rewrites the 5 HTML files in place and rewrites the generated
CSS block in ``frontend/static/tokens.css`` between the marker comments.
Re-running ``--apply`` on already-migrated files is a no-op for the HTML
(no ``style=`` left) and regenerates an identical CSS block (the block is
derived only from the markup, so it stays in sync).
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

REPO = Path(__file__).resolve().parents[1]
FRONTEND = REPO / "frontend"
TOKENS_CSS = FRONTEND / "static" / "tokens.css"

PAGES = [
    FRONTEND / "index.html",
    FRONTEND / "admin.html",
    FRONTEND / "graph.html",
    FRONTEND / "workspace.html",
    FRONTEND / "intro.html",
]

CSS_BEGIN = "/* ==== BEGIN generated inline-style migration (v0.6.1 CSP) ==== */"
CSS_END = "/* ==== END generated inline-style migration (v0.6.1 CSP) ==== */"


# ─── Atom whitelist ───────────────────────────────────────────────────
# Maps a NORMALISED declaration (``prop:value``, no spaces around ``:``,
# single internal spaces, no trailing ``;``) → atom class name. Only the
# common, reusable, single-property declarations live here; anything not
# listed forces its whole style value into a verbatim component class.
# `display:none` is intentionally NON-`!important` (see module docstring).
ATOMS: Dict[str, str] = {
    # display
    "display:flex": "d-flex",
    "display:none": "d-none",
    "display:block": "d-block",
    "display:grid": "d-grid",
    "display:inline-block": "d-inline-block",
    # flex
    "flex-direction:column": "flex-col",
    "flex-wrap:wrap": "flex-wrap",
    "flex:1": "flex-1",
    "flex:2": "flex-2",
    # align / justify
    "align-items:center": "items-center",
    "align-items:flex-start": "items-start",
    "align-items:flex-end": "items-end",
    "align-self:center": "self-center",
    "align-self:start": "self-start",
    "justify-content:center": "justify-center",
    "justify-content:flex-end": "justify-end",
    "justify-content:space-between": "justify-between",
    # gap
    "gap:4px": "gap-4",
    "gap:6px": "gap-6",
    "gap:8px": "gap-8",
    "gap:10px": "gap-10",
    "gap:14px": "gap-14",
    # margin (single value)
    "margin:0": "m-0",
    "margin-top:4px": "mt-4",
    "margin-top:6px": "mt-6",
    "margin-top:8px": "mt-8",
    "margin-top:10px": "mt-10",
    "margin-top:12px": "mt-12",
    "margin-top:16px": "mt-16",
    "margin-top:20px": "mt-20",
    "margin-bottom:4px": "mb-4",
    "margin-bottom:6px": "mb-6",
    "margin-bottom:8px": "mb-8",
    "margin-bottom:10px": "mb-10",
    "margin-bottom:12px": "mb-12",
    "margin-bottom:14px": "mb-14",
    "margin-bottom:16px": "mb-16",
    "margin-bottom:20px": "mb-20",
    "margin-left:auto": "ml-auto",
    "margin-left:6px": "ml-6",
    "margin-left:8px": "ml-8",
    "margin-left:10px": "ml-10",
    "margin-left:12px": "ml-12",
    "margin-right:3px": "mr-3",
    "margin-right:4px": "mr-4",
    # padding (common)
    "padding:10px": "p-10",
    "padding:16px": "p-16",
    "padding:20px": "p-20",
    "padding:8px 10px": "p-8-10",
    "padding:7px 10px": "p-7-10",
    "padding:8px 20px": "p-8-20",
    "padding:9px 12px": "p-9-12",
    "padding:6px 12px": "p-6-12",
    "padding:8px 12px": "p-8-12",
    "padding:12px 20px": "p-12-20",
    "padding:10px 14px": "p-10-14",
    "padding:16px 0": "p-16-0",
    "padding:16px 20px": "p-16-20",
    "padding:3px 10px": "p-3-10",
    "padding:6px 10px": "p-6-10",
    # font-size
    "font-size:10px": "fs-10",
    "font-size:11px": "fs-11",
    "font-size:12px": "fs-12",
    "font-size:13px": "fs-13",
    "font-size:14px": "fs-14",
    "font-size:15px": "fs-15",
    "font-size:16px": "fs-16",
    "font-size:inherit": "fs-inherit",
    # font-weight
    "font-weight:400": "fw-400",
    "font-weight:600": "fw-600",
    "font-weight:700": "fw-700",
    # font-family
    "font-family:var(--font-mono)": "font-mono",
    "font-family:var(--font-ui)": "font-ui",
    # color
    "color:var(--muted)": "c-muted",
    "color:var(--text)": "c-text",
    "color:var(--text-soft)": "c-text-soft",
    "color:var(--text-2)": "c-text-2",
    "color:var(--accent-fg)": "c-accent-fg",
    "color:var(--danger)": "c-danger",
    "color:var(--accent)": "c-accent",
    "color:var(--on-accent)": "c-on-accent",
    # background
    "background:var(--bg)": "bg-bg",
    "background:var(--surface)": "bg-surface",
    "background:var(--surface-2)": "bg-surface-2",
    "background:var(--accent)": "bg-accent",
    "background:transparent": "bg-transparent",
    # border
    "border:1px solid var(--border)": "bd-1",
    "border:none": "bd-none",
    "border:0": "bd-0",
    "border-radius:6px": "br-6",
    "border-radius:7px": "br-7",
    "border-radius:8px": "br-8",
    # sizing
    "width:100%": "w-full",
    "min-width:260px": "minw-260",
    # text
    "cursor:pointer": "cursor-pointer",
    "text-align:center": "text-center",
    "text-decoration:none": "no-underline",
    "text-decoration:underline": "underline",
    "line-height:1.5": "lh-15",
    "line-height:1.6": "lh-16",
    "letter-spacing:1px": "ls-1",
    "letter-spacing:.5px": "ls-05",
    "letter-spacing:0": "ls-0",
    # position / misc
    "position:relative": "pos-relative",
    "position:fixed": "pos-fixed",
    "vertical-align:middle": "va-middle",
    "vertical-align:-2px": "va-n2",
    "white-space:pre-wrap": "ws-pre-wrap",
    "word-break:break-all": "wb-all",
    "word-break:break-word": "wb-word",
    "resize:vertical": "resize-v",
    "overflow:auto": "ov-auto",
    "overflow:hidden": "ov-hidden",
    "overflow-y:auto": "ovy-auto",
    "outline:none": "outline-none",
    "accent-color:var(--accent)": "accent-accent",
}

# CSS body for each atom = its declaration (atom→decl is ATOMS inverted).
ATOM_DECL: Dict[str, str] = {cls: decl for decl, cls in ATOMS.items()}
assert len(ATOM_DECL) == len(ATOMS), "duplicate atom class name detected"


def normalise_decl(decl: str) -> str:
    """Normalise one ``prop:value`` declaration (semantics-preserving)."""
    decl = decl.strip()
    if not decl:
        return ""
    prop, _, value = decl.partition(":")
    prop = prop.strip().lower()
    value = re.sub(r"\s+", " ", value.strip())
    return f"{prop}:{value}"


def split_decls(style_value: str) -> List[str]:
    """Split a style attribute value into normalised declarations."""
    out = []
    for raw in style_value.split(";"):
        d = normalise_decl(raw)
        if d:
            out.append(d)
    return out


def component_name(decls: List[str]) -> str:
    """Deterministic, collision-resistant class name for a verbatim value."""
    key = ";".join(decls)
    h = hashlib.md5(key.encode("utf-8")).hexdigest()[:8]
    return f"u-{h}"


def classes_for(
    style_value: str,
    components: Dict[str, List[str]],
    used_atoms: Dict[str, None],
) -> List[str]:
    """Resolve a style value to a list of class names.

    Records any verbatim component into ``components`` (name → decls)
    and any atom used into ``used_atoms``.
    """
    decls = split_decls(style_value)
    if not decls:
        return []
    if all(d in ATOMS for d in decls):
        # de-dup while preserving declaration order
        seen, atoms = set(), []
        for d in decls:
            cls = ATOMS[d]
            if cls not in seen:
                seen.add(cls)
                atoms.append(cls)
                used_atoms[cls] = None
        return atoms
    name = component_name(decls)
    components.setdefault(name, decls)
    return [name]


# Matches a single opening tag that carries a ``style="..."`` attribute.
# Attribute values in these files never contain ``>`` (verified), so
# ``[^>]*`` correctly stops at the tag's own ``>``.
_TAG_RE = re.compile(r"<[a-zA-Z][^>]*\sstyle=\"[^\"]*\"[^>]*>")
_STYLE_RE = re.compile(r"\sstyle=\"([^\"]*)\"")
_CLASS_RE = re.compile(r"\sclass=\"([^\"]*)\"")
_TAGNAME_RE = re.compile(r"^<([a-zA-Z][\w-]*)")


def rewrite_tag(
    tag: str,
    components: Dict[str, List[str]],
    used_atoms: Dict[str, None],
) -> str:
    m_style = _STYLE_RE.search(tag)
    if not m_style:
        return tag
    new_classes = classes_for(m_style.group(1), components, used_atoms)
    # remove the style attribute
    tag = tag[: m_style.start()] + tag[m_style.end():]
    if not new_classes:
        return tag
    m_class = _CLASS_RE.search(tag)
    if m_class:
        existing = m_class.group(1).split()
        merged = existing + [c for c in new_classes if c not in existing]
        new_attr = ' class="' + " ".join(merged) + '"'
        return tag[: m_class.start()] + new_attr + tag[m_class.end():]
    # no class attr — insert one right after the tag name
    m_name = _TAGNAME_RE.match(tag)
    insert_at = m_name.end()
    return (
        tag[:insert_at]
        + ' class="' + " ".join(new_classes) + '"'
        + tag[insert_at:]
    )


def migrate_html(
    text: str,
    components: Dict[str, List[str]],
    used_atoms: Dict[str, None],
) -> Tuple[str, int]:
    count = [0]

    def repl(m: re.Match) -> str:
        count[0] += 1
        return rewrite_tag(m.group(0), components, used_atoms)

    new_text = _TAG_RE.sub(repl, text)
    return new_text, count[0]


def generate_css(used_atoms: Dict[str, None], components: Dict[str, List[str]]) -> str:
    lines = [CSS_BEGIN,
             "/* Auto-generated by scripts/migrate_inline_styles.py — do not",
             " * hand-edit between the markers; re-run the script instead.",
             " * Atoms (reusable single-property utilities) + components",
             " * (verbatim relocations of one-off inline styles). Enables",
             " * CSP style-src without 'unsafe-inline' for the HTML surface. */"]
    # Atoms, grouped, sorted for stable output
    lines.append("/* atoms */")
    for cls in sorted(used_atoms):
        lines.append(f".{cls}{{{ATOM_DECL[cls]}}}")
    # Components
    if components:
        lines.append("/* components (verbatim one-off styles) */")
        for name in sorted(components):
            body = ";".join(components[name])
            lines.append(f".{name}{{{body}}}")
    lines.append(CSS_END)
    return "\n".join(lines) + "\n"


def upsert_css_block(css_text: str, block: str) -> str:
    if CSS_BEGIN in css_text and CSS_END in css_text:
        pre = css_text[: css_text.index(CSS_BEGIN)]
        post = css_text[css_text.index(CSS_END) + len(CSS_END):]
        return pre.rstrip() + "\n\n" + block + post.lstrip("\n")
    return css_text.rstrip() + "\n\n\n" + block


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--report", action="store_true", help="dry-run summary")
    g.add_argument("--apply", action="store_true", help="rewrite files")
    args = ap.parse_args()

    components: Dict[str, List[str]] = {}
    used_atoms: Dict[str, None] = {}
    rewrites: Dict[Path, str] = {}
    total = 0

    for page in PAGES:
        text = page.read_text(encoding="utf-8")
        new_text, n = migrate_html(text, components, used_atoms)
        total += n
        rewrites[page] = new_text
        print(f"  {n:4d}  {page.relative_to(REPO)}")

    print(f"\nTotal inline style attrs migrated: {total}")
    print(f"Atoms used: {len(used_atoms)} / {len(ATOMS)} defined")
    print(f"Verbatim component classes: {len(components)}")

    if args.report:
        print("\n[report only -- no files written]")
        # show a few sample components
        for name in sorted(components)[:8]:
            print(f"  .{name} {{ {';'.join(components[name])} }}")
        return 0

    # --apply
    for page, new_text in rewrites.items():
        page.write_text(new_text, encoding="utf-8")
    block = generate_css(used_atoms, components)
    tokens = TOKENS_CSS.read_text(encoding="utf-8")
    TOKENS_CSS.write_text(upsert_css_block(tokens, block), encoding="utf-8")
    print(f"\nWrote {len(rewrites)} HTML files + CSS block in {TOKENS_CSS.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
