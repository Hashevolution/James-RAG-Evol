"""v0.6 G8.c — pack mount/unmount dispatch helpers for replay_graph.

Per `docs/reviews/v0.5-b3-plugin-api-stability.md` §4.4. Lives in
its own module so `core/lifecycle/replay_graph.py` (already at
~22 KB grandfathered, over the 20 KB cap) doesn't grow further.

This module owns:

  * The no-op handlers
    :func:`handle_ontology_pack_mounted` /
    :func:`handle_ontology_pack_unmounted` that satisfy
    ``replay_graph.py``'s `set(_HANDLERS) == set(LIFECYCLE_
    EVENT_TYPES)` assertion. The actual mounted-packs tracking
    happens in the dispatch loop, not the handlers (the handlers
    are just registry stubs to keep the existing
    ``edges / chains / invalidated`` projection clean).
  * :func:`apply_pack_event` — the dispatch-loop helper that
    updates a caller-supplied ``mounted_pack_ids`` list when the
    incoming event is a pack mount/unmount. Idempotent on
    duplicate mount; removes-if-present on unmount.

The replay-side filter integration (G1.b tenant filter) and the
edge-state handlers stay in ``replay_graph.py``. This module is
a pure-helper carve-out for the pack projection.
"""
from __future__ import annotations

from typing import Any, Dict, List

from core.lifecycle.replay_audit import (
    EVT_ONTOLOGY_PACK_MOUNTED,
    EVT_ONTOLOGY_PACK_UNMOUNTED,
)


def handle_ontology_pack_mounted(
    edges: Dict[str, Dict[str, Any]],
    chains: Dict[str, List[str]],
    invalidated: set,
    payload: Dict[str, Any],
) -> None:
    """No-op handler — pack tracking happens in
    :func:`apply_pack_event`, called by the dispatch loop. The
    handler registry needs an entry for every
    ``LIFECYCLE_EVENT_TYPES`` member; this satisfies the assertion.
    """
    return


def handle_ontology_pack_unmounted(
    edges: Dict[str, Dict[str, Any]],
    chains: Dict[str, List[str]],
    invalidated: set,
    payload: Dict[str, Any],
) -> None:
    """No-op handler — pack tracking happens in
    :func:`apply_pack_event`."""
    return


def apply_pack_event(
    event_type: str,
    payload: Dict[str, Any],
    mounted_pack_ids: List[str],
) -> None:
    """Update ``mounted_pack_ids`` from a pack mount/unmount event.

    Args:
        event_type: the event row's ``event_type`` field. Only
            :data:`EVT_ONTOLOGY_PACK_MOUNTED` and
            :data:`EVT_ONTOLOGY_PACK_UNMOUNTED` are acted on;
            everything else is a no-op.
        payload: parsed event payload dict.
        mounted_pack_ids: mutable list of currently-mounted pack
            ids (in registration order). Mutated in place.

    Semantics:
      * Mount with non-string / empty / duplicate ``pack_id`` →
        no-op (defensive).
      * Unmount with non-string / empty / not-currently-mounted
        ``pack_id`` → no-op (silent — matches the rest of the
        replay layer's "skip malformed rows" stance).
    """
    if event_type == EVT_ONTOLOGY_PACK_MOUNTED:
        pid = payload.get("pack_id")
        if isinstance(pid, str) and pid and pid not in mounted_pack_ids:
            mounted_pack_ids.append(pid)
        return
    if event_type == EVT_ONTOLOGY_PACK_UNMOUNTED:
        pid = payload.get("pack_id")
        if isinstance(pid, str) and pid in mounted_pack_ids:
            mounted_pack_ids.remove(pid)
        return


__all__ = (
    "handle_ontology_pack_mounted",
    "handle_ontology_pack_unmounted",
    "apply_pack_event",
)
