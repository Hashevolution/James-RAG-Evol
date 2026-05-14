"""
PROJECT JAMES — Knowledge Cascade Phase C (file delete).

docs/design/v0.3-knowledge-cascade.md §5 — Phase C.

업로드된 파일 1개를 삭제하면 그 파일이 만들어낸 모든 파생물 (vector
chunks / entity files / 다른 entity 의 relation 의 source) 까지 한
연산으로 cascade 한다. 이전엔 `delete_entity` + `delete_by_source` 만
있어서 "파일은 사라졌는데 entity 의 relation 안에는 그 doc 의 흔적이
남는다" 라는 데이터 부정합이 있었다.

Phase A (PR #266) 가 `sources: [{doc_id, weight, role, ts}]` 인프라를
깔고, Phase B (PR #269) 가 ingestion 시점에 sources 를 직접 쓰기
시작했다. Phase C 는 그 sources 를 **삭제 방향에서 추적** 하는 부분.

핵심 invariant (디자인 §5):
  - manual sources 는 cascade 가 건드리지 않는다 (그래프 에디터에서
    admin 이 명시적으로 추가한 source 는 파일 삭제와 무관).
  - legacy sources (doc_id=None) 도 건드리지 않는다 (Phase A back-fill,
    출처 미상이라 cascade 가 안전하게 식별할 수 없음).
  - relation 의 모든 non-manual non-legacy source 가 사라지면 relation
    자체가 사라진다. confidence 는 derived 라 자동으로 0 이 되고 곧
    relation 도 사라지므로 stale confidence 는 남지 않는다.
  - orphan entity 는 (a) `attributes.source_document == filename` 이고
    (b) 다른 어떤 entity 도 이 entity 를 target_id 로 가리키지 않을
    때만 삭제. (b) 가 만족되지 않으면 entity 는 남고 confidence 만 감소.
"""
from __future__ import annotations

import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from core.relations_schema import (
    MANUAL_SOURCE_ROLE,
    compute_confidence_from_sources,
)


# uploads/ 의 물리 파일명 prefix 패턴. /upload/ endpoint 가
# `str(uuid.uuid4()) + "_" + original_filename` 형식으로 저장하므로
# 36-char uuid + underscore 를 strip 하면 원본 이름이 나온다.
_UUID_PREFIX_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
                             r"[0-9a-f]{4}-[0-9a-f]{12}_(.+)$",
                             re.IGNORECASE)

_FM_SPLIT_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)


def strip_uuid_prefix(physical_filename: str) -> str:
    """uploads/ 물리 파일명에서 uuid prefix 를 제거해 ingestion 이 사용한
    원본 filename 을 얻는다. prefix 없으면 그대로 반환 (legacy uploads
    + 직접 배치된 파일 호환)."""
    m = _UUID_PREFIX_RE.match(physical_filename)
    return m.group(1) if m else physical_filename


def _read_frontmatter(path: Path) -> Optional[Tuple[Dict[str, Any], str]]:
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


def _write_frontmatter(path: Path, fm: Dict[str, Any], body: str) -> None:
    text = yaml.safe_dump(
        fm, allow_unicode=True, sort_keys=False, default_flow_style=False,
    ).rstrip()
    path.write_text(f"---\n{text}\n---\n{body}", encoding="utf-8")


def _iter_entity_files(entity_root: Path):
    if not entity_root.exists():
        return
    yield from entity_root.rglob("*.md")


