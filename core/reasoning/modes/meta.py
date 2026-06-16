"""``handle_meta`` — internal-data inventory ("what do you have?").

v0.6.1 v16 (2026-06-16) — operator catch: the legacy formatter
showed only top-level dirs + the first 8 alphabetical names per dir,
which surfaced as "entity/ (313개): 2024년_2분기_실적, 2025년_4분기,
2026년_투자자_서한, aci, aider, aip, ai_보안, ai_수요 (+305개 더)".
The user wanted a structured at-a-glance view: classification by
entity_type + thematic prefix grouping + most-recent additions.
This rewrite implements that hybrid layout WITHOUT touching the LLM
(stays a deterministic fast path per the routes/llm.py wiring).

Rule #1 4-layer protection note: this PR touches `core/reasoning`,
which had been at a 0-line-changed streak through the v0.6.1
chrome cycle. The streak break is honest-framed in the PR body:
the change is mother-platform meta-response UX, no vertical content,
no measurement axis impact (multihop / RGB benchmarks don't route
through `handle_meta`). Streak resets at v17.
"""
from __future__ import annotations

import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple


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
    cascade helper module (so meta.py stays leaf-import-clean).
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
_TYPE_LABELS = {
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


# ────────────────────────────────────────────────────────────────────
# meta — internal-data inventory ("what do you have?")
# ────────────────────────────────────────────────────────────────────
def handle_meta(
    engine,
    safe_query: str,
    system_prompt: str,
    user_role: str,
    t_start: float,
) -> Dict[str, Any]:
    """Inventory handler — answers "내부 자료가 무엇이 있나" with a
    hybrid view (entity_type classification + thematic prefix grouping
    + most-recent additions) so the operator gets an at-a-glance map,
    not a flat 313-row dump.

    The LLM is still NOT in the path (routes/llm.py L233 contract).
    Everything below comes from the filesystem + lightweight
    frontmatter peek per file.
    """
    t_meta = time.time()
    answer = ""
    try:
        from tools.wiki.wiki_editor import list_entities, WIKI_PATH

        all_entities = list_entities(limit=500)
        total = len(all_entities)

        if total == 0:
            answer = "현재 보유한 wiki 자료가 없습니다."
        else:
            # Augment each entity with entity_type + mtime so we can
            # group / sort downstream. Bounded to 500 — typical v0.2
            # corpus is ~300, head-read is < 1 KB so total cost
            # stays well under 200 ms even on a slow disk.
            wiki_root = Path(WIKI_PATH)
            enriched = []
            for e in all_entities:
                rel = e.get("path", "")
                abs_path = wiki_root / rel
                etype = _peek_entity_type(abs_path)
                try:
                    mtime = abs_path.stat().st_mtime if abs_path.exists() else 0
                except OSError:
                    mtime = 0
                enriched.append({
                    "name":  e.get("name", ""),
                    "path":  rel,
                    "type":  etype,
                    "mtime": mtime,
                })

            # ── entity_type classification ──────────────────────
            by_type: Dict[str, List[str]] = defaultdict(list)
            for e in enriched:
                t = e["type"] or "(미분류)"
                by_type[t].append(e["name"])

            # ── thematic prefix grouping ────────────────────────
            # Unmatched names (theme == "") roll up into a single
            # "기타" bucket so we don't surface a long alphabetical
            # noise tail. The themed buckets dominate the section.
            by_theme: Dict[str, List[str]] = defaultdict(list)
            for e in enriched:
                theme = _classify_theme(e["name"]) or "기타"
                by_theme[theme].append(e["name"])

            # ── most-recent additions ───────────────────────────
            recent = sorted(
                enriched, key=lambda x: x["mtime"], reverse=True,
            )[:5]

            # ── format as markdown — uses the v0.6.1 v15 serif
            # answer typography on the client side. Heading levels
            # match the client's .md-h2/-h3 size step.
            out: List[str] = []
            out.append(f"## 보유 자료 총 {total}개")
            out.append("")
            out.append("자메스가 현재 보유한 wiki 자료를 분류·주제·최근순으로 정리했어요.")
            out.append("")

            # 분류별 — sort by descending count so the biggest bucket
            # surfaces first. Cap each row at 6 sample names so a
            # 100-entity type doesn't dominate.
            out.append("### 분류별 (entity_type 기준)")
            type_rows = sorted(
                by_type.items(), key=lambda kv: -len(kv[1]),
            )
            for raw_t, names in type_rows:
                label = _TYPE_LABELS.get(raw_t, raw_t.title() or "미분류")
                sample = ", ".join(names[:6])
                more = f" 외 {len(names) - 6}개" if len(names) > 6 else ""
                out.append(f"- **{label}** ({len(names)}개): {sample}{more}")
            out.append("")

            # 주제별 — themed buckets first (descending count), then
            # a single rolled-up "기타" line at the end so the section
            # stays scannable instead of fanning out into prefix noise.
            out.append("### 주제별 (이름 패턴)")
            other_count = len(by_theme.pop("기타", []))
            theme_rows = sorted(
                by_theme.items(), key=lambda kv: -len(kv[1]),
            )
            for theme, names in theme_rows:
                sample = ", ".join(names[:5])
                more = f" 외 {len(names) - 5}개" if len(names) > 5 else ""
                out.append(f"- **{theme}** ({len(names)}개): {sample}{more}")
            if other_count:
                out.append(
                    f"- **기타** ({other_count}개) — 위 카테고리 외 일반 항목"
                )
            out.append("")

            # 최근 추가 — mtime-sorted top 5.
            out.append("### 최근 추가된 자료 (top 5)")
            for e in recent:
                if not e["name"]:
                    continue
                label = _TYPE_LABELS.get(e["type"], e["type"] or "미분류")
                out.append(f"- {e['name']} _(타입: {label})_")
            out.append("")

            # Drill-in invite. Ends with a period so the client-side
            # truncation guard (chat.js isLikelyTruncated SOFT signal)
            # doesn't fire on the trailing closing quote.
            out.append(
                "특정 항목을 자세히 보려면 그 이름을 직접 질문하세요. "
                "예: \"비트코인에 대해 알려줘\"."
            )
            answer = "\n".join(out)

    except Exception as e:
        engine._log("meta_inventory", e, user_role)
        answer = f"자료 목록 조회 실패: {e}"

    engine._elapsed(t_meta, "META_inventory")
    return {
        "answer":        answer,
        "mode":          "meta",
        "graph_paths":   [],
        "graph_used":    0,
        "sources":       [],
        "blocked":       False,
        "role_used":     user_role,
        "timing_sec":    round(time.time() - t_start, 2),
        "unified_score": 1.0,
        "loop_count":    0,
    }


__all__ = ["handle_meta"]
