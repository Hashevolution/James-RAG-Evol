"""PROJECT JAMES — Plugin registry tests (PR-C3).

Covers ``core/plugins/registry.py``:
  - Per-slot register / get round-trip
  - Protocol-validation rejection (object that doesn't satisfy the
    Protocol contract → ``PluginLoadError`` at register time)
  - Conflict policies (UIPanel duplicate (pack_id, panel_id) /
    Scorer duplicate pack_id) raise
  - Order-preserving iteration
  - Process-wide singleton is a fresh registry per test (via
    ``_set_registry_for_testing``)
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

from core.plugins.errors import PluginLoadError  # noqa: E402
from core.plugins.registry import (  # noqa: E402
    PluginRegistry,
    _set_registry_for_testing,
    get_registry,
)


# ─── Protocol-conforming stubs ─────────────────────────────────────


class _StubOntology:
    """Minimum OntologyPack-conforming stub. Empty tuples / dict are
    legal per the Protocol contract."""

    pack_id = "test-ontology"
    entity_types: tuple = ()
    relation_types: tuple = ()
    hierarchies: dict = {}


class _StubPrompts:
    """Minimum PromptPack-conforming stub. Both methods return empty
    so the pack contributes nothing (legal per the design memo's
    fall-through-to-default rule)."""

    pack_id = "test-prompts"

    def system_prompt(self, mode: str) -> str:
        return ""

    def few_shot(self, task: str) -> list:
        return []


class _StubUIPanel:
    """Minimum UIPanel-conforming stub. ``render`` returns the empty
    string — legal per the protocol."""

    def __init__(self, pack_id: str = "test-ui", panel_id: str = "main"):
        self.pack_id = pack_id
        self.panel_id = panel_id

    def render(self, ctx) -> str:
        return ""


class _StubScorer:
    """Minimum Scorer-conforming stub. Returns a fixed score so the
    test doesn't need to construct a realistic candidate dict."""

    def __init__(self, pack_id: str = "test-scorer"):
        self.pack_id = pack_id

    def score(self, query: str, candidate: dict) -> float:
        return 0.5


class _NonConforming:
    """Has none of the required Protocol attributes — register_* must
    reject it."""

    pass


# ─── Fixture base ──────────────────────────────────────────────────


class _RegistryFixture(unittest.TestCase):
    """Each test gets a fresh registry so order-sensitive assertions
    don't leak across cases."""

    def setUp(self):
        self._saved = get_registry()
        self.registry = PluginRegistry()
        _set_registry_for_testing(self.registry)

    def tearDown(self):
        _set_registry_for_testing(self._saved)


# ─── Ontology slot ─────────────────────────────────────────────────


class OntologyRegistration(_RegistryFixture):

    def test_register_then_get(self):
        ont = _StubOntology()
        self.registry.register_ontology(ont)
        self.assertEqual(self.registry.ontology_packs(), (ont,))

    def test_multiple_packs_preserve_order(self):
        # Two ontology packs is legal — consumer merges. Iteration
        # order must match registration order so a deterministic
        # tie-break exists at the consumer.
        a = _StubOntology()
        a.pack_id = "a"  # type: ignore[misc]
        b = _StubOntology()
        b.pack_id = "b"  # type: ignore[misc]
        self.registry.register_ontology(a)
        self.registry.register_ontology(b)
        self.assertEqual(self.registry.ontology_packs(), (a, b))

    def test_non_conforming_rejected(self):
        with self.assertRaisesRegex(
            PluginLoadError, r"does not satisfy.*OntologyPack"
        ):
            self.registry.register_ontology(_NonConforming())  # type: ignore[arg-type]


# ─── Prompts slot ──────────────────────────────────────────────────


