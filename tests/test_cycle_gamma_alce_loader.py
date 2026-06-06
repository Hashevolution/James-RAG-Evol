"""Cycle γ Phase A.2 — ALCE loader contract tests.

Every test runs against a hand-written synthetic fixture written to
a tmpdir so the suite never touches the network and never depends
on the live ALCE GitHub / HuggingFace data tarball.

The synthetic rows mirror the published per-variant schema verified
against ALCE's official ``eval.py``:

* ASQA   — ``question`` / ``qa_pairs[].short_answers`` /
           ``annotations[].long_answer`` / ``docs[].text``
* QAMPARI — ``question`` / ``answers`` (list of acceptable answer
           groups) / ``docs[].text``
* ELI5   — ``question`` / ``answer`` (reference long answer) /
           ``claims`` / ``docs[].text``

Real measurement runs (Phase B+) populate the cache by pointing
``cache_dir`` at the directory ALCE's ``download_data.sh`` creates.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _write_fixture(
    cache_dir: Path,
    variant: str,
    entries: list,
) -> Path:
    """Write a synthetic ALCE fixture under ``cache_dir`` using the
    expected filename for the variant."""
    from eval.external import alce_loader as al
    cfg = al._VARIANTS[variant]
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / cfg.filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False)
    return path


class VariantRegistryTests(unittest.TestCase):
    def test_variant_registry_complete(self):
        from eval.external.alce_loader import ALCE_VARIANTS
        self.assertEqual(set(ALCE_VARIANTS), {"asqa", "qampari", "eli5"})

    def test_constructor_rejects_unknown_variant(self):
        from eval.external.alce_loader import ALCELoader
        with self.assertRaises(ValueError):
            ALCELoader(variant="bogus")

    def test_default_variant_is_asqa(self):
        from eval.external.alce_loader import ALCELoader
        loader = ALCELoader()
        self.assertEqual(loader.variant, "asqa")
        self.assertEqual(loader.benchmark_id, "alce-asqa")

    def test_each_variant_has_distinct_filename(self):
        from eval.external import alce_loader as al
        files = [cfg.filename for cfg in al._VARIANTS.values()]
        self.assertEqual(len(files), len(set(files)))

    def test_each_variant_has_a_mapper(self):
        """Import-time invariant — every _VARIANTS entry has a mapper."""
        from eval.external import alce_loader as al
        self.assertEqual(set(al._MAPPERS), set(al._VARIANTS))


class CacheBehaviourTests(unittest.TestCase):
    def test_missing_cache_raises_file_not_found(self):
        from eval.external.alce_loader import ALCELoader
        with tempfile.TemporaryDirectory() as td:
            loader = ALCELoader(variant="asqa", cache_dir=Path(td))
            with self.assertRaises(FileNotFoundError):
                loader.iter_queries()

    def test_cache_path_uses_variant_filename(self):
        from eval.external.alce_loader import ALCELoader
        with tempfile.TemporaryDirectory() as td:
            asqa = ALCELoader(variant="asqa", cache_dir=Path(td))
            qampari = ALCELoader(variant="qampari", cache_dir=Path(td))
            eli5 = ALCELoader(variant="eli5", cache_dir=Path(td))
            # Each variant resolves to its own filename in the same
            # directory.
            self.assertNotEqual(asqa.cache_path, qampari.cache_path)
            self.assertNotEqual(asqa.cache_path, eli5.cache_path)
            self.assertEqual(asqa.cache_path.parent, Path(td))


class ASQAMappingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_basic_entry_maps_correctly(self):
        from eval.external.alce_loader import ALCELoader
        _write_fixture(self.cache, "asqa", [
            {
                "sample_id": "asqa-001",
                "question": "When was OpenAI founded?",
                "qa_pairs": [
                    {"question": "Founding year?",
                     "short_answers": ["2015", "in 2015"]},
                ],
                "annotations": [
                    {"long_answer": "OpenAI was founded in December 2015 …"},
                ],
                "docs": [
                    {"title": "OpenAI", "text": "OpenAI founded 2015."},
                    {"title": "Sam Altman", "text": "co-founder."},
                ],
            },
        ])
        loader = ALCELoader(variant="asqa", cache_dir=self.cache)
        out = loader.iter_queries()
        self.assertEqual(len(out), 1)
        q = out[0]
        self.assertEqual(q.id, "alce-asqa-asqa-001")
        self.assertEqual(q.benchmark, "alce-asqa")
        self.assertEqual(q.question, "When was OpenAI founded?")
        self.assertEqual(q.gold_answer, "2015")
        self.assertEqual(q.context,
                         ("OpenAI founded 2015.", "co-founder."))
        self.assertEqual(q.metadata["docs_titles"],
                         ["OpenAI", "Sam Altman"])
        self.assertEqual(q.metadata["retriever"], "gtr")
        self.assertEqual(q.metadata["variant"], "asqa")
        # qa_pairs / annotations preserved verbatim.
        self.assertEqual(len(q.metadata["qa_pairs"]), 1)
        self.assertEqual(len(q.metadata["annotations"]), 1)

    def test_missing_short_answers_yields_empty_gold(self):
        from eval.external.alce_loader import ALCELoader
        _write_fixture(self.cache, "asqa", [
            {"sample_id": "asqa-002", "question": "?",
             "qa_pairs": [], "annotations": [], "docs": []},
        ])
        loader = ALCELoader(variant="asqa", cache_dir=self.cache)
        q = loader.iter_queries()[0]
        self.assertEqual(q.gold_answer, "")


class QAMPARIMappingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_list_of_lists_answers_round_trip(self):
        from eval.external.alce_loader import ALCELoader
        _write_fixture(self.cache, "qampari", [
            {
                "sample_id": "q-001",
                "question": "Name the founders of OpenAI.",
                "answers": [
                    ["Sam Altman", "Altman"],
                    ["Elon Musk"],
                    ["Greg Brockman"],
                ],
                "docs": [{"title": "OpenAI", "text": "Founders: Altman, Musk, Brockman."}],
            },
        ])
        loader = ALCELoader(variant="qampari", cache_dir=self.cache)
        q = loader.iter_queries()[0]
        self.assertEqual(q.benchmark, "alce-qampari")
        # Primary = first group's first string.
        self.assertEqual(q.gold_answer, "Sam Altman")
        # Full list-of-lists preserved for the scorer.
        self.assertEqual(q.metadata["answers"],
                         [["Sam Altman", "Altman"], ["Elon Musk"],
                          ["Greg Brockman"]])

    def test_first_group_as_flat_string_accepted(self):
        """Some QAMPARI rows store the first answer as a bare string
        instead of a single-element list — the loader handles both."""
        from eval.external.alce_loader import ALCELoader
        _write_fixture(self.cache, "qampari", [
            {"sample_id": "q-002", "question": "?",
             "answers": ["Solo answer", ["Other"]],
             "docs": []},
        ])
        loader = ALCELoader(variant="qampari", cache_dir=self.cache)
        q = loader.iter_queries()[0]
        self.assertEqual(q.gold_answer, "Solo answer")


class ELI5MappingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_basic_entry_maps_correctly(self):
        from eval.external.alce_loader import ALCELoader
        _write_fixture(self.cache, "eli5", [
            {
                "sample_id": "eli5-001",
                "question": "Why is the sky blue?",
                "answer": "Rayleigh scattering …",
                "claims": [
                    "Air molecules scatter blue light more than red.",
                    "Shorter wavelengths scatter more.",
                ],
                "docs": [
                    {"title": "Rayleigh scattering",
                     "text": "Rayleigh scattering causes blue sky."},
                ],
            },
        ])
        loader = ALCELoader(variant="eli5", cache_dir=self.cache)
        q = loader.iter_queries()[0]
        self.assertEqual(q.benchmark, "alce-eli5")
        self.assertEqual(q.gold_answer, "Rayleigh scattering …")
        # claims preserved for the NLI-based citation scorer.
        self.assertEqual(len(q.metadata["claims"]), 2)
        self.assertEqual(q.metadata["retriever"], "bm25")


class DocsFallbackTests(unittest.TestCase):
    """The ``docs`` field may carry ``text`` (passage body) or
    ``sent`` (QA-extracted sentence). The loader prefers ``text``
    but falls back to ``sent``."""

    def test_text_field_preferred_over_sent(self):
        from eval.external.alce_loader import ALCELoader
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            _write_fixture(cache, "asqa", [
                {"sample_id": "x", "question": "?",
                 "qa_pairs": [{"short_answers": ["a"]}],
                 "annotations": [],
                 "docs": [{"title": "T",
                           "text": "body wins",
                           "sent": "snippet loses"}]},
            ])
            loader = ALCELoader(variant="asqa", cache_dir=cache)
            q = loader.iter_queries()[0]
            self.assertEqual(q.context, ("body wins",))

    def test_sent_used_when_text_absent(self):
        from eval.external.alce_loader import ALCELoader
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            _write_fixture(cache, "asqa", [
                {"sample_id": "y", "question": "?",
                 "qa_pairs": [{"short_answers": ["a"]}],
                 "annotations": [],
                 "docs": [{"title": "T", "sent": "snippet OK"}]},
            ])
            loader = ALCELoader(variant="asqa", cache_dir=cache)
            q = loader.iter_queries()[0]
            self.assertEqual(q.context, ("snippet OK",))


class TakeSampleAndCorruptTests(unittest.TestCase):
    def test_n_samples_front_slice_across_variants(self):
        from eval.external.alce_loader import ALCELoader
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            _write_fixture(cache, "qampari", [
                {"sample_id": f"q{i}", "question": "?",
                 "answers": [["x"]], "docs": []}
                for i in range(10)
            ])
            loader = ALCELoader(variant="qampari", cache_dir=cache)
            out = loader.iter_queries(n_samples=3)
            self.assertEqual([q.id for q in out],
                             ["alce-qampari-q0", "alce-qampari-q1",
                              "alce-qampari-q2"])

    def test_non_list_root_raises_value_error(self):
        from eval.external.alce_loader import ALCELoader
        from eval.external import alce_loader as al
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            cache.mkdir(parents=True, exist_ok=True)
            path = cache / al._VARIANTS["asqa"].filename
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"not": "data wrapper"}, f)
            loader = ALCELoader(variant="asqa", cache_dir=cache)
            with self.assertRaises(ValueError):
                loader.iter_queries()

    def test_top_level_data_key_unwrapped(self):
        """Some ALCE variants wrap rows under {'data': [...]}; the
        loader unwraps so callers see a flat list."""
        from eval.external.alce_loader import ALCELoader
        from eval.external import alce_loader as al
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            cache.mkdir(parents=True, exist_ok=True)
            path = cache / al._VARIANTS["asqa"].filename
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"data": [
                    {"sample_id": "w1", "question": "?",
                     "qa_pairs": [{"short_answers": ["yes"]}],
                     "annotations": [], "docs": []},
                ]}, f)
            loader = ALCELoader(variant="asqa", cache_dir=cache)
            out = loader.iter_queries()
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0].id, "alce-asqa-w1")

    def test_non_dict_rows_silently_skipped(self):
        from eval.external.alce_loader import ALCELoader
        from eval.external import alce_loader as al
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            cache.mkdir(parents=True, exist_ok=True)
            path = cache / al._VARIANTS["eli5"].filename
            with open(path, "w", encoding="utf-8") as f:
                json.dump([
                    {"sample_id": "ok", "question": "?",
                     "answer": "a", "claims": [], "docs": []},
                    "garbage row",
                    {"sample_id": "ok2", "question": "??",
                     "answer": "b", "claims": [], "docs": []},
                ], f)
            loader = ALCELoader(variant="eli5", cache_dir=cache)
            out = loader.iter_queries()
            self.assertEqual(len(out), 2)


if __name__ == "__main__":
    unittest.main()
