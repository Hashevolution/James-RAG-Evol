"""
PROJECT JAMES - Ontology (Phase 4 → α-8)

Phase 3.5: weight, sensitive, compute_graph_score 추가
Phase 4:   [P4-ONT-1] allowed_head/tail 타입 제약
           validate_relation_types(), is_valid_relation_triple()
α-8 Phase A (2026-06-02): horizontal types extension —
           4 existing types + 5 new (event/date/location/quantity/project)
           + 6 new relations (OCCURRED_AT/HAPPENED_ON/LOCATED_IN/
           INVOLVES/MEASURED_AS/WORKED_ON). Additive-only; no migration.
"""

from typing import Dict, List, Optional, Set, Tuple

# ─── α-8: abstract root + entity types registry ───────────────────────
# Existing 4 types kept; 5 new horizontal types added. Mother-platform
# rule #1 compliance verified per design memo §2.3 (only horizontal types;
# no legal/food/retail/finance-specific types). v0.5 domain packs extend
# this dict via plugin mechanism (forward compat hook per design memo §3.4).
ENTITY_TYPES: Dict[str, Dict] = {
    # Existing (unchanged contracts; gain `parent` field only)
    "person":   {"parent": "Entity", "active": True, "since": "v0.1"},
    "org":      {"parent": "Entity", "active": True, "since": "v0.1"},
    "concept":  {"parent": "Entity", "active": True, "since": "v0.1"},
    "document": {"parent": "Entity", "active": True, "since": "v0.1"},
    # α-8 additions (horizontal only)
    "event":    {"parent": "Entity", "active": True, "since": "v0.4-α-8"},
    "date":     {"parent": "Entity", "active": True, "since": "v0.4-α-8"},
    "location": {"parent": "Entity", "active": True, "since": "v0.4-α-8"},
    "quantity": {"parent": "Entity", "active": True, "since": "v0.4-α-8"},
    "project":  {"parent": "Entity", "active": True, "since": "v0.4-α-8"},
}

# ─── v0.5 B.5: Enterprise document subtypes (mother-level) ────────────
# Per `docs/design/v0.5-enterprise-document-ontology.md` §3.1.
# 10 generic enterprise document classes; each passes the 4-vertical test
# (legal / food / retail / finance applicability documented in design memo).
# Vertical-specific subtypes (NDA, force_majeure, recipe, 10_K, treatment_
# protocol, etc.) are explicitly REJECTED here and deferred to v1.0
# vertical-pack plugins extending this dict via the parent-pointer chain
# (e.g., NDA → contract → document → Entity).
DOCUMENT_SUBTYPES: Dict[str, Dict] = {
    "contract":        {"parent": "document", "since": "v0.5"},
    "policy":          {"parent": "document", "since": "v0.5"},
    "procedure":       {"parent": "document", "since": "v0.5"},
    "memo":            {"parent": "document", "since": "v0.5"},
    "report":          {"parent": "document", "since": "v0.5"},
    "specification":   {"parent": "document", "since": "v0.5"},
    "meeting_minutes": {"parent": "document", "since": "v0.5"},
    "standard":        {"parent": "document", "since": "v0.5"},
    "form":            {"parent": "document", "since": "v0.5"},
    "record":          {"parent": "document", "since": "v0.5"},
}

# ─── v0.5 B.5: Enterprise roles for documents ─────────────────────────
# Per design memo §3.4. Document-relationship roles; orthogonal to the
# baseline RBAC (admin / manager / employee / external in core/security/).
# Permission tokens are suggestive at this registry layer — actual
# enforcement lives in the existing security pipeline. B.5 contributes
# the *contract*, not the *enforcer*.
ENTERPRISE_ROLES: Dict[str, Dict] = {
    "AUTHOR":   {"perms_over_doc": {"read", "edit", "submit_review"}, "since": "v0.5"},
    "REVIEWER": {"perms_over_doc": {"read", "comment", "reject"},      "since": "v0.5"},
    "APPROVER": {"perms_over_doc": {"read", "approve", "reject"},      "since": "v0.5"},
    "READER":   {"perms_over_doc": {"read"},                            "since": "v0.5"},
}

