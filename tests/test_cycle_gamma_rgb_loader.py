"""Cycle γ Phase A.1 — RGB loader contract tests.

Every test runs against a hand-written synthetic fixture written to
a tmpdir so the suite never touches the network and never depends
on the live RGB GitHub repo.

The synthetic rows mirror the published schema verified against the
official ``evalue.py`` (``id`` / ``query`` / ``answer`` /
``positive`` / ``negative`` / ``positive_wrong``) so the schema
mapping is exercised end-to-end. Real measurement runs (Phase B+)
will populate the cache from the live repo via ``allow_download=
True``.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _write_synthetic(
    cache_dir: Path,
    variant: str,
    entries: list,
) -> Path:
    """Write a synthetic <variant>.json into the loader's cache dir
    layout (``<cache_dir>/<variant>.json``)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{variant}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False)
    return path


class VariantRegistryTests(unittest.TestCase):
    """RGB_VARIANTS covers every published variant. Constructor
    rejects unknown variants."""

    def test_variant_registry_complete(self):
        from eval.external.rgb_loader import RGB_VARIANTS
        self.assertEqual(set(RGB_VARIANTS), {
            "en", "zh",
            "en_refine", "zh_refine",
            "en_int", "zh_int",
            "en_fact", "zh_fact",
        })

    def test_constructor_rejects_unknown_variant(self):
        from eval.external.rgb_loader import RGBLoader
        with self.assertRaises(ValueError):
            RGBLoader(variant="bogus")

    def test_default_variant_is_english_base(self):
        from eval.external.rgb_loader import RGBLoader
        loader = RGBLoader()
        self.assertEqual(loader.variant, "en")
        self.assertEqual(loader.benchmark_id, "rgb-en")


class CacheBehaviourTests(unittest.TestCase):
    """Cache absence + downloads disabled = FileNotFoundError."""

    def test_missing_cache_no_download_raises(self):
        from eval.external.rgb_loader import RGBLoader
        with tempfile.TemporaryDirectory() as td:
            loader = RGBLoader(variant="en", cache_dir=Path(td),
                                allow_download=False)
            with self.assertRaises(FileNotFoundError):
                loader.iter_queries()

    def test_cache_path_respects_cache_dir(self):
        from eval.external.rgb_loader import RGBLoader
        with tempfile.TemporaryDirectory() as td:
            loader = RGBLoader(variant="en", cache_dir=Path(td))
            self.assertEqual(loader.cache_path,
                              Path(td) / "en.json")


