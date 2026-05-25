"""D5.D — Cross-lingual entity alias pack contract tests.

Pins the alias pack data + the graph_engine integration so a
refactor that drops the pack or breaks the snapshot augmentation
is caught here.

Coverage:
  • alias pack data shape (list of (canonical, [alias]) tuples)
  • all canonical names + aliases are non-empty strings
  • iter helper returns a shallow copy (callers can iterate safely)
  • graph_engine snapshot augmentation: when a wiki entity matches
    a canonical name, the alias surface forms are merged under the
    same entity_id at the same entity_type
  • alias pack does NOT override existing wiki frontmatter aliases
    (first-write wins — wiki content is authoritative)
  • a pack entry whose canonical name has no matching wiki entity
    is silently skipped (operator hasn't installed that entity)
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.entity_alias_pack import _ENTITY_ALIAS_PACK, iter_entity_aliases


# ─── Alias pack data shape ───────────────────────────────────────


class AliasPackShapeTests(unittest.TestCase):
    """Pin the (canonical, [aliases]) tuple structure + content rules."""

    def test_pack_is_nonempty(self):
        self.assertGreater(len(_ENTITY_ALIAS_PACK), 0)

    def test_every_entry_is_tuple_of_str_and_list(self):
        for entry in _ENTITY_ALIAS_PACK:
            self.assertIsInstance(entry, tuple)
            self.assertEqual(len(entry), 2)
            canonical, aliases = entry
            self.assertIsInstance(canonical, str)
            self.assertGreater(len(canonical), 0)
            self.assertIsInstance(aliases, list)
            self.assertGreater(len(aliases), 0)

    def test_every_alias_is_nonempty_str(self):
        for canonical, aliases in _ENTITY_ALIAS_PACK:
            for alias in aliases:
                self.assertIsInstance(alias, str, f"in {canonical!r}")
                self.assertGreater(len(alias.strip()), 0, f"in {canonical!r}")

    def test_palantir_has_korean_alias(self):
        # D5.D root cause this PR fixes — the 2026-05-25 cross-lingual
        # diagnostic case. Palantir wiki entity exists in the JAMES
        # corpus; "팔란티어" was the missing alias.
        found = False
        for canonical, aliases in _ENTITY_ALIAS_PACK:
            if "Palantir" in canonical and "팔란티어" in aliases:
                found = True
                break
        self.assertTrue(found, "Palantir entry must include '팔란티어' alias")

    def test_nvidia_has_english_alias(self):
        # Reverse direction — wiki entity is Korean (`엔비디아.md`),
        # need English aliases so an English query matches it.
        found = False
        for canonical, aliases in _ENTITY_ALIAS_PACK:
            if canonical == "엔비디아" and "Nvidia" in aliases:
                found = True
                break
        self.assertTrue(found, "엔비디아 entry must include 'Nvidia' alias")


class IterHelperTests(unittest.TestCase):

    def test_iter_returns_list_of_tuples(self):
        result = iter_entity_aliases()
        self.assertIsInstance(result, list)
        for entry in result:
            self.assertIsInstance(entry, tuple)
            self.assertEqual(len(entry), 2)

    def test_iter_returns_shallow_copy(self):
        # Mutating the returned list must not affect subsequent calls
        result_a = iter_entity_aliases()
        original_len = len(result_a)
        result_a.append(("test_canonical", ["test_alias"]))
        result_b = iter_entity_aliases()
        self.assertEqual(len(result_b), original_len)


# ─── graph_engine snapshot augmentation ──────────────────────────


class _FakeWikiGen:
    """Minimal stand-in for WikiGenerator that exposes only the
    surfaces `build_entity_map_snapshot` reads: `entity_id_index`,
    `_read_frontmatter`, `_normalize_name`.
    """

    def __init__(self, entity_fixtures: dict):
        """entity_fixtures: {entity_id: frontmatter_dict}"""
        self._fixtures = entity_fixtures
        # build a fake entity_id_index — values are strings the snapshot
        # builder will pass through to `_read_frontmatter`
        self.entity_id_index = {eid: eid for eid in entity_fixtures}

    def _read_frontmatter(self, path) -> dict:
        # path is the value from entity_id_index, which we set to eid above
        return self._fixtures.get(str(path), {})

    @staticmethod
    def _normalize_name(name: str) -> str:
        import re
        return re.sub(r"[^\w가-힣]", "_", name.strip().lower())


class _GraphEngineHarness:
    """Minimal harness — exposes only the fields
    `build_entity_map_snapshot` uses. Avoids spinning up the full
    engine (which loads wiki, vector store, etc.)."""

    def __init__(self, wiki_gen):
        self.wiki_generator = wiki_gen
        import threading
        self._map_lock = threading.Lock()

    @staticmethod
    def _log(step, error, role="system"):
        pass


class SnapshotAugmentationTests(unittest.TestCase):

    def _build(self, fixtures):
        from core.graph_engine import GraphEngine

        h = _GraphEngineHarness(_FakeWikiGen(fixtures))
        # Pass the harness as `self` directly — works on bound and
        # unbound function references alike across Python versions.
        snapshot = GraphEngine.build_entity_map_snapshot(h)
        return snapshot

    def test_palantir_korean_alias_resolves_to_wiki_entity(self):
        # Fixture: wiki has the Palantir org entity but no Korean
        # alias in its frontmatter. The alias pack should add the
        # Korean surface form to the snapshot.
        snapshot = self._build({
            "e_org_palantir": {
                "entity_type": "org",
                "normalized_name": "palantir_technologies__pltr_",
                "name": "Palantir Technologies (PLTR)",
                "aliases": ["Palantir Technologies", "PLTR"],
            },
        })
        # Canonical and existing frontmatter aliases — present
        self.assertEqual(
            snapshot.get(("org", "palantir_technologies__pltr_")),
            "e_org_palantir",
        )
        # Alias pack augmentation — Korean form should be present
        self.assertEqual(snapshot.get(("org", "팔란티어")), "e_org_palantir")

    def test_nvidia_english_alias_resolves_to_korean_wiki_entity(self):
        # Reverse case — wiki entity is Korean; alias pack adds the
        # English surface forms.
        snapshot = self._build({
            "e_org_nvidia": {
                "entity_type": "org",
                "normalized_name": "엔비디아",
                "name": "엔비디아",
                "aliases": [],
            },
        })
        self.assertEqual(snapshot.get(("org", "엔비디아")), "e_org_nvidia")
        # Augmentation
        self.assertEqual(snapshot.get(("org", "nvidia")), "e_org_nvidia")
        self.assertEqual(snapshot.get(("org", "nvda")), "e_org_nvidia")

    def test_pack_entry_without_wiki_match_is_skipped(self):
        # OpenAI is in the pack but the operator hasn't installed an
        # OpenAI wiki entity. The pack entry should be silently
        # skipped (no snapshot entry for OpenAI or its aliases).
        snapshot = self._build({
            "e_org_palantir": {
                "entity_type": "org",
                "normalized_name": "palantir_technologies__pltr_",
                "name": "Palantir Technologies (PLTR)",
                "aliases": [],
            },
        })
        # OpenAI is in the pack but no wiki match — no snapshot entry
        self.assertIsNone(snapshot.get(("org", "openai")))
        self.assertIsNone(snapshot.get(("org", "오픈에이아이")))

    def test_wiki_frontmatter_alias_takes_precedence_first_write(self):
        # If the wiki frontmatter already has an alias that the pack
        # also covers, the wiki one wins (first-write semantics in
        # the snapshot dict).
        snapshot = self._build({
            "e_org_palantir_wiki": {
                "entity_type": "org",
                "normalized_name": "palantir_technologies__pltr_",
                "name": "Palantir Technologies (PLTR)",
                "aliases": ["팔란티어"],  # already in frontmatter
            },
        })
        # The Korean alias resolves to the wiki-derived eid (which is
        # also what the pack would have produced — same eid). The key
        # invariant is "no overwrite": both produce e_org_palantir_wiki.
        self.assertEqual(snapshot.get(("org", "팔란티어")), "e_org_palantir_wiki")

    def test_pack_only_augments_matched_type(self):
        # When the canonical match is under type "org", the aliases
        # are added under "org" only — not propagated across types.
        snapshot = self._build({
            "e_org_tesla": {
                "entity_type": "org",
                "normalized_name": "tesla__inc___tsla_",
                "name": "Tesla, Inc. (TSLA)",
                "aliases": [],
            },
        })
        # Tesla pack entry includes "테슬라" — should land under "org"
        self.assertEqual(snapshot.get(("org", "테슬라")), "e_org_tesla")
        # ...but NOT under "person" / "concept" / "document"
        self.assertIsNone(snapshot.get(("person", "테슬라")))
        self.assertIsNone(snapshot.get(("concept", "테슬라")))
        self.assertIsNone(snapshot.get(("document", "테슬라")))
