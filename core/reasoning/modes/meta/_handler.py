"""``handle_meta`` — internal-data inventory ("what do you have?")
orchestrator.

The dispatcher reads the operator's query, decides whether to render
the deterministic overview or one of the focused detail views
(type / theme / recent / LLM narrative), and returns the standard
reasoning-engine row dict.

Module-size split (CLAUDE.md rule #5): originally the bottom half of
the 31.6 KB ``modes/meta.py``. Now lives under
``modes/meta/_handler.py``; parsing helpers, degree map, and
renderers live in sibling modules.
"""
from __future__ import annotations

import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

from core.reasoning.modes.meta._degree import _build_degree_map
from core.reasoning.modes.meta._parse import (
    _TYPE_LABELS,
    _classify_theme,
    _parse_meta_filter,
    _peek_entity_type,
)
from core.reasoning.modes.meta._render import (
    _render_llm_narrative,
    _render_recent_detail,
    _render_theme_detail,
    _render_type_detail,
)


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

            # v0.6.1 v17 (2026-06-16) — meta follow-up routing. If
            # the query carries a type / theme / recent filter, render
            # the focused detail view instead of the generic overview.
            # The overview path stays the default for first-shot
            # queries like "내부 자료가 무엇이 있나".
            meta_filter = _parse_meta_filter(safe_query)
            if meta_filter["kind"] == "type":
                answer = _render_type_detail(enriched, meta_filter["raw"])
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
            if meta_filter["kind"] == "theme":
                answer = _render_theme_detail(enriched, meta_filter["label"])
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
            if meta_filter["kind"] == "recent":
                answer = _render_recent_detail(enriched)
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

            # ── most-recent additions ───────────────────────────
            recent = sorted(
                enriched, key=lambda x: x["mtime"], reverse=True,
            )[:5]

            # ── graph-degree top-K (option C) ───────────────────
            # Computed for overview + summary paths so the most-
            # connected hub entities surface alongside the type and
            # theme breakdowns. Skipped on focused detail views to
            # keep their response narrow.
            degree_map = _build_degree_map(enriched, wiki_root)
            top_degree = sorted(
                degree_map.items(), key=lambda kv: -kv[1],
            )[:10]
            # Drop trailing zeros — if the corpus has no recorded
            # relations at all, don't render an empty section.
            top_degree = [(n, d) for n, d in top_degree if d > 0]

            # ── option D: LLM narrative variant ─────────────────
            if meta_filter["kind"] == "summary":
                answer = _render_llm_narrative(
                    engine,
                    total=total,
                    by_type=by_type,
                    by_theme=by_theme,
                    recent=recent,
                    top_degree=top_degree,
                )
                engine._elapsed(t_meta, "META_inventory")
                return {
                    "answer":        answer,
                    "mode":          "meta",
                    "graph_paths":   [],
                    "graph_used":    len(top_degree),
                    "sources":       [],
                    "blocked":       False,
                    "role_used":     user_role,
                    "timing_sec":    round(time.time() - t_start, 2),
                    "unified_score": 1.0,
                    "loop_count":    0,
                }

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

            # 핵심 entity — graph degree top-K (option C).
            # Skipped when the corpus has no edges so the section
            # doesn't render an empty placeholder.
            if top_degree:
                out.append("### 핵심 entity (연결 수 top 10)")
                out.append("_(다른 항목과 가장 많이 연결된 hub)_")
                out.append("")
                for name, deg in top_degree:
                    # find the type label so the row reads as
                    # "PALANTIR (27 연결, 조직)" — operator instantly
                    # sees both the importance and the category.
                    etype = next(
                        (e["type"] for e in enriched if e["name"] == name),
                        "",
                    )
                    label = _TYPE_LABELS.get(etype, etype or "미분류")
                    out.append(f"- **{name}** ({deg} 연결, {label})")
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
