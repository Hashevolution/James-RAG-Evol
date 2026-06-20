"""meta-mode graph-degree top-K — v0.6.1 v18 option C.

Out-degree = count of ``- target:`` lines in the entity's frontmatter
relations block. In-degree = times this entity's name OR id appears
as another entity's target / target_id. Strong proxy for "hub
entity" without spinning up the full GraphEngine.

Module-size split (CLAUDE.md rule #5): originally part of the 31.6 KB
``modes/meta.py``. Lifted out to keep ``_handler.py`` slim.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple


# v0.6.1 v18 (2026-06-16) — option C: graph-degree top-K.
# Out-degree = count of `- target:` lines in the entity's frontmatter
# relations block. Cheap (regex scan, no yaml parse), strong proxy
# for "hub entity" without spinning up the full GraphEngine. Reads
# the same files we already read for entity_type peek so cost stays
# under 200 ms even at 500 entities.
_REL_TARGET_RE   = re.compile(r"^\s*target:\s*([^\r\n#]+)", re.MULTILINE)
_REL_TARGETID_RE = re.compile(r"^\s*target_id:\s*([^\r\n#]+)", re.MULTILINE)
_ENTITY_ID_RE    = re.compile(r"^\s*id:\s*([^\r\n#]+)", re.MULTILINE)


def _norm_key(s: str) -> str:
    """Aggressive normalize for name matching across casing / hyphen /
    space / dot variants. "PALANTIR TECHNOLOGIES" → "palantir_technologies".
    """
    s = (s or "").lower().strip().strip("\"'").strip()
    for ch in (" ", "-", "."):
        s = s.replace(ch, "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")


def _peek_fm_section(path: Path) -> str:
    """Return the frontmatter text block (between the two '---'
    delimiters) for cheap regex inspection. Capped at 12 KB —
    frontmatter that overflows is a structural outlier."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            head = fh.read(12288)
    except OSError:
        return ""
    if not head.startswith("---"):
        return head
    end = head.find("---", 3)
    return head[3:end] if end > 0 else head


def _build_degree_map(
    enriched: List[Dict[str, Any]], wiki_root: Path,
) -> Dict[str, int]:
    """Compute hybrid degree = out + in for each entity name.
    out = `- target:` lines in own frontmatter.
    in  = times this entity's name OR id appears as another entity's
          target / target_id. Two-key match — by normalized name and
          by entity_id — so loose form ("PALANTIR TECHNOLOGIES") still
          counts even when wiki file slugs are aggressive
          ("palantir_technologies").
    """
    # First pass — collect each entity's own id + out-targets.
    name_to_id: Dict[str, str] = {}     # canonical name → entity_id
    id_to_name: Dict[str, str] = {}     # entity_id → canonical name
    name_key_to_canonical: Dict[str, str] = {}  # normalized name key → name
    out_targets: Dict[str, List[Tuple[str, str]]] = {}  # name → [(target_name, target_id)]

    for e in enriched:
        name = e.get("name") or ""
        if not name:
            continue
        fm_text = _peek_fm_section(wiki_root / e["path"])
        # own id
        m_id = _ENTITY_ID_RE.search(fm_text)
        eid = m_id.group(1).strip().strip("\"'").strip() if m_id else ""
        if eid:
            name_to_id[name] = eid
            id_to_name[eid] = name
        name_key_to_canonical[_norm_key(name)] = name
        # targets
        target_names = [m.group(1).strip().strip("\"'").strip()
                        for m in _REL_TARGET_RE.finditer(fm_text)]
        target_ids = [m.group(1).strip().strip("\"'").strip()
                      for m in _REL_TARGETID_RE.finditer(fm_text)]
        # pair them positionally — yaml lists usually keep target +
        # target_id co-located; if a row only has one, the other side
        # is empty string.
        pairs: List[Tuple[str, str]] = []
        for i in range(max(len(target_names), len(target_ids))):
            tn = target_names[i] if i < len(target_names) else ""
            ti = target_ids[i]   if i < len(target_ids)   else ""
            pairs.append((tn, ti))
        out_targets[name] = pairs

    # Second pass — in-degree by id-first, name-key-second.
    in_count: Dict[str, int] = defaultdict(int)
    for src, pairs in out_targets.items():
        for tn, ti in pairs:
            canonical = ""
            if ti and ti in id_to_name:
                canonical = id_to_name[ti]
            elif tn:
                canonical = name_key_to_canonical.get(_norm_key(tn), "")
            if canonical and canonical != src:
                in_count[canonical] += 1

    return {
        e["name"]: len(out_targets.get(e["name"], [])) + in_count.get(e["name"], 0)
        for e in enriched if e.get("name")
    }


__all__ = [
    "_REL_TARGET_RE",
    "_REL_TARGETID_RE",
    "_ENTITY_ID_RE",
    "_norm_key",
    "_peek_fm_section",
    "_build_degree_map",
]
