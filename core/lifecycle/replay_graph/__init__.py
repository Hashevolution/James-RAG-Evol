"""T5.B — read-side ``reconstruct_graph_at(t)`` primitive.

This package is the read-side counterpart of
:mod:`core.lifecycle.replay_audit` (T5.A). It folds the lifecycle
event stream from ``audit_log`` into a deterministic
:class:`GraphSnapshot` for any cutoff time ``t``. Together the two
modules realise the v0.4.2 T5 audit-only invariant (design memo §2 +
§4 I1)::

    ∀ t. reconstruct_graph_at(t) =
        replay of every lifecycle event row whose timestamp ≤ t.

Decision LOCKs (memo §7):

* LOCK 4 — ``reconstruct_graph_at`` is a **pure function**: no DB
  write, no module-level cache mutation, no global state read
  beyond the audit_log SELECT. Determinism is the whole point —
  the same ``(t, audit_log_path)`` pair always produces the same
  snapshot.
* LOCK 5 — the audit-only invariant (I1) is pinned by a contract
  test that monkeypatches the DB read and asserts every byte the
  snapshot depends on came through it (PR-T5.D).

Why pure event-log fold (not DB scan)
-------------------------------------
The whole point of T5 is that an operator can ship the audit_log
to a third party — no wiki snapshot, no graph dump — and the third
party can reproduce the graph state at any past ``t``. That is
"replay invariant" in the corpus-retrieval analysis (PR #712 §6).
If reconstruction touches the wiki on disk, the invariant collapses.

Out of scope for this PR
------------------------
* Mutation-site wiring (T1/T2/T2.D/T6/T7 → ``emit_lifecycle_event``).
  Lands in T5.A.b or T5.B follow-up. Until wiring happens the
  production audit_log has no lifecycle rows, so live integration
  tests stay synthetic (this module's tests INSERT events directly).
* Live-graph equality invariant (I4) against the on-disk wiki.
  PR-T5.D pins it once mutation wiring is in.
* Cross-chain consistency vs :func:`reconstruct_view_at`. PR-T5.C.

## v0.6 package split (CLAUDE.md rule #5)

This package was a single ``core/lifecycle/replay_graph.py`` file
(23.0 KB, over the 20 KB cap) until the v0.6 oversize-module split.
The public API surface is byte-identical — all existing imports
(``from core.lifecycle.replay_graph import reconstruct_graph_at`` /
``GraphSnapshot`` / ``view_from_snapshot``) keep working through
this façade:

  * :mod:`core.lifecycle.replay_graph.snapshot` — ``GraphSnapshot``
    dataclass + ``_empty_snapshot`` factory
  * :mod:`core.lifecycle.replay_graph.handlers` — 9 per-event-type
    handlers + ``_HANDLERS`` dispatch dict + sanity assert
  * :mod:`core.lifecycle.replay_graph.db_read` — ``_default_db_path``
    + ``_read_lifecycle_events`` (the only side-channel)
  * :mod:`core.lifecycle.replay_graph.primitives` —
    ``reconstruct_graph_at``, ``view_from_snapshot``,
    ``_validity_contains``
  * this ``__init__.py`` — re-exports
"""
from __future__ import annotations

# Re-export `sqlite3` at the package root because the legacy single
# file imported it at module scope. Test suites (e.g.
# tests/test_t5_reconstruct_graph_at.py::test_only_reads_the_audit_db)
# monkeypatch ``replay_graph.sqlite3.connect`` to spy on every
# connection the primitive opens — the I1 audit-only invariant test.
# Module objects are shared globally, so a patch through this alias
# also covers ``db_read.sqlite3.connect``.
import sqlite3  # noqa: F401

# ─── re-exports — preserves the pre-split import surface ─────────

from core.lifecycle.replay_graph.snapshot import (  # noqa: F401
    GraphSnapshot,
    _empty_snapshot,
)
from core.lifecycle.replay_graph.handlers import (  # noqa: F401
    _HANDLERS,
    _h_supersede_edge_created,
    _h_supersede_chain_extended,
    _h_cascade_invalidate,
    _h_t1_expiration_cascade,
    _h_t2_dispatch_contradiction,
    _h_t2d_ingest_dispatch,
    _h_backfill_snapshot,
    handle_ontology_pack_mounted,
    handle_ontology_pack_unmounted,
    apply_pack_event,
)
from core.lifecycle.replay_graph.db_read import (  # noqa: F401
    _default_db_path,
    _read_lifecycle_events,
)
from core.lifecycle.replay_graph.primitives import (  # noqa: F401
    reconstruct_graph_at,
    view_from_snapshot,
    _validity_contains,
)


__all__ = [
    "GraphSnapshot",
    "reconstruct_graph_at",
    "view_from_snapshot",
]
