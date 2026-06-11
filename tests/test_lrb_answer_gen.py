"""LRB answer generation tests — prompt build + dispatch + adapter wiring."""
from __future__ import annotations



from eval.external.lrb.adapters import (
    JamesValidityAdapter, VanillaRagAdapter)
from eval.external.lrb.answer_gen import (
    GenerationResult, _is_claude_model, _is_ollama_model,
    answer_from_adapter, build_prompt, generate_answer)


def test_build_prompt_contains_question_and_docs():
    p = build_prompt(
        "Who directs Public Works?",
        [("d1", "Dept", "Lena Ortiz directs the Department of Public Works."),
         ("d2", "Other", "Marcus heads a different dept.")])
    assert "Who directs Public Works?" in p
    assert "[1] Dept (d1):" in p
    assert "Lena Ortiz" in p
    assert "[2] Other (d2):" in p
    assert "Insufficient Information" in p  # abstention instruction


def test_build_prompt_empty_docs():
    p = build_prompt("Q?", [])
    assert "(no documents retrieved)" in p


def test_build_prompt_truncates_long_doc():
    long_doc = ("X" * 2000)
    p = build_prompt("Q?", [("d1", "T", long_doc)])
    # default max_chars_per_doc = 800
    assert p.count("X") <= 800


def test_dispatch_ollama_models():
    assert _is_ollama_model("gemma4:e4b")
    assert _is_ollama_model("mixtral:8x7b")
    assert _is_ollama_model("llama3.1:8b")
    assert not _is_ollama_model("claude-haiku-4-5")


def test_dispatch_claude_models():
    assert _is_claude_model("claude-haiku-4-5")
    assert not _is_claude_model("gemma4:e4b")


def test_unsupported_model_returns_error():
    result = generate_answer("Q", [("d1", "T", "body")], model="gpt-4")
    assert isinstance(result, GenerationResult)
    assert result.answer == ""
    assert result.error is not None
    assert "unsupported" in result.error


def test_answer_from_adapter_returns_retrieved():
    """Pipeline: build adapter → ingest → answer_from_adapter returns
    both the GenerationResult AND the retrieved doc_ids (even if LLM
    fails)."""
    a = VanillaRagAdapter()
    a.ingest("d1", "Dept of Public Works",
             "Lena Ortiz is the director of Public Works.", 0)
    a.ingest("d2", "Dept of Parks",
             "Marcus Chen directs Parks.", 0)

    # Use unsupported model so we don't actually hit LLM — just verify
    # wiring (retrieval should still happen).
    result, retrieved = answer_from_adapter(
        a, "Who directs Public Works?",
        k=2, query_time=0, valid_time=0, model="not-a-model")

    assert isinstance(result, GenerationResult)
    assert isinstance(retrieved, list)
    assert "d1" in retrieved  # token-overlap finds the relevant doc


def test_answer_from_adapter_validity_window_filter():
    """JAMES adapter must filter superseded docs at query time before
    answer generation — answer_from_adapter respects the SUT's
    retrieve_at semantics."""
    a = JamesValidityAdapter()
    a.ingest("d1", "Dept", "Lena Ortiz is director.", 0)
    a.supersede("d1", "d1.v2", "Dept", "Marcus Chen is director.", 5)

    # At t=10 (post-supersede), retrieval should return only d1.v2
    _, retrieved = answer_from_adapter(
        a, "Who is director?",
        k=5, query_time=10, valid_time=10, model="not-a-model")
    assert "d1" not in retrieved
    assert "d1.v2" in retrieved


def test_generation_result_default_truncated_false():
    r = GenerationResult(answer="hi", model="m", elapsed_s=0.1)
    assert r.truncated is False
    assert r.error is None