def cascade_remove_doc_from_sources(
    doc_entity_id: str,
    entity_root:   Path,
) -> Dict[str, int]:
    """모든 entity 의 relation sources 에서 ``doc_entity_id`` 항목을 제거.

    설계 §14 의 reference 구현. manual / legacy source 는 건드리지 않음.
    sources 가 모두 사라진 relation 은 relation 자체가 사라진다.

    Returns:
        counts = {
          "entities_scanned":     int,
          "entities_touched":     int,
          "relations_recomputed": int,
          "relations_dropped":    int,
        }
    """
    counts = {
        "entities_scanned":     0,
        "entities_touched":     0,
        "relations_recomputed": 0,
        "relations_dropped":    0,
    }
    for path in _iter_entity_files(entity_root):
        parsed = _read_frontmatter(path)
        if not parsed:
            continue
        fm, body = parsed
        counts["entities_scanned"] += 1
        relations = fm.get("relations") or []
        if not isinstance(relations, list):
            continue

        new_rels: List[Dict[str, Any]] = []
        touched = False
        for rel in relations:
            if not isinstance(rel, dict):
                new_rels.append(rel)
                continue
            srcs = rel.get("sources")
            if not isinstance(srcs, list):
                new_rels.append(rel)
                continue
            # Filter: keep manual sources unconditionally; keep non-matching
            # doc_ids. Drop entries where doc_id == this doc AND role != manual.
            kept = [
                s for s in srcs
                if not (isinstance(s, dict)
                        and s.get("doc_id") == doc_entity_id
                        and s.get("role")   != MANUAL_SOURCE_ROLE)
            ]
            if len(kept) == len(srcs):
                # 이 relation 은 deleted doc 의 영향을 받지 않음
                new_rels.append(rel)
                continue
            touched = True
            if not kept:
                counts["relations_dropped"] += 1
                continue   # relation 자체가 사라짐
            rel["sources"]    = kept
            rel["confidence"] = compute_confidence_from_sources(kept)
            new_rels.append(rel)
            counts["relations_recomputed"] += 1

        if touched:
            counts["entities_touched"] += 1
            fm["relations"] = new_rels
            _write_frontmatter(path, fm, body)

    return counts


def find_orphan_entities(
    deleted_filename: str,
    deleted_doc_id:   str,
    entity_root:      Path,
) -> List[Path]:
    """``attributes.source_document == deleted_filename`` 인 entity 중
    cascade 후에 도달 불가능 + 흔적 없는 것들의 파일 경로.

    설계 §5 의 base rule (incoming 0) 를 한 단계 강화: cascade_remove_
    doc_from_sources 가 끝난 상태에서 **남은 relation 도 0** 일 때만
    orphan. 이 추가 조건은 manual source 가 살아남아 relation 자체는
    유지된 entity 를 orphan 으로 오인해 삭제하는 것을 막아준다 (성공
    기준 §12.1 의 "**only** existed because of this doc" 정합).

    선행조건: 호출 시점에 cascade_remove_doc_from_sources 가 완료되어
    있어야 stale target_id 가 incoming 에 끼지 않는다."""
    incoming_target_ids: set = set()
    candidate_paths: List[Tuple[Path, str, int]] = []
    for path in _iter_entity_files(entity_root):
        parsed = _read_frontmatter(path)
        if not parsed:
            continue
        fm, _body = parsed
        rels = fm.get("relations") or []
        if not isinstance(rels, list):
            rels = []
        for rel in rels:
            if isinstance(rel, dict):
                tid = rel.get("target_id")
                if tid and tid != "UNRESOLVED":
                    incoming_target_ids.add(tid)
        attrs = fm.get("attributes") or {}
        eid   = fm.get("entity_id", "")
        if not isinstance(attrs, dict):
            continue
        if attrs.get("source_document") == deleted_filename \
                and eid and eid != deleted_doc_id:
            candidate_paths.append((path, eid, len(rels)))

    return [
        p for p, eid, n_rels in candidate_paths
        if eid not in incoming_target_ids and n_rels == 0
    ]


def find_doc_entity_path(
    deleted_doc_id: str,
    entity_root:    Path,
) -> Optional[Path]:
    """doc entity 파일 (= ingestion 이 만들었던 document type entity) 의
    실제 경로를 찾는다. type 디렉토리 (document/) 위에 평탄하게 있으므로
    바로 매칭."""
    for path in _iter_entity_files(entity_root):
        parsed = _read_frontmatter(path)
        if not parsed:
            continue
        fm, _ = parsed
        if fm.get("entity_id") == deleted_doc_id:
            return path
    return None


