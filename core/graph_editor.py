"""
PROJECT JAMES — Knowledge Cascade Phase E (graph editor backend).

docs/design/v0.3-knowledge-cascade.md §7 — Phase E.

`/admin/graph` 의 admin 이 edge 별 sources 를 직접 수정할 수 있게 하는
3 endpoint 의 코어 로직. UI 가 클릭한 edge 의 source list / weight /
role 을 받아 양방향 entity 파일의 frontmatter relation 의 ``sources``
배열을 갱신한다.

Phase B (PR #269) 가 ingestion 시점에 `sources` 를 stamp 하고
Phase C (PR #270) 가 cascade 가 manual source 를 보존하도록 만들었기
때문에, Phase E 의 manual source write 는 자연스럽게 cascade-안전:
admin 이 추가한 ``role=manual`` source 는 doc 파일 삭제 시에도
유지된다.

Trust model (§7):
  - admin 만 호출 가능 (server endpoint 에서 admin.data feature gate
    + ``JAMES_GRAPH_EDIT=1`` env flag opt-in).
  - 모든 write 는 양쪽 (forward + inverse) entity 파일에 동시 반영.
  - audit log 에 before+after sources 배열 차이 기록.
  - 두 admin 의 동시 PUT 은 last-writer-wins. POST (append) 는 commutative.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from core.relations_schema import (
    MANUAL_SOURCE_ROLE,
    VALID_SOURCE_ROLES,
    compute_confidence_from_sources,
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


def read_relation(
    src_entity_id: str,
    tgt_entity_id: str,
    relation_type: str,
    *,
    wiki_generator,
) -> Optional[Dict[str, Any]]:
    """forward 측 entity 의 frontmatter 에서 매칭 relation dict 를 그대로
    반환 (sources 배열 포함). 없으면 None.

    UI 의 edit modal 이 edge 클릭 시 sources 를 fresh load 하기 위한
    read path. snapshot endpoint 에 sources 를 넣지 않은 이유는 213
    entity × N relation × N source 면 wire payload 가 폭증하기 때문 —
    on-demand fetch 로 격리.
    """
    src_path, src_fm, _body = _load_entity_by_id(src_entity_id, wiki_generator)
    _ = src_path   # unused
    rels = src_fm.get("relations") or []
    idx = _find_relation_index(rels, tgt_entity_id, relation_type)
    if idx is None:
        return None
    rel = rels[idx]
    # 안전한 복사본 — caller 가 변형해도 frontmatter 무영향
    if isinstance(rel, dict):
        return dict(rel)
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


# ─────────────────────────────────────────────────────────────────
# Public API — 3 mutation operations
# ─────────────────────────────────────────────────────────────────

def replace_relation_sources(
    src_entity_id: str,
    tgt_entity_id: str,
    relation_type: str,
    new_sources:   List[Dict[str, Any]],
    *,
    wiki_generator,
    sync_inverse:  bool = True,
) -> Dict[str, Any]:
    """PUT semantics — forward + inverse 양쪽 relation 의 sources 를
    전부 ``new_sources`` 로 교체. confidence 는 자동 derive. 매칭
    relation 이 없으면 새로 만든다.

    Returns audit-friendly diff:
      {
        "forward": {"before": [...], "after": [...]},
        "inverse": {"before": [...], "after": [...]} | None,
        "src_entity_id": ..., "tgt_entity_id": ...,
        "relation_type": ..., "inverse_type": ...,
      }
    """
    sources = _validate_sources(new_sources)
    if not sources:
        raise ValueError("new_sources must not be empty for PUT — use DELETE instead")

    src_path, src_fm, src_body = _load_entity_by_id(src_entity_id, wiki_generator)
    inv_type = _inverse_type(relation_type)

    src_rels = list(src_fm.get("relations") or [])
    fwd_idx = _find_relation_index(src_rels, tgt_entity_id, relation_type)
    fwd_before = list(src_rels[fwd_idx].get("sources", [])) \
                 if fwd_idx is not None else []

    fwd_rel = src_rels[fwd_idx] if fwd_idx is not None else {
        "target":      None,    # 채워짐 (tgt entity load 후)
        "target_id":   tgt_entity_id,
        "target_type": None,
        "type":        relation_type,
        "label":       _label_for_type(relation_type),
    }
    fwd_rel["sources"]    = sources
    fwd_rel["confidence"] = compute_confidence_from_sources(sources)

    inv_diff = None
    inv_path = inv_fm = inv_body = None
    if sync_inverse:
        try:
            inv_path, inv_fm, inv_body = _load_entity_by_id(
                tgt_entity_id, wiki_generator,
            )
        except ValueError:
            # target entity 가 없으면 inverse 동기화 skip (forward 만 반영).
            # admin 이 의도적으로 dangling edge 를 만들 수도 있으므로 에러
            # 가 아닌 부분-성공으로 처리.
            inv_path = None

    if inv_path is not None:
        # forward 의 target 이름/타입을 inverse 의 self 로 사용.
        # source entity 의 name 으로 채워야 함.
        src_name = src_fm.get("name") or ""
        src_type = src_fm.get("entity_type") or ""
        # forward rel 의 target_name 도 inverse 의 self 이름과 일치해야 자연
        if fwd_rel.get("target") is None:
            fwd_rel["target"] = inv_fm.get("name", tgt_entity_id)
        if fwd_rel.get("target_type") is None:
            fwd_rel["target_type"] = inv_fm.get("entity_type", "concept")

        inv_rels = list(inv_fm.get("relations") or [])
        inv_idx = _find_relation_index(inv_rels, src_entity_id, inv_type)
        inv_before = list(inv_rels[inv_idx].get("sources", [])) \
                     if inv_idx is not None else []
        inv_rel = inv_rels[inv_idx] if inv_idx is not None else {
            "target":      src_name,
            "target_id":   src_entity_id,
            "target_type": src_type,
            "type":        inv_type,
            "label":       _label_for_type(inv_type),
        }
        inv_rel["sources"]    = sources
        inv_rel["confidence"] = compute_confidence_from_sources(sources)
        if inv_idx is None:
            inv_rels.append(inv_rel)
        else:
            inv_rels[inv_idx] = inv_rel
        inv_fm["relations"] = inv_rels
        _write_entity(inv_path, inv_fm, inv_body)
        inv_diff = {"before": inv_before, "after": list(sources)}

    if fwd_idx is None:
        src_rels.append(fwd_rel)
    else:
        src_rels[fwd_idx] = fwd_rel
    src_fm["relations"] = src_rels
    _write_entity(src_path, src_fm, src_body)

    return {
        "forward":        {"before": fwd_before, "after": list(sources)},
        "inverse":        inv_diff,
        "src_entity_id":  src_entity_id,
        "tgt_entity_id":  tgt_entity_id,
        "relation_type":  relation_type,
        "inverse_type":   inv_type,
    }


def append_relation_source(
    src_entity_id: str,
    tgt_entity_id: str,
    relation_type: str,
    source:        Dict[str, Any],
    *,
    wiki_generator,
    sync_inverse:  bool = True,
) -> Dict[str, Any]:
    """POST semantics — 단일 source 를 forward + inverse 양쪽 relation
    의 sources 배열 끝에 append. 매칭 relation 이 없으면 새로 만든다.

    동시 호출 시 commutative (append 만 하므로). 같은 source 가 두 번
    append 되면 두 row 가 모두 보존 — dedup 은 admin 의 일.
    """
    src_norm = _validate_sources([source])
    if not src_norm:
        raise ValueError("source must be a valid sources entry")
    one = src_norm[0]

    src_path, src_fm, src_body = _load_entity_by_id(src_entity_id, wiki_generator)
    inv_type = _inverse_type(relation_type)

    src_rels = list(src_fm.get("relations") or [])
    fwd_idx = _find_relation_index(src_rels, tgt_entity_id, relation_type)
    if fwd_idx is None:
        # forward relation 신규 생성
        # target 이름/타입은 inverse load 가능하면 거기서 / 아니면 placeholder
        tgt_name = tgt_entity_id
        tgt_type = "concept"
        try:
            _, inv_fm_peek, _ = _load_entity_by_id(tgt_entity_id, wiki_generator)
            tgt_name = inv_fm_peek.get("name", tgt_entity_id)
            tgt_type = inv_fm_peek.get("entity_type", "concept")
        except ValueError:
            pass
        new_rel = {
            "target":      tgt_name,
            "target_id":   tgt_entity_id,
            "target_type": tgt_type,
            "type":        relation_type,
            "label":       _label_for_type(relation_type),
            "confidence":  0.0,
            "sources":     [],
        }
        src_rels.append(new_rel)
        fwd_idx = len(src_rels) - 1

    fwd_before = list(src_rels[fwd_idx].get("sources", []))
    new_fwd_sources = list(fwd_before) + [one]
    src_rels[fwd_idx]["sources"]    = new_fwd_sources
    src_rels[fwd_idx]["confidence"] = compute_confidence_from_sources(
        new_fwd_sources
    )
    src_fm["relations"] = src_rels
    _write_entity(src_path, src_fm, src_body)

    inv_diff = None
    if sync_inverse:
        try:
            inv_path, inv_fm, inv_body = _load_entity_by_id(
                tgt_entity_id, wiki_generator,
            )
        except ValueError:
            inv_path = None

        if inv_path is not None:
            inv_rels = list(inv_fm.get("relations") or [])
            inv_idx = _find_relation_index(inv_rels, src_entity_id, inv_type)
            if inv_idx is None:
                inv_rels.append({
                    "target":      src_fm.get("name", src_entity_id),
                    "target_id":   src_entity_id,
                    "target_type": src_fm.get("entity_type", "concept"),
                    "type":        inv_type,
                    "label":       _label_for_type(inv_type),
                    "confidence":  0.0,
                    "sources":     [],
                })
                inv_idx = len(inv_rels) - 1
            inv_before = list(inv_rels[inv_idx].get("sources", []))
            new_inv_sources = list(inv_before) + [one]
            inv_rels[inv_idx]["sources"]    = new_inv_sources
            inv_rels[inv_idx]["confidence"] = compute_confidence_from_sources(
                new_inv_sources
            )
            inv_fm["relations"] = inv_rels
            _write_entity(inv_path, inv_fm, inv_body)
            inv_diff = {"before": inv_before, "after": new_inv_sources}

    return {
        "forward":       {"before": fwd_before, "after": new_fwd_sources},
        "inverse":       inv_diff,
        "src_entity_id": src_entity_id,
        "tgt_entity_id": tgt_entity_id,
        "relation_type": relation_type,
        "inverse_type":  inv_type,
    }


def delete_relation(
    src_entity_id: str,
    tgt_entity_id: str,
    relation_type: str,
    *,
    wiki_generator,
    sync_inverse:  bool = True,
) -> Dict[str, Any]:
    """DELETE semantics — forward + inverse 양쪽 relation 자체를 제거.

    매칭 relation 이 없으면 no-op (해당 측 ``removed`` False 반환).
    """
    src_path, src_fm, src_body = _load_entity_by_id(src_entity_id, wiki_generator)
    inv_type = _inverse_type(relation_type)

    src_rels = list(src_fm.get("relations") or [])
    fwd_idx = _find_relation_index(src_rels, tgt_entity_id, relation_type)
    fwd_before = None
    fwd_removed = False
    if fwd_idx is not None:
        fwd_before = list(src_rels[fwd_idx].get("sources", []))
        src_rels.pop(fwd_idx)
        src_fm["relations"] = src_rels
        _write_entity(src_path, src_fm, src_body)
        fwd_removed = True

    inv_removed = False
    inv_before = None
    if sync_inverse:
        try:
            inv_path, inv_fm, inv_body = _load_entity_by_id(
                tgt_entity_id, wiki_generator,
            )
        except ValueError:
            inv_path = None
        if inv_path is not None:
            inv_rels = list(inv_fm.get("relations") or [])
            inv_idx = _find_relation_index(inv_rels, src_entity_id, inv_type)
            if inv_idx is not None:
                inv_before = list(inv_rels[inv_idx].get("sources", []))
                inv_rels.pop(inv_idx)
                inv_fm["relations"] = inv_rels
                _write_entity(inv_path, inv_fm, inv_body)
                inv_removed = True

    return {
        "forward":       {"removed": fwd_removed, "before": fwd_before},
        "inverse":       {"removed": inv_removed, "before": inv_before},
        "src_entity_id": src_entity_id,
        "tgt_entity_id": tgt_entity_id,
        "relation_type": relation_type,
        "inverse_type":  inv_type,
    }


# ─────────────────────────────────────────────────────────────────
# Env flag helper (디자인 §7 — JAMES_GRAPH_EDIT=1 opt-in)
# ─────────────────────────────────────────────────────────────────

def graph_edit_enabled() -> bool:
    """``JAMES_GRAPH_EDIT=1`` 이면 그래프 에디터 endpoint 사용 가능.

    디자인 §7 의 graceful degradation: 첫 release cycle 동안 admin 이
    명시적으로 켜야 한다. 기본 off — 운영자가 의도하지 않은 mutation
    을 실수로 invoke 할 수 없게.
    """
    v = os.environ.get("JAMES_GRAPH_EDIT", "").strip()
    return v in ("1", "true", "TRUE", "yes", "on")
