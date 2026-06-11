"""§5.7.13 Abstraction Module — trust-contract tests.

Locks the contract from ARCHITECTURE.md §5.7.13:
  • API surface (Decision / AbstractionMap / build_map / mask_text /
    unmask_text + emit_egress_event)
  • 6 invariants (determinism, substring safety, particle/boundary
    safety, hallucination flagging, local-only map, no-egress purity)
  • PoC parity (§5.7.13 validation pointer — the 5 PoC self-tests
    re-run as pytest cases against the production module)

Parity tests mirror `scripts/research/abstraction_layer_poc.py`'s
`_selftest` cases 1-5. If a future change to the production module
breaks one of these, the PoC's 5/5 promise is also broken — the test
file is the gate.
"""
from __future__ import annotations

import sqlite3
from typing import List

import pytest

from core.abstraction import (
    AbstractionMap,
    Decision,
    build_map,
    default_decider,
    emit_egress_event,
    mask_text,
    unmask_text,
)
from core.abstraction._policy import (
    _entity_name,
    _entity_type,
    _is_sensitive,
)


# ─── API surface (§5.7.13 contract) ─────────────────────────────────

def test_decision_enum_three_outcomes():
    """§5.7.12 three-way: MASK / PASS / KEEP_LOCAL. No other values."""
    assert {Decision.MASK, Decision.PASS, Decision.KEEP_LOCAL} == set(Decision)


def test_decision_string_values_are_stable():
    """String values are stable — used in audit rows and persisted in
    research outputs. Changing them is a contract break."""
    assert Decision.MASK.value == "mask"
    assert Decision.PASS.value == "pass"
    assert Decision.KEEP_LOCAL.value == "keep"


def test_public_api_surface_matches_init():
    """The frozen public surface in __init__.__all__ matches §5.7.13."""
    import core.abstraction as ab

    expected = {
        "Decision", "AbstractionMap", "default_decider",
        "build_map", "mask_text", "unmask_text", "emit_egress_event",
        "run_cloud_egress",
    }
    assert set(ab.__all__) == expected
    for name in expected:
        assert hasattr(ab, name), f"missing public symbol {name!r}"


# ─── §5.7.13 invariant #1 — determinism ─────────────────────────────

def test_determinism_same_input_same_map():
    """build_map(entities, decider) is byte-identical across calls.
    Required for §5.7.2 trace-schema replay."""
    entities = [
        {"name": "김철수", "entity_type": "person", "sensitive": True},
        {"name": "이영희", "entity_type": "person", "sensitive": True},
        {"name": "박민수", "entity_type": "person", "sensitive": True},
    ]
    a = build_map(entities, default_decider()).forward
    b = build_map(entities, default_decider()).forward
    assert a == b
    assert a == {"김철수": "PERSON_1", "이영희": "PERSON_2", "박민수": "PERSON_3"}


def test_determinism_counter_advances_in_declaration_order():
    """Per-TYPE counter follows entity declaration order."""
    entities = [
        {"name": "B", "entity_type": "person", "sensitive": True},
        {"name": "A", "entity_type": "person", "sensitive": True},
    ]
    amap = build_map(entities, default_decider())
    assert amap.forward == {"B": "PERSON_1", "A": "PERSON_2"}


# ─── §5.7.13 invariant #2 — substring safety ────────────────────────

def test_substring_safety_longest_first():
    """A name that is a substring of another must not corrupt the
    replacement (PoC self-test §5)."""
    ents = [
        {"name": "김철", "entity_type": "person", "sensitive": True},
        {"name": "김철수", "entity_type": "person", "sensitive": True},
    ]
    amap = build_map(ents, default_decider())
    masked = mask_text("김철수와 김철은 다른 사람이다.", amap)
    # both replaced, no corruption — '김철수' got its own placeholder
    # even though '김철' is a prefix of it
    assert "김철수" not in masked
    assert "김철" not in masked.replace(amap.forward["김철수"], "")
    restored, flagged = unmask_text(masked, amap)
    assert restored == "김철수와 김철은 다른 사람이다."
    assert flagged == []


