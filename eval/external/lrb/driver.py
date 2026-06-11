"""LRB driver — load scenario, walk events for each SUT, run queries
at each timestamp, compute per-axis scores. Deterministic.

The driver doesn't know which SUT it's running — it calls a generic
adapter interface (``ingest`` / ``update`` / ``supersede`` / ``delete``
/ ``retrieve``) defined in `eval/external/lrb/adapters/`.

Per the prereg, the driver:
  1. Loads scenario fixture (sha-pinned in result)
  2. Replays the initial corpus (week 0 INGEST)
  3. For each timestamp T in {0, 6, 12}:
       a. Walk events with ``week <= T`` (apply to SUT)
       b. For each query, call ``adapter.retrieve(q, k=10)``
          and measure latency, retrieved doc ids, retrieved-context
          token count
  4. Score via `lrb_scorer.score_axes` against per-T gold
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Protocol

from .scorer import score_axes


class LrbAdapter(Protocol):
    """SUT contract for LRB.

    Adapters MUST be deterministic given the same event sequence.
    """

    def ingest(self, doc_id: str, title: str, text: str,
               week: int) -> None: ...

    def update(self, doc_id: str, title: str, text: str,
               week: int) -> None: ...

    def supersede(self, old_doc_id: str, new_doc_id: str,
                  title: str, text: str, week: int) -> None: ...

    def delete(self, doc_id: str, week: int) -> None: ...

    def retrieve(self, q: str, k: int, t_week: int) -> List[str]:
        """Return top-k retrieved doc_ids for query ``q`` evaluated at
        timestamp ``t_week``. May or may not honour ``t_week`` (Vanilla
        ignores it; JAMES uses validity windows)."""

    def retrieved_text_length(self, doc_ids: List[str]) -> int:
        """Total character count of the bodies of the returned
        retrieved docs. Used to compute token-cost proxy (chars/4)."""


@dataclass
class QueryResult:
    query_id: str
    timestamp: str
    week:      int
    gold:      List[str]
    retrieved: List[str]
    latency_s: float
    context_chars: int


@dataclass
class SutRunResult:
    sut_name: str
    fixture_sha: str
    per_query: List[QueryResult] = field(default_factory=list)
    elapsed_s: float = 0.0


def load_scenario(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fixture_sha(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _apply_event(adapter: LrbAdapter, ev: dict) -> None:
    op = ev["op"]
    a = ev["args"]
    w = ev["week"]
    if op == "INGEST":
        adapter.ingest(a["doc_id"], a["title"], a["text"], w)
    elif op == "UPDATE":
        adapter.update(a["doc_id"], a["title"], a["text"], w)
    elif op == "SUPERSEDE":
        adapter.supersede(a["old_doc_id"], a["new_doc_id"],
                          a["title"], a["text"], w)
    elif op == "DELETE":
        adapter.delete(a["doc_id"], w)
    else:
        raise ValueError(f"unknown op: {op}")


def run_sut(adapter_factory: Callable[[], LrbAdapter],
            scenario: dict,
            fixture_sha_hex: str,
            sut_name: str,
            timestamps: Optional[List[int]] = None,
            k: int = 10) -> SutRunResult:
    """Run one SUT over the scenario across all timestamps.

    Per prereg, the SUT instance is **fresh per timestamp** — we
    re-replay events up to T from a fresh adapter. This isolates each
    T-evaluation from cross-T state contamination and matches "what if
    a user asks at week T?" semantics. Latency therefore measures
    retrieval-only at the T snapshot (not retrieve+catchup).
    """
    if timestamps is None:
        # Parse T=0 / T=6w / T=12w
        timestamps = []
        for ts in scenario["timestamps"]:
            ts = ts.replace("T=", "").replace("w", "")
            timestamps.append(int(ts))

    result = SutRunResult(sut_name=sut_name, fixture_sha=fixture_sha_hex)
    start = time.perf_counter()
    initial = scenario["initial_corpus"]
    events = scenario["events"]
    queries = scenario["queries"]

    for t_week in timestamps:
        adapter = adapter_factory()

        # Apply initial corpus (week 0 INGEST)
        for doc in initial:
            adapter.ingest(doc["doc_id"], doc["title"], doc["text"], 0)

        # Apply events through t_week (inclusive)
        for ev in events:
            if ev["week"] <= t_week:
                _apply_event(adapter, ev)

        # Run queries
        ts_label = f"T={t_week}w" if t_week > 0 else "T=0"
        for q in queries:
            gold = q["gold"][ts_label]
            t0 = time.perf_counter()
            retrieved = adapter.retrieve(q["q"], k=k, t_week=t_week)
            lat = time.perf_counter() - t0
            chars = adapter.retrieved_text_length(retrieved)
            result.per_query.append(QueryResult(
                query_id=q["query_id"],
                timestamp=ts_label,
                week=t_week,
                gold=gold,
                retrieved=retrieved,
                latency_s=lat,
                context_chars=chars,
            ))

    result.elapsed_s = time.perf_counter() - start
    return result


def score_run(run: SutRunResult, k_recall: int = 10) -> dict:
    """Compute the 7 LRB Phase A axes from a per-query run result."""
    rows = [{
        "query_id":      qr.query_id,
        "timestamp":     qr.timestamp,
        "gold":          qr.gold,
        "retrieved":     qr.retrieved,
        "latency_s":     qr.latency_s,
        "context_chars": qr.context_chars,
    } for qr in run.per_query]
    return score_axes(rows, k_recall=k_recall)
