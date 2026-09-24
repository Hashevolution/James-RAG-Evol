"""The matrix runner applies the baseline capture's integrity guards.

On 2026-09-22 the T0 smoke of ``scripts/qvt_ablation_matrix.py`` was
stopped at 4/7 answers reading "답변 생성에 실패했습니다." — generation
failures that ``core/reasoning/pipeline.py`` softens into abstentions and
the oracle would have scored as correct refusals. Every guard against
that already existed in ``scripts/qvt_capture_baseline.py``; the matrix
runner was a parallel copy and had none of them. Both now import
``eval/qvt/capture_integrity.py``.

These tests are behavioural and mock the server, bench and oracle, so
they run the same on CI as on the capture host.

Run:
  python -m pytest tests/test_qvt_matrix_integrity_guards.py -q
"""
from __future__ import annotations

import importlib
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from eval.qvt import capture_integrity as ci  # noqa: E402

_PIN_KEYS = tuple(ci.ROUTING_PIN_ENV)


@pytest.fixture
def runner(monkeypatch):
    for k in _PIN_KEYS + ("JAMES_ENABLE_CLAUDE_BACKEND", "JAMES_FORCE_CLOUD",
                          "JAMES_REASONING_BACKEND", "JAMES_LLM_MODEL"):
        monkeypatch.delenv(k, raising=False)
    sys.modules.pop("qvt_ablation_matrix", None)
    return importlib.import_module("qvt_ablation_matrix")


# ─── routing pin ────────────────────────────────────────────────────


def test_every_tier_is_pinned(runner):
    """Without the kill-switch, resolve_for_mode ignores JAMES_LLM_MODEL
    and the local tiers all measure the preference-list model."""
    for tier in runner._TIER_MODELS:
        env = runner._cell_env("L1", tier)
        for k, v in ci.ROUTING_PIN_ENV.items():
            assert env.get(k) == v, (tier, k)


def test_every_row_and_sector_cell_is_pinned(runner):
    for row in runner._ROW_ENVS:
        env = runner._cell_env(row, "M_M")
        assert env.get("JAMES_DISABLE_MODE_AWARE_ROUTING") == "1", row
    for cell in runner._SECTOR_CELL_ENVS:
        env = runner._cell_env("L1", "M_M", sector_cell=cell)
        assert env.get("JAMES_DISABLE_MODE_AWARE_ROUTING") == "1", cell


def test_no_overlay_can_unset_the_pin(runner):
    """The pin is applied before the tier / sector overlays. That is
    only safe while no overlay names a pin key — make that a rule."""
    overlays = (list(runner._ROW_ENVS.values())
                + list(runner._SECTOR_CELL_ENVS.values())
                + list(runner._TIER_BACKEND_OVERRIDE.values())
                + [runner._FIXED_ENV])
    for overlay in overlays:
        assert not set(overlay) & set(_PIN_KEYS), overlay


def test_operator_env_cannot_unpin(runner, monkeypatch):
    """An operator .env with routing re-enabled must not leak in."""
    monkeypatch.setenv("JAMES_DISABLE_MODE_AWARE_ROUTING", "")
    monkeypatch.setenv("JAMES_SETTINGS_USE_DB", "1")
    env = runner._cell_env("L1", "M_S")
    assert env["JAMES_DISABLE_MODE_AWARE_ROUTING"] == "1"
    assert env["JAMES_SETTINGS_USE_DB"] == "0"


# ─── shared abort rule ──────────────────────────────────────────────


@pytest.mark.parametrize("health, aborts", [
    ({"total": 7, "failed": 0, "error": None}, False),
    ({"total": 7, "failed": 1, "error": None}, True),   # no tolerated fraction
    ({"total": 0, "failed": 0, "error": None}, True),   # nothing to score
    ({"total": 0, "failed": 0, "error": "JSONDecodeError: x"}, True),
])
def test_abort_reason(health, aborts):
    assert bool(ci.abort_reason(health)) is aborts


def test_unreadable_bench_file_aborts(tmp_path):
    """Before abort_reason, an unparsable file read as failed == 0."""
    bad = tmp_path / "bench.json"
    bad.write_text("{not json", encoding="utf-8")
    health = ci.answer_health(bad)
    assert health["failed"] == 0
    assert "unreadable" in ci.abort_reason(health)


