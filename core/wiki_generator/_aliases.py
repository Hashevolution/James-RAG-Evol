"""Wiki generator — alias expansion + name validation constants.

Module-level regex constants, allowed extraction types, and the
synonyms loader/expander. Split out of the monolithic
``core/wiki_generator.py`` in Stage C.1 (2026-05-24) so the package
respects CLAUDE.md rule #5 (< 20 KB per file).

External callers depend on:

- ``_ALLOWED_EXTRACT_TYPES`` — ``tests/test_event_ingest_emit.py:342``
- ``_expand_alias_candidates`` — ``scripts/migrate_aliases.py:33``

Both are re-exported from ``core.wiki_generator`` so existing import
paths keep working byte-identical.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

import yaml


_SAFE_ENTITY_NAME_RE = re.compile(r'^[A-Za-z0-9가-힣\s\-_,()&·\.]{2,80}$')
_ALLOWED_EXTRACT_TYPES = frozenset(("person", "org", "concept", "event"))
_ONTOLOGY_LABELS_KO = "공부, 연구, 가르침, 소속, 근무, 분류, 구성, 관련, 생산, 산업, 분야, 설립됨"

# 괄호 패턴 — 반각/전각 모두 처리. e.g. "RAG (검색 증강 생성)" / "RAG（검색 증강 생성）"
_PAREN_ALIAS_RE = re.compile(r'^(.+?)\s*[\(（](.+?)[\)）]\s*$')

# wiki/synonyms.yaml 한 번 로드해서 캐시. (Issue #3)
# {surface_form_lower: [other_form1, other_form2, ...]} 양방향.
_SYNONYM_INDEX: Dict[str, List[str]] | None = None


def _load_synonyms() -> Dict[str, List[str]]:
    """wiki/synonyms.yaml에서 synonym 그룹 로드 → 양방향 lookup index 빌드.

    yaml 형식::

      - canonical: 비트코인
        aliases: [BTC, Bitcoin]

    반환: ``{lowercase_form → [같은 그룹의 다른 form들]}``.

    Late-binds ``WIKI_DIR`` from ``core.wiki_generator`` so tests that
    do ``import core.wiki_generator as wg_mod; wg_mod.WIKI_DIR = tmp``
    see the override. Lazy import avoids circular dependency at
    package-init time.
    """
    global _SYNONYM_INDEX
    if _SYNONYM_INDEX is not None:
        return _SYNONYM_INDEX

    from core.wiki_generator import WIKI_DIR

    index: Dict[str, List[str]] = {}
    syn_path = Path(WIKI_DIR) / "synonyms.yaml"
    if not syn_path.exists():
        _SYNONYM_INDEX = index
        return index

    try:
        groups = yaml.safe_load(syn_path.read_text(encoding="utf-8")) or []
        if not isinstance(groups, list):
            _SYNONYM_INDEX = index
            return index
        for g in groups:
            if not isinstance(g, dict):
                continue
            canonical = (g.get("canonical") or "").strip()
            aliases   = g.get("aliases") or []
            if not canonical or not isinstance(aliases, list):
                continue
            forms = [canonical] + [str(a).strip() for a in aliases if a]
            forms = [f for f in forms if f]
            for f in forms:
                others = [x for x in forms if x != f]
                if others:
                    index.setdefault(f.lower(), []).extend(others)
    except Exception as e:
        print(f"[SYNONYMS] load failed: {e}")

    _SYNONYM_INDEX = index
    return index


def _expand_alias_candidates(name: str) -> List[str]:
    """이름에서 alias 후보를 자동 추출.

    - 괄호 패턴 ``"X (Y)"`` → ``["X (Y)", "X", "Y"]``
    - synonym 매핑 (wiki/synonyms.yaml) → 같은 그룹의 다른 form 모두 추가
    - 그 외에는 ``[name]`` 만 반환

    LLM이 풍부한 이름(``"RAG (검색 증강 생성)"``)으로 entity를 만들고,
    질의 시점엔 짧은 형태(``"RAG"``)로 entity를 추출하기 때문에 매칭 갭을
    메우려면 양쪽 형태를 모두 alias로 등록해야 한다.
    """
    if not isinstance(name, str):
        return []
    name = name.strip()
    if not name:
        return []
    out: List[str] = [name]
    m = _PAREN_ALIAS_RE.match(name)
    if m:
        for part in (m.group(1).strip(), m.group(2).strip()):
            if part and part not in out and len(part) >= 2:
                out.append(part)

    # synonym 매핑 (Issue #3)
    syn_index = _load_synonyms()
    # name 본체와 (괄호 분리된) 짧은 form 모두 lookup
    for candidate in list(out):
        for other in syn_index.get(candidate.lower(), []):
            if other not in out:
                out.append(other)

    return out


__all__ = [
    "_SAFE_ENTITY_NAME_RE",
    "_ALLOWED_EXTRACT_TYPES",
    "_ONTOLOGY_LABELS_KO",
    "_PAREN_ALIAS_RE",
    "_load_synonyms",
    "_expand_alias_candidates",
]
