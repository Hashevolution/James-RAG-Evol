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


if __name__ == "__main__":
    unittest.main()
