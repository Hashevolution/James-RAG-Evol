"""Cycle γ Phase A.2 — ALCE (Gao et al. 2023) loader.

ALCE = Automatic LLM Citation Evaluation. Three sub-benchmarks:

* **ASQA**    — ambiguous QA with multiple acceptable short answers
                + a reference long answer + annotated QA pairs.
* **QAMPARI** — list-based answers (each question has multiple
                acceptable answer groups).
* **ELI5**    — long-form explanation with atomic claims for
                NLI-based citation verification.

Citation precision/recall is the headline metric (the per-bench
scorer in A.4 implements it). The loader's job is just to lift the
published fixture rows into the unified :class:`ExternalQuery`
shape without rewriting any of them — the citation-eval logic lives
downstream.

Source
------

ALCE publishes the fixtures as a single tarball on HuggingFace:

    https://huggingface.co/datasets/princeton-nlp/ALCE-data/resolve/main/ALCE-data.tar

The tarball expands into a ``data/`` directory with one JSON per
variant + retriever. The loader doesn't unpack tarballs itself —
that adds non-trivial code for a one-time bootstrap. Operators run
the official ``download_data.sh`` (or unpack the tarball manually)
and point ``cache_dir`` at the resulting directory. The loader then
reads ``<cache_dir>/<expected_filename>``.

Per-variant expected filenames (verified against ALCE's ``eval.py``
default flags):

* ASQA    → ``asqa_eval_gtr_top100.json``
* QAMPARI → ``qampari_eval_gtr_top100.json``
* ELI5    → ``eli5_eval_bm25_top100.json``

Schema mapping (per variant)
----------------------------

The three variants have different gold-answer shapes; the unified
schema absorbs them with a per-variant ``_entry_to_query_*`` helper
and routes the remainder under ``metadata``:

* ASQA:
    ``id``         → ``"alce-asqa-<sample_id>"``
    ``benchmark``  → ``"alce-asqa"``
    ``question``   → ``entry["question"]``
    ``context``    → tuple(doc["text"] for doc in entry["docs"])
    ``gold_answer`` → primary short answer (first qa_pair's first
                     ``short_answers`` entry)
    ``metadata``   → ``qa_pairs`` / ``annotations`` /
                    ``docs_titles`` / variant / retriever

* QAMPARI:
    ``id``         → ``"alce-qampari-<sample_id>"``
    ``benchmark``  → ``"alce-qampari"``
    ``question``   → ``entry["question"]``
    ``context``    → tuple(doc["text"])
    ``gold_answer`` → first answer of the first answer group
    ``metadata``   → ``answers`` (list of lists, preserved) /
                    ``docs_titles`` / variant / retriever

* ELI5:
    ``id``         → ``"alce-eli5-<sample_id>"``
    ``benchmark``  → ``"alce-eli5"``
    ``question``   → ``entry["question"]``
    ``context``    → tuple(doc["text"])
    ``gold_answer`` → ``entry["answer"]`` (the reference long answer)
    ``metadata``   → ``claims`` (atomic claims for NLI scoring) /
                    ``docs_titles`` / variant / retriever

Self-eval trap rule (memory ``feedback_self_evaluation_trap``):
the loader does NOT rewrite questions, does NOT curate a subset,
does NOT recompute gold labels. Every byte of the source row
either lands in :class:`ExternalQuery` directly or under
``metadata`` for the A.4 scorer.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from eval.external.base import ExternalBenchFixture, ExternalQuery


# ─── Variant registry (mirrors ALCE's eval.py default flags) ─────────


@dataclass(frozen=True)
class _AlceVariantConfig:
    """Per-variant filename + retriever id.

    The filename is what ``download_data.sh`` writes to ``data/``;
    the retriever id is recorded under ``metadata.retriever`` so a
    cross-bench analysis can group results by retrieval setup.
    """
    filename:  str
    retriever: str


_VARIANTS: Dict[str, _AlceVariantConfig] = {
    "asqa":    _AlceVariantConfig("asqa_eval_gtr_top100.json",    "gtr"),
    "qampari": _AlceVariantConfig("qampari_eval_gtr_top100.json", "gtr"),
    "eli5":    _AlceVariantConfig("eli5_eval_bm25_top100.json",   "bm25"),
}

ALCE_VARIANTS: Tuple[str, ...] = tuple(_VARIANTS.keys())


# ─── Shared helpers ────────────────────────────────────────────────


def _extract_docs(entry: Dict[str, Any]) -> Tuple[Tuple[str, ...],
                                                    List[str]]:
    """Return ``(context_texts, titles)`` for one entry.

    The loader keeps the doc *texts* under ``context`` (so the scorer
    can resolve a citation ``[1]`` back to its passage) and the
    *titles* under ``metadata["docs_titles"]`` (for forensic
    inspection / by-source aggregation downstream).
    """
    docs = entry.get("docs") or []
    if not isinstance(docs, list):
        return (), []
    texts: List[str] = []
    titles: List[str] = []
    for d in docs:
        if not isinstance(d, dict):
            continue
        # ALCE's eval.py accepts both 'text' (passage body) and
        # 'sent' (QA-extracted sentence) — prefer the longer body.
        body = d.get("text") or d.get("sent") or ""
        title = d.get("title") or ""
        texts.append(str(body))
        titles.append(str(title))
    return tuple(texts), titles


def _resolve_id(entry: Dict[str, Any]) -> str:
    """ALCE rows usually carry ``sample_id`` (ASQA / QAMPARI /
    ELI5 all share this key). Fall back to ``question_id`` or a
    positional placeholder if the source row lacks it — validate_
    queries surfaces the rest."""
    for key in ("sample_id", "question_id", "id"):
        val = entry.get(key)
        if val is not None:
            return str(val)
    return "noid"


# ─── Per-variant mappers ───────────────────────────────────────────


def _entry_to_query_asqa(entry: Dict[str, Any]) -> ExternalQuery:
    sid = _resolve_id(entry)
    qa_pairs = entry.get("qa_pairs") or []
    # Primary short answer = first qa_pair's first short_answers entry.
    primary = ""
    if isinstance(qa_pairs, list) and qa_pairs:
        first = qa_pairs[0] if isinstance(qa_pairs[0], dict) else {}
        shorts = first.get("short_answers") or []
        if isinstance(shorts, list) and shorts:
            primary = str(shorts[0])
    texts, titles = _extract_docs(entry)
    cfg = _VARIANTS["asqa"]
    metadata: Dict[str, Any] = {
        "qa_pairs":    qa_pairs,
        "annotations": entry.get("annotations") or [],
        "docs_titles": titles,
        "variant":     "asqa",
        "retriever":   cfg.retriever,
    }
    return ExternalQuery(
        id=f"alce-asqa-{sid}",
        benchmark="alce-asqa",
        question=str(entry.get("question", "")),
        context=texts,
        gold_answer=primary,
        metadata=metadata,
    )


def _entry_to_query_qampari(entry: Dict[str, Any]) -> ExternalQuery:
    sid = _resolve_id(entry)
    answers = entry.get("answers") or []
    primary = ""
    # QAMPARI answers are a list of answer-groups; each group is a list
    # of acceptable strings for one "slot" in the list-answer. We pick
    # the first group's first string for the primary; the full
    # structure stays under metadata for the scorer.
    if isinstance(answers, list) and answers:
        first_group = answers[0]
        if isinstance(first_group, list) and first_group:
            primary = str(first_group[0])
        elif isinstance(first_group, str):
            primary = first_group
    texts, titles = _extract_docs(entry)
    cfg = _VARIANTS["qampari"]
    metadata: Dict[str, Any] = {
        "answers":     answers,
        "docs_titles": titles,
        "variant":     "qampari",
        "retriever":   cfg.retriever,
    }
    return ExternalQuery(
        id=f"alce-qampari-{sid}",
        benchmark="alce-qampari",
        question=str(entry.get("question", "")),
        context=texts,
        gold_answer=primary,
        metadata=metadata,
    )


def _entry_to_query_eli5(entry: Dict[str, Any]) -> ExternalQuery:
    sid = _resolve_id(entry)
    texts, titles = _extract_docs(entry)
    cfg = _VARIANTS["eli5"]
    metadata: Dict[str, Any] = {
        "claims":      entry.get("claims") or [],
        "docs_titles": titles,
        "variant":     "eli5",
        "retriever":   cfg.retriever,
    }
    return ExternalQuery(
        id=f"alce-eli5-{sid}",
        benchmark="alce-eli5",
        question=str(entry.get("question", "")),
        context=texts,
        gold_answer=str(entry.get("answer") or ""),
        metadata=metadata,
    )


_MAPPERS: Dict[str, Callable[[Dict[str, Any]], ExternalQuery]] = {
    "asqa":    _entry_to_query_asqa,
    "qampari": _entry_to_query_qampari,
    "eli5":    _entry_to_query_eli5,
}


# Sanity at import time: every variant has a mapper. A future
# _VARIANTS entry that forgets to register a mapper here becomes a
# load-time error rather than silently dropping rows.
assert set(_MAPPERS) == set(_VARIANTS), (
    "every ALCE variant must have an entry in _MAPPERS"
)


# ─── Loader ────────────────────────────────────────────────────────


def _default_cache_dir() -> Path:
    """Loader-local cache (``eval/external/_fixtures/alce/``).
    Operators normally point at ALCE's ``data/`` directory instead;
    this default just exists for the rare git-cloned-fixtures case.
    """
    return Path(__file__).resolve().parent / "_fixtures" / "alce"


class ALCELoader(ExternalBenchFixture):
    """Loader for one ALCE variant (``asqa`` / ``qampari`` / ``eli5``).

    Usage::

        loader = ALCELoader(variant="asqa", cache_dir=Path("data"))
        queries = loader.iter_queries(n_samples=20)   # Phase B smoke
        # or:
        queries = loader.iter_queries()               # full split

    The loader expects ``cache_dir/<filename>`` to exist on disk —
    typically populated by running ALCE's official ``download_data.
    sh`` and pointing ``cache_dir`` at the resulting ``data/``
    directory. Auto-download from the HuggingFace tarball is NOT
    implemented here (the bootstrap is a single ``bash``
    invocation; pulling + unpacking a tarball would just duplicate
    that with more failure modes).
    """

    def __init__(
        self,
        *,
        variant: str = "asqa",
        cache_dir: Optional[Path] = None,
    ):
        if variant not in _VARIANTS:
            raise ValueError(
                f"unknown ALCE variant: {variant!r}. "
                f"Valid: {ALCE_VARIANTS}"
            )
        self._variant = variant
        self._cache_dir = Path(cache_dir) if cache_dir else None

    @property
    def benchmark_id(self) -> str:
        return f"alce-{self._variant}"

    @property
    def variant(self) -> str:
        return self._variant

    @property
    def cache_path(self) -> Path:
        base = self._cache_dir or _default_cache_dir()
        return base / _VARIANTS[self._variant].filename

    def iter_queries(
        self,
        *,
        split: str = "dev",
        n_samples: Optional[int] = None,
    ) -> List[ExternalQuery]:
        path = self.cache_path
        if not path.exists():
            raise FileNotFoundError(
                f"ALCE {self._variant!r} fixture not at {path}. "
                f"Run ALCE's `bash download_data.sh` and point "
                f"cache_dir at the resulting data/ directory."
            )
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)

        if isinstance(raw, dict) and "data" in raw:
            # ALCE wraps the actual rows under a top-level "data" key
            # in some variants; unwrap so the mapper sees the flat list.
            raw = raw["data"]
        if not isinstance(raw, list):
            raise ValueError(
                f"ALCE {self._variant!r} fixture must be a JSON list "
                f"(or a dict with a 'data' list); got "
                f"{type(raw).__name__}"
            )

        mapper = _MAPPERS[self._variant]
        queries = [mapper(e) for e in raw if isinstance(e, dict)]
        self.validate_queries(queries)
        return self.take_sample(queries, n_samples)


__all__ = [
    "ALCE_VARIANTS",
    "ALCELoader",
]
