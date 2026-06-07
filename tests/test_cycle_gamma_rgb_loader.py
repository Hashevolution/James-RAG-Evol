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
        self.assertEqual(len(out), 1)
        q = out[0]
        self.assertEqual(q.id,         "rgb-en-0001")
        self.assertEqual(q.benchmark,  "rgb-en")
        self.assertEqual(q.question,   "Who founded OpenAI?")
        # positive + negative are concatenated into context.
        self.assertEqual(len(q.context), 2)
        self.assertEqual(q.gold_answer, "Sam Altman")
        self.assertEqual(q.metadata["positive_count"], 1)
        self.assertEqual(q.metadata["negative_count"], 1)
        self.assertEqual(q.metadata["language"], "en")
        self.assertEqual(q.metadata["variant"], "en")
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
        self.assertEqual(out[0].metadata["language"], "zh")
        self.assertEqual(out[0].benchmark, "rgb-zh")

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
        q = loader.iter_queries()[0]
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
        q = loader.iter_queries()[0]
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
        q = loader.iter_queries()[0]
        self.assertEqual(q.benchmark, "rgb-en_fact")
        self.assertEqual(q.metadata["positive_wrong"],
                         ["The capital of France is Lyon."])

    def test_negative_rejection_case_has_zero_positives(self):
        """RGB encodes negative-rejection (abstention) cases as rows
        whose positive list is empty — the scorer (Phase A.4) checks
        ``metadata['positive_count'] == 0``. The loader must preserve
        that flag faithfully."""
        from eval.external.rgb_loader import RGBLoader
        _write_synthetic(self.cache, "en", [
            {"id": "neg1",
             "query": "Who is the next CEO of nonexistent company?",
             "answer": "",
             "positive": [],
             "negative": ["distractor 1", "distractor 2"]},
        ])
        loader = RGBLoader(variant="en", cache_dir=self.cache)
        q = loader.iter_queries()[0]
        self.assertEqual(q.metadata["positive_count"], 0)
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
                 "positive": [], "negative": []}
                for i in range(10)
            ]
            _write_synthetic(Path(td), "en", entries)
            loader = RGBLoader(variant="en", cache_dir=Path(td))
            out = loader.iter_queries(n_samples=3)
            self.assertEqual(len(out), 3)
            self.assertEqual([q.id for q in out],
                             ["rgb-en-r0", "rgb-en-r1", "rgb-en-r2"])


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
            self.assertEqual(len(queries), 1)
            self.assertEqual(queries[0].id, "rgb-en-99")

    def test_jsonl_file_loads_one_query_per_line(self):
        """The on-disk format for the official ``en`` / ``zh`` /
        ``*_int`` / ``*_fact`` variants is JSONL; round-trip pin."""
        from eval.external.rgb_loader import RGBLoader
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            cache.mkdir(parents=True, exist_ok=True)
            entries = [
                {"id": 0, "query": "a?", "answer": "a",
                 "positive": ["p"], "negative": []},
                {"id": 1, "query": "b?", "answer": "b",
                 "positive": [], "negative": ["n"]},
                {"id": 2, "query": "c?", "answer": "c",
                 "positive": ["p"], "negative": []},
            ]
            with open(cache / "en.json", "w", encoding="utf-8") as f:
                for e in entries:
                    f.write(json.dumps(e) + "\n")
                f.write("\n")    # trailing blank line — must be tolerated
            loader = RGBLoader(variant="en", cache_dir=cache)
            queries = loader.iter_queries()
            self.assertEqual(len(queries), 3)
            self.assertEqual([q.id for q in queries],
                              ["rgb-en-0", "rgb-en-1", "rgb-en-2"])

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
