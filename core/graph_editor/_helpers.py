"""Graph editor — shared helpers (file I/O + ontology + relation lookup).

Frontmatter read/write, entity-by-id loader, ontology-driven
forward/inverse type pair, relation-index search, and the
source-list normalizer/validator. Used by every write operation in
``_writes.py`` and by the ``read_relation`` accessor in the
package facade.

Split out of the monolithic ``core/graph_editor.py`` in Stage C.5
(2026-05-24) so the package respects CLAUDE.md rule #5 (< 20 KB
per file).
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from core.relations_schema import (
    MANUAL_SOURCE_ROLE,
    VALID_SOURCE_ROLES,
)


_FM_SPLIT_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)


# ─────────────────────────────────────────────────────────────────
# entity 파일 I/O (cascade.py 의 helper 와 동일 패턴이지만 dedup 안 함
# — 두 모듈은 독립 lifecycle 이라 미세 결합 회피)
# ─────────────────────────────────────────────────────────────────

def _read_entity(path: Path) -> Optional[Tuple[Dict[str, Any], str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    m = _FM_SPLIT_RE.match(text)
    if not m:
        return None
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(fm, dict):
        return None
    return fm, m.group(2)


def _write_entity(path: Path, fm: Dict[str, Any], body: str) -> None:
    text = yaml.safe_dump(
        fm, allow_unicode=True, sort_keys=False, default_flow_style=False,
    ).rstrip()
    path.write_text(f"---\n{text}\n---\n{body}", encoding="utf-8")


def _load_entity_by_id(
    entity_id: str,
    wiki_generator,
) -> Tuple[Path, Dict[str, Any], str]:
    """entity_id → (path, frontmatter, body). 없으면 ValueError."""
    idx = getattr(wiki_generator, "entity_id_index", {}) or {}
    path = idx.get(entity_id)
    if not path:
        # 인덱스 미스 — fresh rebuild 한 번 시도
        try:
            wiki_generator.refresh_entity_map()
            path = wiki_generator.entity_id_index.get(entity_id)
        except Exception:
            path = None
    if not path:
        raise ValueError(f"entity_id not found: {entity_id}")
    parsed = _read_entity(Path(path))
    if not parsed:
        raise ValueError(f"entity file unreadable: {path}")
    fm, body = parsed
    return Path(path), fm, body


# ─────────────────────────────────────────────────────────────────
# ontology — forward/inverse type pair 도출
# ─────────────────────────────────────────────────────────────────

def _inverse_type(forward_type: str) -> str:
    """ontology 가 정의한 inverse type 을 반환. 미정의면 자신 (대칭).

    RELATED_TO 같은 대칭 relation 은 inverse 가 자신과 같다. 비대칭
    (BELONGS_TO ↔ HAS_MEMBER) 은 명시적 mapping. 정의 부재 시 안전한
    fallback 으로 forward 와 같은 type 반환.
    """
    try:
        from core.ontology import RELATION_TYPES, normalize_relation
    except ImportError:
        return forward_type
    std = normalize_relation(forward_type)
    info = RELATION_TYPES.get(std, {})
    inv = info.get("inverse")
    return inv or std


def _label_for_type(rel_type: str) -> str:
    try:
        from core.ontology import RELATION_TYPES, get_relation_label
    except ImportError:
        return rel_type
    info = RELATION_TYPES.get(rel_type, {})
    if info.get("label"):
        return info["label"]
    return get_relation_label(rel_type) or rel_type


# ─────────────────────────────────────────────────────────────────
# relation 매칭 + sources 합성
# ─────────────────────────────────────────────────────────────────

def _find_relation_index(
    relations: List[Dict[str, Any]],
    target_id: str,
    rel_type:  str,
) -> Optional[int]:
    """frontmatter 의 ``relations`` 배열에서 (target_id, type) 매칭
    relation 의 index 반환. 같은 (target_id, type) 가 여러 개 있으면
    첫 번째. None 이면 매칭 없음."""
    for i, rel in enumerate(relations):
        if not isinstance(rel, dict):
            continue
        if rel.get("target_id") == target_id and rel.get("type") == rel_type:
            return i
    return None


def _validate_sources(sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """클라이언트가 보낸 sources 배열을 정규화 + 검증.

    - dict 가 아닌 항목은 drop.
    - weight 는 [0.0, 1.0] 으로 clamp.
    - role 은 VALID_SOURCE_ROLES 중 하나여야 함 (외 → 예외).
    - manual / extract 등 모든 role 허용 — 보안 결정은 endpoint 에서
      (admin 만 호출 가능).
    - ts 가 없으면 now() 로 채움.
    """
    out: List[Dict[str, Any]] = []
    now_iso = datetime.now().isoformat()
    for s in sources or []:
        if not isinstance(s, dict):
            continue
        role = s.get("role")
        if role not in VALID_SOURCE_ROLES:
            raise ValueError(f"invalid source role: {role!r}")
        try:
            w = float(s.get("weight", 0.0))
        except (TypeError, ValueError):
            w = 0.0
        w = max(0.0, min(1.0, w))
        entry: Dict[str, Any] = {
            "doc_id": s.get("doc_id"),
            "weight": w,
            "role":   role,
            "ts":     s.get("ts") or now_iso,
        }
        # optional metadata for manual sources
        if role == MANUAL_SOURCE_ROLE:
            if s.get("author"):
                entry["author"] = str(s["author"])[:80]
            if s.get("note"):
                entry["note"] = str(s["note"])[:300]
        out.append(entry)
    return out


__all__ = [
    "_FM_SPLIT_RE",
    "_read_entity",
    "_write_entity",
    "_load_entity_by_id",
    "_inverse_type",
    "_label_for_type",
    "_find_relation_index",
    "_validate_sources",
]
