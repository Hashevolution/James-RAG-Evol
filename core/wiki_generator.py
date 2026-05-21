# =========================
# PROJECT JAMES - FINAL STABLE WikiGenerator
# =========================

import os
import json
import yaml
import hashlib
import re
from datetime import datetime
from typing import Dict, List, Any, Optional
from pathlib import Path

from config import WIKI_DIR
from core.relations_schema import (
    ENTITY_TYPES_CORE,
    EXTRACT_SOURCE_ROLE,
    INVERSE_SOURCE_ROLE,
    compute_confidence_from_sources,
    validate_occurred_at,
)
from core.vector_store import VectorStore
from llm.router import RouterWrapper
from utils.metadata import MetadataGenerator


_SAFE_ENTITY_NAME_RE = re.compile(r'^[A-Za-z0-9가-힣\s\-_,()&·\.]{2,80}$')
_ALLOWED_EXTRACT_TYPES = frozenset(("person", "org", "concept"))
_ONTOLOGY_LABELS_KO = "공부, 연구, 가르침, 소속, 근무, 분류, 구성, 관련, 생산, 산업, 분야, 설립됨"

# 괄호 패턴 — 반각/전각 모두 처리. e.g. "RAG (검색 증강 생성)" / "RAG（검색 증강 생성）"
_PAREN_ALIAS_RE = re.compile(r'^(.+?)\s*[\(（](.+?)[\)）]\s*$')

# wiki/synonyms.yaml 한 번 로드해서 캐시. (Issue #3)
# {surface_form_lower: [other_form1, other_form2, ...]} 양방향.
_SYNONYM_INDEX: Dict[str, List[str]] | None = None


def _load_synonyms() -> Dict[str, List[str]]:
    """wiki/synonyms.yaml에서 synonym 그룹 로드 → 양방향 lookup index 빌드.

    yaml 형식:
      - canonical: 비트코인
        aliases: [BTC, Bitcoin]

    반환: ``{lowercase_form → [같은 그룹의 다른 form들]}``
    """
    global _SYNONYM_INDEX
    if _SYNONYM_INDEX is not None:
        return _SYNONYM_INDEX

    index: Dict[str, List[str]] = {}
    syn_path = Path(WIKI_DIR) / "synonyms.yaml"
    if not syn_path.exists():
        _SYNONYM_INDEX = index
        return index

    try:
        groups = yaml.safe_load(syn_path.read_text(encoding="utf-8")) or []
        if not isinstance(groups, list):
            _SYNONYM_INDEX = index
            return index
        for g in groups:
            if not isinstance(g, dict):
                continue
            canonical = (g.get("canonical") or "").strip()
            aliases   = g.get("aliases") or []
            if not canonical or not isinstance(aliases, list):
                continue
            forms = [canonical] + [str(a).strip() for a in aliases if a]
            forms = [f for f in forms if f]
            for f in forms:
                others = [x for x in forms if x != f]
                if others:
                    index.setdefault(f.lower(), []).extend(others)
    except Exception as e:
        print(f"[SYNONYMS] load failed: {e}")

    _SYNONYM_INDEX = index
    return index


def _expand_alias_candidates(name: str) -> List[str]:
    """이름에서 alias 후보를 자동 추출.

    - 괄호 패턴 ``"X (Y)"`` → ``["X (Y)", "X", "Y"]``
    - synonym 매핑 (wiki/synonyms.yaml) → 같은 그룹의 다른 form 모두 추가
    - 그 외에는 ``[name]`` 만 반환

    LLM이 풍부한 이름(`"RAG (검색 증강 생성)"`)으로 entity를 만들고,
    질의 시점엔 짧은 형태(`"RAG"`)로 entity를 추출하기 때문에 매칭 갭을
    메우려면 양쪽 형태를 모두 alias로 등록해야 한다.
    """
    if not isinstance(name, str):
        return []
    name = name.strip()
    if not name:
        return []
    out: List[str] = [name]
    m = _PAREN_ALIAS_RE.match(name)
    if m:
        for part in (m.group(1).strip(), m.group(2).strip()):
            if part and part not in out and len(part) >= 2:
                out.append(part)

    # synonym 매핑 (Issue #3)
    syn_index = _load_synonyms()
    # name 본체와 (괄호 분리된) 짧은 form 모두 lookup
    for candidate in list(out):
        for other in syn_index.get(candidate.lower(), []):
            if other not in out:
                out.append(other)

    return out


