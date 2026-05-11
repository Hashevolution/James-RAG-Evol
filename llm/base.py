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

    def is_available(self) -> bool:
        """provider 연결 가능 여부 확인."""
        return False
