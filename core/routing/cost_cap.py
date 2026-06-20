"""v0.6.1 Phase 4 — Cost-aware monthly cap (plumb-first).

Single-host monthly token tally backed by an atomic-write JSON
file. Phase 5 will call ``check_cap`` before any cloud egress;
this module is callable but has no consumer yet.

Env contract (lazy, resolved at call time for test isolation):
  JAMES_COST_CAP_MONTHLY_USD : USD ceiling for the current month.
                                 0.0 (default) = no cap.
  JAMES_COST_CAP_FILE        : tally file path. Default:
                                 ``$JAMES_WORKSPACE/.james_cost.json``
                                 fallback to ``./.james_cost.json``.

Concurrency: last-writer-wins on the tally file. Acceptable for
the v0.6.1 single-host operator model. Multi-host coordination is
a v0.6.2+ concern.

File schema (forward-compatible — extra keys allowed):
  {
    "month": "2026-06",
    "tokens": 12345,
    "usd_est": 0.0738,
    "schema": 1
  }

On month rollover or schema-version mismatch, the reader returns
a fresh tally without overwriting the file — the writer rolls
over on the next ``record`` call.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import List, NamedTuple, Optional


_SCHEMA_VERSION = 1
_DEFAULT_FILE = ".james_cost.json"


# v0.6.1 Phase 5b' (2026-06-20) — published token-rate table for
# the cloud backends JAMES routes through. USD per 1,000,000 tokens
# (i.e. divide by 1_000_000 then multiply by token count).
#
# The numbers track Anthropic's public list price as of v0.6.1.
# Operators on a different contract (volume pricing, internal rate
# card) override per-model via ``JAMES_COST_RATE_<MODEL_KEY>=<in>:<out>``
# at call time — ``_resolve_rate`` reads that env first.
#
# Keys are lowercase + dot-stripped slug forms so caller `model`
# strings ("claude-4-opus", "Claude 4 Sonnet", "claude_4_haiku") all
# normalise to the same lookup.
_TOKEN_RATES_USD_PER_M: dict = {
    # Anthropic Claude 4 family (v0.6.1 list price)
    "claude-4-opus":     (15.0, 75.0),
    "claude-4-sonnet":   ( 3.0, 15.0),
    "claude-4-haiku":    ( 1.0,  5.0),
    # Claude Code CLI tends to identify as the underlying model; the
    # default research backend (``claude_code_cli``) maps to opus.
    "claude_code_cli":   (15.0, 75.0),
    # Generic fallback used when ``model`` is empty AND no env
    # override exists. Anchored at a mid-tier rate so an unidentified
    # call doesn't silently underestimate.
    "*":                 ( 3.0, 15.0),
}


def _normalise_model_key(model: str) -> str:
    """Slug form for token-rate lookup. ``"Claude 4 Opus"`` →
    ``"claude-4-opus"``; tolerates dot / space / underscore / case."""
    s = (model or "").strip().lower()
    for ch in (" ", "_", "."):
        s = s.replace(ch, "-")
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-")


def _resolve_rate(model: str) -> tuple[float, float]:
    """Return ``(input_usd_per_m, output_usd_per_m)`` for the model.

    Resolution order:
      1. ``JAMES_COST_RATE_<MODEL_KEY>=<input>:<output>`` env (operator
         override; both numbers required; bad form falls through to
         the table with a logged warning).
      2. ``_TOKEN_RATES_USD_PER_M`` shipped table.
      3. ``_TOKEN_RATES_USD_PER_M["*"]`` generic fallback.

    ``MODEL_KEY`` is the normalised key UPPER-cased with hyphens kept
    (e.g. ``JAMES_COST_RATE_CLAUDE-4-OPUS=10.0:50.0``).
    """
    key = _normalise_model_key(model)
    if key:
        env_name = f"JAMES_COST_RATE_{key.upper()}"
        raw = os.environ.get(env_name, "").strip()
        if raw:
            try:
                in_str, out_str = raw.split(":", 1)
                return (max(0.0, float(in_str)), max(0.0, float(out_str)))
            except (ValueError, AttributeError):
                print(
                    f"[routing.cost_cap] {env_name}={raw!r} not in "
                    "'<input>:<output>' form; using shipped table"
                )
    if key in _TOKEN_RATES_USD_PER_M:
        return _TOKEN_RATES_USD_PER_M[key]
    return _TOKEN_RATES_USD_PER_M["*"]


def estimate_usd(
    input_tokens: int,
    output_tokens: int = 0,
    *,
    model: str = "",
) -> float:
    """Return USD estimate for a (input, output) token pair.

    Returns ``0.0`` for empty input. The rate table + env override
    are resolved at call time so test isolation works.
    """
    if input_tokens <= 0 and output_tokens <= 0:
        return 0.0
    in_rate, out_rate = _resolve_rate(model)
    return (
        max(0, int(input_tokens))  * in_rate  / 1_000_000.0 +
        max(0, int(output_tokens)) * out_rate / 1_000_000.0
    )


class CostStatus(NamedTuple):
    """Outcome of ``check_cap``.

    under_cap   : True iff the projected total (used + estimate)
                  stays under cap_usd. Also True when cap_usd == 0.0
                  (the no-cap branch).
    used_tokens : tokens recorded for the current month.
    used_usd_est: USD estimate for the current month.
    cap_usd     : the cap value in effect (0.0 = no cap).
    month       : YYYY-MM the tally is bound to.
    reasons     : list of human strings explaining the verdict
                  ("over_cap", "no_cap", "fresh_tally", ...).
    """
    under_cap:    bool
    used_tokens:  int
    used_usd_est: float
    cap_usd:      float
    month:        str
    reasons:      List[str]


def _current_month() -> str:
    """Return YYYY-MM in UTC. Centralised so tests can monkey-patch."""
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _resolve_path(explicit: Optional[str] = None) -> str:
    """Resolve the tally file path with env + workspace fallback."""
    if explicit:
        return explicit
    raw = os.environ.get("JAMES_COST_CAP_FILE", "").strip()
    if raw:
        return raw
    ws = os.environ.get("JAMES_WORKSPACE", "").strip()
    if ws and os.path.isdir(ws):
        return os.path.join(ws, _DEFAULT_FILE)
    return _DEFAULT_FILE


def _resolve_cap_env() -> float:
    """Read JAMES_COST_CAP_MONTHLY_USD at call time."""
    raw = os.environ.get("JAMES_COST_CAP_MONTHLY_USD", "").strip()
    if not raw:
        return 0.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        print(
            f"[routing.cost_cap] JAMES_COST_CAP_MONTHLY_USD={raw!r} "
            "not a number; treating as no-cap (0.0)"
        )
        return 0.0


class CostBudget:
    """Atomic JSON-file monthly tally.

    Construct directly for tests + scripts; call ``default_budget()``
    in production to honor env defaults.
    """

    def __init__(
        self,
        path: Optional[str] = None,
        cap_usd: float = 0.0,
    ) -> None:
        self.path = _resolve_path(path)
        self.cap_usd = max(0.0, float(cap_usd))

    # ─── load / save ──────────────────────────────────────────────
    def _load(self) -> dict:
        """Read the tally file. Missing / malformed → fresh tally
        (the reader does NOT rewrite; the writer rolls over)."""
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            return {"month": _current_month(), "tokens": 0,
                    "usd_est": 0.0, "schema": _SCHEMA_VERSION}
        except (OSError, ValueError) as exc:
            print(
                f"[routing.cost_cap] tally file unreadable "
                f"({self.path}): {exc}; using fresh tally"
            )
            return {"month": _current_month(), "tokens": 0,
                    "usd_est": 0.0, "schema": _SCHEMA_VERSION}

        # Schema-version mismatch → fresh tally (forward-compat).
        if data.get("schema") != _SCHEMA_VERSION:
            return {"month": _current_month(), "tokens": 0,
                    "usd_est": 0.0, "schema": _SCHEMA_VERSION}

        # Month rollover → fresh tally.
        if data.get("month") != _current_month():
            return {"month": _current_month(), "tokens": 0,
                    "usd_est": 0.0, "schema": _SCHEMA_VERSION}

        # Normalise numeric fields.
        data["tokens"] = int(data.get("tokens", 0) or 0)
        data["usd_est"] = float(data.get("usd_est", 0.0) or 0.0)
        return data

    def _save(self, data: dict) -> None:
        """Atomic write: tmp + os.replace."""
        directory = os.path.dirname(self.path) or "."
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError:
            pass
        tmp = f"{self.path}.tmp.{os.getpid()}.{int(time.time() * 1000)}"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    # ─── operations ───────────────────────────────────────────────
    def record(self, tokens: int, usd_est: float = 0.0) -> None:
        """Add tokens + USD estimate to the current month's tally."""
        data = self._load()
        data["tokens"] = int(data["tokens"]) + max(0, int(tokens))
        data["usd_est"] = float(data["usd_est"]) + max(0.0, float(usd_est))
        self._save(data)

    def status(self) -> CostStatus:
        """Snapshot the current tally + cap state."""
        data = self._load()
        reasons: List[str] = []
        cap = self.cap_usd
        if cap <= 0.0:
            reasons.append("no_cap")
            under = True
        else:
            under = data["usd_est"] < cap
            reasons.append("under_cap" if under else "over_cap")
        return CostStatus(
            under_cap=under,
            used_tokens=int(data["tokens"]),
            used_usd_est=float(data["usd_est"]),
            cap_usd=cap,
            month=str(data["month"]),
            reasons=reasons,
        )


