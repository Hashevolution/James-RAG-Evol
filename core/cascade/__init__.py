"""``core.cascade`` — Knowledge Cascade Phase C (delete) + Phase D (modify).

Originally a single 24 KB module; split in Stage C.2 (2026-05-24) into
a small package so every file respects CLAUDE.md rule #5 (< 20 KB).
External callers — ``server_llmwiki.py`` and the
``test_phase_{c,d,e}_*`` test files — keep their existing import paths
because every public name is re-exported here.

Design references:

- ``docs/design/v0.3-knowledge-cascade.md`` §5 — Phase C (delete).
- ``docs/design/v0.3-knowledge-cascade.md`` §6 — Phase D (modify).

Layout:

- ``_helpers.py`` — uuid-prefix regex, frontmatter read/write, entity-
  file iteration. Shared by both phases.
- ``_delete.py`` — Phase C: ``cascade_remove_doc_from_sources``,
  ``find_orphan_entities``, ``find_doc_entity_path``,
  ``backup_upload_file``, top-level ``cascade_delete_upload``.
- ``_modify.py`` — Phase D: ``load_extraction_sidecar``,
  ``diff_triples``, top-level ``cascade_modify_doc``.

The split is purely textual — no semantic change. Same function
signatures, same return shapes.
"""
from __future__ import annotations

from ._delete import (
    backup_upload_file,
    cascade_delete_upload,
    cascade_remove_doc_from_sources,
    find_doc_entity_path,
    find_orphan_entities,
)
from ._helpers import (
    _FM_SPLIT_RE,
    _UUID_PREFIX_RE,
    _iter_entity_files,
    _read_frontmatter,
    _write_frontmatter,
    strip_uuid_prefix,
)
from ._modify import (
    cascade_modify_doc,
    diff_triples,
    load_extraction_sidecar,
)


__all__ = [
    # Phase C — delete
    "backup_upload_file",
    "cascade_delete_upload",
    "cascade_remove_doc_from_sources",
    "find_doc_entity_path",
    "find_orphan_entities",
    # Phase D — modify
    "cascade_modify_doc",
    "diff_triples",
    "load_extraction_sidecar",
    # helpers (kept exported for tests / scripts that import them directly)
    "strip_uuid_prefix",
    "_read_frontmatter",
    "_write_frontmatter",
    "_iter_entity_files",
    "_UUID_PREFIX_RE",
    "_FM_SPLIT_RE",
]
