"""``core.lifecycle`` — v0.4 Layer 4 Lifecycle Semantics.

This package hosts the EVENT/TEMPORAL track of the v0.4 architectural
shift (`docs/handovers/v0.4.0-sprint5-layer4-first-bundle-entry.md`,
strategic memo `docs/design/v0.4-lifecycle-semantics-roadmap.md`).

Sprint 5 first-bundle scope (v0.4.0):

- ``clock``                 — single ``now()`` helper (locked via
                              entry memo §12.2; monkey-patchable for
                              tests, used by every T1+T7 call site
                              that needs "current time").
- ``expiration_cascade``    — T1 batch (lands at PR-T1.B).
- ``supersede_chain``       — T7 EVENT operations (lands at PR-T7.A).
- ``contradiction_arbiter`` — T2 A/B classifier (lands at PR-T2.A).

This PR (PR-0, validator prep) ships only the package skeleton + the
``clock`` helper. Subsequent PR-T1.A/B + PR-T7.A/B + PR-T2.A/B/C land
the rest.
"""
from __future__ import annotations

from core.lifecycle import clock, schema

__all__ = ["clock", "schema"]
