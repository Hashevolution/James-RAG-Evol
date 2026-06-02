"""
PROJECT JAMES — Relation sources schema helpers (Knowledge Cascade Phase A)

문서: docs/design/v0.3-knowledge-cascade.md

Phase A 의 목적은 frontmatter `relations:` 에 `sources` 필드 인프라를
추가하는 것이다. confidence 는 **그대로 두고** sources 만 새로 채워
넣는다. Phase B 에서 ingestion 이 sources 에 직접 쓰기 시작하고,
Phase C/D 의 파일 cascade 와 Phase E 의 그래프 에디터가 같은 sources
배열을 통해 흐르게 된다.

본 모듈은 Phase A 시점에 production 경로가 의존하지 않는다 — 마이그
레이션 스크립트와 미래 phase 의 코드가 공유할 helper 만 노출한다.
production 의 `relation["confidence"]` 읽기 경로는 Phase A 단계에서
완전히 그대로 작동한다.

용어:
- ``role``: source 의 종류. cascade 가 어떤 source 를 어떻게 다룰지
  결정한다. 4 종.
  * extract  — LLM 이 doc 본문에서 추출
  * inverse  — back-reference (migrate_inverse_relations.py 가 생성)
  * manual   — admin 이 그래프 에디터로 수동 입력 (Phase E)
  * legacy   — Phase A 마이그레이션 시점에 출처 추적 없이 back-fill
               된 사전-마이그레이션 잔류 (cascade 가 건드리지 않음)

v0.4 Sprint 5 first-bundle (2026-05-26+, PR 0 validator prep):
  Extends the schema with T1 (Temporal Validity) + T7 (Supersede
  Chain) fields. Existing v0.3 callers see no behaviour change —
  every new field has a v0.3-equivalent safe default. See
  ``docs/handovers/v0.4.0-sprint5-layer4-first-bundle-entry.md``
  §2 for scope + §12.2 for the clock decision.

  - **Source-level (T1)**: ``valid_from`` / ``valid_until``
    (ISO 8601 strings or None).
  - **Edge-level (T1+T7)**: ``validity`` (``{from, to}`` dict),
    ``status`` (``{active, superseded_by, superseded_at}`` dict),
    ``mutation_type`` (``"active" | "invalidated" | "superseded" |
    "expired"`` enum).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


# Source role constants — string literals are intentional. yaml 직렬화 시
# 그대로 frontmatter 에 쓰이고, cascade 분기가 문자열 매칭으로 동작한다.
LEGACY_SOURCE_ROLE  = "legacy"
EXTRACT_SOURCE_ROLE = "extract"
INVERSE_SOURCE_ROLE = "inverse"
MANUAL_SOURCE_ROLE  = "manual"

VALID_SOURCE_ROLES = frozenset({
    LEGACY_SOURCE_ROLE,
    EXTRACT_SOURCE_ROLE,
    INVERSE_SOURCE_ROLE,
    MANUAL_SOURCE_ROLE,
})

# Confidence cap. Noisy-OR is mathematically in [0, 1) for finite weights
# in [0, 1], so the cap is informational — used to keep the public type
# contract stable for downstream code that previously saw clamped values.
CONFIDENCE_CAP = 1.0


# ── Entity-type vocabulary (PR-11 graph evolution) ────────────────────
#
# 문서: docs/design/v0.3-graph-evolution.md
#
# JAMES 그래프의 5 entity type. 처음 4 종 (person/concept/org/document)
# 은 wiki_generator 가 LLM 추출로 emit. 5번째 `event` 는 시간 축에
# 묶인 노드로 PR-11 의 핵심. PR-11a-1 시점에는 본 상수만 존재 —
# production 코드 (wiki_generator.py 등) 는 여전히 4 종 literal 을
# 사용. lift 는 PR-11a-2 / PR-11b 에서.
#
# 이 상수는 *graph-valid* type 의 진실 원천이다. α-8 (2026-06-03) 까지
# 는 ingest-capable subset 과 의도적으로 분리됐으나 (admin path 로
# 생성된 event 노드는 ingest emit 과 무관) α-8 extractor extension
# 후로는 ingest 도 9 type 모두 emit 가능. 본 상수가 truth source.
ENTITY_TYPES_CORE: tuple[str, ...] = (
    "person",
    "concept",
    "org",
    "document",
    # α-8 horizontal extension (2026-06-03) — must mirror
    # core/ontology.py:ENTITY_TYPES. wiki/entity/<type>/ directories
    # auto-created at WikiGenerator startup, empty until first ingest
    # of that type. 5 new types all horizontal per design memo §2.3
    # boundary test (no legal/food/finance vertical drift).
    "event",
    "date",
    "location",
    "quantity",
    "project",
)

# Event-like entity 의 list — core 는 "event" 하나. OntologyPack 의
# entity_types 가 시간 축을 요구하는 subtype 을 추가하면 loader
# (PR-11e) 가 이 set 을 mutate. ingest post-processor 와 admin
# endpoint 가 멤버십으로 occurred_at 강제 여부를 결정한다.
#
# set (mutable) 인 이유: loader 가 startup 시점에 추가. 코드 변경 후
# 런타임 mutate 는 정의되지 않은 동작 (test 환경에서만 _reset_
# helper 로 의도적으로 변경).
EVENT_LIKE_ENTITY_TYPES: set[str] = {"event"}

# occurred_at 의 quantization bucket — 디자인 §4.1.
# 미상 / 분기·연 단위 정보도 명시적으로 표현 가능하도록 5 단계 enum.
# 저장은 항상 full ISO 8601 (예: "2026-01-10" 또는 "2026-01-10T15:32:00Z"),
# precision 은 consumer 에게 어디까지 신뢰할지 알려주는 메타데이터.
VALID_OCCURRED_AT_PRECISIONS: frozenset[str] = frozenset({
    "year",
    "month",
    "day",
    "hour",
    "minute",
})


def validate_occurred_at(
    value: str,
    precision: str = "day",
) -> None:
    """Validate that ``value`` is a parseable ISO 8601 datetime / date
    string AND that ``precision`` is one of the 5 supported buckets.

    Raises ``ValueError`` on either failure. The function is
    side-effect-free; callers use it as an admission gate before
    writing an event node.

    Trailing ``Z`` (Zulu / UTC) is accepted via the standard
    ``+00:00`` substitution. Naive datetimes (no tz) are accepted —
    the cascade and retrieval paths treat all stored timestamps as
    workspace-local unless an explicit offset is present.
    """
    if not isinstance(value, str) or not value:
        raise ValueError(
            "occurred_at must be a non-empty ISO 8601 string"
        )
    if precision not in VALID_OCCURRED_AT_PRECISIONS:
        raise ValueError(
            f"occurred_at_precision must be one of "
            f"{sorted(VALID_OCCURRED_AT_PRECISIONS)}, got {precision!r}"
        )
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError(
            f"occurred_at not parseable as ISO 8601: {value!r}"
        ) from e


def compute_confidence_from_sources(sources: list | None) -> float:
    """Noisy-OR over per-source weights — see design memo §3.

    Formula: ``P(confirmed) = 1 - Π(1 - w_i)``

    Properties (the reason this formula was chosen over `sum` / `max` /
    `mean`):
      - 0 sources → 0.0
      - 1 source with weight w → w (identity preserved, so single-source
        Phase A back-fills are byte-identical to the legacy clamped sum)
      - many sources → asymptotic to 1.0 but never saturates exactly,
        so a quarterly-report cascade with 5–20 corroborating docs
        keeps signal differentiation (clamped sum loses it after 2)
      - delete cascade strictly decreases confidence (monotonic),
        never leaves a relation at a stale 1.0 ceiling

    Weights outside [0, 1] are clamped per-element before multiplication,
    so a malformed weight cannot move the running product past 0 or
    below 0.
    """
    if not sources:
        return 0.0
    product = 1.0
    for s in sources:
        if not isinstance(s, dict):
            continue
        w = s.get("weight")
        if not isinstance(w, (int, float)):
            continue
        w_clamped = max(0.0, min(1.0, float(w)))
        product *= (1.0 - w_clamped)
    return round(1.0 - product, 4)


def read_relation_sources(rel: dict | None) -> list:
    """Relation 에서 sources 배열을 안전하게 꺼낸다.

    - 신규 (Phase A 마이그레이션 후): `rel["sources"]` 가 그대로 반환
    - 레거시 (마이그레이션 전 또는 마이그레이션 실패 fallback):
      ``confidence`` 만 있는 relation 에서 synthetic legacy source 1개
      를 즉석 생성. doc_id 는 None — 누가 강화했는지 모름.

    이 함수의 목적은 Phase B / C / D / E 의 코드가 "sources 가 있다"
    고 가정하고 동작할 수 있게 정규화하는 것. Phase A 머지 뒤에는
    마이그레이션 스크립트가 모든 relation 에 sources 를 채워두므로
    fallback 경로는 거의 안 타지만, 외부에서 손편집된 .md 가 들어왔을
    때를 대비해 항상 안전한 결과를 반환한다.
    """
    if not isinstance(rel, dict):
        return []
    s = rel.get("sources")
    if isinstance(s, list):
        return s
    conf = rel.get("confidence")
    if isinstance(conf, (int, float)):
        return [{
            "doc_id": None,
            "weight": float(conf),
            "role":   LEGACY_SOURCE_ROLE,
            "ts":     None,
        }]
    return []


# v0.4 Sprint 5 — T1 + T7 schema extension lives in
# ``core.lifecycle.schema`` so the v0.3 surface here stays small enough
# to take future Phase-A follow-ups without breaching the 20 KB cap.
# Re-export for back-compat — existing callers can still
# ``from core.relations_schema import VALID_MUTATION_TYPES`` etc.
from core.lifecycle.schema import (  # noqa: F401
    T1_MUTATION_ACTIVE,
    T1_MUTATION_EXPIRED,
    T1_MUTATION_INVALIDATED,
    T1_MUTATION_SUPERSEDED,
    T1_SOURCE_FIELD_VALID_FROM,
    T1_SOURCE_FIELD_VALID_UNTIL,
    T7_EDGE_FIELD_MUTATION_TYPE,
    T7_EDGE_FIELD_STATUS,
    T7_EDGE_FIELD_VALIDITY,
    VALID_MUTATION_TYPES,
    apply_v04_edge_defaults,
    apply_v04_source_defaults,
    validate_edge_v04_fields,
    validate_source_v04_fields,
)


def build_legacy_source(
    confidence: float,
    mtime_iso:  str | None,
) -> dict[str, Any]:
    """Phase A 마이그레이션이 기존 confidence-only relation 에 부착할
    1-source back-fill row.

    - doc_id None — 디자인 §2 non-goal: 사전 마이그레이션 backref 의
      출처는 복원하지 않는다. cascade 가 ``role == legacy`` 인 항목을
      file delete 처리 대상에서 제외한다.
    - weight 는 기존 confidence 값을 그대로 보존. compute_confidence_
      from_sources 가 같은 숫자를 돌려준다 → 행동 변화 0.
    - ts 는 entity 파일의 mtime ISO string (대략적 시간 표시. 실제
      relation 이 추가된 시각은 알 수 없음).
    """
    return {
        "doc_id": None,
        "weight": float(confidence),
        "role":   LEGACY_SOURCE_ROLE,
        "ts":     mtime_iso,
    }
