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

  • default (light synthesis: single recommendation, short answer)
      → CAP_LIGHT = 800
    matches V3'.e synthesis arm — `eval_count` lands ~400-450, so 800
    is 1.8x headroom and the floor finishes inside the budget.

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
CAP_SUBSTITUTION: Final[int] = 200
CAP_LIGHT: Final[int] = 800
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


__all__ = [
    "CAP_SUBSTITUTION",
    "CAP_LIGHT",
    "CAP_HEAVY",
    "ReasoningStage",
    "TaskBudget",
    "retry_doubled",
]