class SchemaMappingTests(unittest.TestCase):
    """Synthetic fixture → ExternalQuery shape."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_basic_entry_maps_correctly(self):
        from eval.external.rgb_loader import RGBLoader
        _write_synthetic(self.cache, "en", [
            {
                "id": "0001",
                "query": "Who founded OpenAI?",
                "answer": "Sam Altman",
                "positive": ["Sam Altman co-founded OpenAI in 2015."],
                "negative": ["FTX is a cryptocurrency exchange."],
            },
        ])
        loader = RGBLoader(variant="en", cache_dir=self.cache)
        out = loader.iter_queries()
        # Default abstention_mode=True emits BOTH the
        # noise-robustness query AND the negative-rejection variant
        # for every row with positive evidence (cycle γ Phase B #3,
        # 2026-06-08). One fixture row → two queries.
        self.assertEqual(len(out), 2)
        q = out[0]   # noise-robustness query
        self.assertEqual(q.id,         "rgb-en-0001-noise")
        self.assertEqual(q.benchmark,  "rgb-en")
        self.assertEqual(q.question,   "Who founded OpenAI?")
        # positive + negative are concatenated into context.
        self.assertEqual(len(q.context), 2)
        self.assertEqual(q.gold_answer, "Sam Altman")
        self.assertEqual(q.metadata["positive_count"], 1)
        self.assertEqual(q.metadata["negative_count"], 1)
        self.assertEqual(q.metadata["language"], "en")
        self.assertEqual(q.metadata["variant"], "en")
        self.assertEqual(q.metadata["setting"], "noise_robustness")
        self.assertEqual(q.metadata["answer_aliases"], [])
        # _fact-only field absent on base variant
        self.assertNotIn("positive_wrong", q.metadata)

    def test_zh_variant_marks_language(self):
        from eval.external.rgb_loader import RGBLoader
        _write_synthetic(self.cache, "zh", [
            {"id": "z1", "query": "中国首都是哪里？",
             "answer": "北京",
             "positive": ["北京是中国首都。"], "negative": []},
        ])
        loader = RGBLoader(variant="zh", cache_dir=self.cache)
        out = loader.iter_queries()
        # zh row has positive → noise + negrej both emitted (2 queries)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0].metadata["language"], "zh")
        self.assertEqual(out[0].benchmark, "rgb-zh")
        # Both queries inherit the language tag.
        self.assertEqual(out[1].metadata["language"], "zh")

    def test_list_answer_flattens_with_aliases(self):
        from eval.external.rgb_loader import RGBLoader
        _write_synthetic(self.cache, "en", [
            {"id": "a1", "query": "Capital of the United States?",
             "answer": ["Washington, D.C.", "Washington DC",
                        "Washington"],
             "positive": ["The U.S. capital is Washington, D.C."],
             "negative": []},
        ])
        loader = RGBLoader(variant="en", cache_dir=self.cache)
        out = loader.iter_queries()
        q = out[0]   # noise-robustness query (first emitted)
        # First element is the primary answer; the rest are aliases.
        self.assertEqual(q.gold_answer, "Washington, D.C.")
        self.assertEqual(q.metadata["answer_aliases"],
                         ["Washington DC", "Washington"])

    def test_nested_list_answer_flattens_one_level(self):
        """Some RGB rows wrap aliases in a list-of-lists; loader
        flattens one level so the scorer sees a flat alias list."""
        from eval.external.rgb_loader import RGBLoader
        _write_synthetic(self.cache, "en", [
            {"id": "a2", "query": "Who?",
             "answer": [["Sam Bankman-Fried", "SBF"], "Bankman-Fried"],
             "positive": ["doc"], "negative": []},
        ])
        loader = RGBLoader(variant="en", cache_dir=self.cache)
        q = loader.iter_queries()[0]   # noise-robustness query
        self.assertEqual(q.gold_answer, "Sam Bankman-Fried")
        self.assertEqual(q.metadata["answer_aliases"],
                         ["SBF", "Bankman-Fried"])

    def test_fact_variant_preserves_positive_wrong(self):
        """The _fact variant carries an extra distractor list that the
        counterfactual-robustness scorer needs."""
        from eval.external.rgb_loader import RGBLoader
        _write_synthetic(self.cache, "en_fact", [
            {"id": "f1", "query": "Capital?", "answer": "Paris",
             "positive": ["Paris is the capital of France."],
             "negative": ["Berlin is in Germany."],
             "positive_wrong": ["The capital of France is Lyon."]},
        ])
        loader = RGBLoader(variant="en_fact", cache_dir=self.cache)
        q = loader.iter_queries()[0]   # noise-robustness query
        self.assertEqual(q.benchmark, "rgb-en_fact")
        self.assertEqual(q.metadata["positive_wrong"],
                         ["The capital of France is Lyon."])

    def test_native_zero_positive_row_emits_only_one_query(self):
        """A row whose published positive list is already empty
        cannot have its positives stripped — the negative-rejection
        variant would be a clone of the noise-robustness one. The
        loader skips the duplicate so cost stays predictable.
        """
        from eval.external.rgb_loader import RGBLoader
        _write_synthetic(self.cache, "en", [
            {"id": "neg1",
             "query": "Who is the next CEO of nonexistent company?",
             "answer": "",
             "positive": [],
             "negative": ["distractor 1", "distractor 2"]},
        ])
        loader = RGBLoader(variant="en", cache_dir=self.cache)
        out = loader.iter_queries()
        # Only the noise-robustness query is emitted (negrej clone
        # skipped).
        self.assertEqual(len(out), 1)
        q = out[0]
        self.assertEqual(q.metadata["positive_count"], 0)
        self.assertEqual(q.metadata["setting"], "noise_robustness")
        # context = positive ∪ negative; even with 0 positives the
        # negative docs are still there for the scorer to inspect.
        self.assertEqual(len(q.context), 2)


class TakeSampleIntegrationTests(unittest.TestCase):
    """``n_samples`` slices the front of the fixture without
    altering the schema."""

    def test_n_samples_returns_front_slice(self):
        from eval.external.rgb_loader import RGBLoader
        with tempfile.TemporaryDirectory() as td:
            entries = [
                {"id": f"r{i}", "query": "?", "answer": "a",
                 "positive": [], "negative": []}   # no positives →
                                                    # only 1 query per
                                                    # row (no negrej
                                                    # clone)
                for i in range(10)
            ]
            _write_synthetic(Path(td), "en", entries)
            loader = RGBLoader(variant="en", cache_dir=Path(td))
            out = loader.iter_queries(n_samples=3)
            self.assertEqual(len(out), 3)
            self.assertEqual([q.id for q in out],
                             ["rgb-en-r0-noise",
                              "rgb-en-r1-noise",
                              "rgb-en-r2-noise"])

    def test_n_samples_counts_emitted_queries_not_fixture_rows(self):
        """When abstention_mode=True doubles rows that carry positive
        evidence, n_samples must still mean "return N queries", not
        "return N fixture rows worth of queries". This keeps the cost
        accounting predictable for the runner."""
        from eval.external.rgb_loader import RGBLoader
        with tempfile.TemporaryDirectory() as td:
            entries = [
                {"id": f"r{i}", "query": "?", "answer": "a",
                 "positive": ["p"], "negative": ["n"]}   # each row → 2 queries
                for i in range(10)
            ]
            _write_synthetic(Path(td), "en", entries)
            loader = RGBLoader(variant="en", cache_dir=Path(td))
            out = loader.iter_queries(n_samples=3)
            self.assertEqual(len(out), 3)
            # First two queries are the first row's noise + negrej.
            self.assertEqual(out[0].id, "rgb-en-r0-noise")
            self.assertEqual(out[1].id, "rgb-en-r0-negrej")
            self.assertEqual(out[2].id, "rgb-en-r1-noise")


class AbstentionModeTests(unittest.TestCase):
    """Phase B #3 (2026-06-08) — the loader emits noise-robustness +
    negative-rejection queries for every row with positives. These
    tests pin the dual-axis contract end-to-end."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.cache = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    def _entry(self):
        return {
            "id":       "x1",
            "query":    "Who founded OpenAI?",
            "answer":   "Sam Altman",
            "positive": ["Sam Altman co-founded OpenAI in 2015."],
            "negative": ["FTX is a cryptocurrency exchange.",
                          "Mars rover Perseverance."],
        }

    def test_dual_mode_emits_two_queries_when_positives_exist(self):
        from eval.external.rgb_loader import RGBLoader
        _write_synthetic(self.cache, "en", [self._entry()])
        loader = RGBLoader(variant="en", cache_dir=self.cache,
                            abstention_mode=True)
        out = loader.iter_queries()
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0].metadata["setting"], "noise_robustness")
        self.assertEqual(out[1].metadata["setting"], "negative_rejection")

    def test_negrej_query_has_positive_count_zero(self):
        """The whole point of the negrej variant: scorer routes on
        positive_count=0 → abstention axis."""
        from eval.external.rgb_loader import RGBLoader
        _write_synthetic(self.cache, "en", [self._entry()])
        loader = RGBLoader(variant="en", cache_dir=self.cache)
        out = loader.iter_queries()
        negrej = out[1]
        self.assertEqual(negrej.metadata["positive_count"], 0)
        self.assertEqual(negrej.id, "rgb-en-x1-negrej")

    def test_negrej_context_excludes_positives(self):
        """The model must see only distractors — otherwise it would
        trivially answer correctly and the abstention test would be
        invalid."""
        from eval.external.rgb_loader import RGBLoader
        _write_synthetic(self.cache, "en", [self._entry()])
        loader = RGBLoader(variant="en", cache_dir=self.cache)
        out = loader.iter_queries()
        negrej_context = list(out[1].context)
        # Two negatives, zero positives.
        self.assertEqual(len(negrej_context), 2)
        self.assertNotIn(
            "Sam Altman co-founded OpenAI in 2015.",
            negrej_context,
        )

    def test_negrej_query_empty_gold_so_noise_axis_skips_it(self):
        """The negrej query's gold_answer is empty so the
        noise-robustness branch (gated on positive_count > 0 too)
        cannot accidentally credit a match."""
        from eval.external.rgb_loader import RGBLoader
        _write_synthetic(self.cache, "en", [self._entry()])
        loader = RGBLoader(variant="en", cache_dir=self.cache)
        out = loader.iter_queries()
        self.assertEqual(out[1].gold_answer, "")

    def test_paired_id_links_negrej_back_to_noise(self):
        """For per-question forensic analysis."""
        from eval.external.rgb_loader import RGBLoader
        _write_synthetic(self.cache, "en", [self._entry()])
        loader = RGBLoader(variant="en", cache_dir=self.cache)
        out = loader.iter_queries()
        negrej = out[1]
        self.assertEqual(negrej.metadata["paired_id"], out[0].id)

    def test_abstention_mode_false_emits_only_noise_query(self):
        from eval.external.rgb_loader import RGBLoader
        _write_synthetic(self.cache, "en", [self._entry()])
        loader = RGBLoader(variant="en", cache_dir=self.cache,
                            abstention_mode=False)
        out = loader.iter_queries()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].metadata["setting"], "noise_robustness")

    def test_abstention_mode_default_is_true(self):
        from eval.external.rgb_loader import RGBLoader
        loader = RGBLoader(variant="en")
        self.assertTrue(loader.abstention_mode)


