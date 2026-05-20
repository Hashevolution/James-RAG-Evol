"""
PROJECT JAMES — File Scanner (Phase 7, Self-Awareness)

자메스가 자신의 코드 구조와 파일을 인식하고 기억하는 도구.

기능:
  1. 프로젝트 전체 .py 파일 스캔
  2. 함수/클래스/docstring 추출
  3. 폴더 구조 트리 생성
  4. wiki에 자메스_코드구조.md 저장 → Graph-RAG 검색 가능
  5. vector store 인덱싱 → 코드 관련 질문 답변 가능
  6. 변경 감지 (hash 비교) → 서버 재시작마다 최신 유지

사용:
  서버 시작 시: auto_index_on_startup()
  수동 요청 시: scan_and_index(query=사용자_질문)
"""

import os
import ast
import json
import hashlib
import re
from pathlib import Path
from datetime import datetime

try:
    from config import BASE_DIR, WIKI_DIR
except ImportError:
    BASE_DIR = "."
    WIKI_DIR = "./wiki"

BASE_PATH  = Path(os.path.abspath(BASE_DIR))
WIKI_PATH  = Path(WIKI_DIR) if os.path.isabs(WIKI_DIR) else BASE_PATH / "wiki"
SELF_DIR   = WIKI_PATH / "prod" / "entity" / "system"
HASH_FILE  = BASE_PATH / "workspace" / ".james_code_hash.json"
SELF_WIKI  = SELF_DIR / "자메스_코드구조.md"

# 스캔 대상 폴더 (BASE_DIR 기준)
SCAN_DIRS = [
    "core", "tools", "llm", "utils",
    ".",    # 루트 .py 파일들
]

# 제외 파일/폴더
EXCLUDE = {
    "__pycache__", ".git", "node_modules", "venv", ".venv",
    "chroma_db", "uploads", "wiki", "memory", "workspace",
    "tests", "test_",
}

# 보안: 절대 내용 노출 안 할 파일
SENSITIVE_FILES = {
    "auth.py", "security_layer.py", "config.py",
    "security.py",
}


# ─────────────────────────────────────────────
# 파일 분석
# ─────────────────────────────────────────────

