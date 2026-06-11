"""LRB v0.2.1 cross-model tests — wrapper + scorer + parse + token-mode
reproduction."""
from __future__ import annotations

from pathlib import Path

import pytest

from eval.external.lrb.adapters import (
    JamesValidityAdapter, NaiveSupersedeAdapter, VanillaRagAdapter)
from eval.external.lrb.cross_model import retrieve_at_cross_model
from eval.external.lrb.driver import fixture_sha, load_scenario
from eval.external.lrb.driver_phase_b import (
    run_sut_phase_b, score_run)
from eval.external.lrb.llm_rerank import (
    _build_prompt, _is_claude_model, _is_ollama_model, _parse_scores,
    rerank)

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_S1 = ROOT / "eval" / "external" / "_fixtures" / "lrb" / \
    "scenario_S1_quarterly.json"
FIXTURE_S2 = ROOT / "eval" / "external" / "_fixtures" / "lrb" / \
    "scenario_S2_yearly_timetravel.json"


# ── get_doc accessor ─────────────────────────────────────────────────


def test_get_doc_vanilla():
    a = VanillaRagAdapter()
    a.ingest("d1", "Title", "Body text", 0)
    assert a.get_doc("d1") == ("Title", "Body text")
    assert a.get_doc("missing") is None


def test_get_doc_naive():
    a = NaiveSupersedeAdapter()
    a.ingest("d1", "Title", "Body", 0)
    assert a.get_doc("d1") == ("Title", "Body")


def test_get_doc_james():
    a = JamesValidityAdapter()
    a.ingest("d1", "Title", "Body", 0)
    assert a.get_doc("d1") == ("Title", "Body")


def test_get_doc_james_returns_text_even_after_supersede():
    """get_doc returns the data; validity is enforced at retrieve_at
    time. The wrapper feeds doc_ids already filtered by retrieve_at,
    so get_doc must not re-filter."""
    a = JamesValidityAdapter()
    a.ingest("d1", "Old", "Old body", 0)
    a.supersede("d1", "d1.v2", "New", "New body", 5)
    # d1 is "out" of validity at t=10 but get_doc still returns data
    # (read-only accessor used downstream of retrieve_at).
    assert a.get_doc("d1") == ("Old", "Old body")
    assert a.get_doc("d1.v2") == ("New", "New body")


# ── Model dispatch ──────────────────────────────────────────────────


def test_dispatch_ollama_models():
    assert _is_ollama_model("gemma4:e4b")
    assert _is_ollama_model("gemma3:12b")
    assert _is_ollama_model("mixtral:8x7b")
    assert _is_ollama_model("mistral:7b")
    assert _is_ollama_model("llama3.1:8b")
    assert _is_ollama_model("qwen2.5:7b")
    assert not _is_ollama_model("claude-haiku-4-5")
    assert not _is_ollama_model("gpt-4")


def test_dispatch_claude_models():
    assert _is_claude_model("claude-haiku-4-5")
    assert _is_claude_model("claude-sonnet-4-6")
    assert _is_claude_model("claude-opus-4-7")
    assert not _is_claude_model("gemma4:e4b")


# ── Prompt construction ──────────────────────────────────────────────


def test_build_prompt_contains_query_and_candidates():
    p = _build_prompt(
        "Who directs Public Works?",
        [("d1", "Dept", "Body of dept doc"),
         ("d2", "Other Dept", "Other body")])
    assert "Who directs Public Works?" in p
    assert "[d1] Dept" in p
    assert "[d2] Other Dept" in p
    assert '"scores"' in p


def test_build_prompt_truncates_long_text():
    long_text = "X" * 1000
    p = _build_prompt("q", [("d1", "T", long_text)])
    # snippet capped at 300 chars
    assert p.count("X") <= 300


# ── Score parsing ──────────────────────────────────────────────────


def test_parse_scores_strict_json():
    assert _parse_scores('{"scores": [8, 6, 2]}') == [8.0, 6.0, 2.0]


def test_parse_scores_clipped():
    assert _parse_scores('{"scores": [15, -3, 5]}') == [10.0, 0.0, 5.0]


def test_parse_scores_with_prose():
    text = ('Here are the scores:\n{"scores": [9, 7]}\n'
            'I hope that helps!')
    assert _parse_scores(text) == [9.0, 7.0]


def test_parse_scores_empty_on_garbage():
    assert _parse_scores("not json") == []
    assert _parse_scores("") == []
    assert _parse_scores('{"wrong_key": [1, 2]}') == []


def test_parse_scores_float_ok():
    assert _parse_scores('{"scores": [8.5, 6.25, 2.0]}') == [
        8.5, 6.25, 2.0]


# ── Wrapper behaviour (token mode = pass-through) ────────────────────


def test_token_mode_passes_through():
    a = VanillaRagAdapter()
    a.ingest("d1", "Public Works", "Director", 0)
    a.ingest("d2", "Other", "Unrelated", 0)
    direct = a.retrieve_at("Public Works director", k=2,
                            query_time=0, valid_time=0)
    wrapped = retrieve_at_cross_model(
        a, "Public Works director", k=2,
        query_time=0, valid_time=0,
        mode="token", model="any")
    assert direct == wrapped


def test_invalid_mode_raises():
    a = VanillaRagAdapter()
    with pytest.raises(ValueError):
        retrieve_at_cross_model(a, "q", k=5, query_time=0,
                                valid_time=0, mode="invalid",
                                model="x")


def test_empty_pool_returns_empty():
    a = VanillaRagAdapter()
    # Nothing ingested
    result = retrieve_at_cross_model(
        a, "q", k=5, query_time=0, valid_time=0,
        mode="llm-grounded", model="gemma4:e4b")
    assert result == []


# ── Token-mode reproduction vs Phase B baseline ──────────────────────


def test_token_mode_s1_reproduces_phase_b_baseline():
    """v0.2.1 wrapper in token mode MUST produce byte-identical scores
    to Phase B baseline (per prereg §1.4 'cross-model = additive' rule).
    """
    from scripts.research.lrb_run_v021_cross_model import (
        run_sut_cross_model)
    from eval.external.lrb.driver import score_run as score_run_phase_a
    sc = load_scenario(FIXTURE_S1)
    sha = fixture_sha(FIXTURE_S1)
    for cls, expected_r1 in [
        (VanillaRagAdapter, 0.616667),
        (NaiveSupersedeAdapter, 0.738889),
        (JamesValidityAdapter, 0.738889),
    ]:
        r = run_sut_cross_model(cls, sc, sha, sut_name="t",
                                mode="token", model="token-baseline",
                                ollama_url="http://localhost:11434",
                                timeout=10.0, k=10)
        axes = score_run_phase_a(r)
        assert abs(axes["overall"]["exploratory"]["R@1"]
                    - expected_r1) < 1e-5


def test_token_mode_s2_reproduces_phase_b_baseline():
    from scripts.research.lrb_run_v021_cross_model import (
        run_sut_cross_model)
    sc = load_scenario(FIXTURE_S2)
    sha = fixture_sha(FIXTURE_S2)
    for cls, expected_r1 in [
        (VanillaRagAdapter, 0.225),
        (NaiveSupersedeAdapter, 0.5375),
        (JamesValidityAdapter, 0.7125),
    ]:
        r = run_sut_cross_model(cls, sc, sha, sut_name="t",
                                mode="token", model="token-baseline",
                                ollama_url="http://localhost:11434",
                                timeout=10.0, k=10)
        axes = score_run(r)
        assert abs(axes["overall"]["exploratory"]["R@1"]
                    - expected_r1) < 1e-5
