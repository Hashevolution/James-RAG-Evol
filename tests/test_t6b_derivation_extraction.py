"""v0.4.1 PR-T6.B — derivation extraction contract tests.

Pins ``extract_derivation_chain`` across both paths (operator-tagged
+ flag-gated LLM-inferred) plus the negative / edge cases.

Run:
  python -m unittest tests.test_t6b_derivation_extraction
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.lifecycle.derivation import (  # noqa: E402
    extract_derivation_chain,
)


# ---------------------------------------------------------------------------
# Operator-tagged path
# ---------------------------------------------------------------------------

class OperatorTaggedTests(unittest.TestCase):

    def test_valid_explicit_list_returned(self):
        """Caller pre-sets derived_from; module returns it as-is."""
        new_rel = {
            "id": "e_new",
            "target": "USA",
            "type": "BASED_IN",
            "derived_from": [
                {"base_fact_id": "e_base_a", "derivation": "transitive"},
                {"base_fact_id": "e_base_b", "derivation": "operator"},
            ],
        }
        result = extract_derivation_chain(new_rel)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["base_fact_id"], "e_base_a")
        self.assertEqual(result[0]["derivation"], "transitive")

    def test_missing_derivation_defaults_to_operator(self):
        """Caller passes a bare {base_fact_id} → module fills in
        ``derivation: "operator"`` so the schema validator passes."""
        new_rel = {
            "id": "e_new",
            "derived_from": [{"base_fact_id": "e_base_a"}],
        }
        result = extract_derivation_chain(new_rel)
        self.assertEqual(result[0]["derivation"], "operator")

    def test_invalid_operator_tagged_raises(self):
        """Malformed entry → ValueError (T6.A validator)."""
        new_rel = {
            "id": "e_new",
            "derived_from": [
                {"base_fact_id": "e_base_a", "derivation": "made-up"},
            ],
        }
        with self.assertRaisesRegex(ValueError, "derivation must be one of"):
            extract_derivation_chain(new_rel)

    def test_cycle_in_operator_tagged_raises(self):
        """Decision 3 LOCK — self-reference rejected when
        ``context_edges_by_id`` is provided."""
        new_rel = {
            "id": "e_self",
            "derived_from": [
                {"base_fact_id": "e_self", "derivation": "transitive"},
            ],
        }
        with self.assertRaisesRegex(ValueError, "derivation cycle"):
            extract_derivation_chain(
                new_rel,
                context_edges_by_id={"e_self": new_rel},
            )

    def test_empty_operator_tagged_list_falls_through(self):
        """An EMPTY operator-tagged list shouldn't preempt the LLM
        path — explicit empty = "no operator tag", fall through to
        the LLM check (which is OFF by default → returns [])."""
        new_rel = {"id": "e_new", "derived_from": []}
        result = extract_derivation_chain(new_rel)
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# LLM-inferred path — flag-gated
# ---------------------------------------------------------------------------

class LLMInferredPathTests(unittest.TestCase):

    def test_flag_off_returns_empty(self):
        """Default behavior — no flag, no LLM call."""
        new_rel = {"id": "e_new", "target": "X", "type": "RELATED_TO"}
        provider = MagicMock()
        # Explicit enable_llm=False overrides env to ensure the test
        # is independent of the CI runner's env state.
        result = extract_derivation_chain(
            new_rel, llm_provider=provider, enable_llm=False,
        )
        self.assertEqual(result, [])
        provider.assert_not_called()

    def test_flag_on_without_provider_returns_empty(self):
        """Flag ON but provider missing — return empty rather than
        crashing the ingestion."""
        new_rel = {"id": "e_new", "target": "X", "type": "RELATED_TO"}
        result = extract_derivation_chain(
            new_rel, enable_llm=True, llm_provider=None,
        )
        self.assertEqual(result, [])

    def test_flag_on_with_provider_called_and_returned(self):
        """The full LLM-inferred path: provider gets prompt +
        context summary, returns derivations, module validates +
        returns."""
        new_rel = {"id": "e_new", "target": "USA", "type": "BASED_IN"}
        ctx = {
            "e_base_a": {"id": "e_base_a", "target": "California",
                         "type": "BASED_IN"},
            "e_base_b": {"id": "e_base_b", "target": "USA",
                         "type": "PART_OF"},
        }

        def provider(prompt: str, summary):
            self.assertIn("BASED_IN", prompt)
            self.assertIn("California", prompt)
            return [
                {"base_fact_id": "e_base_a", "derivation": "transitive"},
                {"base_fact_id": "e_base_b"},   # derivation defaulted
            ]

        result = extract_derivation_chain(
            new_rel, context_edges_by_id=ctx,
            llm_provider=provider, enable_llm=True,
        )
        self.assertEqual(len(result), 2)
        # Missing derivation defaulted to "inferred" (LLM-inferred path).
        self.assertEqual(result[1]["derivation"], "inferred")
        self.assertEqual(result[1]["base_fact_id"], "e_base_b")

    def test_llm_provider_must_return_list(self):
        """Provider returning a non-list raises."""
        new_rel = {"id": "e_new"}
        with self.assertRaisesRegex(ValueError, "must return a list"):
            extract_derivation_chain(
                new_rel, llm_provider=lambda p, s: "not a list",
                enable_llm=True,
            )

    def test_llm_provider_entries_must_be_dicts(self):
        new_rel = {"id": "e_new"}
        with self.assertRaisesRegex(ValueError, "non-dict entry"):
            extract_derivation_chain(
                new_rel,
                llm_provider=lambda p, s: ["not a dict"],
                enable_llm=True,
            )

    def test_llm_provider_output_validated_against_schema(self):
        """T6.A validator fires on LLM output too — invalid
        derivation value → ValueError."""
        new_rel = {"id": "e_new"}
        bad = lambda p, s: [{"base_fact_id": "e_base_a",
                             "derivation": "made-up"}]  # noqa: E731
        with self.assertRaisesRegex(ValueError, "derivation must be one of"):
            extract_derivation_chain(
                new_rel, llm_provider=bad, enable_llm=True,
            )

    def test_env_flag_read_when_enable_llm_none(self):
        """When ``enable_llm`` is None, the module reads the env
        flag. Set + restore to keep the test isolated."""
        new_rel = {"id": "e_new"}
        provider = MagicMock(return_value=[])

        prior = os.environ.get("JAMES_T6_LLM_DERIVATION")
        try:
            os.environ["JAMES_T6_LLM_DERIVATION"] = "1"
            extract_derivation_chain(new_rel, llm_provider=provider)
            provider.assert_called_once()
        finally:
            if prior is None:
                os.environ.pop("JAMES_T6_LLM_DERIVATION", None)
            else:
                os.environ["JAMES_T6_LLM_DERIVATION"] = prior


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class EdgeCaseTests(unittest.TestCase):

    def test_non_dict_new_rel_raises(self):
        with self.assertRaisesRegex(ValueError, "must be a dict"):
            extract_derivation_chain("not a dict")  # type: ignore[arg-type]

    def test_minimal_new_rel_returns_empty(self):
        """Bare relation with no derived_from + no LLM → []."""
        result = extract_derivation_chain({"target": "X"})
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
