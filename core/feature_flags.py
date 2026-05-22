"""PROJECT JAMES — Cognitive feature flags registry.

UI-IA risk signal #5 (docs/UI_API_MAPPING.md §8): six Cognitive
Layer features are wired into the backend pipeline but have no
admin toggle surface — they're env-only. This module is the
substrate that lets the admin Configure → Cognitive sub-page
(PR-2 of the same series) read + write those flags through
``GET / POST /admin/settings/cognitive``.

The registry below is the **single source of truth** for which
env vars correspond to which cognitive feature, and which polarity
(``"enable"`` = env=1 means ON, ``"disable"`` = env=1 means OFF).
The two flags that ship default-ON (``verify``, ``rerank``) use
``"disable"`` polarity so the env var only needs to exist when the
operator wants to turn them OFF.

Apply semantics: ``apply_cognitive_flag(key, on)`` mutates the
in-process ``os.environ`` directly, mirroring the existing
``POST /admin/settings`` pattern (``server_llmwiki.py:5380`` —
``os.environ["JAMES_PROTECTED_FILES"] = ...``). The toggle takes
effect on the next call to the feature (every cognitive helper
reads the env var per-call — see ``rerank.py:37``,
``query_rewriter.py:79``, ``reflect.py:118``, etc.). Restart is
not required.

Persistence note: in-process env mutation is non-durable. A
container restart re-reads the boot ``.env`` file and reverts to
those values. Persistent storage is a v0.4 candidate (would
require a settings table + a boot-time loader that layers DB
values over env).
"""
from __future__ import annotations

import os
from typing import Any, Dict, List


# ─── Registry ───────────────────────────────────────────────────


# Each entry pins (env var name, polarity, human label, default).
# Polarity is one of two values:
#   "enable"  — env == "1" means the feature is ON, default OFF
#   "disable" — env == "1" means the feature is OFF, default ON
#
# Adding a new cognitive toggle: append here and ensure the helper
# module that consumes the env var reads it per-call (so a runtime
# toggle takes immediate effect — boot-time caching would defeat
# the UI).
COGNITIVE_FEATURE_FLAGS: Dict[str, Dict[str, Any]] = {
    "verify": {
        "env":       "JAMES_DISABLE_VERIFY",
        "polarity":  "disable",
        "label":     "Verifier base scan",
        "label_key": "set.cognitive_flag_verify",
        "default":   True,
        "module":    "core/reasoning/verify.py",
    },
    "fact_check": {
        "env":       "JAMES_ENABLE_FACT_CHECK",
        "polarity":  "enable",
        "label":     "Fact-checker (LLM-driven, runs after verify)",
        "label_key": "set.cognitive_flag_fact_check",
        "default":   False,
        "module":    "core/reasoning/verify.py",
    },
    "reflect": {
        "env":       "JAMES_ENABLE_REFLECT",
        "polarity":  "enable",
        "label":     "Reflection loop (draft → critique → revise)",
        "label_key": "set.cognitive_flag_reflect",
        "default":   False,
        "module":    "core/reasoning/reflect.py",
    },
    "planner": {
        "env":       "JAMES_ENABLE_PLANNER",
        "polarity":  "enable",
        "label":     "Planner (task decomposition into 2–5 subtasks)",
        "label_key": "set.cognitive_flag_planner",
        "default":   False,
        "module":    "core/reasoning/planner.py",
    },
    "query_rewrite": {
        "env":       "JAMES_ENABLE_QUERY_REWRITE",
        "polarity":  "enable",
        "label":     "Query rewriter (LLM-driven expansion)",
        "label_key": "set.cognitive_flag_query_rewrite",
        "default":   False,
        "module":    "core/retrieval/query_rewriter.py",
    },
    "rerank": {
        "env":       "JAMES_DISABLE_RERANK",
        "polarity":  "disable",
        "label":     "Cross-encoder reranker",
        "label_key": "set.cognitive_flag_rerank",
        "default":   True,
        "module":    "core/retrieval/rerank.py",
    },
}

# Stable order for callers that need a deterministic listing — UI
# legends, audit logs. Default-ON features first (most stable),
# default-OFF after, then alphabetical inside each group.
COGNITIVE_FLAG_ORDER: List[str] = [
    "verify", "rerank", "fact_check", "planner", "query_rewrite", "reflect",
]


# ─── Read ───────────────────────────────────────────────────────


