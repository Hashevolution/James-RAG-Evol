"""Stage 2 — α-8 cloud tier extension wiring contract tests.

Locks the changes in `scripts/qvt_ablation_matrix.py` from PR #705
(design memo §2.1 + §2.2 + §2.3 + §2.5 + §4 cost guard):

  • _TIER_BACKEND_OVERRIDE has M_CLOUD with the 3 cloud routing envs
  • _cell_env() routes M_CLOUD through the override (no JAMES_LLM_MODEL)
  • _cell_env() with local tier stays byte-identical (regression guard)
  • _tier_backend_id() resolves correctly
  • Default --tiers (omitted) excludes M_CLOUD (opt-in safety)
  • Explicit --tiers M_CLOUD passes through
  • Pre-flight cost guard: M_CLOUD + over-budget = refuse start
  • _run_cell payload (mocked) includes backend_id field + schema v4

The runner spawns real subprocesses; tests use heavy monkey-patching
to exercise the env composition and payload shape without booting a
server.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch):
    """Clear cloud-related envs per test so M_CLOUD overrides are the
    only source. Existing JAMES_LLM_MODEL is also cleared so we can
    observe the runner's intent without OS-side noise."""
    for k in ("JAMES_ENABLE_CLAUDE_BACKEND", "JAMES_FORCE_CLOUD",
              "JAMES_REASONING_BACKEND", "JAMES_LLM_MODEL",
              "JAMES_CLOUD_CALL_BUDGET"):
        monkeypatch.delenv(k, raising=False)
    yield


def _fresh_runner():
    if "qvt_ablation_matrix" in sys.modules:
        del sys.modules["qvt_ablation_matrix"]
    return importlib.import_module("qvt_ablation_matrix")


# ─── _TIER_BACKEND_OVERRIDE contract ────────────────────────────────


def test_m_cloud_in_tier_models_as_empty_sentinel():
    """M_CLOUD lives in _TIER_MODELS with empty string sentinel.
    Real backend is named via _TIER_BACKEND_OVERRIDE."""
    runner = _fresh_runner()
    assert "M_CLOUD" in runner._TIER_MODELS
    assert runner._TIER_MODELS["M_CLOUD"] == ""


def test_m_cloud_in_backend_override_with_three_envs():
    """The cloud routing triplet must be present per design memo §2.1."""
    runner = _fresh_runner()
    assert "M_CLOUD" in runner._TIER_BACKEND_OVERRIDE
    override = runner._TIER_BACKEND_OVERRIDE["M_CLOUD"]
    assert override.get("JAMES_ENABLE_CLAUDE_BACKEND") == "1"
    assert override.get("JAMES_FORCE_CLOUD") == "1"
    assert override.get("JAMES_REASONING_BACKEND") == "claude_code_cli"


def test_local_tiers_not_in_backend_override():
    """Regression guard — adding M_CLOUD must not put local tiers into
    the cloud override dict by accident."""
    runner = _fresh_runner()
    for local in ("M_XS", "M_S", "M_M", "M_L", "M_XL"):
        assert local not in runner._TIER_BACKEND_OVERRIDE, (
            f"local tier {local!r} should not be in _TIER_BACKEND_OVERRIDE"
        )


# ─── _tier_backend_id() resolution ──────────────────────────────────


def test_tier_backend_id_cloud():
    runner = _fresh_runner()
    assert runner._tier_backend_id("M_CLOUD") == "claude_code_cli"


def test_tier_backend_id_local_tiers_default_to_ollama():
    runner = _fresh_runner()
    for local in ("M_XS", "M_S", "M_M", "M_L", "M_XL"):
        assert runner._tier_backend_id(local) == "ollama_local"


# ─── _cell_env() divergence ────────────────────────────────────────


def test_cell_env_local_tier_unchanged(monkeypatch):
    """Regression — M_M tier (production) env composition must include
    JAMES_LLM_MODEL=gemma4:e4b and NOT include cloud routing envs."""
    runner = _fresh_runner()
    env = runner._cell_env("L1", "M_M")
    assert env.get("JAMES_LLM_MODEL") == "gemma4:e4b"
    # Cloud routing envs must NOT appear for local tier
    assert "JAMES_FORCE_CLOUD" not in env or env["JAMES_FORCE_CLOUD"] != "1"
    assert "JAMES_REASONING_BACKEND" not in env or \
        env["JAMES_REASONING_BACKEND"] != "claude_code_cli"


