"""Integrity guards shared by every QVT capture path.

Why this is a shared module
---------------------------
On 2026-09-22 the T0 smoke (``scripts/qvt_ablation_matrix.py``) was
stopped with 4 of 7 completed queries reading "답변 생성에 실패했습니다.".
The cause was not new. Every guard that would have caught it had already
been written that week — **in the other script**:

    guard                              capture_baseline   ablation_matrix
    JAMES_SETTINGS_USE_DB=0            yes                yes (2026-06-15)
    JAMES_DISABLE_MODE_AWARE_ROUTING   yes (#1142)        no
    abort on generation failure        yes (#1141)        no
    recorded provenance                yes (#1143)        no
    host state                         yes (#1147)        no

The two scripts were written as parallel copies ("Server lifecycle
helpers — copied from qvt_capture_baseline.py"), so a fix to one never
reached the other. Adding the guards to the matrix runner by copying them
again would reproduce the exact drift that caused the defect. They live
here instead, and both scripts import them.

Contents
--------
* ``ROUTING_PIN_ENV`` — the env that makes a measured model the model
  that answers. Mode-aware routing (#969–#990) overrides
  ``JAMES_LLM_MODEL`` for chat / retrieval / wiki_edit via
  ``resolve_for_mode(mode, requested="")``, which bypasses
  ``config.GEMMA_MODEL`` on purpose. Without the kill-switch, five matrix
  tiers measure one model under five labels.
* ``answer_health`` — refuse to score a run whose answers are
  infrastructure failures. ``core/reasoning/pipeline.py:321`` treats the
  synth-failure string as a no-data trigger and the softener turns it
  into an abstention, so a timed-out LLM is scored as the system
  *correctly declining* — in abstention_f1 and graded_answer at once.
* ``abort_reason`` — the single rule both scripts use to turn an
  ``answer_health`` result into "score it" or "stop". Kept here so the
  threshold cannot drift between them either.
* ``resolved_models`` — what will actually answer under a given applied
  env. Takes the env explicitly: the capture script's first version read
  ``os.environ`` and recorded a model that never ran (#1143), because the
  pinned env is applied to the spawned server, not the runner.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

# Applied on top of any cell / baseline env. See module docstring.
ROUTING_PIN_ENV: Dict[str, str] = {
    "JAMES_DISABLE_MODE_AWARE_ROUTING": "1",
    # config._llm_setting is DB-first: "if the operator set the env AND
    # the DB has a different value, the DB silently wins". Its docstring
    # says measurement runners disable the DB layer.
    "JAMES_SETTINGS_USE_DB": "0",
}

# Source of truth: core/reasoning/pipeline.py:321 — the pair it treats as
# generation failure. Deliberately NOT "자료에 없음. 관련된", which is a
# semantic abstention and therefore a measurement.
SYNTH_FAILURE_PREFIXES: Tuple[str, ...] = (
    "답변 생성에 실패",
    "LLM 응답 생성 중 오류",
)


def infrastructure_failure_prefixes() -> Tuple[str, ...]:
    """Synth-failure markers plus the backend's own error prefixes.

    ``core.cache_manager._ERROR_PREFIXES`` is the repo's existing list of
    "this is an error, do not cache it" markers; reusing it keeps this
    guard aligned with what the rest of the system already calls broken.
    """
    extra: Tuple[str, ...] = ()
    try:
        from core.cache_manager import _ERROR_PREFIXES  # noqa: WPS433
        extra = tuple(_ERROR_PREFIXES)
    except Exception:
        pass
    return SYNTH_FAILURE_PREFIXES + extra


def answer_health(bench_path: Path) -> Dict[str, Any]:
    """Count answers that are infrastructure failures, not answers.

    ``blocked`` rows are excluded: step7 ships security fixtures that are
    *supposed* to be refused, and counting them would make the guard
    refuse every healthy run.
    """
    prefixes = infrastructure_failure_prefixes()
    try:
        data = json.loads(Path(bench_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"total": 0, "failed": 0, "examples": [],
                "error": "{}: {}".format(type(exc).__name__, exc)}
    considered = 0
    failed: List[str] = []
    for row in data.get("results") or []:
        if row.get("blocked"):
            continue
        considered += 1
        preview = str(row.get("answer_preview") or "").lstrip()
        if any(preview.startswith(p) for p in prefixes):
            failed.append("{}: {}".format(row.get("id"), preview[:48]))
    return {"total": considered, "failed": len(failed),
            "examples": failed[:5], "error": None}


def abort_reason(health: Mapping[str, Any]) -> Optional[str]:
    """Why a run must not be scored, or ``None`` if it may be.

    Any infrastructure failure aborts — there is no tolerated fraction.
    One softened failure moves abstention_f1 and graded_answer together,
    and the noise bands those axes are compared against are 0.07 wide.

    An unreadable bench file also aborts. Before this helper the capture
    script checked only ``failed``, so a file that failed to parse read
    as ``failed == 0`` — healthy.
    """
    if health.get("error"):
        return "bench output unreadable: {}".format(health["error"])
    if not health.get("total"):
        return "bench output has no scorable answers"
    if health.get("failed"):
        return "{}/{} answers are infrastructure failures, not measurements".format(
            health["failed"], health["total"])
    return None


def resolved_models(applied_env: Mapping[str, str]) -> Dict[str, Any]:
    """What will answer under ``applied_env`` — the env the *server* sees.

    Records both the effective model and what mode-aware routing *would*
    pick, so a reader sees the gap between a pinned measurement and live
    production routing without having to already know about it.
    """
    out: Dict[str, Any] = {"probe": "applied-env", "error": None}
    try:
        from core.model_resolver import resolve_for_mode  # noqa: WPS433
        for mode in ("retrieval", "chat"):
            r = resolve_for_mode(mode, requested="")
            out[mode] = {"tag": getattr(r, "tag", None),
                         "source": getattr(r, "source", None)}
    except Exception as exc:
        out["error"] = "{}: {}".format(type(exc).__name__, exc)

    pinned = str(applied_env.get("JAMES_LLM_MODEL", "") or "").strip()
    if pinned:
        out["config_default"] = pinned
        out["config_default_source"] = "applied_env[JAMES_LLM_MODEL]"
    else:
        try:
            import config  # noqa: WPS433
            out["config_default"] = getattr(config, "GEMMA_MODEL", None)
        except Exception:
            out["config_default"] = None
        out["config_default_source"] = "config.GEMMA_MODEL"

    disabled = bool(str(applied_env.get(
        "JAMES_DISABLE_MODE_AWARE_ROUTING", "") or "").strip())
    out["mode_aware_routing_disabled"] = disabled
    # With the kill-switch set, core/reasoning/engine_routing.py never
    # calls resolve_for_mode and the engine falls back to GEMMA_MODEL.
    if disabled:
        out["effective"] = {"tag": out.get("config_default"),
                            "source": "GEMMA_MODEL (mode-aware routing disabled)"}
    else:
        out["effective"] = {"tag": (out.get("retrieval") or {}).get("tag"),
                            "source": "mode-aware routing (retrieval preference)"}

    # Cloud synth (matrix tier M_CLOUD): trace_synth_call sends only the
    # synth stage to the cloud backend when this pair is set; rewrite /
    # plan / verify stay on the local model above. Recording the local
    # tag alone as "effective" would name a model that did not write
    # the answers.
    backend = str(applied_env.get("JAMES_REASONING_BACKEND", "") or "").strip()
    if (str(applied_env.get("JAMES_FORCE_CLOUD", "") or "").strip()
            and backend):
        out["synth_override"] = {
            "backend": backend,
            "tag": None,
            "source": "JAMES_FORCE_CLOUD (backend picks the model)",
            "applies_to": "synth stage only",
        }
    return out
