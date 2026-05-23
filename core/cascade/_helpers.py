"""Cascade — module-level helpers shared by Phase C (delete) and Phase D (modify).

Holds the uuid-prefix regex, the frontmatter split regex, the
``strip_uuid_prefix`` filename helper, and the three ``_read_/
_write_frontmatter`` + ``_iter_entity_files`` primitives used by every
sweep function in ``_delete.py`` and ``_modify.py``.

Split out of the monolithic ``core/cascade.py`` in Stage C.2
(2026-05-24) so every file respects CLAUDE.md rule #5 (< 20 KB).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml


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


__all__ = [
    "_UUID_PREFIX_RE",
    "_FM_SPLIT_RE",
    "strip_uuid_prefix",
    "_read_frontmatter",
    "_write_frontmatter",
    "_iter_entity_files",
]
