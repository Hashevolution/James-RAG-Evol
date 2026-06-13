"""``AnswerBlock`` result dataclass for ``generate_answer``.

Extracted from the legacy single-file ``core/reasoning/pipeline_synth.py``
during the v0.6 oversize-module split (CLAUDE.md rule #5). Behaviour
is byte-identical to the pre-split file; only the location moved.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class AnswerBlock:
    """Outputs of generate_answer() that the orchestrator threads into
    the result dict (web_used / web_sources / pending_save_proposal_id
    derivations happen in pipeline.py).
    """
    answer: str = ""
    web_results: List[Dict[str, Any]] = field(default_factory=list)
    pending_save_proposal_id: str = ""


__all__ = ["AnswerBlock"]
