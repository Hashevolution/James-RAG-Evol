"""
PROJECT JAMES - LLM Base Interface (Phase 5.5)

인터페이스만. GPU 업그레이드 후 구현체 추가 예정.
Multi-LLM 라우팅은 Phase 6 이후.
"""

from abc import ABC, abstractmethod
from typing import List, Dict


class BaseLLM(ABC):
    """LLM 공통 인터페이스. 각 provider에서 구현."""
    name: str = "base"

    @abstractmethod
    def generate(self, messages: List[Dict], **kwargs) -> str:
        raise NotImplementedError

    def generate_meta(self, messages: List[Dict], **kwargs) -> Dict:
        """Return generated text + provider metadata as a dict.

        D6 follow-up (2026-05-25). Lets call sites read a native
        truncation signal (``done_reason``) when the provider exposes
        one, replacing the heuristic in
        ``core.reasoning.backends.ollama_local`` with a precise signal.

        Contract: returns at minimum::

            {"text": str, "done_reason": str}

        ``done_reason`` values follow Ollama's vocabulary:
          - ``"stop"``    — model produced a stop token / EOS
          - ``"length"``  — ``num_predict`` cap was hit (truncation)
          - ``"load"``    — model still loading (rare)
          - ``""``        — provider doesn't expose the signal

        Default implementation falls back to ``.generate(...)`` so
        pre-D6 plugin providers keep working unchanged. Provider-
        specific overrides (Ollama, Claude API, etc.) plug in
        their native signal.
        """
        return {
            "text": self.generate(messages, **kwargs),
            "done_reason": "",
        }

    def is_available(self) -> bool:
        """provider 연결 가능 여부 확인."""
        return False
