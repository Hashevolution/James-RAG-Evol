"""Admin foldable nav + game→tech concept (item #2, 2026-05-08).

User feedback: "어드민 페이지도 폰에서 보기 좋게 변경. 사이드 메뉴도
폴더블 형식으로 개선. 장비 현황에 나오는 게임 컨셉을 기술과 비즈니스에
어울리는 컨셉으로 수정".

Two changes:

A. Foldable admin nav
   - Each section header (.nav-section.nav-foldable) toggles the
     following .nav-group on click. Desktop + mobile.
   - Mobile: hamburger button slides the entire nav as a drawer.
   - Backdrop closes the drawer when clicked.
   - Selecting a page on mobile auto-closes the drawer (UX).

B. Hardware tier names — RPG → tech/business tiers
   - CPU: Wooden Sword/Magic Sword → Entry CPU/Mainstream CPU/...
   - GPU: Wizard Staff/Grand Wizard Staff → Entry Accelerator/...
   - RAM: Iron Shield → Light Memory/Standard Memory/...
   - Disk: Backpack → Personal Storage/Team Storage/...
   - james_rank: Wizard ranks → Personal/Workstation/Production/
                                 Enterprise/Datacenter Tier

Run:
  python -m unittest tests.test_admin_foldable_tech
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parent.parent
HW_INSPECTOR = ROOT / "tools" / "system" / "hardware_inspector.py"
ADMIN_HTML   = ROOT / "frontend" / "admin.html"
ADMIN_JS     = ROOT / "frontend" / "static" / "admin.js"
MOBILE_CSS   = ROOT / "frontend" / "static" / "mobile.css"


class TechTierNamesTests(unittest.TestCase):
    """Hardware tier names should reflect tech/business reality, not
    fantasy RPG. Operators show this to stakeholders."""

    @classmethod
    def setUpClass(cls):
        cls.src = HW_INSPECTOR.read_text(encoding="utf-8")

    def test_no_rpg_weapon_names_in_returned_data(self):
        # The forbidden RPG names must not appear AS QUOTED VALUES inside
        # the weapons dict (i.e. inside name_map/desc_map). They MAY appear
        # in human-readable comments explaining the historical concept.
        # Strategy: check the RANGES that contain `name_map` / `desc_map`
        # / `rank_map` literal blocks, not the whole file.
        import re
        forbidden = [
            "Wooden Sword", "Iron Sword", "Silver Blade", "Magic Sword",
            "Legendary Holy Sword",
            "Leather Shield", "Iron Shield", "Magic Shield", "Immortal Shield",
            "Apprentice Staff", "Wizard Staff", "Sage Staff",
            "Grand Wizard Staff", "Divine Wand",
            "Small Pouch", "Travel Bag", "Large Backpack",
            "Magic Space Bag", "Infinite Warehouse",
            "Legendary Wizard", "Apprentice Wizard",
        ]
        # The active weapon mapping is between `def _weapon_meta(` and the
        # closing `}` before `meta = weapons.get(...)`. Pull that slice.
        m = re.search(
            r'def _weapon_meta\([^)]*\)[^{]*?weapons\s*=\s*\{(.+?)\n\s*\}\s*\n\s*meta\s*=\s*weapons',
            self.src, re.DOTALL,
        )
        self.assertIsNotNone(m, "could not locate weapons dict body")
        weapons_body = m.group(1)
        for term in forbidden:
            self.assertNotIn(term, weapons_body,
                             f"RPG term {term!r} still inside weapons dict — "
                             f"replace with tech/business equivalent")
        # Also check rank_map (5-line dict literal).
        m2 = re.search(r"rank_map\s*=\s*\[(.+?)\]", self.src, re.DOTALL)
        self.assertIsNotNone(m2, "rank_map not found")
        rank_body = m2.group(1)
        for term in ("Legendary Wizard", "Grand Wizard", "Apprentice Wizard",
                     "Trainee", "Wizard"):
            # 'Wizard' as standalone word — not 'Workstation' etc.
            self.assertNotRegex(rank_body, rf'"\s*{re.escape(term)}\s*"',
                                f"rank_map still contains RPG rank {term!r}")

    def test_tech_tier_names_present(self):
        # Spot-check a few tech-tier names exist.
        for term in ("Entry CPU", "Mainstream CPU",
                     "Entry Accelerator", "Production GPU", "Datacenter GPU",
                     "Standard Memory", "Wide Context Memory",
                     "Personal Storage", "Enterprise Storage",
                     "Datacenter Tier", "Enterprise Tier", "Personal Tier"):
            self.assertIn(term, self.src,
                          f"expected tech-tier term {term!r} in hardware_inspector")

    def test_role_names_business_friendly(self):
        # GPU role: "GPU Inference" → "AI Acceleration"
        self.assertIn('"AI Acceleration"', self.src,
                      "GPU role should be 'AI Acceleration' (business term)")
        self.assertIn('"Compute"', self.src,
                      "CPU role should be 'Compute'")


class FoldableNavHtmlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = ADMIN_HTML.read_text(encoding="utf-8")

    def test_hamburger_toggle_button_present(self):
        self.assertIn('id="admin-nav-toggle"', self.html,
                      "hamburger toggle button missing")
        self.assertIn('onclick="toggleAdminNav()"', self.html)

    def test_nav_sections_have_foldable_class(self):
        # All section headers should be foldable.
        # Count nav-foldable occurrences vs nav-section.
        import re
        sections = re.findall(r'class="nav-section[^"]*nav-foldable', self.html)
        self.assertGreaterEqual(
            len(sections), 4,
            f"expected ≥4 foldable sections, found {len(sections)}",
        )

    def test_nav_groups_exist(self):
        # Each section should be followed by a .nav-group container.
        import re
        groups = re.findall(r'class="nav-group"', self.html)
        self.assertGreaterEqual(len(groups), 4)

    def test_fold_icon_in_each_section(self):
        # Visual cue (▾) should be in each section header.
        import re
        icons = re.findall(r'class="nav-fold-icon"', self.html)
        self.assertGreaterEqual(len(icons), 4)


class FoldableNavCssTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.css = MOBILE_CSS.read_text(encoding="utf-8")

    def test_collapsed_class_rules(self):
        self.assertIn(".nav-section.nav-collapsed", self.css)
        self.assertIn(".nav-group.nav-group-collapsed", self.css)

    def test_drawer_transform_for_mobile(self):
        # Mobile drawer slides in via translateX.
        self.assertIn("translateX(-100%)", self.css,
                      "mobile drawer must start translateX(-100%)")
        self.assertIn(".admin-nav-open", self.css,
                      "open-state class must reset translateX")

    def test_backdrop_for_mobile_drawer(self):
        self.assertIn("admin-nav-backdrop", self.css)


class FoldableNavJsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = ADMIN_JS.read_text(encoding="utf-8")

    def test_toggle_admin_nav_function(self):
        self.assertIn("function toggleAdminNav()", self.js)
        # Backdrop is dynamically created.
        self.assertIn("admin-nav-backdrop", self.js)

    def test_toggle_nav_section_function(self):
        self.assertIn("function toggleNavSection", self.js)
        # Toggles the next sibling .nav-group.
        self.assertIn("nextElementSibling", self.js)
        self.assertIn("nav-group-collapsed", self.js)

    def test_show_page_auto_closes_mobile_drawer(self):
        # When mobile drawer is open + user picks a page, drawer should close.
        idx = self.js.index("function showPage(id, el)")
        body = self.js[idx:idx + 1500]
        self.assertIn("admin-nav-open", body,
                      "showPage must check if drawer is open")
        self.assertIn("matchMedia('(max-width: 768px)')", body,
                      "auto-close should only fire on mobile")


if __name__ == "__main__":
    unittest.main()
