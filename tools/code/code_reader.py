"""
PROJECT JAMES - Code Reader (Phase 5.5)

역할: workspace 내 파일 읽기 전용.
Sandbox 검증 후에만 접근 허용.

절대 제약:
  ❌ 쓰기/수정 금지
  ❌ workspace 외부 접근 금지
  ✅ Sandbox validate_path 통과 필수
  ✅ 읽기 이벤트 감사 로그 기록
"""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tools.code.sandbox import policy_validate_path, log_security_event

AUDIT_LOG_PATH = "james_audit_tool.jsonl"

SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".ts", ".java", ".cpp", ".c", ".h",
    ".go", ".rs", ".kt", ".swift", ".rb", ".php",
    ".md", ".txt", ".json", ".yaml", ".yml", ".toml",
    ".html", ".css", ".sql", ".sh", ".bat",
}

MAX_FILE_SIZE_BYTES = 500 * 1024   # 500KB
MAX_LINES_RETURN    = 1000          # 최대 반환 라인


def _log_read(path: str, lines: int, success: bool):
    entry = {
        "time":    datetime.now().isoformat(),
        "event":   "FILE_READ",
        "path":    path,
        "lines":   lines,
        "success": success,
        "layer":   "code_reader",
    }
    try:
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # Phase 1: mirror to SQLite (see core/audit_bridge.py).
    try:
        from core.audit_bridge import mirror_to_audit_db
        mirror_to_audit_db(entry)
    except Exception:
        pass


class CodeReader:
    """
    workspace 내 파일 읽기 전용 도구.
    모든 접근은 PolicyEngine + Sandbox 검증 후 허용.

    Phase 3-3 (#44): 인스턴스 단위 user_role을 보관해 모든 경로 검증이
    PolicyEngine.issue_capability("fs.read")를 거치도록 한다. 외부에서
    role을 지정하지 않으면 admin (호환성 — 자가 테스트 / 직접 호출).
    """

    def __init__(self, user_role: str = "admin"):
        self.user_role = user_role

    def read_file(
        self,
        path:        str,
        start_line:  int = 1,
        end_line:    Optional[int] = None,
    ) -> Tuple[bool, str, Dict]:
        """
        파일 내용 읽기.

        Args:
            path:       읽을 파일 경로 (workspace 상대 경로)
            start_line: 시작 라인 (1-based)
            end_line:   끝 라인 (None=전체)

        Returns:
            (success, content, metadata)
        """
        # PolicyEngine + sandbox 경로 검증 (#44 phase 3-3)
        path_ok, reason = policy_validate_path(path, self.user_role, "fs.read")
        if not path_ok:
            log_security_event("PATH_VIOLATION", f"read:{path} → {reason}")
            _log_read(path, 0, False)
            return False, f"[SANDBOX] 경로 차단: {reason}", {}

        p = Path(path)

        # 파일 존재 확인
        if not p.exists():
            _log_read(path, 0, False)
            return False, f"파일 없음: {path}", {}

        if not p.is_file():
            return False, f"파일이 아님: {path}", {}

        # 확장자 확인
        if p.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return False, f"지원하지 않는 파일 형식: {p.suffix}", {}

        # 파일 크기 확인
        size = p.stat().st_size
        if size > MAX_FILE_SIZE_BYTES:
            return False, f"파일 크기 초과: {size/1024:.1f}KB (최대 500KB)", {}

        # 파일 읽기
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            _log_read(path, 0, False)
            return False, f"읽기 실패: {e}", {}

        lines = content.split("\n")
        total_lines = len(lines)

        # 라인 범위 적용
        s = max(0, start_line - 1)
        e_ = min(total_lines, end_line) if end_line else total_lines
        e_ = min(e_, s + MAX_LINES_RETURN)

        selected = lines[s:e_]
        result   = "\n".join(
            f"{s + i + 1:4d}│ {line}"
            for i, line in enumerate(selected)
        )

        meta = {
            "path":         path,
            "total_lines":  total_lines,
            "shown_lines":  len(selected),
            "start_line":   s + 1,
            "end_line":     s + len(selected),
            "size_bytes":   size,
            "extension":    p.suffix,
        }

        _log_read(path, len(selected), True)
        print(f"[READER] ✅ {path} ({len(selected)}/{total_lines}줄)")
        return True, result, meta

    def list_files(
        self,
        directory: str = "./workspace",
        recursive: bool = False,
    ) -> Tuple[bool, List[Dict]]:
        """
        workspace 내 파일 목록 조회.
        """
        path_ok, reason = policy_validate_path(directory, self.user_role, "fs.read")
        if not path_ok:
            log_security_event("PATH_VIOLATION", f"list:{directory}")
            return False, []

        p = Path(directory)
        if not p.exists() or not p.is_dir():
            return False, []

        files = []
        try:
            pattern = "**/*" if recursive else "*"
            for f in p.glob(pattern):
                if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
                    files.append({
                        "path":      str(f),
                        "name":      f.name,
                        "extension": f.suffix,
                        "size_kb":   round(f.stat().st_size / 1024, 2),
                        "lines":     None,   # 빠른 목록은 라인 수 생략
                    })
        except Exception:
            return False, []

        print(f"[READER] 목록: {directory} → {len(files)}개 파일")
        return True, files

    def get_structure(self, directory: str = "./workspace") -> Tuple[bool, str]:
        """
        디렉토리 구조 트리 형태 반환.
        """
        path_ok, reason = policy_validate_path(directory, self.user_role, "fs.read")
        if not path_ok:
            log_security_event("PATH_VIOLATION", f"structure:{directory}")
            return False, f"차단: {reason}"

        p = Path(directory)
        if not p.exists():
            return False, f"경로 없음: {directory}"

        lines = [f"{p.name}/"]
        try:
            self._tree(p, lines, prefix="")
        except Exception as e:
            return False, f"구조 읽기 실패: {e}"

        return True, "\n".join(lines)

    @staticmethod
    def _tree(path: Path, lines: list, prefix: str, depth: int = 0):
        if depth > 5:   # 최대 깊이 5
            return
        try:
            items = sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name))
        except PermissionError:
            return
        for i, item in enumerate(items):
            is_last    = i == len(items) - 1
            connector  = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{item.name}{'/' if item.is_dir() else ''}")
            if item.is_dir():
                ext = "    " if is_last else "│   "
                CodeReader._tree(item, lines, prefix + ext, depth + 1)


if __name__ == "__main__":
    print("=== Code Reader 자가 테스트 ===\n")

    import os
    os.makedirs("./workspace", exist_ok=True)
    # encoding="utf-8" required: Windows default is cp949 → Korean
    # comment would be saved in cp949 and CodeReader's utf-8 read
    # would emit replacement chars.
    with open("./workspace/test.py", "w", encoding="utf-8") as f:
        f.write("# 테스트 파일\nprint('hello')\n")

    reader = CodeReader()

    ok, content, meta = reader.read_file("./workspace/test.py")
    print(f"  {'✅' if ok else '❌'} 정상 읽기: {meta.get('shown_lines',0)}줄")

    ok2, _ = reader.read_file("../secret.py")
    print(f"  {'✅' if not ok2 else '❌'} 경로 탈출 차단: {not ok2}")

    ok3, files = reader.list_files("./workspace")
    print(f"  {'✅' if ok3 else '❌'} 파일 목록: {len(files)}개")

    ok4, struct = reader.get_structure("./workspace")
    print(f"  {'✅' if ok4 else '❌'} 구조 조회:\n{struct}")