def default_budget() -> CostBudget:
    """Construct a CostBudget honoring the env defaults."""
    return CostBudget(path=None, cap_usd=_resolve_cap_env())


def check_cap(
    tokens_estimate: int,
    *,
    budget: Optional[CostBudget] = None,
    usd_estimate: float = 0.0,
    output_tokens_estimate: int = 0,
    model: str = "",
) -> CostStatus:
    """Pre-flight cap check.

    Returns ``under_cap=False`` iff cap_usd > 0.0 AND the projected
    total (existing usd_est + the larger of ``usd_estimate`` /
    ``estimate_usd(tokens_estimate, output_tokens_estimate, model=model)``)
    would exceed it.

    v0.6.1 Phase 5b' (2026-06-20) — token-rate table landed. When
    ``usd_estimate`` is left at its default ``0.0``, the cap projection
    now uses ``estimate_usd(tokens_estimate, output_tokens_estimate,
    model=model)`` so callers that pass token counts alone get a
    real projection. Explicit ``usd_estimate`` still wins when set
    (operator override / pre-computed billing line).
    """
    if budget is None:
        budget = default_budget()
    base = budget.status()
    cap = base.cap_usd
    if cap <= 0.0:
        # No cap configured → always under.
        return base
    explicit = max(0.0, float(usd_estimate))
    if explicit > 0.0:
        projected_delta = explicit
    else:
        projected_delta = estimate_usd(
            tokens_estimate, output_tokens_estimate, model=model,
        )
    projected = base.used_usd_est + projected_delta
    under = projected < cap
    reasons = list(base.reasons)
    if under and "over_cap" in reasons:
        reasons.remove("over_cap")
        reasons.append("under_cap")
    elif (not under) and "under_cap" in reasons:
        reasons.remove("under_cap")
        reasons.append("over_cap")
    if tokens_estimate:
        reasons.append(f"tokens_estimate={int(tokens_estimate)}")
    return CostStatus(
        under_cap=under,
        used_tokens=base.used_tokens,
        used_usd_est=base.used_usd_est,
        cap_usd=cap,
        month=base.month,
        reasons=reasons,
    )


__all__ = [
    "CostStatus",
    "CostBudget",
    "default_budget",
    "check_cap",
]
