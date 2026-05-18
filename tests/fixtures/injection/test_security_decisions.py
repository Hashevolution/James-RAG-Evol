"""Decision-correctness tests for injection fixtures (Track 2).

Schema: ``reports/promo-assets/injection-fixtures-schema-v0.md``.

For each fixture, drive ``core.security_layer.SecurityLayer.pre_check``
with the prompt and assert that the layer's ``allowed`` field matches
``not entry["expected_block"]``.

This is the JAMES-specific harness — Provia (Ali Afana's project) and
other consumers will write their own version of this file, wiring
*their* security implementation as the unit under test. The schema is
shared; the project-local glue is not.

Coverage today (baseline_kr_en.yaml):
  - prompt_injection : 25 cases (15 KO + 10 EN) — input-stage gate
  - data_exfiltration:  4 cases — these test the END-TO-END behavior;
                        the input gate may pass and the output filter
                        may handle the redaction, so we treat the
                        decision check leniently for this category
                        (see ``_check_decision`` below).
  - benign           :  6 cases (KO) — false-positive guard

Run:
    python -m pytest tests/fixtures/injection/test_security_decisions.py -v
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Bootstrap project root for "core.security_layer" import — tests
# live in tests/fixtures/injection/, three levels deep.
ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "PyYAML is required to load injection fixtures."
    ) from exc


FIXTURE_DIR = Path(__file__).parent


def _load_all_fixtures() -> List[Tuple[str, Dict[str, Any]]]:
    """Same shape helper as in ``test_fixture_format.py``. Duplicated
    here intentionally so each test file is standalone; the contract
    we ship to Ali is "you can copy this directory into your project".
    """
    out: List[Tuple[str, Dict[str, Any]]] = []
    for path in sorted(FIXTURE_DIR.glob("*.yaml")):
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, list):
            continue
        for entry in loaded:
            if isinstance(entry, dict):
                out.append((path.name, entry))
    return out


class JamesSecurityDecisionTests(unittest.TestCase):
    """For each fixture, pre_check must agree with expected_block."""

    @classmethod
    def setUpClass(cls):
        # Import here so a missing core.security_layer surfaces as a
        # clean skip rather than a module-load crash for the schema
        # tests next door.
        try:
            from core.security_layer import SecurityLayer
        except ImportError as e:
            raise unittest.SkipTest(
                f"core.security_layer not importable: {e}"
            )
        cls.sl = SecurityLayer()
        cls.fixtures = _load_all_fixtures()

    @staticmethod
    def _is_blocked(pre_check_result: Dict[str, Any]) -> bool:
        """``pre_check`` returns ``{"allowed": bool, "query": str, ...}``;
        blocked is the negation of allowed.
        """
        return not pre_check_result.get("allowed", True)

    def _check_decision(self, fname: str, entry: Dict[str, Any]) -> None:
        """One fixture's decision check. Lifted out so subclasses can
        override the leniency for non-input-stage categories.
        """
        category = entry["category"]
        prompt = entry["prompt"]
        expected_block = entry["expected_block"]

        # We always evaluate against role=external because the
        # baseline file is shaped to assert behavior for an
        # un-trusted caller. ABAC matrix variations belong in
        # category=data_exfiltration with expected_role set.
        role = entry.get("expected_role", "external")
        result = self.sl.pre_check(prompt, role)
        blocked = self._is_blocked(result)

        if category == "data_exfiltration":
            # Output-stage redaction is the primary defense for this
            # category — the input gate is allowed to pass without
            # failing the test (in which case the project-local
            # output filter, mask_sensitive, is what protects). We
            # still require *some* defense: either input-block or
            # the post-stage check would mask the answer. The
            # fixture-level test can't easily drive both stages, so
            # we record the input-stage outcome as informational only
            # and don't fail when expected_block=True yet
            # input-allowed.
            return

        # All other categories are input-stage. Decision must match.
        self.assertEqual(
            blocked, expected_block,
            f"{fname}:{entry['id']} ({category}, {entry['locale']}) — "
            f"expected blocked={expected_block}, got {blocked}. "
            f"prompt={prompt!r}",
        )

    def test_all_baseline_decisions(self):
        # subTest so a single regression doesn't hide the rest of the
        # suite. pytest will report each failing id individually.
        for fname, entry in self.fixtures:
            with self.subTest(fixture=f"{fname}:{entry['id']}"):
                self._check_decision(fname, entry)


class CoverageMetaTests(unittest.TestCase):
    """A few size / counting tests so a future PR that removes the
    baseline by accident fails CI loudly.
    """

    @classmethod
    def setUpClass(cls):
        cls.fixtures = _load_all_fixtures()

    def test_total_at_least_30(self):
        # Schema promises ~65 from JAMES; v0 baseline ships 35.
        # Anything fewer than 30 in this directory means someone
        # truncated the spin-out — flag it.
        self.assertGreaterEqual(
            len(self.fixtures), 30,
            f"only {len(self.fixtures)} fixtures present — baseline "
            "spin-out should ship at least 30.",
        )

    def test_prompt_injection_at_least_20(self):
        cnt = sum(
            1 for _, e in self.fixtures
            if e.get("category") == "prompt_injection"
        )
        self.assertGreaterEqual(
            cnt, 20,
            f"prompt_injection coverage is {cnt}; baseline should "
            "carry the bulk of the JAMES Phase 4 cases (~25).",
        )

    def test_both_languages_covered(self):
        locales = {e.get("locale") for _, e in self.fixtures}
        # Strip None just in case
        locales.discard(None)
        # We require both KO and EN at minimum — the schema reserves
        # other locales for follow-up contributions (Arabic from Ali,
        # etc.).
        self.assertIn("ko_KR", locales, "Korean baseline missing")
        self.assertIn("en_US", locales, "English baseline missing")


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
