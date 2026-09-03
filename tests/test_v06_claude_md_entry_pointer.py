"""v0.6 — CLAUDE.md "Where to look next" first-row staleness guard.

CLAUDE.md is the **session briefing** every fresh Claude Code session
reads first. The "Where to look next" table's first row IS the entry
point — the doc whose content tells the next session what cycle
they're in and what to work on.

When a cycle handover lands but CLAUDE.md isn't updated, the next
session reads a stale entry pointer and starts work in the wrong
cycle. This has happened (the `v0.6-entry-skeleton-2026-06-13.md`
itself §5 calls this out as a NEW solo-doable: "a test that asserts
CLAUDE.md 'Where to look next' first row points at the most recent
handover skeleton OR entry doc — would catch the staleness this
skeleton exists to prevent").

This test pins four invariants on the first data row:

  1. **Existence** — the file path it links to MUST exist on disk.
  2. **Location** — the file MUST live under `docs/handovers/`
     (entry skeletons + cycle close handovers + entry docs all live
     there; pointing at a memory file or a research report on the
     first row is a category error).
  3. **Marker** — the row MUST carry an "entry" / "next session" /
     "skeleton" marker so the next session can tell at a glance
     "this is THE entry, not the next-most-recent doc".
  4. **Recency** (added 2026-08-21) — the file it points at MUST be
     the NEWEST dated handover on disk. Invariants 1-3 only check
     that the pointer resolves; they pass happily while the pointer
     rots. That is exactly what happened between 2026-06-13 and
     2026-08-19: three newer handovers landed
     (`v0.6.1-session-close-2026-06-{22,23,26}.md`) while the first
     row still named the 2026-06-13 entry skeleton, and this test
     stayed green the whole time. Recency is measured off the
     ``YYYY-MM-DD`` in the filename; handovers without a date in
     the name are track docs, not cycle entries, and are ignored.

A future PR that lands a new cycle's entry doc without updating
CLAUDE.md fails invariant #4 (the first row still names an older
handover), and a renamed/deleted one fails #1. Either failure
surfaces at PR time, not 3 weeks later when a fresh session reads
the stale pointer.

Run:
  python -m unittest tests.test_v06_claude_md_entry_pointer
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


REPO_ROOT = Path(__file__).resolve().parent.parent
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"

# Heading anchor for the table. Lives at column 0, must be exact.
SECTION_HEADER = "## Where to look next"

# Path pattern inside a backticked cell — matches a relative repo
# path with `.md` extension. Tolerates leading/trailing markdown
# emphasis markers (`**path**`).
_BACKTICKED_PATH = re.compile(r"`([^`]+\.md)`")

# `v0.6.1-session-close-2026-06-26.md` -> date part. Handover docs
# without a date (track docs like `v0.2.1-business-track.md`) are not
# cycle entries and take no part in the recency comparison.
_DATED_HANDOVER = re.compile(r"(\d{4})-(\d{2})-(\d{2})\.md$")

HANDOVERS_DIR = REPO_ROOT / "docs" / "handovers"


def _filename_date(path) -> tuple | None:
    """Return ``(YYYY, MM, DD)`` from a handover filename, or None."""
    m = _DATED_HANDOVER.search(str(path).replace("\\", "/"))
    if not m:
        return None
    return tuple(int(g) for g in m.groups())


def _newest_dated_handovers() -> list:
    """Every handover carrying the newest filename date.

    A list rather than a single file because one session can close
    with two docs dated the same day — either is a legitimate entry
    pointer.
    """
    dated = [
        (d, p) for p in HANDOVERS_DIR.glob("*.md")
        if (d := _filename_date(p.name)) is not None
    ]
    if not dated:
        return []
    newest = max(d for d, _ in dated)
    return [p for d, p in dated if d == newest]


def _find_first_data_row() -> str:
    """Return the first table row AFTER the `## Where to look next`
    header + the table's `|---|---|` separator.

    Raises:
        AssertionError-like via unittest if the section / table /
        first row aren't found in the expected shape.
    """
    body = CLAUDE_MD.read_text(encoding="utf-8")
    if SECTION_HEADER not in body:
        raise RuntimeError(
            f"CLAUDE.md missing canonical section header: "
            f"{SECTION_HEADER!r}"
        )
    after = body.split(SECTION_HEADER, 1)[1]
    # Skip the column header `| Purpose | File |` + separator
    # `|---|---|`, then return the next non-blank `| ... |` line.
    saw_separator = False
    for line in after.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith("|"):
            # Past the table without seeing a data row.
            break
        if re.match(r"\|\s*-+\s*\|", stripped):
            saw_separator = True
            continue
        if saw_separator:
            return stripped
    raise RuntimeError(
        "CLAUDE.md `Where to look next` table has no data rows — "
        "the entry pointer is gone, fresh sessions will land "
        "without orientation"
    )


class WhereToLookNextEntryRowTests(unittest.TestCase):
    """Invariants #1-#3 on the first data row (see #4 below)."""

    @classmethod
    def setUpClass(cls):
        cls.row = _find_first_data_row()

    def test_first_row_carries_entry_marker(self):
        """The first row must announce itself as the entry — so the
        next session can scan the table and stop at row 1 with
        confidence. Accept any of the established markers."""
        head = self.row.lower()
        markers = (
            "next session",
            "entry",
            "skeleton",
            "다음 세션",
            "🟢🟢🟢",   # the visual marker pattern used since v0.4
        )
        self.assertTrue(
            any(m in head for m in markers),
            f"first row of `Where to look next` is missing the "
            f"entry marker — fresh sessions won't know it's THE "
            f"entry. Row: {self.row!r}",
        )

    def test_first_row_references_an_existing_md_file(self):
        """Extract every backticked `.md` path in the row and assert
        at least one of them exists on disk. A stale pointer that
        names a deleted/renamed doc would fail here."""
        paths = _BACKTICKED_PATH.findall(self.row)
        self.assertTrue(
            paths,
            f"first row carries no backticked `.md` path — the "
            f"next session can't follow a link that isn't there. "
            f"Row: {self.row!r}",
        )
        existing = [
            p for p in paths
            if (REPO_ROOT / p).is_file()
        ]
        self.assertTrue(
            existing,
            f"first row references paths {paths!r}, none of which "
            f"exist on disk — the entry pointer is stale. The most "
            f"recent cycle's entry doc has likely landed under a "
            f"new filename without updating CLAUDE.md.",
        )

    def test_first_row_points_at_a_handover_doc(self):
        """The entry doc must live under `docs/handovers/` (where
        entry skeletons + cycle close handovers + entry docs all
        canonically live). Pointing at a memory file or a research
        report on row 1 is a category error — those are linked from
        subsequent rows."""
        paths = _BACKTICKED_PATH.findall(self.row)
        existing_handovers = [
            p for p in paths
            if p.startswith("docs/handovers/") and (REPO_ROOT / p).is_file()
        ]
        self.assertTrue(
            existing_handovers,
            f"first row of `Where to look next` references paths "
            f"{paths!r}, but none are under `docs/handovers/` AND "
            f"present on disk. The first row IS the cycle entry; "
            f"category-mixing it with a memory file or report "
            f"makes the table un-scannable.",
        )


