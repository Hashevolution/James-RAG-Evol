"""Cycle γ Phase A.3 — 2WikiMultiHopQA loader contract tests.

Synthetic JSON fixtures in tmpdir — network-free, repo-free. Schema
verified against the official README of github.com/Alab-NII/2wikimultihop.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _write_fixture(cache_dir: Path, split: str, entries: list) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{split}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False)
    return path


def _basic_entry(_id="wk-001", answer="Paris", q_type="comparison",
                  n_paragraphs=2, supporting=(("T0", 0), ("T1", 1))):
    context = [
        [f"T{i}", [f"sentence {i}.0", f"sentence {i}.1"]]
        for i in range(n_paragraphs)
    ]
    return {
        "_id": _id,
        "question": "Where?",
        "answer": answer,
        "type": q_type,
        "entity_ids": "Q1_Q2",
        "context": context,
        "supporting_facts": [list(sf) for sf in supporting],
        "evidences": [["A", "lives_in", answer]],
        "evidences_id": [],
        "answer_id": "Q90",
    }


class RegistryTests(unittest.TestCase):
    def test_splits_and_types(self):
        from eval.external.wikimulti_loader import (
            WIKIMULTI_SPLITS, WIKIMULTI_TYPES,
        )
        self.assertEqual(set(WIKIMULTI_SPLITS), {"train", "dev", "test"})
        self.assertEqual(set(WIKIMULTI_TYPES), {
            "comparison", "inference",
            "compositional", "bridge-comparison",
        })

    def test_constructor_rejects_unknown_split(self):
        from eval.external.wikimulti_loader import WikiMultiLoader
        with self.assertRaises(ValueError):
            WikiMultiLoader(split="bogus")

    def test_default_loader_is_dev(self):
        from eval.external.wikimulti_loader import WikiMultiLoader
        loader = WikiMultiLoader()
        self.assertEqual(loader.split, "dev")
        self.assertEqual(loader.benchmark_id, "2wiki")


class CacheTests(unittest.TestCase):
    def test_missing_cache_raises(self):
        from eval.external.wikimulti_loader import WikiMultiLoader
        with tempfile.TemporaryDirectory() as td:
            loader = WikiMultiLoader(cache_dir=Path(td))
            with self.assertRaises(FileNotFoundError):
                loader.iter_queries()

    def test_cache_path_uses_split_filename(self):
        from eval.external.wikimulti_loader import WikiMultiLoader
        with tempfile.TemporaryDirectory() as td:
            loader = WikiMultiLoader(split="train", cache_dir=Path(td))
            self.assertEqual(loader.cache_path.name, "train.json")

    def test_split_kwarg_mismatch_raises(self):
        from eval.external.wikimulti_loader import WikiMultiLoader
        with tempfile.TemporaryDirectory() as td:
            loader = WikiMultiLoader(split="dev", cache_dir=Path(td))
            with self.assertRaises(ValueError):
                loader.iter_queries(split="train")


class SchemaMappingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_basic_entry_maps_correctly(self):
        from eval.external.wikimulti_loader import WikiMultiLoader
        _write_fixture(self.cache, "dev", [_basic_entry()])
        loader = WikiMultiLoader(split="dev", cache_dir=self.cache)
        out = loader.iter_queries()
        self.assertEqual(len(out), 1)
        q = out[0]
        self.assertEqual(q.id,        "2wiki-wk-001")
        self.assertEqual(q.benchmark, "2wiki")
        self.assertEqual(q.question,  "Where?")
        self.assertEqual(q.gold_answer, "Paris")
        # Sentences joined per paragraph; one passage per paragraph.
        self.assertEqual(q.context,
                         ("sentence 0.0 sentence 0.1",
                          "sentence 1.0 sentence 1.1"))
        # Metadata round-trip
        self.assertEqual(q.metadata["context_titles"], ["T0", "T1"])
        self.assertEqual(q.metadata["context_sentences"],
                         [["sentence 0.0", "sentence 0.1"],
                          ["sentence 1.0", "sentence 1.1"]])
        self.assertEqual(q.metadata["supporting_facts"],
                         [["T0", 0], ["T1", 1]])
        self.assertEqual(q.metadata["type"], "comparison")
        self.assertEqual(q.metadata["entity_ids"], "Q1_Q2")
        self.assertEqual(q.metadata["answer_id"], "Q90")
        self.assertEqual(q.metadata["split"], "dev")

    def test_test_split_without_answer_yields_empty_gold(self):
        from eval.external.wikimulti_loader import WikiMultiLoader
        e = _basic_entry()
        del e["answer"]   # test set has no answer
        _write_fixture(self.cache, "test", [e])
        loader = WikiMultiLoader(split="test", cache_dir=self.cache)
        q = loader.iter_queries()[0]
        self.assertEqual(q.gold_answer, "")

    def test_each_type_preserved(self):
        """Every official 2Wiki question type survives the mapping."""
        from eval.external.wikimulti_loader import (
            WikiMultiLoader, WIKIMULTI_TYPES,
        )
        entries = [_basic_entry(_id=f"t-{i}", q_type=t)
                   for i, t in enumerate(WIKIMULTI_TYPES)]
        _write_fixture(self.cache, "dev", entries)
        loader = WikiMultiLoader(cache_dir=self.cache)
        out = loader.iter_queries()
        self.assertEqual([q.metadata["type"] for q in out],
                         list(WIKIMULTI_TYPES))

    def test_malformed_context_pair_skipped(self):
        """A context entry that isn't ``[title, sentences]`` is
        silently skipped — the rest of the paragraphs load."""
        from eval.external.wikimulti_loader import WikiMultiLoader
        e = _basic_entry()
        # Inject one bad entry between two good ones.
        e["context"] = [
            ["T0", ["sent A"]],
            "not a pair",
            ["T2", ["sent B"]],
        ]
        _write_fixture(self.cache, "dev", [e])
        loader = WikiMultiLoader(cache_dir=self.cache)
        q = loader.iter_queries()[0]
        self.assertEqual(q.context, ("sent A", "sent B"))
        self.assertEqual(q.metadata["context_titles"], ["T0", "T2"])


class ParsingTests(unittest.TestCase):
    def test_non_list_root_raises_value_error(self):
        from eval.external.wikimulti_loader import WikiMultiLoader
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            cache.mkdir(parents=True, exist_ok=True)
            with open(cache / "dev.json", "w", encoding="utf-8") as f:
                json.dump({"not": "a list"}, f)
            loader = WikiMultiLoader(cache_dir=cache)
            with self.assertRaises(ValueError):
                loader.iter_queries()

    def test_non_dict_rows_silently_skipped(self):
        from eval.external.wikimulti_loader import WikiMultiLoader
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            _write_fixture(cache, "dev", [
                _basic_entry(_id="ok-1"),
                "garbage",
                _basic_entry(_id="ok-2"),
            ])
            loader = WikiMultiLoader(cache_dir=cache)
            out = loader.iter_queries()
            self.assertEqual([q.id for q in out],
                             ["2wiki-ok-1", "2wiki-ok-2"])

    def test_n_samples_front_slice(self):
        from eval.external.wikimulti_loader import WikiMultiLoader
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            _write_fixture(cache, "dev", [
                _basic_entry(_id=f"row-{i}") for i in range(5)
            ])
            loader = WikiMultiLoader(cache_dir=cache)
            out = loader.iter_queries(n_samples=3)
            self.assertEqual([q.id for q in out],
                             ["2wiki-row-0", "2wiki-row-1",
                              "2wiki-row-2"])


if __name__ == "__main__":
    unittest.main()
