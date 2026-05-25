"""v0.4 Sprint 2 #6 — frontend i18n key parity for character profile.

Regression guard for the bug where the admin Character page kept
showing Korean labels in EN mode. Root cause was a layer below
the existing PR-4 ``label_key`` contract (already covered by
``test_character_profile_i18n.py``): the summary card body
(``buildCharacterSummary``) and the connections panel
(``renderConnectionsPanel``) rendered ~25 Korean strings via plain
template-literal concatenation, never going through ``t()``.

This file pins two invariants — neither can be checked at runtime
unless the admin page is rendered in a browser:

  1. Every ``char.*`` key in i18n.js EN dict has a KO counterpart
     and vice versa. Adding a key on only one side silently
     regresses the page (key falls back to the EN value or the
     raw key string).

  2. Every ``t('char.…')`` call site in admin.js resolves to a key
     that exists in BOTH dicts. A typo would have rendered the
     literal key string (e.g. "char.conn.pair_titel") on the UI
     and would otherwise need browser testing to spot.

Run: ``pytest tests/test_i18n_char_keys_parity.py``
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

REPO = Path(__file__).resolve().parent.parent
I18N_JS = REPO / "frontend" / "static" / "i18n.js"
ADMIN_JS = REPO / "frontend" / "static" / "admin.js"


def _extract_char_keys_per_lang(source: str) -> dict:
    """Walk i18n.js and bucket char.* keys by their containing lang
    block. The file structure is:

        const TRANSLATIONS = {
          en: { 'key': 'val', ... },
          ko: { 'key': 'val', ... }
        };

    Track depth via lang headers (``en: {`` / ``ko: {``) and the
    matching close brace. This is more robust than a single regex
    against the whole file when keys span multiple lines.
    """
    keys: dict = {"en": set(), "ko": set()}
    current_lang = None
    for line in source.splitlines():
        m_open = re.match(r"^\s*(en|ko):\s*\{", line)
        if m_open:
            current_lang = m_open.group(1)
            continue
        # Treat any bare-ish closing brace as the end of the lang block.
        if re.match(r"^\s*\}\s*[,;]?\s*$", line):
            current_lang = None
            continue
        if current_lang is None:
            continue
        m_key = re.search(r"'(char\.[^']+)'\s*:", line)
        if m_key:
            keys[current_lang].add(m_key.group(1))
    return keys


def _extract_char_t_calls(source: str) -> set:
    """Pull every literal ``t('char.…')`` key from admin.js. Skip
    computed forms like ``t('char.trait.' + id)`` — those are
    covered by ``test_character_profile_i18n.py`` (one key per
    trait, ID convention pinned).

    The trailing ``\\s*[),]`` anchor distinguishes a complete key
    (``t('char.foo')`` or ``t('char.foo', {…})``) from a prefix
    used in concatenation (``t('char.foo.' + id + '.hi')``).
    """
    out = set()
    for m in re.finditer(
        r"\bt\(\s*'(char\.[A-Za-z0-9_.]+?)'\s*[),]", source
    ):
        out.add(m.group(1))
    return out


class CharI18nParityTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.i18n_src = I18N_JS.read_text(encoding="utf-8")
        cls.admin_src = ADMIN_JS.read_text(encoding="utf-8")
        cls.keys = _extract_char_keys_per_lang(cls.i18n_src)

    def test_en_and_ko_dicts_have_same_char_keys(self):
        en = self.keys["en"]
        ko = self.keys["ko"]
        only_en = en - ko
        only_ko = ko - en
        self.assertEqual(
            only_en, set(),
            f"char.* keys present in EN but missing in KO: {sorted(only_en)}",
        )
        self.assertEqual(
            only_ko, set(),
            f"char.* keys present in KO but missing in EN: {sorted(only_ko)}",
        )
        self.assertGreaterEqual(
            len(en), 60,
            "expected at least 60 char.* keys after v0.4 Sprint 2 #6 "
            "(summary card + connections panel additions). Got "
            f"{len(en)} — did someone delete the new keys?",
        )

    def test_admin_js_calls_only_known_char_keys(self):
        called = _extract_char_t_calls(self.admin_src)
        defined = self.keys["en"] & self.keys["ko"]
        unknown = called - defined
        self.assertEqual(
            unknown, set(),
            "admin.js calls t('char.…') with keys not defined in i18n.js. "
            f"Missing keys: {sorted(unknown)}. "
            "Add them to BOTH the en and ko dicts.",
        )

    def test_v04_sprint2_6_keys_present(self):
        """Explicit anchor — the specific keys added by v0.4 Sprint 2 #6.
        Removing any of these silently degrades the character page.
        """
        required = {
            # Summary card frame (replaces hardcoded CORE/VALUES/STYLE
            # spans in admin.html)
            "char.card.core",
            "char.card.values",
            "char.card.style",
            # Summary card body (replaces Korean strings in
            # buildCharacterSummary)
            "char.summary.core_balanced",
            "char.summary.core_prominent",
            "char.summary.values_empty",
            "char.summary.style_balanced",
            "char.summary.style_suffix",
            # Connections panel (replaces Korean strings in
            # renderConnectionsPanel)
            "char.conn.strength_strong",
            "char.conn.strength_mid",
            "char.conn.strength_weak",
            "char.conn.pair_title",
            "char.conn.pair_explain",
            "char.conn.out_title",
            "char.conn.out_row_pos",
            "char.conn.out_row_neg",
            "char.conn.in_title",
            "char.conn.in_row_pos",
            "char.conn.in_row_neg",
            "char.conn.indep_empty",
        }
        defined = self.keys["en"] & self.keys["ko"]
        missing = required - defined
        self.assertEqual(
            missing, set(),
            f"v0.4 Sprint 2 #6 keys missing from i18n.js: {sorted(missing)}",
        )


if __name__ == "__main__":
    unittest.main()
