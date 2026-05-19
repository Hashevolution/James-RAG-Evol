"""[P4 unified UX, 2026-05-10] Stop reading persona.style / persona.custom
in the LLM system prompt.

Background — 4-PR redesign:
  P1: backend traits 11→16 + correlations + ripple
  P2: interactive SVG radar UI
  P3: remove free-text persona from frontend (Settings → Character Identity)
  P4 (this PR): backend cleanup — get_system_prompt drops style/custom

Why P4 is its own PR:
  Even after P3 removed the frontend inputs, the backend still injected any
  legacy persona.style / persona.custom values stored in the DB into every
  LLM prompt. That makes 'P3' incomplete — the conflict between the radar's
  parametric sliders and old free-text directives lives on for any user
  who had previously saved them.

  P4 cuts the LLM-prompt path while preserving the DB rows (non-destructive
  — users can inspect / clean up themselves). A one-shot per-process
  deprecation log informs the user.

Run:
    python -m unittest tests.test_character_prompt_cleanup
"""
from __future__ import annotations

import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "core" / "memory" / "store.py"

import core.memory.store as store_mod
from core.memory.store import MemoryStore


class _StubStore:
    """Replace get_persona to return controlled values without DB hits."""
    def __init__(self, persona):
        self._p = persona


def _patch(store, persona):
    return mock.patch.object(store, "get_persona", return_value=persona)


# ─── 1. Source-level: style / custom 읽기 제거 ─────────────────────
class SourceLevelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = STORE.read_text(encoding="utf-8")

    def test_get_system_prompt_does_not_inject_style(self):
        # 함수 본문 슬라이스
        idx = self.src.index("def get_system_prompt")
        # 다음 def 까지
        nxt = self.src.index("\n    def ", idx + 1)
        body = self.src[idx:nxt]
        # 옛 패턴: lines.append(f"당신은 {style}입니다.") — 이 문장이 남아있으면
        # 자유텍스트가 LLM 으로 그대로 주입됨.
        self.assertNotIn("당신은 {style}", body,
            "P4: '당신은 {style}입니다' 라인이 남아 있으면 자유텍스트가 LLM 으로 주입됨")
        # 옛 패턴: lines.append(custom)
        self.assertNotRegex(
            body, r"lines\.append\(\s*custom\s*\)",
            msg="lines.append(custom) 라인이 남아 있으면 자유텍스트 주입 — P4가 무력화됨",
        )
        # 옛 변수 binding 도 사라져야 함 (deprecation 체크는 persona.get 직접 호출).
        self.assertNotRegex(
            body, r"^\s*style\s*=\s*persona\.get",
            msg="'style = persona.get(...)' binding 은 P4에서 제거되어야 함",
        )
        self.assertNotRegex(
            body, r"^\s*custom\s*=\s*persona\.get",
            msg="'custom = persona.get(...)' binding 은 P4에서 제거되어야 함",
        )

    def test_deprecation_log_sentinel_present(self):
        # 옛 row 가 있으면 1회 안내 — 개발자가 우연히 제거하지 않도록 sentinel.
        self.assertIn("_PERSONA_DEPRECATION_LOGGED", self.src,
            "deprecation 안내용 모듈 플래그가 있어야 함")

    def test_character_profile_directives_still_separate(self):
        """character_profile.get_prompt_modifiers 는 reasoning/engine.py 가
        직접 호출 — store.get_system_prompt 가 중복 호출하지 않아야 함
        (이중 주입 방지)."""
        idx = self.src.index("def get_system_prompt")
        nxt = self.src.index("\n    def ", idx + 1)
        body = self.src[idx:nxt]
        # 코드 영역만 — 문자열 docstring 종료(""")는 함수 본문 안에 두 번 나타남.
        # 첫 두 번째 """ 이후가 실제 코드.
        first_quote  = body.index('"""')
        second_quote = body.index('"""', first_quote + 3)
        code = body[second_quote + 3:]
        self.assertNotIn("get_prompt_modifiers", code,
            "store.get_system_prompt 코드 본문은 trait directives 를 직접 "
            "끼워넣지 않음 — engine.py 가 별도로 처리 (단일 진실 공급원)")


