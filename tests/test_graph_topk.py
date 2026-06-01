"""Unit tests for α-7 graph_topk module.

Cover: top-K cap, score-descending order, tie-breaking by DFS visit
order, path tail extraction, path filtering preserves only surviving
entities' paths, idempotence, edge cases.
"""

from __future__ import annotations

import unittest

from core.graph_topk import DEFAULT_TOP_K, _path_tail_name, top_k_filter


class TestPathTailName(unittest.TestCase):
    """Path-tail extraction per `expand_dynamic`'s format."""

    def test_single_hop_path(self):
        path = "Alice -[KNOWS(w=1.0)]→ Bob"
        self.assertEqual(_path_tail_name(path), "Bob")

    def test_multi_hop_path(self):
        path = "Alice -[KNOWS(w=1.0)]→ Bob -[WORKS_AT(w=1.1)]→ Acme"
        self.assertEqual(_path_tail_name(path), "Acme")

    def test_empty_path(self):
        self.assertEqual(_path_tail_name(""), "")

    def test_path_with_korean_name(self):
        path = "OpenAI -[RESEARCHES(w=1.0)]→ 인공지능"
        self.assertEqual(_path_tail_name(path), "인공지능")

    def test_path_with_spaces_around_name(self):
        # Trailing whitespace from the format string should strip.
        path = "Alice -[KNOWS(w=1.0)]→  Bob  "
        self.assertEqual(_path_tail_name(path), "Bob")

    def test_path_without_arrow_returns_empty(self):
        # Malformed input — no arrow means we can't identify a tail.
        self.assertEqual(_path_tail_name("plain string"), "")


class TestTopKFilter(unittest.TestCase):
    """top_k_filter cap, sort, tie-break, path correspondence."""

    def _entity(self, name: str, score: float) -> dict:
        return {"name": name, "_dfs_score": score, "entity_type": "concept"}

    def test_passthrough_when_under_k(self):
        entities = [self._entity("A", 0.9), self._entity("B", 0.5)]
        paths = ["seed -[X]→ A", "seed -[Y]→ B"]
        kept_entities, kept_paths = top_k_filter(entities, paths, k=10)
        self.assertEqual(kept_entities, entities)
        self.assertEqual(kept_paths, paths)

    def test_caps_to_k_by_score_descending(self):
        entities = [
            self._entity("low1", 0.1),
            self._entity("mid",  0.5),
            self._entity("high", 0.9),
            self._entity("low2", 0.1),
        ]
        paths = []
        kept_entities, _ = top_k_filter(entities, paths, k=2)
        self.assertEqual(len(kept_entities), 2)
        # Highest scores survive.
        self.assertEqual({e["name"] for e in kept_entities}, {"high", "mid"})

    def test_tiebreak_by_dfs_visit_order(self):
        # Three entities tied at 0.5; visit order A → B → C → D (D higher).
        entities = [
            self._entity("A_first",  0.5),
            self._entity("B_second", 0.5),
            self._entity("C_third",  0.5),
            self._entity("D_high",   0.9),
        ]
        kept_entities, _ = top_k_filter(entities, [], k=3)
        # D_high + first two of the tied set in DFS order = A, B.
        names = [e["name"] for e in kept_entities]
        self.assertEqual(names[0], "D_high")
        self.assertIn("A_first", names)
        self.assertIn("B_second", names)
        self.assertNotIn("C_third", names)

    def test_paths_filtered_to_surviving_tails(self):
        entities = [
            self._entity("Alice", 0.9),
            self._entity("Bob",   0.5),
            self._entity("Eve",   0.1),  # Will be filtered.
        ]
        paths = [
            "seed -[KNOWS(w=1.0)]→ Alice",
            "seed -[KNOWS(w=1.0)]→ Bob",
            "seed -[KNOWS(w=1.0)]→ Eve",      # Should be dropped.
            "Alice -[WORKS_WITH(w=1.0)]→ Bob",  # Bob survives → kept.
        ]
        kept_entities, kept_paths = top_k_filter(entities, paths, k=2)
        self.assertEqual({e["name"] for e in kept_entities}, {"Alice", "Bob"})
        # Eve's path dropped; the other 3 surviving (Alice / Bob single
        # hop + Bob as tail of the Alice→Bob hop).
        self.assertEqual(len(kept_paths), 3)
        for p in kept_paths:
            tail = _path_tail_name(p)
            self.assertIn(tail, {"Alice", "Bob"})

    def test_idempotent_application(self):
        entities = [
            self._entity("a", 0.9),
            self._entity("b", 0.5),
            self._entity("c", 0.1),
            self._entity("d", 0.05),
        ]
        paths = ["seed -[X]→ a", "seed -[X]→ b", "seed -[X]→ c", "seed -[X]→ d"]
        once = top_k_filter(entities, paths, k=2)
        twice = top_k_filter(once[0], once[1], k=2)
        self.assertEqual([e["name"] for e in once[0]],
                         [e["name"] for e in twice[0]])
        self.assertEqual(once[1], twice[1])

    def test_k_zero_returns_empty(self):
        # Defensive — caller asked for nothing.
        kept_entities, kept_paths = top_k_filter(
            [self._entity("A", 0.9)], ["seed -[X]→ A"], k=0,
        )
        self.assertEqual(kept_entities, [])
        self.assertEqual(kept_paths, [])

    def test_missing_score_treated_as_zero(self):
        entities = [
            {"name": "no_score", "entity_type": "concept"},
            self._entity("scored", 0.5),
        ]
        kept_entities, _ = top_k_filter(entities, [], k=1)
        # The scored entity wins.
        self.assertEqual(kept_entities[0]["name"], "scored")

    def test_default_k_value(self):
        # Sanity: DEFAULT_TOP_K is 10 (matches build_graph_context_str's
        # downstream cap).
        self.assertEqual(DEFAULT_TOP_K, 10)


if __name__ == "__main__":
    unittest.main()
