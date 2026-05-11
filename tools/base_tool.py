"""
PROJECT JAMES - BaseTool Interface (Phase 5.5)

모든 Tool의 기반 인터페이스.
Core Engine과 분리된 Tool Layer 전용.

절대 제약:
  ❌ Core Engine import 금지
  ✅ authorize() → execute() 순서 강제
  ✅ 실행 결과에 tool_used 포함
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """
    모든 Tool의 기반 클래스.
    Tool Layer 전용 — Core Engine 직접 접근 금지.
    """

    name: str = "base"
    description: str = ""
    requires_sandbox: bool = True   # 기본: Sandbox 통과 필수

    def authorize(self, context: dict) -> bool:
        """
        Tool 실행 권한 확인.
        기본: 차단 (각 Tool에서 재정의 필수).

        context 예시:
          {"user_role": "admin", "allow_fs": False, "allow_shell": False}
        """
        return False

    @abstractmethod
    def execute(self, input_data: dict) -> dict:
        """
        Tool 실행. authorize() 통과 후에만 호출됨.

        Returns:
            {"success": bool, "result": Any, "tool_used": str, ...}
        """
        raise NotImplementedError

    def _result(self, success: bool, result: Any, **extra) -> dict:
        """표준 결과 포맷 생성 헬퍼."""
        return {
            "success":   success,
            "result":    result,
            "tool_used": self.name,
            **extra,
        }

    def _error(self, reason: str) -> dict:
        return {"success": False, "result": None,
                "tool_used": self.name, "error": reason}
