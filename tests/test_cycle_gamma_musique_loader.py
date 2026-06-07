"""Cycle γ Phase A.3 — MuSiQue loader contract tests.

Synthetic JSONL fixtures in tmpdir — network-free, repo-free.
Schema verified against MuSiQue's ``raw_data_to_official_format.py``
output spec.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _write_jsonl(cache_dir: Path, variant: str, split: str,
                  entries: list) -> Path:
    from eval.external.musique_loader import _expected_filename
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / _expected_filename(variant, split)
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return path


def _basic_entry(orig_id="mq-001", answer="X", n_paragraphs=3,
                  support_idxs=(0,), hops=2, answerable=True):
    paragraphs = [
        {"idx": i, "title": f"T{i}",
         "paragraph_text": f"text {i}",
         "is_supporting": i in support_idxs}
        for i in range(n_paragraphs)
    ]
    decomp = [
        {"id": f"d{i}", "question": f"sub Q {i}",
         "answer": f"sub A {i}", "paragraph_support_idx": i}
        for i in range(hops)
    ]
    return {
        "id": orig_id, "question": "Multi-hop Q?",
        "paragraphs": paragraphs,
        "question_decomposition": decomp,
        "answer": answer, "answer_aliases": [],
        "answerable": answerable,
    }


class RegistryTests(unittest.TestCase):
    def test_variants_and_splits(self):
        from eval.external.musique_loader import (
            MUSIQUE_VARIANTS, MUSIQUE_SPLITS,
        )
        self.assertEqual(set(MUSIQUE_VARIANTS), {"ans", "full"})
        self.assertEqual(set(MUSIQUE_SPLITS), {"train", "dev", "test"})

    def test_constructor_rejects_unknown_variant(self):
        from eval.external.musique_loader import MuSiQueLoader
        with self.assertRaises(ValueError):
            MuSiQueLoader(variant="bogus")

    def test_constructor_rejects_unknown_split(self):
        from eval.external.musique_loader import MuSiQueLoader
        with self.assertRaises(ValueError):
            MuSiQueLoader(split="bogus")

    def test_default_loader_is_ans_dev(self):
        from eval.external.musique_loader import MuSiQueLoader
        loader = MuSiQueLoader()
        self.assertEqual(loader.variant, "ans")
        self.assertEqual(loader.split, "dev")
        self.assertEqual(loader.benchmark_id, "musique-ans")


class CacheTests(unittest.TestCase):
    def test_missing_cache_raises(self):
        from eval.external.musique_loader import MuSiQueLoader
        with tempfile.TemporaryDirectory() as td:
            loader = MuSiQueLoader(cache_dir=Path(td))
            with self.assertRaises(FileNotFoundError):
                loader.iter_queries()

    def test_filename_includes_variant_split_and_version(self):
        from eval.external.musique_loader import MuSiQueLoader
        with tempfile.TemporaryDirectory() as td:
            loader = MuSiQueLoader(variant="full", split="train",
                                     cache_dir=Path(td))
            self.assertEqual(loader.cache_path.name,
                              "musique_full_v1.0_train.jsonl")

    def test_split_kwarg_mismatch_raises(self):
        from eval.external.musique_loader import MuSiQueLoader
        with tempfile.TemporaryDirectory() as td:
            loader = MuSiQueLoader(split="dev", cache_dir=Path(td))
            with self.assertRaises(ValueError):
                loader.iter_queries(split="train")


class SchemaMappingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_basic_entry_maps_correctly(self):
        from eval.external.musique_loader import MuSiQueLoader
        _write_jsonl(self.cache, "ans", "dev", [_basic_entry()])
        loader = MuSiQueLoader(variant="ans", split="dev",
                                 cache_dir=self.cache)
        out = loader.iter_queries()
        self.assertEqual(len(out), 1)
        q = out[0]
        self.assertEqual(q.id, "musique-ans-mq-001")
        self.assertEqual(q.benchmark, "musique-ans")
        self.assertEqual(q.question, "Multi-hop Q?")
        self.assertEqual(q.gold_answer, "X")
        # context = paragraph_texts in order
        self.assertEqual(q.context, ("text 0", "text 1", "text 2"))
        # metadata round-trip
        self.assertEqual(q.metadata["paragraph_titles"],
                         ["T0", "T1", "T2"])
        self.assertEqual(q.metadata["paragraph_is_supporting"],
                         [True, False, False])
        self.assertEqual(q.metadata["paragraph_idx"], [0, 1, 2])
        self.assertEqual(q.metadata["support_idx_set"], [0])
        self.assertEqual(q.metadata["hop_count"], 2)
        self.assertTrue(q.metadata["answerable"])
        self.assertEqual(q.metadata["variant"], "ans")
        self.assertEqual(q.metadata["split"], "dev")

    def test_unanswerable_full_variant_preserved(self):
        from eval.external.musique_loader import MuSiQueLoader
        _write_jsonl(self.cache, "full", "dev", [
            _basic_entry(orig_id="u1", answer="", answerable=False),
        ])
        loader = MuSiQueLoader(variant="full", split="dev",
                                 cache_dir=self.cache)
        q = loader.iter_queries()[0]
        self.assertFalse(q.metadata["answerable"])
        self.assertEqual(q.gold_answer, "")

    def test_hop_count_matches_decomposition_len(self):
        from eval.external.musique_loader import MuSiQueLoader
        _write_jsonl(self.cache, "ans", "dev", [
            _basic_entry(orig_id="h4", hops=4),
        ])
        loader = MuSiQueLoader(cache_dir=self.cache)
        q = loader.iter_queries()[0]
        self.assertEqual(q.metadata["hop_count"], 4)

    def test_multiple_supporting_idxs_preserved(self):
        from eval.external.musique_loader import MuSiQueLoader
        _write_jsonl(self.cache, "ans", "dev", [
            _basic_entry(orig_id="m1", n_paragraphs=4,
                         support_idxs=(0, 2, 3)),
        ])
        loader = MuSiQueLoader(cache_dir=self.cache)
        q = loader.iter_queries()[0]
        self.assertEqual(q.metadata["support_idx_set"], [0, 2, 3])

    def test_answer_aliases_preserved(self):
        from eval.external.musique_loader import MuSiQueLoader
        e = _basic_entry()
        e["answer_aliases"] = ["alias 1", "alias 2"]
        _write_jsonl(self.cache, "ans", "dev", [e])
        loader = MuSiQueLoader(cache_dir=self.cache)
        q = loader.iter_queries()[0]
        self.assertEqual(q.metadata["answer_aliases"],
                         ["alias 1", "alias 2"])


class JsonlParsingTests(unittest.TestCase):
    def test_blank_lines_skipped(self):
        from eval.external.musique_loader import MuSiQueLoader, _expected_filename
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            cache.mkdir(parents=True, exist_ok=True)
            path = cache / _expected_filename("ans", "dev")
            with open(path, "w", encoding="utf-8") as f:
                f.write(json.dumps(_basic_entry(orig_id="a")) + "\n")
                f.write("\n")
                f.write(json.dumps(_basic_entry(orig_id="b")) + "\n")
            loader = MuSiQueLoader(cache_dir=cache)
            out = loader.iter_queries()
            self.assertEqual(len(out), 2)

    def test_bad_line_skipped_silently(self):
        """One malformed line should NOT take down the whole fixture
        — the rest of the rows still load."""
        from eval.external.musique_loader import MuSiQueLoader, _expected_filename
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            cache.mkdir(parents=True, exist_ok=True)
            path = cache / _expected_filename("ans", "dev")
            with open(path, "w", encoding="utf-8") as f:
                f.write(json.dumps(_basic_entry(orig_id="a")) + "\n")
                f.write("{not valid json\n")
                f.write(json.dumps(_basic_entry(orig_id="b")) + "\n")
            loader = MuSiQueLoader(cache_dir=cache)
            out = loader.iter_queries()
            self.assertEqual(len(out), 2)

    def test_n_samples_front_slice(self):
        from eval.external.musique_loader import MuSiQueLoader
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            _write_jsonl(cache, "ans", "dev", [
                _basic_entry(orig_id=f"row-{i}") for i in range(5)
            ])
            loader = MuSiQueLoader(cache_dir=cache)
            out = loader.iter_queries(n_samples=2)
            self.assertEqual([q.id for q in out],
                             ["musique-ans-row-0", "musique-ans-row-1"])


if __name__ == "__main__":
    unittest.main()
