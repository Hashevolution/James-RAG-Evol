"""Cycle γ Phase A.3 — MuSiQue (Trivedi et al. 2022) loader.

MuSiQue (https://github.com/StonyBrookNLP/musique) is one of the
two multi-hop QA evidence paths for cycle γ. Its official format is
JSONL (one JSON object per line) and ships in two variants:

* **MuSiQue-Ans** — answerable questions only (cleanest signal for
  EM / F1 + support-fact accuracy).
* **MuSiQue-Full** — includes unanswerable questions (rows with
  ``answerable == False``). Useful for abstention robustness
  measurements.

Each variant publishes ``train`` / ``dev`` / ``test`` splits. Test
gold answers are withheld so the loader still yields the rows but
gold_answer falls back to ``""`` on test.

Source filenames (official format)
----------------------------------

* ``musique_ans_v1.0_<split>.jsonl``
* ``musique_full_v1.0_<split>.jsonl``

Schema (verified against ``raw_data_to_official_format.py``)
------------------------------------------------------------

Each JSONL line is a dict::

    {
      "id":                    <str>,
      "paragraphs": [
        {
          "idx":               <int>,
          "title":             <str>,
          "paragraph_text":    <str>,
          "is_supporting":     <bool>,
        }, ...
      ],
      "question":              <str>,
      "question_decomposition": [
        {
          "id":                <str>,
          "question":          <str>,
          "answer":            <str>,
          "paragraph_support_idx": <int | None>,
        }, ...
      ],
      "answer":                <str>,
      "answer_aliases":        [<str>, ...],
      "answerable":            <bool>,
    }

Schema mapping (MuSiQue → :class:`ExternalQuery`)
-------------------------------------------------

* ``id``         → ``"musique-<variant>-<orig_id>"``
* ``benchmark``  → ``"musique-<variant>"`` (e.g. ``"musique-ans"``)
* ``question``   → ``entry["question"]``
* ``context``    → tuple of every ``paragraph_text`` (order
                   preserved so the ``idx`` field still indexes
                   into ``context``)
* ``gold_answer`` → ``entry["answer"]``  (``""`` on test set)
* ``metadata``   → ``{
    "paragraph_titles":          [...],
    "paragraph_is_supporting":   [bool, ...],
    "paragraph_idx":             [int, ...],
    "support_idx_set":           [int, ...],   # sorted list of supporting idxs
    "answer_aliases":            [...],
    "question_decomposition":    [...],
    "answerable":                bool,
    "hop_count":                 int,           # len(question_decomposition)
    "variant":                   "ans" | "full",
    "split":                     "train"/"dev"/"test",
  }``

Self-eval trap rule (memory ``feedback_self_evaluation_trap``):
the loader does NOT rewrite questions, does NOT curate a subset,
does NOT modify gold labels.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from eval.external.base import ExternalBenchFixture, ExternalQuery


MUSIQUE_VARIANTS: Tuple[str, ...] = ("ans", "full")
MUSIQUE_SPLITS:   Tuple[str, ...] = ("train", "dev", "test")


def _expected_filename(variant: str, split: str) -> str:
    return f"musique_{variant}_v1.0_{split}.jsonl"


def _default_cache_dir() -> Path:
    return Path(__file__).resolve().parent / "_fixtures" / "musique"


def _entry_to_query(
    entry: Dict[str, Any],
    *,
    variant: str,
    split: str,
) -> ExternalQuery:
    orig_id = str(entry.get("id", "")).strip() or "noid"
    paragraphs = entry.get("paragraphs") or []
    if not isinstance(paragraphs, list):
        paragraphs = []

    paragraph_texts: List[str] = []
    paragraph_titles: List[str] = []
    paragraph_is_supporting: List[bool] = []
    paragraph_idx: List[int] = []
    support_idx: List[int] = []

    for i, p in enumerate(paragraphs):
        if not isinstance(p, dict):
            continue
        paragraph_texts.append(str(p.get("paragraph_text", "")))
        paragraph_titles.append(str(p.get("title", "")))
        # idx may be missing on some rows; fall back to the positional
        # index so downstream code can still match support indices.
        idx = p.get("idx")
        paragraph_idx.append(int(idx) if isinstance(idx, int) else i)
        is_sup = bool(p.get("is_supporting"))
        paragraph_is_supporting.append(is_sup)
        if is_sup:
            support_idx.append(paragraph_idx[-1])

    decomp = entry.get("question_decomposition") or []
    aliases = entry.get("answer_aliases") or []
    answerable = bool(entry.get("answerable", True))

    metadata: Dict[str, Any] = {
        "paragraph_titles":        paragraph_titles,
        "paragraph_is_supporting": paragraph_is_supporting,
        "paragraph_idx":           paragraph_idx,
        "support_idx_set":         sorted(set(support_idx)),
        "answer_aliases":          list(aliases) if isinstance(aliases, list) else [],
        "question_decomposition":  decomp if isinstance(decomp, list) else [],
        "answerable":              answerable,
        "hop_count":               len(decomp) if isinstance(decomp, list) else 0,
        "variant":                 variant,
        "split":                   split,
    }

    return ExternalQuery(
        id=f"musique-{variant}-{orig_id}",
        benchmark=f"musique-{variant}",
        question=str(entry.get("question", "")),
        context=tuple(paragraph_texts),
        gold_answer=str(entry.get("answer") or ""),
        metadata=metadata,
    )


class MuSiQueLoader(ExternalBenchFixture):
    """Loader for one MuSiQue variant + split.

    Usage::

        loader = MuSiQueLoader(variant="ans", split="dev",
                                cache_dir=Path("data"))
        queries = loader.iter_queries(n_samples=20)

    Operators populate ``cache_dir`` by running MuSiQue's
    ``download_data.sh`` and pointing ``cache_dir`` at the directory
    that holds the official-format ``.jsonl`` files.
    """

    def __init__(
        self,
        *,
        variant: str = "ans",
        split: str = "dev",
        cache_dir: Optional[Path] = None,
    ):
        if variant not in MUSIQUE_VARIANTS:
            raise ValueError(
                f"unknown MuSiQue variant: {variant!r}. "
                f"Valid: {MUSIQUE_VARIANTS}"
            )
        if split not in MUSIQUE_SPLITS:
            raise ValueError(
                f"unknown MuSiQue split: {split!r}. "
                f"Valid: {MUSIQUE_SPLITS}"
            )
        self._variant = variant
        self._split = split
        self._cache_dir = Path(cache_dir) if cache_dir else None

    @property
    def benchmark_id(self) -> str:
        return f"musique-{self._variant}"

    @property
    def variant(self) -> str:
        return self._variant

    @property
    def split(self) -> str:
        return self._split

    @property
    def cache_path(self) -> Path:
        base = self._cache_dir or _default_cache_dir()
        return base / _expected_filename(self._variant, self._split)

    def iter_queries(
        self,
        *,
        split: Optional[str] = None,
        n_samples: Optional[int] = None,
    ) -> List[ExternalQuery]:
        # Accept the abstract-base's ``split`` keyword for interface
        # uniformity, but the actual split is fixed at construction.
        if split is not None and split != self._split:
            raise ValueError(
                f"split mismatch: loader bound to {self._split!r}, "
                f"caller passed {split!r}"
            )
        path = self.cache_path
        if not path.exists():
            raise FileNotFoundError(
                f"MuSiQue fixture not at {path}. Run MuSiQue's "
                f"download_data.sh and point cache_dir at the "
                f"resulting directory."
            )

        queries: List[ExternalQuery] = []
        with open(path, encoding="utf-8") as f:
            for line_no, raw in enumerate(f, start=1):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                except json.JSONDecodeError:
                    # One bad line should not destroy the run — skip
                    # silently the way RGB / ALCE do for non-dict
                    # rows. The scorer counts the rows it actually
                    # got, so a sudden drop is visible downstream.
                    continue
                if not isinstance(entry, dict):
                    continue
                queries.append(_entry_to_query(
                    entry, variant=self._variant, split=self._split,
                ))
        self.validate_queries(queries)
        return self.take_sample(queries, n_samples)


__all__ = [
    "MUSIQUE_VARIANTS",
    "MUSIQUE_SPLITS",
    "MuSiQueLoader",
]