def _flag_is_on(env_name: str, polarity: str) -> bool:
    """Resolve a single env var to its semantic ON/OFF state.

    Public surface — also used by tests to assert state without
    duplicating polarity logic.
    """
    raw = os.environ.get(env_name, "")
    if polarity == "enable":
        return raw == "1"
    # polarity == "disable"
    return raw != "1"


def read_cognitive_flags() -> List[Dict[str, Any]]:
    """Return the current state of every cognitive flag.

    Output shape (one entry per flag, in COGNITIVE_FLAG_ORDER)::

        [
          {
            "key":       "verify",
            "label":     "Verifier base scan",            # EN fallback
            "label_key": "set.cognitive_flag_verify",     # i18n lookup
            "env":       "JAMES_DISABLE_VERIFY",
            "polarity":  "disable",
            "default":   true,
            "on":        true,            # resolved semantic state
            "module":    "core/reasoning/verify.py",
          },
          ...
        ]

    ``label_key`` mirrors the convention used by ``LLM_TASK_TYPES``
    in ``frontend/static/admin.js`` — the UI binds ``data-i18n`` to
    it and falls back to ``label`` if the key is missing from the
    i18n table.
    """
    out: List[Dict[str, Any]] = []
    for key in COGNITIVE_FLAG_ORDER:
        spec = COGNITIVE_FEATURE_FLAGS[key]
        out.append({
            "key":       key,
            "label":     spec["label"],
            "label_key": spec["label_key"],
            "env":       spec["env"],
            "polarity":  spec["polarity"],
            "default":   spec["default"],
            "on":        _flag_is_on(spec["env"], spec["polarity"]),
            "module":    spec["module"],
        })
    return out


# ─── Write ──────────────────────────────────────────────────────


def apply_cognitive_flag(key: str, on: bool) -> Dict[str, Any]:
    """Mutate ``os.environ`` so the named flag reads as ``on``.

    Returns the before/after delta for audit logging::

        {"key": "...", "env": "...", "before": True/False, "after": True/False}

    Semantics:
      - For ``"enable"`` polarity: set env to "1" when ON; pop env
        when OFF.
      - For ``"disable"`` polarity: pop env when ON (default); set
        env to "1" when OFF.
      - Popping rather than writing "0" keeps the env table tidy
        and avoids any future code that uses ``bool(os.environ
        .get(name))`` being misled by the truthy non-empty string.

    Raises:
      ValueError — unknown ``key`` (defensive guard so a typo
                   from the admin endpoint surfaces as a 400, not
                   a silent no-op).
    """
    spec = COGNITIVE_FEATURE_FLAGS.get(key)
    if spec is None:
        raise ValueError(
            f"unknown cognitive flag {key!r}; "
            f"valid: {sorted(COGNITIVE_FEATURE_FLAGS)}"
        )

    env_name = spec["env"]
    polarity = spec["polarity"]
    before   = _flag_is_on(env_name, polarity)

    # Decide whether env should be set to "1" or popped, given the
    # polarity and the desired ON/OFF state.
    if polarity == "enable":
        want_env_set = bool(on)
    else:
        want_env_set = not bool(on)

    if want_env_set:
        os.environ[env_name] = "1"
    else:
        os.environ.pop(env_name, None)

    after = _flag_is_on(env_name, polarity)
    return {
        "key":     key,
        "env":     env_name,
        "before":  before,
        "after":   after,
    }


def apply_cognitive_flags(updates: Dict[str, bool]) -> List[Dict[str, Any]]:
    """Apply many flag updates in one shot. Returns the per-key
    delta list (same shape as ``apply_cognitive_flag``, one entry
    per update).

    All updates land atomically with respect to the caller's view —
    each ``apply_cognitive_flag`` is a single dict mutation. There's
    no cross-flag transaction (env is a flat namespace), so if one
    key is invalid the prior writes already landed; the function
    raises on the first invalid key so the caller can see exactly
    where it stopped.
    """
    out: List[Dict[str, Any]] = []
    for key, value in updates.items():
        if not isinstance(value, bool):
            raise ValueError(
                f"flag {key!r} value must be bool; got {type(value).__name__}"
            )
        out.append(apply_cognitive_flag(key, value))
    return out


__all__ = [
    "COGNITIVE_FEATURE_FLAGS",
    "COGNITIVE_FLAG_ORDER",
    "apply_cognitive_flag",
    "apply_cognitive_flags",
    "read_cognitive_flags",
]
