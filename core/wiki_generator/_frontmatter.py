"""Wiki generator — frontmatter, indexing, single-entity write path.

Holds the ``WikiFrontmatterMixin`` (Layers 0–2 in the dependency
graph): instance state via ``__init__``, the entity-id index build,
ID generation, name normalization, frontmatter read, duplicate
detection, single-file ``create_entity_file`` writer, the
``update_index`` summary, ``resolve_pending_relations`` UNRESOLVED
sweep, and ``get_entity_statistics``.

The ``WIKI_DIR`` binding is late-imported from ``core.wiki_generator``
inside ``__init__`` so the test pattern
``import core.wiki_generator as wg_mod; wg_mod.WIKI_DIR = tmp``
keeps working after the Stage C.1 split.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from core.relations_schema import (
    ENTITY_TYPES_CORE,
    compute_confidence_from_sources,
    validate_occurred_at,
)
from core.vector_store import VectorStore
from llm.router import RouterWrapper
from utils.metadata import MetadataGenerator

from ._aliases import _expand_alias_candidates


class WikiFrontmatterMixin:

    def __init__(self, source_type: str = "prod"):
        """
        [P4.5-1] source_type 분리
          source_type='prod' → wiki/entity/prod/{type}/
          source_type='test' → wiki/entity/test/{type}/
        """
        # Late-bind WIKI_DIR: tests do ``wg_mod.WIKI_DIR = tmp`` between
        # instantiations, so reading the binding at __init__ time
        # (rather than at module import) is the load-bearing invariant.
        from core.wiki_generator import WIKI_DIR

        self.gemma_client = RouterWrapper("extract")
        self.metadata_gen = MetadataGenerator()
        self.vector_store = VectorStore()

        # [P4.5-1] source_type에 따라 entity 경로 분리
        self.source_type    = source_type if source_type in ("prod", "test") else "prod"
        self.wiki_base_path = Path(WIKI_DIR)
        self.entity_path    = self.wiki_base_path / "entity" / self.source_type

        # ENTITY_TYPES_CORE = 5 types (event 5th, PR-11). LLM extraction
        # prompt below still emits only 3 types (person/org/concept);
        # `document` is post-processor source-attribution; `event` is
        # admin POST path (PR-11a-2). Directory listing / index build /
        # search default to all 5 — empty event/ dir is a no-op until
        # the first admin event creation.
        self.entity_types = list(ENTITY_TYPES_CORE)

        for t in self.entity_types:
            (self.entity_path / t).mkdir(parents=True, exist_ok=True)

        self.index_path = self.wiki_base_path / "index.md"
        if not self.index_path.exists():
            self._create_index_template()

        self.entity_id_index: Dict[str, Path] = {}
        self._build_entity_id_index()


    def _create_index_template(self):
        """index.md 초기 템플릿 생성"""

        content = (
            "---\n"
            f'updated_at: "{datetime.now().isoformat()}"\n'
            "total_entities: 0\n"
            "---\n\n"
            "# 자메스 Wiki Index\n\n"
            "## person (0)\n\n"
            "## concept (0)\n\n"
            "## org (0)\n\n"
            "## document (0)\n\n"
            "## event (0)\n"
        )

        self.index_path.write_text(content, encoding="utf-8")

    # =========================
    # INDEX BUILD
    # =========================

    def _build_entity_id_index(self):
        self.entity_id_index.clear()

        for t in self.entity_types:
            d = self.entity_path / t
            if not d.exists():
                continue

            for f in d.glob("*.md"):
                fm = self._read_frontmatter(f)
                if fm and fm.get("entity_id"):
                    self.entity_id_index[fm["entity_id"]] = f

        print(f"[INDEX] {len(self.entity_id_index)} entities loaded")

    def refresh_entity_map(self):
        self._build_entity_id_index()

    def _register_entity_id(self, entity_id: str, filepath: Path):
        self.entity_id_index[entity_id] = filepath

    # =========================
    # ID GENERATION (SECURE)
    # =========================

    def _generate_entity_id(self, name: str, entity_type: str) -> str:
        normalized = self._normalize_name(name)

        # 🔐 보안: SALT 추가
        SALT = "JAMES_SECURE_V1"
        raw = f"{normalized}_{entity_type}_{SALT}"

        h = hashlib.sha256(raw.encode()).hexdigest()[:8]   # graph_rag_engine 정규식 {8} 일치
        return f"e_{entity_type}_{h}"

    def _normalize_name(self, name: str) -> str:
        return re.sub(r"[^\w가-힣]", "_", name.strip().lower())

    def _build_overlap_snapshot(self):
        """Return `{normalized_name: (canonical_name, entity_id, entity_type)}`
        for every existing wiki entity (any type), aliases included.

        v0.4 Sprint 1 #1 addition — used by ingestion's entity-name
        overlap detection (`_infer_overlap_relations` in `_merge.py`)
        so a newly-ingested event named *"비트코인 spot ETF 11개
        일괄 승인"* automatically gets a RELATED_TO relation to the
        existing "비트코인" concept entity when its normalized name
        appears as a token in the new entity's name.

        First-write-wins: if two entities share a normalized name
        (e.g. one canonical + one alias on a different entity), the
        earlier one in `entity_id_index` iteration order takes
        precedence. Tests pin this — production rarely has the
        collision because aliases that match another canonical name
        would already trip `_find_existing_entity_id` during ingest.
        """
        from pathlib import Path
        snapshot = {}
        for eid, filepath in self.entity_id_index.items():
            try:
                fm = self._read_frontmatter(Path(filepath))
            except Exception:
                continue
            if not fm:
                continue
            canonical = fm.get("name", "")
            norm = fm.get("normalized_name", "") or self._normalize_name(canonical)
            etype = fm.get("entity_type", "concept")
            if norm and norm not in snapshot:
                snapshot[norm] = (canonical, eid, etype)
            for alias in fm.get("aliases", []) or []:
                alias_norm = self._normalize_name(alias)
                if alias_norm and alias_norm not in snapshot:
                    snapshot[alias_norm] = (canonical, eid, etype)
        return snapshot

    # =========================
    # ENTITY SEARCH (FIXED)
    # =========================

    def _find_existing_entity_id(
        self,
        name: str,
        entity_type: Optional[str]
    ) -> Optional[str]:

        normalized = self._normalize_name(name)

        # 🔥 핵심 FIX: None 대응
        if entity_type:
            search_types = [entity_type]
        else:
            search_types = self.entity_types

        for t in search_types:
            d = self.entity_path / t
            if not d.exists():
                continue

            for f in d.glob("*.md"):
                fm = self._read_frontmatter(f)
                if not fm:
                    continue

                if fm.get("normalized_name") == normalized:
                    return fm.get("entity_id")

                for alias in fm.get("aliases", []):
                    if self._normalize_name(alias) == normalized:
                        return fm.get("entity_id")

        return None

    # =========================
    # FRONTMATTER
    # =========================

    def _read_frontmatter(self, path: Path) -> Optional[Dict]:
        try:
            content = path.read_text(encoding="utf-8")
            if not content.startswith("---"):
                return None

            end = content.find("---", 3)
            if end < 0:
                return None

            return yaml.safe_load(content[3:end]) or {}
        except Exception:
            return None

    # =========================
    # CREATE ENTITY
    # =========================

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
            "attributes":      attributes,
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

    # =========================
    # SENSITIVITY DEFAULT (ABAC)
    # =========================

    @staticmethod
    def _default_sensitivity(entity_type: str) -> str:
        """entity_type별 기본 민감도 등급 반환"""
        mapping = {
            "person":   "confidential",  # 개인정보 → 기밀
            "org":      "internal",      # 조직정보 → 내부
            "document": "confidential",  # 문서 → 기밀
            "concept":  "public",        # 개념/지식 → 공개
            "event":    "internal",      # 시간 축 사건 → 내부 (PR-11b)
        }
        return mapping.get(entity_type, "internal")

    # =========================
    # DUPLICATE CHECK
    # =========================

    def find_duplicate_entities(self, entity: Dict) -> Optional[str]:

        name = entity.get("name", "")
        normalized = self._normalize_name(name)

        t = entity.get("type", "concept")
        d = self.entity_path / t

        if not d.exists():
            return None

        for f in d.glob("*.md"):
            fm = self._read_frontmatter(f)
            if not fm:
                continue

            if fm.get("normalized_name") == normalized:
                return str(f)

        return None

__all__ = ["WikiFrontmatterMixin"]
