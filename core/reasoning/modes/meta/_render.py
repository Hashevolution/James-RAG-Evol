"""meta-mode response renderers — type / theme / recent detail +
LLM narrative variant.

Pure formatting helpers. The ``_render_llm_narrative`` helper is the
only one that touches an external system (the engine's LLM); it
catches and logs all backend errors so the renderer always returns
a usable string.

Module-size split (CLAUDE.md rule #5): originally part of the 31.6 KB
``modes/meta.py``. Now lives under ``modes/meta/_render.py`` to keep
the dispatcher slim.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from core.reasoning.modes.meta._parse import _TYPE_LABELS, _classify_theme


def _render_type_detail(enriched: List[Dict[str, Any]], etype: str) -> str:
    """Render the full list of entities matching a specific
    entity_type. Capped at 80 names + "외 N 개" so a giant bucket
    doesn't blow the answer length.
    """
    matching = [
        e for e in enriched
        if (e["type"] or "(미분류)") == (etype or "(미분류)")
    ]
    label = _TYPE_LABELS.get(etype, etype.title() or "미분류")
    if not matching:
        return f"## “{label}” 분류 자료 없음\n\n해당 분류로 등록된 wiki 항목이 없습니다."
    # Sort: alphabetical for stability across calls.
    names = sorted([e["name"] for e in matching if e["name"]])
    out: List[str] = [
        f"## 분류 ‘{label}’ — 총 {len(matching)}개",
        "",
        f"_(전체 보유 자료 중 entity_type = `{etype or '(미분류)'}` 항목)_",
        "",
    ]
    CAP = 80
    head = names[:CAP]
    tail = len(names) - len(head)
    # Bullet list — markdown renders these as the .md-ul on the client.
    out.extend(f"- {n}" for n in head)
    if tail > 0:
        out.append(f"- _(외 {tail}개 더 — 더 좁은 키워드로 다시 질문해 보세요)_")
    out.append("")
    out.append(
        "특정 항목을 자세히 보려면 이름으로 직접 질문하세요. "
        "예: \"" + head[0] + "에 대해 알려줘\"."
    )
    return "\n".join(out)


def _render_theme_detail(enriched: List[Dict[str, Any]], theme: str) -> str:
    matching = [e for e in enriched if _classify_theme(e["name"]) == theme]
    if not matching:
        return (
            f"## 주제 ‘{theme}’ 자료 없음\n\n"
            "해당 주제 키워드와 매치되는 wiki 항목이 없습니다."
        )
    names = sorted([e["name"] for e in matching if e["name"]])
    out: List[str] = [
        f"## 주제 ‘{theme}’ — 총 {len(matching)}개",
        "",
        "_(이름 패턴 기반 그룹)_",
        "",
    ]
    CAP = 80
    head = names[:CAP]
    tail = len(names) - len(head)
    out.extend(f"- {n}" for n in head)
    if tail > 0:
        out.append(f"- _(외 {tail}개 더)_")
    out.append("")
    out.append(
        "특정 항목을 자세히 보려면 이름으로 직접 질문하세요. "
        "예: \"" + head[0] + "에 대해 알려줘\"."
    )
    return "\n".join(out)


def _render_llm_narrative(
    engine,
    *,
    total: int,
    by_type: Dict[str, List[str]],
    by_theme: Dict[str, List[str]],
    recent: List[Dict[str, Any]],
    top_degree: List[Tuple[str, int]],
) -> str:
    """v0.6.1 v18 (2026-06-16) — option D: LLM narrative variant.

    Builds a compact summary block first (counts + top names +
    最近 추가) then asks the engine's general LLM to write a 2-3
    paragraph narrative ("이 자료의 주요 주제 / 강점 / 빈약한
    영역"). The deterministic data block is appended below the
    narrative so the operator can verify the LLM's claims at a
    glance.
    """
    # ── data block (deterministic, always renders) ──────────
    type_rows = sorted(by_type.items(), key=lambda kv: -len(kv[1]))[:8]
    theme_rows = [
        (t, n) for t, n in sorted(by_theme.items(), key=lambda kv: -len(kv[1]))
        if t != "기타"
    ][:6]

    type_summary = ", ".join(
        f"{_TYPE_LABELS.get(t, t or '미분류')} {len(ns)}개"
        for t, ns in type_rows
    )
    theme_summary = ", ".join(
        f"{theme} {len(ns)}개" for theme, ns in theme_rows
    )
    hub_summary = ", ".join(f"{name} ({d}연결)" for name, d in top_degree[:5])
    recent_summary = ", ".join(
        e["name"] for e in recent[:5] if e.get("name")
    )

    prompt = (
        f"아래는 한 RAG 시스템이 보유한 wiki 자료의 분포 요약입니다.\n"
        f"이 정보를 바탕으로 한국어로 2~3문단의 자연어 요약을 작성해 주세요.\n"
        f"- 어떤 주제·분야에 강점이 있는지\n"
        f"- 빈약하거나 빠진 영역이 있는지\n"
        f"- 운영자가 다음에 어떤 자료를 추가하면 좋을지 한 줄 추천\n"
        f"숫자는 정확히 인용하고, 추측은 하지 마세요.\n\n"
        f"[총 자료 수] {total}개\n"
        f"[분류별] {type_summary}\n"
        f"[주제별] {theme_summary}\n"
        f"[핵심 hub] {hub_summary or '연결 데이터 없음'}\n"
        f"[최근 추가] {recent_summary}\n\n"
        f"요약:"
    )
    try:
        narrative = engine.llm.call_gemma(
            prompt, timeout=30, use_cache=False,
        ) or ""
    except Exception as e:
        try:
            engine._log("meta_narrative_llm", e, "")
        except Exception:
            pass
        narrative = ""
    narrative = narrative.strip()

    out: List[str] = [f"## 보유 자료 총 {total}개 — 요약"]
    out.append("")
    if narrative:
        out.append(narrative)
        out.append("")
        out.append("---")
        out.append("")
    out.append("### 분류별")
    for t, ns in type_rows:
        label = _TYPE_LABELS.get(t, t or "미분류")
        out.append(f"- **{label}** ({len(ns)}개)")
    out.append("")
    if theme_rows:
        out.append("### 주제별")
        for theme, ns in theme_rows:
            out.append(f"- **{theme}** ({len(ns)}개)")
        out.append("")
    if top_degree:
        out.append("### 핵심 hub (연결 수)")
        for name, deg in top_degree[:5]:
            out.append(f"- **{name}** ({deg} 연결)")
        out.append("")
    if recent:
        out.append("### 최근 추가")
        for e in recent[:5]:
            if e.get("name"):
                out.append(f"- {e['name']}")
        out.append("")
    out.append(
        "특정 분류·주제를 더 자세히 보려면 그 이름으로 다시 질문해 보세요. "
        "예: \"개념 자료에는 뭐가 있어?\"."
    )
    return "\n".join(out)


def _render_recent_detail(enriched: List[Dict[str, Any]], n: int = 30) -> str:
    recent = sorted(enriched, key=lambda x: x["mtime"], reverse=True)[:n]
    if not recent:
        return "## 최근 추가된 자료 없음\n\nwiki 에 아직 등록된 항목이 없습니다."
    out: List[str] = [
        f"## 최근 추가된 자료 (top {len(recent)})",
        "",
        "_(파일 수정 시각 기준 내림차순)_",
        "",
    ]
    for e in recent:
        if not e["name"]:
            continue
        label = _TYPE_LABELS.get(e["type"], e["type"] or "미분류")
        out.append(f"- {e['name']} _(타입: {label})_")
    out.append("")
    out.append(
        "특정 항목을 자세히 보려면 이름으로 직접 질문하세요."
    )
    return "\n".join(out)


__all__ = [
    "_render_type_detail",
    "_render_theme_detail",
    "_render_llm_narrative",
    "_render_recent_detail",
]
