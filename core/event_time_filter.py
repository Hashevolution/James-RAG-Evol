"""PROJECT JAMES — Event time-bucket filter (PR-11c).

문서: docs/design/v0.3-graph-evolution.md §5.3

`event` 노드는 ``occurred_at`` 필드를 갖는 시간 축 entity. 본 모듈은
entity dict 리스트에서 occurred_at 윈도우 필터를 적용하는 helper
를 제공한다. retrieval / admin / snapshot 어느 entry 에서도 같은
필터 함수를 호출해 결과를 일관되게 제한할 수 있다.

설계 메모 §5.3 의 두 규칙:
  - filter 가 retrieval scoring 이후 적용되는 hard cut (re-weight 가
    아닌 cut). 호출자는 이미 score 정렬된 결과에 본 함수를 적용한다.
  - non-event entity (occurred_at 없음) 는 ``occurred_after`` 와
    ``occurred_before`` 가 **모두 absent** 일 때만 통과. 즉 time-scoped
    query 는 암묵적으로 event 노드로 제한된다 — 사용자가 시간을
    명시했으면 시간 없는 노드는 답이 아니다.

본 모듈은 `core/relations_schema.py` 의 ``validate_occurred_at`` 을
재사용해 bound 자체의 ISO 8601 파싱을 강제한다. malformed entity
의 occurred_at 은 raise 가 아닌 silent drop — 한 entity 의 dirty
metadata 가 전체 filter 결과를 죽이지 않도록 한다.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from core.relations_schema import validate_occurred_at


def _parse_iso(value: str) -> Optional[datetime]:
    """Best-effort ISO 8601 parse. Returns ``None`` on failure (used in
    the per-entity loop so a dirty entity does not raise).

    Accepts trailing ``Z`` via the standard ``+00:00`` substitution.
    Naive datetimes are accepted (no tz attached); the filter treats
    them as workspace-local just like the storage path does.
    """
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _coerce_naive(dt: datetime) -> datetime:
    """Strip tzinfo so naive and tz-aware datetimes can be compared
    side-by-side. JAMES treats stored occurred_at as workspace-local
    when no offset is present (memo §4.1).
    """
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def entity_within_time_bucket(
    entity: Dict[str, Any],
    occurred_after: Optional[str],
    occurred_before: Optional[str],
) -> bool:
    """Decide whether one entity passes the (after, before) window.

    Rules (memo §5.3):
      - both bounds absent → every entity passes (no filter active).
      - either bound set:
          * non-event entities (no `occurred_at` field) are dropped.
          * event entities with malformed `occurred_at` are dropped
            silently (one bad entity must not poison the result set).
          * event entities are kept iff occurred_at lies in the
            (after, before) closed interval.
    """
    if occurred_after is None and occurred_before is None:
        return True

    raw = entity.get("occurred_at")
    if raw is None:
        return False
    ts = _parse_iso(raw)
    if ts is None:
        return False
    ts = _coerce_naive(ts)

    if occurred_after is not None:
        lo = _parse_iso(occurred_after)
        if lo is None:
            # bound itself is unparseable — caller should have caught
            # earlier via validate_occurred_at, but defend in depth.
            return False
        if ts < _coerce_naive(lo):
            return False

    if occurred_before is not None:
        hi = _parse_iso(occurred_before)
        if hi is None:
            return False
        if ts > _coerce_naive(hi):
            return False

    return True


def filter_entities_by_time_bucket(
    entities: List[Dict[str, Any]],
    *,
    occurred_after: Optional[str] = None,
    occurred_before: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Filter ``entities`` to those passing the time-bucket window.

    Validates the bounds eagerly via ``validate_occurred_at`` so the
    caller gets a clear ``ValueError`` for a malformed param. Per-entity
    parsing is best-effort (see ``entity_within_time_bucket``).

    Order preserved — callers that already sorted by relevance keep
    the same ordering in the filtered output (hard cut, not re-rank).
    """
    if occurred_after is not None:
        validate_occurred_at(occurred_after)
    if occurred_before is not None:
        validate_occurred_at(occurred_before)

    return [
        e for e in entities
        if entity_within_time_bucket(e, occurred_after, occurred_before)
    ]


__all__ = [
    "entity_within_time_bucket",
    "filter_entities_by_time_bucket",
]
