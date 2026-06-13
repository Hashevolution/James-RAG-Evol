"""v0.6 Track C — CSP nonce graduation doc structural test.

Pins the canonical sections + the script-vs-style flag separation
+ the §3.1 pre-flight `grep <script>` instruction. A future PR that
deletes the per-flag warning OR merges the script flag with the
style flag would silently let an operator graduate `style-src`
before the UI #6 migration lands → hard UI break in production.
This test surfaces such a regression at PR time.

Run:
  python -m unittest tests.test_v06_csp_graduation_doc
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


REPO_ROOT = Path(__file__).resolve().parent.parent
DOC = REPO_ROOT / "docs" / "deployment" / "v0.6-csp-nonce-graduation.md"


class DocPresenceTests(unittest.TestCase):
    def test_doc_exists(self):
        self.assertTrue(DOC.is_file(),
                        "graduation doc removed — Track C follow-up "
                        "needs it to land safely")

    def setUp(self):
        self.body = DOC.read_text(encoding="utf-8")


class CanonicalSectionsTests(DocPresenceTests):
    """The doc must keep its operator-orienting structure."""

    def test_carries_canonical_sections(self):
        # Match `## N. ` at start of line (allow trailing title text).
        for n in (1, 2, 3, 4, 5, 6, 7, 8):
            with self.subTest(section=n):
                pattern = re.compile(rf"^## {n}\.", re.MULTILINE)
                self.assertTrue(
                    pattern.search(self.body),
                    f"missing section ## {n}.",
                )

    def test_tldr_table_lists_both_flags(self):
        # §1 must mention both env vars explicitly so an operator
        # scanning the TL;DR can't graduate the wrong one.
        self.assertIn("JAMES_CSP_USE_NONCE_SCRIPT", self.body)
        self.assertIn("JAMES_CSP_USE_NONCE_STYLE", self.body)


class FlagSeparationContractTests(DocPresenceTests):
    """The whole point of the split-flag design (PR #884) is that
    one flag is safe today + the other one breaks the UI. The doc
    MUST carry both halves of that contract verbatim — a future
    edit that drops the warning would invite a production break."""

    def test_script_flag_marked_safe_today(self):
        # Look for the canonical safety phrase OR an equivalent
        # ("safe today", "safely set", "safely TODAY", etc.).
        head = self.body.lower()
        safe_phrases = [
            "safe to set today",
            "safely set today",
            "safe to graduate today",
            "safely set",
            "안전하게 설정",
        ]
        self.assertTrue(
            any(p in head for p in safe_phrases),
            "doc must declare the script flag safe-today somewhere — "
            "otherwise operators won't graduate the one flag that's "
            "actually ready",
        )

    def test_style_flag_marked_breaks_ui(self):
        head = self.body.lower()
        break_phrases = [
            "break the ui",
            "breaks the ui",
            "hard-break",
            "hard break",
            "ui 전체 깨짐",
            "ui 깨짐",
            "깨짐",
        ]
        self.assertTrue(
            any(p in head for p in break_phrases),
            "doc must warn that the style flag breaks the UI today — "
            "otherwise an operator graduates it and takes prod down",
        )

    def test_csp3_section_referenced(self):
        # The mechanism reference matters: an operator who hits the
        # break wants to grep for "CSP3 §6.6.2.4" to understand why.
        self.assertIn("CSP3 §6.6.2.4", self.body,
                      "the §6.6.2.4 reference is the canonical "
                      "browser-side rule that explains the break")


class PreFlightCheckTests(DocPresenceTests):
    """§3.1 pre-flight verification — without it operators graduate
    without checking the baseline → script flag breaks pages that
    still ship an inline <script>."""

    def test_preflight_section_present(self):
        self.assertIn("3.1", self.body,
                      "the §3.1 pre-flight check section is required")

    def test_preflight_greps_for_inline_script(self):
        # Both Powershell + bash hints must include a literal `<script>`
        # target so an operator copy-pastes the right command.
        self.assertIn("<script>", self.body,
                      "the pre-flight grep target is the literal "
                      "`<script>` open tag")


class RollbackPathTests(DocPresenceTests):
    """A graduation doc without a rollback path is half a doc."""

    def test_rollback_section_present(self):
        self.assertTrue(
            re.search(r"^## 5\. Rollback", self.body, re.MULTILINE),
            "the §5 rollback section must exist — otherwise an "
            "operator who hits a regression has no documented escape",
        )

    def test_rollback_returns_to_unflagged_state(self):
        # The rollback section MUST describe unsetting the env var,
        # not "leave the flag and patch CSP" or similar.
        rollback_block = self.body.split("## 5.")[1].split("## 6.")[0]
        head = rollback_block.lower()
        self.assertTrue(
            any(p in head for p in (
                "unset", "empty string", 'environment=""', "환경 변수"
            )),
            "rollback should be unsetting the env var, not patching "
            "the directive",
        )


if __name__ == "__main__":
    unittest.main()
