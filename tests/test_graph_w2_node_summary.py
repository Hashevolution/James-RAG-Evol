"""[W2 2026-05-10] graph 페이지 — 질문창/자동질문 제거 + 노드 요약 패널.

User context: graph 페이지가 탐색 + 질문 답변 두 역할을 동시에 수행해서
복잡함. W2 에서 graph 페이지를 **순수 탐색기**로 단순화 — 질문은 /chat
페이지로 이관. 노드 클릭 시 자동 질문 chip 대신 엔티티 본문 발췌·메타
표시.

이 테스트는 4 가지를 검증:
  1. graph.html DOM 에서 query-bar / answer-card / suggested-questions /
     query-reasoning-overlay 모두 제거됨
  2. graph.js 에서 askQuestion / animatePaths / generateSuggestedQuestions
     등 질문-답변 함수 모두 제거됨
  3. 노드 요약 패널 (.np-summary*) CSS + render 헬퍼 추가됨
  4. /admin/entities/<id> 호출 패턴 존재

Run:
    python -m unittest tests.test_graph_w2_node_summary
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
HTML = ROOT / "frontend" / "graph.html"
CSS  = ROOT / "frontend" / "static" / "graph.css"
JS   = ROOT / "frontend" / "static" / "graph.js"


# [PR-#8b, 2026-05-13] graph.html's inline ``<style>`` block was
# extracted to static/graph.css. Tests that check for CSS-class
# definitions (.np-summary*, removed legacy .query-bar etc.) must
# now read the page + stylesheet combined — the regexes are source-
# agnostic so concatenating them keeps the contracts intact.
def _read_page_with_css() -> str:
    return HTML.read_text(encoding="utf-8") + "\n" + CSS.read_text(encoding="utf-8")


class HtmlRemovalsTests(unittest.TestCase):
    """graph.html — 질문 인프라 DOM 모두 제거."""

    @classmethod
    def setUpClass(cls):
        cls.src = _read_page_with_css()

    def test_no_query_bar_div(self):
        # 질문 입력창 자체가 사라져야.
        self.assertNotRegex(
            self.src, r'<div\s+class="query-bar"',
            "query-bar div 가 남아있음 — askQuestion 가능",
        )

    def test_no_qbox_input(self):
        self.assertNotRegex(self.src, r'id="qbox"',
                            "qbox 입력 필드가 남아있음")

    def test_no_ask_button(self):
        self.assertNotRegex(self.src, r'id="ask-btn"')
        self.assertNotIn("askQuestion()", self.src,
                         "Ask 버튼의 onclick 이 남아있음")

    def test_no_answer_card(self):
        self.assertNotRegex(self.src, r'id="answer-card"')
        for el_id in ("ac-q", "ac-a", "ac-paths", "ac-history", "ac-toggle"):
            self.assertNotRegex(
                self.src, rf'id="{el_id}"',
                f"answer-card 의 {el_id} 가 남아있음",
            )

    def test_no_suggested_questions_div(self):
        self.assertNotRegex(self.src, r'id="suggested-questions"')

    def test_no_query_reasoning_overlay(self):
        self.assertNotRegex(self.src, r'id="query-reasoning-overlay"')

    def test_no_orphan_query_css(self):
        # CSS 클래스 정의 자체가 남아 있으면 dead code — orphan 방지.
        for cls_name in (".query-bar", ".answer-card", ".suggested-questions",
                         ".sq-chip", ".query-reasoning-overlay",
                         ".qr-brain", ".qr-text", ".btn-ask"):
            self.assertNotRegex(
                self.src, re.escape(cls_name) + r"\s*\{",
                f"orphan CSS 정의: {cls_name}",
            )


class HtmlAdditionsTests(unittest.TestCase):
    """graph.html — 신규 .np-summary* CSS."""

    @classmethod
    def setUpClass(cls):
        cls.src = _read_page_with_css()

    def test_summary_css_classes_defined(self):
        for cls_name in (".np-summary", ".np-summary-meta",
                         ".np-summary-type", ".np-summary-sens",
                         ".np-summary-body"):
            self.assertRegex(
                self.src, re.escape(cls_name) + r"\s*\{",
                f"요약 패널 CSS 누락: {cls_name}",
            )

    def test_neighbor_panel_still_exists(self):
        # neighbor-panel 자체는 유지 (요약 패널의 host).
        self.assertRegex(self.src, r'id="neighbor-panel"')


class JsRemovalsTests(unittest.TestCase):
    """graph.js — 질문-답변 함수 모두 제거."""

    @classmethod
    def setUpClass(cls):
        cls.src = JS.read_text(encoding="utf-8")

    def test_no_askQuestion_window_export(self):
        # 함수 정의 자체 차단 (주석 안의 회고 언급은 허용).
        self.assertNotRegex(
            self.src,
            r"window\.askQuestion\s*=\s*async\s*function",
            "askQuestion 함수가 남아있음",
        )

    def test_no_recordAnswer_function(self):
        self.assertNotRegex(
            self.src, r"function\s+recordAnswer\s*\(",
        )

    def test_no_renderAnswerCard_function(self):
        self.assertNotRegex(
            self.src, r"function\s+renderAnswerCard\s*\(",
        )

    def test_no_renderHistoryList_function(self):
        self.assertNotRegex(
            self.src, r"function\s+renderHistoryList\s*\(",
        )

    def test_no_onHistoryClick_function(self):
        self.assertNotRegex(
            self.src, r"function\s+onHistoryClick\s*\(",
        )

    def test_no_toggleAnswerCard_function(self):
        self.assertNotRegex(
            self.src, r"window\.toggleAnswerCard\s*=",
        )

    def test_no_closeAnswer_function(self):
        self.assertNotRegex(
            self.src, r"window\.closeAnswer\s*=",
        )

    def test_no_activatePath_function(self):
        self.assertNotRegex(
            self.src, r"function\s+activatePath\s*\(",
        )

    def test_no_animatePaths_function(self):
        self.assertNotRegex(
            self.src, r"function\s+animatePaths\s*\(",
        )

    def test_no_parsePath_function(self):
        self.assertNotRegex(
            self.src, r"function\s+parsePath\s*\(",
        )

    def test_no_resolveHop_function(self):
        self.assertNotRegex(
            self.src, r"function\s+resolveHop\s*\(",
        )

    def test_no_suggested_question_helpers(self):
        for fn in ("generateSuggestedQuestions",
                   "renderSuggestedQuestions",
                   "clearSuggestedQuestions"):
            self.assertNotRegex(
                self.src, rf"function\s+{fn}\s*\(",
                f"{fn} 가 남아있음",
            )

    def test_no_korean_particle_helpers(self):
        # 자동 질문 생성용 helper. 다른 용도 없음.
        self.assertNotRegex(self.src, r"function\s+_hasJongseong\s*\(")
        self.assertNotRegex(self.src, r"function\s+_ko_p\s*\(")

    def test_no_reasoning_overlay_helpers(self):
        self.assertNotRegex(self.src, r"function\s+showReasoningOverlay\s*\(")
        self.assertNotRegex(self.src, r"function\s+hideReasoningOverlay\s*\(")

    def test_no_afterGlow_state(self):
        # afterGlow / GLOW_MS 는 path glow decay 인프라 — animatePaths 전용.
        self.assertNotRegex(self.src, r"var\s+afterGlow\s*=\s*new\s+Map")
        self.assertNotRegex(self.src, r"var\s+GLOW_MS\s*=")


class JsAdditionsTests(unittest.TestCase):
    """graph.js — 신규 노드 요약 패널 fetch + render."""

    @classmethod
    def setUpClass(cls):
        cls.src = JS.read_text(encoding="utf-8")

    def test_fetch_helper_defined(self):
        self.assertRegex(
            self.src,
            r"function\s+fetchAndRenderEntitySummary\s*\(",
            "fetchAndRenderEntitySummary 헬퍼 누락",
        )

    def test_render_helper_defined(self):
        self.assertRegex(
            self.src,
            r"function\s+renderEntitySummary\s*\(",
        )

    def test_render_placeholder_helper(self):
        # 로딩 상태 표시 (UI race 방지) 도 별도 헬퍼.
        self.assertRegex(
            self.src,
            r"function\s+renderEntitySummaryPlaceholder\s*\(",
        )

    def test_fetch_targets_admin_entities_endpoint(self):
        # /admin/entities/<id> 호출 패턴이 있어야.
        self.assertIn("/admin/entities/", self.src,
                      "/admin/entities/ 호출 패턴이 없음")

    def test_fetch_called_from_explore(self):
        # exploreFromNode 함수 본문 안에서 fetchAndRenderEntitySummary 가
        # 호출되는지 확인. exploreFromNode 시작 지점 → 다음 최상위 함수
        # 정의 (또는 파일 끝) 까지의 윈도우 안에 호출이 있어야 함. 중첩
        # 콜백 (forEach) 의 } 가 단순 [^}] 정규식을 깨므로 윈도우 방식.
        m_start = re.search(r"function\s+exploreFromNode\s*\(", self.src)
        self.assertIsNotNone(m_start, "exploreFromNode 정의가 없음")
        body_start = m_start.end()
        # 다음 최상위 function 정의로 끝 잡기 (선두 2-space 들여쓰기 가정).
        m_next = re.search(
            r"\n  (?:window\.|function )", self.src[body_start:],
        )
        end = body_start + m_next.start() if m_next else len(self.src)
        body = self.src[body_start:end]
        self.assertIn(
            "fetchAndRenderEntitySummary", body,
            "exploreFromNode 가 fetchAndRenderEntitySummary 를 호출하지 않음",
        )

    def test_request_seq_for_race_protection(self):
        # 동시에 여러 노드 클릭 시 마지막 요청만 반영하는 sequence 가드.
        self.assertIn("_summaryReqSeq", self.src,
                      "race 가드 sequence 변수 누락")


class IntegrationTests(unittest.TestCase):
    """W2 핵심 효과 — 질문 인프라가 통째로 사라졌고 신규 패널이 들어왔다."""

    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")
        cls.js   = JS.read_text(encoding="utf-8")

    def test_graph_page_no_longer_calls_query_endpoint(self):
        # /query/ POST 가 graph.js 에 더 이상 없음 (chat.js 만 사용).
        self.assertNotIn("'/query/'", self.js)
        self.assertNotIn('"/query/"', self.js)

    def test_explore_panel_still_works(self):
        # neighbor 클릭 → 재귀 explore 는 그대로 (UX 핵심).
        self.assertIn("onNeighborClick", self.js)
        self.assertIn("exploreFromNode", self.js)

    def test_summary_panel_visible_in_html(self):
        # neighbor-panel 안에 .np-summary 가 들어갈 자리는 JS 가 생성하므로
        # HTML 자체엔 직접 마크업 X — neighbor-panel div 만 존재해야.
        self.assertIn('id="neighbor-panel"', self.html)


if __name__ == "__main__":
    unittest.main()
