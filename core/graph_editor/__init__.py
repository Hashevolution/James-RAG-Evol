"""``core.graph_editor`` — Knowledge Cascade Phase E (graph editor backend).

``docs/design/v0.3-knowledge-cascade.md`` §7 — Phase E.

``/admin/graph`` 의 admin 이 edge 별 sources 를 직접 수정할 수 있게
하는 3 endpoint 의 코어 로직. UI 가 클릭한 edge 의 source list /
weight / role 을 받아 양방향 entity 파일의 frontmatter relation 의
``sources`` 배열을 갱신한다.

Phase B (PR #269) 가 ingestion 시점에 ``sources`` 를 stamp 하고
Phase C (PR #270) 가 cascade 가 manual source 를 보존하도록 만들었기
때문에, Phase E 의 manual source write 는 자연스럽게 cascade-안전:
admin 이 추가한 ``role=manual`` source 는 doc 파일 삭제 시에도
유지된다.

Trust model (§7):

- admin 만 호출 가능 (server endpoint 에서 admin.data feature gate +
  ``JAMES_GRAPH_EDIT=1`` env flag opt-in).
- 모든 write 는 양쪽 (forward + inverse) entity 파일에 동시 반영.
- audit log 에 before+after sources 배열 차이 기록.
- 두 admin 의 동시 PUT 은 last-writer-wins. POST (append) 는 commutative.

Originally a single 20 KB module; split in Stage C.5 (2026-05-24)
into a 3-module package so every file respects CLAUDE.md rule #5
(< 20 KB). External callers — ``server_llmwiki.py`` and the
``test_phase_e_graph_editor`` / ``test_event_admin_endpoint`` test
files — keep their existing import paths.

Node-level attribute editor (PR-O6) lives in
``core/graph_node_editor.py`` so this module stays focused on
edge-level mutations. The two modules share file I/O helpers via
direct import.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from ._helpers import (
    _FM_SPLIT_RE,
    _find_relation_index,
    _inverse_type,
    _label_for_type,
    _load_entity_by_id,
    _read_entity,
    _validate_sources,
    _write_entity,
)
from ._writes import (
    append_relation_source,
    delete_relation,
    replace_relation_sources,
)


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


__all__ = [
    # write API
    "replace_relation_sources",
    "append_relation_source",
    "delete_relation",
    # read API
    "read_relation",
    # env flag
    "graph_edit_enabled",
    # helpers (kept exported — graph_node_editor + tests import them directly)
    "_FM_SPLIT_RE",
    "_read_entity",
    "_write_entity",
    "_load_entity_by_id",
    "_inverse_type",
    "_label_for_type",
    "_find_relation_index",
    "_validate_sources",
]
