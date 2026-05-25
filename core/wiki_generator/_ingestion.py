"""Wiki generator — document → entity LLM ingestion path.

``WikiIngestionMixin`` (Layer 3 in the dependency graph): the
``process_document_for_entities`` orchestrator and its LLM extraction
helper ``_llm_extract_document_entities`` plus the safety filter
``_is_safe_extracted_entity`` (staticmethod, kept here because it
gates the LLM output before any merge code touches it).

The orchestrator wires the document pipeline:

  LLM extract → safe filter → for each entity:
    existing? → _merge.merge_relations_into_existing_entity
    new?      → _build_entity_relations + _frontmatter.create_entity_file
  + a document-level entity that relates to every extracted entity
  + refresh entity_map + resolve_pending_relations
  + (optional) Phase D extraction sidecar JSON for modify cascade.

All inter-mixin calls go through ``self`` so the MRO composed in
``core/wiki_generator/__init__.py`` resolves them correctly.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.relations_schema import EXTRACT_SOURCE_ROLE

from ._aliases import (
    _ALLOWED_EXTRACT_TYPES,
    _ONTOLOGY_LABELS_KO,
    _SAFE_ENTITY_NAME_RE,
)


class WikiIngestionMixin:

    def process_document_for_entities(
        self,
        filename:  str,
        content:   str,
        chunk_ids: List[str],
        user_role: str = "admin",
        metadata:  Optional[Dict] = None,
        extraction_sidecar_path: Optional[str] = None,
    ) -> List[str]:
        """
        문서 본문에서 LLM으로 인물/조직/개념 entity와 relation을 추출하여
        각 entity별 .md를 생성하고, 추가로 원본을 document entity로도 보존한다.

        Phase D (Knowledge Cascade): 호출자가 ``extraction_sidecar_path`` 를
        주면 LLM extraction 결과 (entities + relations 원본 + metadata) 를
        JSON sidecar 로 저장한다. Phase D 의 modify cascade 가 다음 재업로드
        시 이 sidecar 를 읽어 old/new diff 를 계산한다. sidecar 부재 시
        modify cascade 는 wipe+reingest fallback 으로 동작 — backwards
        compatible (Phase B 이전 업로드도 안전).

        Returns:
            생성된 entity_id 리스트 (실패 시 빈 리스트 또는 document만)
        """
        metadata  = metadata or {}
        extracted = self._llm_extract_document_entities(filename, content, metadata)

        # Phase B (Knowledge Cascade): 이 ingestion 가 만들어내는 모든
        # relation 은 같은 doc 에서 유래하므로 doc_entity_id 와 ts 를
        # 한 번 계산해 모든 _build_entity_relations / doc_relations 호출
        # 에 동일하게 stamp. doc entity 자체는 _generate_entity_id 가
        # name+type 결정적 함수라 미리 계산해도 나중 create 시점과 같다.
        ingest_ts     = datetime.now().isoformat()
        doc_name      = os.path.splitext(filename)[0]
        doc_entity_id = self._generate_entity_id(doc_name, "document")

        # v0.4 Sprint 1 #1 — entity-name overlap snapshot built once
        # per document so every entity in this doc can reuse it
        # without re-scanning every wiki file. The snapshot is a
        # frozen view at ingestion start; entities created later in
        # this same doc are not in it (their overlaps to siblings
        # are resolved by `resolve_pending_relations` post-pass).
        overlap_snapshot = self._build_overlap_snapshot()

        created_ids:   List[str]      = []
        name_to_id:    Dict[str, str] = {}
        name_to_type:  Dict[str, str] = {}

        for ent in extracted.get("entities", []):
            if not self._is_safe_extracted_entity(ent):
                continue
            name  = ent["name"].strip()
            etype = ent["type"]

            existing_id = self._find_existing_entity_id(name, etype)
            if existing_id:
                # Cross-doc aggregation — docs/design/v0.3-knowledge-cascade.md
                # §4 Phase B 의 "find_or_create_relation + sources.append".
                # 이전 구현은 `continue` 로 두 번째 doc 의 강화를 통째로
                # 버렸다 (Knowledge Cascade 핵심 가치 무효화). 이제 기존
                # entity 의 frontmatter 에 새 doc 의 sources 만 누적 merge.
                new_rels = self._build_entity_relations(
                    name, extracted.get("relations", []),
                    doc_id=doc_entity_id, ts=ingest_ts,
                )
                # v0.4 Sprint 1 #1 — overlap detection also applies
                # on the merge branch so re-ingestion of an entity
                # whose name overlaps with newly-existing tokens
                # picks up the relation. Identical pattern to the
                # new-entity branch below.
                merge_overlap_rels = self._infer_overlap_relations(
                    name, overlap_snapshot,
                    doc_id=doc_entity_id, ts=ingest_ts,
                )
                if merge_overlap_rels:
                    seen = {(r.get("target"), r.get("label"))
                            for r in new_rels}
                    for r in merge_overlap_rels:
                        key = (r.get("target"), r.get("label"))
                        if key not in seen:
                            new_rels.append(r)
                            seen.add(key)
                if new_rels:
                    stats = self._merge_relations_into_existing_entity(
                        existing_id, new_rels, doc_entity_id, ingest_ts,
                    )
                    print(f"[ENTITY-EXTRACT] '{name}' ({etype}) exists "
                          f"-> merged sources={stats['sources_appended']} "
                          f"new_rels={stats['relations_added']}")
                else:
                    print(f"[ENTITY-EXTRACT] '{name}' ({etype}) exists "
                          f"-> no new triples in this doc")
                name_to_id[name]   = existing_id
                name_to_type[name] = etype
                continue

            ent_relations = self._build_entity_relations(
                name, extracted.get("relations", []),
                doc_id=doc_entity_id, ts=ingest_ts,
            )
            # v0.4 Sprint 1 #1 — token-level entity-name overlap
            # detection. New event/document/concept entities whose
            # name contains an existing entity's normalized name as
            # a token get an automatic RELATED_TO relation. Without
            # this step, "비트코인 spot ETF 11개 일괄 승인" event
            # was being ingested with zero link to the existing
            # "비트코인" concept (LLM extractor only emits explicit
            # source/target pairs from the document body).
            overlap_rels = self._infer_overlap_relations(
                name, overlap_snapshot,
                doc_id=doc_entity_id, ts=ingest_ts,
            )
            if overlap_rels:
                seen_targets = {(r.get("target"), r.get("label"))
                                for r in ent_relations}
                for r in overlap_rels:
                    key = (r.get("target"), r.get("label"))
                    if key not in seen_targets:
                        ent_relations.append(r)
                        seen_targets.add(key)
            # [B-2-A fix] top-level `summary` mirrors `attributes.summary`
            # so the wiki body builder (`_frontmatter.py:create_entity_file`)
            # can populate `## 요약`. The builder only reads top-level keys;
            # without this mirror every newly-ingested entity's body section
            # stays empty even though `attributes.summary` carries the LLM
            # description.
            # v0.4 Sprint 3 BL-2 — stop emitting `attributes.summary` here.
            # Top-level `summary` is canonical; the duplicate at
            # `attributes.summary` was kept only because older callers
            # passed it that way. _frontmatter.py:create_entity_file still
            # reads `attributes.summary` as a fallback for legacy wiki
            # files on disk, but new ingestion writes shouldn't keep
            # creating the duplicate.
            _desc = (ent.get("description") or "")[:300]
            payload = {
                "name":        name,
                "type":        etype,
                "summary":     _desc,
                "attributes":  {
                    "source_document":  filename,
                },
                "relations":   ent_relations,
                "sensitivity": "internal",
                "source_type": self.source_type,
            }
            # PR-11b — carry event time-axis fields from LLM extraction
            # to the create_entity_file event branch. Without these,
            # the event branch's validate_occurred_at() always fails
            # and falls back to concept (the symptom that surfaced in
            # the 2026-05-21 live verification).
            if etype == "event":
                if ent.get("occurred_at"):
                    payload["occurred_at"] = ent["occurred_at"]
                if ent.get("occurred_at_precision"):
                    payload["occurred_at_precision"] = ent["occurred_at_precision"]
            try:
                self.create_entity_file(payload, filename, chunk_ids, user_role=user_role)
                # PR-11b — event entities use the date-aware hash
                # (`_generate_event_entity_id`, PR-11a-2) so the
                # entity_id we record here matches the file
                # create_entity_file actually wrote. Falling through to
                # the 4-type `_generate_entity_id` would produce a
                # stale id and break cross-doc aggregation / id
                # lookups for the same event.
                if etype == "event" and payload.get("occurred_at"):
                    from core.graph_node_editor import _generate_event_entity_id
                    eid = _generate_event_entity_id(
                        name,
                        payload["occurred_at"],
                        payload.get("occurred_at_precision", "day"),
                    )
                else:
                    eid = self._generate_entity_id(name, etype)
                name_to_id[name]   = eid
                name_to_type[name] = etype
                created_ids.append(eid)
                print(f"[ENTITY-EXTRACT] OK {etype}/{name}")
            except ValueError as e:
                print(f"[ENTITY-EXTRACT] Trust reject: {name} ({e})")
            except Exception as e:
                print(f"[ENTITY-EXTRACT] FAIL {name}: {e}")

        # document entity (원본 보존 + 모든 추출 entity와 RELATED_TO).
        # Phase B: doc 의 outgoing edge 도 sources 를 stamp (doc_id=self).
        # cascade delete 시 sources[*].doc_id 가 deleted doc 이면 drop —
        # 이 self-source 들은 doc 삭제 시 함께 사라진다 (대상 entity 의
        # incoming sources 가 0 이 되면 relation 자체가 사라짐 = Phase C 의
        # cascade 와 정합).
        doc_relations = [
            {
                "target":      n,
                "target_type": name_to_type.get(n, "concept"),
                "label":       "관련",
                "confidence":  0.7,
                "sources":     [{
                    "doc_id": doc_entity_id,
                    "weight": 0.7,
                    "role":   EXTRACT_SOURCE_ROLE,
                    "ts":     ingest_ts,
                }],
            }
            for n in name_to_id
        ]
        kw = metadata.get("keywords", [])
        kw_str = ", ".join(str(k) for k in kw) if isinstance(kw, list) else str(kw)
        # [B-2-A fix] mirror top-level summary for the document entity too —
        # same reason as the entity-extract branch above.
        _doc_summary = (metadata.get("summary") or "")[:500]
        doc_payload = {
            "name":        doc_name,
            "type":        "document",
            "summary":     _doc_summary,
            "attributes":  {
                "summary":   _doc_summary,
                "category":  metadata.get("category", "기타"),
                "keywords":  kw_str,
            },
            "relations":   doc_relations,
            "sensitivity": metadata.get("sensitivity", "internal"),
            "source_type": self.source_type,
        }
        try:
            self.create_entity_file(doc_payload, filename, chunk_ids, user_role=user_role)
            created_ids.append(self._generate_entity_id(doc_name, "document"))
        except Exception as e:
            print(f"[ENTITY-EXTRACT] document entity FAIL: {e}")

        try:
            self.refresh_entity_map()
        except Exception:
            self._build_entity_id_index()

        # 이 ingest 로 새 entity 가 들어왔다 → 이전 ingest 가 UNRESOLVED 로
        # 남겨둔 relation 들이 매칭될 수 있다. entity_map refresh 직후 2-pass
        # 재매칭을 돌려 그래프 edge 가 새로 늘어나는 효과를 즉시 반영한다.
        try:
            self.resolve_pending_relations()
        except Exception as e:
            print(f"[ENTITY-EXTRACT] resolve_pending_relations fail (무시): {e}")

        # Phase D — extraction sidecar 저장. 재업로드 시 modify cascade 가
        # old vs new diff 를 계산하려면 마지막 LLM 출력이 필요하다.
        # 사용자 ingest 정보 (filename / category / keywords) + 추출 원본을
        # 함께 저장해 cascade 가 self-contained 로 동작.
        if extraction_sidecar_path:
            try:
                sidecar = {
                    "filename":   filename,
                    "ingest_ts":  ingest_ts,
                    "metadata":   {
                        "summary":  metadata.get("summary", ""),
                        "category": metadata.get("category", "기타"),
                        "keywords": metadata.get("keywords", []),
                    },
                    "extraction": {
                        "entities":  extracted.get("entities", []),
                        "relations": extracted.get("relations", []),
                    },
                }
                with open(extraction_sidecar_path, "w", encoding="utf-8") as sf:
                    json.dump(sidecar, sf, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"[ENTITY-EXTRACT] sidecar write skipped: {e}")

        print(f"[ENTITY-EXTRACT] {filename} -> {len(created_ids)} entities created "
              f"(extracted {len(name_to_id)} + 1 document)")
        return created_ids

    def _llm_extract_document_entities(
        self,
        filename: str,
        content:  str,
        metadata: Dict,
    ) -> Dict:
        """LLM 호출 + JSON 파싱. 실패 시 {'entities':[], 'relations':[]} 반환."""
        # generate_metadata 와 같은 형식으로 통일 (그쪽이 안정적으로 동작 검증됨)
        text = (content or "")[:2000]

        # Issue #5: products/tools (Claude Code, Aider, GPT-4) were misclassified
        # as `org`. Issue #6: 91% of relations defaulted to 관련 (RELATED_TO),
        # leaving the 11 ontology-specific labels under-used. Both addressed by
        # tightening this single prompt with explicit type rules + label hints
        # by entity-type pair + "use 관련 only when nothing else fits".
        prompt = (
            "Output ONLY raw JSON. No explanation, no markdown.\n"
            "Format: {\"entities\": [{\"name\":\"X\",\"type\":\"person|org|concept|event\","
            "\"description\":\"한줄\",\"occurred_at\":\"YYYY-MM-DD or omit\"}], "
            "\"relations\": [{\"source\":\"X\","
            "\"target\":\"Y\",\"label\":\"관련\",\"confidence\":0.7}]}\n\n"

            "TYPES (4 only):\n"
            "  person  = individual (Sam Altman, 이재명)\n"
            "  org     = company/institution (Anthropic, 삼성전자, 한국은행)\n"
            "  concept = idea, method, tech, AND products/tools/services\n"
            "            (RAG, GPT-4, Claude Code, Aider, 비트코인, 갤럭시)\n"
            "  event   = time-bound occurrence (Q1 실적 발표, ETF 승인, 이벤트).\n"
            "            MUST include occurred_at field (ISO 8601: YYYY-MM-DD).\n"
            "            If the date is not explicit in the document, "
            "emit as concept instead — DO NOT invent a date.\n"
            "RULE: a product/tool is CONCEPT, the maker is ORG.\n"
            "  e.g. Anthropic=org, Claude Code=concept (Anthropic 'produces' Claude Code).\n"
            "  Same name must NEVER appear as both org and concept.\n\n"

            f"RELATION LABELS (Korean, pick from): {_ONTOLOGY_LABELS_KO}\n"
            "Prefer specific label by type pair, NOT 관련:\n"
            "  person→org     => 근무 / 소속\n"
            "  person→concept => 연구 / 공부\n"
            "  org→person     => 설립됨\n"
            "  org→concept    => 생산 / 분야\n"
            "  concept→concept=> 분류 / 구성\n"
            "Use 관련 ONLY when none of the above fits.\n\n"

            "Max 6 entities, 6 relations. Extract only entities EXPLICITLY named below.\n\n"
            "Document:\n"
            + text
            + "\n\nJSON:"
        )
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

    @staticmethod
    def _is_safe_extracted_entity(ent: Any) -> bool:
        """Schema + 보안 검증. injection-safe + 길이/타입 화이트리스트."""
        if not isinstance(ent, dict):
            return False
        name = ent.get("name", "")
        if not isinstance(name, str):
            return False
        name = name.strip()
        if len(name) < 2 or len(name) > 80:
            return False
        if not _SAFE_ENTITY_NAME_RE.match(name):
            return False
        if ent.get("type") not in _ALLOWED_EXTRACT_TYPES:
            return False
        return True


__all__ = ["WikiIngestionMixin"]