# ─── §5.7.13 invariant #3 — particle/boundary safety ────────────────

def test_korean_particle_after_placeholder():
    """`PERSON_3의` must unmask to `<real>의` — `\\b` would fail here."""
    amap = AbstractionMap()
    amap.placeholder_for("김철수", "person")   # → PERSON_1
    amap.placeholder_for("이영희", "person")   # → PERSON_2
    amap.placeholder_for("박민수", "person")   # → PERSON_3
    restored, flagged = unmask_text(
        "PERSON_3의 보고라인 최상단은 PERSON_1 이다.", amap,
    )
    assert restored == "박민수의 보고라인 최상단은 김철수 이다."
    assert flagged == []


def test_two_digit_placeholder_not_split():
    """`PERSON_12` is one token, not `PERSON_1` + `2` (PoC `_PLACEHOLDER_RE`
    not-a-digit lookahead)."""
    amap = AbstractionMap()
    # allocate 12 placeholders so PERSON_12 is real
    for i in range(12):
        amap.placeholder_for(f"name{i}", "person")
    assert amap.forward["name11"] == "PERSON_12"
    restored, flagged = unmask_text("alpha PERSON_12 beta", amap)
    assert "name11" in restored
    assert flagged == []


def test_placeholder_inside_identifier_not_matched():
    """Lookbehind: `xPERSON_1` is not a placeholder match."""
    amap = AbstractionMap()
    amap.placeholder_for("김철수", "person")
    restored, flagged = unmask_text("xPERSON_1 and PERSON_1", amap)
    # only the standalone PERSON_1 is restored
    assert restored == "xPERSON_1 and 김철수"
    assert flagged == []


# ─── §5.7.13 invariant #4 — hallucination flagging ──────────────────

def test_hallucinated_placeholder_flagged_not_restored():
    """A reasoner-introduced placeholder absent from the map is
    flagged and **left verbatim** in restored text (PoC self-test §2).
    Silent de-abstraction would let cloud inject content under a real
    name — the threat this module exists to defeat."""
    amap = AbstractionMap()
    amap.placeholder_for("김철수", "person")
    bad = "최상단은 PERSON_1 이며, PERSON_9 도 관여한다."
    restored, flagged = unmask_text(bad, amap)
    assert flagged == ["PERSON_9"]
    assert "PERSON_9" in restored  # verbatim, NOT silently restored
    assert "김철수" in restored


def test_unknown_type_placeholder_not_flagged():
    """A `FOO_1` token shaped like a placeholder but with a TYPE not
    in the ontology is NOT flagged — it isn't ours to claim."""
    amap = AbstractionMap()
    amap.placeholder_for("김철수", "person")
    restored, flagged = unmask_text("PERSON_1 and FOO_99 walk in", amap)
    assert flagged == []  # FOO not in ontology
    assert restored == "김철수 and FOO_99 walk in"


def test_flagged_list_deduplicates():
    """Same hallucinated placeholder appearing twice → one entry."""
    amap = AbstractionMap()
    restored, flagged = unmask_text("PERSON_1 and PERSON_1 again", amap)
    assert flagged == ["PERSON_1"]


# ─── §5.7.12 three-way egress policy ────────────────────────────────

def test_default_decider_non_sensitive_passes():
    """Not-sensitive → PASS."""
    decide = default_decider()
    assert decide({"name": "팀A", "entity_type": "org", "sensitive": False}) == Decision.PASS


def test_default_decider_sensitive_closed_world_masks():
    """Sensitive, no open-world hint → MASK (safer-egress default)."""
    decide = default_decider()
    assert decide({"name": "김철수", "entity_type": "person", "sensitive": True}) == Decision.MASK


def test_default_decider_open_world_type_keeps_local():
    """Sensitive + open-world TYPE → KEEP_LOCAL (PoC self-test §3)."""
    decide = default_decider(open_world_types=["concept"])
    assert decide({"name": "와파린", "entity_type": "concept", "sensitive": True}) == Decision.KEEP_LOCAL


