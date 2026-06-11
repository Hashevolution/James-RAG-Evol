"""Track C — TimeQA loader (Chen et al. 2021).

Pre-registered per `docs/research/track-c-c0-bench-selection-
2026-06-11.md` §1.1 as Primary bench for temporal reasoning axis.

Source URL (operator must verify license + download):
  https://github.com/wenhuchen/Time-Sensitive-QA

Expected file layout (when operator drops data into the fixture dir):
  eval/external/_fixtures/timeqa/
    ├── easy/
    │   ├── train.jsonl
    │   ├── dev.jsonl
    │   └── test.jsonl
    └── hard/
        ├── train.jsonl
        ├── dev.jsonl
        └── test.jsonl

Each line is a JSON object. The TimeQA paper format (verified from
public release notes — operator should cross-check against the
official repo at first download):

    {
      "idx":      <str>,
      "question": <str>,
      "paragraphs": [<str>, ...],      # Wikipedia passages
      "targets": [
        {
          "answer":     <str>,
          "start_time": <str | int>,    # ISO date or year
          "end_time":   <str | int>,
        },
        ...
      ],
      "question_time": <str | int>,    # the time the question asks about
    }

Per Track C C0 §1.1 sample sizes:
  * Smoke n=100 from dev (deterministic first-n slice)
  * Full n=1000 from dev

Per Track C C0 §3.1 scoring axes:
  * Token F1 + EM (SQuAD norm, `answer_f1.py`)
  * TimeQA-specific time-aware F1: answer must be in valid time window
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional


# Default fixture root (operator drops data here)
DEFAULT_FIXTURE_DIR = (Path(__file__).resolve()
                       .parent.parent.parent.parent
                       / "eval" / "external" / "_fixtures" / "timeqa")


def fixture_path(difficulty: str = "easy",
                  split: str = "dev",
                  fixture_dir: Optional[Path] = None) -> Path:
    """Return the expected JSONL path for (difficulty, split).

    Args:
      difficulty: "easy" or "hard"
      split:      "train" / "dev" / "test"
      fixture_dir: override the default fixture dir (testing)
    """
    base = fixture_dir or DEFAULT_FIXTURE_DIR
    return base / difficulty / f"{split}.jsonl"


def load_rows(path: Path) -> List[Dict[str, Any]]:
    """Load TimeQA JSONL rows. Returns empty list if path missing
    (operator action: download data)."""
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def to_track_c_format(row: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a TimeQA row to the Track C unified shape.

    Returns:
      {
        "query_id":   <str>,
        "question":   <str>,
        "context":    <str>,        # concatenated paragraphs
        "gold":       <str>,         # primary answer (first target)
        "answer_aliases": [<str>],   # additional targets
        "time_window": (start, end), # for time-aware F1
        "question_time": <str>,
      }
    """
    targets = row.get("targets") or []
    primary = targets[0] if targets else {}
    aliases = [t.get("answer", "") for t in targets[1:]
                if t.get("answer", "")]
    context = "\n\n".join(row.get("paragraphs") or [])
    return {
        "query_id":      str(row.get("idx", "")),
        "question":      row.get("question", ""),
        "context":       context,
        "gold":          primary.get("answer", ""),
        "answer_aliases": aliases,
        "time_window": (
            primary.get("start_time", ""),
            primary.get("end_time", ""),
        ),
        "question_time": row.get("question_time", ""),
    }


def load_smoke(n: int = 100,
                difficulty: str = "easy",
                split: str = "dev",
                fixture_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """First-n deterministic slice in the normalised Track C shape."""
    rows = load_rows(fixture_path(difficulty, split, fixture_dir))
    return [to_track_c_format(r) for r in rows[:n]]


def is_available(difficulty: str = "easy",
                  split: str = "dev",
                  fixture_dir: Optional[Path] = None) -> bool:
    """Operator-action check — fast probe for whether TimeQA data has
    been dropped into the fixture dir.

    Used by Track C runner to skip with a clear message rather than
    crash if the bench isn't present."""
    return fixture_path(difficulty, split, fixture_dir).exists()


__all__ = [
    "DEFAULT_FIXTURE_DIR",
    "fixture_path", "load_rows", "to_track_c_format",
    "load_smoke", "is_available",
]
