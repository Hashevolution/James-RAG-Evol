"""scripts/bench.py --mode flag contract tests.

Pins the precedence rule (per-query `mode` > --mode CLI > suite
`default_mode` > omit) without invoking the live server. We patch
`requests.post` and inspect the body that `_run_one` would send.

Companion to:
  - `test_chat_mode_picker.py` (server-side ``mode_override`` Pydantic +
    engine wiring contract — pre-existing, covers the receiving side)
  - `feedback_bench_step7_chat_mode_passthrough` memory note (why the
    flag exists at all: step7 RAG queries get classified as chat
    by IntentClassifier and bypass run_retrieval_pipeline)
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _stub_response(status: int = 200, json_body=None):
    r = MagicMock()
    r.status_code = status
    r.text = "" if json_body is None else "stub"
    r.json.return_value = json_body or {
        "answer": "stub", "blocked": False, "graph_paths": [], "mode": "retrieval",
        "unified_score": 0.5,
    }
    return r


@pytest.fixture
def captured_post():
    """Patch requests.post and return the MagicMock for inspection."""
    from scripts import bench as bench_mod
    with patch.object(bench_mod.requests, "post", return_value=_stub_response()) as m:
        yield m


def _q(qid=1, text="test", category="retrieve", mode=None):
    out = {"id": qid, "text": text, "category": category}
    if mode is not None:
        out["mode"] = mode
    return out


def test_default_no_mode_field_in_body(captured_post):
    """Baseline — no --mode + no per-query mode → body has no mode_override key."""
    from scripts.bench import _run_one
    _run_one("KEY", _q(), "/query/", 30, None)
    body = captured_post.call_args.kwargs["json"]
    assert "mode_override" not in body


def test_default_mode_applied_when_per_query_absent(captured_post):
    """--mode=retrieval (passed as default_mode) → body.mode_override='retrieval'."""
    from scripts.bench import _run_one
    _run_one("KEY", _q(), "/query/", 30, "retrieval")
    body = captured_post.call_args.kwargs["json"]
    assert body["mode_override"] == "retrieval"


def test_per_query_mode_overrides_default(captured_post):
    """Per-query `mode` field wins over the --mode CLI default."""
    from scripts.bench import _run_one
    _run_one("KEY", _q(mode="meta"), "/query/", 30, "retrieval")
    body = captured_post.call_args.kwargs["json"]
    assert body["mode_override"] == "meta"


def test_empty_string_per_query_falls_back_to_default(captured_post):
    """Empty string per-query mode is falsy → default_mode takes over.
    (Same precedence rule as engine.py:_query_impl which treats empty as
    'no override' and consults QueryRouter — but here we still want the
    bench CLI default to apply, otherwise --mode would be silently
    overridable by a stray empty field.)"""
    from scripts.bench import _run_one
    _run_one("KEY", _q(mode=""), "/query/", 30, "retrieval")
    body = captured_post.call_args.kwargs["json"]
    assert body["mode_override"] == "retrieval"


def test_body_still_has_required_fields(captured_post):
    """Adding mode_override must not displace question/api_key/session_id."""
    from scripts.bench import _run_one
    _run_one("KEY", _q(qid=7, text="q7"), "/query/", 30, "retrieval")
    body = captured_post.call_args.kwargs["json"]
    assert body["question"] == "q7"
    assert body["api_key"] == "KEY"
    assert body["session_id"] == "bench_step7_7"
