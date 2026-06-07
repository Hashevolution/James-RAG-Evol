"""Cycle γ Phase A.5 — unified runner contract tests.

Pins:
  * build_loader dispatch covers all 4 SUPPORTED_BENCHES.
  * build_scorer dispatch matches the loader benchmark_id.
  * StubProducer integration: the runner threads queries through
    a producer and into the scorer without touching an LLM.
  * Producer-raises errors do NOT kill the run; they surface as
    one row per failure with status=error.
  * Loader/scorer benchmark-id mismatch is caught before producer
    work starts.
  * Result dict shape is stable + JSON-serialisable.
  * write_result is atomic (final file appears all at once).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ─── Helpers ──────────────────────────────────────────────────────


def _write_rgb_fixture(tmp: Path) -> Path:
    """Write a tiny synthetic RGB fixture so RGBLoader can read it
    without hitting the network."""
    cache = tmp / "rgb"
    cache.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "id":       1,
            "query":    "What is the capital of France?",
            "answer":   "Paris",
            "positive": ["Paris is the capital of France."],
            "negative": [],
        },
        {
            "id":       2,
            "query":    "What is the population of Atlantis?",
            "answer":   "[Insufficient Information]",
            "positive": [],
            "negative": ["Atlantis is a mythical city."],
        },
    ]
    (cache / "en.json").write_text(json.dumps(rows), encoding="utf-8")
    return cache


def _write_2wiki_fixture(tmp: Path) -> Path:
    """Write a tiny synthetic 2WikiMultiHopQA fixture so WikiMultiLoader
    can read it without hitting the network."""
    cache = tmp / "2wiki"
    cache.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "_id":      "w1",
            "question": "Who composed Symphony X?",
            "context":  [["Title A", ["s0", "s1"]]],
            "supporting_facts": [["Title A", 0]],
            "answer":   "Beethoven",
            "type":     "comparison",
        },
        {
            "_id":      "w2",
            "question": "Who painted Painting Y?",
            "context":  [["Title B", ["s0"]]],
            "supporting_facts": [["Title B", 0]],
            "answer":   "Van Gogh",
            "type":     "inference",
        },
    ]
    (cache / "dev.json").write_text(json.dumps(rows), encoding="utf-8")
    return cache


# ─── Dispatch tests ────────────────────────────────────────────────


class BuildLoaderTests(unittest.TestCase):
    def test_rgb_dispatch(self):
        from eval.external.runner import build_loader
        from eval.external.rgb_loader import RGBLoader
        loader = build_loader("rgb", variant="en")
        self.assertIsInstance(loader, RGBLoader)
        self.assertEqual(loader.benchmark_id, "rgb-en")

    def test_alce_dispatch(self):
        from eval.external.runner import build_loader
        from eval.external.alce_loader import ALCELoader
        loader = build_loader("alce", variant="asqa")
        self.assertIsInstance(loader, ALCELoader)
        self.assertEqual(loader.benchmark_id, "alce-asqa")

    def test_musique_dispatch(self):
        from eval.external.runner import build_loader
        from eval.external.musique_loader import MuSiQueLoader
        loader = build_loader("musique", variant="ans", split="dev")
        self.assertIsInstance(loader, MuSiQueLoader)
        self.assertEqual(loader.benchmark_id, "musique-ans")

    def test_2wiki_dispatch(self):
        from eval.external.runner import build_loader
        from eval.external.wikimulti_loader import WikiMultiLoader
        loader = build_loader("2wiki", split="dev")
        self.assertIsInstance(loader, WikiMultiLoader)
        self.assertEqual(loader.benchmark_id, "2wiki")

    def test_unknown_bench_raises(self):
        from eval.external.runner import build_loader
        with self.assertRaises(ValueError):
            build_loader("bogus")


class BuildScorerTests(unittest.TestCase):
    def test_rgb_scorer_dispatch(self):
        from eval.external.runner import build_scorer
        from eval.external.rgb_scorer import RGBScorer
        s = build_scorer("rgb", variant="en")
        self.assertIsInstance(s, RGBScorer)
        self.assertEqual(s.benchmark_id, "rgb-en")

    def test_alce_scorer_dispatch_with_verifier(self):
        from eval.external.runner import build_scorer
        from eval.external.alce_scorer import (
            ALCEScorer, StringContainmentVerifier,
        )
        verifier = StringContainmentVerifier(min_overlap=0.7)
        s = build_scorer("alce", variant="asqa", verifier=verifier)
        self.assertIsInstance(s, ALCEScorer)
        # Custom verifier honoured.
        self.assertIs(s.verifier, verifier)

    def test_musique_scorer_dispatch(self):
        from eval.external.runner import build_scorer
        from eval.external.musique_scorer import MuSiQueScorer
        s = build_scorer("musique", variant="ans")
        self.assertIsInstance(s, MuSiQueScorer)
        self.assertEqual(s.benchmark_id, "musique-ans")

    def test_2wiki_scorer_dispatch(self):
        from eval.external.runner import build_scorer
        from eval.external.wikimulti_scorer import WikiMultiScorer
        s = build_scorer("2wiki")
        self.assertIsInstance(s, WikiMultiScorer)
        self.assertEqual(s.benchmark_id, "2wiki")

    def test_unknown_bench_raises(self):
        from eval.external.runner import build_scorer
        with self.assertRaises(ValueError):
            build_scorer("bogus")


# ─── StubProducer + run_external_bench end-to-end ──────────────────


class StubProducerTests(unittest.TestCase):
    def test_stub_requires_callable(self):
        from eval.external.runner import StubProducer
        with self.assertRaises(TypeError):
            StubProducer("not callable")

    def test_stub_must_return_dict(self):
        from eval.external.runner import StubProducer
        from eval.external import ExternalQuery
        sp = StubProducer(lambda q: "not a dict")
        with self.assertRaises(TypeError):
            sp.produce(ExternalQuery(
                id="x", benchmark="rgb-en", question="?",
                context=(), gold_answer="",
            ))


class EndToEndStubRunTests(unittest.TestCase):
    """The big one: drive a real loader + real scorer through a
    StubProducer that answers from the fixture's gold so the scorer
    has something concrete to grade."""

    def test_rgb_perfect_stub_yields_one(self):
        from eval.external.runner import (
            StubProducer, build_loader, build_scorer,
            run_external_bench,
        )
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cache = _write_rgb_fixture(tmp)
            loader = build_loader("rgb", variant="en",
                                   cache_dir=cache,
                                   allow_download=False)
            scorer = build_scorer("rgb", variant="en")

            # Answer with the gold so RGB's negative-rejection
            # F1 axis can both score the positive case and the
            # abstention case.
            def answer(q):
                return {"answer": q.gold_answer}
            sp = StubProducer(answer)

            result = run_external_bench(
                loader=loader, scorer=scorer, producer=sp,
            )
            self.assertEqual(result["benchmark"], "rgb-en")
            self.assertEqual(result["n_queries"], 2)
            self.assertEqual(result["n_rows"], 2)
            self.assertEqual(result["n_errors"], 0)
            self.assertEqual(result["producer"], "stub")
            self.assertIn("axes", result)
            self.assertIn("rows", result)
            self.assertIn("started_at", result)
            self.assertIn("elapsed_s", result)
            # Result must be JSON-serialisable end-to-end.
            self.assertIsInstance(json.dumps(result), str)

    def test_2wiki_perfect_stub_emits_em_f1(self):
        from eval.external.runner import (
            StubProducer, build_loader, build_scorer,
            run_external_bench,
        )
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cache = _write_2wiki_fixture(tmp)
            loader = build_loader("2wiki", split="dev",
                                   cache_dir=cache)
            scorer = build_scorer("2wiki")

            def answer(q):
                return {"answer": q.gold_answer}
            sp = StubProducer(answer)

            result = run_external_bench(
                loader=loader, scorer=scorer, producer=sp,
            )
            self.assertEqual(result["benchmark"], "2wiki")
            self.assertEqual(result["n_queries"], 2)
            axes = {a["name"]: a for a in result["axes"]}
            # Perfect-answer stub → EM = F1 = 1.0
            self.assertEqual(axes["em"]["score"], 1.0)
            self.assertEqual(axes["f1"]["score"], 1.0)

    def test_n_samples_caps_the_run(self):
        from eval.external.runner import (
            StubProducer, build_loader, build_scorer,
            run_external_bench,
        )
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cache = _write_2wiki_fixture(tmp)
            loader = build_loader("2wiki", split="dev",
                                   cache_dir=cache)
            scorer = build_scorer("2wiki")
            sp = StubProducer(lambda q: {"answer": "anything"})
            result = run_external_bench(
                loader=loader, scorer=scorer, producer=sp,
                n_samples=1,
            )
            self.assertEqual(result["n_queries"], 1)

    def test_producer_raises_surface_as_error_rows(self):
        from eval.external.runner import (
            StubProducer, build_loader, build_scorer,
            run_external_bench,
        )
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cache = _write_2wiki_fixture(tmp)
            loader = build_loader("2wiki", split="dev",
                                   cache_dir=cache)
            scorer = build_scorer("2wiki")

            def explode(q):
                raise RuntimeError(f"boom for {q.id}")
            sp = StubProducer(explode)
            result = run_external_bench(
                loader=loader, scorer=scorer, producer=sp,
            )
            self.assertEqual(result["n_errors"], 2)
            self.assertTrue(all(r["status"] == "error"
                                  for r in result["rows"]))
            self.assertTrue(any("boom" in r["answer"]
                                  for r in result["rows"]))


class BenchmarkIdMismatchTests(unittest.TestCase):
    def test_runner_catches_loader_scorer_mismatch(self):
        from eval.external.runner import (
            StubProducer, build_loader, build_scorer,
            run_external_bench,
        )
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cache = _write_2wiki_fixture(tmp)
            loader = build_loader("2wiki", split="dev",
                                   cache_dir=cache)
            scorer = build_scorer("musique", variant="ans")
            sp = StubProducer(lambda q: {"answer": "x"})
            with self.assertRaises(ValueError):
                run_external_bench(
                    loader=loader, scorer=scorer, producer=sp,
                )


# ─── Progress callback + write_result ──────────────────────────────


class ProgressCallbackTests(unittest.TestCase):
    def test_on_progress_fires_at_each_threshold(self):
        from eval.external.runner import (
            StubProducer, build_loader, build_scorer,
            run_external_bench,
        )
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cache = _write_2wiki_fixture(tmp)
            loader = build_loader("2wiki", split="dev",
                                   cache_dir=cache)
            scorer = build_scorer("2wiki")
            sp = StubProducer(lambda q: {"answer": "x"})

            calls: list = []
            def cb(i, n, e):
                calls.append((i, n))
            run_external_bench(
                loader=loader, scorer=scorer, producer=sp,
                progress_every=1, on_progress=cb,
            )
            # Fires once per row + final == 2 queries → 2 calls
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[-1][1], 2)


class WriteResultTests(unittest.TestCase):
    def test_write_creates_dir_and_atomic_rename(self):
        from eval.external.runner import write_result
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "nested" / "deep" / "result.json"
            payload: Dict[str, Any] = {"hello": "world", "n": 7}
            final = write_result(payload, out)
            self.assertEqual(final, out)
            self.assertTrue(out.exists())
            # Tmp side-file must not remain.
            self.assertFalse(
                out.with_suffix(out.suffix + ".tmp").exists()
            )
            self.assertEqual(json.loads(out.read_text(encoding="utf-8")),
                              payload)


# ─── Producer defaults ─────────────────────────────────────────────


class ProducerDefaultsTests(unittest.TestCase):
    """Pin the .name attribute and constructor surface so a config
    file can rely on the public API."""

    def test_closed_corpus_producer_name(self):
        from eval.external.runner import ClosedCorpusGemmaProducer
        p = ClosedCorpusGemmaProducer(model="gemma4:e4b")
        self.assertEqual(p.name, "closed-corpus-gemma")

    def test_james_engine_producer_name(self):
        from eval.external.runner import JamesEngineProducer
        p = JamesEngineProducer(model="gemma4:e4b")
        self.assertEqual(p.name, "james-engine")


if __name__ == "__main__":
    unittest.main()