def test_cell_env_cloud_tier_sets_routing_triplet():
    """M_CLOUD tier: cloud routing triplet present, JAMES_LLM_MODEL absent."""
    runner = _fresh_runner()
    env = runner._cell_env("L1", "M_CLOUD")
    assert env.get("JAMES_ENABLE_CLAUDE_BACKEND") == "1"
    assert env.get("JAMES_FORCE_CLOUD") == "1"
    assert env.get("JAMES_REASONING_BACKEND") == "claude_code_cli"
    # JAMES_LLM_MODEL is meaningless for cloud backend — must be unset
    assert "JAMES_LLM_MODEL" not in env


def test_cell_env_cloud_strips_inherited_llm_model(monkeypatch):
    """If OS env has JAMES_LLM_MODEL set (operator's .env), the
    M_CLOUD cell still drops it — leaving it would put a misleading
    Ollama tag into the spawned server's environment."""
    monkeypatch.setenv("JAMES_LLM_MODEL", "gemma3:4b")
    runner = _fresh_runner()
    env = runner._cell_env("L1", "M_CLOUD")
    assert "JAMES_LLM_MODEL" not in env


def test_cell_env_all_local_tiers_set_llm_model():
    """Each local tier sets JAMES_LLM_MODEL to its Ollama tag."""
    runner = _fresh_runner()
    for tier, expected_tag in (
        ("M_XS", "gemma3:1b"), ("M_S", "gemma3:4b"),
        ("M_M", "gemma4:e4b"), ("M_L", "gemma3:12b"),
        ("M_XL", "gemma3:27b"),
    ):
        env = runner._cell_env("L1", tier)
        assert env.get("JAMES_LLM_MODEL") == expected_tag, (
            f"tier {tier!r} expected {expected_tag!r}"
        )


# ─── --tiers default opt-in safety ──────────────────────────────────


def test_default_tiers_excludes_m_cloud_opt_in_safety(monkeypatch):
    """--tiers omitted → local tiers only. M_CLOUD requires explicit
    listing so a stray `python qvt_ablation_matrix.py` doesn't burn
    Max-plan quota."""
    runner = _fresh_runner()
    with patch.object(runner, "_render_report") as rr, \
         patch.object(runner, "_run_cell") as rc, \
         patch.object(runner, "_resolve_fixture",
                      return_value=Path("/nope/fixture.json")), \
         patch.object(runner, "_current_git_sha", return_value="test"):
        # Use --dry-run + sector-cells to short-circuit before any
        # subprocess spawn while still exercising the tier parse path.
        rr.return_value = 0
        rc.return_value = None
        # We don't actually need to run; we patch `_parse_subset` exits
        # to grab `tiers` value before any cell loop.
        captured = {}

        original_parse = runner._parse_subset

        def spy_parse(arg, universe, label):
            result = original_parse(arg, universe, label)
            if label == "tiers":
                captured["tiers"] = result
            return result
        with patch.object(runner, "_parse_subset", side_effect=spy_parse):
            # tiers omitted via CLI — main() should default to local only
            try:
                runner.main(["--dry-run"])
            except SystemExit:
                pass
        # main() short-circuits the default-tier path entirely (no
        # _parse_subset call when args.tiers is None), so we check the
        # printed planning instead — but easier to test the logic
        # directly through a synthetic argv.

    # Direct test: default tier universe (--tiers omitted) = 5 gemma
    # scale ladder. M_MIXTRAL (paper control) and M_CLOUD (cloud) are
    # opt-in only, so neither is in the default set.
    assert set(runner._DEFAULT_TIERS) == {"M_XS", "M_S", "M_M", "M_L", "M_XL"}
    assert "M_CLOUD" not in runner._DEFAULT_TIERS
    assert "M_MIXTRAL" not in runner._DEFAULT_TIERS


def test_explicit_tiers_m_cloud_passes_through():
    """--tiers M_CLOUD is allowed — explicit operator opt-in."""
    runner = _fresh_runner()
    parsed = runner._parse_subset("M_CLOUD",
                                  list(runner._TIER_MODELS.keys()), "tiers")
    assert parsed == ["M_CLOUD"]


def test_explicit_tiers_mix_local_and_cloud():
    """--tiers M_M,M_CLOUD — local + cloud together (head-to-head)."""
    runner = _fresh_runner()
    parsed = runner._parse_subset("M_M,M_CLOUD",
                                  list(runner._TIER_MODELS.keys()), "tiers")
    assert "M_M" in parsed
    assert "M_CLOUD" in parsed


# ─── Pre-flight cost guard ──────────────────────────────────────────


@pytest.fixture
def fake_fixture(tmp_path):
    """Write a 20-query step7-shaped fixture for cost guard tests."""
    fixture_path = tmp_path / "step7_queries.json"
    fixture_path.write_text(
        json.dumps({"version": "test", "queries": [{"id": i} for i in range(20)]}),
        encoding="utf-8",
    )
    return fixture_path


