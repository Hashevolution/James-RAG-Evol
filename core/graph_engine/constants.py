"""DFS + scoring constants for the graph engine.

Extracted from the legacy single-file ``core/graph_engine.py`` during
the v0.6 oversize-module split (CLAUDE.md rule #5). Values are
byte-identical to the pre-split file; only the location moved.
"""
from __future__ import annotations


CONFIDENCE_THRESHOLD = 0.6
MAX_DEPTH            = 4
DFS_SCORE_THRESHOLD  = 0.05
DEPTH_DECAY          = 0.7


__all__ = [
    "CONFIDENCE_THRESHOLD",
    "MAX_DEPTH",
    "DFS_SCORE_THRESHOLD",
    "DEPTH_DECAY",
]
