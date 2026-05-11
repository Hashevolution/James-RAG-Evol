"""
PROJECT JAMES — Wiki Editor Tool (Phase 7)

admin이 챗을 통해 wiki entity를 즉시 수정/삭제/추가하는 도구.

보안 원칙:
  - admin role만 호출 가능 (reasoning_engine에서 체크)
  - WIKI_DIR 범위 내 파일만 접근
  - 변경 전 자동 백업
  - 감사 로그 기록
  - 변경 후 vector_store + entity_index 재동기화
"""

import os
import json
import shutil
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

try:
    from config import BASE_DIR, WIKI_DIR
except ImportError:
    BASE_DIR = "."
    WIKI_DIR = "./wiki"

WIKI_PATH    = Path(WIKI_DIR) if os.path.isabs(WIKI_DIR) else Path(BASE_DIR) / "wiki"
BACKUP_DIR   = Path(BASE_DIR) / "workspace" / ".wiki_backups"
AUDIT_FILE   = Path(BASE_DIR) / "james_wiki_edit_log.jsonl"
PROTECTED    = {"security_layer.py", "auth.py", "config.py", "server_llmwiki.py"}


# ─────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────

def _in_wiki_dir(path: Path) -> bool:
    """WIKI_DIR 범위 내 파일인지 확인 (path traversal 방지)"""
    try:
        path.resolve().relative_to(WIKI_PATH.resolve())
        return True
    except ValueError:
        return False