# ─── 2. Behavior: 결과 문자열에 style / custom 가 들어가지 않음 ──
class BehaviorTests(unittest.TestCase):
    def setUp(self):
        # 매 테스트마다 deprecation 플래그 리셋.
        store_mod._PERSONA_DEPRECATION_LOGGED["done"] = False

    def test_style_not_in_output_even_if_in_db(self):
        s = MemoryStore()
        with _patch(s, {"name": "James", "language": "Korean",
                        "style": "보안 중심의 AI",     # legacy 값
                        "custom": "항상 짧게"}):       # legacy 값
            out = s.get_system_prompt()
        self.assertNotIn("보안 중심의 AI", out,
            "legacy persona.style 은 LLM 프롬프트에 들어가면 안됨")
        self.assertNotIn("항상 짧게", out,
            "legacy persona.custom 은 LLM 프롬프트에 들어가면 안됨")
        self.assertIn("James", out,
            "name 은 여전히 프롬프트에 포함되어야 함")
        self.assertIn("Korean", out,
            "language 도 여전히 프롬프트에 포함")

    def test_default_name_when_missing(self):
        s = MemoryStore()
        with _patch(s, {}):
            out = s.get_system_prompt()
        self.assertIn("자메스", out,
            "name 미설정 시 기본값 '자메스' 사용")

    def test_deprecation_log_emitted_once(self):
        s = MemoryStore()
        legacy = {"name": "James", "language": "Korean", "style": "old style"}

        # 첫 호출: 로그 발생.
        buf1 = io.StringIO()
        with redirect_stdout(buf1), _patch(s, legacy):
            s.get_system_prompt()
        self.assertIn("(deprecated)", buf1.getvalue(),
            "legacy style/custom 가 있으면 deprecation 로그가 1회 발생")

        # 두 번째 호출: 같은 프로세스에서 다시 로그 X (per-process 1회).
        buf2 = io.StringIO()
        with redirect_stdout(buf2), _patch(s, legacy):
            s.get_system_prompt()
        self.assertNotIn("(deprecated)", buf2.getvalue(),
            "이미 안내했으므로 중복 로그 X")

    def test_no_deprecation_when_no_legacy_data(self):
        s = MemoryStore()
        clean = {"name": "James", "language": "Korean"}
        buf = io.StringIO()
        with redirect_stdout(buf), _patch(s, clean):
            s.get_system_prompt()
        self.assertNotIn("(deprecated)", buf.getvalue(),
            "legacy data 없을 때는 deprecation 로그 X")


# ─── 3. Engine integration unchanged (regression guard) ───────────
class EngineIntegrationTests(unittest.TestCase):
    """엔진은 store.get_system_prompt 와 character_profile.get_prompt_modifiers
    두 곳에서 prompt 조각을 받아 합친다. P4 가 store 쪽만 손대므로 engine
    경로 자체는 변하면 안됨.

    [chore 2026-05-19] After the #293 engine.py split (engine_memory.py
    + engine_synth.py), the two calls live inside engine_memory.
    These tests now grep the *concatenated* engine source via the
    shared helper, so a future split that moves them again still
    passes without rewriting the assertions.
    """

    def test_engine_still_calls_get_system_prompt(self):
        from tests._pipeline_src import engine_source
        src = engine_source()
        self.assertIn("get_system_prompt()", src,
            "engine 은 P4 후에도 store.get_system_prompt 를 계속 호출")

    def test_engine_still_calls_get_prompt_modifiers(self):
        from tests._pipeline_src import engine_source
        src = engine_source()
        self.assertIn("get_prompt_modifiers", src,
            "engine 은 P4 후에도 character_profile 에서 trait directives 를 받음 "
            "— 성격 표현은 trait 에서, 이름/언어는 store 에서, 라는 분리가 핵심")


# ─── 4. Persona endpoint 그대로 작동 (backward compat) ─────────────
class PersonaEndpointTests(unittest.TestCase):
    """프론트가 (drop-in) 빈 style/custom 으로 POST 해도 서버는 OK,
    그리고 GET 도 그대로 동작."""

    @unittest.skipIf(
        os.environ.get("CI") == "true",
        "skipped in CI — `from server_llmwiki import app` pulls the "
        "vector store + HuggingFace model into memory, which routinely "
        "exceeds the 30s pytest-timeout on cache-miss runners. Local "
        "runs cover this test; CI workflow already excludes other "
        "server-import tests via --ignore=. See "
        "docs/handovers/v0.3.0-platform-track.md `CI pytest 3 fail` note.",
    )
    def test_persona_endpoint_still_registered(self):
        try:
            from server_llmwiki import app
        except Exception as e:
            self.skipTest(f"server import failed: {e}")
        paths = {r.path for r in app.routes}
        self.assertIn("/admin/persona", paths,
            "GET/POST /admin/persona 는 backward compat 로 유지")


# ─── 5. Set/save 경로는 손대지 않음 (DB 보존) ─────────────────────
class DbPreservationTests(unittest.TestCase):
    """P4 의 핵심 안전 약속: 옛 persona.style / persona.custom row 를
    파괴적으로 삭제하지 않는다. 사용자가 직접 정리할 수 있도록 보존."""

    def test_set_persona_method_unchanged(self):
        # set_persona 가 여전히 임의의 key 를 받아 저장하는 단순 헬퍼인지.
        src = STORE.read_text(encoding="utf-8")
        self.assertIn("def set_persona", src)
        # 'style' / 'custom' 을 명시적으로 거부하는 가드가 *추가되지* 않았는지.
        # (만약 추가됐다면 쓰기 경로를 막는 셈 — backward compat 깨짐)
        idx = src.index("def set_persona")
        nxt = src.index("\n    def ", idx + 1)
        body = src[idx:nxt]
        self.assertNotIn('raise ValueError("style"', body)
        self.assertNotIn('"style" not allowed', body)


if __name__ == "__main__":
    unittest.main()
