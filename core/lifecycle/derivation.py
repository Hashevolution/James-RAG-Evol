"""v0.4.1 PR-T6.B — derivation extraction for ingestion-path wiring.

Given a new relation being ingested, populate its ``derived_from``
field (T6.A schema). Two paths per the v0.4.1 entry memo §2
Decision 2 LOCK:

  - **operator-tagged** (default, deterministic): if the caller
    already supplied ``new_rel.derived_from`` as a non-empty list,
    validate against ``validate_edge_t6_derived_from`` and return
    it as-is. This is the Replayable-RAG-safe path — "every claim
    is sourced", same input → same output, no LLM nondeterminism.

  - **LLM-inferred** (flag-gated): when ``JAMES_T6_LLM_DERIVATION=1``
    AND the caller passes an ``llm_provider`` callable, delegate
    to the LLM to suggest derivations from the surrounding context.
    Default OFF preserves the deterministic floor.

The two paths are mutually exclusive within a single call —
operator-tagged wins when present, LLM-inferred only fires when
no operator tag is supplied.

## What this module is NOT

- Not a cascade. ``invalidate_derived_facts`` is T6.C's job.
- Not a writer. The caller is responsible for writing the returned
  list back into the relation dict and persisting to the wiki.
- Not an LLM prompt-builder for production. T6.B ships the
  interface; v0.4.2+ can refine the prompt template + parser as
  the operator-tagged path gathers signal about what derivations
  actually look like in practice.

## Replayable RAG consistency

The operator-tagged path is fully deterministic — same input
produces byte-identical output. The LLM-inferred path is non-
deterministic by construction, and is therefore default OFF; when
enabled, each derivation entry carries an ``llm_provider_id``
(supplied by the caller) so replay can reproduce the inference.
"""
from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional

from core.lifecycle.schema import (
    T6_DERIVATION_INFERRED,
    T6_DERIVATION_OPERATOR,
    T6_DERIVATION_TRANSITIVE,
    T6_EDGE_FIELD_DERIVED_FROM,
    VALID_DERIVATION_TYPES,
    validate_edge_t6_derived_from,
)


# Public type alias for documentation. The callable receives a
# prompt string + the caller's context summary, returns a list of
# proposed derivation dicts. The module validates the output before
# returning to the caller; a malformed return raises ValueError.
LLMDerivationProvider = Callable[
    [str, List[Dict[str, Any]]],
    List[Dict[str, Any]],
]


_FLAG_ENV = "JAMES_T6_LLM_DERIVATION"


def _flag_enabled(explicit: Optional[bool]) -> bool:
    """Resolve the LLM-inferred flag. ``explicit`` overrides the
    env when not None (tests pass True/False directly)."""
    if explicit is not None:
        return bool(explicit)
    return os.environ.get(_FLAG_ENV) == "1"


def _normalize_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Default missing ``derivation`` to ``T6_DERIVATION_OPERATOR``.
    Callers passing a bare ``{base_fact_id: ...}`` get the safer
    operator-tagged label so the schema validator passes downstream.
    """
    out = dict(entry)
    out.setdefault("derivation", T6_DERIVATION_OPERATOR)
    return out


def _validate_chain(
    candidates: List[Dict[str, Any]],
    *,
    context_edges_by_id: Optional[Dict[str, Any]] = None,
    edge_id: Optional[str] = None,
) -> None:
    """Validate the proposed chain via T6.A's validator. Wraps the
    list into a faux edge dict so we can reuse the existing
    ``validate_edge_t6_derived_from`` contract (and its cycle check)."""
    faux_edge: Dict[str, Any] = {T6_EDGE_FIELD_DERIVED_FROM: candidates}
    if isinstance(edge_id, str) and edge_id:
        faux_edge["id"] = edge_id
    validate_edge_t6_derived_from(faux_edge, edges_by_id=context_edges_by_id)


def _build_llm_prompt(
    new_rel: Dict[str, Any],
    context_summary: List[Dict[str, Any]],
) -> str:
    """Minimal v0.4.1 prompt — names the task + lists the candidate
    base edges by id. v0.4.2+ can extend with semantic hints, role
    information, or ontology constraints. Caller-supplied
    ``llm_provider`` is responsible for the actual model call.
    """
    target = new_rel.get("target")
    pred = new_rel.get("type") or new_rel.get("label")
    cand_lines = []
    for c in context_summary[:20]:  # cap context to keep prompt bounded
        cid = c.get("id") or ""
        ctarget = c.get("target") or ""
        ctype = c.get("type") or c.get("label") or ""
        if cid:
            cand_lines.append(f"  - id={cid} predicate={ctype} target={ctarget}")
    cand_block = "\n".join(cand_lines) if cand_lines else "  (no candidates)"
    return (
        f"Identify base facts that the new edge is derived from.\n"
        f"New edge: predicate={pred!r} target={target!r}\n"
        f"Candidate base edges:\n{cand_block}\n"
        f"Return a JSON list of "
        f"{{base_fact_id, derivation}} pairs where derivation is one of "
        f"{sorted(VALID_DERIVATION_TYPES)}. Empty list when no "
        f"derivation is warranted."
    )


def _context_summary(
    context_edges_by_id: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Distill an edges-by-id map into a compact context list. The
    LLM provider sees only ``id`` / ``target`` / ``type`` (no
    sources / no validity / no status) to keep the prompt
    self-contained and the provider's logic simple."""
    if not isinstance(context_edges_by_id, dict):
        return []
    out = []
    for eid, edge in context_edges_by_id.items():
        if not isinstance(edge, dict):
            continue
        out.append({
            "id":     eid,
            "target": edge.get("target"),
            "type":   edge.get("type") or edge.get("label"),
        })
    return out