# ─── provenance ─────────────────────────────────────────────────────


def test_local_cell_effective_model_is_the_tier_model(runner):
    snap = ci.resolved_models(runner._cell_env("L1", "M_S"))
    assert snap["mode_aware_routing_disabled"] is True
    assert snap["effective"]["tag"] == runner._TIER_MODELS["M_S"]
    assert "synth_override" not in snap


def test_cloud_cell_names_the_synth_backend(runner):
    """M_CLOUD drops JAMES_LLM_MODEL; the answers are written by the
    cloud backend, which the local effective tag alone would hide."""
    snap = ci.resolved_models(runner._cell_env("L1", "M_CLOUD"))
    assert snap["synth_override"]["backend"] == "claude_code_cli"
    assert snap["synth_override"]["applies_to"] == "synth stage only"


# ─── _run_cell: abort without writing, record on success ────────────


def _bench(tmp: Path, answers):
    p = tmp / "bench_x_step7_y.json"
    rows = [{"id": f"q{i}", "answer_preview": a, "blocked": False}
            for i, a in enumerate(answers)]
    rows.append({"id": "sec", "answer_preview": "blocked", "blocked": True})
    p.write_text(json.dumps({"results": rows}, ensure_ascii=False),
                 encoding="utf-8")
    return p


def _fake_result():
    axis = SimpleNamespace(mean_recall=0.8, mean_accuracy=0.7, f1=0.5,
                           mean_chars=1500.0, mean_s=130.0)
    return SimpleNamespace(
        path_coverage=axis, graded_answer=axis, abstention=axis,
        token_cost=axis, latency_cost=axis,
        summary=lambda: "fake", to_dict=lambda: {"fake": True})


def _patched(runner, tmp, bench_path, host_record=True):
    def fake_bench(*a, host_log=None, **k):
        if host_log is not None and host_record:
            host_log.append({"run": len(host_log) + 1, "before": {}})
        return bench_path
    return [
        mock.patch.object(runner, "ROOT", tmp),
        mock.patch.object(runner, "_resolve_output_dir", return_value=tmp),
        mock.patch.object(runner, "_run_single_bench", side_effect=fake_bench),
        mock.patch.object(runner, "score_five_axis", return_value=_fake_result()),
        mock.patch.object(runner, "score_five_axis_by_question_type",
                          return_value={}),
        mock.patch.object(runner, "_backend_registry_snapshot", return_value={}),
        mock.patch.object(runner, "_router_evidence", return_value={}),
    ]


def _run(runner, patches):
    for p in patches:
        p.start()
    try:
        return runner._run_cell("L1", "M_M", 2, {"version": "t"}, "abc1234",
                                resume=False)
    finally:
        for p in patches:
            p.stop()


def test_failing_answers_abort_the_cell_and_write_nothing(runner):
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        bench = _bench(tmp, ["정상 답변", "답변 생성에 실패했습니다.", "정상"])
        out = _run(runner, _patched(runner, tmp, bench))
        assert out is None
        assert not list(tmp.glob("qvt-ablation-cell-*.json")), \
            "a laundered cell on disk would be read by --resume / render"


def test_healthy_cell_records_v6_integrity_fields(runner):
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        bench = _bench(tmp, ["정상 답변", "자료에 없음. 관련된 문서가 없습니다."])
        payload = _run(runner, _patched(runner, tmp, bench))
        assert payload is not None
        assert payload["schema"] == "qvt-ablation-cell-v6"
        assert payload["resolved_models"]["effective"]["tag"] == "gemma4:e4b"
        # the blocked security fixture is not counted; the semantic
        # abstention is a measurement, not a failure
        assert [h["failed"] for h in payload["answer_health"]] == [0, 0]
        assert [h["total"] for h in payload["answer_health"]] == [2, 2]
        assert [h["run"] for h in payload["host_state"]] == [1, 2]
        written = json.loads(
            (tmp / "qvt-ablation-cell-L1-M_M.json").read_text(encoding="utf-8"))
        assert written["answer_health"] == payload["answer_health"]
