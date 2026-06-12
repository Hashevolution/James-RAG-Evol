"""α-8 Phase A — type-aware graph entity filter (preserves evidence-of-absence).

Implements the design constraint from
`docs/design/v0.4-alpha-8-ontology-typed-filter.md` §2.4 (R1-R5):

  R1. Never silently drop a type slot — if a query expects type T, emit a
      row for T even if zero entities of type T were surfaced.
  R2. Empty-type rows are first-class context — explicit "(none found)" line.
  R3. Don't conflate "empty" with "type not in query" — classifier output
      identifies query-relevant types; irrelevant types may be omitted.
  R4. Order types by relevance to query, not alphabetic.
  R5. Cap total type slots <= 10 (loose); never silently truncate WITHIN slots.

Module is **opt-in** via `JAMES_DISABLE_TYPED_FILTER` env var (disable-polarity,
default unset = filter ON; set to any truthy value disables for byte-identical
production behaviour during sector cell measurement).

Filter operates on the entity list AFTER DFS traversal, just before context
string assembly. It does NOT modify the DFS itself (α-7 mechanism — rejected
because it removed entities the LLM needed to detect absence).

Public API:
- `is_typed_filter_disabled()` — read the runtime flag
- `classify_query_intent(query)` — keyword heuristic → ranked type list
- `group_entities_by_type(entities, query_types, cap=10)` — apply R1-R5,
   returns a list of `(type_name, entity_list, present_flag)` tuples in
   intent-rank order, with empty slots emitted for query_types that have
   no entities
- `format_typed_context(groups)` — render to the explicit
  `[Type]: name1, name2` / `[Type]: (none found in graph for this query)`
  string the LLM will read.
"""

from __future__ import annotations

import os
import re
from typing import Dict, Iterable, List, Sequence, Tuple

from core.ontology import DOCUMENT_SUBTYPES, ENTITY_TYPES


# ─── Runtime flag ──────────────────────────────────────────────────────

_DISABLE_ENV_VAR = "JAMES_DISABLE_TYPED_FILTER"


def is_typed_filter_disabled() -> bool:
    """True if `JAMES_DISABLE_TYPED_FILTER` is set to a truthy value.

    Default (env var unset / empty / "0" / "false") returns False = filter ON.
    Used by the matrix runner sector cells to compare with the typed filter
    inactive (= production byte-identical pre-α-8 path).
    """
    raw = (os.environ.get(_DISABLE_ENV_VAR, "") or "").strip().lower()
    return raw not in ("", "0", "false", "no", "off")


# ─── Query intent classifier (keyword heuristic) ──────────────────────
#
# Cheap deterministic classifier per design memo §2.1 step 5. LLM-judge
# upgrade is a v0.5+ candidate. The bag-of-keywords design is intentional:
# if a heuristic classifier-based filter beats heuristic top-K, the LLM
# classifier upgrade has a *floor* not a ceiling (per design memo §1.3).

_INTENT_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    # Temporal intent → date + event
    "date": (
        "when", "what year", "what date", "what time", "what month",
        "언제", "년도", "몇 년", "몇년", "몇 월", "몇월", "날짜",
    ),
    "event": (
        "what happened", "which event", "what event", "occurred",
        "어떤 일", "무슨 일", "사건", "발생",
    ),
    # Spatial intent → location
    "location": (
        "where", "place", "city", "country", "located", "address",
        "어디", "어디서", "장소", "위치", "도시", "나라", "국가",
    ),
    # Numeric intent → quantity
    "quantity": (
        "how much", "how many", "price", "amount", "cost", "size",
        "weight", "volume", "percent", "ratio",
        "얼마", "몇", "가격", "값", "수량", "비율", "%",
    ),
    # Identity intent → person + org
    "person": (
        "who", "founder", "ceo", "director", "author", "ko-founder",
        "누구", "설립자", "대표", "임원", "저자", "작가",
    ),
    "org": (
        "which company", "what company", "which organization",
        "what organization", "firm", "agency", "corporation",
        "어떤 회사", "회사", "기업", "조직", "단체", "기관",
    ),
    # Project / initiative intent
    "project": (
        "which project", "what project", "initiative", "program",
        "어떤 프로젝트", "프로젝트", "이니셔티브", "프로그램", "과제",
    ),
}

# Tokenizer accepts ASCII + CJK characters; case-insensitive substring match.
_TOKEN_RE = re.compile(r"\s+")