def extract_derivation_chain(
    new_rel: Dict[str, Any],
    *,
    context_edges_by_id: Optional[Dict[str, Any]] = None,
    llm_provider: Optional[LLMDerivationProvider] = None,
    enable_llm: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """Return the ``derived_from`` list to set on ``new_rel``.

    Resolution order:

      1. **Operator-tagged** — when ``new_rel.derived_from`` is
         already a non-empty list, validate via T6.A's contract
         (including cycle check when ``context_edges_by_id`` is
         provided + ``new_rel`` carries an ``id``) and return it
         as-is. The caller can pre-set the field at ingest time.

      2. **LLM-inferred** — when operator-tagged is absent AND
         ``JAMES_T6_LLM_DERIVATION=1`` (or ``enable_llm=True``)
         AND ``llm_provider`` is supplied, call the provider with
         a prompt + context summary, validate the response shape,
         return it. Each entry's ``derivation`` defaults to
         ``T6_DERIVATION_INFERRED`` if missing.

      3. **Default** — empty list. The caller writes
         ``derived_from: []`` to the wiki via
         ``apply_t6_edge_defaults`` (T6.A migration).

    Args:
        new_rel: the relation being ingested.
        context_edges_by_id: optional map of nearby edges (e.g.,
            other relations on the same entity) — used for both
            cycle checking AND building the LLM prompt context.
        llm_provider: optional callable. Receives (prompt_str,
            context_summary_list); returns a list of derivation
            dicts. Validated against the T6.A schema before return.
        enable_llm: explicit override of the env flag. Tests pass
            True/False; production reads ``JAMES_T6_LLM_DERIVATION``.

    Raises:
        ``ValueError`` when operator-tagged input is malformed OR
        the LLM provider returns an invalid shape.
    """
    if not isinstance(new_rel, dict):
        raise ValueError(
            f"new_rel must be a dict, got {type(new_rel).__name__}"
        )

    # ─── Path 1: operator-tagged ─────────────────────────────────
    operator_tagged = new_rel.get(T6_EDGE_FIELD_DERIVED_FROM)
    if isinstance(operator_tagged, list) and operator_tagged:
        normalized = [
            _normalize_entry(e) if isinstance(e, dict) else e
            for e in operator_tagged
        ]
        _validate_chain(
            normalized,
            context_edges_by_id=context_edges_by_id,
            edge_id=new_rel.get("id"),
        )
        return normalized

    # ─── Path 2: LLM-inferred (flag-gated) ───────────────────────
    if _flag_enabled(enable_llm):
        if llm_provider is None:
            # Flag on but caller forgot to wire a provider. Don't
            # crash — return empty so ingestion can proceed; the
            # audit_log layer can warn at boot if this happens.
            return []
        summary = _context_summary(context_edges_by_id)
        prompt = _build_llm_prompt(new_rel, summary)
        raw = llm_provider(prompt, summary)
        if not isinstance(raw, list):
            raise ValueError(
                f"llm_provider must return a list, got "
                f"{type(raw).__name__}"
            )
        # Apply the inferred-default + validate.
        inferred = []
        for entry in raw:
            if not isinstance(entry, dict):
                raise ValueError(
                    f"llm_provider returned non-dict entry: "
                    f"{type(entry).__name__}"
                )
            normalized = dict(entry)
            normalized.setdefault("derivation", T6_DERIVATION_INFERRED)
            inferred.append(normalized)
        _validate_chain(
            inferred,
            context_edges_by_id=context_edges_by_id,
            edge_id=new_rel.get("id"),
        )
        return inferred

    # ─── Path 3: default ─────────────────────────────────────────
    return []


__all__ = [
    "LLMDerivationProvider",
    "extract_derivation_chain",
    "T6_DERIVATION_INFERRED",
    "T6_DERIVATION_OPERATOR",
    "T6_DERIVATION_TRANSITIVE",
]
