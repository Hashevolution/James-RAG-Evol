"""Axis-2 fixture — graph-vs-flat differential under access control.

Designed to expose the one effect that is *specific* to graph-RAG: a
multi-hop reasoning path routes through an intermediate "hub" node that is
**more sensitive than the answer node**. When the hub is gated, graph
traversal cannot reach an answer that flat/vector RAG would still retrieve
(flat needs only the evidence endpoints, not the connecting path).

Sensitivity uses JAMES's ordinal MLS model
(`SENSITIVITY_LEVEL = public<internal<confidential<secret`).

Node ids are fabricated (out of distribution). Each question carries:
- ``anchor``  : public entry node
- ``paths``   : one or more gold multi-hop paths (node-id lists); a question
                is graph-answerable iff *some* path is fully accessible.
- ``support`` : evidence-bearing nodes a flat retriever needs (endpoints);
                a question is flat-answerable iff *all* are accessible.
- ``answer``  : the answer-bearing node (for reference).
"""
from __future__ import annotations

from typing import Dict, List

NODES: Dict[str, Dict] = {
    "a1":  {"name": "Atlas Gate",     "entity_type": "org",       "sensitivity": "public"},
    "a2":  {"name": "Borealis Yard",  "entity_type": "org",       "sensitivity": "public"},
    "e3":  {"name": "Cinder Notice",  "entity_type": "record",    "sensitivity": "public"},
    "e1":  {"name": "Delta Annex",    "entity_type": "unit",      "sensitivity": "internal"},
    "e2":  {"name": "Gamma Relay",    "entity_type": "unit",      "sensitivity": "internal"},
    "e4":  {"name": "Ion Cache",      "entity_type": "store",     "sensitivity": "internal"},
    "alt": {"name": "Juno Bypass",    "entity_type": "unit",      "sensitivity": "internal"},
    "h":   {"name": "Cobalt Hub",     "entity_type": "facility",  "sensitivity": "confidential"},  # HUB
    "s1":  {"name": "Foxglove Core",  "entity_type": "substance", "sensitivity": "secret"},
}

QUESTIONS: List[Dict] = [
    # Hub-gated, answer LESS sensitive than hub → graph loses, flat wins.
    {"id": "Q1", "anchor": "a1", "paths": [["a1", "h", "e1"]], "support": ["a1", "e1"], "answer": "e1"},
    {"id": "Q2", "anchor": "a2", "paths": [["a2", "h", "e2"]], "support": ["a2", "e2"], "answer": "e2"},
    {"id": "Q3", "anchor": "a1", "paths": [["a1", "h", "e3"]], "support": ["a1", "e3"], "answer": "e3"},  # public answer behind conf hub
    # No-hub control (fully internal route).
    {"id": "Q4", "anchor": "a2", "paths": [["a2", "alt", "e4"]], "support": ["a2", "e4"], "answer": "e4"},
    # Genuinely secret answer → both lose for low roles (control: no differential).
    {"id": "Q5", "anchor": "a1", "paths": [["a1", "h", "s1"]], "support": ["a1", "s1"], "answer": "s1"},
    # Redundant: hub path OR internal bypass → redundancy should rescue graph.
    {"id": "Q6", "anchor": "a1", "paths": [["a1", "h", "e1"], ["a1", "alt", "e1"]], "support": ["a1", "e1"], "answer": "e1"},
    # No-hub route to an internal answer.
    {"id": "Q7", "anchor": "a2", "paths": [["a2", "alt", "e2"]], "support": ["a2", "e2"], "answer": "e2"},
]
