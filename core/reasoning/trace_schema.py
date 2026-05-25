"""Frozen trace-row schema for the cognitive middleware layer (L0 MVP).

ARCHITECTURE.md §5.7.2 Reasoning backends + trace schema:

    LLM 호출은 core/reasoning/backends/ 의 명명된 어댑터를 통해서만
    발생한다. 모든 백엔드는 동일 row 형태로audit_bridge에 기록하며, 그
    형태는 이 모듈의 frozen dataclass (stage, parent_step_id,
    backend_id, inputs_hash, output_summary, applied_rule) 로 고정된다.
    새 백엔드는 registry 만 확장, schema 는 확장 안 함 — replay 도구는
    transport 와 무관하게 한 가지 row 형태만 읽는다.

Row mapping onto the existing audit_log table (Audit Phase 1–4 pattern,
no DB migration required):

    endpoint        ← "reason:<stage>"            — Phase 3 LIKE filter
    security_event  ← applied_rule
    elapsed_sec     ← latency_ms / 1000
    user_role       ← caller-supplied (default "system")
    query           ← "<backend_id>:<inputs_hash>"
    answer          ← compact JSON of {parent_step_id, output_summary,
                       error?, plus any caller extras}

L1 wires this into pipeline.py/modes.py; L2 ships scripts/replay_trace.py
that reads audit_log rows back into TraceStep instances. The schema is
the contract those two PRs both honor.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional, FrozenSet


# Stage whitelist — adding a stage is a code change on purpose so a typo
# at a call site fails loud (matches the PolicyEngine.can_use_feature
# pattern from W4-Q1). The seven stages cover Phase 1–4 of the cognitive
# layer track (docs/handovers/v0.3-cognitive-layer-track.md):
#
#   plan      — Planner decomposition (Phase 2 PR-7)
#   retrieve  — Loop-0 retrieval (existing path)
#   rerank    — Cross-encoder reranking (Phase 1 PR-1)
#   reflect   — draft → critique → revised (Phase 2 PR-5)
#   verify    — generator → critic → fact-checker chain (Phase 2 PR-6)
#   tool      — Tool router dispatch (Phase 2 PR-8)
#   synth     — Final synthesizer (existing LLM call site)
ALLOWED_STAGES: FrozenSet[str] = frozenset({
    "plan", "retrieve", "rerank", "reflect", "verify", "tool", "synth",
})


@dataclass(frozen=True)
class TraceStep:
    """One reasoning step. Six required fields exactly match
    ARCHITECTURE.md §5.7.2; latency_ms / error are observability extras
    that don't appear in the contract (consumers may ignore them).
    """
    stage: str
    backend_id: str
    parent_step_id: str
    inputs_hash: str
    output_summary: str
    applied_rule: str
    latency_ms: int = 0
    error: str = ""

    def __post_init__(self) -> None:
        if self.stage not in ALLOWED_STAGES:
            raise ValueError(
                f"unknown reasoning stage {self.stage!r}; "
                f"allowed: {sorted(ALLOWED_STAGES)}"
            )
        if not isinstance(self.backend_id, str):
            raise TypeError("backend_id must be str")
        if not isinstance(self.applied_rule, str) or not self.applied_rule:
            raise ValueError("applied_rule must be a non-empty str")


def compute_inputs_hash(prompt: str, system: str = "") -> str:
    """sha256(system + "\\n" + prompt)[:16]. Stable across processes so
    replay can detect "same inputs, different outcome" regressions.
    """
    h = hashlib.sha256()
    h.update((system or "").encode("utf-8", errors="replace"))
    h.update(b"\n")
    h.update((prompt or "").encode("utf-8", errors="replace"))
    return h.hexdigest()[:16]


def truncate_summary(text: str, limit: int = 200) -> str:
    if text is None:
        return ""
    s = str(text)
    return s if len(s) <= limit else s[:limit]


def emit_trace_step(
    step: TraceStep,
    *,
    user_role: str = "system",
    extras: Optional[Dict[str, Any]] = None,
    db_path: Optional[str] = None,
) -> bool:
    """Mirror a TraceStep onto the existing audit_log table.

    Routes through core.audit_bridge.mirror_to_audit_db with the
    "reason:<stage>" endpoint prefix so Phase 3's category filter can
    surface reasoning rows alongside tool / attack / system rows.

    Returns the bridge's bool (True on insert, False on failure). Never
    raises — audit emission must not block the reasoning path.
    """
    from core.audit_bridge import mirror_to_audit_db   # lazy: test isolation

    # Build the entry by laying TraceStep fields out as top-level
    # non-reserved keys. audit_bridge._resolve_answer folds every
    # non-reserved key into the `answer` JSON column, so the final row
    # carries them in one flat JSON blob:
    #
    #   answer = {"parent_step_id": "...", "output_summary": "...", ...}
    #
    # The reserved keys (time / role / endpoint / event / blocked /
    # exec_time_sec / tool_used / target) map onto dedicated columns.
    entry: Dict[str, Any] = {
        # reserved → columns
        "time":           None,                       # bridge falls back to now()
        "role":           user_role,
        "endpoint":       f"reason:{step.stage}",
        "event":          step.applied_rule,
        "exec_time_sec":  round(step.latency_ms / 1000.0, 6) if step.latency_ms else None,
        # Pack backend_id:inputs_hash into the `query` column so Phase 3's
        # free-text search can find all rows for one backend or one input
        # fingerprint.
        "tool_used":      step.backend_id or "orchestrator",
        "target":         step.inputs_hash,
        "blocked":        bool(step.error),
        # non-reserved → folded into the answer JSON
        "parent_step_id": step.parent_step_id,
        "output_summary": step.output_summary,
    }
    if step.error:
        entry["error"] = step.error
    if extras:
        for k, v in extras.items():
            # don't let extras clobber the schema fields or the bridge's
            # reserved keys
            if k in entry or k in {
                "time", "role", "layer", "event", "blocked",
                "exec_time_sec", "elapsed_sec",
                "tool_used", "target_file", "path", "target",
                "endpoint",
            }:
                continue
            entry[k] = v

    ok = mirror_to_audit_db(entry, db_path=db_path)
    # v0.4 Sprint 3 BL-1 — stdout mirror so the operator sees the
    # reasoning chain in stdout alongside the synth path. Before this,
    # planner / reflect / verify only wrote to audit_log DB (memory:
    # feedback_stdout_vs_audit_log_trace_split) — debugging a run
    # required querying the DB. Follows the observability.emit_step
    # convention: JAMES_TRACE_STDOUT=1 default ON, "0"/"false"/"no"
    # silences the mirror. Best-effort — a cp949 console crash never
    # blocks the reasoning path.
    _stdout_mirror_trace_step(step, extras)
    return ok


def _stdout_mirror_trace_step(
    step: TraceStep,
    extras: Optional[Dict[str, Any]],
) -> None:
    """Write a single-line `[reason:<stage>] …` row to stdout.

    Matches the format of observability.emit_step's mirror so the
    operator can grep / tail a single console stream for the whole
    chain. JAMES_TRACE_STDOUT default ON to match the operator-setup
    convention from PR #283 (Phase 1 observability).
    """
    if os.getenv("JAMES_TRACE_STDOUT", "1").strip().lower() in (
        "0", "false", "no", "",
    ):
        return
    try:
        trace_hint = ""
        if extras:
            tid = extras.get("trace_id") or ""
            if isinstance(tid, str) and tid:
                trace_hint = f" [trace {tid[:8]}]"
        latency = f"{step.latency_ms}ms" if step.latency_ms else "?ms"
        err = f" err={step.error[:60]}" if step.error else ""
        print(
            f"[reason:{step.stage}] {step.applied_rule} · "
            f"{step.backend_id or '?'} · {latency}{trace_hint}{err}",
            flush=True,
        )
    except Exception:
        # cp949 / closed-stdout / sentinel-string crashes must never
        # block the reasoning path. Operator sees the gap (no print)
        # rather than a wedged request.
        pass


def trace_step_to_dict(step: TraceStep) -> Dict[str, Any]:
    """Plain dict copy for tests / replay. asdict() respects frozen."""
    return asdict(step)


__all__ = [
    "ALLOWED_STAGES",
    "TraceStep",
    "compute_inputs_hash",
    "truncate_summary",
    "emit_trace_step",
    "trace_step_to_dict",
]
