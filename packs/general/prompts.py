"""``GeneralPrompts`` — no-op overlay for the dogfood pack.

Satisfies the :class:`core.plugins.base.PromptPack` Protocol with
empty-string / empty-list return values across every mode and every
task. The existing prompt builder in ``core/reasoning/modes/`` stays
authoritative; this class declares that the ``general`` pack supplies
no override.

See :mod:`packs.general.ontology` for the matching reasoning behind
the no-op pattern.
"""
from __future__ import annotations

from typing import Any, Dict, List


class GeneralPrompts:
    """Pack-level prompt declaration. Returns empty in v0.3.

    The Protocol contract is "empty string for unknown mode" / "empty
    list for unknown task." Returning empty for *every* mode and task
    is a legal pack — it simply contributes no override.
    """

    pack_id: str = "general"

    def system_prompt(self, mode: str) -> str:
        # Empty string is the graceful fall-through path — the existing
        # default prompt builder in core/reasoning/modes/ stays in
        # control. See docs/PLUGIN_AUTHORING.md §4.2.
        return ""

    def few_shot(self, task: str) -> List[Dict[str, Any]]:
        return []


__all__ = ["GeneralPrompts"]
