"""v0.6.1 — CLAUDE.md rule #5 module-size invariant test.

Rule #5: no file in ``core/`` exceeds 20 KB (20,480 bytes,
LF-normalized).

This test is the safety net behind the seven split refactors that
landed in PR #900-#908 (v0.5 cycle close addendum) — without it, a
future PR can push a single file back over 20 KB and reviewers
have to catch it by hand at PR time.

Two protections:

1. **Forward-only enforcement** — every ``core/**/*.py`` file MUST
   stay under the 20 KB ceiling, EXCEPT for an explicit grandfather
   list of files that were already over-cap when this test landed.
   The grandfather list documents the split-debt TODO so future-self
   doesn't lose sight of it.

2. **Anti-grandfather creep** — every grandfathered file must STILL
   be over the ceiling for the entry to remain valid. If a file falls
   back under the ceiling (good — somebody split it), the entry MUST
   be removed in the same PR. This stops the list growing silently
   or holding stale entries that mask a real regression.

Run: ``python -m unittest tests.test_v06_module_size_gate``
"""
from __future__ import annotations

import os
import unittest
from pathlib import Path


CAP_BYTES = 20 * 1024  # 20 KB = 20,480 bytes per CLAUDE.md rule #5
CORE_DIR = Path(__file__).resolve().parent.parent / "core"


# ─── Grandfather list ──────────────────────────────────────────────
# Files in ``core/`` that were already over the 20 KB cap when this
# test landed (2026-06-20). Each entry is split-debt: a future PR
# should split the file into smaller modules and remove the entry.
#
# Format: { relative_path: brief_split_plan }. The path is relative
# to the ``core/`` directory and uses POSIX separators for stability
# across Windows + Linux CI.
GRANDFATHERED: dict = {
    # v0.6.1 v18.7 (2026-06-20) — meta.py split into the meta/
    # package (PR `refactor/v0.6.1-meta-mode-split`); the entry
    # was removed in the same PR per the anti-creep rule.
    #
    # 2026-06-21 — the two files grandfathered by the vision-wire PR
    # (model_resolver.py, intent_classifier.py) were SPLIT in
    # `fix/v0.6.1-test-suite-sweep`: the Phase-3a tier ladder moved to
    # core/model_resolver_tiers.py and the classify_fast tables to
    # core/intent_fast_patterns.py. Both are back under the cap, so per
    # the anti-creep rule their entries were removed in the same PR.
    # No grandfather entries currently — every core/**/*.py is at or
    # under the rule #5 ceiling.
}


def _normalized_size(path: Path) -> int:
    """Return the file size after CRLF → LF normalization.

    Matches the size git stores in its blob for repos with
    ``core.autocrlf=true`` on Windows — the byte count rule #5
    actually constrains on disk.
    """
    with open(path, "rb") as fh:
        return len(fh.read().replace(b"\r\n", b"\n"))


def _all_core_python_files() -> list[Path]:
    """Walk ``core/`` and return every ``*.py`` file.

    ``__pycache__`` directories are skipped (Python writes byte-code
    there and the size has no operator meaning).
    """
    out: list[Path] = []
    for root, dirs, files in os.walk(CORE_DIR):
        # Prune byte-code dir in-place so os.walk doesn't descend.
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in files:
            if name.endswith(".py"):
                out.append(Path(root) / name)
    return out


def _rel(path: Path) -> str:
    """Path relative to core/ as POSIX (stable across OSes)."""
    return path.relative_to(CORE_DIR).as_posix()


class ModuleSizeGateTests(unittest.TestCase):
    """Rule #5 enforcement (forward-only) + grandfather anti-creep."""

    def test_no_new_oversize_files(self):
        """Every ``core/**/*.py`` not on the grandfather list MUST
        stay under the 20 KB ceiling."""
        violations: list[str] = []
        for path in _all_core_python_files():
            rel = _rel(path)
            if rel in GRANDFATHERED:
                continue
            size = _normalized_size(path)
            if size > CAP_BYTES:
                violations.append(
                    f"  {rel}: {size:,} bytes (over cap by "
                    f"{size - CAP_BYTES:,} bytes)"
                )
        if violations:
            self.fail(
                "CLAUDE.md rule #5 violation — "
                f"{len(violations)} file(s) over 20 KB:\n"
                + "\n".join(violations)
                + "\n\nEither split the file into smaller modules "
                "(see e.g. core/abstraction/ for the pattern), or "
                "if the file genuinely cannot be split right now, "
                "add it to GRANDFATHERED in this test file with a "
                "brief split plan."
            )

    def test_grandfather_entries_still_oversize(self):
        """Every entry in ``GRANDFATHERED`` must STILL be over the
        cap. If a file fell back under, the entry is stale (somebody
        already split it) and MUST be removed in the same PR."""
        stale: list[str] = []
        for rel in GRANDFATHERED:
            path = CORE_DIR / rel
            if not path.exists():
                stale.append(
                    f"  {rel}: grandfather entry exists but file "
                    f"is missing — entry stale, remove."
                )
                continue
            size = _normalized_size(path)
            if size <= CAP_BYTES:
                stale.append(
                    f"  {rel}: now {size:,} bytes ≤ 20,480 bytes — "
                    f"file is split-clean, remove grandfather entry."
                )
        if stale:
            self.fail(
                "Stale grandfather entries — "
                f"{len(stale)} entry/entries refer to files that no "
                "longer violate the cap:\n"
                + "\n".join(stale)
                + "\n\nRemove the stale entry/entries from "
                "GRANDFATHERED so the test starts enforcing the cap "
                "for that file again."
            )

    def test_grandfather_paths_exist(self):
        """Every grandfather entry MUST point at a real file.
        Catches typos in path strings at gate-add time."""
        missing = [
            rel for rel in GRANDFATHERED
            if not (CORE_DIR / rel).exists()
        ]
        if missing:
            self.fail(
                "Grandfather entries point at missing files:\n  "
                + "\n  ".join(missing)
            )


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
