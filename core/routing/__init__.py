"""v0.6.1 Phase 4 — Privacy + Cost Cap primitives (plumb-first).

Phase 4 of the 5-Phase routing build-out. See
``docs/design/v0.6.1-phase4-privacy-cost-cap.md`` for the design
memo and ``docs/reference/routing-matrix.md`` for the phase ladder.

Public API (frozen per design memo §3):

  from core.routing import (
      # privacy gate
      PrivacyCheck, detect_pii, check_query_privacy,
      # cost cap
      CostStatus, CostBudget, default_budget, check_cap,
  )

**Plumb-first contract**: these primitives are populated, not yet
consumed. ``engine.py``, ``call_gemma``, and ``resolve_for_mode``
are unchanged in Phase 4. The Phase 5 wire (cloud egress decision)
will call ``check_query_privacy`` + ``check_cap`` before any
``run_cloud_egress`` call.

Layering vs §5.7.12 / §5.7.13:
  - §5.7.12 / §5.7.13 = per-entity mask / pass / keep-local INSIDE
    a cloud call (already shipped in ``core/abstraction/``).
  - Phase 4 = per-query pre-check that the cloud call can happen
    at all (privacy gate + cost cap).
  These are orthogonal axes. A query can pass Phase 4 and still
  have its individual entities masked by §5.7.12, or fail Phase 4
  (PII / over-cap) and never reach §5.7.12.
"""
from __future__ import annotations

import os

from core.routing.privacy import (
    PrivacyCheck,
    check_query_privacy,
    detect_pii,
)
from core.routing.cost_cap import (
    CostBudget,
    CostStatus,
    check_cap,
    default_budget,
    estimate_usd,
)


def snapshot() -> dict:
    """Routing-side introspection for ``/admin/llm/resolution``.

    Returns the routing build-out phase marker plus the Phase 4
    sub-keys (``privacy`` + ``cost_cap``). ``model_resolver.
    resolution_snapshot()`` merges this dict in. Lives here so the
    resolver stays under the rule-#5 20 KB ceiling and so the
    Phase 5 wire extends this single helper rather than editing
    the resolver again.
    """
    out: dict = {
        "phase": "phase4_privacy_cost_cap_primitives",
    }
    try:
        budget = default_budget()
        cost = budget.status()
        out["cost_cap"] = {
            "cap_usd":      cost.cap_usd,
            "used_usd_est": cost.used_usd_est,
            "used_tokens":  cost.used_tokens,
            "month":        cost.month,
            "under_cap":    cost.under_cap,
            "tally_path":   budget.path,
        }
    except Exception as exc:  # never break the resolver snapshot
        out["cost_cap"] = {"error": f"{type(exc).__name__}: {exc}"}
    out["privacy"] = {
        "force_local_env": os.environ.get(
            "JAMES_PRIVACY_FORCE_LOCAL", "",
        ).strip() == "1",
        "extra_patterns_configured": bool(
            os.environ.get("JAMES_PRIVACY_PII_PATTERNS_EXTRA", "").strip(),
        ),
    }
    return out


__all__ = [
    # privacy
    "PrivacyCheck",
    "detect_pii",
    "check_query_privacy",
    # cost
    "CostStatus",
    "CostBudget",
    "default_budget",
    "check_cap",
    "estimate_usd",
    # introspection
    "snapshot",
]