def backup_upload_file(
    physical_path:  Path,
    upload_dir:     Path,
) -> Path:
    """``uploads/{file}`` 를 ``uploads/.deleted/{ts}_{file}`` 로 이동.

    설계 §5: 파일은 N 일 동안 복구 가능한 backup 으로 보존. 실제
    cleanup 은 별도 운영 도구의 일 (Phase C scope 밖).

    .deleted 디렉토리가 없으면 생성. 이미 같은 이름이 있으면 (재시도
    등) ``{ts}_{idx}_{file}`` 으로 충돌 회피.
    """
    deleted_dir = upload_dir / ".deleted"
    deleted_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = deleted_dir / f"{ts}_{physical_path.name}"
    idx  = 1
    while dest.exists():
        dest = deleted_dir / f"{ts}_{idx}_{physical_path.name}"
        idx += 1
    shutil.move(str(physical_path), str(dest))
    return dest


def cascade_delete_upload(
    physical_filename: str,
    *,
    wiki_generator,         # core.wiki_generator.WikiGenerator
    vector_store,           # core.vector_store.VectorStore (delete_by_source 만 필요)
    upload_dir:        Path,
    user_role:         str = "admin",
) -> Dict[str, Any]:
    """업로드 파일 하나의 전 cascade. 디자인 §5 의 step 1~5 + audit.

    Returns audit-friendly summary dict:
      {
        "physical_filename":     str,
        "original_filename":     str,
        "doc_entity_id":         str,
        "doc_entity_deleted":    bool,
        "orphan_entities_deleted": int,
        "vector_deleted":        bool,
        "file_backup":           str  (relative path under upload_dir),
        "counts":                {cascade_remove_doc_from_sources 의 결과},
      }

    Raises:
      FileNotFoundError — 물리 파일이 uploads/ 에 없을 때.
    """
    physical_path = Path(upload_dir) / physical_filename
    if not physical_path.is_file():
        raise FileNotFoundError(
            f"upload not found: {physical_path}"
        )

    original_filename = strip_uuid_prefix(physical_filename)
    doc_name          = os.path.splitext(original_filename)[0]
    doc_entity_id     = wiki_generator._generate_entity_id(doc_name, "document")
    entity_root       = Path(wiki_generator.entity_path)

    # Step 1+2 — 모든 entity 의 sources 에서 이 doc 제거
    counts = cascade_remove_doc_from_sources(doc_entity_id, entity_root)

    # Step 3 — orphan sweep (이 doc 만으로 생긴 + 다른 누구도 안 가리키는
    #          extracted entities). doc entity 본체는 제외.
    orphan_paths = find_orphan_entities(
        original_filename, doc_entity_id, entity_root,
    )
    for p in orphan_paths:
        try:
            p.unlink()
        except OSError as e:
            print(f"[CASCADE] orphan unlink fail {p}: {e}")

    # Step 4 — doc entity 본체 삭제
    doc_path = find_doc_entity_path(doc_entity_id, entity_root)
    doc_deleted = False
    if doc_path is not None:
        try:
            doc_path.unlink()
            doc_deleted = True
        except OSError as e:
            print(f"[CASCADE] doc entity unlink fail {doc_path}: {e}")

    # Step 5 — vector chunks
    vec_deleted = False
    try:
        vec_deleted = bool(vector_store.delete_by_source(original_filename))
    except Exception as e:
        print(f"[CASCADE] vector delete fail {original_filename}: {e}")

    # Step 6 — 물리 파일 → .deleted/ 백업
    backup_path = backup_upload_file(physical_path, Path(upload_dir))

    # Index refresh — entity 파일들이 사라졌으므로 wiki_generator 의
    # in-memory entity_id_index 가 stale. refresh 가 가능한 instance 면 호출.
    try:
        if hasattr(wiki_generator, "refresh_entity_map"):
            wiki_generator.refresh_entity_map()
    except Exception as e:
        print(f"[CASCADE] entity index refresh skipped: {e}")

    return {
        "physical_filename":       physical_filename,
        "original_filename":       original_filename,
        "doc_entity_id":           doc_entity_id,
        "doc_entity_deleted":      doc_deleted,
        "orphan_entities_deleted": len(orphan_paths),
        "vector_deleted":          vec_deleted,
        "file_backup":             str(backup_path.relative_to(Path(upload_dir))),
        "counts":                  counts,
        "user_role":               user_role,
    }
