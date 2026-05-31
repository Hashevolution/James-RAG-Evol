"""Contract — 4-step verification rule for `eval/qvt/oracle.py`.

The 4-step rule (memory `feedback_oracle_phrase_artifacts`, α-5
cycle 2026-05-31) requires that BEFORE concluding "JAMES failed",
the operator must:

  1. Check the suspicious axis value (0 / saturated).
  2. Read answer samples manually.
  3. Check the JAMES response keys the matcher inspects.
  4. Reconcile design intent vs matcher coverage.

The rule itself is a process. This file converts the lessons of
the cycle's three measurement-debt corrections (#618, #619, #623)
into hard contract invariants that fail loudly if a future PR
regresses the oracle into the broken state the rule was designed
to catch.

Three contract groups:

  - **Group A — sources credit** (lesson from #618): if a bench
    row has a `sources` field with valid filenames, `score_path_coverage`
    MUST credit them. Anyone who removes the sources branch
    re-creates the path_recall=0 saturation bug.

  - **Group B — canary refusals** (lesson from #619 + #623): a set
    of 10 obvious gemma4:e4b English refusal phrasings MUST be
    detected by `detect_abstention`. Anyone who shortens the
    phrase list to "save bytes" re-creates the 76% hallucination
    saturation bug.

  - **Group C — saturation sentinel** (lesson from the cycle in
    aggregate): a tiny mixed-truth fixture must produce an
    `abstention_f1` strictly between 0 and 1. Anyone whose change
    pushes the test-fixture F1 to 0 or 1 has broken the rule's
    deepest invariant (the oracle should never saturate on a
    fixture designed to exercise both classes).

Failure messages here intentionally point back at
`memory/feedback_oracle_phrase_artifacts.md` so the developer who
broke the contract reads the rule before "fixing" the test.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.qvt.oracle import (  # noqa: E402
    _ABSTENTION_PHRASES,
    _slug_for_match,
    detect_abstention,
    score_abstention_f1,
    score_path_coverage,
)


_4STEP_RULE_DOC = (
    "See memory/feedback_oracle_phrase_artifacts.md (4-step rule). "
    "Run the rule BEFORE concluding the oracle is correct."
)


# ---------------------------------------------------------------------------
# Group A — sources credit (lesson from #618)
# ---------------------------------------------------------------------------


class SourcesCreditContract(unittest.TestCase):
    """If JAMES emits `sources`, the path scorer MUST credit them.

    The α-5 cycle's `path_recall = 0.000` finding turned out to be
    bench.py + oracle ignoring `response.sources` (top-3 citation
    filenames). PR #618 fixed it by adding slug-normalised credit
    against the `sources` field. This test pins that fix so a future
    refactor cannot remove it silently.
    """

    def _bench(self, expected_titles, sources):
        return {
            "results": [
                {
                    "id": 1,
                    "sources": sources,
                    # intentionally no graph_paths_meta / path_metrics —
                    # forces the scorer to credit via sources or fail
                }
            ]
        }

    def _fixture(self, expected_titles):
        return {
            "queries": [
                {
                    "id": 1,
                    "expected_path": {"nodes": expected_titles},
                }
            ]
        }

    def test_sources_field_credited_when_filenames_match_titles(self):
        # MultiHop-RAG pattern: expected title is the prose title,
        # source filename is the multihop_<id>_<slug> form.
        fixture = self._fixture(
            ["The FTX trial is bigger than Sam Bankman-Fried"]
        )
        bench = self._bench(
            expected_titles=None,
            sources=["multihop_0001_the-FTX-trial-is-bigger-than-Sam-Bankman-Fried.txt"],
        )
        axis = score_path_coverage(bench, fixture)
        self.assertGreater(
            axis.mean_recall,
            0.0,
            msg=(
                "score_path_coverage returned 0 for a fixture where the "
                "`sources` field exactly matches the expected node title "
                "after slug normalisation. This regression re-creates the "
                f"α-5 #618 bug. {_4STEP_RULE_DOC}"
            ),
        )
        row = axis.per_query[0]
        self.assertEqual(
            row.via_sources,
            1,
            msg=("via_sources counter must increment when the citation "
                 "matches the expected title."),
        )

    def test_slug_normalisation_handles_multihop_prefix_and_extension(self):
        # Slug normaliser must strip both the multihop_<id>_ prefix and the
        # .txt extension. Without this, source filenames never match
        # expected article titles → systematic recall = 0.
        slug = _slug_for_match("multihop_0010_SBF-s-trial-starts-soon-but.txt")
        self.assertNotIn("multihop_", slug,
                         msg="slug normaliser must strip multihop_<id>_ prefix")
        self.assertNotIn(".txt", slug,
                         msg="slug normaliser must strip .txt extension")
        self.assertTrue(slug.startswith("sbf-s-trial"),
                        msg=f"unexpected slug shape: {slug!r}")

    def test_legacy_path_metrics_branch_still_works(self):
        # When there's no sources AND no graph_paths, but the bench row
        # carries pre-computed path_metrics (older bench JSONs), the scorer
        # should fall back to those rather than dropping to zero.
        bench = {
            "results": [
                {
                    "id": 1,
                    "path_metrics": {"hits": 2, "expected_count": 3, "path_recall": 0.6667},
                }
            ]
        }
        fixture = {"queries": []}  # legacy bench → empty fixture path
        axis = score_path_coverage(bench, fixture)
        self.assertAlmostEqual(axis.mean_recall, 0.6667, places=3)


# ---------------------------------------------------------------------------
# Group B — canary refusals (lesson from #619 + #623)
# ---------------------------------------------------------------------------


_CANARY_REFUSALS = (
    # The phrases that gemma4:e4b's grounding training emits on
    # null-truth queries. If any of these is removed from the phrase
    # list (or detect_abstention is changed in a way that misses them),
    # the abstention F1 collapses by ~0.3 on the canonical baseline.
    "Based on the provided sources, it is impossible to determine the answer.",
    "Insufficient data to answer the question from the provided sources.",
    "The first letter cannot be determined from the source material.",
    "The query cannot be answered with the available information.",
    "None of the provided sources contain information about this person.",
    "The identity of the CEO cannot be confirmed from the data.",
    "Insufficient information to determine the requested fact.",
    "The required entity cannot be identified in the source files.",
    # Korean canary — the original baseline phrases must still detect.
    "관련 정보가 없습니다.",
    "내부 자료에 없는 내용입니다.",
)

_CANARY_NON_REFUSALS = (
    # Partial-answer + disclaimer rows that must NOT be flagged as
    # refusals. These appear in truth=present queries; flagging them
    # creates FPs and pushes F1 back down.
    "The company is Amazon. However, specific revenue details are not "
    "in the source files.",
    "The CEO is Tim Cook. The provided sources do not include his start date.",
    "The first letter is M. The full state name is not directly named.",
)


class CanaryRefusalContract(unittest.TestCase):
    """detect_abstention must flag the canary refusals and not the partial-
    answer rows. Failure means someone broke the α-5 #619/#623 fix.
    """

    def test_every_canary_refusal_is_detected(self):
        for refusal in _CANARY_REFUSALS:
            with self.subTest(refusal=refusal[:60]):
                self.assertTrue(
                    detect_abstention(refusal),
                    msg=(
                        f"Canary refusal not detected: {refusal!r}. "
                        "This regression re-creates the α-5 #619/#623 "
                        f"hallucination-rate saturation bug. {_4STEP_RULE_DOC}"
                    ),
                )

    def test_partial_answer_rows_not_flagged(self):
        for partial in _CANARY_NON_REFUSALS:
            with self.subTest(partial=partial[:60]):
                self.assertFalse(
                    detect_abstention(partial),
                    msg=(
                        f"Partial-answer row falsely flagged as refusal: "
                        f"{partial!r}. Over-broad phrases (e.g. 'does not "
                        "contain' / 'is not available' without anchor) "
                        f"cause this. {_4STEP_RULE_DOC}"
                    ),
                )

    def test_phrase_list_minimum_size(self):
        # Defence in depth: if the phrase list shrinks below 25, someone
        # likely dropped phrases. Re-evaluate carefully.
        self.assertGreaterEqual(
            len(_ABSTENTION_PHRASES), 25,
            msg=(
                f"Abstention phrase list shrunk to {len(_ABSTENTION_PHRASES)} "
                "phrases. The α-5 cycle established a floor of "
                "≥ 25 phrases across Korean + English + grounding-trained "
                f"refusals. {_4STEP_RULE_DOC}"
            ),
        )


# ---------------------------------------------------------------------------
# Group C — saturation sentinel (lesson from the cycle in aggregate)
# ---------------------------------------------------------------------------


class SaturationSentinelContract(unittest.TestCase):
    """A mixed-truth fixture must produce abstention F1 strictly in (0, 1).

    The deepest lesson of α-5: an oracle that saturates at 0 or 1 on a
    fixture designed to exercise both classes is broken before any
    JAMES code is even touched. This sentinel test runs a small fixture
    through the canonical scorers and refuses to let either axis pin
    against either extreme.

    If this test fails, the 4-step rule says: do NOT change JAMES —
    the matcher is the problem.
    """

    def _mixed_fixture(self):
        return {
            "queries": [
                # 2 truth=present queries
                {"id": 1, "abstention_truth": "present"},
                {"id": 2, "abstention_truth": "present"},
                # 2 truth=absent queries
                {"id": 3, "abstention_truth": "absent"},
                {"id": 4, "abstention_truth": "absent"},
            ]
        }

    def _mixed_bench(self):
        return {
            "results": [
                # truth=present, system answers → TN
                {"id": 1, "answer": "The company is Amazon."},
                # truth=present, system over-abstains → FP
                {"id": 2, "answer": "The information needed is not available."},
                # truth=absent, system correctly abstains → TP
                {"id": 3,
                 "answer": "It is impossible to determine the requested fact."},
                # truth=absent, system hallucinates → FN
                {"id": 4, "answer": "The CEO is Steve Jobs."},
            ]
        }

    def test_abstention_f1_not_saturated_on_mixed_fixture(self):
        axis = score_abstention_f1(
            self._mixed_bench(),
            self._mixed_fixture(),
        )
        f1 = axis.f1
        self.assertGreater(
            f1, 0.0,
            msg=(
                "abstention_f1 saturated at 0 on a fixture with one TP and "
                "one FN. The oracle is no longer detecting any refusals. "
                f"{_4STEP_RULE_DOC}"
            ),
        )
        self.assertLess(
            f1, 1.0,
            msg=(
                "abstention_f1 saturated at 1 on a fixture deliberately "
                "containing one FP and one FN. The oracle is treating every "
                f"answer as a refusal. {_4STEP_RULE_DOC}"
            ),
        )


if __name__ == "__main__":
    unittest.main()
