"""Auto-routing — per-call backend selection based on task weight.

Direction 5 of the v0.3.x measurement framework follow-up
(`docs/handovers/v0.3.x-direction5-auto-routing-track.md`).

D5 sits **above** the Provider Contract (`core/llm_router.py` /
`core/reasoning/backends/`). It does not change the contract surface;
it decides *which* registered backend gets the call, leaving the
backend invocation path untouched. Pre-D5 behavior:
`JAMES_LLM_MODEL` env wins for every call. With D5 enabled
(`JAMES_AUTO_ROUTER=1`), the router consults a per-call task-weight
signal and selects the appropriate backend.

This module is **D5.A — skeleton only**. Phase plan:
  • D5.A (this PR) — module + flag default OFF + stub policy
    returning the legacy backend regardless of `enabled` state.
  • D5.B — backend registry capability tags.
  • D5.C — actual routing policy + STEP 7 bench in PR body.
  • D5.D — wiki entity `aliases:` + entity_extract resolve
    (cross-lingual RAG option 3, bundled per design memo §Cross-lingual).
  • D5.E — closure result doc + memory sync.

Default-off invariant: with `JAMES_AUTO_ROUTER` unset/0, behavior is
byte-identical to pre-D5 main. Mirrors the
`JAMES_ADAPTIVE_BUDGET` pattern from D1
(`core/retrieval/query_rewriter.py:_adaptive_budget_enabled`).
"""

from __future__ import annotations

import os
from typing import Final, Literal, Optional

ReasoningStage = Literal[
    "query_rewriter",
    "planner",
    "reflect",
    "verify",
    "synth",
]

# Canonical default when neither JAMES_LLM_MODEL nor the router is
# configured. Matches the rest of the codebase's implicit fallback
# (see `core/model_resolver.py`).
_DEFAULT_BACKEND_ID: Final[str] = "gemma4:e4b"

_FLAG_ON_VALUES: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})


def _auto_router_enabled() -> bool:
    """Env-flag gate for D5.

    Default OFF — `JAMES_AUTO_ROUTER=1` (or `true` / `yes` / `on`)
    activates the routing. Until then, `Router()` returns the legacy
    backend on every call → byte-identical to pre-D5 main.

    Mirrors `core.retrieval.query_rewriter._adaptive_budget_enabled`.
    """
    return os.getenv("JAMES_AUTO_ROUTER", "0").strip().lower() in _FLAG_ON_VALUES


def _legacy_backend_id() -> str:
    """Return whatever the rest of the codebase resolves to today.

    Pre-D5, every reasoning call effectively hits `JAMES_LLM_MODEL`
    (or the codebase default when unset). Returning the same value
    here is the contract for `enabled=False` and the D5.A stub
    `enabled=True` branch.
    """
    return os.getenv("JAMES_LLM_MODEL", _DEFAULT_BACKEND_ID) or _DEFAULT_BACKEND_ID


class Router:
    """Per-call backend selector.

    Stateless except for the `enabled` flag captured at construction
    time. Safe to call concurrently.

    D5.A stub: `select_backend` always returns the legacy backend
    regardless of `enabled`. The flag-on branch becomes meaningful at
    D5.C when policy + budget signal land. This preserves the
    default-off invariant during the D5.A/B/C build-up — opting in
    via `JAMES_AUTO_ROUTER=1` is safe at every intermediate PR
    because behavior is unchanged until D5.C ships the policy.
    """

    __slots__ = ("enabled",)

    def __init__(self, *, enabled: Optional[bool] = None) -> None:
        """Create a router instance.

        Args:
            enabled: explicit override. `None` (default) consults the
                env flag. Tests pass an explicit bool.
        """
        self.enabled = _auto_router_enabled() if enabled is None else bool(enabled)

    def select_backend(
        self,
        stage: ReasoningStage,
        prompt: str,
        *,
        context: str = "",
        budget_signal: Optional[int] = None,
    ) -> str:
        """Return the backend ID to invoke for this call.

        Args:
            stage: reasoning-stage identifier (matches D1's
                `ReasoningStage`).
            prompt: the prompt string the stage is about to send.
            context: optional retrieval context. Reserved for D5.C
                policy + D5.D cross-lingual alias resolution.
            budget_signal: optional cap from `TaskBudget.assess(...)`.
                D5.C will use this as the primary routing input
                (substitution-tier → small backend, heavy-tier →
                large backend).

        Returns:
            Backend ID string (e.g. `"gemma4:e4b"`). Currently always
            the legacy backend; D5.C replaces the flag-on branch with
            real policy.
        """
        # D5.A: flag-off and flag-on both return legacy. The branch
        # exists so D5.C can drop policy in without touching call sites.
        if not self.enabled:
            return _legacy_backend_id()
        # D5.C will replace this line with policy(stage, prompt, context, budget_signal)
        return _legacy_backend_id()
