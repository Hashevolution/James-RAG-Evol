"""
PROJECT JAMES - Ollama Client (Phase 5.5)

기존 GemmaClient 래핑. 새 로직 없음.
Multi-LLM 라우터는 Phase 6 이후.
"""

from llm.base import BaseLLM
from typing import List, Dict


class OllamaClient(BaseLLM):
    name = "ollama"

    def __init__(self):
        # D6 follow-up (2026-05-25) — hold a single GemmaClient
        # instance so `generate_meta` can read `_last_done_reason`
        # after `generate(...)` returns. Pre-D6 the client was
        # constructed inline per call; the inline construction is
        # preserved as a fallback path inside `generate(...)` so
        # legacy call sites that don't use `generate_meta` keep
        # the same memory profile.
        self._gemma_client = None

    def _client(self):
        from core.gemma_client import GemmaClient
        if self._gemma_client is None:
            self._gemma_client = GemmaClient()
        return self._gemma_client

    def generate(self, messages: List[Dict], **kwargs) -> str:
        """messages → 단일 prompt 변환 후 GemmaClient 호출.

        kwargs로 timeout / use_cache / max_tokens / model 모두 통과 가능
        (call_router가 이 generate를 호출하므로 호출자의 옵션이 손실 없이 전달).
        ``model`` 인자가 있으면 GemmaClient가 그 model로 ollama API 호출 (#15).
        """
        prompt     = "\n".join(m.get("content","") for m in messages if m.get("content"))
        timeout    = kwargs.get("timeout",    120)
        use_cache  = kwargs.get("use_cache",  True)
        max_tokens = kwargs.get("max_tokens", 0)
        model      = kwargs.get("model")
        return self._client().call_gemma(
            prompt, timeout=timeout, use_cache=use_cache, max_tokens=max_tokens,
            model=model,
        )

    def generate_meta(self, messages: List[Dict], **kwargs) -> Dict:
        """D6 follow-up — return text + native Ollama `done_reason`.

        Calls `generate(...)` then reads the cached GemmaClient's
        `_last_done_reason` attribute (populated inside
        `GemmaClient.call_gemma` from the raw Ollama response).

        Returns:
            {"text": str, "done_reason": str}

            `done_reason` is whatever Ollama returned ("stop" /
            "length" / "load" / ""). Empty when:
              - GemmaClient hit a cache (no fresh Ollama call)
              - Ollama version < 0.1.30 (field not in response)
              - call errored before reaching `response.json()`

        The `ollama_local` backend (`core.reasoning.backends.ollama_local`)
        consumes this to replace its length-+-terminator heuristic
        with the precise native signal — falling back to the
        heuristic only when `done_reason` is empty.
        """
        text = self.generate(messages, **kwargs)
        client = self._client()
        return {
            "text": text,
            "done_reason": getattr(client, "_last_done_reason", "") or "",
        }

    def is_available(self) -> bool:
        try:
            import requests
            requests.get("http://127.0.0.1:11434", timeout=2)
            return True
        except Exception:
            return False
