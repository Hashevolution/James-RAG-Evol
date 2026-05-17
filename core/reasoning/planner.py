"""Planner — Cognitive Layer Phase 2 PR-7.

ARCHITECTURE.md §5.7.1: "Planner — decompose a question into ordered
subtasks; choose retrieval depth". Per the cognitive-layer track
handover, MVP scope is "처음엔 단순 표시, 추후 본격" — the planner
emits a decomposition plan + audit trail, and the synth step
optionally prepends the plan to the LLM prompt so the model follows
it. Driving retrieval / tool routing from the plan lands in a future
PR (PR-7 follow-up or new "plan-driven retrieval" cycle).

Posture: opt-in via JAMES_ENABLE_PLANNER=1. Default OFF preserves
v0.3.0+PR-1+PR-2+PR-5+PR-6+PR-8 byte-identical behaviour. When enabled,
one extra LLM round-trip per query (~5-10s on CPU ollama).

Routes through the Backend registry (Phase 0 L0). Trace emit uses
stage="plan" — already in ALLOWED_STAGES, no §5.7.2 schema change.

Failure posture: every failure path returns a single-subtask plan
(the original query). Synth never sees None or raises here.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from core.reasoning.trace_schema import (
    TraceStep,
    compute_inputs_hash,
    emit_trace_step,
    truncate_summary,
)


DEFAULT_BACKEND_ID = "ollama_local"
DEFAULT_TIMEOUT_S = 20.0
DEFAULT_MAX_TOKENS = 400
# Decomposition cap. More than 5 subtasks is usually the model
# elaborating rather than decomposing — and the synth prompt only
# benefits from a focused checklist, not a wall of bullet points.
MAX_SUBTASKS = 5
# Trivial query gate. 4-character queries ("RAG?") don't need
# decomposition; trying to plan them invites hallucination.
MIN_QUERY_LEN = 12


@dataclass
class Plan:
    """Outcome of one planning pass.

    ``subtasks`` is always non-empty — on failure it falls back to
    ``[original_query]`` so downstream code never has to guard
    against an empty list.
    """
    original_query: str
    subtasks:       List[str] = field(default_factory=list)
    rationale:      str = ""

    def is_trivial(self) -> bool:
        """A trivial plan (1 subtask == the original query) means
        the planner either skipped or fell back. Callers can branch
        on this to avoid prepending a useless single-line checklist
        to the synth prompt.
        """
        return (
            len(self.subtasks) <= 1
            or (len(self.subtasks) == 1
                and self.subtasks[0].strip() == self.original_query.strip())
        )


def _enabled() -> bool:
    return os.environ.get("JAMES_ENABLE_PLANNER") == "1"


def _is_korean(text: str) -> bool:
    if not text:
        return False
    korean_chars = sum(1 for c in text if "가" <= c <= "힣")
    return korean_chars >= max(1, int(len(text) * 0.2))


PLAN_PROMPT_KO = (
    "아래 질문에 답하기 위해 필요한 하위 작업 (subtask) 들을 순서대로 "
    "2-5 개로 분해하라.\n\n"
    "[질문]\n{query}\n\n"
    "규칙:\n"
    "- 각 subtask 는 한 줄, 짧고 명령형 ('NVIDIA 의 GPU 라인업 조사')\n"
    "- 한 단계가 다음 단계의 입력이 되는 자연 순서\n"
    "- 질문이 단순하면 (1-2 단계로 충분) 그만큼만 출력\n"
    "- 의미를 보존하고 새 주제를 만들지 마라\n\n"
    "JSON 으로만 응답:\n"
    '{{"subtasks": ["...", "..."], "rationale": "한 줄 이유"}}'
)

PLAN_PROMPT_EN = (
    "Decompose the question below into 2-5 ordered subtasks needed to "
    "answer it.\n\n"
    "[Question]\n{query}\n\n"
    "Rules:\n"
    "- One line per subtask, imperative form (e.g., 'Survey NVIDIA's GPU lineup')\n"
    "- Natural order — each step's output feeds the next\n"
    "- If the question is simple (1-2 steps suffice), output only that many\n"
    "- Preserve meaning; do not introduce new topics\n\n"
    "Respond with JSON only:\n"
    '{{"subtasks": ["...", "..."], "rationale": "one-line reason"}}'
)


# Tolerant JSON sniff — accepts either pure JSON or JSON padded with
# prose. We anchor on the ``"subtasks"`` key so a model that ignores
# the "JSON only" instruction and adds a one-line explanation still
# parses.
_JSON_OBJ_RE = re.compile(
    r'\{[^{}]*"subtasks"\s*:\s*\[[^\]]*\][^{}]*\}',
    re.DOTALL,
)


def _parse_plan_response(text: str) -> Optional[Tuple[List[str], str]]:
    """Return ``(subtasks, rationale)`` or ``None`` on parse failure."""
    if not text:
        return None
    try:
        blob = json.loads(text)
        return _extract(blob)
    except (json.JSONDecodeError, ValueError):
        pass
    m = _JSON_OBJ_RE.search(text)
    if m:
        try:
            blob = json.loads(m.group(0))
            return _extract(blob)
        except (json.JSONDecodeError, ValueError):
            pass
    return None


def _extract(blob) -> Optional[Tuple[List[str], str]]:
    if not isinstance(blob, dict):
        return None
    subs = blob.get("subtasks") or []
    if not isinstance(subs, list):
        return None
    cleaned: List[str] = []
    for s in subs:
        if not isinstance(s, str):
            continue
        st = s.strip()
        if not st:
            continue
        cleaned.append(st[:200])
        if len(cleaned) >= MAX_SUBTASKS:
            break
    if not cleaned:
        return None
    rationale = blob.get("rationale", "")
    if not isinstance(rationale, str):
        rationale = ""
    return cleaned, rationale.strip()[:300]


class Planner:
    """Stateless wrapper around a Backend.

    The Backend caches the underlying LLM client across calls so
    successive plans on the same backend share connection state.
    """

    def __init__(
        self,
        backend_id: str = DEFAULT_BACKEND_ID,
        *,
        timeout: float = DEFAULT_TIMEOUT_S,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        self._backend_id = backend_id
        self._timeout = timeout
        self._max_tokens = max_tokens

    def plan(
        self,
        query: str,
        *,
        user_role: str = "system",
        force: bool = False,
    ) -> Plan:
        """Return a Plan with 1-5 subtasks.

        Falls back to ``Plan(query, [query], "...")`` when:
          * env opt-in unset and ``force`` is False
          * query empty / shorter than MIN_QUERY_LEN
          * backend lookup fails / .complete() raises / error string /
            empty response / malformed JSON / empty subtasks list
        """
        query = (query or "").strip()
        identity = Plan(original_query=query, subtasks=[query],
                        rationale="planner skipped")
        if not query or len(query) < MIN_QUERY_LEN:
            return identity
        if not force and not _enabled():
            return identity

        try:
            from core.reasoning.backends import get_backend
            backend = get_backend(self._backend_id)
        except Exception:
            self._emit_skip(query, user_role, "backend_lookup_failed")
            return identity

        is_ko = _is_korean(query)
        tmpl = PLAN_PROMPT_KO if is_ko else PLAN_PROMPT_EN
        prompt = tmpl.format(query=query)

        t0 = time.time()
        try:
            result = backend.complete(
                prompt,
                max_tokens=self._max_tokens,
                timeout=self._timeout,
            )
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:200]}"
            self._emit(
                query=query, prompt=prompt, output="",
                latency_ms=int((time.time() - t0) * 1000),
                error=err, user_role=user_role,
            )
            return identity
        latency_ms = int((time.time() - t0) * 1000)

        text = getattr(result, "text", "") or ""
        err = getattr(result, "error", "") or ""
        if err or not text:
            self._emit(
                query=query, prompt=prompt, output=text,
                latency_ms=latency_ms, error=err or "empty_response",
                user_role=user_role,
            )
            return identity

        parsed = _parse_plan_response(text)
        if parsed is None:
            self._emit(
                query=query, prompt=prompt, output=text,
                latency_ms=latency_ms, error="parse_failed",
                user_role=user_role,
            )
            return identity

        subtasks, rationale = parsed
        self._emit(
            query=query, prompt=prompt,
            output=f"{len(subtasks)} subtasks: " + " / ".join(
                s[:40] for s in subtasks[:3]
            ),
            latency_ms=latency_ms, error="", user_role=user_role,
        )
        return Plan(
            original_query=query,
            subtasks=subtasks,
            rationale=rationale,
        )

    def _emit(
        self,
        *,
        query: str,
        prompt: str,
        output: str,
        latency_ms: int,
        error: str,
        user_role: str,
    ) -> None:
        extras = {"original_query": query[:200]}
        try:
            from core.observability import get_trace_id
            tid = get_trace_id()
            if tid:
                extras["trace_id"] = tid
        except Exception:
            pass
        try:
            emit_trace_step(
                TraceStep(
                    stage="plan",
                    backend_id=self._backend_id,
                    parent_step_id="",
                    inputs_hash=compute_inputs_hash(prompt),
                    output_summary=truncate_summary(output),
                    applied_rule="reasoning.plan.decompose",
                    latency_ms=latency_ms,
                    error=error,
                ),
                user_role=user_role,
                extras=extras,
            )
        except Exception:
            # Best-effort — never block the synth path on audit_log
            # unavailability.
            pass

    def _emit_skip(self, query: str, user_role: str, reason: str) -> None:
        """Skip cases (no opt-in, no backend) — still emit so the
        replay tool can show "planner was asked but bypassed".
        """
        self._emit(
            query=query, prompt=query, output="",
            latency_ms=0, error=f"skipped: {reason}",
            user_role=user_role,
        )


# ─── module-level singleton ────────────────────────────────────────
_SINGLETON: Optional[Planner] = None
_SINGLETON_LOCK = threading.Lock()


def get_planner() -> Planner:
    global _SINGLETON
    if _SINGLETON is None:
        with _SINGLETON_LOCK:
            if _SINGLETON is None:
                _SINGLETON = Planner()
    return _SINGLETON


def _clear_singleton_for_tests() -> None:
    """Test helper. Production code never calls this."""
    global _SINGLETON
    with _SINGLETON_LOCK:
        _SINGLETON = None


__all__ = [
    "DEFAULT_BACKEND_ID",
    "MAX_SUBTASKS",
    "Plan",
    "Planner",
    "get_planner",
]
