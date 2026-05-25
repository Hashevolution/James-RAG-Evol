"""Cascade — Phase D (modify cascade).

``docs/design/v0.3-knowledge-cascade.md`` §6 — Phase D reference
implementation.

업로드 파일의 내용 교체 (재업로드 또는 in-place edit) 시 그 파일이
만들어낸 파생물을 cascade 한다. Phase C 와 차이:

- Phase C 는 파일 자체가 사라짐 → 모든 파생물 삭제.
- Phase D 는 파일 ID 는 유지 + 내용만 교체 → cascade 후 새 content
  로 ingestion 재실행 (sidecar 도 새로 작성).

실용적 접근 (디자인 §6 의 "kept-ts 갱신 허용"):

  1. 기존 sidecar 로드 → diff 시각화용 통계만 사용 (실제 cascade 는
     doc_id 전체 wipe 가 더 간결).
  2. cascade_remove_doc_from_sources(doc_id) — 이 doc 의 source 전체
     제거. manual / 다른 doc 의 source 는 영향 없음.
  3. orphan sweep — incoming 0 AND remaining relations 0.
  4. vector chunks 갱신 — delete old + add new.
  5. 물리 파일 내용 교체 (.deleted/ 백업).
  6. 새 content 로 ingestion 재실행 (sidecar 도 새로 생성).
  7. 새 metadata 가 있으면 적용.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._delete import (
    backup_upload_file,
    cascade_remove_doc_from_sources,
    find_orphan_entities,
)
from ._helpers import strip_uuid_prefix


def load_extraction_sidecar(
    physical_filename: str,
    upload_dir:        Path,
) -> Optional[Dict[str, Any]]:
    """Phase B (PR #269) 의 ingestion 이 저장한 LLM extraction sidecar 를
    로드. 없거나 손상되면 None.

    Phase D 의 modify cascade 가 diff 시작점으로 사용 — None 이면
    wipe+reingest fallback (sidecar 가 없는 = Phase D 이전 업로드
    또는 1회용 web 학습 등).
    """
    p = Path(upload_dir) / (physical_filename + ".extraction.json")
    if not p.is_file():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return None


def diff_triples(
    old_extraction: Optional[Dict[str, Any]],
    new_extraction: Dict[str, Any],
) -> Dict[str, list]:
    """LLM extraction 의 (entities, relations) 두 셋을 비교해 변경 분류.

    Triple identity = (subject_name_lower, label_lower, object_name_lower).
    designs §9 의 risk: LLM 재추출 비결정성 → label / weight 의 미세한
    변동이 false-positive 변경을 일으킨다. 본 함수는 label 을 lowercase
    매칭으로 정규화 (대소문자 차이 무시) — weight 변동 무시는 호출자
    (cascade_modify_doc) 가 처리한다.

    Returns: {
      "added_entities":   [{name, type, description}]    — new 에만 있는 entity
      "removed_entities": [{name, type}]                 — old 에만 있는 entity
      "added_triples":    [{source, target, label, confidence}]
      "removed_triples":  [{source, target, label, confidence}]
      "kept_triples":     [{source, target, label, confidence}]
    }
    """
    def _ent_key(e):
        return (
            (e.get("name") or "").strip().lower(),
            (e.get("type") or "concept").strip().lower(),
        )

    def _triple_key(r):
        return (
            (r.get("source") or "").strip().lower(),
            (r.get("label")  or "관련").strip().lower(),
            (r.get("target") or "").strip().lower(),
        )

    old_ext = (old_extraction or {}).get("extraction", old_extraction or {}) or {}
    old_ents = old_ext.get("entities", []) or []
    old_rels = old_ext.get("relations", []) or []
    new_ents = new_extraction.get("entities", []) or []
    new_rels = new_extraction.get("relations", []) or []

    old_ent_map = {_ent_key(e): e for e in old_ents if isinstance(e, dict)}
    new_ent_map = {_ent_key(e): e for e in new_ents if isinstance(e, dict)}
    old_rel_map = {_triple_key(r): r for r in old_rels if isinstance(r, dict)}
    new_rel_map = {_triple_key(r): r for r in new_rels if isinstance(r, dict)}

    added_entities   = [new_ent_map[k] for k in new_ent_map if k not in old_ent_map]
    removed_entities = [old_ent_map[k] for k in old_ent_map if k not in new_ent_map]
    added_triples    = [new_rel_map[k] for k in new_rel_map if k not in old_rel_map]
    removed_triples  = [old_rel_map[k] for k in old_rel_map if k not in new_rel_map]
    kept_triples     = [new_rel_map[k] for k in new_rel_map if k in old_rel_map]

    return {
        "added_entities":   added_entities,
        "removed_entities": removed_entities,
        "added_triples":    added_triples,
        "removed_triples":  removed_triples,
        "kept_triples":     kept_triples,
    }


def cascade_modify_doc(
    physical_filename: str,
    new_content:       str,
    *,
    wiki_generator,
    vector_store,
    upload_dir:        Path,
    new_metadata:      Optional[Dict[str, Any]] = None,
    user_role:         str = "admin",
) -> Dict[str, Any]:
    """업로드 파일의 내용을 새 ``new_content`` 로 교체하고 그 파일이
    만들어낸 wiki 파생물을 갱신한다. 디자인 §6 — Phase D.

    실용적 구현 (kept-ts 갱신 허용):
      1. 기존 sidecar 로드 → diff 시각화용 통계만 사용 (실제 cascade
         는 doc_id 전체 wipe 가 더 간결)
      2. cascade_remove_doc_from_sources(doc_id) — 이 doc 의 source
         전체 제거. manual / 다른 doc 의 source 는 영향 없음.
      3. orphan sweep — incoming 0 AND remaining relations 0
      4. vector chunks 갱신 — delete old + add new
      5. 물리 파일 내용 교체 (.deleted/ 백업)
      6. 새 content 로 ingestion 재실행 (sidecar 도 새로 생성)
      7. 새 metadata 가 있으면 적용

    Returns: 디자인 §5 형식과 유사하지만 modify 전용 통계 포함:
      {
        "physical_filename":    str,
        "original_filename":    str,
        "doc_entity_id":        str,
        "sidecar_present":      bool,    # diff 가능 여부
        "diff":                 {added/removed/kept counts} | None,
        "cascade_counts":       {entities_touched, relations_dropped, ...},
        "orphan_entities_deleted": int,
        "vector_replaced":      bool,
        "file_backup":          str,
        "reingest_entity_ids":  [str],
        "user_role":            str,
      }
    """
    physical_path = Path(upload_dir) / physical_filename
    if not physical_path.is_file():
        raise FileNotFoundError(f"upload not found: {physical_path}")

    original_filename = strip_uuid_prefix(physical_filename)
    doc_name          = os.path.splitext(original_filename)[0]
    doc_entity_id     = wiki_generator._generate_entity_id(doc_name, "document")
    entity_root       = Path(wiki_generator.entity_path)
    upload_dir        = Path(upload_dir)

    # Step 1 — sidecar 로드 + diff 통계 (실제 cascade 결정에는 사용하지
    # 않지만 audit/UI 노출용)
    old_sidecar = load_extraction_sidecar(physical_filename, upload_dir)
    # 새 추출은 ingestion path 에서 다시 도므로 여기선 diff 만 위해 호출
    diff_stats = None
    if old_sidecar is not None:
        try:
            new_extraction_preview = wiki_generator._llm_extract_document_entities(
                original_filename, new_content, new_metadata or {},
            )
            diff = diff_triples(old_sidecar, new_extraction_preview)
            diff_stats = {
                "added_entities":     len(diff["added_entities"]),
                "removed_entities":   len(diff["removed_entities"]),
                "added_triples":      len(diff["added_triples"]),
                "removed_triples":    len(diff["removed_triples"]),
                "kept_triples":       len(diff["kept_triples"]),
            }
        except Exception as e:
            print(f"[CASCADE_MODIFY] diff preview skipped: {e}")

    # Step 2 — 이 doc 의 source 전체 wipe (manual 은 자동 보존)
    cascade_counts = cascade_remove_doc_from_sources(doc_entity_id, entity_root)

    # Step 3 — orphan sweep
    orphan_paths = find_orphan_entities(
        original_filename, doc_entity_id, entity_root,
    )
    for p in orphan_paths:
        try:
            p.unlink()
        except OSError as e:
            print(f"[CASCADE_MODIFY] orphan unlink fail {p}: {e}")

    # doc entity 본체는 modify 에서는 유지 (같은 filename 이 재추출됨).
    # 다만 그 outgoing relations 가 cascade 에 의해 비워졌으므로 다음
    # ingestion 이 다시 채울 수 있도록 한다. 만약 doc entity 가 orphan
    # sweep 에 걸렸을 경우 (실제로는 source_document 매칭 X 라 안 걸림),
    # ingestion 이 새로 생성한다.

    # Step 4 — vector chunks 교체
    vec_replaced = False
    try:
        vector_store.delete_by_source(original_filename)
        # add 는 ingestion 의 일이 아니라 endpoint 의 일 — 본 함수 입장에선
        # ingestion 호출 전 cleanup 만. 새 chunk add 는 endpoint 가 한다
        # (vector_store.add_documents_with_meta 시그니처가 environment-
        # 별로 다를 수 있어 직접 의존을 만들지 않는다).
        vec_replaced = True
    except Exception as e:
        print(f"[CASCADE_MODIFY] vector delete fail: {e}")

    # Step 5 — 물리 파일 → .deleted/ 백업, 그 자리에 새 content
    backup_path = backup_upload_file(physical_path, upload_dir)
    physical_path.write_text(new_content, encoding="utf-8") \
        if isinstance(new_content, str) \
        else physical_path.write_bytes(new_content)

    # Step 6 — ingestion 재실행. sidecar 도 새로 작성됨.
    sidecar_path = str(upload_dir / (physical_filename + ".extraction.json"))
    reingest_ids: List[str] = []
    try:
        reingest_ids = list(
            wiki_generator.process_document_for_entities(
                original_filename,
                new_content if isinstance(new_content, str) else
                new_content.decode("utf-8", errors="replace"),
                [],
                user_role=user_role,
                metadata=new_metadata or {},
                extraction_sidecar_path=sidecar_path,
            ) or []
        )
    except TypeError:
        # 구버전 시그니처 fallback
        try:
            reingest_ids = list(
                wiki_generator.process_document_for_entities(
                    original_filename,
                    new_content if isinstance(new_content, str) else
                    new_content.decode("utf-8", errors="replace"),
                    [], user_role=user_role, metadata=new_metadata or {},
                ) or []
            )
        except Exception as e:
            print(f"[CASCADE_MODIFY] reingest fail: {e}")
    except Exception as e:
        print(f"[CASCADE_MODIFY] reingest fail: {e}")

    try:
        if hasattr(wiki_generator, "refresh_entity_map"):
            wiki_generator.refresh_entity_map()
    except Exception as e:
        print(f"[CASCADE_MODIFY] entity index refresh skipped: {e}")

    return {
        "physical_filename":       physical_filename,
        "original_filename":       original_filename,
        "doc_entity_id":           doc_entity_id,
        "sidecar_present":         old_sidecar is not None,
        "diff":                    diff_stats,
        "cascade_counts":          cascade_counts,
        "orphan_entities_deleted": len(orphan_paths),
        "vector_replaced":         vec_replaced,
        "file_backup":             str(backup_path.relative_to(upload_dir)),
        "reingest_entity_ids":     reingest_ids,
        "user_role":               user_role,
    }


__all__ = [
    "load_extraction_sidecar",
    "diff_triples",
    "cascade_modify_doc",
]
