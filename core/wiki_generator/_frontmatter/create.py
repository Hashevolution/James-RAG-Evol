"""``create_entity_file`` writer — sub-mixin of
``WikiFrontmatterMixin``.

Extracted from the legacy single-file
``core/wiki_generator/_frontmatter.py`` during the v0.6 oversize-module
split (CLAUDE.md rule #5). Behaviour is byte-identical; only the
location moved.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List

import yaml

from core.relations_schema import (
    compute_confidence_from_sources,
    validate_occurred_at,
)

from core.wiki_generator._aliases import _expand_alias_candidates


class WikiCreateMixin:

    def create_entity_file(
        self,
        entity:    Dict,
        filename:  str,
        chunk_ids: List[str],
        user_role: str = "admin",     # [P4.5-MTS] write 주체 role
    ) -> str:
        """
        [P4.5-MTS] Memory Trust Scoring 연동.
        write 전 신뢰도 검증 → 미달 시 ValueError 발생.
        """
        # ── Memory Trust 검증 ──────────────────────────────
        try:
            from core.memory import verify_before_write
            ok, reason, score = verify_before_write(
                entity    = entity,
                user_role = user_role,
                wiki_dir  = str(self.wiki_base_path),
            )
            if not ok:
                raise ValueError(f"[TRUST] write 거부: {reason}")
            print(f"[TRUST] ✅ {entity.get('name','?')} score={score:.3f}")
        except ImportError:
            pass   # memory_trust.py 없으면 건너뜀 (하위 호환)
        except ValueError:
            raise   # write 거부는 상위로 전파

        entity_type = entity.get("type", "concept")
        name = entity.get("name", "unknown")
        # [Stage E.1, 2026-05-24] strip markdown emphasis tokens that LLM
        # extractors sometimes leave wrapping entity names — `**bold**`,
        # `*italic*`, `` `code` ``, `~~strike~~`. Without this, names like
        # `**경쟁사 대비 AMD 기술적 우위**` flow through to the displayed
        # name, the alias set, and the normalized filename, leaking into
        # graph node labels as `**...**` and into IDs as `___..._`. The
        # strip happens here — entity entry point — so every downstream
        # consumer (`_normalize_name`, alias expansion, frontmatter write,
        # filename build) sees a clean name. Existing stale nodes are
        # handled by a separate backlog-rename script (cross-references
        # to fix). Underscore is intentionally NOT stripped — it's a
        # legitimate name character (`gpt_4`) and `_normalize_name`
        # already collapses non-word punctuation downstream.
        name = re.sub(r"[\*`~]+", "", name).strip() or "unknown"

        # ── Event branch (PR-11b) ─────────────────────────────────
        # `event` requires occurred_at. If the LLM (or any caller)
        # emits `type: event` without a parseable occurred_at, downgrade
        # to `concept` rather than invent a date (memo §5.1: "If you
        # cannot determine the date from the document, emit the entity
        # as `concept` instead — do not invent a date.").
        event_occurred_at  = ""
        event_precision    = "day"
        if entity_type == "event":
            raw_at        = entity.get("occurred_at") or ""
            raw_precision = entity.get("occurred_at_precision") or "day"
            try:
                validate_occurred_at(raw_at, precision=raw_precision)
                event_occurred_at = raw_at
                event_precision   = raw_precision
            except ValueError:
                # Graceful fallback. One bad LLM emit must not refuse the
                # whole ingest — the entity still has informational value
                # as a concept.
                print(
                    f"[INGEST] event entity {name!r} missing/invalid "
                    f"occurred_at — falling back to concept"
                )
                entity_type = "concept"

        normalized = self._normalize_name(name)
        if entity_type == "event":
            # Hash incorporates date + precision so same name on
            # different dates yields distinct entity_ids (memo §12 q2).
            # Helper sits in graph_node_editor — both ingest and admin
            # paths must produce identical ids for the same triple.
            from core.graph_node_editor import _generate_event_entity_id
            entity_id = _generate_event_entity_id(
                name, event_occurred_at, event_precision,
            )
            # Filename suffixed with the 8-hex tail keeps duplicate
            # detection unambiguous AND lets same-name events on
            # different dates coexist on disk.
            path = (
                self.entity_path
                / "event"
                / f"{normalized}_{entity_id[-8:]}.md"
            )
        else:
            entity_id = self._generate_entity_id(name, entity_type)
            path = self.entity_path / entity_type / f"{normalized}.md"

        # aliases — `"X (Y)"` 패턴은 outer/inner도 자동 등록 (Issue #7)
        aliases = _expand_alias_candidates(name)
        short = entity.get("attributes", {}).get("약자")
        if short and short not in aliases:
            aliases.append(short)

        # =========================
        # RELATIONS + Ontology 정규화
        # =========================
        try:
            from core.ontology import (
                normalize_relation, validate_relation,
                infer_relations, get_relation_label
            )
            use_ontology = True
        except ImportError:
            use_ontology = False

        relations = []

        for rel in entity.get("relations", []):
            target_name = rel.get("대상") or rel.get("target")
            target_type = rel.get("유형") or rel.get("target_type") or rel.get("type") or "concept"
            raw_label   = rel.get("라벨") or rel.get("label") or "관련"
            confidence  = float(rel.get("신뢰도", rel.get("confidence", 0.8)))

            # Ontology: relation label 표준화
            if use_ontology:
                std_type = normalize_relation(raw_label)
                validate_relation(entity_type, std_type, strict=False)
                display_label = get_relation_label(std_type)
            else:
                std_type      = raw_label
                display_label = raw_label

            target_id = self._find_existing_entity_id(target_name, target_type)

            # Phase B (Knowledge Cascade): caller 가 미리 채운 sources 가 있으면
            # 보존하고 confidence 를 그로부터 derive 해 storage 와 동기화.
            # 없으면 confidence-only 그대로 두어 Phase A 의 legacy fallback 가
            # 동작하도록 한다. (docs/design/v0.3-knowledge-cascade.md §4)
            new_rel = {
                "target":      target_name,
                "target_id":   target_id or "UNRESOLVED",
                "target_type": target_type,
                "type":        std_type,
                "label":       display_label,
                "confidence":  confidence,
            }
            incoming_sources = rel.get("sources")
            if isinstance(incoming_sources, list) and incoming_sources:
                new_rel["sources"]    = incoming_sources
                new_rel["confidence"] = compute_confidence_from_sources(incoming_sources)
            relations.append(new_rel)

        # Ontology: IS_A 자동 추론 relation 추가
        if use_ontology:
            inferred = infer_relations(name, entity_type)
            for inf_rel in inferred:
                inf_target = inf_rel.get("target", "")
                inf_tid    = self._find_existing_entity_id(inf_target, "concept")
                relations.append({
                    "target":      inf_target,
                    "target_id":   inf_tid or "UNRESOLVED",
                    "target_type": "concept",
                    "type":        inf_rel.get("type", "IS_A"),
                    "label":       inf_rel.get("label", "분류"),
                    "confidence":  inf_rel.get("confidence", 1.0),
                    "inferred":    True,
                })

        attributes = entity.get("attributes", {})
        if not isinstance(attributes, dict):
            attributes = {}

        confidence = min(round(0.7 + 0.3 * len(attributes), 2), 1.0)

        # [B-2-A fix] canonical summary lookup. Caller passes top-level
        # `summary` (preferred — _ingestion.py mirrors it from
        # `attributes.summary`). Fall back through `attributes.summary`
        # and `description` so older callers that haven't been updated
        # still produce a non-empty `## 요약` body section. Cap at 500 to
        # keep the YAML frontmatter line-bounded.
        summary_text = (
            entity.get("summary")
            or attributes.get("summary")
            or entity.get("description")
            or ""
        )[:500]

        # v0.4 Sprint 3 BL-2 — strip the duplicate `summary` key from
        # attributes before frontmatter dump. The canonical value lives
        # at top-level (`summary` field below); `attributes.summary`
        # is a legacy duplicate kept only as a *read* fallback for
        # older wiki files on disk (see lookup above). New writes stop
        # emitting the duplicate so the disk shape converges on one
        # source of truth over time. Legacy files remain readable.
        attributes_for_dump = {
            k: v for k, v in attributes.items() if k != "summary"
        }

        frontmatter = {
            # ── 식별 정보 ──
            "entity_id":       entity_id,
            "entity_type":     entity_type,
            "name":            name,
            "normalized_name": normalized,
            "aliases":         aliases,
            # ── Summary (top-level, canonical) ──
            # Top-level `summary` is the canonical field; `attributes.summary`
            # is the legacy duplicate kept for back-compat. Resync scripts
            # treat top-level as source of truth.
            "summary":         summary_text,
            # ── Event time axis (PR-11b) — only present on events ──
            **(
                {
                    "occurred_at":           event_occurred_at,
                    "occurred_at_precision": event_precision,
                }
                if entity_type == "event"
                else {}
            ),
            # ── ABAC (진단 FAIL 수정: sensitivity/owner 저장 보장) ──
            "sensitivity":     self._default_sensitivity(entity_type),
            "owner":           "system",
            # ── 메타 ──
            "attributes":      attributes_for_dump,
            "created_at":      datetime.now().isoformat(),
            "updated_at":      datetime.now().isoformat(),
            "version":         1,
            "sources":         [filename],
            "trusted":         True,
            # [P4.5-2] source_type: prod / test 구분
            "source_type":     self.source_type,
            "confidence":      confidence,
            "verified":        False,
            "embedding_refs":  chunk_ids,
            # ✅ 핵심 수정: relations를 frontmatter에 포함
            # (_read_frontmatter()가 읽을 수 있도록)
            "relations":       relations,
        }

        # 본문 관계 섹션은 사람이 읽기 쉬운 요약만
        rel_summary = "\n".join([
            f"- {r.get('label','관련')}: {r.get('target','')} "
            f"(conf={r.get('confidence',0):.2f})"
            for r in relations
        ]) or "- (관계 없음)"

        md = (
            "---\n"
            + yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False)
            + "---\n\n"
            f"## 요약\n"
            # [B-2-A fix] reuse the canonical `summary_text` computed
            # above. The old logic only checked top-level `summary` /
            # `description`, which left the body blank when the caller
            # placed the value at `attributes.summary` (the ingest path
            # before B-2-A always did).
            f"{summary_text}\n\n"
            f"## 관계\n{rel_summary}\n"
        )

        path.write_text(md, encoding="utf-8")

        self._register_entity_id(entity_id, path)

        return str(path)


__all__ = ["WikiCreateMixin"]
