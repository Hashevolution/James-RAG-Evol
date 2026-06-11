"""Track C — TempReason loader (Tan et al. 2023).

Pre-registered per `docs/research/track-c-c0-bench-selection-
2026-06-11.md` §1.2 as Secondary bench for multi-hop + temporal axis.

Source URL (operator must verify license + download):
  https://github.com/DAMO-NLP-SG/TempReason

Expected file layout (when operator drops data into the fixture dir):
  eval/external/_fixtures/tempreason/
    ├── l1_train.json
    ├── l1_val.json
    ├── l1_test.json
    ├── l2_train.json
    ├── l2_val.json
    ├── l2_test.json
    ├── l3_train.json
    ├── l3_val.json
    └── l3_test.json

Each file is a JSON list (verify format at first download — operator
should cross-check). Per Track C C0 §1.2, the format is roughly:

    [
      {
        "id":       <str>,
        "question": <str>,
        "context":  <str>,           # paragraph(s)
        "answer":   <str>,
        "level":    "L1" | "L2" | "L3",  # difficulty
      },
      ...
    ]

Per Track C C0 sample sizes:
  * Smoke n=100 from val (L1+L2+L3 균등 분포 — 34/33/33)
  * Full n=600 (L1/L2/L3 × 200 each)

Per Track C C0 scoring axes:
  * Token F1 + EM (SQuAD norm, shared `answer_f1.py`)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


# Default fixture root (operator drops data here)
DEFAULT_FIXTURE_DIR = (Path(__file__).resolve()
                       .parent.parent.parent.parent
                       / "eval" / "external" / "_fixtures"
                       / "tempreason")

LEVELS = ("l1", "l2", "l3")
SPLITS = ("train", "val", "test")


def fixture_path(level: str = "l1",
                  split: str = "val",
                  fixture_dir: Optional[Path] = None) -> Path:
    """Return the expected JSON path for (level, split)."""
    base = fixture_dir or DEFAULT_FIXTURE_DIR
    return base / f"{level}_{split}.json"


def load_rows(path: Path) -> List[Dict[str, Any]]:
    """Load TempReason JSON rows. Returns empty list if missing."""
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    if isinstance(data, list):
        return data
    # Some releases wrap in {"data": [...]}; handle gracefully
    if isinstance(data, dict) and "data" in data:
        return data["data"]
    return []


def to_track_c_format(row: Dict[str, Any],
                       *, default_level: str = "") -> Dict[str, Any]:
    """Normalize a TempReason row to Track C unified shape.

    Returns:
      {
        "query_id":      <str>,
        "question":      <str>,
        "context":       <str>,
        "gold":          <str>,
        "answer_aliases": [],
        "level":         "L1" | "L2" | "L3",
      }
    """
    level = row.get("level", default_level) or default_level
    return {
        "query_id":       str(row.get("id", "")),
        "question":       row.get("question", ""),
        "context":        row.get("context", "") or row.get("paragraph", ""),
        "gold":           row.get("answer", ""),
        "answer_aliases": row.get("answer_aliases", []) or [],
        "level":          level.upper(),
    }


def load_smoke_balanced(n: int = 100,
                          split: str = "val",
                          fixture_dir: Optional[Path] = None
                          ) -> List[Dict[str, Any]]:
    """Load n queries balanced across L1/L2/L3.

    n=100 → 34 L1 + 33 L2 + 33 L3.
    """
    per_level = [n // 3 + (1 if i < n % 3 else 0) for i in range(3)]
    out: List[Dict[str, Any]] = []
    for level, k in zip(LEVELS, per_level):
        rows = load_rows(fixture_path(level, split, fixture_dir))
        for r in rows[:k]:
            out.append(to_track_c_format(r, default_level=level))
    return out


def is_available(level: str = "l1",
                  split: str = "val",
                  fixture_dir: Optional[Path] = None) -> bool:
    return fixture_path(level, split, fixture_dir).exists()


def all_levels_available(split: str = "val",
                          fixture_dir: Optional[Path] = None) -> bool:
    return all(is_available(L, split, fixture_dir) for L in LEVELS)


__all__ = [
    "DEFAULT_FIXTURE_DIR", "LEVELS", "SPLITS",
    "fixture_path", "load_rows", "to_track_c_format",
    "load_smoke_balanced", "is_available", "all_levels_available",
]
