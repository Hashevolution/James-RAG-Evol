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
"""

from __future__ import annotations

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

# Confidence cap. Sum of source weights can mathematically exceed 1.0 when
# many docs corroborate the same relation; the user-visible confidence
# stays in [0, 1] so existing UI bars / badges keep their semantics.
CONFIDENCE_CAP = 1.0


def compute_confidence_from_sources(sources: list | None) -> float:
    """sources 배열의 weight 합 (0..1 으로 cap).

    Phase A 시점에는 호출되지 않는다 — confidence 는 frontmatter 의
    저장된 값이 정답. Phase B 에서 ingestion 이 sources 만 쓰고
    confidence 를 derived 로 다루기 시작할 때 호출 site 가 생긴다.
    """
    if not sources:
        return 0.0
    total = 0.0
    for s in sources:
        if not isinstance(s, dict):
            continue
        w = s.get("weight")
        if isinstance(w, (int, float)):
            total += float(w)
    return min(total, CONFIDENCE_CAP)


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
