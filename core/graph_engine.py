"""
PROJECT JAMES - Graph Engine (Phase 4.5)
[REFACTOR] graph_rag_engine.py 분리 — DFS + Graph 책임 전담

책임:
  - DFS 탐색 (expand_graph_dynamic)
  - Node ranking (weight-based)
  - Entity map snapshot
  - Entity loading / matching
  - Graph integrity validation
  - Reasoning path verification
  - Ontology strict enforcement

호출 관계:
  reasoning_engine.py → GraphEngine
  retrieval_engine.py → GraphEngine (entity match)
"""

import re
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from core.wiki_generator import WikiGenerator
from core.ontology import (
    normalize_relation,
    get_ancestors,
    get_relation_weight,
    is_sensitive_relation,
    compute_graph_score,
    is_valid_relation_triple,
    RELATION_TYPES,
)

SYSTEM_LOG_PATH      = "james_system_log.jsonl"
CONFIDENCE_THRESHOLD = 0.6
MAX_DEPTH            = 4
DFS_SCORE_THRESHOLD  = 0.05
DEPTH_DECAY          = 0.7


def _doc_outgoing_hop_valid(source_entity: dict, target_entity: dict) -> bool:
    """[#A5-D, 2026-05-09] Document → entity hop validity gate.

    Background — Palantir → 비트코인 spurious path
    -----------------------------------------------
    The wiki_generator emits two kinds of relations on a document
    entity's `relations` list:
      (a) the document's PRIMARY entity (the one whose `sources:` list
          contains this document) — the doc IS about this entity;
      (b) entities merely MENTIONED in the document — these get a
          `RELATED_TO` edge with conf 0.7 but the document is NOT a
          source for them.
    Old DFS treated both kinds the same and freely traversed (a) and
    (b) outbound from a document. This produced cross-domain false
    paths like:

        Palantir → PLTR_03(doc) → Morgan Stanley → MSBT → 비트코인

    The PLTR_03 → Morgan Stanley hop is type-(b): PLTR_03 mentions
    Morgan Stanley but is NOT a Morgan Stanley source document
    (Morgan Stanley's sources field lists only `09_MorganStanley_*`).

    Rule
    ----
    From a document, only follow outgoing edges where the target
    entity has THIS document in its `sources` field. Type-(a) hops
    pass; type-(b) hops are blocked. The rule does not apply when
    the source entity is non-document — entity → entity inferred
    edges (the bulk of the graph backbone, 78% at conf 0.7) are
    untouched, avoiding the over-cut that broke option 1's bench.

    Source vs target asymmetry
    --------------------------
    `entity.sources` carries filenames with extension (e.g.
    `PLTR_03_밸류에이션_리스크_분석.pdf`); document entity's `name`
    is the stem (`PLTR_03_밸류에이션_리스크_분석`). Match by stem
    contained in any source filename.
    """
    if not source_entity or source_entity.get("entity_type") != "document":
        return True   # rule only applies when source is a document

    if not target_entity:
        return True   # missing data — be permissive (other gates apply)

    src_name = (source_entity.get("name") or "").strip()
    if not src_name:
        return True

    target_sources = target_entity.get("sources") or []
    if not isinstance(target_sources, list):
        return True   # malformed — let other gates handle

    for s in target_sources:
        if not isinstance(s, str):
            continue
        # Match by stem (PLTR_03_…)  in source filename (PLTR_03_….pdf).
        if src_name in s:
            return True

    return False


