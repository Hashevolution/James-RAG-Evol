"""Wiki generator — cross-doc relation merge + inverse label.

``WikiMergeMixin``: the two heavy relation-side methods —
``_merge_relations_into_existing_entity`` (Knowledge Cascade Phase B
"find_or_create_relation + sources.append") and
``_build_entity_relations`` (per-doc outgoing + inverse stamping for
the ingestion pipeline) — plus the ``_inverse_label_for`` staticmethod
that picks Korean inverse labels.

Layer-3 in the dependency graph. Called from the ingestion pipeline
via ``self.<method>`` once the MRO in ``core/wiki_generator/__init__.py``
composes the mixins onto ``WikiGenerator``.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from core.relations_schema import (
    EXTRACT_SOURCE_ROLE,
    INVERSE_SOURCE_ROLE,
    compute_confidence_from_sources,
)

from ._aliases import _SAFE_ENTITY_NAME_RE


class WikiMergeMixin:

    @staticmethod
    def _inverse_label_for(label: str) -> str:
        """한국어 relation label의 inverse 한국어 label.

        Ontology의 ``RELATION_TYPES[type]['inverse']``는 영어 type ID만
        지정한다 (e.g. ``BELONGS_TO``→``HAS_MEMBER``). 그 inverse가 다시
        ``RELATION_TYPES``에 항목으로 등록된 경우는 거의 없으므로, 비대칭
        relation의 inverse 한국어 label은 정의 부재 상태다.

        실용적 fallback: RELATED_TO(91% 차지)는 대칭이라 같은 label
        ('관련')을 그대로 쓰고, 비대칭에서 inverse label을 못 찾으면
        '관련'으로 떨어뜨린다 (graph_paths 채움이 우선, 정확한 inverse
        label 도입은 별도 작업).
        """
        try:
            from core.ontology import (
                RELATION_TYPES, normalize_relation, get_relation_label,
            )
        except ImportError:
            return "관련"
        std = normalize_relation(label)
        info = RELATION_TYPES.get(std, {})
        inv = info.get("inverse")
        if not inv:
            return "관련"
        if inv == std:
            return get_relation_label(std) or "관련"
        inv_info = RELATION_TYPES.get(inv)
        if inv_info and inv_info.get("label"):
            return inv_info["label"]
        return "관련"

    def _merge_relations_into_existing_entity(
        self,
        entity_id:     str,
        new_relations: List[Dict],
        doc_id:        str,
        ts:            str,
    ) -> Dict[str, int]:
        """기존 entity 의 frontmatter relations 에 새 doc 의 sources 누적 merge.

        docs/design/v0.3-knowledge-cascade.md §4 Phase B 의
        "find_or_create_relation + sources.append" 명세를 구현한다.

        매칭 정책:
          - 같은 (target_name, normalized_type) 쌍이면 → 기존 relation 의
            sources 에 append (doc_id 중복은 skip — idempotent)
          - 없으면 → 새 relation 행으로 추가 (target_id 는 UNRESOLVED,
            resolve_pending_relations 가 추후 해소)

        확신성 (confidence) 은 noisy-OR (`compute_confidence_from_sources`)
        로 재 derive. 단조성 보장: source 추가하면 strictly 증가.

        반환:
            {"merged_into":      0 또는 1,
             "sources_appended": int,  # 새로 추가된 source 개수
             "relations_added":  int}  # 새 행으로 추가된 relation 개수
        """
        path = self.entity_id_index.get(entity_id)
        if not path or not Path(path).exists():
            return {"merged_into": 0, "sources_appended": 0,
                    "relations_added": 0}

        text = Path(path).read_text(encoding="utf-8")
        if not text.startswith("---"):
            return {"merged_into": 0, "sources_appended": 0,
                    "relations_added": 0}
        end = text.find("\n---", 4)
        if end < 0:
            return {"merged_into": 0, "sources_appended": 0,
                    "relations_added": 0}
        fm_raw = text[4:end].lstrip("\n")
        body   = text[end + 4:].lstrip("\n")
        try:
            fm = yaml.safe_load(fm_raw) or {}
        except yaml.YAMLError:
            return {"merged_into": 0, "sources_appended": 0,
                    "relations_added": 0}
        if not isinstance(fm, dict):
            return {"merged_into": 0, "sources_appended": 0,
                    "relations_added": 0}

        existing_rels = fm.get("relations") or []
        if not isinstance(existing_rels, list):
            existing_rels = []

        # type 정규화 — 같은 의미의 label 이 다른 raw 표현으로 등장해도
        # 매칭되도록. ontology 없으면 raw label 그대로 비교.
        try:
            from core.ontology import normalize_relation as _norm_rel
        except Exception:
            def _norm_rel(label):
                return label

        def _norm_type(rel: Dict) -> str:
            t = rel.get("type")
            if isinstance(t, str) and t:
                return t
            label = rel.get("label", "")
            return _norm_rel(label) or label

        sources_appended = 0
        relations_added  = 0

        for new_rel in new_relations:
            if not isinstance(new_rel, dict):
                continue
            new_sources = new_rel.get("sources") or []
            if not isinstance(new_sources, list) or not new_sources:
                continue
            new_target = new_rel.get("target")
            if not new_target:
                continue
            new_type = _norm_type(new_rel)
            if not new_type:
                continue

            match_idx = None
            for i, er in enumerate(existing_rels):
                if not isinstance(er, dict):
                    continue
                if er.get("target") != new_target:
                    continue
                if _norm_type(er) != new_type:
                    continue
                match_idx = i
                break

            if match_idx is not None:
                er = existing_rels[match_idx]
                existing_sources = er.get("sources") or []
                if not isinstance(existing_sources, list):
                    existing_sources = []
                existing_doc_ids = {
                    s.get("doc_id") for s in existing_sources
                    if isinstance(s, dict) and s.get("doc_id")
                }
                for ns in new_sources:
                    if not isinstance(ns, dict):
                        continue
                    ns_did = ns.get("doc_id")
                    if ns_did and ns_did in existing_doc_ids:
                        # 같은 doc 가 두 번 contribute — idempotent skip.
                        # 실제 사용 trigger: doc 재업로드 (modify cascade
                        # Phase D 가 별도로 처리하지만 안전망).
                        continue
                    existing_sources.append(ns)
                    if ns_did:
                        existing_doc_ids.add(ns_did)
                    sources_appended += 1
                er["sources"]    = existing_sources
                er["confidence"] = compute_confidence_from_sources(
                    existing_sources)
            else:
                # 기존에 없던 (target, type) — 새 행 추가. target_id 는
                # UNRESOLVED 로 두고 resolve_pending_relations 가 다음
                # ingest 또는 refresh 시점에 매칭. label 은 new_rel 의
                # display label 보존.
                added = {
                    "target":      new_target,
                    "target_id":   new_rel.get("target_id", "UNRESOLVED"),
                    "target_type": new_rel.get("target_type", "concept"),
                    "type":        new_type,
                    "label":       new_rel.get("label", new_type),
                    "confidence":  compute_confidence_from_sources(
                                       new_sources),
                    "sources":     list(new_sources),
                }
                existing_rels.append(added)
                relations_added += 1

        if sources_appended == 0 and relations_added == 0:
            return {"merged_into": 0, "sources_appended": 0,
                    "relations_added": 0}

        fm["relations"]  = existing_rels
        fm["updated_at"] = datetime.now().isoformat()

        new_text = (
            "---\n"
            + yaml.dump(fm, allow_unicode=True, default_flow_style=False)
            + "---\n\n"
            + body
        )
        Path(path).write_text(new_text, encoding="utf-8")

        return {
            "merged_into":      1,
            "sources_appended": sources_appended,
            "relations_added":  relations_added,
        }

    def _build_entity_relations(
        self,
        source_name:   str,
        raw_relations: List,
        doc_id:        Optional[str] = None,
        ts:            Optional[str] = None,
    ) -> List[Dict]:
        """이 entity가 source 또는 target인 relation을 표준 형식으로 모은다.

        Issue #11: 이전 구현은 source==self만 골라서 target 입장 entity의
        relations 필드가 빈 채로 끝났다. graph_paths가 비어 expand가 항상
        0을 반환했다. 이제 양방향으로 부착한다 (incoming은 inverse label).

        Phase B (Knowledge Cascade): ``doc_id`` 가 주어지면 각 emitted rel
        에 ``sources: [{doc_id, weight=conf, role, ts}]`` 를 즉시 stamp.
        outgoing 은 ``role=extract``, inverse 는 ``role=inverse``. 이로써
        ingestion 시점에 inverse back-fill 까지 한 번에 완료되고
        ``migrate_inverse_relations.py`` 의 별도 sweep 가 필요 없어진다.
        ``doc_id`` 가 없으면 (legacy 호출 경로) sources 미부착 → 기존
        confidence-only 동작 그대로.
        """
        out: List[Dict] = []
        seen: set = set()

        def _stamp(role: str, conf: float) -> Optional[List[Dict]]:
            if not doc_id:
                return None
            return [{
                "doc_id": doc_id,
                "weight": conf,
                "role":   role,
                "ts":     ts,
            }]

        for r in raw_relations or []:
            if not isinstance(r, dict):
                continue
            src = (r.get("source") or "").strip()
            tgt = (r.get("target") or "").strip()
            label = (r.get("label") or "관련").strip()[:20]
            try:
                conf = float(r.get("confidence", 0.7))
            except (TypeError, ValueError):
                conf = 0.7
            conf = max(0.0, min(1.0, conf))

            # Outgoing: source가 self
            if src == source_name and tgt and len(tgt) <= 80 \
                    and _SAFE_ENTITY_NAME_RE.match(tgt):
                key = (tgt, label)
                if key not in seen:
                    seen.add(key)
                    rel_dict = {"target": tgt, "label": label, "confidence": conf}
                    sources = _stamp(EXTRACT_SOURCE_ROLE, conf)
                    if sources:
                        rel_dict["sources"] = sources
                    out.append(rel_dict)
            # Incoming: target이 self → source를 inverse label로 추가
            elif tgt == source_name and src and len(src) <= 80 \
                    and _SAFE_ENTITY_NAME_RE.match(src):
                inv_label = self._inverse_label_for(label)
                key = (src, inv_label)
                if key not in seen:
                    seen.add(key)
                    rel_dict = {"target": src, "label": inv_label, "confidence": conf}
                    sources = _stamp(INVERSE_SOURCE_ROLE, conf)
                    if sources:
                        rel_dict["sources"] = sources
                    out.append(rel_dict)
        return out


__all__ = ["WikiMergeMixin"]
