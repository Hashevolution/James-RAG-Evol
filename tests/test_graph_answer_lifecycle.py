"""[item #4-2, 2026-05-09] Graph answer lifecycle UX.

User feedback (combined #4 graph-viz items + extension):
  c-label: 핵심 엔티티 이름 상시 표시
  e: Path 반짝임을 다음 질문까지 지속
  f: Path 지나가는 스팟들 이름 표시
  g: 답변 카드 펼치기/접기
  h: 답변 히스토리 리스트
  i: 히스토리 클릭 → path 애니메이션 재활성화
  j: 답변 모두 닫힘 → 기본 그래프 모드 reset

Decisions
  C-3: history 세션 휘발 (in-memory only, no localStorage)

Implementation (frontend/static/graph.js)
  State:
    activePathEdges  : Set    — replaces afterGlow's primary use (no expiry)
    activePathNodes  : Set    — for label visibility
    activeAnswerId   : id     — currently highlighted history entry
    labelSprites     : Map    — node id → THREE.Sprite
    answerHistory    : Array  — [{id, question, answer, paths, ts}]

  Functions:
    createTextSprite, disposeSprite, refreshLabels, tickLabelPositions
    activatePath, clearActivePath
    recordAnswer, renderAnswerCard, renderHistoryList
    onHistoryClick (i), toggleAnswerCard (g), closeAnswer (j)

Run:
    python -m unittest tests.test_graph_answer_lifecycle
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
JS  = ROOT / "frontend" / "static" / "graph.js"
HTML = ROOT / "frontend" / "graph.html"


class StateVarsTests(unittest.TestCase):
    """Required state containers exist."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_active_path_edges_set(self):
        self.assertRegex(self.js, r"activePathEdges\s*=\s*new Set\(\)")

    def test_active_path_nodes_set(self):
        self.assertRegex(self.js, r"activePathNodes\s*=\s*new Set\(\)")

    def test_active_answer_id(self):
        self.assertIn("activeAnswerId", self.js,
            "activeAnswerId tracks which history entry is currently lit")

    def test_label_sprites_map(self):
        self.assertRegex(self.js, r"labelSprites\s*=\s*new Map\(\)",
            "labelSprites maps node id → Three.Sprite for label rendering")

    def test_answer_history_array(self):
        self.assertRegex(self.js, r"answerHistory\s*=\s*\[\]",
            "answerHistory is in-memory only (decision C-3)")


