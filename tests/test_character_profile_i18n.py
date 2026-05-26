"""PROJECT JAMES — character_profile i18n contract tests.

Pins the ``label_key`` convention introduced by PR-4 of the v0.3.x
i18n sweep so the admin Character page (radar + Fine Tune sliders) can
bind ``data-i18n`` to backend output and switch language without a
re-fetch.

Regression here re-introduces the §3 Phase 2 bug where 12 radar axis
labels + 14 Fine Tune slider labels stayed Korean in EN mode (the
prior renderer preferred ``label_ko`` unconditionally).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

from core.character_profile import TRAITS  # noqa: E402


class TraitI18nTests(unittest.TestCase):

    def test_every_trait_has_label_key(self):
        required = {"label", "label_ko", "label_key",
                    "group", "default", "icon"}
        for tid, spec in TRAITS.items():
            with self.subTest(trait=tid):
                self.assertTrue(required.issubset(spec.keys()),
                    f"trait {tid!r} missing fields: "
                    f"{required - set(spec.keys())}")

    def test_label_key_follows_convention(self):
        # Convention mirrors `growth.capability.<id>` (PR-3 / #396) and
        # `policy.feature.<id>` (PR-2 / #395). Anchored at
        # `char.trait.<id>` so the i18n table stays scannable and
        # adding a trait does NOT need a second registration step.
        for tid, spec in TRAITS.items():
            with self.subTest(trait=tid):
                self.assertEqual(spec["label_key"],
                                 f"char.trait.{tid}")

    def test_label_keys_are_unique(self):
        keys = [s["label_key"] for s in TRAITS.values()]
        self.assertEqual(len(keys), len(set(keys)),
            "label_keys must be unique across traits")


class GetWithMetaPropagatesLabelKeyTests(unittest.TestCase):
    """v0.4 live verify regression (2026-05-26).

    Before the fix, `CharacterProfile.get_with_meta()` returned every
    field except ``label_key``. The admin radar / Fine Tune slider
    rendering in ``admin.js`` keys off ``tr.label_key`` to resolve
    trait names through ``t(label_key)``; an absent key forces the
    Korean fallback (``tr.label_ko``) regardless of the active UI
    language → 12 radar axis labels + 14 slider labels rendered
    Korean in EN mode.

    These tests pin every entry of the API surface so a future
    refactor can't drop ``label_key`` again without breaking CI.
    """

    def setUp(self):
        from core.character_profile import CharacterProfile
        self.cp = CharacterProfile()

    def test_get_with_meta_includes_label_key(self):
        meta = self.cp.get_with_meta()
        self.assertTrue(meta, "get_with_meta() must return non-empty list")
        for entry in meta:
            with self.subTest(trait=entry.get("id")):
                self.assertIn("label_key", entry,
                    f"get_with_meta entry for {entry.get('id')!r} "
                    "missing label_key — admin radar falls back to "
                    "label_ko under EN mode without it")

    def test_get_with_meta_label_key_matches_traits_table(self):
        meta = self.cp.get_with_meta()
        for entry in meta:
            with self.subTest(trait=entry.get("id")):
                self.assertEqual(
                    entry["label_key"],
                    TRAITS[entry["id"]]["label_key"],
                    f"label_key drift between TRAITS table and "
                    f"get_with_meta for trait {entry['id']!r}",
                )

    def test_get_with_meta_label_key_unique_across_entries(self):
        meta = self.cp.get_with_meta()
        keys = [e["label_key"] for e in meta]
        self.assertEqual(len(keys), len(set(keys)),
            "label_keys must remain unique through the API surface")


if __name__ == "__main__":
    unittest.main()