class EntryPointerRecencyTests(unittest.TestCase):
    """Invariant #4 — the pointer must be the NEWEST cycle entry.

    CLAUDE.md rule #6 (state single-source): the newest handover in
    ``docs/handovers/`` IS the state; the root docs only point at it.
    A newer handover landing without this row moving means the next
    session reads a stale state — the failure this test exists to
    make impossible to merge.
    """

    def test_first_row_points_at_the_newest_handover(self):
        row = _find_first_data_row()
        newest = _newest_dated_handovers()
        self.assertTrue(
            newest,
            "docs/handovers/ has no date-stamped handover — the "
            "cycle-entry convention (`<topic>-YYYY-MM-DD.md`) is gone",
        )
        newest_names = {p.name for p in newest}
        referenced = {
            p.rsplit("/", 1)[-1]
            for p in _BACKTICKED_PATH.findall(row)
        }
        self.assertTrue(
            referenced & newest_names,
            f"CLAUDE.md `Where to look next` first row references "
            f"{sorted(referenced)!r}, but the newest handover on disk "
            f"is {sorted(newest_names)!r}. A newer cycle doc landed "
            f"without moving the entry pointer — the next session "
            f"would start from stale state. Either make the new doc "
            f"the first row, or (if it is not a cycle entry) drop the "
            f"date from its filename.",
        )


class TableShapeTests(unittest.TestCase):
    """The table itself must keep its canonical shape — header +
    separator + at least one data row."""

    def test_section_exists(self):
        body = CLAUDE_MD.read_text(encoding="utf-8")
        self.assertIn(SECTION_HEADER, body,
                      "CLAUDE.md must keep the `Where to look next` "
                      "section header verbatim")

    def test_has_at_least_one_data_row(self):
        # _find_first_data_row raises if the table is empty.
        row = _find_first_data_row()
        self.assertTrue(row.startswith("|") and row.endswith("|"))


if __name__ == "__main__":
    unittest.main()