def test_default_decider_open_world_name_keeps_local():
    """Open-world NAME (specific entity) → KEEP_LOCAL even if TYPE is
    closed-world by default."""
    decide = default_decider(open_world_names=["환자김"])
    assert decide({"name": "환자김", "entity_type": "person", "sensitive": True}) == Decision.KEEP_LOCAL


def test_default_decider_string_sensitivity_truthy_values():
    """`sensitivity` chunk-metadata convention accepts string flags."""
    decide = default_decider()
    for v in ("1", "true", "yes", "high", "sensitive", "HIGH", " True "):
        assert decide({"name": "x", "entity_type": "person", "sensitivity": v}) == Decision.MASK
    for v in ("0", "false", "no", "", "low"):
        assert decide({"name": "x", "entity_type": "person", "sensitivity": v}) == Decision.PASS


def test_sensitive_flag_default_false():
    """Missing sensitivity flag → not sensitive (conservative — an
    unflagged entity is not masked but does not block egress)."""
    assert _is_sensitive({"name": "x", "entity_type": "person"}) is False


# ─── PoC §1 parity — closed-world org chart end-to-end ─────────────

def test_poc_case_1_closed_world_org_chart_round_trip():
    """PoC self-test §1: org chart masks, structural reasoning over
    placeholders restores cleanly, non-sensitive entity passes through."""
    entities = [
        {"name": "김철수", "entity_type": "person", "sensitive": True},
        {"name": "이영희", "entity_type": "person", "sensitive": True},
        {"name": "박민수", "entity_type": "person", "sensitive": True},
        {"name": "영업팀", "entity_type": "org", "sensitive": False},
    ]
    docs = (
        "김철수는 영업팀의 팀장이다. "
        "이영희는 김철수에게 보고한다. "
        "박민수는 이영희에게 보고한다."
    )
    amap = build_map(entities, default_decider())
    masked = mask_text(docs, amap)
    # sensitive names gone, non-sensitive entity passes through
    for sensitive_name in ("김철수", "이영희", "박민수"):
        assert sensitive_name not in masked
    assert "영업팀" in masked
    assert "영업팀" in amap.passed

    # simulate cloud reasoning over placeholders
    cloud_reply = "PERSON_3의 보고라인 최상단은 PERSON_1 이다."
    restored, flagged = unmask_text(cloud_reply, amap)
    assert restored == "박민수의 보고라인 최상단은 김철수 이다."
    assert flagged == []


# ─── PoC §3 parity — open-world keep-local ─────────────────────────

def test_poc_case_3_open_world_kept_local():
    """PoC self-test §3: drug names (open-world concept) → KEEP_LOCAL,
    patient name (closed-world person) → masked."""
    med = [
        {"name": "와파린", "entity_type": "concept", "sensitive": True},
        {"name": "아스피린", "entity_type": "concept", "sensitive": True},
        {"name": "환자김", "entity_type": "person", "sensitive": True},
    ]
    decide = default_decider(open_world_types=["concept"])
    amap = build_map(med, decide)
    assert set(amap.keep_local) == {"와파린", "아스피린"}
    assert "환자김" in amap.forward


# ─── §5.7.13 invariant #5 — local-only map ─────────────────────────

def test_map_has_no_persist_method():
    """The map exposes no serialize/save/persist — by design.
    Cross-query reuse would be a re-identification risk."""
    amap = AbstractionMap()
    for attr in ("save", "persist", "to_disk", "serialize", "dumps"):
        assert not hasattr(amap, attr), f"AbstractionMap should not expose {attr}"


def test_two_maps_with_same_input_dont_share_state():
    """Each build_map returns a fresh AbstractionMap — no module-level
    cache, no cross-call leakage."""
    ents = [{"name": "x", "entity_type": "person", "sensitive": True}]
    a = build_map(ents, default_decider())
    b = build_map(ents, default_decider())
    assert a is not b
    assert a.forward == b.forward  # same input → same content
    assert a.reverse is not b.reverse  # but different objects


