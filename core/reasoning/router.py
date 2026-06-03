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

# Canonical legacy backend ID. Matches the always-registered
# `core.reasoning.backends.ollama_local.OllamaLocalBackend` (see
# `core.reasoning.backends.__init__._autoregister`). This is a
# **registry key**, NOT a model tag — `JAMES_LLM_MODEL` controls
# which model the backend asks Ollama for and is passed via
# `backend.complete(model=...)`, never as a backend ID.
_DEFAULT_BACKEND_ID: Final[str] = "ollama_local"

_FLAG_ON_VALUES: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})

# LEO L.B — evidence-scope routing thresholds.
# narrow: scope ≤ 0.30 → small backend (single-doc / verbatim
#   retrieval shape — V3'.e substitution arm signature).
# wide:   scope ≥ 0.70 → large/medium backend (multi-doc + graph
#   fan-out — multi-hop synthesis burden, "shortening the path" applies).
# mid-band (0.30 < scope < 0.70) → fall through to budget-based rule,
#   so D1 task-weight signal still owns the gray zone.
# Module constants so L.D STEP 7 tuning (or Direction 2 regression)
# can swap them in one place without API change. Mirrors the
# `_W_*` weight constants in `core.reasoning.evidence_scope`.
_SCOPE_NARROW_THRESHOLD: Final[float] = 0.30
_SCOPE_WIDE_THRESHOLD: Final[float] = 0.70


def _auto_router_enabled() -> bool:
    """Env-flag gate for D5.

    Default OFF — `JAMES_AUTO_ROUTER=1` (or `true` / `yes` / `on`)
    activates the routing. Until then, `Router()` returns the legacy
    backend on every call → byte-identical to pre-D5 main.

    Mirrors `core.retrieval.query_rewriter._adaptive_budget_enabled`.
    """
    return os.getenv("JAMES_AUTO_ROUTER", "0").strip().lower() in _FLAG_ON_VALUES


def force_cloud_enabled() -> bool:
    """Direction α — operator-explicit cloud routing gate.

    Default OFF — `JAMES_FORCE_CLOUD=1` (or `true` / `yes` / `on`)
    instructs `trace_synth_call` (and any other call site that opts in)
    to wrap synth-stage egress through `core.abstraction.run_cloud_egress`
    instead of calling `backend.complete` directly.

    Self-policing: when the flag is ON but the resolved backend's
    capability is not `provider="cloud"`, the caller logs a warning and
    proceeds with the normal `backend.complete` path — wrapping a local
    backend in abstraction would be a confusing no-op.

    Public (unprefixed) name so external callers — e.g. the planner /
    verify / reflect call sites — can opt in symmetrically once the
    end-to-end shape is proven on synth. Mirrors the public surface of
    `core.retrieval.query_rewriter.adaptive_budget_enabled`.
    """
    return os.getenv("JAMES_FORCE_CLOUD", "0").strip().lower() in _FLAG_ON_VALUES