def _extract_file_info(filepath: Path) -> dict:
    """
    .py 파일에서 구조 정보 추출.
    민감 파일은 함수명/클래스명만, 내용은 제외.
    """
    name = filepath.name
    is_sensitive = name in SENSITIVE_FILES

    info = {
        "path":      str(filepath.relative_to(BASE_PATH)),
        "name":      name,
        "sensitive": is_sensitive,
        "classes":   [],
        "functions": [],
        "imports":   [],
        "docstring": "",
        "lines":     0,
        "size":      filepath.stat().st_size,
    }

    try:
        src = filepath.read_text(encoding="utf-8", errors="replace")
        info["lines"] = len(src.splitlines())

        if is_sensitive:
            # 민감 파일: 구조만 (내용 X)
            info["docstring"] = "[보안 파일 — 구조만 공개]"
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    info["classes"].append(node.name)
                elif isinstance(node, ast.FunctionDef) and node.col_offset == 0:
                    info["functions"].append(node.name)
            return info

        # 일반 파일: 전체 구조 추출
        tree = ast.parse(src)

        # 모듈 docstring
        if (tree.body and isinstance(tree.body[0], ast.Expr)
                and isinstance(tree.body[0].value, ast.Constant)):
            doc = tree.body[0].value.value or ""
            info["docstring"] = doc[:300].strip()

        # 클래스
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = [
                    n.name for n in ast.walk(node)
                    if isinstance(n, ast.FunctionDef)
                    and not n.name.startswith('__')
                ]
                info["classes"].append({
                    "name":    node.name,
                    "methods": methods[:10],
                })

        # 최상위 함수
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                fn_doc = ""
                if (node.body and isinstance(node.body[0], ast.Expr)
                        and isinstance(node.body[0].value, ast.Constant)):
                    fn_doc = str(node.body[0].value.value or "")[:100]
                info["functions"].append({
                    "name":      node.name,
                    "docstring": fn_doc,
                })

        # import 목록
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    info["imports"].append(alias.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    info["imports"].append(node.module.split('.')[0])

        info["imports"] = list(set(info["imports"]))[:15]

    except SyntaxError:
        info["docstring"] = "[파싱 불가]"
    except Exception as e:
        info["docstring"] = f"[오류: {e}]"

    return info


# ─────────────────────────────────────────────
# 폴더 구조 트리
# ─────────────────────────────────────────────

def _build_tree(max_depth: int = 4) -> str:
    """프로젝트 폴더 구조 트리 생성."""
    lines = [f"```\n{BASE_PATH.name}/"]

    def _scan(path: Path, prefix: str, depth: int):
        if depth > max_depth:
            return
        try:
            items = sorted(path.iterdir(),
                           key=lambda x: (x.is_file(), x.name))
            items = [i for i in items if i.name not in EXCLUDE
                     and not i.name.startswith('.')]
        except PermissionError:
            return

        for i, item in enumerate(items):
            is_last   = (i == len(items) - 1)
            connector = "└── " if is_last else "├── "
            extension = "    " if is_last else "│   "

            if item.is_dir():
                lines.append(f"{prefix}{connector}{item.name}/")
                _scan(item, prefix + extension, depth + 1)
            elif item.suffix == '.py':
                size = item.stat().st_size
                lines.append(
                    f"{prefix}{connector}{item.name}"
                    f"  ({size//1024}KB)" if size > 1024 else
                    f"{prefix}{connector}{item.name}"
                )

    _scan(BASE_PATH, "", 1)
    lines.append("```")
    return "\n".join(lines)


# ─────────────────────────────────────────────
# 해시 기반 변경 감지
# ─────────────────────────────────────────────

def _compute_hash(filepath: Path) -> str:
    try:
        content = filepath.read_bytes()
        return hashlib.md5(content, usedforsecurity=False).hexdigest()
    except Exception:
        return ""


def _load_hashes() -> dict:
    try:
        if HASH_FILE.exists():
            return json.loads(HASH_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_hashes(hashes: dict):
    try:
        HASH_FILE.parent.mkdir(parents=True, exist_ok=True)
        HASH_FILE.write_text(
            json.dumps(hashes, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception:
        pass


# ─────────────────────────────────────────────
# 핵심: 스캔 + 인덱싱
# ─────────────────────────────────────────────

def scan_project(force: bool = False) -> dict:
    """
    프로젝트 전체 스캔.
    force=False: 변경된 파일만 처리
    force=True:  전체 재스캔

    Returns: {
        "files":    [file_info, ...],
        "changed":  [changed_paths],
        "total":    int,
        "tree":     str,
    }
    """
    old_hashes = _load_hashes() if not force else {}
    new_hashes = {}
    all_files  = []
    changed    = []

    # 스캔 대상 수집
    py_files = []
    for scan_dir in SCAN_DIRS:
        target = BASE_PATH / scan_dir if scan_dir != "." else BASE_PATH
        if not target.exists():
            continue
        pattern = "*.py" if scan_dir == "." else "**/*.py"
        for f in target.glob(pattern):
            # 제외 조건
            if any(ex in str(f) for ex in EXCLUDE):
                continue
            if f.name.startswith("test_") or f.name.startswith("james_"):
                continue
            py_files.append(f)

    py_files = list(set(py_files))  # 중복 제거

    for filepath in sorted(py_files):
        h = _compute_hash(filepath)
        rel = str(filepath.relative_to(BASE_PATH))
        new_hashes[rel] = h

        if not force and old_hashes.get(rel) == h:
            continue  # 변경 없음 → 스킵

        changed.append(rel)
        info = _extract_file_info(filepath)
        all_files.append(info)

    _save_hashes(new_hashes)

    return {
        "files":   all_files,
        "changed": changed,
        "total":   len(py_files),
        "tree":    _build_tree(),
        "scanned_at": datetime.now().isoformat(),
    }


def build_wiki_content(scan_result: dict) -> str:
    """스캔 결과로 wiki md 파일 생성."""
    files   = scan_result["files"]
    tree    = scan_result["tree"]
    now     = scan_result["scanned_at"]

    lines = [
        "---",
        "entity_id: james_code_structure_001",
        "name: 자메스_코드구조",
        "entity_type: system",
        "sensitivity: internal",
        "source_type: prod",
        f"updated_at: {now}",
        "relations: []",
        "---",
        "",
        "# 자메스 코드 구조 (자동 생성)",
        "",
        f"> 마지막 스캔: {now[:16]}  |  총 {scan_result['total']}개 파일",
        "",
        "## 폴더 구조",
        "",
        tree,
        "",
        "## 파일별 상세",
        "",
    ]

    for f in files:
        lines.append(f"### {f['path']}")
        if f.get("docstring"):
            lines.append(f"> {f['docstring']}")
        lines.append(f"- 크기: {f['lines']}줄 / {f['size']//1024}KB")

        classes = f.get("classes", [])
        if classes:
            class_names = [
                c["name"] if isinstance(c, dict) else c
                for c in classes
            ]
            lines.append(f"- 클래스: {', '.join(class_names)}")

        fns = f.get("functions", [])
        if fns:
            fn_names = [
                fn["name"] if isinstance(fn, dict) else fn
                for fn in fns[:8]
            ]
            lines.append(f"- 주요 함수: {', '.join(fn_names)}")

        if f.get("imports"):
            lines.append(f"- 의존성: {', '.join(f['imports'][:8])}")

        lines.append("")

    return "\n".join(lines)


def save_to_wiki(content: str) -> Path:
    """wiki 파일 저장."""
    SELF_DIR.mkdir(parents=True, exist_ok=True)
    SELF_WIKI.write_text(content, encoding="utf-8")
    print(f"[SCANNER] wiki 저장: {SELF_WIKI}")
    return SELF_WIKI


def index_to_vector(content: str, name: str = "자메스_코드구조.md",
                    vector_store=None) -> int:
    """
    vector store 인덱싱.

    vector_store: 서버의 rag_engine.vector_store 인스턴스를 직접 받음.
                  None이면 내부에서 import 시도 (fallback).
    """
    try:
        # 섹션별 청크 분리 (### 기준)
        sections = re.split(r'\n(?=###)', content)
        chunks   = [s.strip() for s in sections
                    if s.strip() and len(s.strip()) > 50]

        if not chunks:
            print("[SCANNER] ⚠️ 인덱싱할 청크 없음")
            return 0

        # 방법 1: 서버가 직접 vector_store 전달 (최우선)
        vs = vector_store

        # 방법 2: 서버 전역 인스턴스 참조
        if vs is None:
            try:
                import server_llmwiki as _srv
                vs = _srv.rag_engine.vector_store
            except Exception:
                pass

        # 방법 3: 직접 import (마지막 수단)
        if vs is None:
            import sys
            if str(BASE_PATH) not in sys.path:
                sys.path.insert(0, str(BASE_PATH))
            try:
                try:
                    from core.graph_rag_engine import RAGEngine
                except ModuleNotFoundError:
                    from graph_rag_engine import RAGEngine
                engine = RAGEngine(default_role="admin")
                vs = engine.vector_store
            except Exception as e:
                print(f"[SCANNER] ❌ vector store 접근 불가: {e}")
                return 0

        # 기존 청크 삭제 후 재인덱싱
        try:
            vs.delete_by_source(name)
        except Exception:
            pass

        vs.add_documents_with_meta(
            texts=chunks,
            source=name,
            metadata={
                "sensitivity": "internal",
                "owner":       "system",
                "category":    "시스템",
                "source_type": "prod",
            }
        )
        print(f"[SCANNER] ✅ vector 인덱싱: {len(chunks)} chunks")
        return len(chunks)

    except Exception as e:
        print(f"[SCANNER] ❌ vector 인덱싱 실패: {e}")
        return 0


# ─────────────────────────────────────────────
# 외부 진입점
# ─────────────────────────────────────────────

def auto_index_on_startup():
    """
    서버 시작 시 자동 호출.
    변경된 파일만 재인덱싱 (빠름).
    """
    try:
        print("[SCANNER] 프로젝트 코드 스캔 시작...")
        result  = scan_project(force=False)
        changed = result["changed"]

        if not changed:
            print(f"[SCANNER] 변경 없음 — 스킵 (총 {result['total']}개 파일)")
            return

        print(f"[SCANNER] 변경 감지: {len(changed)}개 파일")
        content = build_wiki_content(result)
        save_to_wiki(content)
        index_to_vector(content)
        print("[SCANNER] ✅ 자기 인식 인덱싱 완료")

    except Exception as e:
        print(f"[SCANNER] 시작 시 인덱싱 실패: {e}")


def scan_and_report(query: str = "") -> str:
    """
    수동 스캔 + 보고서 생성.
    챗에서 "네 코드 파악해봐" 요청 시 호출.
    """
    try:
        result  = scan_project(force=True)
        content = build_wiki_content(result)
        save_to_wiki(content)
        chunks  = index_to_vector(content)

        summary = (
            f"✅ 코드 스캔 완료\n\n"
            f"📁 총 파일: {result['total']}개\n"
            f"🔄 갱신됨: {len(result['changed'])}개\n"
            f"📚 인덱싱: {chunks} chunks\n\n"
            f"📂 폴더 구조:\n{result['tree'][:800]}\n\n"
            f"이제 자메스 코드에 대한 질문에 답할 수 있습니다."
        )

        if query:
            summary += f"\n\n💡 '{query}'에 대한 분석은 위 인덱싱 완료 후 검색해보세요."

        return summary

    except Exception as e:
        return f"❌ 스캔 실패: {e}"


def get_file_content(filepath: str) -> str:
    """
    특정 파일 내용 조회 (self_evolve 모드에서 사용).
    민감 파일은 차단.
    """
    fname = Path(filepath).name
    if fname in SENSITIVE_FILES:
        return f"❌ '{fname}'은 보안 파일이라 내용을 볼 수 없습니다."

    target = BASE_PATH / filepath
    if not target.exists():
        # core/ 없이 파일명만 입력한 경우도 탐색
        for f in BASE_PATH.rglob(fname):
            if f.suffix == '.py' and f.name not in SENSITIVE_FILES:
                target = f
                break
        else:
            return f"❌ '{filepath}' 파일을 찾을 수 없습니다."

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
        return content[:3000]  # 최대 3000자
    except Exception as e:
        return f"❌ 파일 읽기 실패: {e}"
