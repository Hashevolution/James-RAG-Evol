"""Schema-validity tests for injection fixtures (Track 2 + 2b).

Schema: ``reports/promo-assets/injection-fixtures-schema-v0.md``
(content is at v1 — backward-compatible refinements: normalization
invariant + ``expected_block_stage`` enum).

These tests verify that every fixture in this directory conforms to
the schema. They are intentionally portable — no JAMES imports beyond
``yaml`` + the stdlib ``unicodedata`` — so other consumer projects
(Provia's auth middleware, future contributors) can drop the same
harness next to their fixture files and get the same shape guarantee.

Decision-correctness (does ``SecurityLayer.pre_check`` agree with each
fixture's ``expected_block``?) lives in
``test_security_decisions.py`` — that one DOES import JAMES.

v1 enforcement (Track 2b):
  - ``test_expected_block_stage_in_enum`` — when the field is set,
    must be one of ``input`` / ``retrieval`` / ``output`` / ``any``.
  - ``test_prompt_is_unnormalized`` — fixtures containing direction
    marks must be stored byte-exact (NFKC normalization would
    otherwise silently strip the override character that the test
    is supposed to exercise).
  - ``test_schema_version_when_present_is_at_least_1`` — the
    ``schema_version`` field is optional; when set, must be >= 1.

Run:
    python -m pytest tests/fixtures/injection/test_fixture_format.py -v
"""
from __future__ import annotations

import unicodedata
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

# v1: where the block is expected to fire in a 3-stage security
# pipeline. ``any`` is the backward-compat default for fixtures
# written under v0 that don't set the field explicitly.
ALLOWED_BLOCK_STAGES = frozenset({
    "input", "retrieval", "output", "any",
})

# Bidi/RTL override characters that must NOT be silently stripped by
# Unicode normalization at any pipeline stage. From v1 schema.
DIRECTION_MARK_CHARS = (
    "‪",  # LRE — left-to-right embedding
    "‫",  # RLE — right-to-left embedding
    "‬",  # PDF — pop directional formatting
    "‭",  # LRO — left-to-right override
    "‮",  # RLO — right-to-left override
)

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


# ─── v1 schema enforcement (Track 2b) ─────────────────────────────

class SchemaV1EnforcementTests(unittest.TestCase):
    """v1 backward-compat refinements (PR #317):

      - ``expected_block_stage`` enum — optional; when set must be one
        of ``input`` / ``retrieval`` / ``output`` / ``any``.
      - Normalization invariant — fixtures containing direction marks
        must be byte-exact under NFKC (otherwise the test silently
        loses the character that matters).
      - ``schema_version`` field — optional; when present, must be >= 1.

    All three are backward-compat with v0 entries — fixtures predating
    v1 are still valid by these tests because the new fields are
    optional and the normalization invariant only fires on direction-
    mark-containing prompts.
    """

    @classmethod
    def setUpClass(cls):
        cls.fixtures = _load_all_fixtures()

    def test_expected_block_stage_in_enum_when_set(self):
        """When the optional field is set, the value must be one of
        the four allowed stage tokens.
        """
        for fname, entry in self.fixtures:
            stage = entry.get("expected_block_stage")
            if stage is None:
                continue   # field is optional
            with self.subTest(fixture=f"{fname}:{entry.get('id', '?')}"):
                self.assertIn(
                    stage, ALLOWED_BLOCK_STAGES,
                    f"expected_block_stage {stage!r} not in v1 enum "
                    f"{sorted(ALLOWED_BLOCK_STAGES)}",
                )

    def test_prompt_is_byte_exact_when_direction_marks_present(self):
        """Direction-mark-containing prompts must be stored byte-exact.
        Mirrors the enforcement snippet in the schema v1 doc — if a
        prompt normalizes under NFKC to a different byte sequence and
        the entry doesn't explicitly opt out via
        ``notes`` containing ``byte_drift_expected``, the fixture is
        silently weakened (the bidi override character that the test
        is exercising can disappear at normalization time).
        """
        for fname, entry in self.fixtures:
            prompt = entry.get("prompt", "")
            if not isinstance(prompt, str):
                continue   # other test reports type mismatch
            if not any(c in prompt for c in DIRECTION_MARK_CHARS):
                continue
            with self.subTest(fixture=f"{fname}:{entry.get('id', '?')}"):
                normalized = unicodedata.normalize("NFKC", prompt)
                if prompt == normalized:
                    continue   # invariant trivially holds
                notes = str(entry.get("notes") or "")
                self.assertIn(
                    "byte_drift_expected", notes,
                    f"prompt contains direction marks but NFKC "
                    f"normalization changes the bytes. Either rewrite "
                    f"the prompt to be NFKC-stable, or document the "
                    f"intentional drift by adding the token "
                    f"`byte_drift_expected` to the `notes` field.",
                )

    def test_schema_version_when_present_is_v1_or_greater(self):
        """The ``schema_version`` field is optional. If a fixture
        carries it, it must be an integer >= 1. Fixtures without the
        field implicitly resolve to v1 (the published schema is at
        v1 since PR #317).
        """
        for fname, entry in self.fixtures:
            v = entry.get("schema_version")
            if v is None:
                continue
            with self.subTest(fixture=f"{fname}:{entry.get('id', '?')}"):
                self.assertIsInstance(
                    v, int,
                    f"schema_version {v!r} must be an integer",
                )
                self.assertGreaterEqual(
                    v, 1,
                    f"schema_version {v!r} predates the v1 publication; "
                    "the field was introduced in v1.",
                )

    def test_data_exfiltration_stage_is_retrieval_when_set(self):
        """Per the v1 stage-mapping table, ``data_exfiltration``
        fixtures should map onto the ``retrieval`` stage (the ABAC
        gate). This is advisory — a fixture may legitimately set
        ``any`` if the project under test doesn't have a separate
        retrieval-stage gate. But if ``expected_block_stage`` IS set
        for data_exfiltration, it must be ``retrieval`` or ``any``
        (not ``input`` / ``output``).
        """
        for fname, entry in self.fixtures:
            if entry.get("category") != "data_exfiltration":
                continue
            stage = entry.get("expected_block_stage")
            if stage is None:
                continue
            with self.subTest(fixture=f"{fname}:{entry.get('id', '?')}"):
                self.assertIn(
                    stage, {"retrieval", "any"},
                    f"data_exfiltration fixture has "
                    f"expected_block_stage={stage!r}; per the v1 "
                    "stage-mapping table this category dies at the "
                    "ABAC gate (retrieval) or `any`.",
                )

    def test_catalog_poisoning_stage_is_output_when_set(self):
        """Companion contract to the data_exfiltration one. The
        v0 baseline doesn't ship catalog_poisoning yet (it's reserved
        for Ali's ar_ecommerce.yaml + future hardening), but the
        contract test must already be in place so the first
        catalog_poisoning fixture that does ship gets stage-checked
        correctly.
        """
        for fname, entry in self.fixtures:
            if entry.get("category") != "catalog_poisoning":
                continue
            stage = entry.get("expected_block_stage")
            if stage is None:
                continue
            with self.subTest(fixture=f"{fname}:{entry.get('id', '?')}"):
                self.assertIn(
                    stage, {"output", "any"},
                    f"catalog_poisoning fixture has "
                    f"expected_block_stage={stage!r}; per the v1 "
                    "stage-mapping table the poison is in the "
                    "catalog (legitimately passes input + retrieval), "
                    "the block fires at the output sanitizer.",
                )


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
