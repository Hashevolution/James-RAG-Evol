"""LRB Phase B driver — supports (query_time, valid_time) queries.

S2 scenario contains queries with per-query (query_time, valid_time)
pairs. The driver builds the adapter up to query_time, then asks each
query with its own valid_time. Vanilla/Naive-supersede ignore
valid_time (they cannot time-travel); JAMES honours it.

Cross-scenario use: same code can run on LRB-S1 too — queries on S1
have implicit query_time = valid_time = T-stamp.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, Dict, List

from .driver import LrbAdapter, QueryResult, SutRunResult
from .scorer import score_axes


def load_scenario(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _apply_event(adapter, ev: dict) -> None:
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


def run_sut_phase_b(adapter_factory: Callable[[], LrbAdapter],
                    scenario: dict,
                    fixture_sha_hex: str,
                    sut_name: str,
                    k: int = 10) -> SutRunResult:
    """Phase B: each query carries (query_time, valid_time). The
    adapter is built up to MAX(query_time) once; queries dispatch
    by their valid_time.
    """
    result = SutRunResult(sut_name=sut_name, fixture_sha=fixture_sha_hex)
    start = time.perf_counter()
    initial = scenario["initial_corpus"]
    events = scenario["events"]
    queries = scenario["queries"]

    # Group queries by query_time (typically a single time, e.g., 24)
    from collections import defaultdict
    by_qt: Dict[int, List[dict]] = defaultdict(list)
    for q in queries:
        by_qt[q["query_time"]].append(q)

    for query_time in sorted(by_qt):
        adapter = adapter_factory()
        for doc in initial:
            adapter.ingest(doc["doc_id"], doc["title"], doc["text"], 0)
        for ev in events:
            if ev["week"] <= query_time:
                _apply_event(adapter, ev)

        for q in by_qt[query_time]:
            gold = q["gold"]
            valid_time = q["valid_time"]
            t0 = time.perf_counter()
            retrieved = adapter.retrieve_at(
                q["q"], k=k, query_time=query_time,
                valid_time=valid_time)
            lat = time.perf_counter() - t0
            chars = adapter.retrieved_text_length(retrieved)
            result.per_query.append(QueryResult(
                query_id=q["query_id"],
                timestamp=f"qt={query_time}/vt={valid_time}",
                week=valid_time,
                gold=gold,
                retrieved=retrieved,
                latency_s=lat,
                context_chars=chars,
            ))

    result.elapsed_s = time.perf_counter() - start
    return result


def score_run(run: SutRunResult, k_recall: int = 10) -> dict:
    rows = [{
        "query_id":      qr.query_id,
        "timestamp":     qr.timestamp,
        "gold":          qr.gold,
        "retrieved":     qr.retrieved,
        "latency_s":     qr.latency_s,
        "context_chars": qr.context_chars,
    } for qr in run.per_query]
    return score_axes(rows, k_recall=k_recall)
