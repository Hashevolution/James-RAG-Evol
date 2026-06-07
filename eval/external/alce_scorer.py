"""Cycle γ Phase A.4.4 — ALCE scorer (citation precision/recall).

ALCE's headline metric is **citation precision/recall**: for each
sentence in the model's answer, does at least one of the cited
passages support the claim (NLI entailment)? The official
``eval.py`` uses a T5-XXL NLI model (``google/t5_xxl_true_nli_mixture``)
to verify entailment; we expose the verifier as a pluggable
callable so the runtime dependency stays optional.

Pluggable backend (Decision LOCK)
----------------------------------

The scorer takes an :class:`NLIVerifier` instance at construction:

* :class:`StringContainmentVerifier` — default fallback. Token
  overlap above a threshold counts as "entailment". **NOT
  ALCE-grade** — the :attr:`ScoreAxis.notes` field records this
  prominently so the cycle γ report cannot accidentally claim
  ALCE-grade scores from the fallback alone.

* HuggingFace NLI verifier (not in this PR) — operators pass a
  callable that wraps a transformers pipeline. The interface is
  ``verify(premise, hypothesis) -> bool``; nothing in this module
  imports transformers.

The default is the fallback so the import path stays
dependency-free; operators who care about ALCE-grade precision pass
their own verifier.

Variant-specific correctness axes (ASQA short-answer match, QAMPARI
list precision/recall, ELI5 claim recall) live in a follow-up PR —
this one ships the *citation* axes only, which are the headline
publication evidence for cycle γ's ABAC + replay angle.

Self-eval trap rule (memory ``feedback_self_evaluation_trap``):
the fallback is honest about being a fallback. The scorer will
*not* claim ALCE-grade scores when the verifier is the default.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Protocol

from eval.external import ScoreAxis
from eval.external.alce_loader import ALCE_VARIANTS
from eval.external.scorer_base import ExternalScorer


# Maps ALCE_VARIANTS to the full benchmark id the loader emits.
def _benchmark_id_for(variant: str) -> str:
    return f"alce-{variant}"


# ─── NLI verifier interface ────────────────────────────────────────


class NLIVerifier(Protocol):
    """Protocol every ALCE backend implements.

    A verifier returns ``True`` when ``premise`` is judged to entail
    ``hypothesis``. The interface is intentionally narrow — boolean
    so the scorer's downstream maths stays unambiguous, and free
    of any tensor / batching concerns so a future transformers
    backend can implement it with a single function.
    """

    def verify(self, premise: str, hypothesis: str) -> bool: ...

    @property
    def is_alce_grade(self) -> bool: ...

    @property
    def name(self) -> str: ...


class StringContainmentVerifier:
    """Default backend — naive token-overlap fallback.

    A claim is considered "entailed" by a passage when at least
    ``min_overlap`` content tokens (lowercased, alphanumeric) from
    the claim appear in the passage. The threshold is intentionally
    lenient (default 0.5 of the claim's tokens) so the fallback
    behaves like a *generous baseline*: it rarely flags real
    entailments as misses, but it also lets through many
    non-entailments. The scorer surfaces this trade-off in its
    ``notes`` field.

    NOT ALCE-grade — operators must pass a real NLI verifier
    (HuggingFace transformers wrapper) to publish ALCE numbers.
    """

    def __init__(self, *, min_overlap: float = 0.5):
        if not (0.0 < min_overlap <= 1.0):
            raise ValueError(
                f"min_overlap must be in (0.0, 1.0]; got {min_overlap!r}"
            )
        self._min_overlap = min_overlap

    @property
    def name(self) -> str:
        return f"string-containment(min_overlap={self._min_overlap})"

    @property
    def is_alce_grade(self) -> bool:
        return False

    def verify(self, premise: str, hypothesis: str) -> bool:
        if not isinstance(premise, str) or not isinstance(hypothesis, str):
            return False
        prem = _content_tokens(premise)
        hyp = _content_tokens(hypothesis)
        if not hyp:
            # Vacuous hypothesis — count as entailed (the claim
            # carries no content to falsify).
            return True
        if not prem:
            return False
        overlap = len([t for t in hyp if t in prem])
        return (overlap / len(hyp)) >= self._min_overlap


# ─── Helpers ───────────────────────────────────────────────────────


_TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def _content_tokens(s: str) -> set:
    """Lowercase alphanumeric tokens, deduplicated."""
    return set(t.lower() for t in _TOKEN.findall(s))


# ALCE citation format: ``[1]``, ``[2, 3]``, ``[ 4 ]``, etc.
# The official eval.py uses ``re.findall(r'\[\d+'...)``; we mirror
# that with a slightly looser comma-list parser so ``[1,2]`` /
# ``[1, 2]`` round-trip into a list of ints.
_CITATION_GROUP = re.compile(r"\[([0-9, ]+)\]")


def _extract_citations(text: str) -> List[List[int]]:
    """For each citation group in the text, return the list of
    1-based indices it cites.

    Example::

        _extract_citations("Foo [1]. Bar [2, 3].")
        # → [[1], [2, 3]]

    Indices below 1 are silently dropped (ALCE indices are
    1-based). Returns an empty list when no citations appear.
    """
    if not isinstance(text, str):
        return []
    groups: List[List[int]] = []
    for m in _CITATION_GROUP.finditer(text):
        items = [tok.strip() for tok in m.group(1).split(",")]
        idxs: List[int] = []
        for it in items:
            if it.isdigit():
                n = int(it)
                if n >= 1:
                    idxs.append(n)
        if idxs:
            groups.append(idxs)
    return groups


# Sentence split — naïve but adequate for ALCE's citation-per-
# statement formula. Production may want spaCy / nltk; the
# minimum-viable scorer keeps the dependency surface flat.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\(\[\"])")


def _split_sentences(text: str) -> List[str]:
    if not isinstance(text, str):
        return []
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(text)]
    return [p for p in parts if p]


def _resolve_model_answer(row: Dict[str, Any]) -> str:
    for key in ("answer", "output", "prediction"):
        val = row.get(key)
        if isinstance(val, str):
            return val
    return ""


def _strip_citations(text: str) -> str:
    """Remove every ``[1]`` / ``[2, 3]`` token from a sentence so
    the NLI hypothesis is just the claim, not the citation markup."""
    return _CITATION_GROUP.sub("", text).strip()


# ─── Scorer ────────────────────────────────────────────────────────


class ALCEScorer(ExternalScorer):
    """ALCE scorer for one variant (``asqa`` / ``qampari`` /
    ``eli5``)."""

    def __init__(
        self,
        *,
        variant: str = "asqa",
        verifier: Optional[NLIVerifier] = None,
    ):
        if variant not in ALCE_VARIANTS:
            raise ValueError(
                f"unknown ALCE variant: {variant!r}. "
                f"Valid: {ALCE_VARIANTS}"
            )
        self._variant = variant
        self._verifier: NLIVerifier = verifier or StringContainmentVerifier()

    @property
    def benchmark_id(self) -> str:
        return _benchmark_id_for(self._variant)

    @property
    def variant(self) -> str:
        return self._variant

    @property
    def verifier(self) -> NLIVerifier:
        return self._verifier

    def score(
        self,
        queries: Iterable["Any"],
        bench_rows: List[Dict[str, Any]],
    ) -> List[ScoreAxis]:
        queries = list(queries)
        self.validate_queries(queries)
        idx = self.index_rows_by_id(bench_rows)

        # Citation-precision bookkeeping: per-citation entailment.
        cite_correct = 0
        cite_total = 0
        # Citation-recall bookkeeping: per-sentence-with-citation.
        sent_supported = 0
        sent_with_citation = 0

        per_query_prec: Dict[str, float] = {}
        per_query_rec:  Dict[str, float] = {}

        for q in queries:
            row = idx.get(q.id)
            if row is None:
                continue
            answer = _resolve_model_answer(row)
            sentences = _split_sentences(answer)
            if not sentences:
                continue

            # Each ALCE row's context is the doc list the citations
            # index into (1-based). Tuple → list for index access.
            docs = list(q.context)

            q_cite_correct = 0
            q_cite_total = 0
            q_sent_supported = 0
            q_sent_with_citation = 0

            for sent in sentences:
                cite_groups = _extract_citations(sent)
                if not cite_groups:
                    continue   # citation-recall denominator excludes
                                # uncited sentences; citation-precision
                                # has no citations to score
                q_sent_with_citation += 1
                hypothesis = _strip_citations(sent)
                # Flatten every citation group's indices into one
                # union — ALCE precision treats each citation
                # individually but recall asks whether AT LEAST ONE
                # citation supports the sentence.
                all_idxs: List[int] = []
                for grp in cite_groups:
                    all_idxs.extend(grp)
                # Citation precision: per-citation entailment.
                sentence_supported_by_any = False
                for cidx in all_idxs:
                    q_cite_total += 1
                    # 1-based → 0-based; out-of-range citations
                    # count as unsupported.
                    if 1 <= cidx <= len(docs):
                        premise = docs[cidx - 1]
                        if self._verifier.verify(premise, hypothesis):
                            q_cite_correct += 1
                            sentence_supported_by_any = True
                if sentence_supported_by_any:
                    q_sent_supported += 1

            cite_correct += q_cite_correct
            cite_total += q_cite_total
            sent_supported += q_sent_supported
            sent_with_citation += q_sent_with_citation

            per_query_prec[q.id] = (
                round(q_cite_correct / q_cite_total, 4)
                if q_cite_total else 0.0
            )
            per_query_rec[q.id] = (
                round(q_sent_supported / q_sent_with_citation, 4)
                if q_sent_with_citation else 0.0
            )

        verifier_note = (
            f"verifier={self._verifier.name}; "
            f"is_alce_grade={self._verifier.is_alce_grade}. "
        )
        if not self._verifier.is_alce_grade:
            verifier_note += (
                "DEFAULT FALLBACK — NOT ALCE-grade. Pass a real NLI "
                "verifier (e.g. T5-XXL TRUE NLI Mixture) for "
                "publishable ALCE scores."
            )

        axes: List[ScoreAxis] = []

        if cite_total > 0:
            axes.append(ScoreAxis(
                name="citation_precision",
                score=round(cite_correct / cite_total, 4),
                n_queries=len(per_query_prec),
                per_query=per_query_prec,
                notes=verifier_note,
            ))
        else:
            axes.append(ScoreAxis(
                name="citation_precision", score=0.0, n_queries=0,
                notes="no citations [n] present in any model answer; "
                      "axis not measured. " + verifier_note,
            ))

        if sent_with_citation > 0:
            axes.append(ScoreAxis(
                name="citation_recall",
                score=round(sent_supported / sent_with_citation, 4),
                n_queries=len(per_query_rec),
                per_query=per_query_rec,
                notes=verifier_note,
            ))
        else:
            axes.append(ScoreAxis(
                name="citation_recall", score=0.0, n_queries=0,
                notes="no sentences with citations in any model answer; "
                      "axis not measured. " + verifier_note,
            ))

        return axes


__all__ = [
    "ALCEScorer",
    "NLIVerifier",
    "StringContainmentVerifier",
]
