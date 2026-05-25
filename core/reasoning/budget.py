"""Adaptive budget — task-weight-driven cap per reasoning stage.

Direction 1 of the v0.3.x measurement framework follow-up
(`docs/handovers/v0.3.x-measurement-framework-track.md §Stage 2.A`).

PR #399 raised every reasoning-stage cap from 200/400/400/400 to 4096 so
that V3'.a/.b/.c/.d (`gemma4:e4b` 4-stage cognitive sweep) would stop
emitting empty responses at the ~500-token hidden reasoning floor.
4096 is safe but wasteful: V3'.e and V3'.a~d measurements show the
actual `eval_count` lands at ~62 (substitution) to ~520 (heavy synthesis)
depending on task weight, so a one-size cap pays ~8x for the heavy path
and ~70x for the substitution path.

`TaskBudget.assess(stage, prompt)` returns a `num_predict` cap matched
to the task weight of the call:

  • substitution-pattern detected (verbatim retrieval imperative)
      → CAP_SUBSTITUTION = 200
    matches V3'.e substitution arm 20/20 at cap=400 with eval_count=62
    flat. 200 leaves 3x headroom over the observed flatline.

  • heavy-synthesis marker (multi-step / structured / 4-stage cognitive)
      → CAP_HEAVY = 4096
    matches PR #399's safe default; V3'.a~d showed all 4 stages reach
    10/10 at this cap.

  • default (light synthesis: single recommendation, short answer,
    cognitive-middleware critique / fact-check / query rewrite)
      → CAP_LIGHT = 1200  [v2 — heuristic bumped 2026-05-24]
    Direction 1 cognitive-stages sweep (N=20, gemma4:e4b, T=0.2)
    measured natural-stop lengths across the 4 middleware prompts:
      query_rewriter natural-stop ~377
      planner        natural-stop ~670 (heavy-escalated)
      reflect        natural-stop ~926
      verify         natural-stop ~984
    The v1 value (CAP_LIGHT=800) covered query_rewriter cleanly but
    truncated reflect and verify in 19/20 calls each, causing -40% /
    -75% quality regression respectively. CAP_LIGHT=1200 covers verify
    (984) with ~20% headroom and stays 5x larger than V3'.e light
    synth's natural-stop of ~235, so the original e-commerce
    light-synthesis use case is unaffected.

Fallback: if a stage downstream sees `done_reason=length` (model hit
the cap before finishing), the caller can use `retry_doubled` to re-run
with the next-tier cap up to CAP_HEAVY.

Vocabulary anchor — Robin Converse's 2026-05-24 LinkedIn endorsement
established that *"parameter count buys reasoning routing precision,
not just capacity"* is the line that travels. This module is the
JAMES-side realization of that framing on the *task-weight* axis:
budget decisions route compute against task type, not against a fixed
floor. Direction 5 (Auto-routing) will layer model selection on top
of the same surface.
"""

from __future__ import annotations

import re
from typing import Final, Literal

ReasoningStage = Literal[
    "query_rewriter",
    "planner",
    "reflect",
    "verify",
    "synth",
]

# Cap tiers — sourced from V3' measurement data.
# v1 (2026-05-24): CAP_LIGHT = 800 — bumped to 1200 (v2) after the
# cognitive-stages sweep showed reflect (natural-stop 926) and verify
# (984) truncate at 800.
CAP_SUBSTITUTION: Final[int] = 200
CAP_LIGHT: Final[int] = 1200
CAP_HEAVY: Final[int] = 4096

# Substitution-pattern regex — imperative "return verbatim" / "as-is".
# Catches Korean / English idiomatic forms operators actually type.
_SUBSTITUTION_PATTERNS: Final[tuple[str, ...]] = (
    r"그대로\s*(?:알려|보여|보내|반환|출력)",
    r"원문\s*(?:그대로)?",
    r"문구\s*(?:그대로)?",
    r"\bverbatim\b",
    r"\bas[-\s]is\b",
    r"\breturn\s+(?:the\s+)?(?:exact|literal|verbatim)\b",
    r"copy[-\s]paste",
)
_SUBSTITUTION_REGEX: Final[re.Pattern[str]] = re.compile(
    "|".join(_SUBSTITUTION_PATTERNS),
    re.IGNORECASE,
)

# Heavy-synthesis markers — multi-step / structured / 4-stage cognitive.
# A single occurrence is sufficient to escalate to CAP_HEAVY because
# false-negatives (light query routed to heavy cap) cost 5x tokens
# but false-positives (heavy query routed to light cap) cost a
# done_reason=length retry — the asymmetry favours escalation.
_HEAVY_MARKERS: Final[tuple[str, ...]] = (
    "단계",
    "분석해",
    "분기",
    "쪼개",
    "decompose",
    "step by step",
    "step-by-step",
    "compare",
    "비교",
    "4-stage",
    "multi-step",
    "철저히",
    "구조적으로",
)
_HEAVY_REGEX: Final[re.Pattern[str]] = re.compile(
    "|".join(re.escape(m) for m in _HEAVY_MARKERS),
    re.IGNORECASE,
)


