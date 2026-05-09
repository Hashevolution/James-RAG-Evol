"""[PR suggested-q, 2026-05-09] Auto-suggested questions on node click.

User feedback:
> "추론 그래프에서 노드 선택시 연결된 노드들과의 연관된 질문을 형성해서
>  사용자에게 이 질문에 대한 분석이나 답변을 원하는지 3가지 정도 자동
>  생성해서 질문란 쪽에 함께 제시하는 방식을 검토"

Pure client-side template generation:
  - generateSuggestedQuestions(node, neighbors) — 3 questions max
    Q1: about the node itself (entity-type aware: person / org /
        document / concept)
    Q2: relationship with the highest-weight neighbor
    Q3: comparison/summary across top 2 neighbors (or single-neighbor
        fallback)
  - Korean particle helpers (_hasJongseong, _ko_p) so 은/는, 이/가,
    과/와, 을/를 are picked correctly per entity name.
  - renderSuggestedQuestions(qs) → chip strip above query bar
  - clearSuggestedQuestions() — on submit / panel close

Run:
    python -m unittest tests.test_graph_suggested_questions
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "frontend" / "static" / "graph.js"
HTML = ROOT / "frontend" / "graph.html"


class GeneratorContractTests(unittest.TestCase):
    """Source-level: generateSuggestedQuestions has the right shape."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_generator_function_defined(self):
        self.assertIn("function generateSuggestedQuestions", self.js)

    def test_returns_at_most_3_questions(self):
        idx = self.js.index("function generateSuggestedQuestions")
        nxt = self.js.index("\n  function ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn(".slice(0, 3)", body,
            "generator must cap output at 3 questions")

    def test_handles_each_entity_type(self):
        idx = self.js.index("function generateSuggestedQuestions")
        nxt = self.js.index("\n  function ", idx + 1)
        body = self.js[idx:nxt]
        # Branches for person / org / document / fallback (concept etc.)
        for type_kw in ("person", "org", "document"):
            self.assertIn("'" + type_kw + "'", body,
                f"generator must branch on entity type '{type_kw}' "
                "for natural-sounding questions")

    def test_uses_top_neighbor_by_weight(self):
        idx = self.js.index("function generateSuggestedQuestions")
        nxt = self.js.index("\n  function ", idx + 1)
        body = self.js[idx:nxt]
        # Top neighbor selected by edge weight, not array order.
        self.assertIn("edge", body)
        self.assertIn("weight", body)
        self.assertIn(".sort", body,
            "neighbors must be sorted by edge weight before picking the "
            "top one for the relationship question")


