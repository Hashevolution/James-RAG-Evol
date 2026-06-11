"""LRB answer_f1 tests — SQuAD norm + EM + F1 + multi-alias."""
from __future__ import annotations


from eval.external.lrb.answer_f1 import (
    _normalize_answer, exact_match, max_em, max_f1, score_answer_f1,
    token_f1)


def test_normalize_lowercase():
    assert _normalize_answer("Hello World") == "hello world"


def test_normalize_articles_dropped():
    assert _normalize_answer("the cat") == "cat"
    assert _normalize_answer("a dog") == "dog"
    assert _normalize_answer("An apple") == "apple"


def test_normalize_punct_dropped():
    assert _normalize_answer("Marcus Chen, Director.") == "marcus chen director"


def test_normalize_whitespace_collapsed():
    assert _normalize_answer("  multiple   spaces  ") == "multiple spaces"


def test_em_exact():
    assert exact_match("Marcus Chen", "Marcus Chen") == 1


def test_em_after_norm():
    assert exact_match("THE marcus", "Marcus") == 1


def test_em_negative():
    assert exact_match("Marcus", "Lena") == 0


def test_em_empty():
    assert exact_match("", "") == 1
    assert exact_match("", "Marcus") == 0


def test_f1_full_overlap():
    assert token_f1("Marcus Chen", "Marcus Chen") == 1.0


def test_f1_partial():
    # "Marcus Chen director" vs "Marcus Chen" → P=2/3, R=2/2, F1=0.8
    assert abs(token_f1("Marcus Chen director", "Marcus Chen") - 0.8) < 1e-6


def test_f1_no_overlap():
    assert token_f1("Lena Ortiz", "Marcus Chen") == 0.0


def test_f1_both_empty():
    assert token_f1("", "") == 1.0


def test_f1_one_empty():
    assert token_f1("", "Marcus") == 0.0
    assert token_f1("Marcus", "") == 0.0


def test_max_em_over_aliases():
    assert max_em("Marcus", ["Lena", "Marcus", "Sofia"]) == 1
    assert max_em("Daniel", ["Lena", "Marcus", "Sofia"]) == 0


def test_max_f1_over_aliases():
    # First alias matches better
    score = max_f1("Marcus Chen", ["Lena Ortiz", "Marcus Chen"])
    assert score == 1.0


def test_score_answer_f1_empty():
    out = score_answer_f1([])
    assert out["EM"] == 0.0
    assert out["F1"] == 0.0
    assert out["n"] == 0


def test_score_answer_f1_perfect():
    rows = [
        {"prediction": "Marcus Chen", "gold": "Marcus Chen"},
        {"prediction": "Lena", "gold": "Lena"},
    ]
    out = score_answer_f1(rows)
    assert out["EM"] == 1.0
    assert out["F1"] == 1.0
    assert out["n"] == 2


def test_score_answer_f1_partial():
    rows = [
        {"prediction": "Marcus", "gold": "Marcus Chen"},   # EM=0, F1=0.667
        {"prediction": "Lena Ortiz", "gold": "Lena Ortiz"},  # both 1.0
    ]
    out = score_answer_f1(rows)
    assert out["EM"] == 0.5
    # F1 mean = (0.6666... + 1.0) / 2 = 0.8333...
    assert abs(out["F1"] - 0.833333) < 1e-4


def test_score_answer_f1_aliases():
    rows = [
        {"prediction": "Marcus C", "gold": "Marcus Chen",
         "answer_aliases": ["Marcus C", "M. Chen"]},
    ]
    out = score_answer_f1(rows)
    # "Marcus C" matches alias #1 exactly
    assert out["EM"] == 1.0
    assert out["F1"] == 1.0


def test_score_answer_f1_empty_prediction_counts():
    rows = [
        {"prediction": "", "gold": "Marcus Chen"},
        {"prediction": "Marcus Chen", "gold": "Marcus Chen"},
    ]
    out = score_answer_f1(rows)
    assert out["n_empty_pred"] == 1
    assert out["EM"] == 0.5
