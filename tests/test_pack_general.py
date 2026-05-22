"""PROJECT JAMES — packs/general/ dogfood pack tests (PR-C5a).

Verifies the no-op overlay pack:
  - Manifest parses and validates
  - GeneralOntology satisfies the OntologyPack Protocol structurally
  - GeneralPrompts satisfies the PromptPack Protocol structurally
  - load_packs_from_env(env={"JAMES_PACKS": "general"}) succeeds
    against the real packs/general/ directory
  - Empty overlay contributes zero entities / relations / hierarchies
    and returns empty for every prompt mode / few-shot task

The pack is byte-identically neutral by design — a regression here
that suddenly registers entity types into the runtime is a contract
violation in v0.3 (PR-C5a explicitly defers the actual-extract work
to PR-C5b).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

from core.plugins.base import (  # noqa: E402
    KNOWN_MODES,
    OntologyPack,
    PromptPack,
)
from core.plugins.loader import load_packs_from_env  # noqa: E402
from core.plugins.manifest import read_manifest  # noqa: E402
from core.plugins.registry import PluginRegistry  # noqa: E402

from packs.general import GeneralOntology, GeneralPrompts  # noqa: E402


_PACK_DIR = Path(__file__).resolve().parent.parent / "packs" / "general"


class PackOnDiskTests(unittest.TestCase):
    """The pack is shipped in this repo; verify it exists and parses."""

    def test_pack_directory_exists(self):
        self.assertTrue(_PACK_DIR.is_dir(), f"packs/general/ missing at {_PACK_DIR}")

    def test_pack_yaml_exists_and_parses(self):
        manifest = read_manifest(_PACK_DIR / "pack.yaml", "general")
        self.assertEqual(manifest.name, "general")
        self.assertEqual(manifest.license, "MIT")
        # Slot mapping is exactly what __init__.py exports.
        self.assertEqual(manifest.plugins["ontology"], "ontology:GeneralOntology")
        self.assertEqual(manifest.plugins["prompts"], "prompts:GeneralPrompts")


class GeneralOntologyProtocolTests(unittest.TestCase):
    """GeneralOntology is a no-op overlay — empty everywhere."""

    def test_satisfies_protocol(self):
        # @runtime_checkable Protocols use structural isinstance —
        # missing or mistyped attributes fail here.
        self.assertIsInstance(GeneralOntology(), OntologyPack)

    def test_pack_id_is_general(self):
        self.assertEqual(GeneralOntology().pack_id, "general")

    def test_entity_types_is_empty_tuple(self):
        # Tuple, not list — the Protocol declares Tuple[str, ...] and
        # the cascade-resolution graph relies on hashable type.
        o = GeneralOntology()
        self.assertEqual(o.entity_types, ())
        self.assertIsInstance(o.entity_types, tuple)

    def test_relation_types_is_empty_tuple(self):
        o = GeneralOntology()
        self.assertEqual(o.relation_types, ())
        self.assertIsInstance(o.relation_types, tuple)

    def test_hierarchies_is_empty_dict(self):
        o = GeneralOntology()
        self.assertEqual(o.hierarchies, {})
        self.assertIsInstance(o.hierarchies, dict)


class GeneralPromptsProtocolTests(unittest.TestCase):
    """GeneralPrompts is a no-op overlay — empty everywhere."""

    def test_satisfies_protocol(self):
        self.assertIsInstance(GeneralPrompts(), PromptPack)

    def test_pack_id_is_general(self):
        self.assertEqual(GeneralPrompts().pack_id, "general")

    def test_system_prompt_returns_empty_for_every_known_mode(self):
        # Every built-in mode falls through to the existing default
        # prompt builder in core/reasoning/modes/. A regression that
        # makes any mode return non-empty is a v0.3 contract violation.
        p = GeneralPrompts()
        for mode in KNOWN_MODES:
            with self.subTest(mode=mode):
                self.assertEqual(p.system_prompt(mode), "")

    def test_system_prompt_returns_empty_for_unknown_mode(self):
        # Unknown mode (future JAMES adds a mode in a minor) must also
        # return "" — never raise on input.
        self.assertEqual(GeneralPrompts().system_prompt("future_mode"), "")

    def test_few_shot_returns_empty_list_for_arbitrary_task(self):
        p = GeneralPrompts()
        self.assertEqual(p.few_shot("any_task"), [])
        self.assertEqual(p.few_shot(""), [])


class LoaderEndToEndTests(unittest.TestCase):
    """The real packs/general/ loads through load_packs_from_env."""

    def test_loader_loads_general_with_explicit_env(self):
        registry = PluginRegistry()
        loaded = load_packs_from_env(
            env={"JAMES_PACKS": "general"},
            registry=registry,
        )
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].name, "general")

    def test_loader_loads_general_when_env_unset(self):
        # Unset (not empty) → defaults to DEFAULT_PACK="general".
        registry = PluginRegistry()
        loaded = load_packs_from_env(env={}, registry=registry)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].name, "general")

    def test_loaded_pack_registers_into_registry(self):
        # After load, the registry has one ontology and one prompt pack
        # bound (both no-op, but both isinstance-checked at registration).
        registry = PluginRegistry()
        load_packs_from_env(
            env={"JAMES_PACKS": "general"},
            registry=registry,
        )
        # registry must expose ontology + prompts slots — exact API
        # is exercised here so a registry refactor that loses one of
        # them is caught.
        self.assertEqual(len(registry.ontology_packs()), 1)
        self.assertEqual(len(registry.prompt_packs()), 1)
        self.assertEqual(registry.ontology_packs()[0].pack_id, "general")
        self.assertEqual(registry.prompt_packs()[0].pack_id, "general")
        # slot_counts diagnostic also exposes the populated state.
        counts = registry.slot_counts()
        self.assertEqual(counts["ontology"], 1)
        self.assertEqual(counts["prompts"], 1)
        self.assertEqual(counts["ui"], 0)
        self.assertEqual(counts["scorers"], 0)


if __name__ == "__main__":
    unittest.main()
