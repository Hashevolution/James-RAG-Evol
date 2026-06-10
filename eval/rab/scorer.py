"""RAB scorer — SPEC v0.1 §2. Deterministic; no LLM anywhere.

Inputs (produced by the driver / SUT adapter):

* ``e_exec``     — ground-truth executed ops:
                   ``[{op_id, type, t_start, t_end}, ...]`` where ``type``
                   is a RAB canonical type and t_* are ISO-8601 strings.
* ``log``        — the SUT's exported audit log: list of event rows per
                   SPEC §1 (``event_id, ts, event_type, parent_id,
                   inputs_hash, payload``) with event_type ALREADY mapped
                   to canonical types via the submission's mapping table.
* ``snapshots``  — ground-truth states at checkpoints: ``{k: state}``.
* ``replays``    — log-only reconstructions: ``{k: state}``.
* ``replay_cost``— ``{"events": int, "seconds": float}`` measured during
                   replay (RF cost axis).

A *state* is the SPEC §2.4 contract shape::

    {"entities": [{"id": ..., ...}, ...],
     "edges":    [{"src": ..., "dst": ..., "type": ..., ...}, ...]}

All scoring is pure-functional over these inputs; re-running on the
same artifacts reproduces scores bit-for-bit (SPEC §4).
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

CANONICAL_TYPES = (
    "INGEST", "UPDATE", "SUPERSEDE", "DELETE",
    "RETRIEVE", "RERANK", "SYNTH", "VERIFY", "ANSWER", "OTHER",
)

# Mutating types count toward AC's decision-bearing denominator along
# with the reasoning-round types the driver records.
_FLOAT_DP = 6


# ─── canonical form (SPEC §2.4) ────────────────────────────────────


def _norm_value(v: Any) -> Any:
    if isinstance(v, float):
        return round(v, _FLOAT_DP)
    if isinstance(v, dict):
        return {k: _norm_value(v[k]) for k in sorted(v)}
    if isinstance(v, list):
        return [_norm_value(x) for x in v]
    return v


def _sort_items(items: List[dict], keys: Tuple[str, ...]) -> List[dict]:
    def sk(d: dict):
        return tuple(str(d.get(k, "")) for k in keys)
    return sorted((dict(i) for i in items), key=sk)


def canon(state: Optional[dict]) -> str:
    """SPEC §2.4 canonical serialisation: keys sorted, entity list
    sorted by id, edge list sorted by (src, dst, type), floats to 6 dp,
    compact separators. ``None`` canonicalises to the empty state."""
    state = state or {}
    norm = {
        "entities": _sort_items(
            [_norm_value(e) for e in (state.get("entities") or [])],
            ("id",)),
        "edges": _sort_items(
            [_norm_value(e) for e in (state.get("edges") or [])],
            ("src", "dst", "type")),
    }
    return json.dumps(norm, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"))


def state_items(state: Optional[dict]) -> set:
    """The item set used for RF-graded Jaccard: entity ids plus
    (src, dst, type) edge triples."""
    state = state or {}
    items = {("entity", str(e.get("id")))
             for e in (state.get("entities") or [])}
    items |= {("edge", str(e.get("src")), str(e.get("dst")),
               str(e.get("type")))
              for e in (state.get("edges") or [])}
    return items


# ─── AC — Audit Completeness (SPEC §2.1) ───────────────────────────


def score_ac(e_exec: List[dict], log: List[dict]) -> Dict[str, Any]:
    """Greedy time-ordered matching: each executed op matches the first
    unconsumed log event of the same canonical type whose ``ts`` falls
    inside the op's [t_start, t_end] window. ISO-8601 strings compare
    lexicographically when zone-normalised — the driver guarantees UTC.
    """
    events_by_type: Dict[str, List[dict]] = {}
    for ev in log:
        events_by_type.setdefault(str(ev.get("event_type", "")), []).append(ev)
    for evs in events_by_type.values():
        evs.sort(key=lambda e: str(e.get("ts", "")))

    consumed: set = set()
    matched = 0
    per_type_total: Dict[str, int] = {}
    per_type_matched: Dict[str, int] = {}

    for op in sorted(e_exec, key=lambda o: str(o.get("t_start", ""))):
        t = str(op.get("type", ""))
        per_type_total[t] = per_type_total.get(t, 0) + 1
        lo, hi = str(op.get("t_start", "")), str(op.get("t_end", ""))
        for ev in events_by_type.get(t, []):
            eid = str(ev.get("event_id", ""))
            ts = str(ev.get("ts", ""))
            if eid in consumed:
                continue
            if lo <= ts <= hi:
                consumed.add(eid)
                matched += 1
                per_type_matched[t] = per_type_matched.get(t, 0) + 1
                break

    total = len(e_exec)
    per_type = {
        t: {
            "total": per_type_total[t],
            "matched": per_type_matched.get(t, 0),
            "ac": round(per_type_matched.get(t, 0) / per_type_total[t], 4),
        }
        for t in sorted(per_type_total)
    }
    return {
        "overall": round(matched / total, 4) if total else 0.0,
        "matched": matched,
        "total": total,
        "per_type": per_type,
    }


# ─── RF — Replay Fidelity (SPEC §2.2) ──────────────────────────────


def score_rf(
    snapshots: Dict[Any, dict],
    replays: Dict[Any, dict],
    replay_cost: Optional[dict] = None,
) -> Dict[str, Any]:
    keys = sorted(snapshots, key=str)
    if not keys:
        return {"exact": 0.0, "graded": 0.0, "k": 0,
                "cost_s_per_1k_events": None}
    exact = 0
    jaccards: List[float] = []
    per_checkpoint = {}
    for k in keys:
        s = snapshots.get(k)
        r = replays.get(k)
        is_exact = canon(r) == canon(s)
        si, ri = state_items(s), state_items(r)
        union = si | ri
        j = (len(si & ri) / len(union)) if union else 1.0
        exact += int(is_exact)
        jaccards.append(j)
        per_checkpoint[str(k)] = {"exact": is_exact, "jaccard": round(j, 4)}

    cost = None
    if replay_cost and replay_cost.get("events"):
        cost = round(
            float(replay_cost.get("seconds", 0.0))
            / (replay_cost["events"] / 1000.0), 4)

    return {
        "exact": round(exact / len(keys), 4),
        "graded": round(sum(jaccards) / len(jaccards), 4),
        "k": len(keys),
        "per_checkpoint": per_checkpoint,
        "cost_s_per_1k_events": cost,
    }


# ─── PC — Provenance Coverage (SPEC §2.3) ──────────────────────────


def _ancestors(ev_id: str, by_id: Dict[str, dict], limit: int = 1000):
    """Yield the parent chain (acyclic guard via visited set + limit)."""
    seen = set()
    cur = by_id.get(ev_id)
    while cur is not None and len(seen) < limit:
        pid = cur.get("parent_id")
        if not pid or pid in seen:
            return
        seen.add(pid)
        nxt = by_id.get(str(pid))
        if nxt is None:
            return
        yield nxt
        cur = nxt


def score_pc(log: List[dict]) -> Dict[str, Any]:
    """A citation ``c`` on an ANSWER event is traceable iff:
      (a) some origin-bearing event (INGEST or SUPERSEDE) in the log
          carries ``payload.doc_id == c``, and
      (b) an ancestor RETRIEVE event of the ANSWER lists ``c`` in
          ``payload.doc_ids``.
    Both conditions are pure log lookups — deterministic."""
    by_id = {str(e.get("event_id", "")): e for e in log}
    # Origin-bearing events: INGEST and SUPERSEDE both introduce a
    # doc's content into the system (SPEC v0.1.1 — the reference
    # implementation caught that supersede-born docs were wrongly
    # untraceable under an INGEST-only rule).
    ingested = {str((e.get("payload") or {}).get("doc_id"))
                for e in log
                if e.get("event_type") in ("INGEST", "SUPERSEDE")}

    total = 0
    traceable = 0
    per_answer = []
    for ev in log:
        if ev.get("event_type") != "ANSWER":
            continue
        cites = [str(c) for c in
                 ((ev.get("payload") or {}).get("citations") or [])]
        retrieved_in_chain: set = set()
        for anc in _ancestors(str(ev.get("event_id", "")), by_id):
            if anc.get("event_type") == "RETRIEVE":
                for d in ((anc.get("payload") or {}).get("doc_ids") or []):
                    retrieved_in_chain.add(str(d))
        ok = 0
        for c in cites:
            total += 1
            if c in ingested and c in retrieved_in_chain:
                traceable += 1
                ok += 1
        per_answer.append({
            "event_id": str(ev.get("event_id", "")),
            "citations": len(cites),
            "traceable": ok,
        })

    return {
        "pc": round(traceable / total, 4) if total else 0.0,
        "traceable": traceable,
        "total_citations": total,
        "per_answer": per_answer,
    }


__all__ = [
    "CANONICAL_TYPES", "canon", "state_items",
    "score_ac", "score_rf", "score_pc",
]
