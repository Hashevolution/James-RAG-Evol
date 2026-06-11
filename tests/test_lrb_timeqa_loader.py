"""TimeQA loader tests — fixture path resolution + JSONL parse +
normalization to Track C shape + is_available probe."""
from __future__ import annotations

import json

import pytest

from eval.external.lrb.timeqa_loader import (
    fixture_path, is_available, load_rows, load_smoke,
    to_track_c_format)


@pytest.fixture
def fake_fixture_dir(tmp_path):
    """Build a fake TimeQA fixture dir with 3 rows."""
    easy_dev = tmp_path / "easy" / "dev.jsonl"
    easy_dev.parent.mkdir(parents=True)
    rows = [
        {
            "idx": "q-001",
            "question": "Who was mayor of Paris in 2010?",
            "paragraphs": ["Bertrand Delanoë was mayor of Paris from "
                            "2001 to 2014.", "irrelevant passage"],
            "targets": [
                {"answer": "Bertrand Delanoë",
                 "start_time": 2001, "end_time": 2014},
                {"answer": "Delanoë",
                 "start_time": 2001, "end_time": 2014},
            ],
            "question_time": 2010,
        },
        {
            "idx": "q-002",
            "question": "Who held position X in 2015?",
            "paragraphs": ["Alice held X from 2010 to 2016."],
            "targets": [
                {"answer": "Alice",
                 "start_time": 2010, "end_time": 2016},
            ],
            "question_time": 2015,
        },
        {
            "idx": "q-003",
            "question": "Empty target case?",
            "paragraphs": ["nothing relevant"],
            "targets": [],
            "question_time": 2020,
        },
    ]
    with easy_dev.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return tmp_path


def test_fixture_path_default_easy_dev():
    p = fixture_path()
    assert p.name == "dev.jsonl"
    assert p.parent.name == "easy"


def test_fixture_path_hard_test():
    p = fixture_path("hard", "test")
    assert p.name == "test.jsonl"
    assert p.parent.name == "hard"


def test_is_available_returns_false_when_missing(tmp_path):
    assert is_available("easy", "dev", fixture_dir=tmp_path) is False


def test_is_available_returns_true_when_present(fake_fixture_dir):
    assert is_available("easy", "dev",
                         fixture_dir=fake_fixture_dir) is True


def test_load_rows_missing_returns_empty(tmp_path):
    rows = load_rows(fixture_path("easy", "dev", fixture_dir=tmp_path))
    assert rows == []


def test_load_rows_parses_jsonl(fake_fixture_dir):
    rows = load_rows(fixture_path("easy", "dev",
                                    fixture_dir=fake_fixture_dir))
    assert len(rows) == 3
    assert rows[0]["idx"] == "q-001"


def test_to_track_c_format():
    row = {
        "idx": "q-001",
        "question": "Who was mayor?",
        "paragraphs": ["Para A", "Para B"],
        "targets": [
            {"answer": "Bertrand", "start_time": 2001, "end_time": 2014},
            {"answer": "Delanoë",  "start_time": 2001, "end_time": 2014},
        ],
        "question_time": 2010,
    }
    norm = to_track_c_format(row)
    assert norm["query_id"] == "q-001"
    assert norm["question"] == "Who was mayor?"
    assert norm["context"] == "Para A\n\nPara B"
    assert norm["gold"] == "Bertrand"
    assert norm["answer_aliases"] == ["Delanoë"]
    assert norm["time_window"] == (2001, 2014)
    assert norm["question_time"] == 2010


def test_to_track_c_empty_targets():
    row = {"idx": "x", "question": "?", "paragraphs": [],
            "targets": [], "question_time": ""}
    norm = to_track_c_format(row)
    assert norm["gold"] == ""
    assert norm["answer_aliases"] == []


def test_load_smoke_n_slice(fake_fixture_dir):
    rows = load_smoke(n=2, difficulty="easy", split="dev",
                       fixture_dir=fake_fixture_dir)
    assert len(rows) == 2
    assert rows[0]["query_id"] == "q-001"


def test_load_smoke_n_larger_than_data(fake_fixture_dir):
    rows = load_smoke(n=100, fixture_dir=fake_fixture_dir)
    assert len(rows) == 3
