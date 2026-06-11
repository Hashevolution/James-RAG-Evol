"""Cycle γ D-2wiki — supporting-fact-aware closed-corpus producer.

The C.4 smoke producer (`ClosedCorpusGemmaProducer`) emits answer text only;
the existing `WikiMultiScorer.support_fact_f1` axis therefore reports
"not measured by design". D-2wiki promotes the cell to research-tier by
prompting the model for citation markers AND parsing them into the
``predicted_supporting_facts: [[title, sent_id], …]`` shape the scorer
already consumes.

**Honest tier**: ⭐ research-tier (small open model citation accuracy
gate). NOT publication-grade — small-model citation precision is a known
weak axis (RAG citations literature 2024+). The producer measures
*citation emission infrastructure*, not state-of-the-art citation
quality. Larger / instruction-tuned cited models are a separate cycle
(E-2wiki).

**Prompt design** (small-model-friendly):
  * Paragraphs are enumerated with title + zero-indexed sentence numbers.
  * Answer + `SUPPORTING_FACTS: [Title #N], [Title #N]` line.
  * Tolerant parser: drops invalid citations, no fail-hard.

**Self-eval trap rule** (memory ``feedback_self_evaluation_trap``):
the producer parses the model's own citations against an external
fixture's gold supporting facts; the scorer's set-F1 is the external
authority, not the model's confidence in its own citations.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Tuple

from eval.external.base import ExternalQuery


# ──────────────────────────────────────────────────────────────────────
# Citation parser (LLM-free; testable without GemmaClient)
# ──────────────────────────────────────────────────────────────────────


# Captures `[Title text #42]` / `[Title text   #  42]` / `[ Title #0 ]`.
# Title is anything that's not a closing bracket, trimmed; sent_id is
# the first non-negative integer immediately after `#`.
_CITATION_RE = re.compile(r"\[\s*([^\]]+?)\s*#\s*(\d+)\s*\]")

# Locates the supporting-facts section anchor. Tolerant of small case /
# punctuation variants the model may emit. Anchored at line start to
# avoid matching the phrase inside the prompt echo.
_SF_ANCHOR_RE = re.compile(
    r"(?im)^\s*supporting[\s_]?facts\s*:?\s*",
)


def _split_at_supporting_facts(text: str) -> Tuple[str, str]:
    """Splits the model completion into (answer_segment, sf_segment).

    If no anchor is found, the whole text is the answer and the SF
    segment is empty. The anchor line itself is stripped from the
    answer side so the answer-axis EM/F1 isn't polluted by the
    citation list.
    """
    if not isinstance(text, str):
        return "", ""
    m = _SF_ANCHOR_RE.search(text)
    if m is None:
        return text.strip(), ""
    answer = text[:m.start()].rstrip()
    sf_segment = text[m.end():]
    return answer, sf_segment


def parse_supporting_facts(
    completion: str,
    *,
    context_titles: List[str],
    context_sentences: List[List[str]],
) -> List[List[Any]]:
    """Returns the validated list of ``[title, sent_id:int]`` pairs.

    Validation rules (tolerant, drop-on-fail, no exceptions):
      * Title must appear in ``context_titles`` (case-sensitive — the
        prompt feeds exact titles, so this catches hallucinated names).
      * ``sent_id`` must be an int in ``[0, len(context_sentences[i]))``
        for the matching paragraph index.
      * Duplicates are deduplicated (set semantics — the scorer's
        ``_set_f1`` collapses repeats anyway).

    The deduped list preserves first-occurrence order so the bench
    row's audit trail mirrors the model's emission order.
    """
    if not isinstance(completion, str):
        return []
    _, sf_segment = _split_at_supporting_facts(completion)
    if not sf_segment:
        return []

    title_to_idx = {t: i for i, t in enumerate(context_titles)}
    seen = set()
    out: List[List[Any]] = []

    for m in _CITATION_RE.finditer(sf_segment):
        title = m.group(1).strip()
        try:
            sent_id = int(m.group(2))
        except ValueError:
            continue
        idx = title_to_idx.get(title)
        if idx is None:
            continue
        sentences = context_sentences[idx] if 0 <= idx < len(
            context_sentences) else []
        if sent_id < 0 or sent_id >= len(sentences):
            continue
        key = (title, sent_id)
        if key in seen:
            continue
        seen.add(key)
        out.append([title, sent_id])

    return out


def _format_paragraph(idx: int, title: str, sentences: List[str]) -> str:
    """Single paragraph block: title + 0-indexed sentences."""
    lines = [f"[{idx}] Title: {title}"]
    for sid, sent in enumerate(sentences):
        lines.append(f"  #{sid}: {sent}")
    return "\n".join(lines)


def build_cited_prompt(query: ExternalQuery) -> str:
    """Build the supporting-fact-aware prompt.

    Reads `metadata.context_titles` + `metadata.context_sentences`; if
    either is absent the producer falls back to numbered paragraphs
    with empty title (the parser will drop all citations, axis goes to
    0 — honest under-attribution rather than a crash).
    """
    titles = list(query.metadata.get("context_titles") or [])
    sentences = list(query.metadata.get("context_sentences") or [])
    n = max(len(titles), len(sentences))

    paragraphs: List[str] = []
    for i in range(n):
        title = titles[i] if i < len(titles) else f"Paragraph {i+1}"
        sents = sentences[i] if i < len(sentences) else []
        paragraphs.append(_format_paragraph(i + 1, title, sents))

    paragraph_block = "\n\n".join(paragraphs)

    return (
        "You are answering a multi-hop question using the provided "
        "paragraphs. Each paragraph has a Title and zero-indexed "
        "sentences (#0, #1, ...).\n\n"
        f"Paragraphs:\n{paragraph_block}\n\n"
        f"Question: {query.question}\n\n"
        "Answer the question concisely on the first line. If the "
        "context is insufficient, answer 'Insufficient Information'.\n\n"
        "Then on a NEW line, list every paragraph-sentence that "
        "supported your answer in this EXACT format:\n"
        "SUPPORTING_FACTS: [<Title> #<sent_id>], [<Title> #<sent_id>]\n"
        "If your answer is 'Insufficient Information', emit "
        "'SUPPORTING_FACTS:' with no citations.\n"
    )


# ──────────────────────────────────────────────────────────────────────
# Producer
# ──────────────────────────────────────────────────────────────────────


class WikiMultiCitedProducer:
    """Closed-corpus 2Wiki producer that emits ``predicted_supporting_facts``.

    The producer is structurally identical to
    `eval.external.runner.ClosedCorpusGemmaProducer` (lazy `GemmaClient`
    import, env-var prompt cap), but:

      * the prompt is supporting-fact-aware (`build_cited_prompt`), and
      * the bench row carries ``predicted_supporting_facts``,
        ``raw_completion``, and ``mode = closed-corpus-cited``.

    The answer-axis EM/F1 reads from the stripped-of-citations answer
    segment so the existing answer scorer isn't polluted by the
    `SUPPORTING_FACTS:` line.
    """

    name = "closed-corpus-cited-2wiki"

    def __init__(
        self,
        *,
        model: str = "gemma4:e4b",
        max_tokens: int = 1024,
        timeout: int = 180,
        think: bool = False,
        use_cache: bool = False,
        max_prompt_chars: int = 200_000,
    ):
        self._model = model
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._think = think
        self._use_cache = use_cache
        self._max_prompt_chars = max_prompt_chars

    def produce(self, query: ExternalQuery) -> Dict[str, Any]:
        from core.gemma_client import GemmaClient   # late import

        prompt = build_cited_prompt(query)

        os.environ["JAMES_GEMMA_MAX_PROMPT_CHARS"] = str(
            self._max_prompt_chars
        )
        client = GemmaClient()
        raw = client.call_gemma(
            prompt,
            model=self._model,
            max_tokens=self._max_tokens,
            think=self._think,
            use_cache=self._use_cache,
            timeout=self._timeout,
        )

        answer_segment, _ = _split_at_supporting_facts(raw)
        supporting_facts = parse_supporting_facts(
            raw,
            context_titles=list(query.metadata.get("context_titles") or []),
            context_sentences=list(
                query.metadata.get("context_sentences") or []),
        )

        return {
            "id":                          query.id,
            "answer":                      answer_segment,
            "predicted_supporting_facts":  supporting_facts,
            "raw_completion":              raw,
            "sources":                     list(query.context[:1])
                                           if query.context else [],
            "mode":                        "closed-corpus-cited",
            "model":                       self._model,
        }


__all__ = [
    "WikiMultiCitedProducer",
    "build_cited_prompt",
    "parse_supporting_facts",
]
