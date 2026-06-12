"""v0.5 G3 — corpus-wide reconstruct_view_at tests.

Covers:

  * Equivalence — per-head reconstruction matches `reconstruct_view_at`
    on a single chain.
  * Order preservation — yields in the order the heads iterable
    produced them.
  * Lazy / streaming — generator semantics; consumers can stop early.
  * `limit` — respects the cap; default `None` yields all.
  * Skips non-dict entries silently (defensive against caller's
    iterator producing junk).
  * Empty / no-match — yields `(head_id, None)` for chain heads whose
    chain has no edge containing `t`.
  * Handles dangling chains (lookup returns None mid-walk).
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from core.lifecycle.supersede_chain import (
    reconstruct_corpus_view_at,
    reconstruct_view_at,
)


def _chain_head(head_id: str, vf: str, vt: str = None,
                superseded_by: str = None,
                mutation_type: str = "active") -> dict:
    """Build a chain-link edge dict for testing."""
    return {
        "id": head_id,
        "type": "RELATED_TO",
        "validity": {"from": vf, "to": vt},
        "status": {
            "active": superseded_by is None,
            "superseded_by": superseded_by,
            "superseded_at": vt if superseded_by else None,
        },
        "mutation_type": mutation_type,
        "sources": [{"doc_id": "doc_x", "weight": 0.9, "role": "primary",
                     "ts": vf, "valid_from": None, "valid_until": None}],
    }


class CorpusReconstructEquivalenceTests(unittest.TestCase):
    """Per-head outputs must match single-head reconstruct_view_at."""

    def setUp(self):
        # Two chain heads, each a single edge (no supersede).
        self.head_a = _chain_head("e_a", "2026-01-01T00:00:00+00:00")
        self.head_b = _chain_head("e_b", "2026-03-01T00:00:00+00:00")
        self.lookup = lambda eid: None  # No chain extensions

    def test_equivalence_for_each_head(self):
        t = datetime(2026, 6, 1, tzinfo=timezone.utc)
        per_head = {
            "e_a": reconstruct_view_at(self.head_a, self.lookup, t),
            "e_b": reconstruct_view_at(self.head_b, self.lookup, t),
        }
        corpus = dict(reconstruct_corpus_view_at(
            [self.head_a, self.head_b], self.lookup, t,
        ))
        self.assertEqual(corpus, per_head)


class CorpusReconstructOrderTests(unittest.TestCase):
    def test_output_order_matches_input_order(self):
        h1 = _chain_head("e_1", "2026-01-01T00:00:00+00:00")
        h2 = _chain_head("e_2", "2026-02-01T00:00:00+00:00")
        h3 = _chain_head("e_3", "2026-03-01T00:00:00+00:00")
        t = datetime(2026, 6, 1, tzinfo=timezone.utc)
        out = list(reconstruct_corpus_view_at(
            [h2, h3, h1], lookup=lambda _: None, t=t,
        ))
        self.assertEqual([head_id for head_id, _ in out],
                         ["e_2", "e_3", "e_1"])


class CorpusReconstructStreamingTests(unittest.TestCase):
    def test_generator_can_be_stopped_early(self):
        heads = [_chain_head(f"e_{i}", "2026-01-01T00:00:00+00:00")
                 for i in range(100)]
        t = datetime(2026, 6, 1, tzinfo=timezone.utc)
        gen = reconstruct_corpus_view_at(heads, lookup=lambda _: None, t=t)
        # Pull the first 3, then drop the generator.
        first_three = [next(gen) for _ in range(3)]
        self.assertEqual(len(first_three), 3)
        self.assertEqual([h for h, _ in first_three],
                         ["e_0", "e_1", "e_2"])

    def test_returns_generator_not_list(self):
        gen = reconstruct_corpus_view_at(
            [], lookup=lambda _: None,
            t=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        # Generator/iterator protocol: has __iter__ + __next__.
        self.assertTrue(hasattr(gen, "__iter__"))
        self.assertTrue(hasattr(gen, "__next__"))


class CorpusReconstructLimitTests(unittest.TestCase):
    def test_limit_caps_output(self):
        heads = [_chain_head(f"e_{i}", "2026-01-01T00:00:00+00:00")
                 for i in range(10)]
        t = datetime(2026, 6, 1, tzinfo=timezone.utc)
        out = list(reconstruct_corpus_view_at(
            heads, lookup=lambda _: None, t=t, limit=3,
        ))
        self.assertEqual(len(out), 3)

    def test_limit_none_yields_all(self):
        heads = [_chain_head(f"e_{i}", "2026-01-01T00:00:00+00:00")
                 for i in range(5)]
        t = datetime(2026, 6, 1, tzinfo=timezone.utc)
        out = list(reconstruct_corpus_view_at(
            heads, lookup=lambda _: None, t=t, limit=None,
        ))
        self.assertEqual(len(out), 5)

    def test_limit_zero_yields_nothing(self):
        heads = [_chain_head("e_a", "2026-01-01T00:00:00+00:00")]
        t = datetime(2026, 6, 1, tzinfo=timezone.utc)
        out = list(reconstruct_corpus_view_at(
            heads, lookup=lambda _: None, t=t, limit=0,
        ))
        self.assertEqual(out, [])

    def test_limit_larger_than_heads_yields_all(self):
        heads = [_chain_head(f"e_{i}", "2026-01-01T00:00:00+00:00")
                 for i in range(3)]
        t = datetime(2026, 6, 1, tzinfo=timezone.utc)
        out = list(reconstruct_corpus_view_at(
            heads, lookup=lambda _: None, t=t, limit=999,
        ))
        self.assertEqual(len(out), 3)


class CorpusReconstructRobustnessTests(unittest.TestCase):
    def test_non_dict_entries_silently_skipped(self):
        head = _chain_head("e_real", "2026-01-01T00:00:00+00:00")
        # The iterable produces some junk entries; the function
        # should skip them and continue with the real head.
        heads = ["not a dict", None, head, 42]
        t = datetime(2026, 6, 1, tzinfo=timezone.utc)
        out = list(reconstruct_corpus_view_at(
            heads, lookup=lambda _: None, t=t,
        ))
        head_ids = [h for h, _ in out]
        self.assertEqual(head_ids, ["e_real"])

    def test_no_match_yields_none(self):
        # Head's validity starts AFTER t → no chain edge matches.
        head = _chain_head("e_future",
                           vf="2027-01-01T00:00:00+00:00")
        t = datetime(2026, 6, 1, tzinfo=timezone.utc)
        out = list(reconstruct_corpus_view_at(
            [head], lookup=lambda _: None, t=t,
        ))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0][0], "e_future")
        self.assertIsNone(out[0][1])

    def test_dangling_chain_yields_partial(self):
        # Head points at a missing chain link via supersede; lookup
        # returns None mid-walk. The chain ends at the head dict;
        # reconstruct_view_at returns the head when its validity
        # window contains t.
        head = _chain_head(
            "e_dangling",
            vf="2026-01-01T00:00:00+00:00",
            superseded_by="e_missing",
            mutation_type="superseded",
        )
        # Force the head's validity to extend through t — verify
        # that supersede→dangling still returns the head edge.
        head["validity"]["to"] = "2027-01-01T00:00:00+00:00"
        t = datetime(2026, 6, 1, tzinfo=timezone.utc)
        out = list(reconstruct_corpus_view_at(
            [head], lookup=lambda _: None, t=t,
        ))
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0][0], "e_dangling")
        self.assertIs(out[0][1], head)

    def test_empty_heads_yields_empty(self):
        out = list(reconstruct_corpus_view_at(
            [], lookup=lambda _: None,
            t=datetime(2026, 6, 1, tzinfo=timezone.utc),
        ))
        self.assertEqual(out, [])


if __name__ == "__main__":
    unittest.main()