def classify_query_intent(query: str) -> List[str]:
    """Heuristic classifier → ranked list of expected entity types.

    Returns types whose keywords appear in the query (case-insensitive
    substring match), ordered by keyword-count descending. Ties broken by
    `ENTITY_TYPES` declaration order. If no keyword matches, returns
    `["concept"]` as the fallback default (concept is the most permissive
    existing type and matches generic "what is X" queries).

    Cap: at most 10 types (R5). Reality check: 7 intent buckets currently
    defined, so the cap is loose.
    """
    if not query:
        return ["concept"]

    q_lower = query.lower()
    counts: Dict[str, int] = {}
    for type_name, keywords in _INTENT_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in q_lower:
                counts[type_name] = counts.get(type_name, 0) + 1

    if not counts:
        return ["concept"]

    # Sort by (count desc, ENTITY_TYPES declaration index asc) — stable
    declaration_order = {t: i for i, t in enumerate(ENTITY_TYPES)}
    ranked = sorted(
        counts.items(),
        key=lambda kv: (-kv[1], declaration_order.get(kv[0], 999)),
    )
    return [t for t, _ in ranked[:10]]


# ─── Grouping with empty-slot preservation (R1-R5) ────────────────────


def _entity_type_of(entity: dict) -> str:
    """Recover an entity's type using the conventional field names."""
    return (
        entity.get("entity_type")
        or entity.get("type")
        or "concept"
    )


def group_entities_by_type(
    entities: Iterable[dict],
    query_types: Sequence[str],
    cap: int = 10,
) -> List[Tuple[str, List[dict], bool]]:
    """Group entities by type, emitting empty rows per R1-R5.

    Args:
        entities: iterable of entity dicts (from graph DFS).
        query_types: query-relevant types in intent-rank order.
        cap: maximum number of type slots in output (R5; default 10).

    Returns:
        A list of `(type_name, entity_list, present_flag)` tuples in the
        order:
          1. query_types in intent-rank order — included whether empty or
             not (R1 + R3); `present_flag` reflects whether entity_list is
             non-empty.
          2. Up to `cap - len(query_types)` additional type slots populated
             from entities whose type is NOT in query_types but DID appear
             in the DFS — included only if non-empty (R3 inverse).

    The total slot count is at most `cap` (R5). Within each slot, ALL
    entities of that type are included; this function never truncates
    inside a slot.
    """
    if cap < 1:
        cap = 1

    # Bucket entities by type
    buckets: Dict[str, List[dict]] = {}
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        t = _entity_type_of(ent)
        buckets.setdefault(t, []).append(ent)

    out: List[Tuple[str, List[dict], bool]] = []
    used: set = set()

    # Phase 1 — query-relevant types in intent order (R1+R4)
    for t in query_types:
        if len(out) >= cap:
            break
        ents = buckets.get(t, [])
        out.append((t, ents, bool(ents)))
        used.add(t)

    # Phase 2 — additional non-empty types not yet covered (R3 inverse)
    # Preserve ENTITY_TYPES declaration order for stable display
    for t in ENTITY_TYPES:
        if len(out) >= cap:
            break
        if t in used:
            continue
        ents = buckets.get(t, [])
        if ents:
            out.append((t, ents, True))

    return out


# ─── Context renderer (string format for the LLM) ────────────────────


def _entity_label(entity: dict) -> str:
    """Pick a readable label for an entity dict."""
    return (
        entity.get("name")
        or entity.get("label")
        or entity.get("title")
        or entity.get("entity_id", "")
        or "?"
    )


def format_typed_context(
    groups: List[Tuple[str, List[dict], bool]],
    *,
    none_phrase: str = "(none found in graph for this query)",
    header: str = "[ENTITIES BY TYPE]",
    entity_separator: str = ", ",
) -> str:
    """Render type-grouped entities to the explicit string the LLM reads.

    Format:
        [ENTITIES BY TYPE]
          [Person]: Alice, Bob, Carol
          [Date]:   (none found in graph for this query)
          [Org]:    Roche, OpenAI
          ...

    The empty-slot phrase is the structural evidence-of-absence signal
    (R2). Default phrase matches the design memo §1.6 example.
    """
    lines: List[str] = [header]
    for type_name, ents, present in groups:
        if present:
            labels = [_entity_label(e) for e in ents]
            rendered = entity_separator.join(labels)
        else:
            rendered = none_phrase
        lines.append(f"  [{type_name.capitalize()}]: {rendered}")
    return "\n".join(lines)


# ─── Convenience: end-to-end application ──────────────────────────────