class CorruptFixtureTests(unittest.TestCase):
    """Malformed JSON / non-list root / non-dict rows surface cleanly."""

    def test_dict_root_treated_as_single_jsonl_entry(self):
        """Phase B smoke (2026-06-08) showed the published RGB
        fixtures are JSONL (one JSON object per line), not a JSON
        array. The loader now accepts either shape. A bare dict
        therefore becomes a 1-entry JSONL stream rather than an
        error — and the per-row validation (id, benchmark match,
        etc.) is what catches malformed entries downstream."""
        from eval.external.rgb_loader import RGBLoader
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            cache.mkdir(parents=True, exist_ok=True)
            entry = {
                "id":       99,
                "query":    "smoke?",
                "answer":   "smoke",
                "positive": ["evidence"],
                "negative": [],
            }
            with open(cache / "en.json", "w", encoding="utf-8") as f:
                json.dump(entry, f)
            loader = RGBLoader(variant="en", cache_dir=cache)
            queries = loader.iter_queries()
            # 1 noise + 1 negrej because positive=["evidence"] exists.
            self.assertEqual(len(queries), 2)
            self.assertEqual(queries[0].id, "rgb-en-99-noise")
            self.assertEqual(queries[1].id, "rgb-en-99-negrej")

    def test_jsonl_file_loads_one_query_per_line(self):
        """The on-disk format for the official ``en`` / ``zh`` /
        ``*_int`` / ``*_fact`` variants is JSONL; round-trip pin."""
        from eval.external.rgb_loader import RGBLoader
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            cache.mkdir(parents=True, exist_ok=True)
            entries = [
                {"id": 0, "query": "a?", "answer": "a",
                 "positive": ["p"], "negative": []},     # → 2 queries
                {"id": 1, "query": "b?", "answer": "b",
                 "positive": [], "negative": ["n"]},     # → 1 (no neg-rej clone)
                {"id": 2, "query": "c?", "answer": "c",
                 "positive": ["p"], "negative": []},     # → 2 queries
            ]
            with open(cache / "en.json", "w", encoding="utf-8") as f:
                for e in entries:
                    f.write(json.dumps(e) + "\n")
                f.write("\n")    # trailing blank line — must be tolerated
            # Use abstention_mode=False to keep this JSONL parsing
            # test isolated from the dual-axis expansion (covered by
            # its own AbstentionModeTests suite).
            loader = RGBLoader(variant="en", cache_dir=cache,
                                abstention_mode=False)
            queries = loader.iter_queries()
            self.assertEqual(len(queries), 3)
            self.assertEqual([q.id for q in queries],
                              ["rgb-en-0-noise",
                               "rgb-en-1-noise",
                               "rgb-en-2-noise"])

    def test_corrupt_json_raises_json_decode_error(self):
        from eval.external.rgb_loader import RGBLoader
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            cache.mkdir(parents=True, exist_ok=True)
            with open(cache / "en.json", "w", encoding="utf-8") as f:
                f.write("{not valid json")
            loader = RGBLoader(variant="en", cache_dir=cache)
            with self.assertRaises(json.JSONDecodeError):
                loader.iter_queries()

    def test_non_dict_rows_silently_skipped(self):
        """A misformatted row inside an otherwise valid list is
        skipped rather than crashing the whole fixture — keeps the
        loader resilient to one bad upstream commit."""
        from eval.external.rgb_loader import RGBLoader
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            cache.mkdir(parents=True, exist_ok=True)
            with open(cache / "en.json", "w", encoding="utf-8") as f:
                json.dump([
                    {"id": "ok", "query": "?", "answer": "a",
                     "positive": [], "negative": []},
                    "this is not a dict",
                    {"id": "ok2", "query": "??", "answer": "b",
                     "positive": [], "negative": []},
                ], f)
            loader = RGBLoader(variant="en", cache_dir=cache)
            out = loader.iter_queries()
            self.assertEqual(len(out), 2)


if __name__ == "__main__":
    unittest.main()
