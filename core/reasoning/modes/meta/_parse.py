"""meta-mode input parsing — theme classifier, type label, filter tokens.

Pure helpers, no I/O outside ``_peek_entity_type`` (which reads the
first 1 KB of a file head to extract its frontmatter ``entity_type``).
Everything here is package-private (``_``-prefixed); only ``handle_meta``
in ``_handler.py`` consumes these symbols.

Module-size split (CLAUDE.md rule #5): originally part of the 31.6 KB
``modes/meta.py``. Now lives under ``modes/meta/_parse.py``; the public
surface (``handle_meta``) is preserved via the package facade
(``modes/meta/__init__.py``).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple


# Themed prefix patterns — try in order, first match wins. Each
# pattern captures the canonical theme label. Tuned for the typical
# JAMES dogfood corpus (year-stamped reports, ai_*, web3 / blockchain,
# financial terms, etc.) but designed so unmatched names fall through
# to the generic alphabetical fallback.
_THEME_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("연도별 보고서·실적",  re.compile(r"^(19|20)\d{2}년?[_\-]")),
    ("AI · 머신러닝",        re.compile(r"^(ai|llm|gpt|ml|mlops|nlp|agent)[_\-]", re.IGNORECASE)),
    ("블록체인 · Web3",      re.compile(r"^(btc|eth|sol|web3|defi|dao|nft|blockchain|crypto)", re.IGNORECASE)),
    ("재무 · 시장",          re.compile(r"^(revenue|earnings|guidance|매출|실적|투자|시장|valuation)", re.IGNORECASE)),
    ("보안 · 정책",          re.compile(r"^(security|보안|정책|policy|compliance|reg|risk)", re.IGNORECASE)),
    ("연구 · 논문",          re.compile(r"^(paper|preprint|arxiv|논문|연구|study)", re.IGNORECASE)),
    ("웹 · 외부 자료",       re.compile(r"^(web|external|news|뉴스)[_\-]", re.IGNORECASE)),
]


def _classify_theme(name: str) -> str:
    """Returns a theme label OR empty string when no theme matches.
    Callers tag unmatched names as "기타" so the section stays compact
    instead of exploding into per-prefix alphabetical buckets.
    """
    for label, pat in _THEME_PATTERNS:
        if pat.search(name):
            return label
    return ""


def _peek_entity_type(path: Path) -> str:
    """Return frontmatter entity_type without depending on the larger
    cascade helper module (so meta stays leaf-import-clean).
    Reads at most the first 1 KB of the file — frontmatter always
    appears at the head of the document, so we never need more.
    """
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            head = fh.read(1024)
    except OSError:
        return ""
    # Quick regex on the head — avoids yaml.safe_load overhead for the
    # 300 + entity loop. Frontmatter uses `entity_type: <value>` on
    # a single line.
    m = re.search(r"^\s*entity_type:\s*([^\r\n#]+)", head, re.MULTILINE)
    if not m:
        return ""
    raw = m.group(1).strip().strip("\"'").strip()
    return raw.lower() or ""


# Human-readable Korean labels for the entity_type axis. Anything
# else passes through with its raw value (TitleCase'd) so unknown
# types still surface meaningfully.
_TYPE_LABELS: Dict[str, str] = {
    "person":       "인물",
    "organization": "조직",
    "org":          "조직",
    "company":      "기업",
    "concept":      "개념",
    "event":        "이벤트",
    "location":     "장소",
    "place":        "장소",
    "document":     "문서",
    "report":       "보고서",
    "asset":        "자산",
    "product":      "제품",
    "tech":         "기술",
    "topic":        "주제",
}


# v0.6.1 v17 (2026-06-16) — query filter taxonomy for meta follow-ups.
# Operator catch: the v16 hybrid overview produces "분류별: 개념(135),
# 조직(86), ..."; the natural follow-up is "개념 자료에는 뭐가 있어?".
# These tables let _parse_meta_filter map a Korean keyword (in the
# raw query) back to either a specific entity_type or a specific
# theme bucket so handle_meta can render a focused detail view.
#
# Each tuple = (keyword token, raw entity_type / theme label).
# Order matters: the first hit wins, so more specific terms ("재무
# 보고서" → "재무 · 시장") should appear before less specific ones
# ("보고서" → "report") in their respective list.
_TYPE_FILTER_TOKENS: List[Tuple[str, str]] = [
    ("인물",       "person"),
    ("사람",       "person"),
    ("조직",       "organization"),
    ("기업",       "company"),
    ("회사",       "company"),
    ("개념",       "concept"),
    ("이벤트",     "event"),
    ("사건",       "event"),
    ("장소",       "location"),
    ("자산",       "asset"),
    ("문서",       "document"),
    ("보고서",     "report"),
    ("미분류",     ""),
    # English fallback so list/show queries land cleanly.
    ("person",       "person"),
    ("organization", "organization"),
    ("company",      "company"),
    ("concept",      "concept"),
    ("event",        "event"),
    ("location",     "location"),
    ("asset",        "asset"),
    ("document",     "document"),
    ("report",       "report"),
]

_THEME_FILTER_TOKENS: List[Tuple[str, str]] = [
    ("연도별",       "연도별 보고서·실적"),
    ("실적",         "연도별 보고서·실적"),
    ("연도",         "연도별 보고서·실적"),
    ("ai",           "AI · 머신러닝"),
    ("에이아이",     "AI · 머신러닝"),
    ("머신러닝",     "AI · 머신러닝"),
    ("llm",          "AI · 머신러닝"),
    ("블록체인",     "블록체인 · Web3"),
    ("크립토",       "블록체인 · Web3"),
    ("crypto",       "블록체인 · Web3"),
    ("web3",         "블록체인 · Web3"),
    ("재무",         "재무 · 시장"),
    ("시장",         "재무 · 시장"),
    ("매출",         "재무 · 시장"),
    ("보안",         "보안 · 정책"),
    ("정책",         "보안 · 정책"),
    ("security",     "보안 · 정책"),
    ("연구",         "연구 · 논문"),
    ("논문",         "연구 · 논문"),
    ("paper",        "연구 · 논문"),
    ("웹",           "웹 · 외부 자료"),
    ("외부",         "웹 · 외부 자료"),
    ("뉴스",         "웹 · 외부 자료"),
]

_RECENT_TOKENS: Tuple[str, ...] = (
    "최근", "새로", "새로운", "최신", "recent", "latest", "new",
    "방금", "오늘", "어제",
)

# v0.6.1 v18 (2026-06-16) — option D narrative trigger. When the
# operator asks "요약해줘" / "정리해줘" / "전체적으로" we route to a
# LLM-narrative variant of the overview. Default overview still takes
# the fast deterministic path.
_NARRATIVE_TOKENS: Tuple[str, ...] = (
    "요약", "정리", "전체적", "총평", "요점", "정리해", "summary",
    "한 줄로", "한줄로", "한 마디", "정리해줘", "보고서로",
)


def _parse_meta_filter(query: str) -> Dict[str, str]:
    """Decide whether the meta query is an OVERVIEW request or a
    follow-up asking for a specific slice (type / theme / recent /
    summary).

    Returns: {"kind": "overview"} | {"kind": "type", "raw": <etype>}
                                  | {"kind": "theme", "label": <theme>}
                                  | {"kind": "recent"}
                                  | {"kind": "summary"}
    """
    q = (query or "").lower().strip()
    if not q:
        return {"kind": "overview"}
    # v0.6.1 v18 (2026-06-16) — narrative trigger FIRST so a request
    # like "AI 자료 요약해줘" goes to the LLM narrative path (which
    # internally still uses the AI filter to scope its prompt context)
    # rather than the deterministic type/theme detail view.
    if any(tok in q for tok in _NARRATIVE_TOKENS):
        return {"kind": "summary"}
    # v0.6.1 v17 (2026-06-16) — theme tokens checked next so a
    # phrase like "재무 보고서" lands on the "재무 · 시장" theme
    # rather than the generic "report" type. Both signals are
    # legitimate; theme is more specific in those compound cases.
    for token, theme in _THEME_FILTER_TOKENS:
        if token in q:
            return {"kind": "theme", "label": theme}
    # Specific-type request — Korean / English single-word tokens.
    for token, etype in _TYPE_FILTER_TOKENS:
        if token in q:
            return {"kind": "type", "raw": etype}
    # Recent request.
    if any(tok in q for tok in _RECENT_TOKENS):
        return {"kind": "recent"}
    return {"kind": "overview"}


__all__ = [
    "_THEME_PATTERNS",
    "_classify_theme",
    "_peek_entity_type",
    "_TYPE_LABELS",
    "_TYPE_FILTER_TOKENS",
    "_THEME_FILTER_TOKENS",
    "_RECENT_TOKENS",
    "_NARRATIVE_TOKENS",
    "_parse_meta_filter",
]