class WikiGenerator:

    def __init__(self, source_type: str = "prod"):
        """
        [P4.5-1] source_type 분리
          source_type='prod' → wiki/entity/prod/{type}/
          source_type='test' → wiki/entity/test/{type}/
        """
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
        except:
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

        frontmatter = {
            # ── 식별 정보 ──
            "entity_id":       entity_id,
            "entity_type":     entity_type,
            "name":            name,
            "normalized_name": normalized,
            "aliases":         aliases,
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
            # [U-1] summary 우선, 없으면 description
            f"{entity.get('summary', '') or entity.get('description', '')}\n\n"
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

    # =========================
    # INDEX
    # =========================

    def update_index(self):

        total = 0
        lines = ["# INDEX\n"]

        for t in self.entity_types:
            d = self.entity_path / t
            count = len(list(d.glob("*.md"))) if d.exists() else 0
            total += count

            lines.append(f"\n## {t} ({count})")

        self.index_path.write_text("\n".join(lines), encoding="utf-8")

    # =========================
    # RESOLVE — frontmatter `relations:` 의 UNRESOLVED 재매칭
    # =========================

    def resolve_pending_relations(self) -> int:
        """
        frontmatter `relations:` 키의 `target_id == "UNRESOLVED"` 항목을
        현재 entity 인덱스로 재매칭하여 채워준다.

        Why frontmatter only:
          create_entity_file 이 권위로 사용하는 위치는 frontmatter
          `relations:` 키이다. body 의 `## 관계` 섹션은 사람-읽기용
          미러(예: `- 관련: FAA (conf=0.90)`)일 뿐 entity_id 를 노출하지
          않으므로 매칭과 무관 — 그대로 둔다.

        Why call this:
          create_entity_file 시점에 target entity 가 아직 ingest 되지
          않았으면 UNRESOLVED 로 남는다 (다른 PDF 가 늦게 들어오거나,
          같은 PDF 의 다른 entity 가 뒤에서 만들어지는 케이스). 본
          메서드를 entity_map refresh 직후 호출하면 그 시점까지 알려진
          모든 entity 와 매칭이 완성된다.

        Returns:
            갱신된 relation 항목의 누적 개수.
        """
        files_changed = 0
        relations_fixed = 0

        for t in self.entity_types:
            d = self.entity_path / t
            if not d.exists():
                continue

            for f in d.glob("*.md"):
                content = f.read_text(encoding="utf-8")
                if not content.startswith("---"):
                    continue
                end = content.find("---", 3)
                if end < 0:
                    continue

                try:
                    fm = yaml.safe_load(content[3:end]) or {}
                except Exception as e:
                    print(f"[RESOLVE] YAML parse fail {f.name}: {e}")
                    continue

                body_tail = content[end + 3:]
                relations = fm.get("relations")
                if not isinstance(relations, list) or not relations:
                    continue

                file_changed = False
                for r in relations:
                    if not isinstance(r, dict):
                        continue
                    if r.get("target_id") != "UNRESOLVED":
                        continue
                    target = (r.get("target") or "").strip()
                    if not target:
                        continue
                    ttype = r.get("target_type")
                    # 정확 target_type 매칭 → 전체 타입 fallback
                    found = (
                        self._find_existing_entity_id(target, ttype)
                        or self._find_existing_entity_id(target, None)
                    )
                    if found:
                        r["target_id"] = found
                        file_changed = True
                        relations_fixed += 1

                if file_changed:
                    new_content = (
                        "---\n"
                        + yaml.dump(
                            fm,
                            allow_unicode    = True,
                            default_flow_style = False,
                            sort_keys        = True,
                        )
                        + "---"
                        + body_tail
                    )
                    f.write_text(new_content, encoding="utf-8")
                    files_changed += 1

        print(f"[RESOLVE] {files_changed} files updated, "
              f"{relations_fixed} relations resolved")
        return relations_fixed

    # =========================
    # STATS
    # =========================

    def get_entity_statistics(self):
        stats = {}
        total = 0

        for t in self.entity_types:
            d = self.entity_path / t
            c = len(list(d.glob("*.md"))) if d.exists() else 0
            stats[t] = c
            total += c

        stats["total"] = total
        return stats

    # =========================
    # DOCUMENT → ENTITY EXTRACTION (LLM-based, P7)
    # =========================

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
            payload = {
                "name":        name,
                "type":        etype,
                "attributes":  {
                    "summary":          (ent.get("description") or "")[:300],
                    "source_document":  filename,
                },
                "relations":   ent_relations,
                "sensitivity": "internal",
                "source_type": self.source_type,
            }
            try:
                self.create_entity_file(payload, filename, chunk_ids, user_role=user_role)
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
        doc_payload = {
            "name":        doc_name,
            "type":        "document",
            "attributes":  {
                "summary":   (metadata.get("summary") or "")[:500],
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
            # max_tokens=1500: original prompt was short and default 0 (unlimited)
            # was fine; the longer enriched prompt above pushed total context high
            # enough that the model began truncating its JSON response (~700 chars
            # in). Explicit budget keeps a complete 6-entity / 6-relation JSON in.
            response = call_router(
                prompt, task_type="extract", use_cache=False, max_tokens=1500,
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
        if not isinstance(ents, list): ents = []
        if not isinstance(rels, list): rels = []
        return {"entities": ents, "relations": rels}

    @staticmethod
    def _is_safe_extracted_entity(ent: Any) -> bool:
        """Schema + 보안 검증. injection-safe + 길이/타입 화이트리스트."""
        if not isinstance(ent, dict): return False
        name = ent.get("name", "")
        if not isinstance(name, str): return False
        name = name.strip()
        if len(name) < 2 or len(name) > 80: return False
        if not _SAFE_ENTITY_NAME_RE.match(name): return False
        if ent.get("type") not in _ALLOWED_EXTRACT_TYPES: return False
        return True

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