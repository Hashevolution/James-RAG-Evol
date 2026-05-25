"""Configure → LLM Task mapping UI (UI-IA risk signal #2 fix).

Static checks on admin.html + admin.js + i18n.js for the section
that surfaces the three previously-orphan endpoints:
  - GET    /admin/llm/selections
  - POST   /admin/llm/select
  - DELETE /admin/llm/select

Same static-snapshot pattern as test_cognitive_toggle_ui.py.
No browser; pins critical wiring so future refactors break loudly.
"""
from __future__ import annotations

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
    """LLM Task → Model section is wired into the settings page with
    the documented DOM ids the admin.js handlers depend on."""

    @classmethod
    def setUpClass(cls):
        cls.html = ADMIN_HTML.read_text(encoding="utf-8")

    def test_section_title_key_present(self):
        self.assertIn('data-i18n="set.llm_selection_title"', self.html)

    def test_section_lives_inside_settings_page(self):
        idx_page = self.html.index('id="page-settings"')
        idx_close = self.html.index(
            '</div>',
            self.html.index('save-llm-selections', idx_page),
        )
        self.assertGreater(idx_close, idx_page,
            "LLM selection section must close inside #page-settings")
        section = self.html[idx_page:idx_close + 6]
        self.assertIn('data-i18n="set.llm_selection_hint"', section)

    def test_row_container_id(self):
        self.assertIn('id="llm-selection-rows"', self.html)

    def test_save_button_uses_data_action(self):
        self.assertIn('data-action="save-llm-selections"', self.html)
        self.assertIn('data-i18n="set.llm_selection_save"', self.html)


class AdminJsHandlerTests(unittest.TestCase):
    """admin.js carries the load + save + diff logic; uses _escHtml,
    Bearer auth, and re-renders on save for canonical server state."""

    @classmethod
    def setUpClass(cls):
        cls.js = ADMIN_JS.read_text(encoding="utf-8")

    def test_data_action_routed(self):
        self.assertIn("case 'save-llm-selections':", self.js)
        self.assertIn("saveLlmSelections()", self.js)

    def test_load_function_defined(self):
        self.assertIn("async function loadLlmSelections", self.js)

    def test_save_function_defined(self):
        self.assertIn("async function saveLlmSelections", self.js)

    def test_task_types_constant_lists_five_canonical(self):
        # The five rows the UI always shows.
        idx = self.js.index("const LLM_TASK_TYPES")
        body = self.js[idx:idx + 2000]
        for key in ("general", "classify", "extract", "coding", "vision"):
            with self.subTest(task=key):
                self.assertIn(f"'{key}'", body,
                    f"LLM_TASK_TYPES must list canonical task '{key}'")

    def test_load_reads_both_installed_and_selections(self):
        idx = self.js.index("async function loadLlmSelections")
        body = self.js[idx:idx + 4000]
        self.assertIn("/admin/llm/installed", body,
            "load must fetch installed models (dropdown options)")
        self.assertIn("/admin/llm/selections", body,
            "load must fetch current task→model mapping")

    def test_load_uses_promise_all_for_parallel_fetch(self):
        idx = self.js.index("async function loadLlmSelections")
        body = self.js[idx:idx + 4000]
        self.assertIn("Promise.all", body,
            "load should fetch installed + selections in parallel — "
            "two sequential round-trips would double the latency")

    def test_save_posts_to_select_endpoint(self):
        idx = self.js.index("async function saveLlmSelections")
        body = self.js[idx:idx + 5000]
        self.assertIn("/admin/llm/select", body,
            "save must POST/DELETE to /admin/llm/select")
        # Both methods must be exercised (set vs clear).
        self.assertIn("'POST'", body)
        self.assertIn("'DELETE'", body)

    def test_save_diffs_against_initial_state(self):
        # Only changed rows hit the network — keeps audit clean and
        # avoids triggering ollama membership checks on unchanged rows.
        idx = self.js.index("async function saveLlmSelections")
        body = self.js[idx:idx + 5000]
        self.assertIn("data-task-initial", body,
            "save must compare against data-task-initial to compute diff")
        # The diff loop should treat empty selection as DELETE, non-
        # empty as POST. Pin both branches.
        self.assertIn("toRemove", body)
        self.assertIn("toSet", body)

    def test_save_reloads_after_success(self):
        idx = self.js.index("async function saveLlmSelections")
        body = self.js[idx:idx + 5000]
        self.assertIn("loadLlmSelections()", body,
            "save must re-render so the next click's diff is computed "
            "against the fresh server state")

    def test_load_is_called_on_settings_mount(self):
        idx = self.js.index("async function loadSettings")
        m = re.search(r"\nasync function\s+\w+\s*\(",
                      self.js[idx + 1:])
        end = idx + 1 + m.start() if m else idx + 5000
        body = self.js[idx:end]
        self.assertIn("loadLlmSelections", body,
            "loadSettings must trigger loadLlmSelections so the section "
            "hydrates when the settings tab mounts")

    def test_render_escapes_every_backend_string(self):
        # Defense: model names + selection values come from the
        # backend / ollama. Every interpolation into innerHTML must
        # go through _escHtml. The render builds option strings,
        # current-label, and the data-task-* attributes.
        idx = self.js.index("async function loadLlmSelections")
        body = self.js[idx:idx + 4000]
        self.assertGreaterEqual(body.count("_escHtml"), 5,
            "render must escape every backend-sourced string (model "
            "name, current value, task key, label) via _escHtml")


class I18nKeysTests(unittest.TestCase):
    """All required i18n keys defined in both locales; HTML refs match."""

    REQUIRED_KEYS = [
        "set.llm_selection_title",
        "set.llm_selection_subtitle",
        "set.llm_selection_hint",
        "set.llm_selection_save",
        "set.llm_saved",
        "set.llm_no_changes",
        "set.llm_no_models",
        "set.llm_default_option",
        "set.llm_default_label",
        "set.llm_task_general",
        "set.llm_task_classify",
        "set.llm_task_extract",
        "set.llm_task_coding",
        "set.llm_task_vision",
    ]

    @classmethod
    def setUpClass(cls):
        cls.i18n_text = I18N_JS.read_text(encoding="utf-8")
        cls.html_text = ADMIN_HTML.read_text(encoding="utf-8")
        ko_idx = cls.i18n_text.index("  ko: {")
        cls.en_block = cls.i18n_text[:ko_idx]
        cls.ko_block = cls.i18n_text[ko_idx:]

    def test_every_required_key_defined_in_en(self):
        for k in self.REQUIRED_KEYS:
            with self.subTest(key=k):
                self.assertIn(f"'{k}':", self.en_block,
                    f"key {k} missing in en block")

    def test_every_required_key_defined_in_ko(self):
        for k in self.REQUIRED_KEYS:
            with self.subTest(key=k):
                self.assertIn(f"'{k}':", self.ko_block,
                    f"key {k} missing in ko block")

    def test_keys_referenced_in_html_are_defined(self):
        refs = re.findall(r'data-i18n="(set\.llm_[a-z_]+)"', self.html_text)
        self.assertGreater(len(refs), 0,
            "admin.html must reference at least one LLM i18n key")
        for k in set(refs):
            with self.subTest(key=k):
                self.assertIn(f"'{k}':", self.en_block,
                    f"HTML references {k} which is not defined in en")


if __name__ == "__main__":
    unittest.main()
