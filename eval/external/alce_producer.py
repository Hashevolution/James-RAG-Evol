"""Cycle γ Phase C.3 — ALCE answer producer.

ALCE evaluates a model's ability to emit inline ``[N]``-style
citations alongside its free-text answer. The standard ALCE
evaluation passes the question + top-k retrieved passages to a
single LLM call with an instruction that says "cite for any factual
claim, use [1][2][3] format, at least one citation per sentence."

This producer reproduces that protocol against a local Ollama model
through :class:`core.gemma_client.GemmaClient`. It is a closed-corpus
producer (mirrors the ``ClosedCorpusGemmaProducer`` from
``eval.external.runner``): the model sees only the published
ALCE evidence passages, never JAMES's own retrieval — so the citation
column is a model-capability + prompt-compliance signal, not a
retrieval signal. The cycle γ self-eval-trap rule
([[feedback_self_evaluation_trap]]) forbids "JAMES retrieval is
better" framing on an ALCE row; we use the published retrieval as-is.

The producer does NOT post-process the model's free-text into
ALCE format — the model emits the format directly per the prompt.
If the model fails to comply (no ``[N]`` tokens appear), the ALCE
scorer reports both axes as "axis not measured" with that note in
its output, which is the honest record of the prompt-compliance gap.

The prompt template is verbatim from princeton-nlp/ALCE's
``prompts/asqa_default.json`` (top-of-file instruction block). The
"Document [i]:" numbering follows ALCE's per-passage convention.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

from eval.external import ExternalQuery


# ALCE official prompt instruction (princeton-nlp/ALCE,
# prompts/asqa_default.json::"instruction"). Pinned verbatim so
# operators can audit the prompt against ALCE's published prompt
# directly.
ALCE_INSTRUCTION_DEFAULT = (
    "Instruction: Write an accurate, engaging, and concise answer "
    "for the given question using only the provided search results "
    "(some of which might be irrelevant) and cite them properly. "
    "Use an unbiased and journalistic tone. Always cite for any "
    "factual claim. When citing several search results, use [1][2][3]. "
    "Cite at least one document and at most three documents in each "
    "sentence. If multiple documents support the sentence, only cite "
    "a minimum sufficient subset of the documents."
)


def _format_documents(docs: List[str]) -> str:
    """Render the passage list in ALCE's "Document [i]:" form.

    1-based numbering matches the citation index the scorer expects:
    the model writes ``[1]`` to cite ``Document [1]``, which
    corresponds to ``query.context[0]`` on the loader side.
    """
    return "\n\n".join(
        f"Document [{i + 1}]: {body}" for i, body in enumerate(docs)
    )


class ALCEClosedCorpusProducer:
    """ALCE-prompted closed-corpus producer.

    Args:
        model: Ollama model id (e.g. ``gemma4:e4b``, ``mixtral:8x7b``).
        n_docs: Number of evidence passages to include in the prompt
            (top-k from ``query.context``). ALCE's official baselines
            run with 5; the pre-registration locks this at 5 for the
            smoke. Operators wanting a different setting must amend
            the pre-registration first.
        max_tokens: Generation budget.
        timeout: Per-call timeout (seconds).
        think: Pass ``think=True`` to GemmaClient for models that
            emit a hidden thinking trace (gemma4:e4b family).
        instruction: Override the default ALCE instruction. The pinned
            default is verbatim from the upstream ``asqa_default``
            prompt; deviating from it requires a pre-reg amendment.
        max_prompt_chars: Override GemmaClient's per-call prompt cap.
            ALCE's top-5 passages can total 5-20k characters; the
            default 4k cap silently truncates evidence
            ([[feedback_synth_context_1000_truncation_rootcause]]).
    """

    name = "alce-closed-corpus"

    def __init__(
        self,
        *,
        model: str = "gemma4:e4b",
        n_docs: int = 5,
        max_tokens: int = 1024,
        timeout: int = 180,
        think: bool = False,
        instruction: str = ALCE_INSTRUCTION_DEFAULT,
        max_prompt_chars: int = 100_000,
    ):
        if n_docs < 1:
            raise ValueError(f"n_docs must be >= 1; got {n_docs!r}")
        self._model = model
        self._n_docs = n_docs
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._think = think
        self._instruction = instruction
        self._max_prompt_chars = max_prompt_chars

    def _prompt(self, query: ExternalQuery) -> str:
        docs = list(query.context)[: self._n_docs]
        return (
            f"{self._instruction}\n\n"
            f"Question: {query.question}\n\n"
            f"Search Results:\n{_format_documents(docs)}\n\n"
            f"Answer:"
        )

    def produce(self, query: ExternalQuery) -> Dict[str, Any]:
        from core.gemma_client import GemmaClient  # late import

        # GemmaClient reads JAMES_GEMMA_MAX_PROMPT_CHARS per-call;
        # ALCE evidence blocks routinely exceed the 4k default cap and
        # silent truncation would invalidate the citation axes.
        os.environ["JAMES_GEMMA_MAX_PROMPT_CHARS"] = str(
            self._max_prompt_chars
        )

        client = GemmaClient()
        ans = client.call_gemma(
            self._prompt(query),
            model=self._model,
            max_tokens=self._max_tokens,
            think=self._think,
            use_cache=False,
            timeout=self._timeout,
        )

        # n_docs locked in result row so the scorer + audit have an
        # in-band record of how many citation indices were valid.
        return {
            "id":     query.id,
            "answer": ans,
            "mode":   "alce-closed-corpus",
            "model":  self._model,
            "n_docs": self._n_docs,
        }


__all__ = [
    "ALCE_INSTRUCTION_DEFAULT",
    "ALCEClosedCorpusProducer",
]
