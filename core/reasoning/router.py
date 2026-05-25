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

from core.reasoning.backends import list_backends_by_tier
from core.reasoning.budget import CAP_HEAVY, CAP_LIGHT, CAP_SUBSTITUTION

ReasoningStage = Literal[
    "query_rewriter",
    "planner",
    "reflect",
    "verify",
    "synth",
]

# D5.C.1 routing policy — stages that escalate beyond their budget signal.
# `verify` is grounding-critical (D1 sub-finding: ~12.5% unique across 40
# baseline calls = high-clustering cognitive stage). Even a light budget
# benefits from a stronger model when the task is "is this answer
# grounded in the retrieved context?". Other stages route by budget.
_GROUNDING_CRITICAL_STAGES: Final[frozenset[str]] = frozenset({"verify"})

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


def _first_in_tier(tier: str) -> Optional[str]:
    """Return the first backend declared at `tier`, or None if no
    backend is registered there. Order matches `_REGISTRY` insertion
    order — for v1 we deliberately don't sort by cost/latency. D5.C.2
    or later can layer a preference function.
    """
    candidates = list_backends_by_tier(tier)
    return candidates[0] if candidates else None


def _route_policy(
    stage: str,
    prompt: str,
    context: str,
    budget_signal: Optional[int],
) -> str:
    """D5.C.1 routing policy v1.

    Decision tree (first match wins):

      1. `stage` ∈ ``_GROUNDING_CRITICAL_STAGES`` (currently just
         ``verify``) → prefer ``large`` tier; fall back to
         ``medium`` if no large registered; legacy otherwise.
      2. ``budget_signal == CAP_SUBSTITUTION`` (200, verbatim
         retrieval) → prefer ``small`` tier; legacy otherwise.
         Substitution doesn't benefit from a larger model — Robin
         2026-05-23 finding: substitution-mode bypasses sampling
         entirely, so a small model gives bit-for-bit identical
         output cheaper.
      3. ``budget_signal == CAP_HEAVY`` (4096, multi-step / 4-stage
         cognitive) → prefer ``large`` tier; fall back to ``medium``;
         legacy otherwise. Heavy synthesis is where the
         cost-asymmetry argument actually favors a stronger model
         (Ali's "shortening the path" framing — 26b finds the answer
         in 49 tokens vs e4b's 450).
      4. Otherwise (``CAP_LIGHT`` 1200, ``None``, or unknown
         signal) → legacy backend. Light synthesis on small model
         is the v0.3.x default; routing only escalates when one of
         the rules above fires.

    `prompt` and `context` are reserved for D5.C.2 (prompt-surface
    signals) and D5.D (cross-lingual alias resolution).

    The "prefer tier X, fall back to legacy" pattern means an
    operator who registers only ``ollama_local`` (the default)
    routes everything to ``ollama_local`` — no broken decisions
    when no larger backend is available. Opt-in routing.
    """
    if stage in _GROUNDING_CRITICAL_STAGES:
        chosen = _first_in_tier("large") or _first_in_tier("medium")
        if chosen:
            return chosen
        return _legacy_backend_id()

    if budget_signal == CAP_SUBSTITUTION:
        chosen = _first_in_tier("small")
        if chosen:
            return chosen
        return _legacy_backend_id()

    if budget_signal == CAP_HEAVY:
        chosen = _first_in_tier("large") or _first_in_tier("medium")
        if chosen:
            return chosen
        return _legacy_backend_id()

    # CAP_LIGHT, None, or any unrecognized signal → legacy.
    # Explicit `CAP_LIGHT` branch listed for readability even though
    # it falls through to the same legacy path.
    _ = CAP_LIGHT  # documents the intentional fall-through; satisfies linters
    return _legacy_backend_id()


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
        # D5.C.1: flag-off → legacy backend (byte-identical to pre-D5).
        # flag-on → policy decides (see `_route_policy` for the
        # decision tree). Wiring at the 5 stage call sites lands in
        # D5.C.2 / D5.C.3; until then, `Router` is constructible but
        # not yet consulted by `core/retrieval/*` or
        # `core/reasoning/*` call sites.
        if not self.enabled:
            return _legacy_backend_id()
        return _route_policy(stage, prompt, context, budget_signal)
