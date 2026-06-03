"""Cloud-egress runner — orchestrates mask → call → unmask → audit.

Single helper that caller sites use to push a prompt to a cloud backend
under the §5.7.12 / §5.7.13 contract. The runner is the place where the
4 caller obligations are enforced in one spot:

  1. (caller-side) PolicyEngine MUST gate egress BEFORE calling the runner.
     The runner does not authorize — it enforces. If a caller bypasses
     PolicyEngine and reaches the runner, the §5.7.12 invariant is
     already violated; the runner cannot detect that.
  2. (runner) every egress emits one `reason:egress` audit row.
  3. (runner) cloud-introduced placeholders (`flagged` from `unmask_text`)
     are returned alongside the answer — caller surfaces, never strips.
  4. (runner) `keep_local` entities whose name appears in the prompt
     payload are a **refused egress** — the runner returns an error
     `CompletionResult` and emits a `refused_*` audit reason. This is
     defense-in-depth: even if a caller's PolicyEngine accidentally
     authorized an egress that includes an open-world sensitive entity,
     the runner catches it before the cloud sees the prompt.

Returns a `(CompletionResult, flagged)` tuple. Callers unpack and decide
what to do with `flagged` (surface to user, log, block, etc.) — the
runner does not silently strip.

Module-size discipline: this file is the orchestration only. Mask /
unmask in `_mask.py`; policy in `_policy.py`; audit emit in `_audit.py`.
"""
from __future__ import annotations

from typing import Any, Callable, List, Sequence, Tuple

from core.reasoning.backends import Backend, CompletionResult

from core.abstraction._audit import emit_egress_event
from core.abstraction._mask import (
    build_map,
    mask_text,
    unmask_text,
)
from core.abstraction._policy import Decision


def run_cloud_egress(
    *,
    backend: Backend,
    prompt: str,
    entities: Sequence[dict],
    decider: Callable[[dict], Decision],
    stage: str = "synth",
    system: str = "",
    max_tokens: int = 1024,
    timeout: float = 60.0,
    **opts: Any,
) -> Tuple[CompletionResult, List[str]]:
    """Run one prompt through a cloud backend under abstraction.

    Args:
      backend:    a registered cloud-tier `Backend` (per §5.7.8 D5
                  registry). The runner is backend-agnostic; the caller
                  decides which cloud backend to use.
      prompt:     the raw prompt the synth/verify stage would otherwise
                  send. The runner masks BEFORE handing it to the backend.
      entities:   typed graph entity dicts (same shape as
                  `core/graph_typed_filter.py` payloads:
                  `{"name", "entity_type", "entity_id", "sensitive"}`).
                  Drives the mask map + the keep-local refusal check.
      decider:    the per-entity Decision policy. The caller chooses —
                  typically `default_decider(open_world_types=...)` until
                  the §4.2 query-conditioned classifier (S7) lands.
      stage:      stage label for the audit row (`"synth"` / `"verify"`).
      system:     optional system prompt (also masked — names in system
                  text leak just as readily as names in the user prompt).
      max_tokens, timeout, **opts: passed through to `backend.complete`.

    Returns:
      `(CompletionResult, flagged)` tuple.
      • `CompletionResult.text` is the **unmasked** answer — placeholders
        replaced with real names via the local map.
      • `flagged` is the list of cloud-introduced placeholders absent
        from the local map (§5.7.13 invariant #4); never stripped from
        the response (left verbatim in `text`), surfaced separately so
        the caller can decide treatment (UI annotation, refuse-show, …).

    On a refused egress (keep-local name in prompt), returns an error
    `CompletionResult` with `error="refused: keep_local in prompt: …"`
    and an empty `flagged` list. The cloud backend is NOT called.
    On a backend-side error (timeout, network, CLI not found), the
    backend's error `CompletionResult` is returned as-is with the
    unmask step skipped (no answer to unmask).
    """
    amap = build_map(entities, decider)

    # §5.7.13 caller obligation #4 (runner-side defense-in-depth):
    # keep_local entities must not be in the prompt at all on the cloud
    # route. mask_text only replaces names in `forward`; a name in
    # `keep_local` that happens to be in the prompt text would leak
    # unmasked. Refuse the egress entirely.
    leaked = [n for n in amap.keep_local if n in prompt or (system and n in system)]
    if leaked:
        emit_egress_event(
            stage, prompt, backend.backend_id, amap,
            reason=f"refused_keep_local_in_prompt:{','.join(leaked)}",
        )
        return (
            CompletionResult(
                text="",
                backend_id=backend.backend_id,
                error=f"refused: keep_local entities in prompt: {','.join(leaked)}",
            ),
            [],
        )

    masked_prompt = mask_text(prompt, amap)
    masked_system = mask_text(system, amap) if system else ""

    result = backend.complete(
        masked_prompt,
        system=masked_system,
        max_tokens=max_tokens,
        timeout=timeout,
        **opts,
    )

    # Backend reported an error before producing text — emit egress audit
    # (we did egress the masked prompt; the cloud just didn't reply
    # cleanly) and skip the unmask step. No `flagged` because there is
    # no reply text to scan.
    if result.error and not result.text:
        emit_egress_event(
            stage, prompt, backend.backend_id, amap,
            reason=f"backend_error:{result.error[:60]}",
        )
        return (result, [])

    restored, flagged = unmask_text(result.text or "", amap)
    emit_egress_event(
        stage, prompt, backend.backend_id, amap,
        flagged=flagged,
    )

    return (
        CompletionResult(
            text=restored,
            backend_id=result.backend_id,
            model=result.model,
            latency_ms=result.latency_ms,
            error=result.error,
            done_reason=result.done_reason,
        ),
        flagged,
    )


__all__ = ["run_cloud_egress"]