RELATION_TYPES: Dict[str, Dict] = {
    "STUDIES":     {"label":"공부",  "inverse":"STUDIED_BY",   "transitive":False, "weight":1.0, "sensitive":False, "allowed_head":{"person"},         "allowed_tail":{"concept"}},
    "RESEARCHES":  {"label":"연구",  "inverse":"RESEARCHED_BY","transitive":False, "weight":1.0, "sensitive":False, "allowed_head":{"person","org"},    "allowed_tail":{"concept"}},
    "TEACHES":     {"label":"가르침","inverse":"TAUGHT_BY",    "transitive":False, "weight":0.9, "sensitive":False, "allowed_head":{"person"},         "allowed_tail":{"concept","person"}},
    "BELONGS_TO":  {"label":"소속",  "inverse":"HAS_MEMBER",   "transitive":True,  "weight":1.2, "sensitive":False, "allowed_head":{"person","org"},    "allowed_tail":{"org"}},
    "WORKS_AT":    {"label":"근무",  "inverse":"EMPLOYS",      "transitive":False, "weight":1.1, "sensitive":False, "allowed_head":{"person"},         "allowed_tail":{"org"}},
    "FOUNDED_BY":  {"label":"설립됨","inverse":"FOUNDED",      "transitive":False, "weight":1.0, "sensitive":False, "allowed_head":{"org"},            "allowed_tail":{"person"}},
    "IS_A":        {"label":"분류",  "inverse":"HAS_SUBTYPE",  "transitive":True,  "weight":1.1, "sensitive":False, "allowed_head":{"concept"},        "allowed_tail":{"concept"}},
    "PART_OF":     {"label":"구성",  "inverse":"HAS_PART",     "transitive":True,  "weight":1.0, "sensitive":False, "allowed_head":None,               "allowed_tail":None},
    "RELATED_TO":  {"label":"관련",  "inverse":"RELATED_TO",   "transitive":False, "weight":0.7, "sensitive":False, "allowed_head":None,               "allowed_tail":None},
    "PRODUCES":    {"label":"생산",  "inverse":"PRODUCED_BY",  "transitive":False, "weight":1.0, "sensitive":False, "allowed_head":{"org"},            "allowed_tail":{"concept","document"}},
    "OPERATES_IN": {"label":"산업",  "inverse":"HAS_PLAYER",   "transitive":False, "weight":0.8, "sensitive":False, "allowed_head":{"org"},            "allowed_tail":{"concept"}},
    "BELONGS_TO_INDUSTRY": {"label":"분야","inverse":"INDUSTRY_OF","transitive":False,"weight":0.8,"sensitive":False,"allowed_head":{"org","concept"},  "allowed_tail":{"concept"}},
    # 고위험 sensitive
    "HAS_SECRET":     {"label":"비밀보유","inverse":"SECRET_OF",    "transitive":False,"weight":0.0,"sensitive":True, "allowed_head":None,"allowed_tail":None},
    "KNOWS_PASSWORD": {"label":"암호보유","inverse":"PASSWORD_OF",  "transitive":False,"weight":0.0,"sensitive":True, "allowed_head":None,"allowed_tail":None},
    "HAS_CREDENTIAL": {"label":"자격증명","inverse":"CREDENTIAL_OF","transitive":False,"weight":0.0,"sensitive":True, "allowed_head":None,"allowed_tail":None},
    "OWNS_PRIVATE":   {"label":"비공개소유","inverse":"PRIVATE_OF", "transitive":False,"weight":0.0,"sensitive":True, "allowed_head":None,"allowed_tail":None},
    # ─── α-8 Phase A: 6 new relations for horizontal types ───
    "OCCURRED_AT":  {"label":"발생장소","inverse":"HOSTED",      "transitive":False, "weight":1.0, "sensitive":False, "allowed_head":{"event"},                      "allowed_tail":{"location"}},
    "HAPPENED_ON":  {"label":"발생일",  "inverse":"DATE_OF",     "transitive":False, "weight":1.0, "sensitive":False, "allowed_head":{"event"},                      "allowed_tail":{"date"}},
    "LOCATED_IN":   {"label":"위치",    "inverse":"CONTAINS",    "transitive":True,  "weight":0.9, "sensitive":False, "allowed_head":{"event","org","person"},       "allowed_tail":{"location"}},
    "INVOLVES":     {"label":"참여",    "inverse":"PARTICIPATED","transitive":False, "weight":0.9, "sensitive":False, "allowed_head":{"event","project"},            "allowed_tail":{"person","org","concept"}},
    "MEASURED_AS":  {"label":"수치",    "inverse":"MEASURES",    "transitive":False, "weight":0.8, "sensitive":False, "allowed_head":None,                           "allowed_tail":{"quantity"}},
    "WORKED_ON":    {"label":"수행",    "inverse":"WORKED_BY",   "transitive":False, "weight":1.0, "sensitive":False, "allowed_head":{"person","org"},               "allowed_tail":{"project"}},
    # ─── v0.5 B.5: document-specific relations ──────────────────────
    # Per design memo §3.3. AUTHORED_BY / APPROVED_BY / REFERENCES /
    # DERIVED_FROM. SUPERSEDES already exists in the T7 supersede chain
    # layer (core/lifecycle/supersede_chain.py) — not added here.
    "AUTHORED_BY":  {"label":"작성자",  "inverse":"AUTHORED",     "transitive":False, "weight":1.0, "sensitive":False, "allowed_head":{"document"},                     "allowed_tail":{"person"}},
    "APPROVED_BY":  {"label":"승인자",  "inverse":"APPROVED",     "transitive":False, "weight":1.0, "sensitive":True,  "allowed_head":{"document"},                     "allowed_tail":{"person"}},
    "REFERENCES":   {"label":"참조함",  "inverse":"REFERENCED_BY","transitive":False, "weight":0.8, "sensitive":False, "allowed_head":{"document"},                     "allowed_tail":{"document"}},
    "DERIVED_FROM": {"label":"유래",    "inverse":"DERIVED_INTO", "transitive":True,  "weight":0.9, "sensitive":False, "allowed_head":{"document"},                     "allowed_tail":{"document"}},
}

