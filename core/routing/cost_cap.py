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
) -> CostStatus:
    """Pre-flight cap check.

    Returns ``under_cap=False`` iff cap_usd > 0.0 AND the projected
    total (existing usd_est + ``usd_estimate``) would exceed it.

    ``tokens_estimate`` is currently informational (rolled into
    the CostStatus' projected math when ``usd_estimate`` is 0.0 by
    assuming a 0.0 USD-per-token rate — i.e. only the explicit
    ``usd_estimate`` counts). Phase 5 will add a token-rate table
    so the caller can pass tokens alone.
    """
    if budget is None:
        budget = default_budget()
    base = budget.status()
    cap = base.cap_usd
    if cap <= 0.0:
        # No cap configured → always under.
        return base
    projected = base.used_usd_est + max(0.0, float(usd_estimate))
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