class TaskBudget:
    """Per-stage adaptive cap assessor.

    Stateless. Safe to call concurrently. Designed to be a drop-in
    replacement for hardcoded `max_tokens=DEFAULT_MAX_TOKENS` arguments
    at the 5 reasoning-stage call sites.
    """

    __slots__ = ()

    def assess(
        self,
        stage: ReasoningStage,
        prompt: str,
        context: str = "",
    ) -> int:
        """Return the cap appropriate for this stage + prompt.

        Args:
            stage: reasoning-stage identifier (see ReasoningStage).
            prompt: the prompt string the stage is about to send.
            context: optional retrieval context. Currently unused by the
                heuristic; reserved for Direction 2 (Task-weight metric)
                which will add context-aware signals (entropy, vocab
                depth, etc.).

        Returns:
            num_predict cap in tokens. One of {CAP_SUBSTITUTION,
            CAP_LIGHT, CAP_HEAVY}.

        Notes:
            • Substitution detection only runs for stages that can serve
              verbatim output (`query_rewriter`, `synth`). The cognitive
              middleware stages (`planner`, `reflect`, `verify`) always
              require synthesis — substitution patterns inside their
              prompts describe the *user's* request, not what the stage
              itself emits.
            • Heavy-synthesis markers are checked across all stages
              because a multi-step user query implies multi-step
              decomposition / critique / verification too.
        """
        if stage in ("query_rewriter", "synth"):
            if _SUBSTITUTION_REGEX.search(prompt):
                return CAP_SUBSTITUTION

        if _HEAVY_REGEX.search(prompt):
            return CAP_HEAVY

        return CAP_LIGHT


def retry_doubled(prev_cap: int, max_cap: int = CAP_HEAVY) -> int:
    """Return the next-tier cap when a previous call hit done_reason=length.

    Used by the call-site retry path: if the model emits length-truncation,
    re-issue with this cap. Bounded by `max_cap` (default CAP_HEAVY) so
    a misclassified substitution cannot escalate beyond the safe ceiling.

    Args:
        prev_cap: the cap used in the previous (truncated) call.
        max_cap: ceiling for the retry. Default CAP_HEAVY.

    Returns:
        min(prev_cap * 2, max_cap). Returns `max_cap` when prev_cap is
        already at or beyond the ceiling.
    """
    return min(prev_cap * 2, max_cap)


def complete_with_retry(
    backend,
    prompt: str,
    *,
    cap: int,
    max_cap: int = CAP_HEAVY,
    timeout: float = 60.0,
    stage: str = "",
    **opts,
):
    """Call `backend.complete(prompt, max_tokens=cap, …)` and retry once
    with `retry_doubled(cap, max_cap)` if the response is truncated.

    D6 (2026-05-25) — closes the design ↔ wiring gap where the
    `retry_doubled` helper existed but no call site invoked it.

    Retry trigger: `result.done_reason == "length"`. Backends that
    don't track `done_reason` (legacy / future plugin backends)
    leave it empty → no retry — pre-D6 behavior is preserved.

    Single retry only — bounded by `max_cap` (default `CAP_HEAVY`).
    A misclassified light task that was already at `CAP_HEAVY` won't
    spiral; `retry_doubled` saturates at the ceiling.

    `cap` and `max_cap` are integers in the same token unit
    `backend.complete` accepts via `max_tokens`. `**opts` is
    forwarded as-is on both the first and the retry call.

    `stage` — optional caller identifier used for the audit row
    emitted when a retry actually fires (`reason:retry` endpoint).
    Empty string falls back to the backend_id read off the
    `CompletionResult`. The audit emit is try/except-wrapped — an
    audit failure never blocks the production call path.

    Returns the `CompletionResult` of the **retry** when one was
    issued, otherwise the first call's result.
    """
    result = backend.complete(
        prompt,
        max_tokens=cap,
        timeout=timeout,
        **opts,
    )
    if not getattr(result, "done_reason", "") == "length":
        return result
    retried_cap = retry_doubled(cap, max_cap=max_cap)
    if retried_cap <= cap:
        # Already at the ceiling — retry would change nothing.
        return result

    # D6 audit emit — record the retry decision so operators can
    # monitor truncation hits + tune heuristics in v3/v4 falsification
    # cycles. Schema: endpoint="reason:retry", query=stage or
    # backend_id, answer="cap_before=X cap_after=Y backend=Z
    # prompt={hash8}".
    try:
        import hashlib
        from core.audit_bridge import mirror_to_audit_db

        backend_id = getattr(result, "backend_id", "") or "unknown"
        prompt_hash = (
            hashlib.sha256(prompt.encode("utf-8", errors="ignore")).hexdigest()[:8]
            if prompt
            else ""
        )
        # NOTE: `audit_bridge._resolve_query` reads `target` / `path` /
        # `tool_used` keys, not `query`. So we put the stage in `target`
        # to actually land in the SQL `query` column.
        mirror_to_audit_db({
            "endpoint": "reason:retry",
            "role": "system",
            "target": stage or backend_id,
            "cap_before": cap,
            "cap_after": retried_cap,
            "backend": backend_id,
            "prompt_hash": prompt_hash,
        })
    except Exception:
        pass

    return backend.complete(
        prompt,
        max_tokens=retried_cap,
        timeout=timeout,
        **opts,
    )


__all__ = [
    "CAP_SUBSTITUTION",
    "CAP_LIGHT",
    "CAP_HEAVY",
    "ReasoningStage",
    "TaskBudget",
    "complete_with_retry",
    "retry_doubled",
]
