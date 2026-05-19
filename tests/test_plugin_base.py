"""Tests for ``core/plugins/base.py`` — Track C PR-C2.

Covers the 3-item test plan in ``docs/design/v0.3-plugin-api.md``
§"Test plan / For PR-C2":

  1. Each Protocol is ``@runtime_checkable`` and ``isinstance(obj, P)``
     works against a class that satisfies the surface.
  2. A minimal class implementing each Protocol satisfies it.
  3. A class missing one required field/method fails the isinstance
     check.

Plus a small set of sanity guards: PanelContext shape, errors module
re-exports, KNOWN_MODES coverage, ``__all__`` is intentional.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

from core.plugins import (  # noqa: E402
    KNOWN_MODES,
    OntologyPack,
    PanelContext,
    PluginLoadError,
    PluginVersionError,
    PromptPack,
    Scorer,
    UIPanel,
)


# ─── Minimal compliant implementations ─────────────────────────────


class _MiniOntology:
    pack_id = "mini_ontology"
    entity_types = ("contract",)
    relation_types = ("references",)
    hierarchies = {"contract": ("clause",)}


class _MiniPrompts:
    pack_id = "mini_prompts"

    def system_prompt(self, mode: str) -> str:
        return "" if mode not in KNOWN_MODES else f"prompt for {mode}"

    def few_shot(self, task):
        return []


class _MiniPanel:
    pack_id = "mini_panels"
    panel_id = "stats"

    def render(self, ctx) -> str:
        return f"<div>role={ctx.user_role}</div>"


class _MiniScorer:
    pack_id = "mini_scorer"

    def score(self, query: str, candidate: dict) -> float:
        return 0.5


# ─── Protocol satisfaction ─────────────────────────────────────────


class OntologyPackProtocolTests(unittest.TestCase):

    def test_minimal_impl_satisfies(self):
        self.assertIsInstance(_MiniOntology(), OntologyPack)

    def test_missing_field_fails(self):
        class _NoRelations:
            pack_id = "x"
            entity_types = ()
            # relation_types missing
            hierarchies = {}
        self.assertNotIsInstance(_NoRelations(), OntologyPack)

    def test_missing_pack_id_fails(self):
        class _NoId:
            entity_types = ()
            relation_types = ()
            hierarchies = {}
        self.assertNotIsInstance(_NoId(), OntologyPack)


class PromptPackProtocolTests(unittest.TestCase):

    def test_minimal_impl_satisfies(self):
        self.assertIsInstance(_MiniPrompts(), PromptPack)

    def test_unknown_mode_returns_empty(self):
        """Contract: unknown mode → graceful empty-string fallthrough.
        Pinned via the minimal impl above + the docstring guarantee.
        """
        p = _MiniPrompts()
        self.assertEqual(p.system_prompt("not_a_mode"), "")
        self.assertEqual(p.few_shot("anything"), [])

    def test_missing_system_prompt_fails(self):
        class _NoSys:
            pack_id = "x"

            def few_shot(self, task):
                return []
        self.assertNotIsInstance(_NoSys(), PromptPack)

    def test_missing_few_shot_fails(self):
        class _NoFew:
            pack_id = "x"

            def system_prompt(self, mode):
                return ""
        self.assertNotIsInstance(_NoFew(), PromptPack)


class UIPanelProtocolTests(unittest.TestCase):

    def test_minimal_impl_satisfies(self):
        self.assertIsInstance(_MiniPanel(), UIPanel)

    def test_missing_panel_id_fails(self):
        class _NoPid:
            pack_id = "x"

            def render(self, ctx):
                return ""
        self.assertNotIsInstance(_NoPid(), UIPanel)

    def test_render_can_return_empty(self):
        """Empty string is a legal return — the panel decided it has
        nothing to show for this user/locale.
        """
        class _Empty:
            pack_id = "x"
            panel_id = "p"

            def render(self, ctx):
                return ""
        self.assertIsInstance(_Empty(), UIPanel)
        self.assertEqual(
            _Empty().render(PanelContext(user_role="external")),
            "",
        )


class ScorerProtocolTests(unittest.TestCase):

    def test_minimal_impl_satisfies(self):
        self.assertIsInstance(_MiniScorer(), Scorer)

    def test_missing_score_fails(self):
        class _NoScore:
            pack_id = "x"
        self.assertNotIsInstance(_NoScore(), Scorer)


# ─── PanelContext shape ───────────────────────────────────────────


class PanelContextTests(unittest.TestCase):

    def test_required_user_role(self):
        ctx = PanelContext(user_role="admin")
        self.assertEqual(ctx.user_role, "admin")
        self.assertEqual(ctx.session_id, "")
        self.assertEqual(ctx.locale, "en")

    def test_optional_fields(self):
        ctx = PanelContext(
            user_role="external",
            session_id="s-1",
            locale="ko",
        )
        self.assertEqual(ctx.session_id, "s-1")
        self.assertEqual(ctx.locale, "ko")

    def test_slots_block_extra_attributes(self):
        """__slots__ on PanelContext keeps the surface narrow — a
        pack that tries to attach extra state on the context object
        fails fast rather than leaking pack state across requests.
        """
        ctx = PanelContext(user_role="admin")
        with self.assertRaises(AttributeError):
            ctx.malicious_state = "x"   # type: ignore[attr-defined]


# ─── KNOWN_MODES coverage ──────────────────────────────────────────


class KnownModesTests(unittest.TestCase):

    def test_includes_all_five_built_in_modes(self):
        # The five modes that core/reasoning/modes/ ships with.
        for mode in ("chat", "meta", "wiki_edit",
                     "self_evolve", "coding"):
            self.assertIn(mode, KNOWN_MODES)

    def test_is_tuple_not_list(self):
        # KNOWN_MODES is a closed enum — mutability would let a
        # pack add modes at import time, defeating the validator.
        self.assertIsInstance(KNOWN_MODES, tuple)


# ─── Errors ────────────────────────────────────────────────────────


class ErrorClassesTests(unittest.TestCase):

    def test_plugin_load_error_inherits_runtime_error(self):
        # The loader (PR-C3) catches RuntimeError at the startup
        # boundary — pin that PluginLoadError stays inside that net.
        self.assertTrue(issubclass(PluginLoadError, RuntimeError))

    def test_plugin_version_error_inherits_runtime_error(self):
        self.assertTrue(issubclass(PluginVersionError, RuntimeError))

    def test_errors_have_messages(self):
        # Sanity — raising with a message round-trips it.
        try:
            raise PluginLoadError("pack 'foo' not found")
        except PluginLoadError as e:
            self.assertIn("foo", str(e))


# ─── Package-level __all__ ─────────────────────────────────────────


class PackageExportsTests(unittest.TestCase):

    def test_all_4_protocols_in_all(self):
        import core.plugins as pkg
        for name in ("OntologyPack", "PromptPack", "UIPanel", "Scorer"):
            self.assertIn(name, pkg.__all__)

    def test_panel_context_and_known_modes_in_all(self):
        import core.plugins as pkg
        self.assertIn("PanelContext", pkg.__all__)
        self.assertIn("KNOWN_MODES", pkg.__all__)

    def test_errors_in_all(self):
        import core.plugins as pkg
        self.assertIn("PluginLoadError", pkg.__all__)
        self.assertIn("PluginVersionError", pkg.__all__)


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