# ─── §5.7.13 invariant #6 — no-egress purity ───────────────────────

def test_mask_text_is_pure():
    """mask_text has no side effects on its inputs."""
    amap = AbstractionMap()
    amap.placeholder_for("김철수", "person")
    original_forward = dict(amap.forward)
    original_reverse = dict(amap.reverse)
    _ = mask_text("김철수가 왔다", amap)
    _ = mask_text("김철수가 또 왔다", amap)
    assert amap.forward == original_forward
    assert amap.reverse == original_reverse


def test_unmask_text_is_pure():
    """unmask_text has no side effects on the map."""
    amap = AbstractionMap()
    amap.placeholder_for("김철수", "person")
    original_forward = dict(amap.forward)
    _ = unmask_text("PERSON_1 and PERSON_9", amap)
    assert amap.forward == original_forward


def test_mask_text_makes_no_network_call(monkeypatch):
    """No-egress purity: mask_text must not import any network module
    at call time. Module-level imports are checked by spying on
    `socket.socket` — if mask_text instantiates one, the test fails."""
    import socket

    calls = []
    real_socket = socket.socket

    def _spy(*a, **kw):
        calls.append((a, kw))
        return real_socket(*a, **kw)

    monkeypatch.setattr(socket, "socket", _spy)
    amap = AbstractionMap()
    amap.placeholder_for("김철수", "person")
    _ = mask_text("김철수가 왔다", amap)
    _ = unmask_text("PERSON_1", amap)
    assert calls == [], "mask/unmask must not open sockets"


# ─── §5.7.13 caller obligation #2 — audit emit ─────────────────────


def _read_audit_rows(db_path: str) -> List[tuple]:
    """Read `reason:egress` rows. The audit_bridge JSON-packs non-reserved
    keys (`query`, `answer`) into the SQLite `answer` column, mirroring
    the convention used by `core.reasoning.router.emit_route_event`. We
    parse the JSON back so the test can assert on the logical
    (endpoint, query, answer) the caller passed in, not on the
    bridge-internal wrapping shape."""
    import json
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            "SELECT endpoint, answer FROM audit_log "
            "WHERE endpoint='reason:egress'"
        )
        out: List[tuple] = []
        for endpoint, packed in cur.fetchall():
            blob = json.loads(packed) if packed else {}
            out.append((endpoint, blob.get("query", ""), blob.get("answer", "")))
        return out
    finally:
        conn.close()