LABEL_TO_TYPE: Dict[str, str] = {
    "공부":"STUDIES","연구":"RESEARCHES","가르침":"TEACHES","소속":"BELONGS_TO",
    "근무":"WORKS_AT","분류":"IS_A","구성":"PART_OF","관련":"RELATED_TO",
    "생산":"PRODUCES","산업":"OPERATES_IN","분야":"BELONGS_TO_INDUSTRY","설립됨":"FOUNDED_BY",
    "비밀보유":"HAS_SECRET","암호보유":"KNOWS_PASSWORD","관계":"RELATED_TO","연결":"RELATED_TO",
    # α-8 Phase A
    "발생장소":"OCCURRED_AT","발생일":"HAPPENED_ON","위치":"LOCATED_IN",
    "참여":"INVOLVES","수치":"MEASURED_AS","수행":"WORKED_ON",
    # v0.5 B.5: document relations
    "작성자":"AUTHORED_BY","승인자":"APPROVED_BY",
    "참조함":"REFERENCES","유래":"DERIVED_FROM",
}

ALLOWED_RELATIONS: Dict[str, Set[str]] = {
    # Existing 4 types unchanged (preserve superset semantics)
    "person":   {"STUDIES","RESEARCHES","TEACHES","BELONGS_TO","WORKS_AT","RELATED_TO","HAS_SECRET","HAS_CREDENTIAL","LOCATED_IN","WORKED_ON","INVOLVES"},
    "org":      {"BELONGS_TO","OPERATES_IN","PRODUCES","RELATED_TO","FOUNDED_BY","LOCATED_IN","WORKED_ON","INVOLVES"},
    "concept":  {"IS_A","PART_OF","RELATED_TO","BELONGS_TO_INDUSTRY","INVOLVES"},
    "document": {"RELATED_TO","BELONGS_TO","OWNS_PRIVATE",
                 # v0.5 B.5: document-specific relations
                 "AUTHORED_BY","APPROVED_BY","REFERENCES","DERIVED_FROM"},
    # α-8 Phase A: 5 new horizontal types
    "event":    {"OCCURRED_AT","HAPPENED_ON","INVOLVES","LOCATED_IN","RELATED_TO"},
    "date":     {"HAPPENED_ON","RELATED_TO"},
    "location": {"LOCATED_IN","RELATED_TO"},
    "quantity": {"MEASURED_AS","RELATED_TO"},
    "project":  {"WORKED_ON","INVOLVES","PRODUCES","RELATED_TO"},
}