def _backup(path: Path) -> Optional[Path]:
    """변경 전 백업"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"{ts}_{path.name}"
    shutil.copy2(path, dest)
    return dest


def _audit(action: str, target: str, detail: str, user_role: str = "admin"):
    """감사 로그 기록"""
    entry = {
        "time":      datetime.now().isoformat(),
        "action":    action,
        "target":    target,
        "detail":    detail,
        "user_role": user_role,
    }
    with open(AUDIT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[WIKI_EDIT] {action}: {target} | {detail[:60]}")


def _resync_vector(name: str, content: str, source_type: str = "prod"):
    """wiki 변경 후 vector store 재동기화"""
    try:
        try:
            from core.graph_rag_engine import RAGEngine   # 사용자 프로젝트: core/ 위치
        except ModuleNotFoundError:
            try:
                from graph_rag_engine import RAGEngine    # 루트 fallback
            except ModuleNotFoundError:
                import sys
                # [F821 fix 2026-05-11] previously referenced an
                # undefined ``BASE_PATH``; the in-dir() guard made it
                # silently fall through to ".". Use the module-level
                # ``BASE_DIR`` imported at the top of this file —
                # that's the intent.
                sys.path.insert(0, str(BASE_DIR))
                from core.graph_rag_engine import RAGEngine
        engine = RAGEngine(default_role="admin")

        # 기존 청크 삭제 후 재추가
        try:
            engine.vector_store.delete_by_source(name)
        except Exception:
            pass  # 없어도 무방

        if content.strip():
            from utils.tokenizer import split_chunks
            chunks = split_chunks(content)
            engine.vector_store.add_documents_with_meta(
                texts=chunks,
                source=name,
                metadata={
                    "sensitivity": "internal",
                    "owner":       "admin",
                    "category":    "wiki",
                    "source_type": source_type,
                }
            )
            print(f"[WIKI_EDIT] vector 재동기화: {name} ({len(chunks)} chunks)")
    except Exception as e:
        print(f"[WIKI_EDIT] vector 재동기화 실패: {e}")


def _refresh_index():
    """entity_id_index 갱신"""
    try:
        try:
            from core.graph_rag_engine import RAGEngine   # 사용자 프로젝트: core/ 위치
        except ModuleNotFoundError:
            try:
                from graph_rag_engine import RAGEngine    # 루트 fallback
            except ModuleNotFoundError:
                import sys
                # [F821 fix 2026-05-11] previously referenced an
                # undefined ``BASE_PATH``; the in-dir() guard made it
                # silently fall through to ".". Use the module-level
                # ``BASE_DIR`` imported at the top of this file —
                # that's the intent.
                sys.path.insert(0, str(BASE_DIR))
                from core.graph_rag_engine import RAGEngine
        engine = RAGEngine(default_role="admin")
        engine.wiki_generator.refresh_entity_map()
        print("[WIKI_EDIT] entity_id_index 갱신 완료")
    except Exception as e:
        print(f"[WIKI_EDIT] entity_id_index 갱신 실패: {e}")


# ─────────────────────────────────────────────
# 핵심 탐색
# ─────────────────────────────────────────────

def find_entity_file(name: str) -> Optional[Path]:
    """
    이름으로 entity .md 파일 탐색.
    wiki/prod/entity/ 하위 전체를 검색.
    """
    if not WIKI_PATH.exists():
        return None

    name_lower = name.lower().replace(" ", "_")

    for md in WIKI_PATH.rglob("*.md"):
        if not _in_wiki_dir(md):
            continue
        if md.stem.lower().replace(" ", "_") == name_lower:
            return md
        # frontmatter의 name 필드도 확인
        try:
            content = md.read_text(encoding="utf-8")
            if re.search(rf'name:\s*["\']?{re.escape(name)}["\']?', content, re.IGNORECASE):
                return md
        except Exception:
            pass

    return None


def list_entities(entity_type: str = "", limit: int = 50) -> list:
    """entity 목록 반환"""
    results = []
    pattern = "**/*.md"
    for md in list(WIKI_PATH.rglob(pattern))[:limit]:
        if not _in_wiki_dir(md): continue
        results.append({
            "name": md.stem,
            "path": str(md.relative_to(WIKI_PATH)),
        })
    return results


# ─────────────────────────────────────────────
# CRUD 핵심 함수
# ─────────────────────────────────────────────

def read_entity(name: str) -> Tuple[bool, str, str]:
    """
    entity 읽기.
    Returns: (success, content, message)
    """
    path = find_entity_file(name)
    if not path:
        return False, "", f"'{name}' entity 파일을 찾을 수 없습니다."
    content = path.read_text(encoding="utf-8")
    return True, content, f"'{name}' 읽기 완료: {path}"


def update_entity(name: str, new_content: str,
                  user_role: str = "admin") -> Tuple[bool, str]:
    """
    entity 파일 내용 전체 업데이트.
    Returns: (success, message)
    """
    path = find_entity_file(name)
    if not path:
        return False, f"'{name}' 파일 없음"

    if not _in_wiki_dir(path):
        return False, "WIKI_DIR 범위 외 파일 접근 차단"

    backup = _backup(path)
    old_content = path.read_text(encoding="utf-8")

    path.write_text(new_content, encoding="utf-8")
    _audit("UPDATE", str(path.name), f"chars {len(old_content)}→{len(new_content)}", user_role)
    _resync_vector(path.name, new_content)
    _refresh_index()

    return True, f"✅ '{name}' 수정 완료 (백업: {backup.name})"


def append_to_entity(name: str, append_text: str,
                     user_role: str = "admin") -> Tuple[bool, str]:
    """
    entity 파일 끝에 내용 추가.
    Returns: (success, message)
    """
    path = find_entity_file(name)
    if not path:
        return False, f"'{name}' 파일 없음"

    if not _in_wiki_dir(path):
        return False, "WIKI_DIR 범위 외 파일 접근 차단"

    backup = _backup(path)
    old_content = path.read_text(encoding="utf-8")
    new_content = old_content.rstrip() + "\n\n" + append_text.strip()

    path.write_text(new_content, encoding="utf-8")
    _audit("APPEND", path.name, append_text[:60], user_role)
    _resync_vector(path.name, new_content)
    _refresh_index()

    return True, f"✅ '{name}'에 내용 추가 완료 (백업: {backup.name})"


def delete_entity(name: str, user_role: str = "admin") -> Tuple[bool, str]:
    """
    entity 파일 삭제 (백업 후).
    Returns: (success, message)
    """
    path = find_entity_file(name)
    if not path:
        return False, f"'{name}' 파일 없음"

    if not _in_wiki_dir(path):
        return False, "WIKI_DIR 범위 외 파일 접근 차단"

    backup = _backup(path)
    content = path.read_text(encoding="utf-8")

    path.unlink()
    _audit("DELETE", path.name, f"삭제됨 (백업: {backup.name})", user_role)

    # vector에서 제거
    try:
        try:
            from core.graph_rag_engine import RAGEngine   # 사용자 프로젝트: core/ 위치
        except ModuleNotFoundError:
            try:
                from graph_rag_engine import RAGEngine    # 루트 fallback
            except ModuleNotFoundError:
                import sys
                # [F821 fix 2026-05-11] previously referenced an
                # undefined ``BASE_PATH``; the in-dir() guard made it
                # silently fall through to ".". Use the module-level
                # ``BASE_DIR`` imported at the top of this file —
                # that's the intent.
                sys.path.insert(0, str(BASE_DIR))
                from core.graph_rag_engine import RAGEngine
        RAGEngine(default_role="admin").vector_store.delete_by_source(path.name)
    except Exception:
        pass

    _refresh_index()
    return True, f"✅ '{name}' 삭제 완료 (백업: {backup.name})"


def create_entity(name: str, entity_type: str, description: str,
                  relations: list = None, sensitivity: str = "internal",
                  source_type: str = "prod",
                  user_role: str = "admin") -> Tuple[bool, str]:
    """
    새 entity 파일 생성.
    Returns: (success, message)
    """
    from datetime import datetime
    normalized = re.sub(r'[^\w가-힣]', '_', name).strip('_')
    type_dir   = WIKI_PATH / source_type / "entity" / entity_type
    type_dir.mkdir(parents=True, exist_ok=True)

    path = type_dir / f"{normalized}.md"
    if path.exists():
        return False, f"'{name}' 파일이 이미 존재합니다: {path}"

    rel_lines = ""
    if relations:
        rel_list = "\n".join(
            f"  - target: {r.get('target','')}\n"
            f"    type: {r.get('type','관련')}\n"
            f"    confidence: 0.8"
            for r in relations
        )
        rel_lines = f"relations:\n{rel_list}"
    else:
        rel_lines = "relations: []"

    content = (
        f"---\n"
        f"entity_id: {normalized}_{datetime.now().strftime('%Y%m%d%H%M%S')}\n"
        f"name: {name}\n"
        f"entity_type: {entity_type}\n"
        f"sensitivity: {sensitivity}\n"
        f"source_type: {source_type}\n"
        f"created_at: {datetime.now().isoformat()}\n"
        f"{rel_lines}\n"
        f"---\n\n"
        f"# {name}\n\n"
        f"{description}\n"
    )

    path.write_text(content, encoding="utf-8")
    _audit("CREATE", path.name, f"type={entity_type} desc={description[:40]}", user_role)
    _resync_vector(path.name, content, source_type)
    _refresh_index()

    return True, f"✅ '{name}' 생성 완료: {path}"


# ─────────────────────────────────────────────
# LLM 명령 파싱 헬퍼
# ─────────────────────────────────────────────

def parse_edit_intent(query: str) -> Dict[str, Any]:
    """
    챗 명령에서 편집 의도 파싱.
    Returns: {action, target, detail}

    예:
      "김철수 정보에 삼성전자 퇴직 추가해줘"
        → {action: "append", target: "김철수", detail: "삼성전자 퇴직"}
      "이영희 파일 삭제해줘"
        → {action: "delete", target: "이영희", detail: ""}
      "새로운 박민수 entity 만들어줘 - 서울대 법학과"
        → {action: "create", target: "박민수", detail: "서울대 법학과"}
    """
    q = query.strip()

    # 삭제 패턴
    if re.search(r'(삭제|제거|지워|없애)', q):
        target = _extract_target(q, r'(삭제|제거|지워|없애)')
        return {"action": "delete", "target": target, "detail": ""}

    # 생성 패턴
    if re.search(r'(추가|만들어|생성|새로운|새로 만)', q):
        # "만들어줘" 앞에 대상이 오는 경우
        if re.search(r'새\s*(entity|항목|파일|정보)', q, re.IGNORECASE):
            target = _extract_target(q, r'(새|생성|만들어)')
            detail = re.sub(r'.*(새|생성|만들어).+?[-:]\s*', '', q).strip()
            return {"action": "create", "target": target, "detail": detail}
        # "~에 추가해줘" → append
        if re.search(r'에\s*(추가|더해)', q):
            target = _extract_target(q, r'에\s*(추가|더해)')
            detail = re.sub(r'.*에\s*(추가|더해).+', '', q).strip()
            detail = re.sub(rf'{re.escape(target)}\s*에\s*(추가|더해)\s*', '', q).strip()
            return {"action": "append", "target": target, "detail": detail}

    # 수정 패턴
    if re.search(r'(수정|변경|고쳐|바꿔|업데이트)', q):
        target = _extract_target(q, r'(수정|변경|고쳐|바꿔|업데이트)')
        detail = re.sub(r'.*(수정|변경|고쳐|바꿔|업데이트).*', '', q).strip()
        return {"action": "update", "target": target, "detail": detail}

    return {"action": "unknown", "target": "", "detail": q}


def _extract_target(query: str, stop_pattern: str) -> str:
    """명령어 앞의 대상(entity 이름) 추출"""
    # stop_pattern 이전 텍스트에서 마지막 명사 추출
    before = re.split(stop_pattern, query)[0].strip()
    # 조사 제거 (을/를/의/에/은/는)
    before = re.sub(r'(을|를|의|에|은|는|이|가|로|으로)\s*$', '', before).strip()
    # 마지막 단어 추출
    words = before.split()
    return words[-1] if words else ""
