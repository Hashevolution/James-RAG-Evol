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
from core.gemma_client import GemmaClient   # type/fallback retained
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

        self.entity_types = ["person", "concept", "org", "document"]

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
            "## document (0)\n"
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
            from core.memory_trust import verify_before_write
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

        normalized = self._normalize_name(name)
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

            relations.append({
                "target":      target_name,
                "target_id":   target_id or "UNRESOLVED",
                "target_type": target_type,
                "type":        std_type,
                "label":       display_label,
                "confidence":  confidence,
            })

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
    # RESOLVE (SAFE YAML 방식)
    # =========================

    def resolve_pending_relations(self):

        resolved = 0

        for t in self.entity_types:
            d = self.entity_path / t
            if not d.exists():
                continue

            for f in d.glob("*.md"):

                content = f.read_text(encoding="utf-8")

                if "UNRESOLVED" not in content:
                    continue

                end = content.find("---", 3)
                fm = yaml.safe_load(content[3:end])
                body = content[end+4:]

                try:
                    parts = body.split("## 관계")
                    if len(parts) < 2:
                        continue

                    rel_yaml = parts[1]
                    relations = yaml.safe_load(rel_yaml)

                    changed = False

                    for r in relations:
                        if r.get("target_id") == "UNRESOLVED":

                            found = self._find_existing_entity_id(
                                r["target"],
                                r["target_type"]
                            )

                            if not found:
                                found = self._find_existing_entity_id(r["target"], None)

                            if found:
                                r["target_id"] = found
                                changed = True

                    if changed:
                        new_body = "## 관계\n" + yaml.dump(relations, allow_unicode=True)

                        new_content = (
                            "---\n"
                            + yaml.dump(fm, allow_unicode=True)
                            + "---\n\n"
                            + parts[0]
                            + new_body
                        )

                        f.write_text(new_content, encoding="utf-8")
                        resolved += 1

                except Exception as e:
                    print("[RESOLVE ERROR]", e)

        print(f"[RESOLVE] {resolved} fixed")
        return resolved

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
    ) -> List[str]:
        """
        문서 본문에서 LLM으로 인물/조직/개념 entity와 relation을 추출하여
        각 entity별 .md를 생성하고, 추가로 원본을 document entity로도 보존한다.

        Returns:
            생성된 entity_id 리스트 (실패 시 빈 리스트 또는 document만)
        """
        metadata  = metadata or {}
        extracted = self._llm_extract_document_entities(filename, content, metadata)

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
                print(f"[ENTITY-EXTRACT] '{name}' ({etype}) already exists -> skip")
                name_to_id[name]   = existing_id
                name_to_type[name] = etype
                continue

            ent_relations = self._build_entity_relations(
                name, extracted.get("relations", [])
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

        # document entity (원본 보존 + 모든 추출 entity와 RELATED_TO)
        doc_name = os.path.splitext(filename)[0]
        doc_relations = [
            {
                "target":      n,
                "target_type": name_to_type.get(n, "concept"),
                "label":       "관련",
                "confidence":  0.7,
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

        prompt = (
            "You must output ONLY a JSON object. "
            "No explanation, no thinking, no markdown. Just raw JSON.\n\n"
            "Output format:\n"
            '{"entities": [{"name": "X", "type": "person|org|concept", "description": "한줄설명"}], '
            '"relations": [{"source": "X", "target": "Y", "label": "관련", "confidence": 0.7}]}\n\n'
            f"Allowed relation labels (Korean only): {_ONTOLOGY_LABELS_KO}\n"
            "Max 6 entities and 6 relations. "
            "Extract only entities EXPLICITLY named in the document below. No inference.\n\n"
            "Document:\n"
            + text
            + "\n\nJSON:"
        )
        try:
            from llm.router import call_router
            response = call_router(prompt, task_type="extract", use_cache=False)
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

    def _build_entity_relations(
        self,
        source_name:   str,
        raw_relations: List,
    ) -> List[Dict]:
        """이 entity가 source 또는 target인 relation을 표준 형식으로 모은다.

        Issue #11: 이전 구현은 source==self만 골라서 target 입장 entity의
        relations 필드가 빈 채로 끝났다. graph_paths가 비어 expand가 항상
        0을 반환했다. 이제 양방향으로 부착한다 (incoming은 inverse label).
        """
        out: List[Dict] = []
        seen: set = set()
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
                    out.append({"target": tgt, "label": label, "confidence": conf})
            # Incoming: target이 self → source를 inverse label로 추가
            elif tgt == source_name and src and len(src) <= 80 \
                    and _SAFE_ENTITY_NAME_RE.match(src):
                inv_label = self._inverse_label_for(label)
                key = (src, inv_label)
                if key not in seen:
                    seen.add(key)
                    out.append({"target": src, "label": inv_label, "confidence": conf})
        return out