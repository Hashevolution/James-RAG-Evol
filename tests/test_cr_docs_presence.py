"""[PR-CR-A, 2026-05-12] Change Request track — docs-presence contract.

Step A of the v0.2.x CR cycle is doc-only: a handover under
``docs/handovers/v0.2.x-cr-track.md``, a new trust-zone section
``§5.6 Change Request primitive`` in ``docs/ARCHITECTURE.md``, and
a ``ROADMAP.md`` entry that points to both. CLAUDE.md rule #4
explicitly requires an architecture-labelled PR for new modules /
new trust zones — this test makes the docs load-bearing so a
later PR cannot quietly skip them.

Mirrors the rollout-gate pattern from
``tests/test_frontend_event_delegation.py`` and
``tests/test_mobile_css_coverage.py``: the documents themselves
are the contract, and a contract test names the load-bearing
substrings so silent drift becomes a CI failure.

Out of scope for this test:
- The actual ``core/change_request.py`` module (PR-CR-B).
- The ``change_requests`` / ``cr_reviews`` SQLite tables (PR-CR-B).
- Any UI element (PR-CR-C).

Run:
    python -m unittest tests.test_cr_docs_presence
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
HANDOVER = ROOT / "docs" / "handovers" / "v0.2.x-cr-track.md"
ARCHITECTURE = ROOT / "docs" / "ARCHITECTURE.md"
ROADMAP = ROOT / "ROADMAP.md"
CLAUDE_MD = ROOT / "CLAUDE.md"


class HandoverPresenceTests(unittest.TestCase):
    """The v0.2.x CR handover doc must exist with the load-bearing
    sections subsequent PRs will reference."""

    @classmethod
    def setUpClass(cls):
        cls.assertTrue = unittest.TestCase().assertTrue  # for setUpClass usage
        cls.text = HANDOVER.read_text(encoding="utf-8") if HANDOVER.exists() else ""

    def test_handover_file_exists(self):
        self.assertTrue(
            HANDOVER.exists(),
            f"missing {HANDOVER.relative_to(ROOT)} — PR-CR-A must create it",
        )

    def test_handover_freezes_scope(self):
        # PR-CR-B/C/D will all reference 'frozen for v0.2.x' to refuse
        # scope creep — if this phrase disappears, the cycle plan is
        # silently broken.
        self.assertIn(
            "frozen for v0.2.x", self.text,
            "handover must declare its scope as 'frozen for v0.2.x' "
            "so subsequent PRs can refuse scope creep with a doc cite",
        )

    def test_handover_names_both_target_types(self):
        # wiki_entity ships in CR-B; run_jobs in CR-D. Both must be
        # in the handover so the dispatcher contract test in CR-B can
        # cross-reference.
        self.assertIn("wiki_entity", self.text)
        self.assertIn("run_jobs", self.text)

    def test_handover_lists_invariants(self):
        # The seven invariants (approver != proposer, base_hash
        # mismatch → superseded, etc.) are the contract that
        # tests/test_change_request_core.py (PR-CR-B) will enforce.
        self.assertIn("Invariants", self.text)
        for phrase in (
            "approver",         # invariant 2
            "base_hash",        # invariant 3
            "transaction",      # invariant 4
            "audit_bridge",     # invariant 7
        ):
            with self.subTest(invariant_token=phrase):
                self.assertIn(phrase, self.text,
                    f"handover invariant section must mention {phrase!r}")

    def test_handover_lists_deferred_v03_items(self):
        # The cycle deliberately punts five items to v0.3 — multi-
        # approver, team/project/department, hierarchical labels,
        # external target_type API, domain-specific status machines.
        # Naming them in the handover is what lets reviewers refuse
        # scope creep without re-litigating.
        for deferred in (
            "Multi-approver",
            "Team",
            "Hierarchical",
            "registration API",
        ):
            with self.subTest(deferred=deferred):
                self.assertIn(deferred, self.text,
                    f"handover must list {deferred!r} among deferred-"
                    "to-v0.3 items so scope creep is refusable")

    def test_handover_names_pr_sequence(self):
        # CR-A through CR-D are the only PRs that should land in this
        # cycle. Naming them keeps the sequence visible.
        for pr in ("CR-A", "CR-B", "CR-C", "CR-D"):
            with self.subTest(pr=pr):
                self.assertIn(pr, self.text,
                    f"handover must name {pr} in the PR sequence")


class ArchitectureSectionTests(unittest.TestCase):
    """ARCHITECTURE.md must declare the new trust zone — CLAUDE.md
    rule #4 requires an architecture-labelled PR for new trust
    zones, and this test pins the load-bearing tokens."""

    @classmethod
    def setUpClass(cls):
        cls.text = ARCHITECTURE.read_text(encoding="utf-8")

    def test_change_request_section_present(self):
        # §5.6 sits between PolicyEngine (5.5) and Evolution
        # Boundaries (§6) — both governance primitives.
        self.assertIn("5.6 Change Request primitive", self.text,
            "ARCHITECTURE.md must declare §5.6 — the new trust zone "
            "(CLAUDE.md rule #4)")

    def test_section_states_audit_bridge_as_source_of_truth(self):
        # The invariant that lets the CR table be reconstructed from
        # audit_bridge is what makes the primitive recoverable.
        idx = self.text.index("5.6 Change Request primitive")
        section = self.text[idx:idx + 4000]
        self.assertIn("audit_bridge", section,
            "§5.6 must name audit_bridge as the source of truth")
        self.assertIn("append-only", section.lower() + section)

    def test_section_states_closed_enum_for_target_type(self):
        # The reason we don't expose external target_type registration
        # before v0.3 — it's exactly the plugin contract surface.
        idx = self.text.index("5.6 Change Request primitive")
        section = self.text[idx:idx + 4000]
        self.assertIn("closed enum", section.lower(),
            "§5.6 must state target_type is a closed enum until v0.3 — "
            "the registration API surface is the plugin contract")
        self.assertIn("v0.3", section)

    def test_section_states_approver_neq_proposer(self):
        # The only baked-in workflow rule.
        idx = self.text.index("5.6 Change Request primitive")
        section = self.text[idx:idx + 4000]
        self.assertIn("approver", section.lower())
        self.assertIn("proposer", section.lower())

    def test_evolution_section_references_cr_wrapping(self):
        # §6 (Evolution Boundaries) must note that the self-
        # evolution gate is being wrapped by CR in CR-D so the
        # CLAUDE.md rule #3 invariant (approver_username present)
        # is visibly preserved.
        idx = self.text.index("## 6. Evolution Boundaries")
        section = self.text[idx:idx + 2000]
        # Either "Change Request" or "CR primitive" — both signal the
        # wrapping. Refuse the section if neither is mentioned.
        self.assertTrue(
            ("Change Request" in section) or ("§5.6" in section),
            "§6 must reference the §5.6 CR primitive so the wrap "
            "decision is visible from the evolution-gate doc surface",
        )


class RoadmapEntryTests(unittest.TestCase):
    """ROADMAP.md must point to the CR track from the v0.2 deferred-
    follow-ups section so future-self knows it's a cycle in flight."""

    @classmethod
    def setUpClass(cls):
        cls.text = ROADMAP.read_text(encoding="utf-8")

    def test_change_request_entry_present(self):
        self.assertIn("Change Request primitive", self.text,
            "ROADMAP must reference the CR track")

    def test_entry_points_to_handover(self):
        # Forward references must remain valid — if a CR-B reviewer
        # follows the ROADMAP link they should land in the handover.
        self.assertIn("v0.2.x-cr-track.md", self.text,
            "ROADMAP entry must point to the handover doc by path")
        self.assertIn("ARCHITECTURE.md §5.6", self.text,
            "ROADMAP entry must point to the architecture section")

    def test_entry_names_done_when(self):
        # Every roadmap item carries a done-when criterion.
        idx = self.text.index("Change Request primitive")
        nxt_dash = self.text.index("- **", idx + 1)
        block = self.text[idx:nxt_dash]
        self.assertIn("Done-when", block.replace("done-when", "Done-when"))


class ClaudeMdEntryTests(unittest.TestCase):
    """CLAUDE.md's 'Where to look next' table must list the CR track
    so any future session that loads only CLAUDE.md finds it."""

    @classmethod
    def setUpClass(cls):
        cls.text = CLAUDE_MD.read_text(encoding="utf-8")

    def test_cr_track_listed(self):
        self.assertIn("v0.2.x-cr-track.md", self.text,
            "CLAUDE.md 'Where to look next' table must list the CR "
            "track handover so future sessions discover it")


if __name__ == "__main__":
    unittest.main()