class GraphEngine:
    """
    DFS 기반 Graph 탐색 + Ontology 검증 전담 엔진.
    reasoning_engine.py 의 loop 내에서 호출된다.
    """

    def __init__(self):
        self.wiki_generator = WikiGenerator()
        self._map_lock      = threading.Lock()

    # ─── 로그 ───────────────────────────────────────────────

    @staticmethod
    def _log(step: str, error: Exception, role: str = "system"):
        entry = {
            "time":   datetime.now().isoformat(),
            "level":  "ERROR",
            "step":   f"graph_engine.{step}",
            "detail": str(error)[:300],
            "role":   role,
        }
        try:
            with open(SYSTEM_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    # ─── Entity Map Snapshot ─────────────────────────────────

    def build_entity_map_snapshot(self) -> Dict[Tuple[str, str], str]:
        """정규화된 (entity_type, normalized_name) → entity_id 매핑"""
        snapshot: Dict[Tuple[str, str], str] = {}
        for eid, filepath in self.wiki_generator.entity_id_index.items():
            try:
                fm = self.wiki_generator._read_frontmatter(Path(filepath))
                if not fm:
                    continue
                e_type = fm.get("entity_type", "concept")
                norm   = fm.get("normalized_name", "")
                if e_type and norm:
                    snapshot[(e_type, norm)] = eid
                    for alias in fm.get("aliases", []):
                        an = self.wiki_generator._normalize_name(alias)
                        if an and (e_type, an) not in snapshot:
                            snapshot[(e_type, an)] = eid
            except Exception as e:
                self._log("entity_map_build", e)
        return snapshot

    def match_entities(
        self,
        entities: List[Dict],
        snapshot: Optional[Dict] = None,
    ) -> List[str]:
        """추출된 entity 목록 → wiki entity_id 목록으로 변환"""
        if snapshot is None:
            with self._map_lock:
                snapshot = self.build_entity_map_snapshot()

        entity_ids, seen = [], set()
        for e in entities:
            if not isinstance(e, dict):
                continue
            name  = e.get("name", "")
            etype = e.get("type", "concept")
            if not name or "/" in name or ".." in name or len(name) > 100:
                continue
            norm = self.wiki_generator._normalize_name(name)
            eid  = snapshot.get((etype, norm))
            if not eid:
                for t in ["person", "org", "concept", "document"]:
                    eid = snapshot.get((t, norm))
                    if eid:
                        break
            if eid and eid not in seen:
                seen.add(eid)
                entity_ids.append(eid)
        return entity_ids

    # ─── Entity 로딩 ─────────────────────────────────────────

    def load_entity(self, entity_id: str) -> Dict:
        if not entity_id or not isinstance(entity_id, str):
            return {}
        filepath = self.wiki_generator.entity_id_index.get(entity_id)
        if not filepath:
            return {}
        return self.wiki_generator._read_frontmatter(Path(filepath)) or {}

    # ─── 무결성 검사 ─────────────────────────────────────────

    def validate_integrity(self, entity_ids: List[str]) -> List[str]:
        """
        DFS 진입 전 entity_id 사전 검증.
        - ID 형식 (e_{type}_{8~10 hex})
        - 실제 로드 가능 여부
        - relation key 혼재 경고
        """
        valid, invalid = [], []
        for eid in entity_ids:
            if not eid or not isinstance(eid, str):
                invalid.append(f"None: {eid}")
                continue
            if not re.match(r"^e_[a-z]+_[a-f0-9]{8,10}$", eid):
                invalid.append(f"형식 오류: {eid}")
                continue
            entity = self.load_entity(eid)
            if not entity:
                invalid.append(f"로드 실패: {eid}")
                continue
            for rel in entity.get("relations", []):
                if not isinstance(rel, dict):
                    continue
                has_type  = "type"  in rel
                has_label = "label" in rel
                if has_type and has_label:
                    print(f"[INTEG] type/label 동시 존재: {eid}")
                elif not has_type and not has_label:
                    print(f"[INTEG] type/label 모두 없음: {eid}")
            valid.append(eid)

        if invalid:
            self._log("integrity", Exception(f"{invalid[:3]}"))
        print(f"[INTEG] {len(valid)}/{len(entity_ids)} 유효")
        return valid

    # ─── Relation 접근자 ─────────────────────────────────────

    @staticmethod
    def get_rel_type(rel: dict) -> str:
        """label/type 혼재 → normalize_relation으로 표준화"""
        raw = rel.get("type") or rel.get("label") or "RELATED_TO"
        return normalize_relation(raw)

    # ─── [P4.5-3] Ontology Strict Enforcement ────────────────

    @staticmethod
    def check_strict_relation(
        rel_type: str,
        head_entity: dict,
        tail_entity: dict,
    ) -> bool:
        """
        [P4.5-3] Strict 모드: 미등록 relation → DFS 차단.
        is_valid_relation_triple() + RELATION_TYPES 존재 여부 이중 검증.

        [BUG-FIX] normalize_relation()이 미등록 relation을 RELATED_TO로
        변환하는 fallback 때문에 미등록 relation이 차단되지 않던 문제 수정.
        → normalize 전에 원본이 등록됐는지 먼저 확인.
        """
        from core.ontology import LABEL_TO_TYPE

        # [BUG-FIX] normalize 전에 원본 등록 여부 먼저 확인
        # normalize가 미등록 → RELATED_TO 변환하면 항상 통과해버리는 문제 방지
        if rel_type not in RELATION_TYPES and rel_type not in LABEL_TO_TYPE:
            print(f"[STRICT] 미등록 relation '{rel_type}' → DFS 차단")
            return False

        std_type = normalize_relation(rel_type)

        # 이중 확인: normalize 후에도 미등록이면 차단
        if std_type not in RELATION_TYPES:
            print(f"[STRICT] normalize 후 미등록 '{std_type}' → DFS 차단")
            return False

        # head/tail 타입 제약 확인 (strict=True)
        if head_entity and tail_entity:
            if not is_valid_relation_triple(head_entity, std_type, tail_entity, strict=True):
                return False

        return True

    # ─── Dynamic DFS ─────────────────────────────────────────

    def expand_dynamic(
        self,
        entity_ids: List[str],
        source_type_filter: Optional[str] = None,  # [P4.5-1] prod/test 필터
    ) -> Tuple[List[Dict], List[str]]:
        """
        [P4-DFS-1] Adaptive DFS with ACT Halting.
        [P4.5-3]   Ontology strict enforcement 통합

        Args:
            entity_ids:          탐색 시작 entity_id 목록
            source_type_filter:  'prod' / 'test' / None (전체)

        Returns:
            (entities_with_depth_score, reasoning_paths)
        """
        visited, entities, paths = set(), [], []

        def dfs(eid: str, d: int, path_so_far: str, parent_score: float):
            if d > MAX_DEPTH or eid in visited or not eid:
                return
            visited.add(eid)

            entity = self.load_entity(eid)
            if not entity:
                return

            # [P4.5-1] source_type 필터
            if source_type_filter:
                entity_src = entity.get("source_type", "prod")
                if entity_src != source_type_filter:
                    return

            relations    = entity.get("relations", [])
            base_score   = compute_graph_score(relations, depth=max(d, 1))
            decayed_score = base_score * (DEPTH_DECAY ** d)

            # ACT Halting
            if d > 0 and decayed_score < DFS_SCORE_THRESHOLD:
                print(f"[DFS-HALT] {entity.get('name','?')} depth={d} score={decayed_score:.4f} → 중단")
                return

            entities.append({**entity, "_dfs_depth": d, "_dfs_score": round(decayed_score, 4)})
            if path_so_far:
                paths.append(path_so_far)

            for rel in relations:
                if not isinstance(rel, dict):
                    continue
                if float(rel.get("confidence", 0)) < CONFIDENCE_THRESHOLD:
                    continue

                std_type = self.get_rel_type(rel)

                # [P3.5-A] sensitive relation 차단
                if is_sensitive_relation(std_type):
                    print(f"[SECURITY] sensitive 차단: {std_type}")
                    continue

                target_id = rel.get("target_id", "")
                if not target_id or target_id in ("UNRESOLVED", eid):
                    continue
                if target_id.startswith("pending"):
                    continue
                if not re.match(r"^e_[a-z]+_[a-f0-9]{8,10}$", target_id):
                    continue

                target_entity = self.load_entity(target_id)

                # [#A5-D] doc→entity gate — see _doc_outgoing_hop_valid.
                # Blocks type-(b) tangential mentions (PLTR_03 → Morgan
                # Stanley) without touching entity→entity edges.
                if not _doc_outgoing_hop_valid(entity, target_entity):
                    print(f"[A5D] doc-tangential hop 차단: "
                          f"{entity.get('name','?')} → "
                          f"{rel.get('target','?')}")
                    continue

                # [P4.5-3] Ontology strict enforcement
                if not self.check_strict_relation(std_type, entity, target_entity or {}):
                    continue

                target_name = rel.get("target", target_id)
                source_name = entity.get("name", eid)
                w           = get_relation_weight(std_type)
                next_path   = (
                    f"{path_so_far} -[{std_type}(w={w:.1f})]→ {target_name}"
                    if path_so_far
                    else f"{source_name} -[{std_type}(w={w:.1f})]→ {target_name}"
                )
                dfs(target_id, d + 1, next_path, decayed_score)

        for eid in entity_ids:
            dfs(eid, 0, "", 1.0)

        print(f"[DFS] 완료: {len(entities)}개 node | {len(paths)}개 경로")
        return entities, paths

    # ─── Ranking ─────────────────────────────────────────────

    @staticmethod
    def rank_nodes(graph_context: List[Dict]) -> List[Dict]:
        """score = compute_graph_score × depth_decay"""
        def node_score(e: Dict) -> float:
            d = max(e.get("_dfs_depth", 0), 0)
            return compute_graph_score(e.get("relations", []), depth=d + 1) * (DEPTH_DECAY ** d)

        ranked = sorted(graph_context, key=node_score, reverse=True)
        for e in ranked[:3]:
            print(f"  [RANK] {e.get('name','?')} depth={e.get('_dfs_depth',0)} score={node_score(e):.4f}")
        return ranked

    # ─── 추론 검증 ───────────────────────────────────────────

    @staticmethod
    def verify_reasoning(graph_paths: List[str]) -> List[str]:
        """
        [P4-VER-1] 추론 경로 검증.
        - sensitive relation 포함 경로 제거
        - 루프 감지 및 제거
        """
        if not graph_paths:
            return []
        sensitive_kws = ["HAS_SECRET", "KNOWS_PASSWORD", "HAS_CREDENTIAL", "OWNS_PRIVATE"]
        verified = []
        for path in graph_paths:
            if "→" not in path:
                continue
            if any(kw in path for kw in sensitive_kws):
                print(f"[VER-1] sensitive 경로 제거: {path[:60]}")
                continue
            nodes      = re.findall(r"^([^-]+)|→\s*([^\-\[]+?)(?:\s*-\[|\s*$)", path)
            node_names = [n[0].strip() or n[1].strip() for n in nodes if n[0].strip() or n[1].strip()]
            if len(node_names) != len(set(node_names)):
                print(f"[VER-1] 루프 감지 — 제거: {path[:60]}")
                continue
            verified.append(path)
        if len(verified) < len(graph_paths):
            print(f"[VER-1] {len(verified)}/{len(graph_paths)} 통과")
        return verified

    # ─── Context 구성 ────────────────────────────────────────

    def build_graph_context_str(
        self,
        graph_entities: List[Dict],
        graph_paths: List[str],
        unified_score: float = 0.0,
    ) -> str:
        """Graph entity + 추론 경로를 LLM용 컨텍스트 문자열로 변환"""
        lines = []
        for e in graph_entities[:10]:
            if not isinstance(e, dict):
                continue
            name  = e.get("name", "Unknown")
            etype = e.get("entity_type", "concept")
            line  = f"[Entity] {name} ({etype}, depth={e.get('_dfs_depth',0)}, score={e.get('_dfs_score',0):.3f})"

            attrs = e.get("attributes", {})
            if isinstance(attrs, dict) and attrs:
                line += f" | 속성: {', '.join(f'{k}:{v}' for k,v in list(attrs.items())[:3])}"

            rels = [
                r for r in e.get("relations", [])
                if isinstance(r, dict) and float(r.get("confidence", 0)) >= CONFIDENCE_THRESHOLD
            ][:3]
            if rels:
                rel_strs = []
                for r in rels:
                    st = self.get_rel_type(r)
                    if is_sensitive_relation(st):
                        continue
                    w = get_relation_weight(st)
                    rel_strs.append(f"{st}->{r.get('target','')}(conf={float(r.get('confidence',0)):.2f},w={w:.1f})")
                if rel_strs:
                    line += f" | 관계: {'; '.join(rel_strs)}"

            if etype == "concept":
                anc = get_ancestors(name, max_depth=2)
                if anc:
                    line += f" | 상위: {'→'.join(anc)}"

            lines.append(line)

        ctx = ""
        if lines:
            ctx += f"\n[GRAPH CONTEXT (unified={unified_score:.2f})]\n" + "\n".join(lines)
        if graph_paths:
            ctx += "\n\n[추론 경로]\n" + "".join(f"  • {p}\n" for p in graph_paths[:10])

        return ctx
