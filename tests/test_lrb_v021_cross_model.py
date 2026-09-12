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
    score_run)
from eval.external.lrb.llm_rerank import (
    _build_prompt, _is_claude_model, _is_ollama_model, _parse_scores)

from tests._lrb_fixtures import ensure_scenario

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_S1 = ensure_scenario("S1")
FIXTURE_S2 = ensure_scenario("S2")


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


def test_token_mode_s2_matches_the_repaired_fixture():
    """Token-mode R@1 for the three SUTs on the collision-repaired S2.

    These are NOT the published Phase B figures, and the difference is
    deliberate. The published run (0.225 / 0.5375 / 0.7125) was measured
    on a fixture whose historical-mid-policy queries injected a bare
    time offset — "…Policy 1: Operating Standard 16 weeks ago?" — that
    matched co-pol-016's numbered title, so the cell scored a numeric
    token collision instead of time-travel retrieval. Diagnosed in
    reports/research-runs/lrb-s2-fixture-nonreproduction-20260819.md,
    repaired 2026-09-08 by spelling policy titles out; the numbers below
    are the re-run that repair requires.

    The artifact suppressed all three SUTs, so the ordering claim and
    the headline gap survive it: V < N < J still holds and J − N is
    0.175 on both fixtures, unchanged to four decimals.

    Until the preprint is re-baselined or footnoted — decision #2 in
    that report, an operator call — papers/lrb-preprint/README.md,
    .zenodo.json and the v0.4.4 release notes still carry the old
    figures. Green here means the repository reproduces itself, not
    that it reproduces the paper.
    """
    from scripts.research.lrb_run_v021_cross_model import (
        run_sut_cross_model)
    sc = load_scenario(FIXTURE_S2)
    sha = fixture_sha(FIXTURE_S2)
    for cls, expected_r1 in [
        (VanillaRagAdapter, 0.2500),      # published 0.225
        (NaiveSupersedeAdapter, 0.5875),  # published 0.5375
        (JamesValidityAdapter, 0.7625),   # published 0.7125
    ]:
        r = run_sut_cross_model(cls, sc, sha, sut_name="t",
                                mode="token", model="token-baseline",
                                ollama_url="http://localhost:11434",
                                timeout=10.0, k=10)
        axes = score_run(r)
        assert abs(axes["overall"]["exploratory"]["R@1"]
                    - expected_r1) < 1e-5


# ── Reranker fallback accounting (2026-09-12) ─────────────────────────


def test_rerank_counts_a_failed_llm_call_as_fallback(monkeypatch):
    """An empty score list (timeout / HTTP error / garbage output) pads
    every candidate with 0.0, so the stable sort returns the
    token-overlap order. That row must be visible as a fallback."""
    from eval.external.lrb import llm_rerank

    llm_rerank.STATS.reset()
    cands = [("d1", "t1", "x"), ("d2", "t2", "y")]

    monkeypatch.setattr(llm_rerank, "_call_ollama", lambda *a, **k: [])
    out = llm_rerank.rerank("q", cands, model="gemma4:e4b")
    assert [d for d, _ in out] == ["d1", "d2"]
    assert llm_rerank.STATS.calls == 1
    assert llm_rerank.STATS.fallbacks == 1
    assert llm_rerank.STATS.last_fallback is True

    monkeypatch.setattr(llm_rerank, "_call_ollama",
                        lambda *a, **k: [1.0, 9.0])
    out = llm_rerank.rerank("q", cands, model="gemma4:e4b")
    assert [d for d, _ in out] == ["d2", "d1"]
    assert llm_rerank.STATS.calls == 2
    assert llm_rerank.STATS.fallbacks == 1
    assert llm_rerank.STATS.last_fallback is False


def test_run_sut_records_per_query_fallback_and_matches_token_mode(monkeypatch):
    """With a reranker that always fails, every llm-grounded row is
    flagged and the retrieved lists equal token mode exactly; token
    mode itself never flags."""
    from eval.external.lrb import llm_rerank
    from scripts.research.lrb_run_v021_cross_model import (
        run_sut_cross_model)

    sc = load_scenario(FIXTURE_S2)
    sha = fixture_sha(FIXTURE_S2)
    monkeypatch.setattr(llm_rerank, "_call_ollama", lambda *a, **k: [])

    grounded = run_sut_cross_model(
        JamesValidityAdapter, sc, sha, sut_name="t", mode="llm-grounded",
        model="gemma4:e4b", ollama_url="http://127.0.0.1:9",
        timeout=1.0, k=10)
    token = run_sut_cross_model(
        JamesValidityAdapter, sc, sha, sut_name="t", mode="token",
        model="token-baseline", ollama_url="http://127.0.0.1:9",
        timeout=1.0, k=10)

    assert len(grounded.per_query) == len(token.per_query) == 80
    assert all(q.rerank_fallback for q in grounded.per_query)
    assert not any(q.rerank_fallback for q in token.per_query)
    assert ([q.retrieved for q in grounded.per_query]
            == [q.retrieved for q in token.per_query])


# ── claude CLI call hardening (2026-09-12) ────────────────────────────


class _FakeProc:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


def test_claude_cli_call_runs_outside_the_repo_with_a_tiny_system_prompt(monkeypatch):
    """The headless call must not auto-discover CLAUDE.md (cwd outside the
    repository), must replace the default system prompt, must not persist
    a session per call, and must decode UTF-8 explicitly. All four were
    missing when the 2026-09-12 cloud leg burned its quota on project
    context. `--bare` is deliberately NOT used: it skips the OAuth login."""
    from eval.external.lrb import llm_rerank

    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        return _FakeProc(0, '{"scores": [3, 1]}')

    monkeypatch.setattr(llm_rerank.subprocess, "run", fake_run)
    out = llm_rerank._call_claude_cli("p", model="claude-haiku-4-5",
                                      timeout=5.0)
    assert out == [3.0, 1.0]
    argv = seen["argv"]
    assert "--bare" not in argv
    assert argv[argv.index("--model") + 1] == "claude-haiku-4-5"
    assert argv[argv.index("--system-prompt") + 1] == llm_rerank.CLAUDE_CLI_SYSTEM_PROMPT
    assert "--no-session-persistence" in argv
    assert seen["kwargs"]["encoding"] == "utf-8"
    assert seen["kwargs"]["errors"] == "replace"
    cwd = Path(seen["kwargs"]["cwd"]).resolve()
    assert ROOT not in cwd.parents and cwd != ROOT
    assert not (cwd / "CLAUDE.md").exists()


def test_claude_cli_call_failures_become_fallbacks(monkeypatch):
    """None stdout (a decode failure in the reader thread), a non-zero
    exit, and an unexpected exception all return [] — which rerank()
    then counts as a fallback — instead of propagating."""
    from eval.external.lrb import llm_rerank

    cases = [
        lambda argv, **k: _FakeProc(0, None),
        lambda argv, **k: _FakeProc(1, "usage limit reached"),
        lambda argv, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    ]
    for fake in cases:
        monkeypatch.setattr(llm_rerank.subprocess, "run", fake)
        assert llm_rerank._call_claude_cli(
            "p", model="claude-haiku-4-5", timeout=5.0) == []

    monkeypatch.setattr(llm_rerank.subprocess, "run", cases[0])
    llm_rerank.STATS.reset()
    out = llm_rerank.rerank("q", [("d1", "t", "x"), ("d2", "t", "y")],
                            model="claude-haiku-4-5")
    assert [d for d, _ in out] == ["d1", "d2"]
    assert llm_rerank.STATS.fallbacks == 1
