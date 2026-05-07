"""
PROJECT JAMES - ReadFileTool (Phase 5.5)

BaseTool 기반 파일 읽기 전용 Tool.
Sandbox 검증 통과 후 workspace 내 파일 읽기.
"""

import os
from pathlib import Path
from typing import Optional

from tools.base_tool import BaseTool
from tools.code.sandbox import policy_validate_path, log_security_event

SUPPORTED_EXT = {
    ".py",".js",".ts",".java",".cpp",".c",".h",".go",".rs",
    ".md",".txt",".json",".yaml",".yml",".toml",".html",".css",".sql",
}
MAX_FILE_BYTES = 500 * 1024
MAX_LINES      = 1000


class ReadFileTool(BaseTool):
    name              = "read_file"
    description       = "workspace 내 파일 읽기 전용"
    requires_sandbox  = True

    def authorize(self, context: dict) -> bool:
        """employee 이상 허용."""
        from core.security_layer import ROLE_LEVEL
        role = context.get("user_role", "external")
        return ROLE_LEVEL.get(role, 0) >= 1   # employee=1 이상

    def execute(self, input_data: dict) -> dict:
        """
        파일 읽기 실행.

        input_data:
          path:       파일 경로
          start_line: 시작 라인 (기본 1)
          end_line:   끝 라인 (기본 전체)
          role:       실행 role (sandbox 경로 검증용)
        """
        path       = input_data.get("path", "")
        start_line = int(input_data.get("start_line", 1))
        end_line   = input_data.get("end_line")
        role       = input_data.get("role", "user")

        # PolicyEngine + sandbox 경로 검증 (#44 phase 3-3)
        path_ok, reason = policy_validate_path(path, role, "fs.read")
        if not path_ok:
            log_security_event("PATH_VIOLATION", f"read:{path}", role=role)
            return self._error(f"경로 차단: {reason}")

        p = Path(path)

        if not p.exists():
            return self._error(f"파일 없음: {path}")
        if not p.is_file():
            return self._error(f"파일이 아님: {path}")
        if p.suffix.lower() not in SUPPORTED_EXT:
            return self._error(f"지원하지 않는 형식: {p.suffix}")
        if p.stat().st_size > MAX_FILE_BYTES:
            return self._error(f"파일 크기 초과 ({p.stat().st_size//1024}KB)")

        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return self._error(f"읽기 실패: {e}")

        lines       = content.split("\n")
        total_lines = len(lines)
        s           = max(0, start_line - 1)
        e_          = min(total_lines, int(end_line)) if end_line else total_lines
        e_          = min(e_, s + MAX_LINES)

        selected = lines[s:e_]
        result   = "\n".join(f"{s+i+1:4d}│ {l}" for i, l in enumerate(selected))

        return self._result(True, result, meta={
            "path": path, "total_lines": total_lines,
            "shown_lines": len(selected), "start": s+1, "end": s+len(selected),
        })

    def list_files(self, directory: str = "./workspace", role: str = "user") -> dict:
        """디렉토리 내 파일 목록."""
        path_ok, reason = policy_validate_path(directory, role, "fs.read")
        if not path_ok:
            return self._error(f"경로 차단: {reason}")
        p = Path(directory)
        if not p.exists():
            return self._error(f"경로 없음: {directory}")
        files = [
            {"path": str(f), "name": f.name, "ext": f.suffix, "kb": round(f.stat().st_size/1024,2)}
            for f in p.glob("*") if f.is_file() and f.suffix.lower() in SUPPORTED_EXT
        ]
        return self._result(True, files, count=len(files))