CONCEPT_HIERARCHY: Dict[str, Optional[str]] = {
    "경제학":"사회과학","법학":"사회과학","심리학":"사회과학","사회학":"사회과학",
    "사회과학":"학문","물리학":"자연과학","화학":"자연과학","생물학":"자연과학",
    "자연과학":"학문","컴퓨터공학":"공학","전자공학":"공학","공학":"학문","학문":None,
    "인공지능":"IT","머신러닝":"인공지능","딥러닝":"머신러닝",
    "IT":"산업","전자":"산업","제조":"산업","금융":"산업","산업":None,
}

# ─── 기본 함수 ───────────────────────────────────────────────

def normalize_relation(label: str) -> str:
    if label in LABEL_TO_TYPE: return LABEL_TO_TYPE[label]
    if label in RELATION_TYPES: return label
    print(f"[ONTOLOGY] 미등록 relation '{label}' → RELATED_TO")
    return "RELATED_TO"

def get_relation_label(rel_type: str) -> str:
    return RELATION_TYPES.get(rel_type, {}).get("label", rel_type)

def get_relation_weight(rel_type: str) -> float:
    return float(RELATION_TYPES.get(normalize_relation(rel_type), {}).get("weight", 0.7))

def is_sensitive_relation(rel_type: str) -> bool:
    return bool(RELATION_TYPES.get(normalize_relation(rel_type), {}).get("sensitive", False))

def compute_graph_score(relations: List[Dict], depth: int = 1) -> float:
    """score = Σ(weight × confidence) / depth

    v0.6.1 — exclude lifecycle-deactivated edges (cascade / T1 / T7) so a
    relation the cascade invalidated no longer inflates the graph score
    that drives DFS halting + entity ranking (companion to the live-output
    filter in expand_dynamic / build_graph_context_str, PR #1021).
    Lazy import keeps core.ontology free of a graph_engine import cycle.
    """
    if not relations or depth < 1: return 0.0
    from core.graph_engine.constants import relation_is_live
    total = 0.0
    for rel in relations:
        if not isinstance(rel, dict): continue
        if not relation_is_live(rel): continue
        raw = rel.get("type") or rel.get("label") or "RELATED_TO"
        if is_sensitive_relation(raw): continue
        total += get_relation_weight(raw) * float(rel.get("confidence", 0.0))
    return round(total / max(depth, 1), 4)

# ─── [P4-ONT-1] 타입 제약 ────────────────────────────────────

def validate_relation_types(
    head_type: str,
    rel_type:  str,
    tail_type: str,
    strict:    bool = False,
) -> Tuple[bool, str]:
    """
    [P4-ONT-1] head/tail entity type이 relation 제약에 부합하는지 검증.

    Returns: (is_valid, reason)
    strict=True → 위반 시 차단 / False → 경고만
    """
    std  = normalize_relation(rel_type)
    info = RELATION_TYPES.get(std, {})
    ah   = info.get("allowed_head")
    at_  = info.get("allowed_tail")

    violations = []
    if ah is not None and head_type not in ah:
        violations.append(f"head '{head_type}' 불허 (허용:{ah})")
    if at_ is not None and tail_type not in at_:
        violations.append(f"tail '{tail_type}' 불허 (허용:{at_})")

    if violations:
        reason = f"[ONT-TYPE] {std}: {' | '.join(violations)}"
        if strict:
            print(f"{reason} → 차단"); return False, reason
        else:
            print(f"{reason} → 경고")
    return True, ""

def is_valid_relation_triple(head: dict, rel_type: str, tail: dict, strict: bool = False) -> bool:
    """entity dict 직접 받아 타입 제약 검증 (DFS 내 사용)"""
    ht = head.get("entity_type", head.get("type", "concept"))
    tt = tail.get("entity_type", tail.get("type", "concept"))
    valid, _ = validate_relation_types(ht, rel_type, tt, strict=strict)
    return valid

# ─── 기타 ────────────────────────────────────────────────────

