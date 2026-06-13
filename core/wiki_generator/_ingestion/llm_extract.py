"""LLM extract → JSON parse helper for document → entity ingestion.

Extracted from the legacy single-file ``core/wiki_generator/_ingestion.py``
during the v0.6 oversize-module split (CLAUDE.md rule #5). Behaviour is
byte-identical; only the location moved.
"""
from __future__ import annotations

import json
import re
from typing import Dict

from core.wiki_generator._ingestion.prompts import build_extract_prompt


def llm_extract_document_entities(
    filename: str,
    content:  str,
    metadata: Dict,
) -> Dict:
    """LLM 호출 + JSON 파싱. 실패 시 {'entities':[], 'relations':[]} 반환.

    Module-level so the mixin in ``mixin.py`` can stay thin and the
    20 KB rule #5 cap leaves headroom for the orchestrator body.
    """
    # generate_metadata 와 같은 형식으로 통일 (그쪽이 안정적으로 동작 검증됨)
    text = (content or "")[:2000]
    prompt = build_extract_prompt(text)

    try:
        from llm.router import call_router
        # max_tokens=4096: bumped from 1500 (2026-05-24) after a real-traffic
        # report where a doc with multiple entities + occurred_at fields per
        # entity (Musk-related companies, ~5 KB markdown) truncated mid-JSON
        # at ~624 chars (Korean+English mix) → JSON parse fail → 0 entities
        # created. Aligns with Direction 1's V3'.a~d 4-stage cognitive
        # sweep finding (PR #461 / #463): on gemma4:e4b the entity-extract
        # task has a natural-stop length above 1500 for multi-entity docs,
        # behaves like the 'heavy synthesis' CAP_HEAVY=4096 tier in
        # core/reasoning/budget.py. The model still stops naturally well
        # below 4096 (Direction 1's cap-is-a-ceiling finding), so the bump
        # incurs no measurable cost on smaller docs — only unblocks the
        # multi-entity case.
        response = call_router(
            prompt, task_type="extract", use_cache=False, max_tokens=4096,
        )
    except Exception as e:
        print(f"[ENTITY-EXTRACT] LLM call FAIL: {e}")
        return {"entities": [], "relations": []}

    if (not response or not response.strip()
            or "응답 없음" in response or "Gemma 오류" in response):
        print(f"[ENTITY-EXTRACT] LLM empty/error response: {response[:80]}")
        return {"entities": [], "relations": []}

    m = re.search(r'\{.*\}', response, re.DOTALL)
    if not m:
        print(f"[ENTITY-EXTRACT] no JSON in response (head): {response[:200]}")
        return {"entities": [], "relations": []}
    raw_json = m.group(0)
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        print(f"[ENTITY-EXTRACT] JSON parse FAIL: {e} | head: {raw_json[:200]}")
        return {"entities": [], "relations": []}

    if not isinstance(data, dict):
        return {"entities": [], "relations": []}
    ents = data.get("entities", []) or []
    rels = data.get("relations", []) or []
    if not isinstance(ents, list):
        ents = []
    if not isinstance(rels, list):
        rels = []
    return {"entities": ents, "relations": rels}


__all__ = ["llm_extract_document_entities"]
