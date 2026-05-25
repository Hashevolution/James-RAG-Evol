"""Graph editor — 3 edge-mutation operations (PUT / POST / DELETE).

The bilaterally-synced write operations called by ``/admin/graph/relation``:

- ``replace_relation_sources`` — PUT semantics; entire sources array
  swapped on both forward + inverse entities
- ``append_relation_source`` — POST semantics; commutative single-
  source append
- ``delete_relation`` — DELETE; remove the relation entirely from
  both entities

Each returns an audit-friendly diff dict (``before`` / ``after``
sources arrays on each side) consumed by the audit-log writer.

Split out of the monolithic ``core/graph_editor.py`` in Stage C.5
(2026-05-24). All three are re-exported from
``core.graph_editor`` so existing import paths keep working.
"""
from __future__ import annotations

from typing import Any, Dict, List

from core.relations_schema import compute_confidence_from_sources

from ._helpers import (
    _find_relation_index,
    _inverse_type,
    _label_for_type,
    _load_entity_by_id,
    _validate_sources,
    _write_entity,
)


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


__all__ = [
    "replace_relation_sources",
    "append_relation_source",
    "delete_relation",
]