def validate_relation(entity_type: str, rel_type: str, strict: bool = False) -> bool:
    allowed = ALLOWED_RELATIONS.get(entity_type, set())
    if rel_type not in allowed:
        msg = f"[ONTOLOGY] '{entity_type}' → '{rel_type}' 비표준"
        if strict: print(f"{msg} → 차단"); return False
        else: print(f"{msg} → 경고")
    return True

def get_ancestors(concept: str, max_depth: int = 3) -> List[str]:
    ancestors, current = [], concept
    for _ in range(max_depth):
        parent = CONCEPT_HIERARCHY.get(current)
        if parent is None: break
        ancestors.append(parent); current = parent
    return ancestors

def is_transitive(rel_type: str) -> bool:
    return RELATION_TYPES.get(rel_type, {}).get("transitive", False)

def infer_relations(entity_name: str, entity_type: str) -> List[Dict]:
    if entity_type == "concept" and entity_name in CONCEPT_HIERARCHY:
        parent = CONCEPT_HIERARCHY[entity_name]
        if parent:
            return [{"target":parent,"target_type":"concept","type":"IS_A",
                     "label":"분류","confidence":1.0,"inferred":True}]
    return []

def validate_entity_schema(entity: dict) -> List[str]:
    issues = []
    name = entity.get("name",""); entity_type = entity.get("entity_type",entity.get("type",""))
    if not name: issues.append("name 없음")
    if entity_type not in ALLOWED_RELATIONS: issues.append(f"미등록 entity_type: {entity_type}")
    if not entity.get("entity_id"): issues.append("entity_id 없음")
    for rel in entity.get("relations",[]):
        if not isinstance(rel, dict): continue
        conf = float(rel.get("confidence",0))
        if conf <= 0 or conf > 1: issues.append(f"confidence 범위 오류: {conf}")
    return issues

# ─── α-8 Phase A: entity types registry helpers ─────────────────────

def is_active_entity_type(entity_type: str) -> bool:
    """ENTITY_TYPES 레지스트리에 등록되고 active=True 인지."""
    info = ENTITY_TYPES.get(entity_type)
    return bool(info and info.get("active", False))


def get_entity_type_info(entity_type: str) -> Dict:
    """ENTITY_TYPES 레지스트리 메타데이터 lookup. 미등록 시 빈 dict."""
    return dict(ENTITY_TYPES.get(entity_type, {}))


def list_active_entity_types() -> List[str]:
    """Active=True 인 entity type 이름 리스트 (선언 순서 보존)."""
    return [t for t, info in ENTITY_TYPES.items() if info.get("active", False)]


if __name__ == "__main__":
    print("=== Ontology Phase 4 자가 테스트 ===\n")
    for rtype in ["BELONGS_TO","STUDIES","RELATED_TO","HAS_SECRET"]:
        print(f"  {rtype:20s} weight={get_relation_weight(rtype):.1f}  sensitive={is_sensitive_relation(rtype)}")
    print()
    cases = [
        ("person","STUDIES","concept",True),
        ("org","STUDIES","concept",False),
        ("person","BELONGS_TO","org",True),
        ("concept","IS_A","concept",True),
        ("person","IS_A","concept",False),
    ]
    for head,rel,tail,exp in cases:
        ok,_ = validate_relation_types(head,rel,tail,strict=False)
        icon = "[OK]" if ok==exp else "[XX]"
        print(f"  {icon} {head:8s} -[{rel:12s}]→ {tail:8s} valid={ok} (기대={exp})")

    print("\n=== α-8 Phase A: new horizontal types ===\n")
    print("  ENTITY_TYPES (active):", list_active_entity_types())
    print()
    a8_cases = [
        ("event","OCCURRED_AT","location",True),
        ("event","HAPPENED_ON","date",True),
        ("person","WORKED_ON","project",True),
        ("event","INVOLVES","person",True),
        ("date","HAPPENED_ON","date",False),  # date is tail-only for HAPPENED_ON
        ("location","LOCATED_IN","event",False),  # tail must be location
    ]
    for head,rel,tail,exp in a8_cases:
        ok,_ = validate_relation_types(head,rel,tail,strict=False)
        icon = "[OK]" if ok==exp else "[XX]"
        print(f"  {icon} {head:8s} -[{rel:12s}]→ {tail:8s} valid={ok} (기대={exp})")

    print("\n[DONE]")
