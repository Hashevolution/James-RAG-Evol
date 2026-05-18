"""Schema-validity tests for injection fixtures (Track 2, PR-O7 prep).

Schema: ``reports/promo-assets/injection-fixtures-schema-v0.md``.

These tests verify that every fixture in this directory conforms to
the v0 schema. They are intentionally portable — no JAMES imports
beyond ``yaml`` — so other consumer projects (Provia's auth middleware,
future contributors) can drop the same harness next to their fixture
files and get the same shape guarantee.

Decision-correctness (does ``SecurityLayer.pre_check`` agree with each
fixture's ``expected_block``?) lives in
``test_security_decisions.py`` — that one DOES import JAMES.

Run:
    python -m pytest tests/fixtures/injection/test_fixture_format.py -v
"""
from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "PyYAML is required to load injection fixtures. "
        "Install with: pip install pyyaml"
    ) from exc


FIXTURE_DIR = Path(__file__).parent

# Schema constants — kept in sync with
# reports/promo-assets/injection-fixtures-schema-v0.md.
ALLOWED_CATEGORIES = frozenset({
    "prompt_injection",
    "path_traversal",
    "unsafe_deserialization",
    "dialect_jailbreak",
    "direction_mark_confusion",
    "catalog_poisoning",
    "data_exfiltration",
    "risky_coding",
    "benign",
})

ALLOWED_SENSITIVITIES = frozenset({
    "public", "internal", "confidential", "secret",
})

ALLOWED_ROLES = frozenset({
    "admin", "manager", "employee", "external",
})

REQUIRED_FIELDS = frozenset({
    "id", "category", "prompt", "expected_block", "locale",
})


def _load_all_fixtures() -> List[Tuple[str, Dict[str, Any]]]:
    """Yield ``(filename, entry)`` for every fixture in the directory.

    The loader is intentionally tolerant of YAML files containing a
    single list at the top level — every fixture file in this
    directory is expected to follow that shape.
    """
    out: List[Tuple[str, Dict[str, Any]]] = []
    for path in sorted(FIXTURE_DIR.glob("*.yaml")):
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, list):
            raise AssertionError(
                f"{path.name}: top-level must be a YAML list of fixtures, "
                f"got {type(loaded).__name__}"
            )
        for entry in loaded:
            if not isinstance(entry, dict):
                raise AssertionError(
                    f"{path.name}: every list element must be a dict, "
                    f"got {type(entry).__name__}"
                )
            out.append((path.name, entry))
    return out


