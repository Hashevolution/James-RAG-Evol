"""[P3 unified UX, 2026-05-10] Remove free-text persona from Settings;
move Identity (name) to Character page.

User feedback (2026-05-10):
> "어드민 웹페이지에 성향 설정에 대하여 글자로 설정하는 부분과 원 그래프를
>  이용하여 조정하는 부분이 충돌할수 있는 요인으로 작동할 우려가 보인다."
> "Q3: (a) 완전 제거"

P3 changes:

  HTML
    - page-settings: '페르소나 설정' 섹션 제거 (이름/성향-역할/추가지시/
      Save Persona button + persona-preview div)
    - page-settings: '답변 언어' 단독 섹션으로 분리 (set.lang_title)
    - page-character: 상단에 Identity 섹션 추가 (이름 입력 + Save Name)

  JS
    - savePersona, updatePersonaPreview 함수 제거
    - loadSettings: persona.style / persona.custom prefill 로직 제거
    - saveIdentity 신설 — name만 /admin/persona 에 POST (style/custom = "")
    - loadIdentity 신설 — character 페이지 진입 시 name prefill
    - loadCharacter 가 loadIdentity 호출

  Backward compat
    - /admin/persona 엔드포인트는 그대로 (name 만 채워서 호출)
    - DB의 persona.style / persona.custom 행은 P4 마이그레이션에서 처리

Run:
    python -m unittest tests.test_character_remove_text_persona
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "frontend" / "admin.html"
JS = ROOT / "frontend" / "static" / "admin.js"
I18N = ROOT / "frontend" / "static" / "i18n.js"


# ─── 1. Settings page no longer has the free-text persona block ───
class SettingsPageStrippedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")

    def _settings_page(self):
        # Slice the page-settings div so we don't accidentally find
        # leftover keys in other pages (e.g., the radar's data attrs).
        idx = self.html.index('id="page-settings"')
        # Try next page id="..." marker; if absent (settings is last
        # page), slice to the closing </main> / end of body.
        marker_at = self.html.find('id="page-', idx + len('id="page-settings"') - 4)
        if marker_at == -1:
            for end_marker in ("</main>", "</body>"):
                e = self.html.find(end_marker, idx)
                if e != -1:
                    return self.html[idx:e]
            return self.html[idx:]
        return self.html[idx:marker_at]

    def test_persona_role_field_removed(self):
        block = self._settings_page()
        self.assertNotIn('id="set-style"', block,
            "성향/역할 입력(set-style)은 P3에서 제거되어야 함 — radar UI와 충돌")

    def test_persona_custom_field_removed(self):
        block = self._settings_page()
        self.assertNotIn('id="set-custom"', block,
            "추가지시 입력(set-custom)은 P3에서 제거되어야 함")

    def test_persona_preview_div_removed(self):
        block = self._settings_page()
        self.assertNotIn('id="persona-preview"', block,
            "persona-preview div는 P3에서 제거 — 미리보기 개념 폐기")

    def test_save_persona_button_removed(self):
        block = self._settings_page()
        self.assertNotIn("savePersona()", block,
            "savePersona button은 settings 페이지에서 제거되어야 함")

    def test_persona_title_removed(self):
        block = self._settings_page()
        self.assertNotIn("set.persona_title", block,
            "'JAMES 페르소나 설정' 섹션 제목 — 더 이상 사용 안 함")

    def test_set_name_no_longer_in_settings(self):
        # name 입력은 character 페이지의 Identity 섹션으로 이전됨.
        block = self._settings_page()
        self.assertNotIn('id="set-name"', block,
            "이름 입력은 character 페이지의 Identity 섹션으로 이전")

    def test_language_section_present(self):
        # 언어 설정은 단독 섹션으로 유지.
        block = self._settings_page()
        self.assertIn('id="set-language"', block,
            "답변 언어 select 는 settings 페이지에 유지 (성격이 아닌 출력 설정)")
        self.assertIn("set.lang_title", block,
            "답변 언어 섹션 제목 i18n 키(set.lang_title) 사용해야 함")


# ─── 2. Character page has the new Identity section ──────────────
class CharacterPageIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")

    def _character_page(self):
        idx = self.html.index('id="page-character"')
        marker_at = self.html.find('id="page-', idx + len('id="page-character"') - 4)
        if marker_at == -1:
            for end_marker in ("</main>", "</body>"):
                e = self.html.find(end_marker, idx)
                if e != -1:
                    return self.html[idx:e]
            return self.html[idx:]
        return self.html[idx:marker_at]

    def test_identity_section_present(self):
        block = self._character_page()
        self.assertIn("char.identity", block,
            "character 페이지 상단에 Identity 섹션 (char.identity 키) 필요")

    def test_name_input_in_character_page(self):
        block = self._character_page()
        self.assertIn('id="set-name"', block,
            "이름 입력(set-name) 은 character 페이지로 이전되어야 함")

    def test_save_identity_button_present(self):
        block = self._character_page()
        self.assertIn("saveIdentity()", block,
            "Identity 섹션의 저장 버튼은 saveIdentity() 호출 — savePersona X")

    def test_identity_label_keys(self):
        block = self._character_page()
        for key in ("char.identity_name", "char.identity_name_desc",
                    "char.identity_save"):
            self.assertIn(key, block,
                f"identity 섹션에 i18n 키 {key!r} 필요")


# ─── 3. JS: savePersona / updatePersonaPreview 함수 제거 ─────────
class JsFunctionsRemovedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_savePersona_function_removed(self):
        # 함수 정의(`async function savePersona`) 가 없어야 함.
        # 주석에 단어가 들어가는건 OK.
        self.assertNotIn("async function savePersona", self.js,
            "savePersona 함수 정의는 P3에서 제거")
        self.assertNotIn("function savePersona(", self.js,
            "savePersona 함수 정의는 P3에서 제거")

    def test_updatePersonaPreview_function_removed(self):
        self.assertNotIn("function updatePersonaPreview", self.js,
            "updatePersonaPreview 함수 정의는 P3에서 제거")

    def test_loadSettings_does_not_read_style_or_custom(self):
        # loadSettings 안에서 set-style / set-custom 관련 prefill 코드 제거.
        idx = self.js.index("async function loadSettings")
        end_marker = "\n}\n"
        end = self.js.index(end_marker, idx) + len(end_marker)
        body = self.js[idx:end]
        self.assertNotIn("set-style", body,
            "loadSettings는 set-style 입력을 더 이상 읽지 않아야 함")
        self.assertNotIn("set-custom", body,
            "loadSettings는 set-custom 입력을 더 이상 읽지 않아야 함")

    def test_loadSettings_still_reads_language(self):
        idx = self.js.index("async function loadSettings")
        end_marker = "\n}\n"
        end = self.js.index(end_marker, idx) + len(end_marker)
        body = self.js[idx:end]
        self.assertIn("set-language", body,
            "loadSettings 는 언어는 계속 prefill 해야 함 (제거 X)")


# ─── 4. JS: saveIdentity / loadIdentity 신설 ─────────────────────
class JsIdentityFunctionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_saveIdentity_function_defined(self):
        self.assertIn("async function saveIdentity", self.js,
            "P3는 saveIdentity 함수 신설 — 이름 저장 전담")

    def test_saveIdentity_exported_to_window(self):
        # Inline onclick="saveIdentity()" 가 동작하려면 window 노출 필요.
        self.assertIn("window.saveIdentity", self.js)

    def test_saveIdentity_posts_only_name(self):
        idx = self.js.index("async function saveIdentity")
        # 함수 끝까지 — 보수적으로 1500자 슬라이스.
        body = self.js[idx:idx + 2000]
        self.assertIn("/admin/persona", body,
            "saveIdentity 는 backward-compat 위해 /admin/persona 사용")
        # style / custom 은 빈 문자열로 보내야 함.
        self.assertIn("style:", body)
        self.assertIn("custom:", body)
        self.assertRegex(body, r"style\s*:\s*['\"]['\"]",
            "saveIdentity body의 style 은 빈 문자열이어야 함")
        self.assertRegex(body, r"custom\s*:\s*['\"]['\"]",
            "saveIdentity body의 custom 은 빈 문자열이어야 함")

    def test_loadIdentity_function_defined(self):
        self.assertIn("async function loadIdentity", self.js,
            "loadIdentity — 캐릭터 페이지 진입 시 이름 prefill")

    def test_loadCharacter_calls_loadIdentity(self):
        idx = self.js.index("async function loadCharacter")
        end = self.js.index("\n}\n", idx)
        body = self.js[idx:end]
        self.assertIn("loadIdentity", body,
            "loadCharacter 는 loadIdentity 를 호출해서 Identity 섹션 prefill")


# ─── 5. i18n: 새 키들이 양쪽 locale에 ─────────────────────────────
class I18nTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.i18n = I18N.read_text(encoding="utf-8")

    def test_identity_keys_in_both_locales(self):
        keys = [
            "char.identity", "char.identity_name", "char.identity_name_desc",
            "char.identity_save", "char.identity_required",
            "char.identity_saved", "char.identity_save_fail",
            "set.lang_title",
        ]
        for k in keys:
            count = self.i18n.count(f"'{k}'")
            self.assertGreaterEqual(count, 2,
                f"i18n 키 {k!r} 가 EN/KO 양쪽에 있어야 함 (found {count})")


# ─── 6. Engine prompt injection 변경 없음 (regression guard) ──────
class EnginePromptStillUsesProfileTests(unittest.TestCase):
    """character_profile.get_prompt_modifiers 가 여전히 engine에 주입됨.
    P3에서 free-text persona 를 끊었어도 trait-based directives 는 살아 있어야 함."""

    def test_engine_still_imports_character_profile(self):
        engine = (ROOT / "core" / "reasoning" / "engine.py").read_text(encoding="utf-8")
        self.assertIn("from core.character_profile import", engine,
            "엔진은 P3 이후에도 character_profile 를 import 해서 trait "
            "directives 를 system_prompt 에 주입해야 함")
        self.assertIn("get_prompt_modifiers", engine)


if __name__ == "__main__":
    unittest.main()
