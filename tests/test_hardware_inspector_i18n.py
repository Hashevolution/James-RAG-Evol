"""PROJECT JAMES — hardware_inspector i18n contract tests.

Pins the ``name_key`` / ``role_key`` / ``desc_key`` convention added by
PR-6 of the v0.3.x i18n sweep series so the admin Hardware page can
bind ``data-i18n`` to backend output and switch language without
re-fetching the live hardware probe.

Regression here re-introduces the §3 Phase 2 bug where the 4 hardware
cards (CPU / Memory / GPU / Storage) + tier names + role subtitles +
descriptions all stayed English regardless of the active language.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

from tools.system.hardware_inspector import _weapon_meta  # noqa: E402


class WeaponMetaI18nTests(unittest.TestCase):

    COMPONENTS = ["cpu", "ram", "gpu", "disk"]

    def test_every_component_surfaces_i18n_keys(self):
        # Probe each component at a known-valid level (5 → middle tier).
        # The shape contract must include name/role/desc + their _key
        # counterparts so the UI can bind data-i18n.
        required = {"icon", "name", "name_key",
                    "role", "role_key",
                    "desc", "desc_key"}
        for component in self.COMPONENTS:
            with self.subTest(component=component):
                meta = _weapon_meta(component, 5)
                self.assertTrue(required.issubset(meta.keys()),
                    f"component {component!r} missing fields: "
                    f"{required - set(meta.keys())}")
                # Keys are non-empty for known components.
                self.assertTrue(meta["name_key"],
                    f"{component} name_key must not be empty")
                self.assertTrue(meta["role_key"],
                    f"{component} role_key must not be empty")
                self.assertTrue(meta["desc_key"],
                    f"{component} desc_key must not be empty")

    def test_name_key_namespace_convention(self):
        # Convention mirrors the i18n table layout (i18n.js):
        # `hw.<component>.tier_<short_id>` so the table stays
        # scannable.
        for component in self.COMPONENTS:
            with self.subTest(component=component):
                meta = _weapon_meta(component, 5)
                self.assertTrue(
                    meta["name_key"].startswith(f"hw.{component}.tier_"),
                    f"{component} name_key must start with "
                    f"'hw.{component}.tier_'; got {meta['name_key']!r}",
                )
                self.assertTrue(
                    meta["desc_key"].startswith(f"hw.{component}.desc_"),
                    f"{component} desc_key must start with "
                    f"'hw.{component}.desc_'; got {meta['desc_key']!r}",
                )

    def test_role_key_namespace(self):
        expected = {
            "cpu":  "hw.role.compute",
            "ram":  "hw.role.memory",
            "gpu":  "hw.role.ai_acceleration",
            "disk": "hw.role.storage",
        }
        for component, expected_key in expected.items():
            with self.subTest(component=component):
                self.assertEqual(_weapon_meta(component, 5)["role_key"],
                                 expected_key)

    def test_tier_keys_change_with_level(self):
        # Different levels for the same component must produce different
        # name_key / desc_key — otherwise a single tier label would leak
        # across all levels.
        meta_low  = _weapon_meta("cpu", 2)   # Entry CPU
        meta_high = _weapon_meta("cpu", 9)   # High-Performance CPU
        self.assertNotEqual(meta_low["name_key"], meta_high["name_key"])
        self.assertNotEqual(meta_low["desc_key"], meta_high["desc_key"])

    def test_gpu_cpu_only_branch_has_key(self):
        # level=0 hits the special (0, 0) "CPU-only" entry. Verify the
        # short_id flows through to the key.
        meta = _weapon_meta("gpu", 0)
        self.assertEqual(meta["name_key"], "hw.gpu.tier_cpu_only")
        self.assertEqual(meta["desc_key"], "hw.gpu.desc_cpu_only")


if __name__ == "__main__":
    unittest.main()
