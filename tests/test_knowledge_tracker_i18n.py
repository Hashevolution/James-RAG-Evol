"""PROJECT JAMES — knowledge_tracker i18n contract tests.

Pins the ``label_key`` / ``desc_key`` convention introduced by PR-3 of
the v0.3.x i18n sweep series so the admin Growth page UI can bind
``data-i18n`` to backend output and switch language without a re-fetch.

A regression here silently re-introduces the §3 Phase 2 bug where the
Growth page's 8 capability rows + 6 domain cards stayed English in
KO mode (and Korean in EN mode for the domain labels via label_ko).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

from core.knowledge_tracker import (  # noqa: E402
    CAPABILITIES,
    DOMAINS,
)


class CapabilityI18nTests(unittest.TestCase):

    def test_every_capability_has_label_and_desc_keys(self):
        required = {"id", "label", "label_key", "desc", "desc_key",
                    "icon", "base"}
        for cap in CAPABILITIES:
            with self.subTest(id=cap.get("id")):
                self.assertTrue(required.issubset(cap.keys()),
                    f"capability {cap.get('id')!r} missing fields: "
                    f"{required - set(cap.keys())}")

    def test_label_key_follows_convention(self):
        # Convention mirrors `policy.feature.<id>` (#395 / PR-2) and
        # `set.cognitive_flag_<key>` (#393). Anchored at
        # `growth.capability.<id>` so the i18n table stays scannable.
        for cap in CAPABILITIES:
            cid = cap["id"]
            with self.subTest(id=cid):
                self.assertEqual(cap["label_key"],
                                 f"growth.capability.{cid}")
                self.assertEqual(cap["desc_key"],
                                 f"growth.capability.{cid}_desc")

    def test_keys_are_unique(self):
        label_keys = [c["label_key"] for c in CAPABILITIES]
        desc_keys  = [c["desc_key"]  for c in CAPABILITIES]
        self.assertEqual(len(label_keys), len(set(label_keys)))
        self.assertEqual(len(desc_keys),  len(set(desc_keys)))


class DomainI18nTests(unittest.TestCase):

    def test_every_domain_has_label_key(self):
        for did, dspec in DOMAINS.items():
            with self.subTest(domain=did):
                self.assertIn("label_key", dspec,
                    f"domain {did!r} missing label_key")
                # `label_ko` is the historic Korean fallback; the
                # i18n table is now the primary KO source so we keep
                # `label_ko` as a defensive backup but don't gate on it.
                self.assertIn("label", dspec)

    def test_domain_label_key_follows_convention(self):
        for did, dspec in DOMAINS.items():
            with self.subTest(domain=did):
                self.assertEqual(dspec["label_key"],
                                 f"growth.domain.{did}")


class GetDomainLevelsSurfacesLabelKey(unittest.TestCase):
    """`get_domain_levels()` must include label_key in its output so the
    Growth page UI (admin.js renderDomains) can bind data-i18n.
    """

    def test_label_key_in_output(self):
        from core.knowledge_tracker import get_tracker
        rows = get_tracker().get_domain_levels()
        for row in rows:
            with self.subTest(domain=row.get("domain")):
                self.assertIn("label_key", row,
                    "get_domain_levels output must carry label_key — "
                    "regression re-introduces the §3 Phase 2 KO/EN "
                    "stuck bug on domain card labels")
                # Sanity — key matches the static catalog.
                self.assertEqual(row["label_key"],
                                 f"growth.domain.{row['domain']}")


if __name__ == "__main__":
    unittest.main()
