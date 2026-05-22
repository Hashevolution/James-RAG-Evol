"""Query rewriter — Cognitive Layer Phase 1 PR-2.

ARCHITECTURE.md §5.7.1: "Query Rewriter — transform user intent into
retrieval-optimized queries". Sits at STEP 0.5b in pipeline.py (the
slot that has been a no-op since v0.1, reserved for this exact moment).

Routes through the Backend registry (Phase 0 L0) so the same rewrite
can use the local Ollama path or a future Claude CLI backend without
this module changing. Default backend is ``ollama_local`` — the
operator's standard local LLM.

Posture:
  * **Opt-in by default** (``JAMES_ENABLE_QUERY_REWRITE=1``). Adding a
    rewrite means one extra LLM round-trip per query (~5–10 s on
    CPU-only ollama setups) — operators choose when to pay that cost.
    A future PR can flip the default once we measure quality impact
    on the user's corpus.
  * **Best-effort fallback**: any failure (disabled, backend error,
    JSON parse failure, runaway length) returns the original query
    untouched. The pipeline always proceeds with a usable string.
  * **Language-aware prompt**: a Korean-heavy query gets a Korean
    rewrite instruction; otherwise English. Detection threshold
    matches the existing pipeline language heuristic
    (≥ 20% Korean character ratio).

Wire-up (pipeline.py STEP 0.5b):
    rewriter = get_query_rewriter()
    expanded_query, latency_ms = rewriter.rewrite(safe_query)
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import Optional, Tuple


# [JAMES_REASONING_BACKEND wiring 2026-05-18] resolved at import time
# so a stock install (env unset) gets "ollama_local" — byte-identical
# to v0.3.0 behavior. Operators flipping the env restart the server.
from core.reasoning.backends import get_default_backend_id as _get_default_backend
DEFAULT_BACKEND_ID = _get_default_backend()
DEFAULT_TIMEOUT_S = 10.0
# gemma4:e4b consumes ~500 hidden reasoning tokens before the first
# visible output on short structured prompts; cap below that floor
# → deterministic empty response (model burns the budget without
# surfacing any byte).
DEFAULT_MAX_TOKENS = 4096
# Reject rewrites that balloon the query — usually a sign the LLM
# elaborated instead of rewriting (e.g., explaining what the query is
# rather than rephrasing it). 3× length is a generous bound.
MAX_EXPANSION_RATIO = 3.0


REWRITE_PROMPT_KO = (
    "다음 검색 질의를 retrieval 시스템에 최적화된 형태로 다시 작성하라.\n"
    "원본 질의: {query}\n\n"
    "규칙:\n"
    "- 의미는 그대로 유지\n"
    "- 핵심 키워드는 강화 (동의어 1-2개 병기 가능)\n"
    "- 대명사 (이것/그것/위/그분 등) 는 구체적인 명사로 치환\n"
    "- 부연 설명 없이 한 문장으로\n\n"
    "JSON 으로만 응답하라:\n"
    '{{"rewritten": "<재작성된 질의>"}}'
)

REWRITE_PROMPT_EN = (
    "Rewrite this search query for optimal retrieval.\n"
    "Original query: {query}\n\n"
    "Rules:\n"
    "- Preserve meaning exactly\n"
    "- Strengthen keywords (1-2 synonyms in parentheses OK)\n"
    "- Replace ambiguous pronouns (this/that/it/the above) with the noun\n"
    "- One sentence, no explanation\n\n"
    "Respond with JSON only:\n"
    '{{"rewritten": "<rewritten query>"}}'
)


def _enabled() -> bool:
    return os.environ.get("JAMES_ENABLE_QUERY_REWRITE") == "1"


def _is_korean(text: str) -> bool:
    """≥ 20% Korean character ratio matches the existing pipeline
    heuristic in core/reasoning/{engine,modes,pipeline}.py.
    """
    if not text:
        return False
    korean_chars = sum(1 for c in text if "가" <= c <= "힣")
    return korean_chars >= max(1, int(len(text) * 0.2))


# Capture JSON object spanning the response. The LLM may pad with
# leading / trailing prose despite the "respond with JSON only"
# instruction — find the first {...} block and parse from there.
_JSON_OBJECT_RE = re.compile(r'\{[^{}]*"rewritten"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', re.DOTALL)


def _parse_rewritten(llm_text: str) -> Optional[str]:
    """Return the rewritten string from the LLM response, or None.

    Tolerates the model padding with prose around the JSON — we anchor
    on the ``"rewritten"`` key rather than insisting the whole response
    parses as JSON.
    """
    if not llm_text:
        return None
    # Fast path: direct JSON parse
    try:
        blob = json.loads(llm_text)
        if isinstance(blob, dict):
            val = blob.get("rewritten")
            if isinstance(val, str) and val.strip():
                return val.strip()
    except (json.JSONDecodeError, ValueError):
        pass
    # Slower path: regex sniff
    m = _JSON_OBJECT_RE.search(llm_text)
    if m:
        candidate = m.group(1).strip()
        # Unescape the limited set of escapes the regex preserved
        candidate = candidate.replace('\\"', '"').replace("\\\\", "\\")
        if candidate:
            return candidate
    return None


class QueryRewriter:
    """Stateless wrapper around a Backend; the Backend caches the LLM
    client across calls.
    """

    def __init__(
        self,
        backend_id: str = DEFAULT_BACKEND_ID,
        *,
        timeout: float = DEFAULT_TIMEOUT_S,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        self._backend_id = backend_id
        self._timeout = timeout
        self._max_tokens = max_tokens

    def rewrite(
        self,
        query: str,
        *,
        force: bool = False,
    ) -> Tuple[str, int, bool]:
        """Return ``(rewritten_query, latency_ms, attempted)``.

        ``attempted`` is True iff the backend's ``.complete()`` was
        actually called for this query — distinguishes "the rewriter
        ran but the LLM returned an equivalent string / parse-failed
        / errored" from "the rewriter was never invoked (env off,
        query too short, backend lookup miss)". Callers use this to
        decide whether to emit a trace row even when the query is
        unchanged — without it, users opt-in to query_rewrite and see
        ZERO trace activity, unable to tell whether the env flag was
        wired through or the LLM just produced an equivalent rewrite.

        Falls back to ``(query, 0, False)`` when:
          * the env opt-in flag is not set (and ``force`` is False)
          * query is empty / shorter than 4 chars (rewrite adds noise)
          * backend lookup fails (registry doesn't know the id)

        Returns ``(query, latency, True)`` (= attempted, but no useful
        rewrite) when:
          * ``backend.complete()`` raises or returns an error
          * the response doesn't contain a valid ``"rewritten"`` value
          * the rewritten string is empty or balloons past
            ``MAX_EXPANSION_RATIO × len(original)``

        Returns ``(rewritten, latency, True)`` on success.
        """
        if not query or len(query.strip()) < 4:
            return (query, 0, False)
        if not force and not _enabled():
            return (query, 0, False)

        try:
            from core.reasoning.backends import get_backend
            backend = get_backend(self._backend_id)
        except Exception:
            return (query, 0, False)

        prompt_tmpl = REWRITE_PROMPT_KO if _is_korean(query) else REWRITE_PROMPT_EN
        prompt = prompt_tmpl.format(query=query)

        t0 = time.time()
        try:
            result = backend.complete(
                prompt,
                max_tokens=self._max_tokens,
                timeout=self._timeout,
            )
        except Exception:
            return (query, int((time.time() - t0) * 1000), True)
        latency_ms = int((time.time() - t0) * 1000)

        if getattr(result, "error", "") or not getattr(result, "text", ""):
            return (query, latency_ms, True)

        rewritten = _parse_rewritten(result.text)
        if not rewritten:
            return (query, latency_ms, True)

        # Reject runaway expansions — usually the LLM explaining instead
        # of rewriting. Keep the original; mark the latency we spent.
        if len(rewritten) > len(query) * MAX_EXPANSION_RATIO:
            return (query, latency_ms, True)

        return (rewritten, latency_ms, True)


# ─── module-level singleton ────────────────────────────────────────
_SINGLETON: Optional[QueryRewriter] = None
_SINGLETON_LOCK = threading.Lock()


def get_query_rewriter() -> QueryRewriter:
    global _SINGLETON
    if _SINGLETON is None:
        with _SINGLETON_LOCK:
            if _SINGLETON is None:
                _SINGLETON = QueryRewriter()
    return _SINGLETON


def _clear_singleton_for_tests() -> None:
    """Test helper. Production code never calls this."""
    global _SINGLETON
    with _SINGLETON_LOCK:
        _SINGLETON = None


__all__ = [
    "DEFAULT_BACKEND_ID",
    "QueryRewriter",
    "get_query_rewriter",
]
