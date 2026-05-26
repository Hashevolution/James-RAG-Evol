"""Single source of truth for "current time" across the v0.4 Layer 4
EVENT/TEMPORAL track.

Locked at Sprint 5 entry memo §12.2 (2026-05-26). The choice is the
**hybrid** option:

- Production paths call ``clock.now()`` for the current-time signal.
  ``compute_confidence_from_sources`` / expiration cascade /
  ``supersede_edge`` / contradiction arbiter all route through this
  single helper.
- Tests monkey-patch ``clock.now`` to freeze time deterministically::

      monkeypatch.setattr("core.lifecycle.clock.now",
                          lambda: datetime(2026, 6, 1, 12, 0, 0,
                                           tzinfo=timezone.utc))

- The forensic replay primitive (``reconstruct_view_at(head,
  predicate, t)``, lands at PR-T7.A) is the **only** path that
  bypasses ``clock.now()`` — it accepts an explicit ``t`` parameter
  for historical reconstruction.

Why a separate module instead of just calling ``datetime.utcnow()``:

- One monkey-patch point flips the entire EVENT/TEMPORAL clock for
  the test suite. Without this indirection every call site would
  need its own freezer fixture.
- The replay primitive's explicit-``t`` path becomes visually
  distinct from the "current" path — code review can immediately
  tell which calls run "now" vs "as of t".
- Future swaps (e.g., monotonic-clock for ordering, NTP-corrected
  wall-clock for cross-machine replay) are one-file changes.

Time zone policy: ``now()`` returns a **UTC-aware** ``datetime``
(``tzinfo=timezone.utc``). All v0.4 audit rows + validity windows +
supersede timestamps land in UTC. Display-side time-zone conversion
is the UI's responsibility.

The module is dependency-free (stdlib only) so it imports fast and
can be reached from any test fixture without dragging in heavy
modules.
"""
from __future__ import annotations

from datetime import datetime, timezone


def now() -> datetime:
    """Return the current wall-clock time as a UTC-aware ``datetime``.

    This is the single function v0.4 Layer 4 calls when it needs
    "current time" — see module docstring for the design rationale.

    Tests freeze this via::

        monkeypatch.setattr("core.lifecycle.clock.now", lambda: <fixed>)

    Production callers never pass arguments; the function signature
    is intentionally argument-free so the monkey-patch lambda above
    is signature-compatible.
    """
    return datetime.now(timezone.utc)


__all__ = ["now"]
