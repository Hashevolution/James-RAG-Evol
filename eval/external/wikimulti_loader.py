"""Cycle γ Phase A.3 — 2WikiMultiHopQA (Ho et al. 2020) loader.

2WikiMultiHopQA (https://github.com/Alab-NII/2wikimultihop) is the
second multi-hop QA evidence path for cycle γ. The fixture pairs
each multi-hop question with a list of Wikipedia paragraphs (one
``[title, sentences]`` pair per paragraph), the answer, and the
supporting-fact list that pins which sentences inside which
paragraphs the reasoning chain depends on.

Source
------

The official fixture is hosted at::

    https://www.dropbox.com/s/npidmtadreo6df2/data.zip

with the updated (``evidences_id``-augmented) version available
separately. Operators unpack the zip and point ``cache_dir`` at the
``data/`` directory. The loader expects ``<cache_dir>/<split>.json``.

Schema (verified against the official README)
---------------------------------------------

Each top-level JSON file is a list of dicts::

    {
      "_id":              <str>,
      "question":         <str>,
      "answer":           <str>,                     # absent on test
      "type":             "comparison" |             # 4 categories
                          "inference" |
                          "compositional" |
                          "bridge-comparison",
      "entity_ids":       <str>,                     # gold paragraph
                                                     # Wikidata ids
      "context": [
        [<title>, [<sentence>, ...]],                # one tuple per
        ...                                           # paragraph
      ],
      "supporting_facts": [[<title>, <sent_id:int>], ...],
      "evidences":        [[<subject>, <relation>, <object>], ...],
      "evidences_id":     <list>,                    # certain types
      "answer_id":        <str>,                     # 2020-12 update
    }

Schema mapping (2Wiki → :class:`ExternalQuery`)
-----------------------------------------------

* ``id``         → ``"2wiki-<orig_id>"``
* ``benchmark``  → ``"2wiki"``
* ``question``   → ``entry["question"]``
* ``context``    → tuple of one string per paragraph; each string is
                  ``" ".join(sentences)`` so the scorer sees the
                  paragraph as a single passage but the per-sentence
                  supporting-facts index still maps via
                  ``metadata["context_sentences"]``
* ``gold_answer`` → ``entry["answer"]`` (``""`` on test where the
                   field is absent)
* ``metadata``   → ``{
    "context_titles":     [...],
    "context_sentences":  [[<sent>, ...], ...],     # per-paragraph
                                                    # sentence lists,
                                                    # preserved so the
                                                    # supporting-fact
                                                    # scorer can index
    "supporting_facts":   [[title, sent_id], ...],
    "type":               <str>,                    # comparison /
                                                    # inference /
                                                    # compositional /
                                                    # bridge-comparison
    "entity_ids":         <str>,
    "evidences":          [...],
    "evidences_id":       [...],
    "answer_id":          <str>,
    "split":              "train" | "dev" | "test",
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


WIKIMULTI_SPLITS: Tuple[str, ...] = ("train", "dev", "test")

# Official 4 question-type categories, kept here so a future scorer
# can iterate them with a single import.
WIKIMULTI_TYPES: Tuple[str, ...] = (
    "comparison",
    "inference",
    "compositional",
    "bridge-comparison",
)


def _default_cache_dir() -> Path:
    return Path(__file__).resolve().parent / "_fixtures" / "wikimulti"


def _entry_to_query(
    entry: Dict[str, Any],
    *,
    split: str,
) -> ExternalQuery:
    # 2Wiki uses ``_id`` (note the leading underscore) — fall through
    # the usual candidates only as a defensive fallback.
    orig_id = (entry.get("_id") or entry.get("id") or "").strip() or "noid"

    context_raw = entry.get("context") or []
    context_texts: List[str] = []
    context_titles: List[str] = []
    context_sentences: List[List[str]] = []

    if isinstance(context_raw, list):
        for item in context_raw:
            # Each item is the [title, [sentences]] pair.
            if not (isinstance(item, list) and len(item) >= 2):
                continue
            title, sentences = item[0], item[1]
            if isinstance(sentences, list):
                sents = [str(s) for s in sentences]
            else:
                sents = []
            context_titles.append(str(title))
            context_sentences.append(sents)
            # Join sentences with a single space so the passage reads
            # the way an LLM would consume it. The per-sentence list
            # stays under metadata for the supporting-fact scorer.
            context_texts.append(" ".join(sents))

    metadata: Dict[str, Any] = {
        "context_titles":    context_titles,
        "context_sentences": context_sentences,
        "supporting_facts":  entry.get("supporting_facts") or [],
        "type":              str(entry.get("type") or ""),
        "entity_ids":        str(entry.get("entity_ids") or ""),
        "evidences":         entry.get("evidences") or [],
        "evidences_id":      entry.get("evidences_id") or [],
        "answer_id":         str(entry.get("answer_id") or ""),
        "split":             split,
    }

    return ExternalQuery(
        id=f"2wiki-{orig_id}",
        benchmark="2wiki",
        question=str(entry.get("question", "")),
        context=tuple(context_texts),
        gold_answer=str(entry.get("answer") or ""),
        metadata=metadata,
    )


class WikiMultiLoader(ExternalBenchFixture):
    """Loader for one 2WikiMultiHopQA split.

    Usage::

        loader = WikiMultiLoader(split="dev",
                                  cache_dir=Path("data"))
        queries = loader.iter_queries(n_samples=20)

    Operators populate ``cache_dir`` by downloading the official
    ``data.zip`` from Dropbox and unpacking it. The loader expects
    ``<cache_dir>/<split>.json``.
    """

    def __init__(
        self,
        *,
        split: str = "dev",
        cache_dir: Optional[Path] = None,
    ):
        if split not in WIKIMULTI_SPLITS:
            raise ValueError(
                f"unknown 2WikiMultiHopQA split: {split!r}. "
                f"Valid: {WIKIMULTI_SPLITS}"
            )
        self._split = split
        self._cache_dir = Path(cache_dir) if cache_dir else None

    @property
    def benchmark_id(self) -> str:
        return "2wiki"

    @property
    def split(self) -> str:
        return self._split

    @property
    def cache_path(self) -> Path:
        base = self._cache_dir or _default_cache_dir()
        return base / f"{self._split}.json"

    def iter_queries(
        self,
        *,
        split: Optional[str] = None,
        n_samples: Optional[int] = None,
    ) -> List[ExternalQuery]:
        if split is not None and split != self._split:
            raise ValueError(
                f"split mismatch: loader bound to {self._split!r}, "
                f"caller passed {split!r}"
            )
        path = self.cache_path
        if not path.exists():
            raise FileNotFoundError(
                f"2WikiMultiHopQA fixture not at {path}. Unpack "
                f"data.zip from the Dropbox link and point cache_dir "
                f"at the resulting directory."
            )
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, list):
            raise ValueError(
                f"2WikiMultiHopQA fixture must be a JSON list; got "
                f"{type(raw).__name__}"
            )
        queries = [
            _entry_to_query(e, split=self._split)
            for e in raw if isinstance(e, dict)
        ]
        self.validate_queries(queries)
        return self.take_sample(queries, n_samples)


__all__ = [
    "WIKIMULTI_SPLITS",
    "WIKIMULTI_TYPES",
    "WikiMultiLoader",
]
