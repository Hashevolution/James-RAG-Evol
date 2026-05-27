"""Idea 1 (2026-05-27) — Path Recall/Precision contract for scripts/bench.py.

Pins the parser of JAMES graph-path strings and the per-query metrics
computation. Companion to `test_bench_mode_flag.py` (F1 --mode flag)
and `test_evidence_scope.py` (L.A/F5 scope formula).

Why these tests exist: bench.py is the harness that produces the
"path-level ground truth" measurements the result-doc cites. If the
parser silently mis-extracts node names, the recall number is wrong
in a way no other test catches.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.bench import _parse_path_nodes, _path_metrics  # noqa: E402


# ─── parser ────────────────────────────────────────────────────────


def test_parser_empty_inputs():
    assert _parse_path_nodes([]) == set()
    assert _parse_path_nodes(None) == set()


def test_parser_skips_non_string_entries():
    """Defensive — graph_paths is List[str] in production but the parser
    should not blow up if some other type sneaks in via a future
    response-shape change."""
    paths = [123, None, {"x": 1}, "Anthropic -[RELATED_TO(w=0.7)]→ Claude"]
    nodes = _parse_path_nodes(paths)
    assert nodes == {"Anthropic", "Claude"}


def test_parser_single_hop():
    paths = ["BlackRock -[OPERATES(w=0.5)]→ 미국 스팟 BTC ETF"]
    assert _parse_path_nodes(paths) == {"BlackRock", "미국 스팟 BTC ETF"}


def test_parser_multi_hop_extracts_intermediate():
    """3-hop path — all 4 nodes captured."""
    paths = [
        "David Soria Parra -[RELATED_TO(w=0.7)]→ MCP "
        "-[RELATED_TO(w=0.7)]→ 08_MCP_(Model_Context_Protocol) "
        "-[RELATED_TO(w=0.7)]→ OpenAI"
    ]
    assert _parse_path_nodes(paths) == {
        "David Soria Parra",
        "MCP",
        "08_MCP_(Model_Context_Protocol)",
        "OpenAI",
    }


def test_parser_dedup_across_paths():
    """Same node appearing in multiple paths counts once."""
    paths = [
        "Anthropic -[RELATED_TO(w=0.7)]→ Claude Sonnet 4.6",
        "Anthropic -[RELATED_TO(w=0.7)]→ MCP",
    ]
    assert _parse_path_nodes(paths) == {"Anthropic", "Claude Sonnet 4.6", "MCP"}


def test_parser_preserves_korean_entity_names():
    """JAMES wiki names use Korean — must not be mangled by str ops."""
    paths = ["RAG (검색 증강 생성) -[RELATED_TO(w=0.5)]→ LLM"]
    nodes = _parse_path_nodes(paths)
    assert "RAG (검색 증강 생성)" in nodes
    assert "LLM" in nodes


# ─── _path_metrics ─────────────────────────────────────────────────


def test_metrics_none_when_no_expected():
    """No expected_path declared → no metric reported (caller omits)."""
    assert _path_metrics(["Anthropic -[X]→ Claude"], []) is None
    assert _path_metrics([], []) is None


def test_metrics_full_recall_single_node():
    paths = ["Anthropic -[RELATED_TO(w=0.7)]→ Claude Sonnet 4.6"]
    pm = _path_metrics(paths, ["Anthropic"])
    assert pm["path_recall"] == 1.0
    assert pm["hits"] == 1
    assert pm["expected_count"] == 1
    assert pm["missed"] == []


def test_metrics_partial_recall():
    """Expect 2 nodes, find 1 → recall=0.5."""
    paths = ["Anthropic -[X(w=0.5)]→ MCP"]
    pm = _path_metrics(paths, ["Anthropic", "Claude Sonnet 4.6"])
    assert pm["path_recall"] == 0.5
    assert pm["hits"] == 1
    assert pm["missed"] == ["Claude Sonnet 4.6"]


def test_metrics_zero_recall_no_overlap():
    paths = ["Anthropic -[X(w=0.5)]→ MCP"]
    pm = _path_metrics(paths, ["BlackRock", "미국 스팟 BTC ETF"])
    assert pm["path_recall"] == 0.0
    assert pm["hits"] == 0
    assert sorted(pm["missed"]) == sorted(
        ["BlackRock", "미국 스팟 BTC ETF"]
    )


def test_metrics_zero_recall_when_no_paths_returned():
    """retrieval-mode bench may produce 0 graph_paths on some queries —
    recall must be 0 (not crash, not None)."""
    pm = _path_metrics([], ["Anthropic"])
    assert pm["path_recall"] == 0.0
    assert pm["actual_node_count"] == 0
    assert pm["path_precision"] == 0.0


def test_metrics_precision_low_when_dfs_fans_out():
    """Realistic shape — DFS returns 4 nodes, only 1 is expected. Recall
    is 1.0 but precision is 0.25. Pin this so future readers don't
    misinterpret 'low precision = bad routing'."""
    paths = [
        "Anthropic -[X]→ Claude Sonnet 4.6 -[X]→ Other -[X]→ Another",
    ]
    pm = _path_metrics(paths, ["Anthropic"])
    assert pm["path_recall"] == 1.0
    assert pm["actual_node_count"] == 4
    assert pm["path_precision"] == 0.25


def test_metrics_round_to_3_decimals():
    """3 expected, 1 hit → 0.333… → rounded to 0.333 (not 0.3 or full
    float). Stable string-compare for result-doc snippets."""
    paths = ["A -[X]→ B"]
    pm = _path_metrics(paths, ["A", "C", "D"])
    assert pm["path_recall"] == 0.333
