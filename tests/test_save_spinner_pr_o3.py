"""장기기억 저장 chip — 진행 spinner + ✓/✗ 전환 (PR-O3, 사이클 12).

User feedback (2026-05-14):

  > 챗에서 장기 기억 저장 클릭 후 응답까지 spinner / 진행 표시 없어서
  > 사용자가 처리 중인지 모름.

Fix (handovers/v0.3-operational-ux-track.md §4 PR-O3):
  - chat.css 에 .chip-spinner (mint 회전 링) + @keyframes chip-spin +
    .chip-result-ok (✓ mint) + .chip-result-fail (✗ red) 정의
  - approveWikiSave 가 클릭 시 chip 의 첫 <span> (📥 아이콘) 자리를
    spinner 로 in-place 교체 → 응답 도착 시 ✓/✗ 로 전환
  - 실패 시 일정 시간 후 원래 아이콘으로 복원해 재클릭 가능

Out of scope:
  - 웹 검색 자체 진행률 표시 (별 PR — 사이클 12 §4 명시)
  - 다른 chip 들의 spinner 화 (위키 저장 chip 만)

Run:
  python -m unittest tests.test_save_spinner_pr_o3
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
JS   = ROOT / "frontend" / "static" / "chat.js"
CSS  = ROOT / "frontend" / "static" / "chat.css"


class SpinnerCssTests(unittest.TestCase):
    """chat.css 에 spinner / 결과 표시 CSS 가 정의되어 있는지."""

    @classmethod
    def setUpClass(cls):
        cls.src = CSS.read_text(encoding="utf-8")

    def test_spinner_class_defined(self):
        self.assertRegex(
            self.src, r"\.chip-spinner\s*\{",
            ".chip-spinner CSS 클래스가 정의되지 않음",
        )

    def test_spinner_uses_accent_mint(self):
        # spinner 의 회전 색이 --accent (mint) 토큰을 사용해야 함.
        # 정의 블록 안에 'var(--accent)' 가 있어야.
        idx = self.src.index(".chip-spinner")
        block = self.src[idx:idx + 500]
        self.assertIn("var(--accent)", block,
            "spinner 가 mint --accent 토큰을 사용하지 않음")

    def test_spinner_animation_keyframes(self):
        self.assertRegex(
            self.src, r"@keyframes\s+chip-spin\s*\{",
            "@keyframes chip-spin 정의 누락",
        )
        idx = self.src.index(".chip-spinner")
        block = self.src[idx:idx + 500]
        self.assertIn("animation: chip-spin", block,
            "spinner 가 chip-spin 애니메이션을 적용하지 않음")

    def test_result_ok_class_defined(self):
        self.assertRegex(
            self.src, r"\.chip-result-ok\s*\{",
            ".chip-result-ok CSS 누락",
        )

    def test_result_fail_class_defined(self):
        self.assertRegex(
            self.src, r"\.chip-result-fail\s*\{",
            ".chip-result-fail CSS 누락",
        )


class ApproveWikiSaveSpinnerTests(unittest.TestCase):
    """approveWikiSave 가 spinner / 결과 클래스를 사용하는지."""

    @classmethod
    def setUpClass(cls):
        cls.src = JS.read_text(encoding="utf-8")

    def _approveWikiSave_body(self) -> str:
        idx = self.src.index("async function approveWikiSave")
        end = self.src.index("\nfunction ", idx + 1)
        return self.src[idx:end]

    def test_inserts_chip_spinner_on_click(self):
        body = self._approveWikiSave_body()
        self.assertIn("chip-spinner", body,
            "approveWikiSave 가 chip-spinner 를 삽입하지 않음")
        # 아이콘 span (첫 자식) 자리를 spinner 로 outerHTML 교체.
        self.assertIn("span:first-child", body,
            "spinner 가 chip 의 첫 <span> 자리에 in-place 삽입되지 않음")

    def test_swap_to_check_on_success(self):
        body = self._approveWikiSave_body()
        self.assertIn("chip-result-ok", body,
            "성공 시 ✓ 결과 클래스로 전환하지 않음")
        self.assertIn("✓", body,
            "성공 시 체크마크 글리프 누락")

    def test_swap_to_cross_on_error(self):
        body = self._approveWikiSave_body()
        self.assertIn("chip-result-fail", body,
            "실패 시 ✗ 결과 클래스로 전환하지 않음")
        self.assertIn("✗", body,
            "실패 시 ✗ 글리프 누락")

    def test_error_path_restores_chip_for_retry(self):
        # 실패 시 chip 을 다시 클릭 가능 상태로 (btn.disabled = false +
        # 원래 아이콘 복원). 사용자가 즉시 재시도 가능해야.
        body = self._approveWikiSave_body()
        self.assertIn("btn.disabled = false", body,
            "실패 시 chip 재활성화 누락")
        # ✗ 가 잠시 보이고 원래 아이콘으로 복원되는지 — setTimeout 호출.
        self.assertIn("setTimeout", body,
            "실패 후 일정 시간 뒤 원래 아이콘으로 복원하는 setTimeout 누락")
        # origIconHTML 변수가 복원에 쓰이는지.
        self.assertIn("origIconHTML", body,
            "복원용 origIconHTML 변수가 정의되지 않음")

    def test_aria_hidden_on_decorative_glyphs(self):
        # spinner / ✓ / ✗ 는 모두 시각적 cue. label span 에 텍스트 상태가
        # 있으므로 스크린리더에는 노출 안 되도록 aria-hidden="true".
        body = self._approveWikiSave_body()
        self.assertIn('aria-hidden="true"', body,
            "spinner/결과 글리프에 aria-hidden 누락 (스크린리더 중복 발화 방지)")


class N6RegressionTests(unittest.TestCase):
    """N-6 의 jamesConfirm 통합이 PR-O3 변경에 살아남았는지."""

    @classmethod
    def setUpClass(cls):
        cls.src = JS.read_text(encoding="utf-8")

    def test_jamesConfirm_still_called(self):
        # PR-O3 가 N-6 의 confirm 흐름을 깨지 않아야.
        self.assertIn("await jamesConfirm(", self.src,
            "N-6 jamesConfirm 호출이 사라짐 — PR-O3 가 회귀 일으킴")

    def test_confirm_gate_still_first(self):
        # if (!ok) return; 이 spinner 삽입 전에 있어야 (취소한 사용자에게
        # spinner 잠깐 보이는 false-positive 차단).
        idx = self.src.index("async function approveWikiSave")
        end = self.src.index("\nfunction ", idx + 1)
        body = self.src[idx:end]
        gate_pos    = body.find("if (!ok) return;")
        spinner_pos = body.find("chip-spinner")
        self.assertGreater(gate_pos, 0, "취소 게이트가 없음")
        self.assertGreater(spinner_pos, 0, "spinner 삽입이 없음")
        self.assertLess(gate_pos, spinner_pos,
            "spinner 삽입이 취소 게이트보다 먼저 일어남 — 취소한 사용자도 "
            "spinner 잠깐 보이는 false-positive 위험")


if __name__ == "__main__":
    unittest.main()
