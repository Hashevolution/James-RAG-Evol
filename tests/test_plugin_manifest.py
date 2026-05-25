"""PROJECT JAMES — Plugin manifest parser tests (PR-C3).

Covers ``core/plugins/manifest.py``:
  - ``parse_manifest`` happy path + every required-field failure mode
  - ``read_manifest`` filesystem cases (missing / invalid YAML)
  - ``check_semver`` accepts-and-rejects pairs
  - License enum + ``warns_at_load`` for ``proprietary``
  - Plugins block (single string vs list, unknown slot rejection,
    bad import-path shape rejection)

A regression here re-introduces the silent-fallback path the design
memo explicitly forbids.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

from core.plugins.errors import (  # noqa: E402
    PluginLoadError,
    PluginVersionError,
)
from core.plugins.manifest import (  # noqa: E402
    ALLOWED_LICENSES,
    KNOWN_SLOTS,
    LICENSES_WITH_WARNING,
    check_semver,
    parse_manifest,
    read_manifest,
)


def _minimum_blob(name: str = "general") -> dict:
    """Smallest valid manifest dict — every required field present."""
    return {
        "name": name,
        "version": "1.0.0",
        "james_api": ">=0.3,<0.4",
        "description": "Test pack",
        "author": "Hashevolution",
        "license": "MIT",
    }


class ParseManifestHappyPathTests(unittest.TestCase):

    def test_minimum_valid_manifest_parses(self):
        m = parse_manifest(_minimum_blob(), "general")
        self.assertEqual(m.name, "general")
        self.assertEqual(m.version, "1.0.0")
        self.assertEqual(m.license, "MIT")
        self.assertEqual(m.plugins, {})
        self.assertFalse(m.warns_at_load)

    def test_manifest_is_frozen_dataclass(self):
        # The Manifest is frozen so a loaded pack's contract cannot
        # drift at runtime. Verify the immutability is enforced.
        m = parse_manifest(_minimum_blob(), "general")
        with self.assertRaises(Exception):
            m.name = "other"  # type: ignore[misc]

    def test_plugins_single_string_value(self):
        blob = _minimum_blob()
        blob["plugins"] = {"ontology": "ontology:GeneralOntology"}
        m = parse_manifest(blob, "general")
        self.assertEqual(m.plugins["ontology"], "ontology:GeneralOntology")

    def test_plugins_list_value(self):
        blob = _minimum_blob()
        blob["plugins"] = {
            "ui": ["ui.search:SearchPanel", "ui.graph:GraphPanel"],
        }
        m = parse_manifest(blob, "general")
        self.assertEqual(
            m.plugins["ui"],
            ["ui.search:SearchPanel", "ui.graph:GraphPanel"],
        )

    def test_plugins_block_omitted_is_empty_dict(self):
        m = parse_manifest(_minimum_blob(), "general")
        self.assertEqual(m.plugins, {})

    def test_plugins_block_none_is_empty_dict(self):
        blob = _minimum_blob()
        blob["plugins"] = None
        m = parse_manifest(blob, "general")
        self.assertEqual(m.plugins, {})


class ParseManifestRequiredFieldFailures(unittest.TestCase):

    def test_missing_name_raises(self):
        blob = _minimum_blob()
        del blob["name"]
        with self.assertRaisesRegex(PluginLoadError, r"missing.*'name'"):
            parse_manifest(blob, "general")

    def test_missing_version_raises(self):
        blob = _minimum_blob()
        del blob["version"]
        with self.assertRaisesRegex(PluginLoadError, r"missing.*'version'"):
            parse_manifest(blob, "general")

    def test_missing_license_raises(self):
        blob = _minimum_blob()
        del blob["license"]
        with self.assertRaisesRegex(PluginLoadError, r"missing.*'license'"):
            parse_manifest(blob, "general")

    def test_empty_string_field_raises(self):
        blob = _minimum_blob()
        blob["author"] = "   "
        with self.assertRaisesRegex(
            PluginLoadError, r"must be a non-empty string"
        ):
            parse_manifest(blob, "general")

    def test_non_string_field_raises(self):
        blob = _minimum_blob()
        blob["version"] = 1.0  # number, not string
        with self.assertRaisesRegex(
            PluginLoadError, r"must be a non-empty string"
        ):
            parse_manifest(blob, "general")


class ManifestNameMustMatchDirectory(unittest.TestCase):

    def test_mismatch_is_loud_error(self):
        blob = _minimum_blob(name="legal")
        with self.assertRaisesRegex(
            PluginLoadError, r"name='legal'.*directory.*'general'"
        ):
            parse_manifest(blob, "general")


class ManifestVersionShape(unittest.TestCase):

    def test_invalid_semver_rejected(self):
        blob = _minimum_blob()
        blob["version"] = "not-a-version"
        with self.assertRaisesRegex(
            PluginLoadError, r"not a valid SemVer"
        ):
            parse_manifest(blob, "general")

    def test_invalid_james_api_specifier_rejected(self):
        blob = _minimum_blob()
        blob["james_api"] = "?not a specifier?"
        with self.assertRaisesRegex(
            PluginLoadError, r"not a valid SemVer specifier"
        ):
            parse_manifest(blob, "general")


class LicenseEnumTests(unittest.TestCase):

    def test_every_allowed_license_parses(self):
        for license_value in ALLOWED_LICENSES:
            with self.subTest(license=license_value):
                blob = _minimum_blob()
                blob["license"] = license_value
                m = parse_manifest(blob, "general")
                self.assertEqual(m.license, license_value)

    def test_unknown_license_rejected(self):
        blob = _minimum_blob()
        blob["license"] = "WTFPL"
        with self.assertRaisesRegex(
            PluginLoadError, r"must be one of"
        ):
            parse_manifest(blob, "general")

    def test_proprietary_warns_at_load(self):
        blob = _minimum_blob()
        blob["license"] = "proprietary"
        m = parse_manifest(blob, "general")
        self.assertTrue(m.warns_at_load)

    def test_mit_does_not_warn(self):
        m = parse_manifest(_minimum_blob(), "general")
        self.assertFalse(m.warns_at_load)

    def test_licenses_with_warning_is_subset_of_allowed(self):
        # Defensive: a future hand-edit of the constants could break
        # this contract — surface the inconsistency loudly.
        self.assertTrue(LICENSES_WITH_WARNING.issubset(ALLOWED_LICENSES))


class PluginsBlockValidation(unittest.TestCase):

    def test_unknown_slot_rejected(self):
        blob = _minimum_blob()
        blob["plugins"] = {"reranker": "x:Y"}  # not in KNOWN_SLOTS
        with self.assertRaisesRegex(
            PluginLoadError, r"not a known slot"
        ):
            parse_manifest(blob, "general")

    def test_bad_import_path_string_rejected(self):
        blob = _minimum_blob()
        blob["plugins"] = {"ontology": "missing_colon"}
        with self.assertRaisesRegex(
            PluginLoadError, r"'module:Class' form"
        ):
            parse_manifest(blob, "general")

    def test_bad_import_path_in_list_rejected(self):
        blob = _minimum_blob()
        blob["plugins"] = {"ui": ["ok:Panel", "bad_no_colon"]}
        with self.assertRaisesRegex(
            PluginLoadError, r"'module:Class' strings"
        ):
            parse_manifest(blob, "general")

    def test_non_dict_plugins_rejected(self):
        blob = _minimum_blob()
        blob["plugins"] = "not a dict"
        with self.assertRaisesRegex(
            PluginLoadError, r"'plugins' must be a mapping"
        ):
            parse_manifest(blob, "general")

    def test_known_slots_constant_is_what_loader_expects(self):
        # The four Protocol types in base.py + the four registry
        # methods in registry.py are slot-named the same way; KNOWN_SLOTS
        # is the single source of truth.
        self.assertEqual(
            KNOWN_SLOTS,
            frozenset({"ontology", "prompts", "ui", "scorers"}),
        )


class ReadManifestFilesystemCases(unittest.TestCase):

    def test_missing_file_raises_with_pack_name(self):
        with self.assertRaisesRegex(
            PluginLoadError, r"pack 'mypack'.*not found"
        ):
            read_manifest(Path("/no/such/pack.yaml"), "mypack")

    def test_invalid_yaml_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "pack.yaml"
            # Mismatched braces — guaranteed YAML parse error,
            # independent of indentation heuristics.
            p.write_text("{name: general, version: 1.0.0\n", encoding="utf-8")
            with self.assertRaisesRegex(
                PluginLoadError, r"not valid YAML"
            ):
                read_manifest(p, "general")

    def test_non_dict_top_level_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "pack.yaml"
            p.write_text("- just a list\n- of items\n", encoding="utf-8")
            with self.assertRaisesRegex(
                PluginLoadError, r"top-level must be a mapping"
            ):
                read_manifest(p, "general")

    def test_round_trip_minimum_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "pack.yaml"
            p.write_text(
                "name: general\n"
                "version: 1.0.0\n"
                "james_api: '>=0.3,<0.4'\n"
                "description: Test\n"
                "author: Hash\n"
                "license: MIT\n",
                encoding="utf-8",
            )
            m = read_manifest(p, "general")
            self.assertEqual(m.name, "general")
            self.assertEqual(m.license, "MIT")


class CheckSemverTests(unittest.TestCase):

    def test_in_range_passes(self):
        # No exception.
        check_semver("general", ">=0.3,<0.4", "0.3.5")
        check_semver("general", ">=0.3,<0.4", "0.3.0")
        check_semver("general", ">=0.3,<0.4", "0.3.99")

    def test_below_range_raises_version_error(self):
        with self.assertRaisesRegex(
            PluginVersionError, r"general.*'>=0.3,<0.4'.*'0.2.0'"
        ):
            check_semver("general", ">=0.3,<0.4", "0.2.0")

    def test_above_range_raises_version_error(self):
        with self.assertRaisesRegex(
            PluginVersionError, r"general.*'>=0.3,<0.4'.*'0.4.0'"
        ):
            check_semver("general", ">=0.3,<0.4", "0.4.0")

    def test_unparseable_core_version_raises_load_error(self):
        with self.assertRaisesRegex(
            PluginLoadError, r"core version.*not a valid SemVer"
        ):
            check_semver("general", ">=0.3,<0.4", "not-a-version")


if __name__ == "__main__":
    unittest.main()
