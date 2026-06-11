"""LRB v0.2.4 — atomic claim extractor.

Per prereg `docs/research/v024-hr-nli-axis-preregistration-2026-06-11.md`
§2:

  * Rule-based extraction (deterministic primary): sentence-split +
    compound-sentence decomposition
  * LLM augmentation (deterministic secondary, temperature=0): rule-
    based 가 split 못 한 sentence 는 LLM 으로 분해
  * Cap: per-answer max 10 atomic claims

Determinism: regex-based sentence boundaries + deterministic compound-
clause split. LLM augmentation uses the same dispatch as llm_rerank
(seed=42, temperature=0).
"""
from __future__ import annotations

import json
import re
from typing import List, Optional

from .llm_rerank import _call_ollama, _is_claude_model, _is_ollama_model

# ──────────────────────────────────────────────────────────────────────
# Rule-based decomposition
# ──────────────────────────────────────────────────────────────────────

_SENT_END = re.compile(r'(?<=[.!?])\s+(?=[A-Z\[\("\']|$)')
_COMPOUND_SPLIT = re.compile(
    r'\s+(?:and|but|however|while|whereas|having|though|although)\s+',
    re.IGNORECASE,
)
_CLAUSE_SUBORD = re.compile(
    r'\s*,?\s+(?:because|since|after|before|when|until)\s+',
    re.IGNORECASE,
)

MAX_CLAIMS_PER_ANSWER = 10
MAX_CLAIM_CHARS = 200
MIN_CLAIM_CHARS = 5


def _sentence_split(text: str) -> List[str]:
    if not text or not text.strip():
        return []
    parts = _SENT_END.split(text.strip())
    return [p.strip() for p in parts if p.strip()]


def _compound_decompose(sentence: str) -> List[str]:
    """Split on coordinating + selected subordinating conjunctions."""
    parts = _COMPOUND_SPLIT.split(sentence)
    out: List[str] = []
    for part in parts:
        sub = _CLAUSE_SUBORD.split(part)
        out.extend(s.strip(" .,;") for s in sub if s.strip())
    return out


def _clean(claim: str) -> str:
    """Drop leading conjunctions / fillers; ensure terminal period."""
    c = claim.strip()
    for prefix in ("and ", "but ", "however, ", "however ",
                    "while ", "whereas ", "though ", "although "):
        if c.lower().startswith(prefix):
            c = c[len(prefix):].strip()
    if c and c[-1] not in ".!?":
        c = c + "."
    return c


def _filter_valid(claims: List[str]) -> List[str]:
    """Drop too-short, too-long, or empty claims. De-dup preserving order."""
    seen = set()
    out: List[str] = []
    for c in claims:
        if not (MIN_CLAIM_CHARS <= len(c) <= MAX_CLAIM_CHARS):
            continue
        key = c.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out[:MAX_CLAIMS_PER_ANSWER]


# ──────────────────────────────────────────────────────────────────────
# LLM augmentation
# ──────────────────────────────────────────────────────────────────────


_LLM_AUG_PROMPT = """Decompose the sentence into a list of atomic factual claims.

An atomic claim is a single simple proposition (subject-predicate-object
or equivalent). Each claim must stand alone (no pronouns referring back
to previous claims).

Sentence: {sentence}

Return ONLY a JSON object of the form:
  {{"claims": ["<claim 1>", "<claim 2>", ...]}}

Output nothing else."""


def _llm_decompose(sentence: str, *, model: str,
                    ollama_url: str = "http://localhost:11434",
                    timeout: float = 30.0) -> List[str]:
    """LLM-based decomposition. Deterministic (temp=0, seed=42).

    Falls back to [sentence] if model fails / JSON parse fails."""
    if not _is_ollama_model(model):
        # Claude path not wired yet for claim extraction (operator
        # action). Fallback to rule-based only.
        return [sentence]

    prompt = _LLM_AUG_PROMPT.format(sentence=sentence)
    text = _call_ollama(prompt, model=model, ollama_url=ollama_url,
                        timeout=timeout)
    if not text:
        return [sentence]

    # _call_ollama returns parsed score list — but we want raw text.
    # Need a different ollama call that returns raw text. Implement
    # inline for now.
    import urllib.error
    import urllib.request

    payload = {
        "model":   model,
        "prompt":  prompt,
        "stream":  False,
        "format":  "json",
        "options": {"temperature": 0.0, "seed": 42},
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{ollama_url.rstrip('/')}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return [sentence]

    response = data.get("response", "").strip()
    try:
        obj = json.loads(response)
        claims = obj.get("claims") if isinstance(obj, dict) else None
        if isinstance(claims, list):
            return [str(c).strip() for c in claims if str(c).strip()]
    except (json.JSONDecodeError, ValueError):
        pass

    # Loose extraction
    match = re.search(r'\{[^{}]*"claims"[^{}]*\}', response, re.DOTALL)
    if match:
        try:
            obj = json.loads(match.group(0))
            claims = obj.get("claims") if isinstance(obj, dict) else None
            if isinstance(claims, list):
                return [str(c).strip() for c in claims if str(c).strip()]
        except (json.JSONDecodeError, ValueError):
            pass

    return [sentence]


# ──────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────


def extract_claims(answer: str,
                    *,
                    llm_augment_model: Optional[str] = None,
                    ollama_url: str = "http://localhost:11434",
                    timeout: float = 30.0) -> List[str]:
    """Extract atomic claims from an answer.

    Args:
      answer:            free-text answer
      llm_augment_model: if set, use this model for compound sentences
                         that rule-based decompose doesn't fully split.
                         If None, use rule-based only (deterministic).
      ollama_url, timeout: passed to llm augmentation

    Returns:
      list of atomic claims (max 10, each MIN..MAX chars).
    """
    if not answer or not answer.strip():
        return []

    sentences = _sentence_split(answer)
    all_claims: List[str] = []
    for sent in sentences:
        decomposed = _compound_decompose(sent)
        # Augment with LLM only if rule-based produced exactly 1 claim
        # AND the sentence has compound-claim indicators (long + has
        # comma)
        if (llm_augment_model
                and len(decomposed) == 1
                and len(sent) > 80
                and ("," in sent or " who " in sent.lower()
                     or " which " in sent.lower())):
            decomposed = _llm_decompose(
                sent, model=llm_augment_model,
                ollama_url=ollama_url, timeout=timeout)
        all_claims.extend(decomposed)

    cleaned = [_clean(c) for c in all_claims]
    return _filter_valid(cleaned)


__all__ = ["extract_claims", "MAX_CLAIMS_PER_ANSWER"]
