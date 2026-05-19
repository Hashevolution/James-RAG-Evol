"""Plugin contract — 4 Protocol types for pack-level extensions.

Track C PR-C2 of the v0.3 Plugin API skeleton. Ships the **contract
surface only** — no loader, no manifest parser, no registry yet. Those
land in PR-C3.

The four types match `docs/design/v0.3-plugin-api.md` §"The four
plugin types":

  - ``OntologyPack``  — entity types, relation types, hierarchies
  - ``PromptPack``    — system prompts + few-shot examples per mode
  - ``UIPanel``       — server-rendered admin/user widgets
  - ``Scorer``        — custom retrieval/answer scoring overrides

Each is ``@runtime_checkable`` so the loader (PR-C3) can validate a
pack at import time via ``isinstance(obj, ProtocolType)``. The
``pack_id`` attribute is the registry key — required on every type.

A pack supplies **zero or more** of these. A pure ontology pack has
no ``PromptPack`` / ``UIPanel`` / ``Scorer``. The loader registers
each slot independently per manifest entry.

These Protocols layer ABOVE the cognitive middleware
(``docs/ARCHITECTURE.md`` §5.7); plugins supply *content*, not new
reasoning primitives. The existing scorer in ``core/retrieval/``, the
existing prompts in ``core/reasoning/modes/``, and the existing
ontology in ``core/relations_schema.py`` stay the defaults — a pack's
slot entry overrides only the slot it registers against.
"""
from __future__ import annotations

from typing import Any, Dict, List, Protocol, Tuple, runtime_checkable


# ─── Panel context ─────────────────────────────────────────────────
# The PanelContext object passed into UIPanel.render(). Defined here
# rather than as a separate import so the contract is self-contained.
# A pack does not import from server_llmwiki or fastapi — the loader
# constructs the context and hands it in.


class PanelContext:
    """Read-only snapshot of the current request that UI panels need
    in order to render correctly without leaking the actual request
    object into pack code.

    Three fields the cognitive layer already tracks:

      - ``user_role``  — the ABAC role from
        ``core/policy_engine.PolicyEngine`` ("external", "employee",
        "admin", …). UIPanel.render() must respect this.
      - ``session_id`` — the chat session this render is happening
        inside. UI panels keyed on session state (e.g. recent
        history) read this.
      - ``locale``     — ISO 639-1 + optional region ("ko" / "en" /
        "ko-KR"). The existing i18n.js mirrors this; pack-side text
        chooses the rendering string from the same key.

    The context is intentionally narrow. A pack that needs more
    server state (e.g. graph node count) goes through the existing
    admin endpoints, not through this object.
    """

    __slots__ = ("user_role", "session_id", "locale")

    def __init__(
        self,
        *,
        user_role: str,
        session_id: str = "",
        locale: str = "en",
    ) -> None:
        self.user_role = user_role
        self.session_id = session_id
        self.locale = locale


# ─── The four plugin types ─────────────────────────────────────────


@runtime_checkable
class OntologyPack(Protocol):
    """Entity types, relation types, hierarchies. Read at startup and
    cached for the process lifetime. Lookup cost is O(1) on dict.

    Required attributes:

      - ``pack_id``         — registry key, matches the pack name in
        ``packs/<pack_id>/``
      - ``entity_types``    — tuple of entity-type strings the pack
        introduces or overrides (e.g. ``("contract", "clause")``).
        Empty tuple means the pack doesn't extend entity types.
      - ``relation_types``  — tuple of relation-type strings the pack
        adds to the ontology. Same empty-tuple semantics.
      - ``hierarchies``     — mapping ``parent -> children`` for any
        hierarchical relations the pack defines. Empty dict OK.
    """

    pack_id: str
    entity_types: Tuple[str, ...]
    relation_types: Tuple[str, ...]
    hierarchies: Dict[str, Tuple[str, ...]]


@runtime_checkable
class PromptPack(Protocol):
    """System prompts + few-shot examples per task. Returned strings
    are concatenated into the existing prompt builder in
    ``core/reasoning/modes/`` — packs do not rewrite the reasoning
    loop, they only supply the text.
    """

    pack_id: str

    def system_prompt(self, mode: str) -> str:
        """Return the system-prompt string for one of the five built-in
        modes (``"chat"``, ``"meta"``, ``"wiki_edit"``,
        ``"self_evolve"``, ``"coding"``).

        Unknown mode MUST return the empty string ``""`` — graceful
        fallthrough lets the existing default prompt path stay in
        control. A pack that doesn't override a mode's prompt simply
        returns ``""`` for that mode.
        """
        ...

    def few_shot(self, task: str) -> List[Dict[str, Any]]:
        """Optional few-shot examples for a named task. Empty list
        ``[]`` means "no examples"; the existing prompt path stays
        unchanged. Each dict typically looks like
        ``{"role": "user", "content": "..."}`` /
        ``{"role": "assistant", "content": "..."}``.
        """
        ...


@runtime_checkable
class UIPanel(Protocol):
    """Server-rendered admin/user widget. The HTML returned by
    ``render()`` is sandboxed at the response-filter layer
    (``core/security_layer``) before reaching the client — packs
    cannot bypass that.

    Path convention: ``/panels/{pack_id}/{panel_id}``. The loader
    (PR-C3) wires the route at startup.
    """

    pack_id: str
    panel_id: str

    def render(self, ctx: PanelContext) -> str:
        """Return server-rendered HTML for the panel. MUST respect
        the ``ctx.user_role`` ABAC decision — a pack that ignores the
        role and leaks admin-only content to an external user is a
        contract violation (the conformance suite in PR-C9 catches
        the obvious cases).

        Empty string ``""`` is a legal return value — typically used
        when the panel decides it has nothing to show for this user
        / locale combination.
        """
        ...


@runtime_checkable
class Scorer(Protocol):
    """Custom retrieval / answer scoring override. Plugged into the
    existing reranker / hybrid-search slot in
    ``core/retrieval/``. The default scorer remains active unless a
    pack explicitly registers a ``Scorer`` against the same slot.

    Multiple packs declaring scorers against the same slot is a
    PluginLoadError — the conflict needs operator resolution, not
    a silent precedence rule.
    """

    pack_id: str

    def score(self, query: str, candidate: Dict[str, Any]) -> float:
        """Return a ``[0.0, 1.0]`` score for the candidate's relevance
        to the query. Higher = more relevant. Scores outside that
        range MUST be clamped by the implementer; the existing
        reranker treats anything outside the range as a bug.
        """
        ...


# ─── Sentinel values ───────────────────────────────────────────────
# Closed enum used by the manifest validator (PR-C3) and named here
# rather than as a string literal duplicated across the codebase.

KNOWN_MODES: Tuple[str, ...] = (
    "chat", "meta", "wiki_edit", "self_evolve", "coding",
)


__all__ = [
    "OntologyPack",
    "PromptPack",
    "UIPanel",
    "Scorer",
    "PanelContext",
    "KNOWN_MODES",
]
