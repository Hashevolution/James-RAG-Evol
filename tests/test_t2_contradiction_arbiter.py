"""v0.4 Sprint 5 PR-T2.A — contract tests for classify_contradiction.

12 parametrized branches per the entry memo §"PR-T2.A Tests"
covering each rule + edge cases + the literal return type.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.lifecycle.contradiction_arbiter import (  # noqa: E402
    classify_contradiction,
)


NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def _edge(
    valid_from: str | None = "2026-04-01T00:00:00+00:00",
    valid_to:   str | None = None,
    source_weight: float | None = 0.7,
) -> dict:
    """Minimal v0.4 edge with one source. Tests override individual
    fields to exercise each rule."""
    sources = []
    if source_weight is not None:
        sources.append({
            "doc_id":      "doc_old",
            "role":        "primary",
            "ts":          "2026-04-01T00:00:00+00:00",
            "weight":      source_weight,
            "valid_from":  None,
            "valid_until": None,
        })
    return {
        "confidence":    source_weight or 0.0,
        "target":        "Target",
        "target_id":     "e_concept_t",
        "type":          "RELATED_TO",
        "sources":       sources,
        "validity":      {"from": valid_from, "to": valid_to},
        "status":        {"active": True, "superseded_by": None, "superseded_at": None},
        "mutation_type": "active",
    }


def _fact_world_changed() -> dict:
    """new_fact.valid_from > old_edge.validity.to (rule 1)."""
    return {
        "valid_from": "2026-07-01T00:00:00+00:00",
        "timestamp":  "2026-07-01T00:00:00+00:00",
        "weight":     0.7,
    }


def _fact_correction(weight: float = 0.95) -> dict:
    """Higher-confidence + retroactive (rule 2)."""
    return {
        "valid_from": "2026-04-01T00:00:00+00:00",
        "timestamp":  "2026-03-01T00:00:00+00:00",  # before old edge's vf
        "weight":     weight,
    }


def _fact_duplicate(ts: str, weight: float | None = 0.7) -> dict:
    """Inside old window + same confidence (rule 3)."""
    return {
        "valid_from": ts,
        "timestamp":  ts,
        "weight":     weight,
    }


# ─── Rule 1 — B_supersede (world changed) ─────────────────────────


def test_rule1_new_valid_from_after_old_validity_to():
    """new.valid_from > old.validity.to → B_supersede"""
    edge = _edge(valid_from="2026-04-01T00:00:00+00:00",
                 valid_to="2026-05-01T00:00:00+00:00")
    fact = _fact_world_changed()
    assert classify_contradiction(edge, fact, now=NOW) == "B_supersede"


def test_rule1_new_valid_from_after_now_when_old_validity_to_is_open():
    """old.validity.to=None → use now as cutoff. new.vf > now → B."""
    edge = _edge(valid_from="2026-04-01T00:00:00+00:00", valid_to=None)
    fact = _fact_world_changed()   # vf 2026-07-01 > now 2026-06-01
    assert classify_contradiction(edge, fact, now=NOW) == "B_supersede"


# ─── Rule 2 — A_invalidate (retroactive correction) ───────────────


def test_rule2_higher_confidence_retroactive_invalidates():
    """new.weight > old.weight AND new.ts ≤ old.validity.from → A."""
    edge = _edge(valid_from="2026-04-01T00:00:00+00:00",
                 valid_to="2026-05-31T00:00:00+00:00",
                 source_weight=0.7)
    fact = _fact_correction(weight=0.95)
    assert classify_contradiction(edge, fact, now=NOW) == "A_invalidate"


def test_rule2_equal_confidence_does_not_invalidate():
    """new.weight == old.weight → rule 2 fails, falls to rule 4 default
    (B_supersede). Pins the strict-greater contract."""
    edge = _edge(source_weight=0.7,
                 valid_from="2026-04-01T00:00:00+00:00",
                 valid_to="2026-05-31T00:00:00+00:00")
    fact = _fact_correction(weight=0.7)  # equal
    # new.timestamp is 2026-03-01 (before old.vf 2026-04-01) so it's
    # outside the window — rule 3 doesn't apply. Falls to rule 4.
    assert classify_contradiction(edge, fact, now=NOW) == "B_supersede"


def test_rule2_lower_confidence_does_not_invalidate():
    """new.weight < old.weight → rule 2 fails."""
    edge = _edge(source_weight=0.9,
                 valid_from="2026-04-01T00:00:00+00:00",
                 valid_to="2026-05-31T00:00:00+00:00")
    fact = _fact_correction(weight=0.5)
    assert classify_contradiction(edge, fact, now=NOW) == "B_supersede"


def test_rule2_higher_confidence_but_later_timestamp_falls_through():
    """new.weight > old.weight BUT new.ts > old.validity.from → rule 2
    fails (not retroactive). Falls through to rule 4 default."""
    edge = _edge(valid_from="2026-04-01T00:00:00+00:00",
                 valid_to="2026-05-31T00:00:00+00:00",
                 source_weight=0.7)
    fact = {
        "valid_from": "2026-04-15T00:00:00+00:00",
        "timestamp":  "2026-04-15T00:00:00+00:00",   # AFTER old.vf
        "weight":     0.95,
    }
    # rule 1: new.vf 2026-04-15 vs old.vt 2026-05-31 → not later, skip
    # rule 2: new.ts > old.vf → not retroactive, skip
    # rule 3: inside window + confidence delta → skip (≠)
    # rule 4: B_supersede
    assert classify_contradiction(edge, fact, now=NOW) == "B_supersede"


# ─── Rule 3 — ignore (duplicate inside window, same confidence) ───


def test_rule3_duplicate_inside_window_same_confidence():
    """new.ts inside old.validity + new.weight == old.weight → ignore."""
    edge = _edge(valid_from="2026-04-01T00:00:00+00:00",
                 valid_to="2026-08-01T00:00:00+00:00",
                 source_weight=0.7)
    fact = _fact_duplicate(ts="2026-05-15T00:00:00+00:00", weight=0.7)
    assert classify_contradiction(edge, fact, now=NOW) == "ignore"


def test_rule3_duplicate_inside_window_no_confidence_either_side():
    """Neither carries weight → treat as equivalent → ignore."""
    edge = _edge(valid_from="2026-04-01T00:00:00+00:00",
                 valid_to="2026-08-01T00:00:00+00:00",
                 source_weight=None)
    fact = _fact_duplicate(ts="2026-05-15T00:00:00+00:00", weight=None)
    assert classify_contradiction(edge, fact, now=NOW) == "ignore"


def test_rule3_inside_window_different_confidence_falls_through():
    """Inside window but confidence delta exists → rule 3 doesn't
    fire; rule 4 default (B_supersede)."""
    edge = _edge(valid_from="2026-04-01T00:00:00+00:00",
                 valid_to="2026-08-01T00:00:00+00:00",
                 source_weight=0.7)
    fact = _fact_duplicate(ts="2026-05-15T00:00:00+00:00", weight=0.9)
    # rule 1: new.vf 2026-05-15 < old.vt 2026-08-01 → skip
    # rule 2: new.ts > old.vf → not retroactive → skip
    # rule 3: inside window BUT confidence differs → skip
    # rule 4: B
    assert classify_contradiction(edge, fact, now=NOW) == "B_supersede"


# ─── Rule 4 — default (edge cases) ────────────────────────────────


def test_rule4_missing_timestamps_defaults_to_supersede():
    """Both new.valid_from and new.timestamp missing → rules 1/2/3 all
    skip → rule 4 fires."""
    edge = _edge()
    fact = {"weight": 0.7}   # no valid_from, no timestamp
    assert classify_contradiction(edge, fact, now=NOW) == "B_supersede"


def test_rule4_missing_confidence_does_not_block_rules_1_3():
    """Even without confidence, rule 1 (world change) and rule 3
    (duplicate-by-time) still work. This pins that rule 4 is a
    last resort, not a first-call fallback."""
    edge = _edge(valid_from="2026-04-01T00:00:00+00:00",
                 valid_to="2026-05-01T00:00:00+00:00",
                 source_weight=None)
    fact = {"valid_from": "2026-07-01T00:00:00+00:00",
            "timestamp":  "2026-07-01T00:00:00+00:00"}
    # rule 1 fires (vf 2026-07-01 > old.vt 2026-05-01)
    assert classify_contradiction(edge, fact, now=NOW) == "B_supersede"


def test_rule4_malformed_iso_strings_fall_to_default():
    """Garbage in valid_from / timestamp → parsers return None →
    rules 1/2/3 all skip → rule 4 fires."""
    edge = _edge(valid_from="not-a-date", valid_to="also-not-a-date")
    fact = {"valid_from": "not-iso", "timestamp": "also-not-iso", "weight": 0.5}
    assert classify_contradiction(edge, fact, now=NOW) == "B_supersede"


# ─── Argument-validation guards ──────────────────────────────────


def test_now_must_be_timezone_aware():
    with pytest.raises(ValueError, match="timezone-aware"):
        classify_contradiction(_edge(), _fact_world_changed(),
                                now=datetime(2026, 6, 1, 12, 0, 0))


def test_now_must_be_datetime():
    with pytest.raises(ValueError, match="datetime"):
        classify_contradiction(_edge(), _fact_world_changed(),
                                now="2026-06-01")


# ─── Parametrized smoke ──────────────────────────────────────────


@pytest.mark.parametrize("expected", ["A_invalidate", "B_supersede", "ignore"])
def test_return_type_is_one_of_three_literals(expected):
    """All three labels reachable — sanity check the literal type."""
    edge = _edge()
    if expected == "A_invalidate":
        fact = _fact_correction(weight=0.95)
    elif expected == "B_supersede":
        fact = _fact_world_changed()
    else:
        fact = _fact_duplicate(ts="2026-05-15T00:00:00+00:00", weight=0.7)
        edge["validity"]["to"] = "2026-08-01T00:00:00+00:00"
    got = classify_contradiction(edge, fact, now=NOW)
    assert got == expected
