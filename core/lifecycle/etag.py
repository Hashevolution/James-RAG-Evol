"""v0.5 G7 — optimistic-concurrency etag for T7 supersede mutations.

Per `docs/reviews/v0.5-b1-ontology-surface-audit.md` G7: two concurrent
writers can both read the same `old_edge`, both produce a supersede
event, both write back, and the second silently overwrites the first
— losing one supersede.

This module adds an **optimistic-concurrency token** ("etag", same
naming as HTTP) computed deterministically over the edge's stable
identity fields. Writers compare the expected etag against the
current edge's etag before mutating; mismatch raises
`EtagMismatchError`. The caller retries with the fresh head — the
standard optimistic-concurrency pattern.

## Why optimistic, not pessimistic

A pessimistic lock would force the wiki I/O layer to acquire a
process-wide mutex around every edge mutation. That has correctness
appeal but ties JAMES's mutation model to a single-process world,
which contradicts the multi-tenant SaaS direction B.1 flagged.

Optimistic locking lets concurrent readers proceed without
coordination, and only the WRITE step needs to verify the etag is
still current. The caller's retry loop is short because supersede
events are rare per edge (chain length stays small).

## What's hashed

The etag is a SHA-256 hex digest (first 12 hex chars; 48 bits of
entropy is overkill for an in-flight-collision check but matches
the existing `e_edge_<10-hex>` id shape for legibility) computed
over a JSON-canonicalised projection of:

  - `id` — the edge's synthetic id
  - `type` — the relation type
  - `validity.from` / `validity.to` — the temporal window
  - `status.active` / `status.superseded_by` / `status.superseded_at`
  - `mutation_type` — the lifecycle label
  - `sources` — the source-list (each source's `doc_id` + `weight`)

Excluded fields (the etag intentionally does not change when these
mutate):
  - `etag` itself (would self-reference)
  - `confidence` — derived from sources at read time; not load-bearing
  - `label` — display-side; not part of identity
  - Any caller-added unknown keys — robust under schema evolution

## Public API

  - `EtagMismatchError` — raised by `check_edge_etag` and
    `supersede_edge` when the optimistic check fails.
  - `compute_edge_etag(edge) → str` — deterministic hash, no
    side effects.
  - `assign_edge_etag(edge) → str` — populates `edge["etag"]`
    in-place from `compute_edge_etag`, returns the value.
  - `check_edge_etag(edge, expected) → None` — raises
    `EtagMismatchError` if `edge["etag"]` != `expected`.

The supersede integration lives in `core/lifecycle/supersede_chain.py`
— this module is the primitive layer, no T7 logic of its own.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict

from core.lifecycle.schema import (
    T7_EDGE_FIELD_ETAG,
    T7_EDGE_FIELD_MUTATION_TYPE,
    T7_EDGE_FIELD_STATUS,
    T7_EDGE_FIELD_VALIDITY,
)


# Number of hex chars in the etag prefix. 12 hex = 48 bits = collision
# probability < 2^-24 for 1k concurrent mutations to one edge, well
# beyond any realistic concurrent-writer count for one edge.
_ETAG_PREFIX_LEN: int = 12


class EtagMismatchError(RuntimeError):
    """Raised when an optimistic-concurrency etag check fails.

    The caller should re-fetch the current edge head and retry the
    mutation. This is not a programming bug — it is the expected
    signal that a concurrent writer mutated the edge first.
    """

    def __init__(self, expected: str, actual: str, edge_id: str = "?"):
        self.expected = expected
        self.actual = actual
        self.edge_id = edge_id
        super().__init__(
            f"etag mismatch on edge {edge_id!r}: "
            f"expected {expected!r}, actual {actual!r}"
        )


def _canonical_projection(edge: dict) -> Dict[str, Any]:
    """Project an edge dict to the etag-hashable identity subset.

    See module docstring 'What's hashed' for the field list. Missing
    fields normalise to None (NOT empty dict) so a `None` validity
    and an `{}` validity hash identically — they have the same
    semantic ("no temporal window known").
    """
    validity = edge.get(T7_EDGE_FIELD_VALIDITY) or {}
    status = edge.get(T7_EDGE_FIELD_STATUS) or {}

    sources = []
    for src in edge.get("sources") or ():
        if not isinstance(src, dict):
            continue
        sources.append({
            "doc_id": src.get("doc_id"),
            "weight": src.get("weight"),
        })

    return {
        "id":           edge.get("id"),
        "type":         edge.get("type"),
        "validity":     {
            "from": validity.get("from"),
            "to":   validity.get("to"),
        },
        "status":       {
            "active":         status.get("active", True),
            "superseded_by":  status.get("superseded_by"),
            "superseded_at":  status.get("superseded_at"),
        },
        "mutation_type": edge.get(T7_EDGE_FIELD_MUTATION_TYPE),
        "sources":       sources,
    }


def compute_edge_etag(edge: dict) -> str:
    """Deterministic etag for an edge dict.

    Returns a SHA-256 hex prefix of the canonicalised projection.
    Pure function — no side effects. Two structurally-equal edges
    return the same etag.

    Raises ValueError if ``edge`` is not a dict (matches the rest of
    the lifecycle module surface).
    """
    if not isinstance(edge, dict):
        raise ValueError(
            f"edge must be a dict, got {type(edge).__name__}"
        )
    canonical = _canonical_projection(edge)
    serialised = json.dumps(canonical, sort_keys=True,
                            ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(serialised.encode("utf-8")).hexdigest()
    return digest[:_ETAG_PREFIX_LEN]


def assign_edge_etag(edge: dict) -> str:
    """Populate ``edge["etag"]`` from ``compute_edge_etag``.

    Mutates ``edge`` in place; returns the assigned value. Idempotent
    in the sense that calling it twice on an unchanged edge produces
    the same value — but the second call DOES reassign the field
    (so callers can use it as a "force-refresh" primitive too).
    """
    if not isinstance(edge, dict):
        raise ValueError(
            f"edge must be a dict, got {type(edge).__name__}"
        )
    value = compute_edge_etag(edge)
    edge[T7_EDGE_FIELD_ETAG] = value
    return value


def check_edge_etag(edge: dict, expected: str) -> None:
    """Raise ``EtagMismatchError`` if ``edge["etag"]`` != ``expected``.

    The check uses the edge's STORED etag (i.e., the field), not a
    recomputed hash. This means a caller that hasn't yet called
    `assign_edge_etag` on the edge will see ``None`` and trigger
    a mismatch — that's the intended behaviour, since "no etag
    stored" means the edge hasn't been through the optimistic-
    concurrency layer and the caller should re-fetch.
    """
    if not isinstance(edge, dict):
        raise ValueError(
            f"edge must be a dict, got {type(edge).__name__}"
        )
    actual = edge.get(T7_EDGE_FIELD_ETAG)
    if actual != expected:
        raise EtagMismatchError(
            expected=str(expected),
            actual=str(actual) if actual is not None else "<absent>",
            edge_id=str(edge.get("id", "?")),
        )


__all__ = (
    "EtagMismatchError",
    "compute_edge_etag",
    "assign_edge_etag",
    "check_edge_etag",
)