class PathPersistenceTests(unittest.TestCase):
    """[#4-2 e/j] activatePath/clearActivePath replace 4.2s expiry."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_activate_path_function(self):
        self.assertIn("function activatePath", self.js)

    def test_clear_active_path_function(self):
        self.assertIn("function clearActivePath", self.js)

    def test_link_color_uses_active_path_edges(self):
        # linkColor must check activePathEdges (the persistent state),
        # not just afterGlow expiry.
        idx = self.js.index(".linkColor(function")
        body = self.js[idx:idx + 800]
        self.assertIn("activePathEdges.has", body,
            "linkColor must consult activePathEdges for persistent lit state")

    def test_link_width_uses_active_path_edges(self):
        idx = self.js.index(".linkWidth(function")
        body = self.js[idx:idx + 800]
        self.assertIn("activePathEdges.has", body,
            "linkWidth must also branch on activePathEdges")

    def test_ask_question_clears_path_first(self):
        # [#4-2 j] new question must reset before firing.
        idx = self.js.index("window.askQuestion")
        body = self.js[idx:idx + 1500]
        self.assertIn("clearActivePath()", body,
            "askQuestion must clearActivePath() before firing — old path "
            "must not bleed into new question's animation")

    def test_close_answer_clears_path(self):
        idx = self.js.index("window.closeAnswer")
        body = self.js[idx:idx + 600]
        self.assertIn("clearActivePath()", body,
            "closing the card must reset graph to default mode (j)")


class SpriteLabelsTests(unittest.TestCase):
    """[#4-2 c-label/f] Sprite-based always-visible name labels."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_create_text_sprite_helper(self):
        self.assertIn("function createTextSprite", self.js)

    def test_dispose_sprite_helper(self):
        # Disposes texture + material to avoid GPU memory leaks on
        # rapid history click (each click could swap sprite sets).
        self.assertIn("function disposeSprite", self.js)
        idx = self.js.index("function disposeSprite")
        body = self.js[idx:idx + 600]
        self.assertIn(".dispose()", body,
            "must dispose() the texture/material to avoid leaks")

    def test_refresh_labels_function(self):
        self.assertIn("function refreshLabels", self.js)
        idx = self.js.index("function refreshLabels")
        body = self.js[idx:idx + 1500]
        # Must consider both hubs and active path nodes.
        self.assertIn("hubIds", body)
        self.assertIn("activePathNodes", body)

    def test_tick_label_positions_in_animation_loop(self):
        # Labels follow node positions per frame.
        self.assertIn("function tickLabelPositions", self.js)
        idx = self.js.index("function pulseTick")
        body = self.js[idx:idx + 1500]
        self.assertIn("tickLabelPositions()", body,
            "pulseTick must call tickLabelPositions per frame")

    def test_buildindices_refreshes_labels(self):
        # When a fresh snapshot loads, hub set may change → labels follow.
        idx = self.js.index("function buildIndices")
        nxt = re.search(r"\n  function ", self.js[idx + 1:])
        end = idx + 1 + nxt.start() if nxt else idx + 1500
        body = self.js[idx:end]
        self.assertIn("refreshLabels()", body,
            "fresh snapshot must refresh labels (hubs may have changed)")


class AnswerCardUxTests(unittest.TestCase):
    """[#4-2 g/h/i] Answer card collapse, history, replay click."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")
        cls.html = HTML.read_text(encoding="utf-8")

    def test_record_answer_helper(self):
        self.assertIn("function recordAnswer", self.js,
            "every answer must funnel through recordAnswer to maintain history")

    def test_render_history_list_function(self):
        self.assertIn("function renderHistoryList", self.js)

    def test_history_click_handler(self):
        self.assertIn("function onHistoryClick", self.js)
        idx = self.js.index("function onHistoryClick")
        body = self.js[idx:idx + 600]
        self.assertIn("activatePath", body,
            "clicking a history entry must re-fire its path animation (i)")

    def test_toggle_answer_card_function(self):
        self.assertIn("window.toggleAnswerCard", self.js,
            "global function so the toggle button can call it inline")

    def test_collapse_class_toggled(self):
        idx = self.js.index("toggleAnswerCard")
        body = self.js[idx:idx + 600]
        self.assertIn("ac-collapsed", body,
            "collapse uses a CSS class on the card (.ac-collapsed)")

    def test_html_has_toggle_button(self):
        self.assertIn('id="ac-toggle"', self.html)
        self.assertIn('onclick="toggleAnswerCard()"', self.html)

    def test_html_has_history_container(self):
        self.assertIn('id="ac-history"', self.html,
            "card must contain the ac-history div for the list")

    def test_css_collapsed_state_hides_body(self):
        # .ac-collapsed must hide answer body sections.
        m = re.search(
            r"\.answer-card\.ac-collapsed[^{]*\{[^}]*display:\s*none",
            self.html, re.DOTALL,
        )
        # Try alternative pattern: multiple selectors comma-separated.
        if not m:
            m = re.search(
                r"\.answer-card\.ac-collapsed\s+\.ac-q[^{]*\{[^}]*display:\s*none",
                self.html, re.DOTALL,
            )
        self.assertIsNotNone(m,
            ".ac-collapsed must hide the answer body via display:none")


class HistoryItemRenderingTests(unittest.TestCase):
    """[#4-2 h] history list items must be sane + secure."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_history_uses_textcontent_not_innerhtml(self):
        # XSS guard — question text is user-input, must not be set via
        # innerHTML. The render function uses textContent.
        idx = self.js.index("function renderHistoryList")
        nxt = self.js.index("\n  function ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn("textContent", body)
        # No raw innerHTML assignment of the question text.
        self.assertNotRegex(body, r"row\.innerHTML\s*=\s*['\"`].*\$\{?e\.question",
            "must not interpolate raw question into innerHTML")


if __name__ == "__main__":
    unittest.main()
