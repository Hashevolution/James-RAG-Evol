"""TempReason loader tests — same shape as TimeQA: path / parse /
normalize / balanced smoke."""
from __future__ import annotations

import json

import pytest

from eval.external.lrb.tempreason_loader import (
    LEVELS, all_levels_available, fixture_path, is_available,
    load_rows, load_smoke_balanced, to_track_c_format)


@pytest.fixture
def fake_fixture_dir(tmp_path):
    """Build a fake TempReason fixture dir with 3 rows per level."""
    for level in LEVELS:
        path = tmp_path / f"{level}_val.json"
        rows = [
            {
                "id":       f"{level}-{i:03d}",
                "question": f"Q{i} for {level}",
                "context":  f"Context for {level} {i}",
                "answer":   f"Answer-{level}-{i}",
                "level":    level.upper(),
            }
            for i in range(1, 5)
        ]
        path.write_text(json.dumps(rows), encoding="utf-8")
    return tmp_path


def test_fixture_path_default():
    p = fixture_path()
    assert p.name == "l1_val.json"


def test_fixture_path_level_split():
    assert fixture_path("l3", "test").name == "l3_test.json"


def test_is_available_missing(tmp_path):
    assert is_available("l1", "val", fixture_dir=tmp_path) is False


def test_is_available_present(fake_fixture_dir):
    assert is_available("l1", "val",
                         fixture_dir=fake_fixture_dir) is True


def test_all_levels_available_true(fake_fixture_dir):
    assert all_levels_available("val",
                                  fixture_dir=fake_fixture_dir) is True


def test_all_levels_available_false_partial(tmp_path):
    # Only l1 present
    (tmp_path / "l1_val.json").write_text("[]", encoding="utf-8")
    assert all_levels_available("val", fixture_dir=tmp_path) is False


def test_load_rows_missing_returns_empty(tmp_path):
    assert load_rows(fixture_path("l1", "val",
                                    fixture_dir=tmp_path)) == []


def test_load_rows_list_form(fake_fixture_dir):
    rows = load_rows(fixture_path("l1", "val",
                                    fixture_dir=fake_fixture_dir))
    assert len(rows) == 4


def test_load_rows_dict_data_form(tmp_path):
    """Some TempReason releases wrap in {"data": [...]}."""
    path = tmp_path / "l1_val.json"
    payload = {"data": [{"id": "a", "question": "q",
                          "context": "c", "answer": "x"}]}
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert len(load_rows(path)) == 1


def test_to_track_c_format():
    row = {
        "id": "001",
        "question": "Q",
        "context": "C",
        "answer": "A",
        "level": "L2",
    }
    norm = to_track_c_format(row)
    assert norm["query_id"] == "001"
    assert norm["question"] == "Q"
    assert norm["context"] == "C"
    assert norm["gold"] == "A"
    assert norm["level"] == "L2"


def test_to_track_c_default_level():
    row = {"id": "x", "question": "?", "context": "",
            "answer": ""}  # no level
    norm = to_track_c_format(row, default_level="l3")
    assert norm["level"] == "L3"


def test_to_track_c_paragraph_field():
    """Some releases use `paragraph` instead of `context`."""
    row = {"id": "y", "question": "?", "paragraph": "p body",
            "answer": "a"}
    norm = to_track_c_format(row)
    assert norm["context"] == "p body"


def test_load_smoke_balanced_distribution(fake_fixture_dir):
    smoke = load_smoke_balanced(n=9, split="val",
                                  fixture_dir=fake_fixture_dir)
    # 9 = 3 + 3 + 3 across L1/L2/L3
    assert len(smoke) == 9
    levels = [r["level"] for r in smoke]
    assert levels.count("L1") == 3
    assert levels.count("L2") == 3
    assert levels.count("L3") == 3


def test_load_smoke_balanced_uneven(fake_fixture_dir):
    smoke = load_smoke_balanced(n=10, split="val",
                                  fixture_dir=fake_fixture_dir)
    # 10 = 4 + 3 + 3 (first level gets extra)
    levels = [r["level"] for r in smoke]
    assert levels.count("L1") == 4
    assert levels.count("L2") == 3
    assert levels.count("L3") == 3


def test_load_smoke_balanced_missing_fixture(tmp_path):
    smoke = load_smoke_balanced(n=9, fixture_dir=tmp_path)
    assert smoke == []
