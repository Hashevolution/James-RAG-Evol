"""R5 enforcement — model SDKs may only be imported from backend modules.

From ``docs/design/v0.3-llm-provider-contract.md`` §R5:

  The backend module is the only place in the JAMES codebase that
  imports the underlying model SDK. ``core/reasoning/``,
  ``core/retrieval/``, ``core/graph/``, ``core/policy_engine.py``,
  ``core/security_layer.py`` — none of these contain ``import openai``
  or ``import google.generativeai`` or equivalent.

This test parses every Python file under the middleware roots with
``ast`` and asserts that none of the forbidden SDK modules appears in
an ``Import`` or ``ImportFrom`` node. Two carve-outs apply:

  1. ``core/reasoning/backends/*.py`` — backend modules are the only
     place SDKs are allowed to live. The contract is that SDKs do not
     *leak upward* from there into the middleware.
  2. ``llm/`` — the existing pre-contract LLM router (``llm/router.py``
     and friends) is what ``ollama_local`` wraps. It is in the SDK
     allowlist but lives outside the middleware roots above, so the
     enforcement here doesn't reach it either way. Listing it
     explicitly in the docstring so a future reader doesn't wonder
     why it's exempt.

Adding a new SDK to the forbidden list is a one-line change in
``_FORBIDDEN_SDK_PREFIXES`` — keep that list narrow enough that the
test reads as policy, not a denylist of every Python package.
"""
from __future__ import annotations

import ast
import os
import sys
import unittest
from pathlib import Path
from typing import Iterable, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()


_ROOT = Path(__file__).resolve().parent.parent


# Module prefixes that count as a model-SDK import. Match by dotted
# prefix so a deeper namespace path (e.g. ``google.generativeai.types``)
# also fires. Keep this list narrow and policy-focused — the goal is
# to catch the obvious "I'm calling OpenAI directly from
# core/reasoning" pattern, not every Python package that happens to
# talk over HTTP.
_FORBIDDEN_SDK_PREFIXES: Tuple[str, ...] = (
    "openai",
    "anthropic",
    "google.generativeai",
    "google_generativeai",
    "cohere",
    "mistralai",
    "replicate",
    "together",
    "groq",
)


# Middleware roots — every .py under these is enforced.
_MIDDLEWARE_DIRS: Tuple[Path, ...] = (
    _ROOT / "core" / "reasoning",
    _ROOT / "core" / "retrieval",
    _ROOT / "core" / "graph",
)
_MIDDLEWARE_FILES: Tuple[Path, ...] = (
    _ROOT / "core" / "policy_engine.py",
    _ROOT / "core" / "security_layer.py",
)


# Carve-out: backend modules ARE allowed to import SDKs. They're the
# barrier the rest of the codebase relies on.
_BACKEND_DIR: Path = _ROOT / "core" / "reasoning" / "backends"


def _iter_middleware_files() -> Iterable[Path]:
    for d in _MIDDLEWARE_DIRS:
        if not d.exists():
            continue
        for f in d.rglob("*.py"):
            # Skip everything under the backends carve-out.
            try:
                f.relative_to(_BACKEND_DIR)
                continue   # under backends/, allowed
            except ValueError:
                pass
            yield f
    for f in _MIDDLEWARE_FILES:
        if f.exists():
            yield f


def _imported_modules(src: str) -> List[str]:
    """Return the dotted module names referenced by Import / ImportFrom
    nodes in ``src``. Ignores syntax errors (returns []).
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    names: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            # node.module is None for `from . import x`; relative
            # imports can't reach an external SDK so skip them.
            if node.module:
                names.append(node.module)
    return names


def _violations_in(path: Path) -> List[str]:
    """Return the forbidden module names imported by ``path``."""
    src = path.read_text(encoding="utf-8", errors="replace")
    imports = _imported_modules(src)
    bad: List[str] = []
    for mod in imports:
        for prefix in _FORBIDDEN_SDK_PREFIXES:
            if mod == prefix or mod.startswith(prefix + "."):
                bad.append(mod)
                break
    return bad


class NoSdkLeakageTests(unittest.TestCase):
    """Per-file architectural assertion. One subTest per middleware
    file so a violation reports the specific file rather than the
    aggregate count.
    """

    def test_middleware_does_not_import_sdks_directly(self):
        files = sorted(_iter_middleware_files())
        self.assertTrue(
            files,
            "no middleware files discovered — the test would silently "
            "pass on a misconfigured tree; check _MIDDLEWARE_DIRS",
        )
        for f in files:
            with self.subTest(file=f.relative_to(_ROOT).as_posix()):
                bad = _violations_in(f)
                self.assertFalse(
                    bad,
                    f"{f.relative_to(_ROOT).as_posix()} imports "
                    f"forbidden SDK module(s) {bad!r}. Per R5 of the "
                    f"Provider contract, model SDKs may only live in "
                    f"core/reasoning/backends/*.py — middleware code "
                    f"must reach the LLM through "
                    f"get_backend(name).complete(...) instead.",
                )

    def test_backend_carve_out_is_real(self):
        """Sanity check: the carve-out covers the existing backend
        files. If someone moves backends/ elsewhere, the test should
        flag that the allowlist drifted out of sync with the layout.
        """
        self.assertTrue(_BACKEND_DIR.exists(),
                        "core/reasoning/backends/ disappeared — R5 "
                        "enforcement would now treat backend SDK "
                        "imports as violations. Update _BACKEND_DIR.")
        # The existing reference backends should still live there.
        for name in ("ollama_local.py", "claude_code_cli.py"):
            self.assertTrue((_BACKEND_DIR / name).exists(),
                            f"reference backend {name} missing from "
                            f"{_BACKEND_DIR}")

    def test_forbidden_prefixes_are_nonempty(self):
        # Guard against an accidental edit that empties the list and
        # turns every enforcement subtest into a no-op.
        self.assertGreater(
            len(_FORBIDDEN_SDK_PREFIXES), 0,
            "_FORBIDDEN_SDK_PREFIXES emptied — R5 enforcement would "
            "be a no-op. At minimum keep openai / anthropic / "
            "google.generativeai.",
        )


class NoSdkLeakageHelpersTests(unittest.TestCase):
    """Self-test for the _imported_modules helper so a bug in the
    AST walk doesn't silently render the enforcement test a no-op.
    """

    def test_plain_import_matched(self):
        self.assertIn("openai", _imported_modules("import openai\n"))

    def test_dotted_import_matched(self):
        self.assertIn(
            "google.generativeai",
            _imported_modules("import google.generativeai as g\n"),
        )

    def test_from_import_matched(self):
        self.assertIn(
            "anthropic",
            _imported_modules("from anthropic import Anthropic\n"),
        )

    def test_relative_import_ignored(self):
        # Relative imports cannot reach an external SDK.
        self.assertEqual(_imported_modules("from . import x\n"), [])

    def test_string_literal_not_flagged(self):
        # "import openai" inside a string literal must not match.
        src = 'x = "import openai"\n'
        self.assertNotIn("openai", _imported_modules(src))

    def test_syntax_error_returns_empty_not_raise(self):
        self.assertEqual(_imported_modules("def broken(:\n"), [])


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