class PromptsRegistration(_RegistryFixture):

    def test_register_then_get(self):
        p = _StubPrompts()
        self.registry.register_prompts(p)
        self.assertEqual(self.registry.prompt_packs(), (p,))

    def test_non_conforming_rejected(self):
        with self.assertRaisesRegex(
            PluginLoadError, r"does not satisfy.*PromptPack"
        ):
            self.registry.register_prompts(_NonConforming())  # type: ignore[arg-type]


# ─── UI slot ───────────────────────────────────────────────────────


class UIRegistration(_RegistryFixture):

    def test_register_then_get(self):
        panel = _StubUIPanel()
        self.registry.register_ui_panel(panel)
        self.assertEqual(self.registry.ui_panels(), (panel,))

    def test_duplicate_pack_panel_pair_rejected(self):
        p1 = _StubUIPanel(pack_id="x", panel_id="main")
        p2 = _StubUIPanel(pack_id="x", panel_id="main")  # same key
        self.registry.register_ui_panel(p1)
        with self.assertRaisesRegex(
            PluginLoadError, r"already registered"
        ):
            self.registry.register_ui_panel(p2)

    def test_same_panel_id_different_pack_id_ok(self):
        # Two packs can both expose a panel called "main" — they
        # mount at different paths.
        p1 = _StubUIPanel(pack_id="x", panel_id="main")
        p2 = _StubUIPanel(pack_id="y", panel_id="main")
        self.registry.register_ui_panel(p1)
        self.registry.register_ui_panel(p2)
        self.assertEqual(len(self.registry.ui_panels()), 2)

    def test_non_conforming_rejected(self):
        with self.assertRaisesRegex(
            PluginLoadError, r"does not satisfy.*UIPanel"
        ):
            self.registry.register_ui_panel(_NonConforming())  # type: ignore[arg-type]


# ─── Scorer slot ───────────────────────────────────────────────────


class ScorerRegistration(_RegistryFixture):

    def test_register_then_get(self):
        s = _StubScorer()
        self.registry.register_scorer(s)
        self.assertEqual(self.registry.scorers(), (s,))

    def test_duplicate_pack_id_rejected(self):
        # Conflict policy: two scorers in the same slot is operator
        # intervention, not silent precedence.
        s1 = _StubScorer(pack_id="rerank")
        s2 = _StubScorer(pack_id="rerank")
        self.registry.register_scorer(s1)
        with self.assertRaisesRegex(
            PluginLoadError, r"already registered.*unresolved.*conflict"
        ):
            self.registry.register_scorer(s2)

    def test_different_pack_ids_ok(self):
        s1 = _StubScorer(pack_id="rerank")
        s2 = _StubScorer(pack_id="hybrid")
        self.registry.register_scorer(s1)
        self.registry.register_scorer(s2)
        self.assertEqual(len(self.registry.scorers()), 2)


# ─── Diagnostics ───────────────────────────────────────────────────


class SlotCountsReflectsState(_RegistryFixture):

    def test_empty_registry(self):
        self.assertEqual(
            self.registry.slot_counts(),
            {"ontology": 0, "prompts": 0, "ui": 0, "scorers": 0},
        )

    def test_after_mixed_registrations(self):
        self.registry.register_ontology(_StubOntology())
        self.registry.register_prompts(_StubPrompts())
        self.registry.register_ui_panel(_StubUIPanel())
        self.registry.register_scorer(_StubScorer())
        self.assertEqual(
            self.registry.slot_counts(),
            {"ontology": 1, "prompts": 1, "ui": 1, "scorers": 1},
        )


class SingletonReplacementForTesting(unittest.TestCase):
    """Verifies the test-only override works without leaking across
    tests in the same module."""

    def test_replace_and_restore(self):
        original = get_registry()
        injected = PluginRegistry()
        _set_registry_for_testing(injected)
        try:
            self.assertIs(get_registry(), injected)
            self.assertIsNot(get_registry(), original)
        finally:
            _set_registry_for_testing(original)
        self.assertIs(get_registry(), original)


if __name__ == "__main__":
    unittest.main()
