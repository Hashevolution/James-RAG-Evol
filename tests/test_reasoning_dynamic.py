"""[item #3, 2026-05-09] Reasoning UI must be stage-driven, not timer-driven.

History:
  PR #97 (#A6-7): real reasoning stream — replaced the fake 2.5s timer
    with /trace/poll/{trace_id} polling. Stage events drive a per-line
    display (auth → retrieve → graph → answer → complete).
  PR #126 (#A8-1): added a 1.6s timer-based rotation of 8 placeholder
    phrases for the gap BEFORE first stage event arrives. Felt
    dynamic but was actually decoupled from server progress.
  Item #3 (this PR): user fed back that the rotation was "formal
    sequential repetition" — disconnected from actual JAMES reasoning
    progress. Removed in favor of a single static placeholder; real
    STAGE_META lines now drive everything once the first event arrives.

This file is the regression guard for that removal:
  - NO timer-based rotation
  - NO THINKING_PLACEHOLDER_PHRASES array
  - placeholder text is static
  - shimmer / brain animation speeds preserved (visual continuity)

The shimmer/neuron speed assertions from the original test are kept
because the user wanted "dynamic visual feel" via shimmer/neuron pulse
speed (PR #126), not via phrase rotation.

Run:
    python -m unittest tests.test_reasoning_dynamic
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
JS  = ROOT / "frontend" / "static" / "chat.js"
CSS = ROOT / "frontend" / "static" / "mobile.css"


class ShimmerSpeedTests(unittest.TestCase):
    """[#A8-1] visual dynamism via shimmer/neuron speed — kept."""

    @classmethod
    def setUpClass(cls):
        cls.css = CSS.read_text(encoding="utf-8")

    def test_shimmer_animation_faster(self):
        for m in re.finditer(r"animation:\s*james-shimmer\s+([\d.]+)s", self.css):
            duration = float(m.group(1))
            self.assertLessEqual(duration, 1.5,
                f"james-shimmer {duration}s must be ≤1.5s")

    def test_neuron_blink_faster(self):
        for m in re.finditer(
            r"\.brain-pulse-active\s+\.neuron-\d.+?(\d+\.?\d*)s",
            self.css, re.DOTALL,
        ):
            duration = float(m.group(1))
            self.assertLessEqual(duration, 1.0,
                f"neuron-N {duration}s must be ≤1.0s")


class StaticPlaceholderTests(unittest.TestCase):
    """[item #3] No timer rotation; placeholder is a single static phrase."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def _appendTyping_body(self) -> str:
        idx = self.js.index("function appendTyping")
        # appendTyping is followed by other functions; bound at next
        # top-level `function`/`async function`/`/* `.
        nxt = re.search(
            r"\n(?:function |async function |/\* )",
            self.js[idx + 1:],
        )
        end = idx + 1 + nxt.start() if nxt else len(self.js)
        return self.js[idx:end]

    def test_no_phrases_array(self):
        self.assertNotIn("THINKING_PLACEHOLDER_PHRASES", self.js,
            "THINKING_PLACEHOLDER_PHRASES must be removed — placeholder "
            "is now a single static phrase, no rotation array")

    def test_no_timer_rotation_in_appendTyping(self):
        body = self._appendTyping_body()
        self.assertNotIn("rotateTimer", body,
            "rotateTimer (1.6s setInterval) was the formal sequential "
            "repetition the user objected to — must not exist")
        # Also no setInterval() in appendTyping at all (no other timers
        # belong here).
        self.assertNotRegex(body, r"\bsetInterval\s*\(",
            "appendTyping must not start any timer — display is purely "
            "stage-event-driven via the existing /trace/poll polling")

    def test_placeholder_static_text_present(self):
        body = self._appendTyping_body()
        # The placeholder text exists as a single literal in the
        # initial innerHTML — no JS-side mutation of textContent on a
        # rotating cycle.
        self.assertRegex(body, r'thinking-placeholder-text[^>]*>[^<]+<',
            "placeholder span must contain a single static phrase")
        # And nothing should be reassigning .textContent on the
        # placeholder span (which the rotation timer used to do).
        self.assertNotIn("placeholderEl.textContent", body,
            "no runtime rewrites of placeholder text — static phrase only")

    def test_placeholder_class_preserved(self):
        # Other code paths grep on this class to remove the placeholder
        # when first stage arrives.
        body = self._appendTyping_body()
        self.assertIn("thinking-placeholder", body)
        self.assertIn("thinking-placeholder-text", body)


class StageEventDrivenDisplayTests(unittest.TestCase):
    """The real progress-driven mechanism (already exists since PR #97)
    must remain wired. After this PR, it's the SOLE driver of the UI."""

    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_apply_removes_placeholder_on_first_event(self):
        # Sanity: the apply() path that handles stage events still
        # removes the static placeholder on first event arrival.
        idx = self.js.index("첫 진짜 stage event 도착 시 정적 placeholder 제거")
        body = self.js[idx:idx + 400]
        self.assertIn(".thinking-placeholder", body)
        self.assertIn("ph.remove()", body)

    def test_trace_poll_endpoint_used(self):
        # Server-side stage events come from /trace/poll/{trace_id}.
        self.assertIn("/trace/poll/", self.js,
            "client must poll /trace/poll/{trace_id} for real stages")

    def test_stage_meta_table_present(self):
        # Per-stage label/icon/color mapping must remain — drives the
        # per-line display after first event.
        self.assertIn("STAGE_META", self.js)
        # A handful of expected stages.
        for stage in ("auth", "retrieve", "graph", "answer", "complete"):
            self.assertIn(f"{stage}:", self.js,
                f"STAGE_META should map stage '{stage}'")

    def test_complete_event_marks_active_done(self):
        # When the final 'complete' event arrives, the active stage line
        # must transition to a finished state — this is the natural
        # sync point with answer wrap-up the user described.
        self.assertIn("markActiveAsDone", self.js)
        idx = self.js.index("if (data.complete)")
        body = self.js[idx:idx + 400]
        self.assertIn("markActiveAsDone()", body,
            "completion must mark the active line done — synchronizes "
            "the UI animation with the actual answer wrap-up moment")


if __name__ == "__main__":
    unittest.main()
