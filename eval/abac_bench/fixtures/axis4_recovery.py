"""Axis-4 fixture — recovery / graceful degradation under partial permissions.

Every question's *primary* path runs through the confidential hub. Some
questions additionally have an *alternative* path; recovery succeeds when an
alternative path is fully permitted for a role whose primary path is gated.

Recovery is only defined for the regime where the answer is *legitimately
reachable* (all evidence endpoints accessible) but the default path is gated
— i.e. a routing failure, not a legitimate denial.

Sensitivities use JAMES's ordinal MLS model.
"""
from __future__ import annotations

from typing import Dict, List

NODES: Dict[str, Dict] = {
    "a1": {"name": "Atlas Gate",    "entity_type": "org",      "sensitivity": "public"},
    "a2": {"name": "Borealis Yard", "entity_type": "org",      "sensitivity": "public"},
    "h":  {"name": "Cobalt Hub",    "entity_type": "facility", "sensitivity": "confidential"},  # default hub
    "h2": {"name": "Onyx Relay",    "entity_type": "facility", "sensitivity": "confidential"},  # gated alt
    "b1": {"name": "Juno Bypass",   "entity_type": "unit",     "sensitivity": "internal"},      # permitted alt
    "b2": {"name": "Kilo Bypass",   "entity_type": "unit",     "sensitivity": "internal"},
    "b3": {"name": "Lima Bypass",   "entity_type": "unit",     "sensitivity": "internal"},
    "e1": {"name": "Ans-One",       "entity_type": "record",   "sensitivity": "internal"},
    "e2": {"name": "Ans-Two",       "entity_type": "record",   "sensitivity": "internal"},
    "e3": {"name": "Ans-Three",     "entity_type": "record",   "sensitivity": "internal"},
    "e4": {"name": "Ans-Four",      "entity_type": "record",   "sensitivity": "internal"},
    "e5": {"name": "Ans-Five",      "entity_type": "record",   "sensitivity": "internal"},
    "e6": {"name": "Ans-Six",       "entity_type": "record",   "sensitivity": "internal"},
}

# paths[0] = primary (always via hub h); paths[1:] = alternatives.
QUESTIONS: List[Dict] = [
    {"id": "R1", "support": ["a1", "e1"], "answer": "e1",
     "paths": [["a1", "h", "e1"], ["a1", "b1", "e1"]]},          # recoverable (internal bypass)
    {"id": "R2", "support": ["a2", "e2"], "answer": "e2",
     "paths": [["a2", "h", "e2"], ["a2", "b2", "e2"]]},          # recoverable
    {"id": "R3", "support": ["a1", "e3"], "answer": "e3",
     "paths": [["a1", "h", "e3"]]},                              # no alt → unrecoverable
    {"id": "R4", "support": ["a2", "e4"], "answer": "e4",
     "paths": [["a2", "h", "e4"], ["a2", "b3", "e4"]]},          # recoverable
    {"id": "R5", "support": ["a1", "e5"], "answer": "e5",
     "paths": [["a1", "h", "e5"]]},                              # no alt → unrecoverable
    {"id": "R6", "support": ["a1", "e6"], "answer": "e6",
     "paths": [["a1", "h", "e6"], ["a1", "h2", "e6"]]},          # alt exists but also gated → unrecoverable
]