class FixtureSchemaTests(unittest.TestCase):
    """Per-fixture structural validation. Loaded via unittest's
    ``subTest`` so a single bad entry doesn't hide the rest.
    """

    @classmethod
    def setUpClass(cls):
        cls.fixtures = _load_all_fixtures()

    def test_at_least_one_fixture_file_present(self):
        self.assertGreater(
            len(self.fixtures), 0,
            "no fixture entries found in "
            f"{FIXTURE_DIR} — the directory must ship at least the "
            "JAMES baseline file (baseline_kr_en.yaml).",
        )

    def test_required_fields_present(self):
        for fname, entry in self.fixtures:
            with self.subTest(fixture=f"{fname}:{entry.get('id', '?')}"):
                missing = REQUIRED_FIELDS - set(entry.keys())
                self.assertFalse(
                    missing,
                    f"required fields missing: {sorted(missing)}",
                )

    def test_id_is_unique_across_all_files(self):
        seen: Dict[str, str] = {}
        for fname, entry in self.fixtures:
            fid = entry.get("id")
            if not isinstance(fid, str) or not fid:
                continue   # other test reports missing id
            self.assertNotIn(
                fid, seen,
                f"duplicate id {fid!r}: first in {seen.get(fid)}, "
                f"again in {fname}",
            )
            seen[fid] = fname

    def test_category_is_in_allowed_enum(self):
        for fname, entry in self.fixtures:
            with self.subTest(fixture=f"{fname}:{entry.get('id', '?')}"):
                cat = entry.get("category")
                self.assertIn(
                    cat, ALLOWED_CATEGORIES,
                    f"category {cat!r} not in schema enum: "
                    f"{sorted(ALLOWED_CATEGORIES)}",
                )

    def test_prompt_is_non_empty_string(self):
        for fname, entry in self.fixtures:
            with self.subTest(fixture=f"{fname}:{entry.get('id', '?')}"):
                p = entry.get("prompt")
                self.assertIsInstance(p, str)
                self.assertTrue(
                    p,
                    "prompt is empty — even attack fixtures must have a "
                    "non-empty payload",
                )

    def test_expected_block_is_bool(self):
        for fname, entry in self.fixtures:
            with self.subTest(fixture=f"{fname}:{entry.get('id', '?')}"):
                self.assertIsInstance(entry.get("expected_block"), bool)

    def test_benign_must_have_expected_block_false(self):
        for fname, entry in self.fixtures:
            if entry.get("category") != "benign":
                continue
            with self.subTest(fixture=f"{fname}:{entry.get('id', '?')}"):
                self.assertIs(
                    entry.get("expected_block"), False,
                    "benign category MUST have expected_block: false — "
                    "this is the false-positive guard contract.",
                )

    def test_locale_is_bcp47_shaped(self):
        # Permissive BCP-47 check — `ll_RR` or `ll_RR_dialect`. Not a
        # full validator (we don't enumerate every region code) but
        # catches "korean" / "english" / "kr" type mistakes.
        for fname, entry in self.fixtures:
            with self.subTest(fixture=f"{fname}:{entry.get('id', '?')}"):
                loc = entry.get("locale")
                self.assertIsInstance(loc, str)
                parts = loc.split("_")
                self.assertGreaterEqual(
                    len(parts), 2,
                    f"locale {loc!r} must be BCP-47 shape "
                    "(e.g. 'ko_KR', 'en_US', 'ar_PS')",
                )
                self.assertTrue(
                    len(parts[0]) == 2 and parts[0].islower(),
                    f"language subtag must be 2 lowercase chars, got {parts[0]!r}",
                )
                self.assertTrue(
                    len(parts[1]) == 2 and parts[1].isupper(),
                    f"region subtag must be 2 uppercase chars, got {parts[1]!r}",
                )

    def test_optional_sensitivity_in_enum(self):
        for fname, entry in self.fixtures:
            sv = entry.get("sensitivity")
            if sv is None:
                continue
            with self.subTest(fixture=f"{fname}:{entry.get('id', '?')}"):
                self.assertIn(
                    sv, ALLOWED_SENSITIVITIES,
                    f"sensitivity {sv!r} not in schema enum",
                )

    def test_optional_expected_role_in_enum(self):
        for fname, entry in self.fixtures:
            er = entry.get("expected_role")
            if er is None:
                continue
            with self.subTest(fixture=f"{fname}:{entry.get('id', '?')}"):
                self.assertIn(
                    er, ALLOWED_ROLES,
                    f"expected_role {er!r} not in schema enum",
                )

    def test_baseline_file_has_minimum_benign_coverage(self):
        """Schema requires ≥ 5 benign cases per locale file (false-positive
        guard). The baseline file ships KO benigns; future per-locale
        files (ar_ecommerce.yaml etc.) should ship their own ≥ 5.
        """
        per_file_benign_count: Dict[str, int] = {}
        for fname, entry in self.fixtures:
            if entry.get("category") == "benign":
                per_file_benign_count[fname] = per_file_benign_count.get(fname, 0) + 1

        for fname, count in per_file_benign_count.items():
            with self.subTest(fixture_file=fname):
                self.assertGreaterEqual(
                    count, 5,
                    f"{fname} ships {count} benign case(s); the schema "
                    f"requires ≥5 per file as the false-positive guard.",
                )

    def test_id_convention_starts_with_locale_short(self):
        """``<locale_short>_<category_short>_<NNN>`` per the schema."""
        for fname, entry in self.fixtures:
            with self.subTest(fixture=f"{fname}:{entry.get('id', '?')}"):
                fid = entry.get("id", "")
                parts = fid.split("_")
                self.assertGreaterEqual(
                    len(parts), 3,
                    f"id {fid!r} does not follow "
                    "<locale_short>_<category_short>_<NNN> convention",
                )
                # First segment should be a 2-3 char locale short.
                self.assertTrue(
                    2 <= len(parts[0]) <= 3 and parts[0].islower(),
                    f"id prefix {parts[0]!r} should be a 2-3 char "
                    "lowercase locale token (kr, en, ar, ja, ...)",
                )


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
