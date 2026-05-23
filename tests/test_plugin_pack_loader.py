"""PROJECT JAMES — Pack loader tests (PR-C3).

Covers ``core/plugins/loader.load_packs_from_env``:
  - Env parsing: unset → default, "" → error, comma-list → list
  - Path traversal probe: ``../something`` rejected
  - Missing pack directory → ``PluginLoadError``
  - Missing pack.yaml → ``PluginLoadError``
  - Successful happy-path load of a fixture pack with ontology + ui
  - SemVer mismatch → ``PluginVersionError``
  - Slot import + Protocol validation + registry population

Pack fixtures live in temp directories per test so the suite does not
depend on ``packs/general/`` existing yet (that's PR-C5).

These tests are NOT the same as ``test_plugin_loader.py``, which
covers the *reasoning-backend* loader from PR #326 (a different
env var, ``JAMES_PLUGINS``, and a different target — backends, not
the 4-type pack slots). Both layers coexist; see
``docs/design/v0.3-plugin-api.md`` §"Relationship to PR #326's
_load_plugins".
"""
from __future__ import annotations

import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

from core.plugins.errors import (  # noqa: E402
    PluginLoadError,
    PluginVersionError,
)
from core.plugins.loader import (  # noqa: E402
    DEFAULT_PACK,
    _parse_env,
    load_packs_from_env,
)
from core.plugins.registry import PluginRegistry  # noqa: E402


# ─── Env parsing ───────────────────────────────────────────────────


class ParseEnvSemantics(unittest.TestCase):

    def test_unset_returns_default_pack(self):
        self.assertEqual(_parse_env(None), [DEFAULT_PACK])

    def test_empty_string_is_error(self):
        with self.assertRaisesRegex(
            PluginLoadError, r"empty string.*explicitly asks for no packs"
        ):
            _parse_env("")

    def test_whitespace_only_is_error(self):
        with self.assertRaisesRegex(
            PluginLoadError, r"empty string"
        ):
            _parse_env("   ")

    def test_only_separators_is_error(self):
        with self.assertRaisesRegex(
            PluginLoadError, r"only separators"
        ):
            _parse_env(" , , ")

    def test_single_pack(self):
        self.assertEqual(_parse_env("general"), ["general"])

    def test_comma_list(self):
        self.assertEqual(_parse_env("general,legal"), ["general", "legal"])

    def test_whitespace_tolerated(self):
        self.assertEqual(
            _parse_env(" general , legal "),
            ["general", "legal"],
        )


# ─── Fixture pack helpers ──────────────────────────────────────────


_MINIMAL_PACK_YAML = textwrap.dedent("""\
    name: {name}
    version: 1.0.0
    james_api: '{james_api}'
    description: Test pack
    author: Hash
    license: MIT
""")


_ONTOLOGY_MODULE = textwrap.dedent("""\
    from typing import Dict, Tuple


    class GeneralOntology:
        pack_id = "{name}"
        entity_types: Tuple[str, ...] = ("test_entity",)
        relation_types: Tuple[str, ...] = ()
        hierarchies: Dict[str, Tuple[str, ...]] = {{}}
""")


def _make_pack(
    tmp_dir: Path,
    name: str = "general",
    james_api: str = ">=0.3,<0.4",
    plugins_block: str = "",
    extra_modules: dict | None = None,
) -> Path:
    """Build a packs/<name>/ directory with pack.yaml + optional code.

    Returns the parent ``packs/`` dir (the loader's expected root).
    """
    packs_root = tmp_dir / "packs"
    pack_dir = packs_root / name
    pack_dir.mkdir(parents=True)
    pack_yaml = _MINIMAL_PACK_YAML.format(name=name, james_api=james_api)
    if plugins_block:
        pack_yaml += "plugins:\n" + textwrap.indent(plugins_block, "  ")
    (pack_dir / "pack.yaml").write_text(pack_yaml, encoding="utf-8")

    for filename, source in (extra_modules or {}).items():
        (pack_dir / filename).write_text(source, encoding="utf-8")

    return packs_root


# ─── Loader tests ──────────────────────────────────────────────────