def apply_typed_filter(
    query: str,
    entities: Iterable[dict],
    cap: int = 10,
) -> Tuple[str, List[Tuple[str, List[dict], bool]]]:
    """Run intent classifier + grouping + rendering in one call.

    Returns `(rendered_string, groups)` so callers can either drop the
    string directly into the LLM prompt or inspect the grouping for
    audit purposes.

    Disabled-state behaviour: when `JAMES_DISABLE_TYPED_FILTER` is set,
    callers should bypass this function and use the existing
    pre-α-8 context assembly path. This function does NOT auto-disable;
    the polarity check belongs at the call site so the integration
    layer can A/B both paths cleanly.
    """
    query_types = classify_query_intent(query)
    groups = group_entities_by_type(entities, query_types, cap=cap)
    rendered = format_typed_context(groups)
    return rendered, groups


# ─── v0.5 B.5.d — Document-subtype intent layer ───────────────────────
#
# Parallel to the entity-type classifier above, but operating on
# DOCUMENT_SUBTYPES (10 horizontal subtypes added in B.5.b). For
# enterprise queries like "which policy is in force?", the
# entity-type-level classifier would return ["org"] or fall through to
# "concept" — losing the structural cue that the user is asking about a
# specific document KIND. This layer fills that gap with the same
# R1-R5 contract preserved at the subtype level.
#
# This layer is additive — existing callers of `classify_query_intent`
# / `apply_typed_filter` are unchanged. Callers that ingest document
# entities can opt in to `apply_document_subtype_filter` for an extra
# typed-context block. The same `JAMES_DISABLE_TYPED_FILTER` env var
# disables both layers.
#
# Vertical-agnostic per CLAUDE.md rule #1 — keywords are generic
# horizontal terms (no NDA / recipe / 10-K / treatment-protocol).

_SUBTYPE_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "contract": (
        "contract", "agreement", "sla", "service agreement", "mou",
        "계약", "계약서", "협약", "서비스 계약",
    ),
    "policy": (
        "policy", "policies", "guideline", "guidelines", "rule book",
        "정책", "지침", "방침",
    ),
    "procedure": (
        "procedure", "process", "sop", "workflow", "how to",
        "절차", "프로세스", "업무 절차", "표준 작업",
    ),
    "memo": (
        "memo", "memorandum", "internal note", "announcement",
        "메모", "공지", "사내 공지", "안내",
    ),
    "report": (
        "report", "summary", "review document", "analysis",
        "보고서", "리포트", "분석 보고",
    ),
    "specification": (
        "specification", "spec", "design doc", "design document",
        "requirements", "api spec",
        "명세", "사양", "스펙", "설계 문서", "요구사항",
    ),
    "meeting_minutes": (
        "minutes", "meeting minutes", "meeting notes", "회의록",
        "회의 기록", "회의 메모",
    ),
    "standard": (
        "standard", "convention", "norm", "baseline document",
        "표준", "규약", "규격", "준칙",
    ),
    "form": (
        "form", "template", "request form", "intake form",
        "양식", "서식", "신청서", "템플릿",
    ),
    "record": (
        "record", "log", "logbook", "ledger", "decision log",
        "기록", "이력", "로그", "장부",
    ),
}


def classify_document_subtype_intent(query: str) -> List[str]:
    """Heuristic classifier → ranked list of expected DOCUMENT_SUBTYPES.

    Mirror of `classify_query_intent` but operating on the v0.5 document
    subtype layer. Returns subtypes whose keywords appear in the query
    (case-insensitive substring match), ordered by keyword-count
    descending. Ties broken by DOCUMENT_SUBTYPES declaration order.

    No fallback: if no subtype keyword matches, returns ``[]`` (the
    document-subtype layer is OPT-IN per-query — the entity-type
    classifier has its own "concept" fallback for general queries).

    Cap: at most 10 subtypes (R5). The 10 horizontal subtypes registered
    in B.5.b naturally fit under the cap.
    """
    if not query:
        return []

    q_lower = query.lower()
    counts: Dict[str, int] = {}
    for subtype_name, keywords in _SUBTYPE_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in q_lower:
                counts[subtype_name] = counts.get(subtype_name, 0) + 1

    if not counts:
        return []

    declaration_order = {t: i for i, t in enumerate(DOCUMENT_SUBTYPES)}
    ranked = sorted(
        counts.items(),
        key=lambda kv: (-kv[1], declaration_order.get(kv[0], 999)),
    )
    return [t for t, _ in ranked[:10]]


