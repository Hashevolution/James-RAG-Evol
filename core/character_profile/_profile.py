"""Character profile — core class (state, set_trait ripple, persistence).

``_ProfileCoreMixin``: the instance-state methods that own the trait
value dict and its read/write paths — ``__init__``, ``get``,
``get_with_meta``, ``get_correlations`` (frontend visualization),
``get_damping``, ``set_trait`` (opposing flip + correlation ripple),
``_load`` / ``_save`` (preferences DB I/O).

Composed onto ``CharacterProfile`` together with ``_SummaryMixin``
(``build_summary`` + ``get_prompt_modifiers``) in
``core/character_profile/__init__.py``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from ._traits import (
    _CORR_INDEX,
    _OPPONENTS,
    _RIPPLE_DAMPING,
    CORRELATIONS,
    TRAITS,
)


class _ProfileCoreMixin:
    def __init__(self):
        self._values: Dict[str, float] = {k: v["default"] for k, v in TRAITS.items()}
        self._load()

    # ─── 조회 ──────────────────────────────────────────────────────
    def get(self) -> Dict:
        return {k: round(v, 3) for k, v in self._values.items()}

    def get_with_meta(self) -> list:
        return [{
            "id":        k,
            "label":     TRAITS[k]["label"],
            "label_ko":  TRAITS[k].get("label_ko", TRAITS[k]["label"]),
            # v0.4 Sprint 2 #6 follow-up — propagate `label_key` so the
            # admin character page resolves trait names through `t(label_key)`
            # under the active UI language. Without this, the frontend
            # falls back to `label_ko` regardless of `lang` and the radar
            # labels + slider rows render Korean in EN mode (live verify
            # 2026-05-26 finding on v0.4.0-alpha.3).
            "label_key": TRAITS[k]["label_key"],
            "icon":      TRAITS[k]["icon"],
            "group":     TRAITS[k]["group"],
            "value":     round(self._values[k], 3),
            "default":   TRAITS[k]["default"],
        } for k in TRAITS]

    @staticmethod
    def get_correlations() -> List[dict]:
        """Return correlations as dicts for frontend visualization.

        Frontend uses these to draw edges between trait vertices on
        the radar chart, color-coded by sign and thickness by weight.
        """
        return [{"from": s, "to": t, "weight": w} for (s, t, w) in CORRELATIONS]

    @staticmethod
    def get_damping() -> float:
        """Expose damping factor so frontend animation matches the
        backend's actual ripple magnitude."""
        return _RIPPLE_DAMPING

    # ─── 변경 ──────────────────────────────────────────────────────
    def set_trait(self, trait_id: str, value: float) -> Dict:
        """성향 설정. 짝(opposing) 즉시 flip + 상관 trait ripple 적용.

        Returns:
            {trait_id, value, opponent, ripples: [{trait, old, new, weight}, ...]}
            opponent: 짝이 있는 group A~D 경우 짝 trait의 새 값 (1.0 - value)
            ripples: 상관관계로 인해 함께 움직인 trait들의 변경 내역
        """
        if trait_id not in TRAITS:
            return {"error": f"알 수 없는 성향: {trait_id}"}

        old_value = self._values[trait_id]
        value = max(0.0, min(1.0, round(value, 3)))
        delta = value - old_value
        self._values[trait_id] = value

        result: Dict = {"trait_id": trait_id, "value": value,
                        "opponent": None, "ripples": []}

        # ─── 짝 자동 flip (Group A~D, sum=1.0 invariant) ────────────
        opp = _OPPONENTS.get(trait_id)
        if opp:
            self._values[opp] = round(1.0 - value, 3)
            result["opponent"] = opp

        # ─── 상관 trait ripple (Group 무관, damped 비례) ────────────
        # 짝 trait은 이미 위에서 처리 — 이중 적용 방지 위해 skip set.
        skip = {trait_id}
        if opp:
            skip.add(opp)

        for target, weight in _CORR_INDEX.get(trait_id, []):
            if target in skip:
                continue
            old = self._values[target]
            nudge = delta * weight * _RIPPLE_DAMPING
            new = max(0.0, min(1.0, round(old + nudge, 3)))
            if abs(new - old) > 0.001:   # 실제 변화 있을 때만 기록
                self._values[target] = new
                result["ripples"].append({
                    "trait":  target,
                    "old":    round(old, 3),
                    "new":    new,
                    "weight": weight,
                })

        self._save()
        return result

    # ─── 영속화 (preferences DB의 trait:* 키) ──────────────────────
    def _load(self):
        try:
            from core.memory.store import _connect
            with _connect() as conn:
                rows = conn.execute(
                    "SELECT key, value FROM preferences WHERE key LIKE 'trait:%'"
                ).fetchall()
                for r in rows:
                    tid = r["key"].replace("trait:", "")
                    if tid in TRAITS:
                        try:
                            self._values[tid] = float(r["value"])
                        except Exception:
                            pass
        except Exception:
            pass

    def _save(self):
        try:
            from core.memory.store import _connect
            now = datetime.now().isoformat()
            with _connect() as conn:
                for tid, val in self._values.items():
                    conn.execute(
                        "INSERT OR REPLACE INTO preferences "
                        "(key, value, raw, confidence, created_at, updated_at) "
                        "VALUES (?,?,?,?,?,?)",
                        (f"trait:{tid}", str(val), "", 1.0, now, now)
                    )
        except Exception as e:
            print(f"[PROFILE] 저장 실패: {e}")


__all__ = ["_ProfileCoreMixin"]