class _LoaderFixture(unittest.TestCase):
    """Each test gets a fresh temp packs root + isolated registry.

    Patches ``_PACKS_ROOT`` in the loader so the temp packs dir is
    treated as the project's packs root for the duration of the test.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self._tmp.name)
        self.registry = PluginRegistry()

    def tearDown(self):
        self._tmp.cleanup()

    def _load(
        self,
        env: dict,
        *,
        core_version: str = "0.3.0",
    ):
        """Run the loader with the temp packs root patched in."""
        packs_root = self.tmp_dir / "packs"
        with mock.patch("core.plugins.loader._PACKS_ROOT", packs_root):
            return load_packs_from_env(
                env=env,
                registry=self.registry,
                core_version=core_version,
            )


class LoaderHappyPath(_LoaderFixture):

    def test_default_pack_unset_env(self):
        _make_pack(self.tmp_dir, name="general")
        manifests = self._load(env={})
        self.assertEqual(len(manifests), 1)
        self.assertEqual(manifests[0].name, "general")

    def test_explicit_pack_via_env(self):
        _make_pack(self.tmp_dir, name="general")
        _make_pack(self.tmp_dir, name="legal")
        manifests = self._load(env={"JAMES_PACKS": "legal"})
        self.assertEqual(len(manifests), 1)
        self.assertEqual(manifests[0].name, "legal")

    def test_multi_pack_load_in_order(self):
        _make_pack(self.tmp_dir, name="general")
        _make_pack(self.tmp_dir, name="legal")
        manifests = self._load(env={"JAMES_PACKS": "general,legal"})
        self.assertEqual([m.name for m in manifests], ["general", "legal"])


class LoaderFailureModes(_LoaderFixture):

    def test_empty_packs_env_refused(self):
        _make_pack(self.tmp_dir, name="general")
        with self.assertRaisesRegex(
            PluginLoadError, r"empty string"
        ):
            self._load(env={"JAMES_PACKS": ""})

    def test_missing_pack_directory(self):
        # No packs dir created at all.
        with self.assertRaisesRegex(
            PluginLoadError, r"not found"
        ):
            self._load(env={"JAMES_PACKS": "general"})

    def test_path_traversal_rejected(self):
        # Even if the directory exists upstream, name with "/" must
        # not escape the packs root.
        _make_pack(self.tmp_dir, name="general")
        with self.assertRaisesRegex(
            PluginLoadError, r"escapes the packs root|not found"
        ):
            self._load(env={"JAMES_PACKS": "../etc"})

    def test_missing_pack_yaml(self):
        # Build the directory but no manifest file.
        packs_root = self.tmp_dir / "packs"
        (packs_root / "general").mkdir(parents=True)
        with self.assertRaisesRegex(
            PluginLoadError, r"pack.yaml not found"
        ):
            self._load(env={"JAMES_PACKS": "general"})

    def test_semver_mismatch_raises_version_error(self):
        _make_pack(self.tmp_dir, name="general", james_api=">=0.4,<0.5")
        with self.assertRaises(PluginVersionError):
            self._load(env={"JAMES_PACKS": "general"}, core_version="0.3.0")


class LoaderSlotIntegration(_LoaderFixture):
    """Wire the loader against a fixture pack that declares an
    ontology slot. Verifies the slot import path resolves, the
    Protocol check passes at register time, and the registry ends up
    populated."""

    def test_ontology_slot_loaded_and_registered(self):
        modules = {
            "ontology.py": _ONTOLOGY_MODULE.format(name="general"),
        }
        _make_pack(
            self.tmp_dir,
            name="general",
            plugins_block="ontology: ontology:GeneralOntology\n",
            extra_modules=modules,
        )
        self._load(env={"JAMES_PACKS": "general"})
        packs = self.registry.ontology_packs()
        self.assertEqual(len(packs), 1)
        self.assertEqual(packs[0].pack_id, "general")
        self.assertIn("test_entity", packs[0].entity_types)

    def test_bad_import_module_raises_load_error(self):
        # Plugins block points to a module that doesn't exist in the pack.
        _make_pack(
            self.tmp_dir,
            name="general",
            plugins_block="ontology: nope:Missing\n",
        )
        with self.assertRaisesRegex(
            PluginLoadError, r"cannot import module"
        ):
            self._load(env={"JAMES_PACKS": "general"})

    def test_bad_class_name_raises_load_error(self):
        # Module exists, but the class name in the manifest doesn't.
        modules = {
            "ontology.py": _ONTOLOGY_MODULE.format(name="general"),
        }
        _make_pack(
            self.tmp_dir,
            name="general",
            plugins_block="ontology: ontology:NotARealClass\n",
            extra_modules=modules,
        )
        with self.assertRaisesRegex(
            PluginLoadError, r"has no class"
        ):
            self._load(env={"JAMES_PACKS": "general"})

    def test_pack_with_zero_slots_loads_with_warning(self):
        # No plugins block at all — manifest still parses; loader
        # warns but does not raise. The registry stays empty.
        _make_pack(self.tmp_dir, name="general")
        self._load(env={"JAMES_PACKS": "general"})
        self.assertEqual(
            self.registry.slot_counts(),
            {"ontology": 0, "prompts": 0, "ui": 0, "scorers": 0},
        )


class LoaderEnvVarSeparation(unittest.TestCase):
    """The pack loader uses JAMES_PACKS; PR #326's reasoning-backend
    loader uses JAMES_PLUGINS. They must not collide."""

    def test_pack_loader_ignores_james_plugins(self):
        # If JAMES_PACKS is unset, the pack loader uses DEFAULT_PACK
        # regardless of JAMES_PLUGINS. The cross-layer env separation
        # is the design memo's stated resolution to Open Question 1.
        env_with_only_plugins = {"JAMES_PLUGINS": "some.backend.module"}
        # Driving the loader with no packs dir on disk verifies that
        # JAMES_PACKS=unset path is taken (would otherwise raise).
        with mock.patch(
            "core.plugins.loader._PACKS_ROOT", Path("/no/such/packs/")
        ):
            # Default pack tries to load; expect PluginLoadError
            # because the packs root doesn't exist — that confirms
            # the loader took the default-pack code path, not an
            # accidental JAMES_PLUGINS path.
            with self.assertRaises(PluginLoadError):
                load_packs_from_env(
                    env=env_with_only_plugins,
                    registry=PluginRegistry(),
                )


class LoaderModuleIsolation(_LoaderFixture):
    """Pin the per-pack module-namespace behavior introduced by the
    loader's switch to ``importlib.util.spec_from_file_location``.

    Before the switch, ``importlib.import_module("ontology")`` cached
    under the short name ``"ontology"`` in ``sys.modules``, so:

    1. Two packs that each shipped ``ontology.py`` saw the second one
       silently ignored (the first one's module returned from cache).
    2. A test that loaded the production ``packs/general/`` first and
       then a fixture pack of the same name found the production
       module returned in place of the fixture's.

    After the switch, the key is per-pack qualified (e.g.
    ``_james_pack__general__ontology``), so both concerns dissolve.
    """

    def test_two_packs_with_same_filename_register_distinctly(self):
        """Two packs each shipping ``ontology.py`` with different
        ``entity_types`` must both register, each with its own
        contents — not the first-loaded one twice."""
        modules_a = {
            "ontology.py": _ONTOLOGY_MODULE.format(name="alpha"),
        }
        _make_pack(
            self.tmp_dir,
            name="alpha",
            plugins_block="ontology: ontology:GeneralOntology\n",
            extra_modules=modules_a,
        )
        # Beta's ontology.py has the SAME filename but different
        # contents — entity_types diverges so the test can prove which
        # one each registered slot came from.
        beta_ontology = textwrap.dedent("""\
            from typing import Dict, Tuple


            class GeneralOntology:
                pack_id = "beta"
                entity_types: Tuple[str, ...] = ("beta_only_entity",)
                relation_types: Tuple[str, ...] = ()
                hierarchies: Dict[str, Tuple[str, ...]] = {}
        """)
        _make_pack(
            self.tmp_dir,
            name="beta",
            plugins_block="ontology: ontology:GeneralOntology\n",
            extra_modules={"ontology.py": beta_ontology},
        )

        self._load(env={"JAMES_PACKS": "alpha,beta"})

        packs = self.registry.ontology_packs()
        self.assertEqual(len(packs), 2)
        by_id = {p.pack_id: p for p in packs}
        self.assertEqual(set(by_id), {"alpha", "beta"})
        # Alpha kept the fixture-default "test_entity" from _ONTOLOGY_MODULE.
        self.assertIn("test_entity", by_id["alpha"].entity_types)
        # Beta kept its own "beta_only_entity" — would fail if the
        # loader's old sys.modules["ontology"] cache returned alpha's
        # module for beta's import.
        self.assertIn("beta_only_entity", by_id["beta"].entity_types)
        self.assertNotIn("test_entity", by_id["beta"].entity_types)

    def test_relaod_same_pack_picks_up_new_file_contents(self):
        """Reloading the same pack name against a different pack_dir
        (or the same pack_dir with different file content) must reflect
        the new content, not return the first-load cached module."""
        # First load: standard fixture ontology with "test_entity".
        modules_v1 = {
            "ontology.py": _ONTOLOGY_MODULE.format(name="general"),
        }
        _make_pack(
            self.tmp_dir,
            name="general",
            plugins_block="ontology: ontology:GeneralOntology\n",
            extra_modules=modules_v1,
        )
        self._load(env={"JAMES_PACKS": "general"})
        first_pack = self.registry.ontology_packs()[0]
        self.assertIn("test_entity", first_pack.entity_types)

        # Now rewrite the pack on disk and load into a *fresh* registry
        # (the loader is the unit under test, not registry idempotence).
        # Second load points at the same pack_dir but the ontology.py
        # now declares a different entity. The loader must re-exec the
        # file, not return the cached module object from the first load.
        replaced_ontology = textwrap.dedent("""\
            from typing import Dict, Tuple


            class GeneralOntology:
                pack_id = "general"
                entity_types: Tuple[str, ...] = ("post_reload_entity",)
                relation_types: Tuple[str, ...] = ()
                hierarchies: Dict[str, Tuple[str, ...]] = {}
        """)
        general_dir = self.tmp_dir / "packs" / "general"
        (general_dir / "ontology.py").write_text(replaced_ontology, encoding="utf-8")

        fresh_registry = PluginRegistry()
        packs_root = self.tmp_dir / "packs"
        with mock.patch("core.plugins.loader._PACKS_ROOT", packs_root):
            load_packs_from_env(
                env={"JAMES_PACKS": "general"},
                registry=fresh_registry,
                core_version="0.3.0",
            )
        second_pack = fresh_registry.ontology_packs()[0]
        self.assertIn("post_reload_entity", second_pack.entity_types)
        self.assertNotIn("test_entity", second_pack.entity_types)


if __name__ == "__main__":
    unittest.main()


# Mark unused imports as expected so the linter passes.
_ = os  # noqa: F841
