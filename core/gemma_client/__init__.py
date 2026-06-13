"""PROJECT JAMES - Gemma Client (Phase 4)

Phase 3.5 수정 적용:
  [CACHE-BUG-FIX] 에러 응답 캐시 금지
    기존: [Gemma 응답 없음] 등 에러도 캐시 저장
          → 이후 동일 프롬프트 재호출 시 에러가 캐시 히트로 즉시 반환
    수정: is_cacheable_response() 검증
          _get_from_cache 조회 시점에도 재검증 (기존 에러 자동 제거)

  [C2-FIX] <think> 블록 제거 후 빈 응답 3단계 복구
    1단계: <think> 제거 후 내용 있으면 정상 사용
    2단계: </think> 이후 텍스트 추출
    3단계: <think> 내부 마지막 문장 추출

  [CACHE-STAT] hit / miss / error 통계 카운터

Phase 4:
  [SPEED] num_predict=700 (thinking 버퍼 확보), num_ctx=2048, temperature=0.2

## v0.6 package split (CLAUDE.md rule #5)

This package was a single ``core/gemma_client.py`` file (24.3 KB,
over the 20 KB cap) until the v0.6 oversize-module split. The
public API surface is byte-identical — all existing imports
(``from core.gemma_client import GemmaClient`` /
``ERROR_PREFIXES`` / ``is_cacheable_response`` etc.) keep working
through this façade:

  * :mod:`core.gemma_client.client` — ``GemmaClient`` class
  * :mod:`core.gemma_client.errors` — ``ERROR_PREFIXES`` +
    ``is_cacheable_response`` + ``log_system_event``
  * :mod:`core.gemma_client.config` — ``_DEFAULT_MAX_PROMPT_LEN`` +
    ``_resolve_max_prompt_len`` (JAMES_GEMMA_MAX_PROMPT_CHARS env)
  * :mod:`core.gemma_client.response_parser` — ``<think>`` block
    3-stage recovery + post-processing
  * this ``__init__.py`` — re-exports

External callers that imported ``_LLM_OPTIONS`` from this module
(only :mod:`llm.providers.deepseek_client`) used a try/except
fallback because the symbol never existed in the pre-split file —
behaviour preserved.
"""
from __future__ import annotations

# ─── re-exports — preserves the pre-split import surface ─────────

from core.gemma_client.config import (  # noqa: F401
    _DEFAULT_MAX_PROMPT_LEN,
    _resolve_max_prompt_len,
)
from core.gemma_client.errors import (  # noqa: F401
    ERROR_PREFIXES,
    is_cacheable_response,
    log_system_event,
)
from core.gemma_client.response_parser import (  # noqa: F401
    recover_think_block,
    recover_vision_response,
)
from core.gemma_client.client import (  # noqa: F401
    GemmaClient,
)


__all__ = [
    "GemmaClient",
    "ERROR_PREFIXES",
    "is_cacheable_response",
    "log_system_event",
]
