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

_RECENT_TOKENS = (
    "최근", "새로", "새로운", "최신", "recent", "latest", "new",
    "방금", "오늘", "어제",
)

# v0.6.1 v18 (2026-06-16) — option D narrative trigger. When the
# operator asks "요약해줘" / "정리해줘" / "전체적으로" we route to a
# LLM-narrative variant of the overview. Default overview still takes
# the fast deterministic path.
_NARRATIVE_TOKENS = (
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
