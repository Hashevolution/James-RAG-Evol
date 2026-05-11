"""requirements.txt consistency guards.

Real user 2026-05-08 hit two install-time footguns:
  (a) GPU 'Unknown' because pynvml wasn't actually installed in the
      active venv (PR #88 chain — eventually they ran
      `pip install pynvml` manually).
  (b) docx export silently fell back to md because python-docx
      wasn't bundled (PR #93's documented fallback path).

Both deps WERE in the right place / mentioned, but a fresh-clone
operator had no clear signal. This file pins the consistency:

  - pynvml is in requirements.txt with a strong-recommendation
    comment (not "optional").
  - python-docx is in requirements.txt for the export feature.
  - The Ollama-pull comment block matches the current default
    models (gemma4:e4b, qwen2.5-coder:32b) — drift between
    config.py and the install instructions is exactly what
    triggered PR #96.

Run:
  python -m unittest tests.test_requirements_consistency
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
REQ_PATH = ROOT / "requirements.txt"


class RequirementsConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.txt = REQ_PATH.read_text(encoding="utf-8")
        cls.lines = cls.txt.splitlines()

    def _pkg_lines(self) -> list[str]:
        # Non-comment, non-blank lines.
        return [l.strip() for l in self.lines
                if l.strip() and not l.strip().startswith("#")]

    def test_pynvml_present_with_min_version(self):
        # Without pynvml, GPU detection silently degrades through
        # nvidia-smi / wmic fallbacks (and on Win11 24H2+ wmic is gone).
        line = next((l for l in self._pkg_lines() if l.startswith("pynvml")), "")
        self.assertTrue(line, "pynvml missing from requirements.txt")
        self.assertRegex(line, r"^pynvml\s*[><=].",
                         "pynvml must declare a version constraint")

    def test_pynvml_no_longer_marked_optional(self):
        # The comment that called it "optional" misled the user to skip
        # installing it. Now it should be marked recommended.
        # Find the line near pynvml and check the comment block above.
        idx = next(i for i, l in enumerate(self.lines) if l.startswith("pynvml"))
        # 5 lines before the pynvml line.
        comment_window = "\n".join(self.lines[max(0, idx - 5):idx])
        self.assertNotRegex(
            comment_window,
            r"#\s*pynvml\s*:\s*optional",
            "pynvml comment must NOT call it 'optional' — comment was the "
            "footgun that made the user skip the install",
        )

    def test_python_docx_present_for_export_feature(self):
        line = next((l for l in self._pkg_lines() if l.startswith("python-docx")), "")
        self.assertTrue(line,
                        "python-docx must be in requirements.txt — without it "
                        "the .docx export silently degrades to .md (PR #93)")
        self.assertRegex(line, r"^python-docx\s*[><=].")

    def test_ollama_pull_comment_uses_current_default(self):
        # The Ollama-pull instructions block must reference the
        # current config.GEMMA_MODEL default, not a stale value.
        # If they drift, a fresh install pulls the wrong model and
        # JAMES fails with "model not found" (the bug PR #96 fixed).
        import config
        default_llm = config.GEMMA_MODEL
        self.assertIn(
            f"ollama pull {default_llm}",
            self.txt,
            f"Ollama-pull comment must include `ollama pull {default_llm}` — "
            f"drift between config.GEMMA_MODEL and the install instructions "
            f"is the exact bug PR #96 fixed.",
        )

    def test_ollama_pull_comment_includes_coding_model(self):
        # Coding mode handler routes to qwen-coder by default —
        # users who want coding to actually work need the model.
        import config
        coding_llm = getattr(config, "CODING_MODEL", "qwen2.5-coder:32b")
        self.assertIn(
            f"ollama pull {coding_llm}",
            self.txt,
            f"Ollama-pull comment must include the coding model "
            f"`{coding_llm}` so coding mode works on a fresh setup",
        )

    def test_no_stale_gemma2_pull_instruction(self):
        # The pre-PR-#96 instruction said `ollama pull gemma2:2b`.
        # PR #96 changed config default to gemma4:e4b. The comment
        # must NOT still reference the stale gemma2:2b.
        # Allow it to be present elsewhere as historical context, but
        # not as an install instruction.
        # Simple check: if "gemma2:2b" appears as the FIRST `ollama pull`
        # instruction, that's stale.
        idx = self.txt.find("ollama pull")
        if idx >= 0:
            window = self.txt[idx:idx + 80]
            self.assertNotIn(
                "ollama pull gemma2:2b",
                window,
                "stale `ollama pull gemma2:2b` instruction — PR #96 "
                "moved the default to gemma4:e4b, install docs must follow",
            )

    def test_env_override_hint_present(self):
        # The fix for "wrong default model" is set JAMES_LLM_MODEL env.
        # Install doc should mention it so users know the override path.
        self.assertIn(
            "JAMES_LLM_MODEL",
            self.txt,
            "install instructions should mention JAMES_LLM_MODEL env "
            "for operators who want a different default",
        )


if __name__ == "__main__":
    unittest.main()
