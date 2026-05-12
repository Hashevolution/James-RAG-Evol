"""[§4 #3, 2026-05-12] Reasoning panel — phase grouping (retrieve →
expand → verify).

Background: ``streamThinking`` in chat.js used to render every stage
event as a flat list of ``.thinking-line`` rows under the bubble. The
user could see *what* happened but not *which step of reasoning* it
was — gate vs lookup vs synthesis blurred together. This PR groups
the same lines into three phase containers:

    RETRIEVE  — auth / retrieve / rerank / risky_coding_blocked
    EXPAND    — graph / tool / coding_* router stages
    VERIFY    — answer / complete / coding_*_done / *_error

The contract:
  1. STAGE_META covers every stage the backend's ``log_stage`` call
     sites actually emit (no future-only entries are *required*, but
     every backend stage MUST be mapped — silent fallback hides bugs).
  2. Each STAGE_META entry has a ``phase`` field in {retrieve,
     expand, verify}.
  3. PHASE_META declares an ``order`` so phases render top-down in
     timeline order regardless of arrival sequence.
  4. The render path creates phase containers lazily (an empty phase
     is never inserted into the DOM) — chat.js's ``getOrCreatePhase``
     and the matching CSS classes are the load-bearing contract.

Run:
    python -m unittest tests.test_reasoning_phase_grouping
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
CHAT_JS = ROOT / "frontend" / "static" / "chat.js"
MOBILE_CSS = ROOT / "frontend" / "static" / "mobile.css"


def _stage_meta_block(js: str) -> str:
    """Slice out the STAGE_META object literal from chat.js so the
    tests only look at the meta block, not unrelated mentions."""
    start = js.index("const STAGE_META = {")
    # Match the closing brace+semicolon of the object literal.
    end = js.index("};", start)
    return js[start:end + 2]


def _phase_meta_block(js: str) -> str:
    start = js.index("const PHASE_META = {")
    end = js.index("};", start)
    return js[start:end + 2]


# Stages the backend actually emits — collected from grep on
# ``log_stage(...)`` call sites across ``core/`` and
# ``server_llmwiki.py`` (see commit message for the full list).
# Future-ready stages that STAGE_META carries (rerank, tool,
# risky_coding_blocked) are NOT required to live here — the tests
# assert every backend stage IS mapped, not that every mapped stage
# IS emitted today.
_BACKEND_EMITTED_STAGES = {
    "auth", "retrieve", "graph", "answer", "complete",
    "coding_route", "coding_llm_pick", "coding_llm_error",
    "coding_done", "coding_fallback_done", "coding_fallback_error",
    "coding_user_pick", "coding_user_pick_done", "coding_user_pick_error",
}


class StageMetaCoverageTests(unittest.TestCase):
    """STAGE_META must cover every backend-emitted stage, and every
    entry must carry a phase field."""

    @classmethod
    def setUpClass(cls):
        cls.js = CHAT_JS.read_text(encoding="utf-8")
        cls.block = _stage_meta_block(cls.js)

    def test_every_backend_stage_is_mapped(self):
        # Any unmapped backend stage falls through to the {icon:'·',
        # label: stage, color:'#888'} default and shows a bare stage
        # name with no phase routing — visible regression.
        for stage in sorted(_BACKEND_EMITTED_STAGES):
            with self.subTest(stage=stage):
                self.assertRegex(
                    self.block,
                    r"\b" + re.escape(stage) + r"\s*:",
                    f"backend stage {stage!r} must appear as a STAGE_META key",
                )

    def test_every_entry_has_a_phase(self):
        # Pull each `key: { ... }` entry and assert phase: 'X' is
        # present and in the allowed set.
        entries = re.findall(
            r"(\w+)\s*:\s*\{\s*([^}]+)\}", self.block,
        )
        self.assertGreater(len(entries), 5,
            "STAGE_META should have multiple entries; regex probably broke")
        for key, body in entries:
            with self.subTest(stage=key):
                m = re.search(r"phase\s*:\s*['\"](\w+)['\"]", body)
                self.assertIsNotNone(
                    m, f"STAGE_META[{key!r}] missing phase field")
                self.assertIn(
                    m.group(1), {"retrieve", "expand", "verify"},
                    f"STAGE_META[{key!r}].phase={m.group(1)!r} not in the "
                    f"allowed set",
                )


class PhaseMetaTests(unittest.TestCase):
    """PHASE_META declares the three timeline phases in display order."""

    @classmethod
    def setUpClass(cls):
        cls.js = CHAT_JS.read_text(encoding="utf-8")
        cls.block = _phase_meta_block(cls.js)

    def test_all_three_phases_declared(self):
        for phase in ("retrieve", "expand", "verify"):
            with self.subTest(phase=phase):
                self.assertRegex(
                    self.block,
                    r"\b" + phase + r"\s*:",
                    f"PHASE_META is missing the {phase!r} phase",
                )

    def test_phases_have_monotonic_order(self):
        # Order fields force the visual timeline regardless of which
        # phase arrives first (defensive against out-of-order events).
        orders = {}
        for phase in ("retrieve", "expand", "verify"):
            m = re.search(
                r"\b" + phase + r"\s*:\s*\{[^}]*order\s*:\s*(\d+)",
                self.block,
            )
            self.assertIsNotNone(m,
                f"PHASE_META[{phase!r}] must declare an order field")
            orders[phase] = int(m.group(1))
        self.assertLess(orders["retrieve"], orders["expand"],
            "retrieve must come before expand in the timeline")
        self.assertLess(orders["expand"], orders["verify"],
            "expand must come before verify in the timeline")


class CanonicalPhaseAssignmentTests(unittest.TestCase):
    """Every gate / lookup stage belongs to retrieve, every relation /
    tool / coding-router stage to expand, every answer / final to
    verify. Drift here changes the visible structure of the reasoning
    panel — explicit per-stage assertions catch it early."""

    @classmethod
    def setUpClass(cls):
        cls.js = CHAT_JS.read_text(encoding="utf-8")
        cls.block = _stage_meta_block(cls.js)

    def _phase_of(self, stage: str) -> str:
        m = re.search(
            r"\b" + re.escape(stage) + r"\s*:\s*\{[^}]*phase\s*:\s*['\"](\w+)['\"]",
            self.block,
        )
        self.assertIsNotNone(
            m, f"STAGE_META[{stage!r}] not found or missing phase")
        return m.group(1)

    def test_retrieve_phase_membership(self):
        for s in ("auth", "retrieve", "rerank", "risky_coding_blocked"):
            with self.subTest(stage=s):
                self.assertEqual(self._phase_of(s), "retrieve")

    def test_expand_phase_membership(self):
        for s in ("graph", "tool",
                  "coding_route", "coding_llm_pick", "coding_user_pick"):
            with self.subTest(stage=s):
                self.assertEqual(self._phase_of(s), "expand")

    def test_verify_phase_membership(self):
        for s in ("answer", "complete",
                  "coding_done", "coding_llm_error",
                  "coding_fallback_done", "coding_fallback_error",
                  "coding_user_pick_done", "coding_user_pick_error"):
            with self.subTest(stage=s):
                self.assertEqual(self._phase_of(s), "verify")


class RenderInfrastructureTests(unittest.TestCase):
    """chat.js must declare the helper functions + CSS hooks the
    phase grouping needs at runtime."""

    @classmethod
    def setUpClass(cls):
        cls.js = CHAT_JS.read_text(encoding="utf-8")
        cls.css = MOBILE_CSS.read_text(encoding="utf-8")

    def test_lazy_phase_helper_present(self):
        # getOrCreatePhase is what keeps empty phases out of the DOM
        # — without it, every answer would render three headers even
        # for a one-line trace.
        self.assertIn("getOrCreatePhase", self.js,
            "chat.js must declare the lazy phase factory helper")
        self.assertRegex(
            self.js,
            r"thinking-phase\[data-phase=",
            "phase containers must be addressable by data-phase",
        )

    def test_phase_state_helper_present(self):
        # refreshPhaseState transitions the header between active /
        # done states when its last running line closes.
        self.assertIn("refreshPhaseState", self.js)

    def test_phase_classes_render_into_dom(self):
        for cls in ("thinking-phase", "thinking-phase-header",
                    "thinking-phase-body", "thinking-phase-icon",
                    "thinking-phase-label",
                    "thinking-phase-active", "thinking-phase-done"):
            with self.subTest(css_class=cls):
                self.assertIn(cls, self.js,
                    f"chat.js must emit class {cls!r}")

    def test_phase_classes_styled_in_mobile_css(self):
        # The minimum visual contract — without these the timeline
        # collapses into the prior flat-list rendering with stray
        # data-* attrs hanging off the parent.
        for selector in (".thinking-phase", ".thinking-phase-header",
                         ".thinking-phase-body",
                         ".thinking-phase-active",
                         ".thinking-phase-done"):
            with self.subTest(selector=selector):
                self.assertIn(selector, self.css,
                    f"mobile.css must style {selector}")

    def test_phase_order_attribute_emitted(self):
        # data-order=1/2/3 is what the in-DOM sort uses to keep the
        # timeline visually monotonic even when phases arrive out of
        # order (rare, but the safety net is cheap).
        self.assertIn('data-order', self.js,
            "chat.js must stamp data-order on every phase container")


if __name__ == "__main__":
    unittest.main()
