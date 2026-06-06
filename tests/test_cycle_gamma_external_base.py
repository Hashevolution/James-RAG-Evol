"""Cycle γ Phase A.0 — ``eval.external.base`` contract tests.

Pins the abstract-base / unified-schema invariants every Phase A.1+
loader will inherit:

  * ``ExternalQuery`` is frozen + serialises to the bench JSON shape
    (``to_bench_row``) the existing scoring helpers consume.
  * ``ExternalBenchFixture`` is genuinely abstract — the bare class
    cannot be instantiated, and ``benchmark_id`` + ``iter_queries``
    are required overrides.
  * ``take_sample`` semantics: ``None`` → full split, positive int →
    front slice, negative / non-int → ``ValueError``.
  * ``validate_queries`` catches benchmark-id mismatch + empty id +
    duplicate id.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ExternalQuerySchemaTests(unittest.TestCase):
    """Schema is frozen + projects to the bench dict shape."""

    def test_is_frozen(self):
        from eval.external import ExternalQuery
        q = ExternalQuery(
            id="rgb-001", benchmark="rgb",
            question="Q?", context=("ctx",), gold_answer="A",
        )
        with self.assertRaises(Exception):
            q.id = "mutated"   # type: ignore[misc]

    def test_to_bench_row_round_trip(self):
        from eval.external import ExternalQuery
        q = ExternalQuery(
            id="rgb-001", benchmark="rgb",
            question="Who is X?",
            context=("para A", "para B"),
            gold_answer="X",
            metadata={"aliases": ["x", "the X"]},
        )
        row = q.to_bench_row()
        # Required JAMES bench JSON columns:
        self.assertEqual(row["id"],   "rgb-001")
        self.assertEqual(row["benchmark"], "rgb")
        self.assertEqual(row["question"], "Who is X?")
        # `text` alias for compatibility with multihop_terse_run.py
        # which keys on q["text"]:
        self.assertEqual(row["text"], row["question"])
        self.assertEqual(row["context"], ["para A", "para B"])
        self.assertEqual(row["gold"], "X")
        self.assertEqual(row["metadata"], {"aliases": ["x", "the X"]})

    def test_metadata_defaults_to_empty_dict(self):
        from eval.external import ExternalQuery
        q = ExternalQuery(
            id="x", benchmark="rgb",
            question="Q?", context=(), gold_answer="A",
        )
        # Distinct dataclass instances must NOT share the same default
        # dict (classic mutable-default trap).
        q2 = ExternalQuery(
            id="y", benchmark="rgb",
            question="Q2?", context=(), gold_answer="B",
        )
        self.assertEqual(q.metadata, {})
        self.assertEqual(q2.metadata, {})
        self.assertIsNot(q.metadata, q2.metadata)

    def test_context_is_a_tuple(self):
        """The dataclass declares ``context: Tuple[str, ...]`` so a
        loader emitting a list will lock down to a tuple at the
        constructor; pinning the type explicitly here protects against
        a future loader relaxing it to a list (which would break
        hashability for caching)."""
        from eval.external import ExternalQuery
        q = ExternalQuery(
            id="x", benchmark="rgb",
            question="?", context=("a", "b"), gold_answer="c",
        )
        self.assertIsInstance(q.context, tuple)


class ExternalBenchFixtureContractTests(unittest.TestCase):
    """The abstract base enforces its contract."""

    def test_cannot_instantiate_abstract_base(self):
        from eval.external import ExternalBenchFixture
        with self.assertRaises(TypeError):
            ExternalBenchFixture()   # type: ignore[abstract]

    def test_subclass_without_overrides_still_abstract(self):
        from eval.external import ExternalBenchFixture

        class Half(ExternalBenchFixture):
            # Only one override — still abstract.
            @property
            def benchmark_id(self) -> str:
                return "x"

        with self.assertRaises(TypeError):
            Half()   # type: ignore[abstract]

    def test_concrete_subclass_instantiable(self):
        from eval.external import ExternalBenchFixture, ExternalQuery

        class Tiny(ExternalBenchFixture):
            @property
            def benchmark_id(self) -> str:
                return "tiny"

            def iter_queries(self, *, split="dev", n_samples=None):
                qs = [ExternalQuery(
                    id="tiny-1", benchmark="tiny",
                    question="?", context=(), gold_answer="a",
                )]
                return self.take_sample(qs, n_samples)

        t = Tiny()
        self.assertEqual(t.benchmark_id, "tiny")
        out = t.iter_queries()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].id, "tiny-1")


class TakeSampleTests(unittest.TestCase):
    """``take_sample`` semantics are uniform across all loaders."""

    def _make(self):
        from eval.external import ExternalBenchFixture, ExternalQuery

        class L(ExternalBenchFixture):
            @property
            def benchmark_id(self) -> str:
                return "L"

            def iter_queries(self, *, split="dev", n_samples=None):
                qs = [ExternalQuery(id=f"L-{i}", benchmark="L",
                                    question="?", context=(),
                                    gold_answer="a")
                      for i in range(5)]
                return self.take_sample(qs, n_samples)
        return L()

    def test_none_returns_full_split(self):
        loader = self._make()
        out = loader.iter_queries(n_samples=None)
        self.assertEqual(len(out), 5)

    def test_zero_returns_empty(self):
        loader = self._make()
        out = loader.iter_queries(n_samples=0)
        self.assertEqual(out, [])

    def test_positive_n_returns_front_slice(self):
        loader = self._make()
        out = loader.iter_queries(n_samples=3)
        self.assertEqual([q.id for q in out],
                         ["L-0", "L-1", "L-2"])

    def test_n_larger_than_split_returns_whole_split(self):
        loader = self._make()
        out = loader.iter_queries(n_samples=100)
        self.assertEqual(len(out), 5)

    def test_negative_raises(self):
        loader = self._make()
        with self.assertRaises(ValueError):
            loader.iter_queries(n_samples=-1)

    def test_non_int_raises(self):
        loader = self._make()
        with self.assertRaises(ValueError):
            loader.iter_queries(n_samples="3")   # type: ignore[arg-type]


class ValidateQueriesTests(unittest.TestCase):
    """``validate_queries`` catches loader misconfiguration early."""

    def _make_loader(self, bid="X"):
        from eval.external import ExternalBenchFixture

        class L(ExternalBenchFixture):
            @property
            def benchmark_id(self) -> str:
                return bid

            def iter_queries(self, *, split="dev", n_samples=None):
                return []
        return L()

    def test_wrong_benchmark_id_raises(self):
        from eval.external import ExternalQuery
        loader = self._make_loader(bid="X")
        bad = [ExternalQuery(id="X-1", benchmark="OTHER",
                             question="?", context=(), gold_answer="a")]
        with self.assertRaises(ValueError):
            loader.validate_queries(bad)

    def test_empty_id_raises(self):
        from eval.external import ExternalQuery
        loader = self._make_loader(bid="X")
        bad = [ExternalQuery(id="", benchmark="X",
                             question="?", context=(), gold_answer="a")]
        with self.assertRaises(ValueError):
            loader.validate_queries(bad)

    def test_duplicate_id_raises(self):
        from eval.external import ExternalQuery
        loader = self._make_loader(bid="X")
        dup = [
            ExternalQuery(id="X-1", benchmark="X", question="?",
                          context=(), gold_answer="a"),
            ExternalQuery(id="X-1", benchmark="X", question="?",
                          context=(), gold_answer="b"),
        ]
        with self.assertRaises(ValueError):
            loader.validate_queries(dup)

    def test_valid_batch_passes_silently(self):
        from eval.external import ExternalQuery
        loader = self._make_loader(bid="X")
        ok = [
            ExternalQuery(id="X-1", benchmark="X", question="?",
                          context=(), gold_answer="a"),
            ExternalQuery(id="X-2", benchmark="X", question="??",
                          context=(), gold_answer="b"),
        ]
        # Returns None — silent pass.
        self.assertIsNone(loader.validate_queries(ok))


if __name__ == "__main__":
    unittest.main()
