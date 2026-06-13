"""LLM extraction prompt for document → entity ingestion.

Extracted from the legacy single-file ``core/wiki_generator/_ingestion.py``
during the v0.6 oversize-module split (CLAUDE.md rule #5). The prompt
text is byte-identical to the pre-split file; only the location moved.

The ``tests/test_entity_type_extension.py`` source-text tests verify
that every horizontal type + per-type rule is present in this file
(see ``test_ingest_prompt_lists_9_types`` /
``test_ingest_prompt_has_per_type_rules``). Editing the prompt
without preserving the 9-type vocabulary breaks ontology contracts.

α-8 extension (2026-06-03): added 5 horizontal types
(event was already here; date/location/quantity/project new) to
match the post-α-8 ontology. Without this extension the wiki had
0 entities of date/location/quantity/project, making the typed
filter's empty-slot signal systematically uninformative — see
memory/project_alpha_8_closure_state.md + feedback_extractor_4_type_gap.
"""
from __future__ import annotations

from core.wiki_generator._aliases import _ONTOLOGY_LABELS_KO


def build_extract_prompt(text: str) -> str:
    """Build the entity-extract LLM prompt for the document body in
    ``text`` (already truncated to 2000 chars by the caller).

    Issue #5: products/tools (Claude Code, Aider, GPT-4) were misclassified
    as `org`. Issue #6: 91% of relations defaulted to 관련 (RELATED_TO),
    leaving the 11 ontology-specific labels under-used. Both addressed by
    tightening this single prompt with explicit type rules + label hints
    by entity-type pair + "use 관련 only when nothing else fits".
    """
    return (
        "Output ONLY raw JSON. No explanation, no markdown.\n"
        "Format: {\"entities\": [{\"name\":\"X\","
        "\"type\":\"person|org|concept|document|event|date|location|quantity|project\","
        "\"description\":\"한줄\",\"occurred_at\":\"YYYY-MM-DD or omit\"}], "
        "\"relations\": [{\"source\":\"X\","
        "\"target\":\"Y\",\"label\":\"관련\",\"confidence\":0.7}]}\n\n"

        "TYPES (9 horizontal — all domain-agnostic, no vertical types):\n"
        "  person   = individual (Sam Altman, 이재명)\n"
        "  org      = company/institution (Anthropic, 삼성전자, 한국은행)\n"
        "  concept  = idea, method, tech, AND products/tools/services\n"
        "             (RAG, GPT-4, Claude Code, Aider, 비트코인, 갤럭시)\n"
        "  document = source document references (rare — usually auto-created)\n"
        "  event    = time-bound occurrence (Q1 실적 발표, ETF 승인, 이벤트).\n"
        "             MUST include occurred_at field (ISO 8601: YYYY-MM-DD).\n"
        "             If date not explicit, emit as concept — DO NOT invent.\n"
        "  date     = explicit calendar reference (2026-05-28, 2026년 1분기,\n"
        "             Q3 2026). Use ONLY when the date itself is the entity\n"
        "             (e.g., 'the 2026 deadline'), NOT when it's an event\n"
        "             attribute. If unsure, prefer event with occurred_at.\n"
        "  location = place name (Seoul, San Francisco, JFK공항, 강남구,\n"
        "             Silicon Valley). City / country / district / facility\n"
        "             are all location. NOT industries or markets.\n"
        "  quantity = explicit numeric measure with unit (10억 달러, 30%,\n"
        "             100 employees, $50M). Use ONLY when the number is\n"
        "             named/referenced as an entity, NOT as attribute.\n"
        "  project  = named initiative / program / campaign\n"
        "             (Project Apollo, MCP v2 개발, Manhattan Project).\n"
        "             NOT generic 'projects' — must have a proper name.\n\n"

        "RULE: a product/tool is CONCEPT, the maker is ORG.\n"
        "  e.g. Anthropic=org, Claude Code=concept (Anthropic 'produces' Claude Code).\n"
        "  Same name must NEVER appear as both org and concept.\n"
        "RULE: prefer SPECIFIC type (event/date/location/quantity/project)\n"
        "  over generic concept when the entity clearly fits. concept is\n"
        "  the catch-all fallback, not the default.\n\n"

        f"RELATION LABELS (Korean, pick from): {_ONTOLOGY_LABELS_KO}\n"
        "Prefer specific label by type pair, NOT 관련:\n"
        "  person→org      => 근무 / 소속\n"
        "  person→concept  => 연구 / 공부\n"
        "  person→project  => 수행\n"
        "  org→person      => 설립됨\n"
        "  org→concept     => 생산 / 분야\n"
        "  org→location    => 위치\n"
        "  org→project     => 수행\n"
        "  concept→concept => 분류 / 구성\n"
        "  event→location  => 발생장소\n"
        "  event→date      => 발생일\n"
        "  event→person    => 참여\n"
        "  *→quantity      => 수치\n"
        "Use 관련 ONLY when none of the above fits.\n\n"

        "Max 6 entities, 6 relations. Extract only entities EXPLICITLY named below.\n\n"
        "Document:\n"
        + text
        + "\n\nJSON:"
    )


__all__ = ["build_extract_prompt"]