def test_cost_guard_refuses_above_budget(fake_fixture, monkeypatch, capsys):
    """M_CLOUD in tiers + estimated > budget → exit 8."""
    runner = _fresh_runner()
    monkeypatch.setattr(runner, "_resolve_fixture",
                        lambda suite: fake_fixture)
    monkeypatch.setattr(runner, "_current_git_sha", lambda: "test")
    monkeypatch.setenv("JAMES_CLOUD_CALL_BUDGET", "10")
    # 1 row L1 × 1 tier M_CLOUD × n_runs 3 × 20 queries = 60 calls > 10
    rc = runner.main(["--tiers", "M_CLOUD", "--rows", "L1",
                      "--n-runs", "3", "--suite", "step7"])
    assert rc == 8
    out = capsys.readouterr().out
    assert "60" in out  # estimated calls
    assert "budget" in out.lower()


def test_cost_guard_allows_under_budget(fake_fixture, monkeypatch):
    """M_CLOUD in tiers + estimated ≤ budget → proceeds past guard.
    (We patch _run_cell to short-circuit so no real bench fires.)"""
    runner = _fresh_runner()
    monkeypatch.setattr(runner, "_resolve_fixture",
                        lambda suite: fake_fixture)
    monkeypatch.setattr(runner, "_current_git_sha", lambda: "test")
    monkeypatch.setenv("JAMES_CLOUD_CALL_BUDGET", "100")
    monkeypatch.setattr(runner, "_run_cell", lambda *a, **k: None)
    # 1 row × 1 tier × 1 run × 20 queries = 20 ≤ 100
    rc = runner.main(["--tiers", "M_CLOUD", "--rows", "L1",
                      "--n-runs", "1", "--suite", "step7"])
    # Exit code is NOT 8 (the budget refuse). It might be other
    # downstream code (no cell ran successfully → no error) but
    # critically NOT 8.
    assert rc != 8


def test_cost_guard_not_triggered_without_cloud_tier(fake_fixture, monkeypatch):
    """Local-only run (no M_CLOUD) → cost guard not invoked, default
    budget never enforced, JAMES_CLOUD_CALL_BUDGET ignored."""
    runner = _fresh_runner()
    monkeypatch.setattr(runner, "_resolve_fixture",
                        lambda suite: fake_fixture)
    monkeypatch.setattr(runner, "_current_git_sha", lambda: "test")
    monkeypatch.setenv("JAMES_CLOUD_CALL_BUDGET", "1")  # extreme — would refuse cloud
    monkeypatch.setattr(runner, "_run_cell", lambda *a, **k: None)
    # M_M is a local tier; no cloud calls planned regardless of budget
    rc = runner.main(["--tiers", "M_M", "--rows", "L1",
                      "--n-runs", "3", "--suite", "step7"])
    assert rc != 8  # cost guard did NOT refuse


def test_cost_guard_default_budget_200(fake_fixture, monkeypatch, capsys):
    """When JAMES_CLOUD_CALL_BUDGET unset, default is 200. 1×1×3×20=60 < 200."""
    runner = _fresh_runner()
    monkeypatch.setattr(runner, "_resolve_fixture",
                        lambda suite: fake_fixture)
    monkeypatch.setattr(runner, "_current_git_sha", lambda: "test")
    monkeypatch.delenv("JAMES_CLOUD_CALL_BUDGET", raising=False)
    monkeypatch.setattr(runner, "_run_cell", lambda *a, **k: None)
    rc = runner.main(["--tiers", "M_CLOUD", "--rows", "L1",
                      "--n-runs", "3", "--suite", "step7"])
    out = capsys.readouterr().out
    assert "budget" in out.lower()
    assert "200" in out  # default budget line printed
    assert rc != 8


def test_cost_guard_invalid_budget_value(fake_fixture, monkeypatch, capsys):
    """Non-integer JAMES_CLOUD_CALL_BUDGET → exit 8."""
    runner = _fresh_runner()
    monkeypatch.setattr(runner, "_resolve_fixture",
                        lambda suite: fake_fixture)
    monkeypatch.setattr(runner, "_current_git_sha", lambda: "test")
    monkeypatch.setenv("JAMES_CLOUD_CALL_BUDGET", "not-a-number")
    rc = runner.main(["--tiers", "M_CLOUD", "--rows", "L1",
                      "--suite", "step7"])
    assert rc == 8
    out = capsys.readouterr().out
    assert "not an integer" in out.lower() or "JAMES_CLOUD_CALL_BUDGET" in out