class KoreanParticleHelperTests(unittest.TestCase):
    """_hasJongseong / _ko_p must handle Korean syllables + English fallback."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_has_jongseong_function(self):
        self.assertIn("function _hasJongseong", self.js)

    def test_ko_particle_function(self):
        self.assertIn("function _ko_p", self.js)

    def test_jongseong_uses_hangul_unicode_block(self):
        idx = self.js.index("function _hasJongseong")
        nxt = self.js.index("\n  function ", idx + 1)
        body = self.js[idx:nxt]
        # The Korean precomposed-syllable Unicode block: U+AC00..U+D7A3.
        # Modulo 28 gives the 종성(jongseong) index — 0 means no batchim.
        self.assertIn("0xAC00", body)
        self.assertIn("0xD7A3", body)
        self.assertIn("28", body,
            "must use the (code - 0xAC00) % 28 trick to detect 종성")

    def test_english_fallback_present(self):
        idx = self.js.index("function _hasJongseong")
        nxt = self.js.index("\n  function ", idx + 1)
        body = self.js[idx:nxt]
        # English consonant ending → treat as 받침; vowel ending → no.
        self.assertIn("[a-z]", body,
            "must have an English fallback heuristic for non-Korean names")

    def test_generator_uses_particle_helper(self):
        idx = self.js.index("function generateSuggestedQuestions")
        nxt = self.js.index("\n  function ", idx + 1)
        body = self.js[idx:nxt]
        # Must call _ko_p with Korean particle pairs.
        self.assertIn("_ko_p(", body)
        self.assertIn("'은'", body)
        self.assertIn("'는'", body)
        self.assertIn("'과'", body)
        self.assertIn("'와'", body)


class RendererTests(unittest.TestCase):
    """renderSuggestedQuestions / clearSuggestedQuestions DOM contract."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")
        cls.html = HTML.read_text(encoding="utf-8")

    def test_render_function_defined(self):
        self.assertIn("function renderSuggestedQuestions", self.js)

    def test_clear_function_defined(self):
        self.assertIn("function clearSuggestedQuestions", self.js)

    def test_renders_into_correct_container(self):
        idx = self.js.index("function renderSuggestedQuestions")
        nxt = self.js.index("\n  function ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn("'suggested-questions'", body,
            "must target the #suggested-questions container")

    def test_chips_use_data_attr_and_listener(self):
        # Same pattern as PR #157's click-handler fix — never use
        # inline onclick with raw-id interpolation.
        idx = self.js.index("function renderSuggestedQuestions")
        nxt = self.js.index("\n  function ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn("data-sq-question", body,
            "chips must carry data-sq-question, not inline onclick")
        self.assertIn("addEventListener('click'", body,
            "click handler must be programmatic — matches PR #157 pattern")

    def test_chip_click_triggers_askQuestion(self):
        idx = self.js.index("function renderSuggestedQuestions")
        nxt = self.js.index("\n  function ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn("window.askQuestion", body,
            "chip click must populate qbox + invoke askQuestion to fire "
            "the query immediately")

    def test_chip_text_uses_escapeHtml(self):
        # Question strings come from concatenated user-data-controlled
        # entity names — escape on the way to innerHTML.
        idx = self.js.index("function renderSuggestedQuestions")
        nxt = self.js.index("\n  function ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn("escapeHtml", body)

    def test_html_container_present(self):
        self.assertIn('id="suggested-questions"', self.html)

    def test_initial_display_none(self):
        # CSS rule must default to display:none — JS toggles to flex.
        self.assertRegex(
            self.html,
            r"\.suggested-questions[^{]*\{[^}]*display:\s*none",
            re.DOTALL,
        )


class IntegrationTests(unittest.TestCase):
    """Integration with explore + askQuestion + close handlers."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_exploreFromNode_renders_suggestions(self):
        idx = self.js.index("function exploreFromNode")
        body = self.js[idx:idx + 3000]
        self.assertIn("renderSuggestedQuestions", body,
            "exploreFromNode must populate the chip strip alongside "
            "the neighbor panel")

    def test_askQuestion_clears_chips(self):
        # Anchor on the actual function definition (other places call
        # window.askQuestion now too).
        idx = self.js.index("window.askQuestion = async function")
        nxt = self.js.index("\n  function ", idx + 1)
        body = self.js[idx:nxt]
        self.assertIn("clearSuggestedQuestions()", body,
            "submitting a question must hide the chips so they don't "
            "linger past the query they relate to")

    def test_closeNeighborPanel_clears_chips(self):
        idx = self.js.index("window.closeNeighborPanel")
        body = self.js[idx:idx + 600]
        self.assertIn("clearSuggestedQuestions", body,
            "closing the neighbor panel must also clear the chips — "
            "they're tied to the active node")


class MobileResponsiveTests(unittest.TestCase):
    """Phone breakpoint tweaks the chip strip."""

    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")

    def test_phone_breakpoint_adjusts_chips(self):
        # 720px @media block must reference .suggested-questions or
        # .sq-chip so the chips are sized for thumb taps.
        idx = self.html.index("@media (max-width: 720px)")
        end = self.html.index("@media (max-width: 480px)", idx)
        block = self.html[idx:end]
        self.assertTrue(
            ".suggested-questions" in block or ".sq-chip" in block,
            "phone media block must adjust chip strip sizing/positioning",
        )


if __name__ == "__main__":
    unittest.main()
