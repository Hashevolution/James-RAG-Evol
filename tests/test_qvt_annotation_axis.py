"""Annotation axis — contract tests.

Pins the parts of ``eval/qvt/annotation_axis.py`` that decide what a
score *means*, including two defects the axis had on its first run:

  * answers keyed by fixture id collapsed repeated samples of one query
    onto whichever came last (three Q17 episodes scored as one refusal)
  * graded mode's blind spot — graded == 1.0 means "contains the
    answer", not "contains nothing else", so a correct warning about an
    embellishment scored as a false alarm. Strict mode, the default,
    does not consult graded at all.

Run:
  python -m pytest tests/test_qvt_annotation_axis.py -q
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "research"))

from eval.qvt import annotation_axis as A  # noqa: E402
from eval.qvt.oracle import detect_abstention  # noqa: E402

FIXTURE = json.loads((REPO_ROOT / "eval" / "regression"
                      / "step7_queries.json").read_text(encoding="utf-8"))
NOTE_EN = ("\n\n(Verification: the following claims are not directly "
           "supported by the source data: x)")


# ─── the note pattern matches what verify actually emits ────────────


@pytest.mark.parametrize("query", ["Anthropic의 CEO는 누구야?",
                                   "Who is Anthropic's CEO?"])
def test_note_re_strips_what_verifier_format_produces(query):
    """Anti-drift: the pattern lives on the measurement side because
    verify builds the note with an inline f-string. If `_format` ever
    changes wording, this fails instead of the axis silently scoring
    notes as answer text."""
    from core.reasoning.verify import Verifier
    base = "Alex Karp"
    out = Verifier()._format(query, base, [], False,
                             ["Alex Karp is the CEO"], "annotate")
    assert out != base, "format did not annotate"
    assert A.strip_note(out) == base


def test_strip_note_leaves_unannotated_answers_alone():
    assert A.strip_note("plain answer") == "plain answer"
    assert A.strip_note(None) == ""


# ─── correctness: fixture labels only ───────────────────────────────


@pytest.mark.parametrize("truth,abstained,graded,strict,want", [
    ("absent", False, 0.0, True, A.WRONG),      # answered the unanswerable
    ("absent", True, 0.0, True, A.RIGHT),       # correct refusal
    ("present", True, 1.0, True, A.WRONG),      # refused the answerable
    ("present", False, 1.0, True, A.UNSCORED),  # strict never uses graded
    ("present", False, 1.0, False, A.RIGHT),    # graded mode does
    ("present", False, 0.67, False, A.UNSCORED),
    ("present", False, None, False, A.UNSCORED),
    ("weird", False, 1.0, False, A.UNSCORED),
])
def test_classify_correctness(truth, abstained, graded, strict, want):
    assert A.classify_correctness(truth, abstained, graded,
                                  strict=strict) == want


def test_strict_is_the_default():
    assert A.classify_correctness("present", False, 1.0) == A.UNSCORED


@pytest.mark.parametrize("correctness,annotated,want", [
    (A.WRONG, True, A.TRUE_ALARM),
    (A.WRONG, False, A.MISS),
    (A.RIGHT, True, A.FALSE_ALARM),
    (A.RIGHT, False, A.CORRECT_SILENCE),
    (A.UNSCORED, True, A.UNSCORED),
])
def test_cell_for(correctness, annotated, want):
    assert A.cell_for(correctness, annotated) == want


# ─── scoring ────────────────────────────────────────────────────────


def test_repeated_ids_are_scored_per_episode():
    """The first version keyed answers by fixture id."""
    eps = [
        {"id": 17, "final_answer": "Alex Karp" + NOTE_EN, "annotated": True},
        {"id": 17, "final_answer": "Alex Karp", "annotated": False},
        {"id": 17, "final_answer": "자료에 없습니다.", "annotated": True},
    ]
    ax = A.score_annotations(eps, FIXTURE)
    assert [r.cell for r in ax.per_query] == [
        A.TRUE_ALARM, A.MISS, A.FALSE_ALARM]


def test_note_cannot_change_the_verdict_it_is_scored_against():
    """A note whose LLM-written claim text trips an abstention phrase
    would, unstripped, turn a hallucination into a 'refusal'."""
    poisoned = ("Alex Karp\n\n(검증: 다음 주장이 자료에 직접 지지되지 "
                "않음: 해당 정보는 자료에 없습니다)")
    assert detect_abstention(poisoned), "fixture no longer exercises the risk"
    ax = A.score_annotations(
        [{"id": 17, "final_answer": poisoned, "annotated": True}], FIXTURE)
    assert ax.per_query[0].abstained is False
    assert ax.per_query[0].cell == A.TRUE_ALARM


def test_precision_and_recall():
    eps = [
        {"id": 17, "final_answer": "Alex Karp", "annotated": True},   # TA
        {"id": 17, "final_answer": "Alex Karp", "annotated": False},  # miss
        {"id": 17, "final_answer": "자료에 없습니다.", "annotated": True},  # FA
    ]
    ax = A.score_annotations(eps, FIXTURE)
    assert (ax.precision, ax.recall) == (0.5, 0.5)
    assert ax.f1 == 0.5
    assert ax.n_scored == 3 and ax.n_annotated == 2


def test_undefined_rates_are_none_not_zero():
    """No annotations → precision undefined, not 0.0 (which would read
    as 'every annotation was wrong')."""
    ax = A.score_annotations(
        [{"id": 17, "final_answer": "Alex Karp", "annotated": False}], FIXTURE)
    assert ax.precision is None
    assert ax.recall == 0.0
    assert ax.f1 is None


def test_unknown_ids_are_skipped():
    ax = A.score_annotations(
        [{"id": 99999, "final_answer": "x", "annotated": True}], FIXTURE)
    assert ax.per_query == [] and ax.n_annotated == 0


# ─── the audit-log loader ───────────────────────────────────────────


def _db(tmp_path, rows):
    db = tmp_path / "audit.db"
    con = sqlite3.connect(db)
    con.execute("create table audit_log (id integer primary key, "
                "timestamp text, endpoint text, query text, answer text, "
                "blocked integer default 0)")
    for i, r in enumerate(rows):
        con.execute("insert into audit_log (timestamp, endpoint, query, "
                    "answer, blocked) values (?,?,?,?,?)",
                    (f"2026-09-28T10:00:{i:02d}",) + r)
    con.commit()
    con.close()
    return db


def test_loader_joins_by_question_text_and_skips_blocked(tmp_path):
    from score_annotations import load_episodes
    q17 = next(q["text"] for q in FIXTURE["queries"] if q["id"] == 17)
    q11 = next(q["text"] for q in FIXTURE["queries"] if q["id"] == 11)
    db = _db(tmp_path, [
        ("reason:verify", "", '{"output_summary": "rec=annotate flags=0 unsupp=1"}', 0),
        ("/query/", q17, "Alex Karp" + NOTE_EN, 0),
        ("/query/", q11, "blocked", 1),
        ("/query/", "not a fixture question", "x", 0),
    ])
    got = load_episodes("2026-09-28T10:00:00", "2026-09-28T10:00:59",
                        FIXTURE, db=db)
    assert [e["id"] for e in got["episodes"]] == [17]
    assert got["episodes"][0]["annotated"] is True
    assert got["unmatched"] == ["not a fixture question"]


def test_loader_recommendation_is_per_episode(tmp_path):
    """A verify row belongs to the episode it precedes, not the next."""
    from score_annotations import load_episodes
    q17 = next(q["text"] for q in FIXTURE["queries"] if q["id"] == 17)
    db = _db(tmp_path, [
        ("reason:verify", "", "rec=annotate flags=0 unsupp=1", 0),
        ("/query/", q17, "a", 0),
        ("/query/", q17, "b", 0),
    ])
    got = load_episodes("2026-09-28T10:00:00", "2026-09-28T10:00:59",
                        FIXTURE, db=db)
    assert [e["annotated"] for e in got["episodes"]] == [True, False]