def _legacy_backend_id() -> str:
    """Return the registry backend ID for the pre-D5 default path.

    The registry's always-auto-registered key is ``"ollama_local"``;
    that is the canonical legacy. ``JAMES_LEGACY_BACKEND`` env can
    override (test injection point — pass a stub backend's registered
    name); empty / unset / unknown → ``_DEFAULT_BACKEND_ID``.

    Pre-2026-05-27 this function read ``JAMES_LLM_MODEL``, treating
    the value as a backend ID. That was an L0/D5.A oversight:
    ``JAMES_LLM_MODEL`` is a **model tag** (e.g. ``"gemma4:e4b"``)
    passed to ``backend.complete(model=...)``, not a registry key.
    The conflation caused ``get_backend("gemma4:e4b")`` to ``KeyError``
    on every routing fallback path under ``JAMES_AUTO_ROUTER=1`` when
    no large/medium-tier backend was registered — the small-tier-only
    fleet scenario the D5 closure result doc promised would just emit
    extra audit rows.
    """
    requested = os.getenv("JAMES_LEGACY_BACKEND", "").strip()
    return requested or _DEFAULT_BACKEND_ID


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
    *,
    evidence_scope: Optional[float] = None,
) -> str:
    """Routing policy — D5.C.1 + LEO L.B.

    Decision tree (first match wins):

      1. `stage` ∈ ``_GROUNDING_CRITICAL_STAGES`` (currently just
         ``verify``) → prefer ``large`` tier; fall back to
         ``medium`` if no large registered; legacy otherwise.
         Grounding-critical stage wins over every other signal,
         including measured evidence scope — a thorough verifier
         is the whole point of `verify`.
      2. **LEO L.B — measured evidence scope override**
         (``evidence_scope`` not None):
           • scope ≤ ``_SCOPE_NARROW_THRESHOLD`` (0.30) → ``small``
             tier; legacy otherwise. Narrow retrieval = single
             doc / verbatim arm = small model is sufficient and
             cheaper. Matches Robin's 2026-05-23 substitution
             bit-for-bit finding.
           • scope ≥ ``_SCOPE_WIDE_THRESHOLD`` (0.70) → ``large`` /
             ``medium`` tier; legacy otherwise. Wide retrieval =
             multi-doc + graph fan-out = synthesis burden, where
             Ali's "shortening the path" cost asymmetry applies.
           • mid-band (0.30 < scope < 0.70) → fall through to the
             budget rules below. Mid-scope is ambiguous; defer to
             D1's task-weight prediction in the gray zone.
         This is the LEO design memo §"Relationship to D5 (not a
         fork)" axis being plugged into the existing tree.
      3. ``budget_signal == CAP_SUBSTITUTION`` (200, verbatim
         retrieval) → prefer ``small`` tier; legacy otherwise.
         Substitution doesn't benefit from a larger model — Robin
         2026-05-23 finding: substitution-mode bypasses sampling
         entirely, so a small model gives bit-for-bit identical
         output cheaper.
      4. ``budget_signal == CAP_HEAVY`` (4096, multi-step / 4-stage
         cognitive) → prefer ``large`` tier; fall back to ``medium``;
         legacy otherwise. Heavy synthesis is where the
         cost-asymmetry argument actually favors a stronger model.
      5. Otherwise (``CAP_LIGHT`` 1200, ``None``, or unknown
         signal) → legacy backend. Light synthesis on small model
         is the v0.3.x default; routing only escalates when one of
         the rules above fires.

    `prompt` and `context` are reserved for D5.C.2 (prompt-surface
    signals) and D5.D (cross-lingual alias resolution).

    LEO open Q #2 answer (intent routing vs synth re-selection):
    measurement wins over prediction — rule 2 sits before rules 3/4
    so a clear scope signal overrides the D1 budget guess. Rule 1
    (verify) still wins over both because grounding is a stage-
    level invariant, not a routing preference.

    LEO open Q #4 answer (7-tier prediction vs evidence_scope
    disagreement): the mid-band fall-through implements "measurement
    can promote/demote one tier" — narrow scope (≤0.30) forces
    small even if budget would say light/legacy; wide scope (≥0.70)
    forces large even if budget would say substitution. The gray
    zone leaves the budget rule untouched, so the override is a
    bounded correction, not a wholesale replacement.

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

    # LEO L.B — measured evidence_scope override (rule 2).
    # Mid-band falls through to budget rules below.
    if evidence_scope is not None:
        if evidence_scope <= _SCOPE_NARROW_THRESHOLD:
            chosen = _first_in_tier("small")
            if chosen:
                return chosen
            return _legacy_backend_id()
        if evidence_scope >= _SCOPE_WIDE_THRESHOLD:
            chosen = _first_in_tier("large") or _first_in_tier("medium")
            if chosen:
                return chosen
            return _legacy_backend_id()
        # mid-band → fall through to budget rule

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
        evidence_scope: Optional[float] = None,
    ) -> str:
        """Return the backend ID to invoke for this call.

        Args:
            stage: reasoning-stage identifier (matches D1's
                `ReasoningStage`).
            prompt: the prompt string the stage is about to send.
            context: optional retrieval context. Reserved for D5.C
                policy + D5.D cross-lingual alias resolution.
            budget_signal: optional cap from `TaskBudget.assess(...)`.
                Substitution-tier → small backend, heavy-tier → large
                backend (D5.C.1 policy).
            evidence_scope: optional ``ScopeBreakdown.scope`` value
                from `core.reasoning.evidence_scope.compute_scope`
                (LEO L.B). When passed (flag ON + L.C engine wiring),
                a narrow scope (≤0.30) forces the small tier; a wide
                scope (≥0.70) forces the large tier; the mid-band
                falls through to the budget rule. `None` (the default
                at L.B before L.C wires the engine) leaves D5.C.1
                behaviour bit-for-bit unchanged.

        Returns:
            Backend ID string (e.g. `"gemma4:e4b"`). When flag OFF,
            always the legacy backend. When flag ON, dispatches to
            `_route_policy` (verify > scope-override > budget rules
            > legacy).
        """
        # Flag-off → legacy backend (byte-identical to pre-D5).
        # Flag-on → policy decides. Wiring at the 5 stage call sites
        # for `budget_signal` landed at D5.C.2; the L.C engine wiring
        # for `evidence_scope` is the next phase (this PR only adds
        # the kwarg surface + policy rule).
        if not self.enabled:
            return _legacy_backend_id()
        return _route_policy(
            stage, prompt, context, budget_signal,
            evidence_scope=evidence_scope,
        )


# ─── D5.C.2 — high-level helpers for stage call sites ─────────────


def _budget_to_tier_label(signal: Optional[int]) -> str:
    """Map a TaskBudget cap to a short tier label for audit / debug."""
    if signal is None:
        return "none"
    if signal == CAP_SUBSTITUTION:
        return "substitution"
    if signal == CAP_LIGHT:
        return "light"
    if signal == CAP_HEAVY:
        return "heavy"
    return f"unknown:{signal}"


def resolve_backend(
    stage: str,
    prompt: str,
    *,
    context: str = "",
    budget_signal: Optional[int] = None,
    evidence_scope: Optional[float] = None,
    fallback_backend_id: Optional[str] = None,
) -> str:
    """High-level helper for stage call sites.

    Replaces ``get_backend(self._backend_id)`` at the 5 cognitive
    call sites (D5.C.2 wiring). Behavior:

      • ``JAMES_AUTO_ROUTER`` flag OFF → returns ``fallback_backend_id``
        (the stage's pre-D5 ``self._backend_id``) or ``_legacy_backend_id()``
        if ``None``. Byte-identical to pre-D5 main.
      • Flag ON → consults ``Router(...).select_backend(stage, prompt, ...)``
        which dispatches to ``_route_policy``.

    Stage call sites pass ``budget_signal`` only when the D1 adaptive
    budget flag is also on (signal is meaningless under D1 flag-off
    because the cap is fixed at ``DEFAULT_MAX_TOKENS=4096`` and
    would unconditionally trigger the CAP_HEAVY branch). Without a
    meaningful signal, the router's policy falls back to legacy.

    ``evidence_scope`` is the measured signal from
    `core.reasoning.evidence_scope.compute_scope` (LEO L.B). The L.C
    engine wiring will be the only caller passing this value; until
    then the kwarg defaults to ``None`` and the L.B policy rule
    (rule 2 in `_route_policy`) is dead code at the production call
    path — flag OFF/ON byte-identical to pre-L.B main.
    """
    r = Router()
    if not r.enabled:
        return fallback_backend_id or _legacy_backend_id()
    return r.select_backend(
        stage,  # type: ignore[arg-type]
        prompt,
        context=context,
        budget_signal=budget_signal,
        evidence_scope=evidence_scope,
    )


def emit_route_event(
    stage: str,
    prompt: str,
    selected_backend: str,
    *,
    budget_signal: Optional[int] = None,
    reason: str = "policy",
    evidence_scope: Optional[object] = None,
) -> None:
    """Emit a ``reason:route`` row to ``audit_log``.

    Stage call sites call this immediately after ``resolve_backend``
    so every routing decision is auditable. Never raises — audit
    failure must not block the production call path (mirrors the
    pattern in ``core.audit_bridge.mirror_to_audit_db``).

    The row schema (mapped onto the existing 11-column ``audit_log``
    table):
      • ``endpoint``  = ``"reason:route"``
      • ``query``     = stage name (call-site identifier)
      • ``answer``    = ``"backend={id} tier={label} reason={why}"``
                        + a short prompt hash for cross-referencing
                        with the originating /query/ row
                        + optional ``evidence_scope`` + 4 components
                        (LEO L.C) when the scope was the routing input

    ``evidence_scope`` accepts a
    ``core.reasoning.evidence_scope.ScopeBreakdown`` (preferred — full
    payload lands in the audit row) or a bare float (just the scalar
    is emitted). ``None`` means "no scope this call" and the audit
    string omits the scope fields entirely → flag-OFF callers stay
    byte-identical to pre-L.C.
    """
    try:
        import hashlib
        from core.audit_bridge import mirror_to_audit_db

        prompt_hash = (
            hashlib.sha256(prompt.encode("utf-8", errors="ignore")).hexdigest()[:8]
            if prompt
            else ""
        )
        tier_label = _budget_to_tier_label(budget_signal)
        scope_fragment = ""
        if evidence_scope is not None:
            payload_fn = getattr(evidence_scope, "as_audit_payload", None)
            if callable(payload_fn):
                payload = payload_fn()
                scope_fragment = " " + " ".join(
                    f"{k}={v}" for k, v in payload.items()
                )
            else:
                try:
                    scope_fragment = (
                        f" evidence_scope={float(evidence_scope):.4f}"
                    )
                except (TypeError, ValueError):
                    scope_fragment = ""
        mirror_to_audit_db({
            "endpoint": "reason:route",
            "role": "system",
            "query": stage,
            "answer": (
                f"backend={selected_backend} tier={tier_label} "
                f"reason={reason} prompt={prompt_hash}"
                f"{scope_fragment}"
            ),
        })
    except Exception:
        pass