def _document_subtype_of(doc: dict) -> str:
    """Recover a document's subtype using the conventional field names."""
    return (
        doc.get("subtype")
        or doc.get("document_subtype")
        or ""
    )


def group_documents_by_subtype(
    documents: Iterable[dict],
    query_subtypes: Sequence[str],
    cap: int = 10,
) -> List[Tuple[str, List[dict], bool]]:
    """Group documents by SUBTYPE, emitting empty rows per R1-R5.

    Subtype-level parallel of `group_entities_by_type`. Same R1-R5
    contract:

      R1. Never silently drop a query-relevant subtype slot.
      R2. Empty subtype rows are first-class context.
      R3. Documents whose subtype is not in ``query_subtypes`` are
          ONLY included as non-empty extra slots (no empty extras).
      R4. Subtype slots are ordered by query intent rank first.
      R5. Total slots capped at ``cap`` (default 10).

    Documents with an empty / unknown subtype are silently skipped at
    bucketing time (they cannot anchor a subtype slot).
    """
    if cap < 1:
        cap = 1

    buckets: Dict[str, List[dict]] = {}
    for doc in documents:
        if not isinstance(doc, dict):
            continue
        sub = _document_subtype_of(doc)
        if not sub:
            continue
        buckets.setdefault(sub, []).append(doc)

    out: List[Tuple[str, List[dict], bool]] = []
    used: set = set()

    # Phase 1 — query-relevant subtypes in intent order (R1+R4)
    for s in query_subtypes:
        if len(out) >= cap:
            break
        docs = buckets.get(s, [])
        out.append((s, docs, bool(docs)))
        used.add(s)

    # Phase 2 — non-empty registered subtypes not yet covered (R3 inverse)
    for s in DOCUMENT_SUBTYPES:
        if len(out) >= cap:
            break
        if s in used:
            continue
        docs = buckets.get(s, [])
        if docs:
            out.append((s, docs, True))

    return out


def _document_label(doc: dict) -> str:
    """Pick a readable label for a document dict."""
    return (
        doc.get("title")
        or doc.get("name")
        or doc.get("doc_id", "")
        or "?"
    )


def format_subtype_context(
    groups: List[Tuple[str, List[dict], bool]],
    *,
    none_phrase: str = "(none found in graph for this query)",
    header: str = "[DOCUMENTS BY SUBTYPE]",
    entity_separator: str = ", ",
) -> str:
    """Render subtype-grouped documents to the LLM-readable string.

    Format:
        [DOCUMENTS BY SUBTYPE]
          [Policy]:    Data retention policy
          [Procedure]: (none found in graph for this query)
          [Report]:    Annual report 2025
          ...

    Empty-slot phrase is the structural evidence-of-absence signal (R2).
    """
    lines: List[str] = [header]
    for subtype_name, docs, present in groups:
        if present:
            labels = [_document_label(d) for d in docs]
            rendered = entity_separator.join(labels)
        else:
            rendered = none_phrase
        # Title-case multi-word subtypes (meeting_minutes → Meeting_Minutes)
        # using simple capitalize on each '_'-separated part for readability.
        display = " ".join(p.capitalize() for p in subtype_name.split("_"))
        lines.append(f"  [{display}]: {rendered}")
    return "\n".join(lines)


def apply_document_subtype_filter(
    query: str,
    documents: Iterable[dict],
    cap: int = 10,
) -> Tuple[str, List[Tuple[str, List[dict], bool]]]:
    """Subtype-level convenience: classify + group + render in one call.

    Returns ``(rendered_string, groups)``. When the query contains no
    subtype keywords, returns ``("", [])`` — the caller should fall back
    to the existing entity-type-level context.

    Disabled-state behaviour: same as `apply_typed_filter` — callers
    check `is_typed_filter_disabled()` at the call site rather than this
    function auto-disabling, so the A/B comparison stays clean at the
    integration layer.
    """
    query_subtypes = classify_document_subtype_intent(query)
    if not query_subtypes:
        return "", []
    groups = group_documents_by_subtype(documents, query_subtypes, cap=cap)
    rendered = format_subtype_context(groups)
    return rendered, groups


__all__ = (
    "is_typed_filter_disabled",
    "classify_query_intent",
    "group_entities_by_type",
    "format_typed_context",
    "apply_typed_filter",
    # v0.5 B.5.d — document subtype layer
    "classify_document_subtype_intent",
    "group_documents_by_subtype",
    "format_subtype_context",
    "apply_document_subtype_filter",
)
