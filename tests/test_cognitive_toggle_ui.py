"""PR-2 — admin UI cognitive feature-toggle surface.

Static checks on admin.html + admin.js + i18n.js for the section
that surfaces `core/feature_flags.py` toggles to the operator.

Tests follow the existing frontend-snapshot pattern (see
test_first_run_wizard.py, test_install_progress.py): no browser,
no DOM emulation — just substring/regex checks that pin the
critical wiring so future refactors can't silently strip it.
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
ADMIN_HTML = ROOT / "frontend" / "admin.html"
ADMIN_JS   = ROOT / "frontend" / "static" / "admin.js"
I18N_JS    = ROOT / "frontend" / "static" / "i18n.js"


class AdminHtmlSectionTests(unittest.TestCase):
    """The Cognitive Features section is wired into the settings page
    with the documented DOM IDs the admin.js handlers depend on."""

    @classmethod
    def setUpClass(cls):
        cls.html = ADMIN_HTML.read_text(encoding="utf-8")

    def test_section_title_present(self):
        self.assertIn('data-i18n="set.cognitive_title"', self.html,
            "Cognitive Features section title key must be wired")

    def test_section_lives_inside_settings_page(self):
        # The new section must appear inside #page-settings.
        idx_page  = self.html.index('id="page-settings"')
        idx_close = self.html.index('</div>',
            self.html.index('save-cognitive-flags', idx_page))
        self.assertGreater(idx_close, idx_page,
            "cognitive section must close inside the settings page")
        # Hint that surfaces the in-process-only persistence.
        section = self.html[idx_page:idx_close + 6]
        self.assertIn('data-i18n="set.cognitive_hint"', section)

    def test_flag_rows_container_id(self):
        # admin.js targets `#cognitive-flag-rows` for the JS-rendered
        # row list. Renaming this without updating the JS would silently
        # break the UI — pin the id here.
        self.assertIn('id="cognitive-flag-rows"', self.html)

    def test_save_button_uses_data_action(self):
        # Inline onclick is forbidden (§5 migration); the save button
        # must route through the data-action delegate.
        self.assertIn('data-action="save-cognitive-flags"', self.html)
        self.assertIn('data-i18n="set.cognitive_save"', self.html)


class AdminJsHandlerTests(unittest.TestCase):
    """admin.js carries the GET/POST + data-action wiring; the
    section render uses _escHtml + Auth-aware fetch."""

    @classmethod
    def setUpClass(cls):
        cls.js = ADMIN_JS.read_text(encoding="utf-8")

    def test_data_action_routed(self):
        # The click delegate must dispatch save-cognitive-flags.
        self.assertIn("case 'save-cognitive-flags':", self.js)
        self.assertIn("saveCognitiveFlags()", self.js)

    def test_load_function_defined(self):
        self.assertIn("async function loadCognitiveFlags", self.js,
            "loadCognitiveFlags must be defined")

    def test_save_function_defined(self):
        self.assertIn("async function saveCognitiveFlags", self.js,
            "saveCognitiveFlags must be defined")

    def test_load_uses_get_endpoint(self):
        idx = self.js.index("async function loadCognitiveFlags")
        body = self.js[idx:idx + 3500]
        self.assertIn("/admin/settings/cognitive", body,
            "loadCognitiveFlags must hit the cognitive endpoint")

    def test_save_posts_to_endpoint_with_api_key_in_body(self):
        idx = self.js.index("async function saveCognitiveFlags")
        body = self.js[idx:idx + 3500]
        self.assertIn("/admin/settings/cognitive", body)
        self.assertIn("'POST'", body, "save must use POST")
        # api_key + flags shape in the JSON body
        self.assertIn("api_key", body)
        self.assertIn("flags", body)

    def test_save_aggregates_checkboxes_with_data_flag_key(self):
        # Contract — the load function STAMPS `data-flag-key` on each
        # checkbox (HTML attribute), the save function READS the key
        # via `dataset.flagKey` (JS camelCase API for the same attr).
        # Both halves must be pinned so a refactor that renames either
        # side breaks the data flow loudly here.
        save_idx = self.js.index("async function saveCognitiveFlags")
        save_body = self.js[save_idx:save_idx + 3500]
        self.assertIn("cognitive-flag-checkbox", save_body,
            "save must collect inputs by the documented class")
        self.assertIn("dataset.flagKey", save_body,
            "save must read the flag key via dataset.flagKey")
        load_idx = self.js.index("async function loadCognitiveFlags")
        load_body = self.js[load_idx:load_idx + 3500]
        self.assertIn("data-flag-key=", load_body,
            "load must render the data-flag-key attribute on each "
            "checkbox so save's dataset.flagKey read has something "
            "to find")

    def test_load_is_called_when_settings_page_loads(self):
        # The settings router (loadSettings or the page-show case)
        # must trigger loadCognitiveFlags so the rows hydrate
        # without an extra user click.
        idx = self.js.index("async function loadSettings")
        # Boundary at the next async-function decl (closest match).
        m = re.search(r"\nasync function\s+\w+\s*\(", self.js[idx + 1:])
        end = idx + 1 + m.start() if m else idx + 5000
        body = self.js[idx:end]
        self.assertIn("loadCognitiveFlags", body,
            "loadSettings must call loadCognitiveFlags so the rows "
            "hydrate when the settings page mounts")

    def test_render_uses_esc_html(self):
        # Defense: every interpolated string from the backend goes
        # through _escHtml. The rendering loop must use it on label,
        # env, module — otherwise a malicious label could XSS the
        # admin tab.
        idx = self.js.index("async function loadCognitiveFlags")
        body = self.js[idx:idx + 3500]
        self.assertGreaterEqual(body.count("_escHtml"), 3,
            "render must escape every backend-sourced string "
            "(label, env, module, key) via _escHtml")

    def test_save_only_fires_on_button_action(self):
        # No inline onclick — must come through the click delegate.
        idx_save = self.js.index("async function saveCognitiveFlags")
        # Walk backwards looking for "onclick" attribute references
        # in the surrounding 200 chars — none allowed.
        window = self.js[max(0, idx_save - 200):idx_save + 200]
        # data-action wiring is OK; explicit `onclick=` is not.
        self.assertNotIn("onclick=", window,
            "save-cognitive-flags must NOT use inline onclick")


class I18nKeysTests(unittest.TestCase):
    """Every cognitive i18n key referenced in admin.html / admin.js
    must be defined in both en and ko locales."""

    @classmethod
    def setUpClass(cls):
        cls.i18n_text = I18N_JS.read_text(encoding="utf-8")
        cls.html_text = ADMIN_HTML.read_text(encoding="utf-8")
        cls.js_text   = ADMIN_JS.read_text(encoding="utf-8")
        # Boundary between en + ko in i18n.js:
        ko_idx = cls.i18n_text.index("  ko: {")
        cls.en_block = cls.i18n_text[:ko_idx]
        cls.ko_block = cls.i18n_text[ko_idx:]

    REQUIRED_KEYS = [
        "set.cognitive_title",
        "set.cognitive_subtitle",
        "set.cognitive_hint",
        "set.cognitive_save",
        "set.cognitive_saved",
        "set.cognitive_no_changes",
    ]

    def test_every_required_key_defined_in_en(self):
        for k in self.REQUIRED_KEYS:
            with self.subTest(key=k):
                self.assertIn(f"'{k}':", self.en_block,
                    f"key {k} missing in en")

    def test_every_required_key_defined_in_ko(self):
        for k in self.REQUIRED_KEYS:
            with self.subTest(key=k):
                self.assertIn(f"'{k}':", self.ko_block,
                    f"key {k} missing in ko")

    def test_keys_referenced_in_html_are_defined(self):
        # data-i18n="set.cognitive_*" references in admin.html
        refs = re.findall(r'data-i18n="(set\.cognitive_[a-z_]+)"',
                          self.html_text)
        self.assertGreater(len(refs), 0,
            "admin.html must reference at least one cognitive i18n key")
        for k in set(refs):
            with self.subTest(key=k):
                self.assertIn(f"'{k}':", self.en_block,
                    f"HTML references {k} which is not defined in en")


if __name__ == "__main__":
    unittest.main()
