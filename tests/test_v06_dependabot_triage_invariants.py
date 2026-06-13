"""v0.6 — Dependabot triage re-evaluation guardrails.

`docs/security/dependabot-2026-06-10-risk-assessment.md` accepts
three live Dependabot advisories as "not exploitable in this
deployment" because no JAMES call site exercises the vulnerable
surface. The risk-acceptance is conditional: §2 and §3 both name an
explicit **re-evaluation trigger** — if a future PR introduces a
call site that *would* reach the vulnerable surface, the dispositions
in the doc become stale and the PR must revisit the assessment.

That trigger only works if it's mechanical. A free-floating doc-side
rule depends on a reviewer remembering to look for the trigger; this
test makes the trigger fire automatically at PR time.

Three invariants, mapped to the doc sections that justify them:

  §2 chromadb (CVE-2026-45829):
      - no import of `chromadb.HttpClient` /
        `chromadb.AsyncHttpClient` (HTTP-server entry the CVE lives
        on)
      - no `trust_remote_code=True` call site (the payload-side
        condition the CVE requires)

  §3 torch (CVE-2025-3000):
      - no `torch.jit.script` / `torch.jit.load` / `torch.jit.trace`
        call site (the vulnerable JIT surface)

Scope: production Python sources under `core/`, `routes/`,
`scripts/`, `eval/`. Excluded: `tests/` (this file's docstring would
self-match), `docs/` (the assessment doc names the patterns as
"things we DON'T do"), `requirements*.txt` (comment blocks reference
the patterns in their rationale), and any `.md` file.

A future PR that legitimately needs one of these patterns must:
  1. Update `docs/security/dependabot-2026-06-10-risk-assessment.md`
     with the new exposure analysis.
  2. Add the file to the per-pattern allow-list below with a
     comment naming the assessment update.

Run:
  python -m unittest tests.test_v06_dependabot_triage_invariants
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


REPO_ROOT = Path(__file__).resolve().parent.parent

# Production source roots — where a vulnerable call site would
# actually expose the deployment. Adding a root here widens the
# guardrail (good); removing one narrows it (review carefully).
SOURCE_ROOTS = ("core", "routes", "scripts", "eval")

# Per-pattern allow-list. If a legitimate future use-case lands,
# add the file's repo-relative path here and reference the doc
# update in the comment. Empty by design — the triage doc claims
# zero call sites today.
_ALLOW_LIST: dict[str, frozenset[str]] = {
    "chromadb.HttpClient":           frozenset(),
    "chromadb.AsyncHttpClient":      frozenset(),
    "trust_remote_code":             frozenset(),
    "torch.jit.script":              frozenset(),
    "torch.jit.load":                frozenset(),
    "torch.jit.trace":               frozenset(),
}


def _iter_python_sources():
    """Yield every `*.py` file under the production source roots.

    Skips `__pycache__/` and any `.venv` / `venv` subtree by virtue
    of the production-root list — none of those live under the
    listed roots.
    """
    for root in SOURCE_ROOTS:
        root_path = REPO_ROOT / root
        if not root_path.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root_path):
            # Prune cache dirs in place — os.walk respects mutation.
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for name in filenames:
                if name.endswith(".py"):
                    yield Path(dirpath) / name


def _grep_pattern(pattern: str) -> list[tuple[str, int, str]]:
    """Return (relpath, lineno, line) for every match of `pattern`
    in any production Python source.

    Matching is **substring** — these are call-shape patterns
    (`module.func`), not full regex. Substring is sufficient because
    every pattern in `_ALLOW_LIST` is already a complete, distinctive
    attribute reference unlikely to collide with unrelated identifiers.
    """
    hits: list[tuple[str, int, str]] = []
    for path in _iter_python_sources():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            # Skip pure-comment lines — they're documenting, not calling.
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if pattern in line:
                rel = path.relative_to(REPO_ROOT).as_posix()
                hits.append((rel, lineno, line.rstrip()))
    return hits


class ChromaDbExposureGuardrailTests(unittest.TestCase):
    """§2 of the triage doc. CVE-2026-45829 (chromatoast) requires
    BOTH the HTTP server surface AND `trust_remote_code=True` in a
    user-controlled payload. Either appearing in JAMES sources means
    the disposition (`not exploitable`) is no longer accurate."""

    def _assert_zero_call_sites(self, pattern: str, section: str):
        hits = _grep_pattern(pattern)
        allowed = _ALLOW_LIST[pattern]
        unexpected = [h for h in hits if h[0] not in allowed]
        if unexpected:
            sample = "\n  ".join(
                f"{rel}:{lineno}: {line}"
                for rel, lineno, line in unexpected[:5]
            )
            self.fail(
                f"Dependabot triage {section} claims zero call sites "
                f"for `{pattern}`, but {len(unexpected)} found:\n  "
                f"{sample}\n\n"
                f"If this is intentional, update "
                f"`docs/security/dependabot-2026-06-10-risk-"
                f"assessment.md` {section} with the new exposure "
                f"analysis and add the file(s) to `_ALLOW_LIST` in "
                f"this test."
            )

    def test_no_http_client_import(self):
        self._assert_zero_call_sites("chromadb.HttpClient", "§2")

    def test_no_async_http_client_import(self):
        self._assert_zero_call_sites("chromadb.AsyncHttpClient", "§2")

    def test_no_trust_remote_code_call_site(self):
        self._assert_zero_call_sites("trust_remote_code", "§2")


class TorchJitExposureGuardrailTests(unittest.TestCase):
    """§3 of the triage doc. CVE-2025-3000 reaches the corruption
    via `torch.jit.script` (and the related JIT entry points). If
    any of these surface in JAMES sources, the disposition becomes
    stale."""

    def _assert_zero_call_sites(self, pattern: str):
        hits = _grep_pattern(pattern)
        allowed = _ALLOW_LIST[pattern]
        unexpected = [h for h in hits if h[0] not in allowed]
        if unexpected:
            sample = "\n  ".join(
                f"{rel}:{lineno}: {line}"
                for rel, lineno, line in unexpected[:5]
            )
            self.fail(
                f"Dependabot triage §3 claims zero call sites for "
                f"`{pattern}`, but {len(unexpected)} found:\n  "
                f"{sample}\n\n"
                f"If this is intentional, update "
                f"`docs/security/dependabot-2026-06-10-risk-"
                f"assessment.md` §3 with the new exposure analysis "
                f"and add the file(s) to `_ALLOW_LIST` in this test."
            )

    def test_no_jit_script_call_site(self):
        self._assert_zero_call_sites("torch.jit.script")

    def test_no_jit_load_call_site(self):
        self._assert_zero_call_sites("torch.jit.load")

    def test_no_jit_trace_call_site(self):
        self._assert_zero_call_sites("torch.jit.trace")


class TriageDocPresenceTests(unittest.TestCase):
    """Sanity — the triage doc the other tests reference must be on
    disk. Renaming it without updating the test would leave the
    guardrail in a broken-pointer state."""

    def test_triage_doc_exists(self):
        doc = REPO_ROOT / "docs" / "security" / "dependabot-2026-06-10-risk-assessment.md"
        self.assertTrue(
            doc.is_file(),
            f"Triage doc missing at {doc} — the guardrail's "
            f"per-section error messages point at a non-existent "
            f"file. Update both the doc path AND this test if the "
            f"doc was intentionally renamed.",
        )


if __name__ == "__main__":
    unittest.main()
