"""Env gates: is the verifier on, is the fact check on.

Split out of the single-file ``core/reasoning/verify.py`` on 2026-09-26.
The file had reached 20,008 B against CLAUDE.md rule #5's 20 KB cap —
472 B of headroom — so it could not take another line. Same shape as the
v0.6 ``core/reasoning/reflect/`` split; ``__init__`` re-exports the
pre-split surface, so the move is a no-op for callers.
"""
from __future__ import annotations

import os


def _enabled() -> bool:
    """Verifier base mode (security_validator heuristic) is **default ON**
    since v0.3.x.

    The base scan is ~5ms of pure-Python pattern matching against the
    final answer — well below the STEP 7 measurement noise floor and
    independent of LLM availability. Keeping it always-on means that
    a vanilla JAMES install gets injection-echo detection from day
    one without an operator having to discover the env flag.

    The legacy opt-in ``JAMES_ENABLE_VERIFY=1`` is still honoured as
    a no-op (truthy → True), so a tightly-coupled .env from earlier
    releases keeps working. The new opt-out is
    ``JAMES_DISABLE_VERIFY=1`` for the rare case an operator wants
    to measure baseline cost or silence the verifier's annotate /
    block recommendations entirely.

    Fact-checking (LLM-driven, +5-15s/query) remains opt-in — see
    :func:`_fact_check_enabled`.
    """
    # α-6 S6 sector ablation — `JAMES_DISABLE_COGNITIVE_STAGES=1`
    # forces all cognitive stages OFF regardless of per-stage flags.
    if os.environ.get("JAMES_DISABLE_COGNITIVE_STAGES") == "1":
        return False
    return os.environ.get("JAMES_DISABLE_VERIFY") != "1"


def _fact_check_enabled() -> bool:
    """Fact-check stays opt-in via ``JAMES_ENABLE_FACT_CHECK=1``.

    The chain ``_enabled() and ...`` means a hard opt-out
    (``JAMES_DISABLE_VERIFY=1``) silences both base scan and
    fact-check in one knob — consistent with operator intent.
    """
    return (
        _enabled()
        and os.environ.get("JAMES_ENABLE_FACT_CHECK") == "1"
    )