def _init_audit_schema(db_path: str) -> None:
    """Minimal audit_log schema matching `core/audit_bridge.py` writes."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                user_role TEXT,
                endpoint TEXT,
                query TEXT,
                answer TEXT,
                graph_paths TEXT,
                blocked INTEGER,
                security_event TEXT,
                elapsed_sec REAL,
                ip_address TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def audit_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_audit.db")
    _init_audit_schema(db_path)
    monkeypatch.setattr("core.audit_bridge._DEFAULT_AUDIT_DB", db_path)
    yield db_path


def test_emit_egress_event_writes_one_row(audit_db):
    entities = [
        {"name": "김철수", "entity_type": "person", "sensitive": True},
        {"name": "삼성전자", "entity_type": "org", "sensitive": True},
        {"name": "30억", "entity_type": "quantity", "sensitive": True},
    ]
    amap = build_map(entities, default_decider())
    emit_egress_event(
        "synth",
        "프롬프트 내용",
        "claude_code_cli",
        amap,
        flagged=[],
    )
    rows = _read_audit_rows(audit_db)
    assert len(rows) == 1
    endpoint, query, answer = rows[0]
    assert endpoint == "reason:egress"
    assert query == "synth"
    # backend id + type histogram + counts in the answer blob
    assert "backend=claude_code_cli" in answer
    assert "PERSON:1" in answer
    assert "ORG:1" in answer
    assert "QUANTITY:1" in answer
    assert "flagged=-" in answer  # empty flagged renders as '-'


def test_emit_egress_event_records_flagged(audit_db):
    """Hallucinated placeholders from unmask_text land in the audit row
    so operators can answer 'did the cloud invent any entities?'."""
    amap = AbstractionMap()
    amap.placeholder_for("김철수", "person")
    _, flagged = unmask_text("PERSON_1 and PERSON_99", amap)
    emit_egress_event("verify", "p", "claude_code_cli", amap, flagged=flagged)
    rows = _read_audit_rows(audit_db)
    assert len(rows) == 1
    _, _, answer = rows[0]
    assert "flagged=PERSON_99" in answer


def test_emit_egress_event_does_not_leak_real_names(audit_db):
    """§5.7.13 invariant #5: real entity names MUST NOT appear in
    audit rows. Only placeholder ids + type histograms."""
    sensitive_names = ["김철수", "삼성전자", "30억"]
    entities = [
        {"name": "김철수", "entity_type": "person", "sensitive": True},
        {"name": "삼성전자", "entity_type": "org", "sensitive": True},
        {"name": "30억", "entity_type": "quantity", "sensitive": True},
    ]
    amap = build_map(entities, default_decider())
    emit_egress_event("synth", "프롬프트", "claude_code_cli", amap)
    rows = _read_audit_rows(audit_db)
    assert len(rows) == 1
    _, _, answer = rows[0]
    for real in sensitive_names:
        assert real not in answer, f"real name {real!r} leaked into audit row"


def test_emit_egress_event_never_raises(monkeypatch):
    """Per docstring: audit failure must not block the caller. If the
    audit_bridge import fails or mirror_to_audit_db raises, the helper
    swallows."""
    def boom(*a, **kw):
        raise RuntimeError("simulated audit failure")

    monkeypatch.setattr("core.audit_bridge.mirror_to_audit_db", boom)

    amap = AbstractionMap()
    amap.placeholder_for("x", "person")
    # MUST NOT raise
    emit_egress_event("synth", "p", "claude_code_cli", amap)


# ─── Sundry contract bits ──────────────────────────────────────────

def test_empty_nameless_entity_silently_skipped():
    """Build is resilient to entities with no name/label."""
    entities = [
        {"entity_type": "person", "sensitive": True},  # no name
        {"name": "", "entity_type": "person", "sensitive": True},  # empty
        {"name": "김철수", "entity_type": "person", "sensitive": True},
    ]
    amap = build_map(entities, default_decider())
    assert amap.forward == {"김철수": "PERSON_1"}


def test_entity_alias_field_resolution():
    """`_entity_name` falls back through name → label → title → entity_id."""
    assert _entity_name({"name": "A"}) == "A"
    assert _entity_name({"label": "B"}) == "B"
    assert _entity_name({"title": "C"}) == "C"
    assert _entity_name({"entity_id": "D"}) == "D"
    assert _entity_name({}) == ""


def test_entity_type_default():
    """Missing type → 'concept' (safe default — most entities classified
    as concept won't egress unless explicitly marked sensitive)."""
    assert _entity_type({"name": "x"}) == "concept"
    assert _entity_type({"name": "x", "type": "org"}) == "org"
    assert _entity_type({"name": "x", "entity_type": "person"}) == "person"


def test_kept_local_dedup():
    """Same KEEP_LOCAL name listed twice → one entry."""
    decide = default_decider(open_world_types=["concept"])
    entities = [
        {"name": "와파린", "entity_type": "concept", "sensitive": True},
        {"name": "와파린", "entity_type": "concept", "sensitive": True},
    ]
    amap = build_map(entities, decide)
    assert amap.keep_local == ["와파린"]


def test_passed_dedup():
    """Same PASS name listed twice → one entry."""
    entities = [
        {"name": "팀A", "entity_type": "org", "sensitive": False},
        {"name": "팀A", "entity_type": "org", "sensitive": False},
    ]
    amap = build_map(entities, default_decider())
    assert amap.passed == ["팀A"]
