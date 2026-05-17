"""``handle_meta`` — internal-data inventory ("what do you have?").

Extracted from the monolithic ``core/reasoning/modes.py`` in the
v0.3.x rule-#5 split. Body is byte-identical to the pre-split version.
"""
from __future__ import annotations

import time
from typing import Any, Dict


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
    """Inventory query handler — answers "what data do you have?" by
    listing wiki entity files directly via tools/wiki/list_entities.

    Pre-this-mode behavior: such queries fell into `retrieval` and
    returned hallucinated answers because the wiki file *list* lives in
    no vector chunk. Now we read the filesystem directly and format a
    grouped summary (top-level dirs first, then sample names).

    Output is intentionally compact (counts + sample, not full list) —
    a 200-entity wiki would otherwise blow the answer length even with
    response_style=brief. The user can drill in with a follow-up
    retrieval query (e.g. "person 카테고리에 어떤 인물 있어?").
    """
    t_meta = time.time()
    answer = ""
    try:
        from tools.wiki.wiki_editor import list_entities

        # Pull a generous slice — the formatter below dedupes by top-
        # level directory anyway. 500 covers any realistic v0.2 corpus.
        all_entities = list_entities(limit=500)
        total = len(all_entities)

        if total == 0:
            answer = "현재 보유한 wiki 자료가 없습니다."
        else:
            # Group by top-level dir under wiki/. The user wants to see
            # the structure ("entity/", "system/", "person/") not a
            # flat 200-row list.
            from collections import defaultdict
            buckets: dict[str, list[str]] = defaultdict(list)
            for e in all_entities:
                p = e.get("path", "")
                # First path segment as bucket; if no separator, use "(root)".
                head = p.split("/", 1)[0].split("\\", 1)[0] if p else "(root)"
                if "/" not in p and "\\" not in p:
                    head = "(root)"
                buckets[head].append(e.get("name", ""))

            lines = [f"📚 보유 wiki 자료: 총 {total}개"]
            for bucket in sorted(buckets.keys()):
                names = buckets[bucket]
                sample = ", ".join(names[:8])
                more = f" (+{len(names) - 8}개 더)" if len(names) > 8 else ""
                lines.append(f"  • {bucket}/  ({len(names)}개): {sample}{more}")
            lines.append("")
            lines.append(
                "특정 항목 자세히 보려면 구체적으로 질문하세요. "
                "예: '비트코인에 대해 알려줘'"
            )
            answer = "\n".join(lines)

    except Exception as e:
        engine._log("meta_inventory", e, user_role)
        answer = f"❌ 자료 목록 조회 실패: {e}"

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
