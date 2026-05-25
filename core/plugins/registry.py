"""Plugin slot registry — in-memory store for loaded Protocol implementations
(Track C PR-C3).

The registry is **populated at startup** by ``core/plugins/loader.py``
and **read at request time** by the consuming subsystem
(``core/reasoning/modes/`` reads prompts, ``core/retrieval/`` reads
scorers, ``server_llmwiki.py`` mounts UI panels at the path
``/panels/{pack_id}/{panel_id}``).

Per ``docs/design/v0.3-plugin-api.md`` §"The four plugin types"
+ §"Loader semantics".

Slot semantics
--------------

| Slot | Allowed multiplicity | Conflict policy |
|---|---|---|
| ``ontology`` | many | merge — each pack adds entity/relation types; loader resolves naming collisions explicitly. |
| ``prompts``  | many | first-non-empty-wins per mode (last-registered first); falls through to the default prompt path when every pack returns ``""``. |
| ``ui``       | many | each panel is mounted at ``/panels/{pack_id}/{panel_id}``; the same ``(pack_id, panel_id)`` registered twice is a :class:`PluginLoadError`. |
| ``scorers``  | one per slot | declaring two scorers for the same retrieval slot is a :class:`PluginLoadError` — needs operator resolution, not silent precedence. |

The "scorer slot" concept above refers to a named retrieval slot
inside ``core/retrieval/`` (e.g. ``"rerank"``, ``"hybrid"``). Each
``Scorer`` Protocol implementation declares which slot it targets
via a ``slot_id`` attribute the loader inspects; the design memo
keeps that field implicit in v0.3 (the slot is the scorer's
``pack_id`` for now) and a follow-up PR will widen it once a second
pack actually registers a scorer.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from core.plugins.base import (
    OntologyPack,
    PromptPack,
    Scorer,
    UIPanel,
)
from core.plugins.errors import PluginLoadError


class PluginRegistry:
    """In-memory registry. One instance per process.

    The registry is **not thread-safe by design** — JAMES populates it
    once at startup before any worker request fires. A reload (e.g.
    operator changes ``JAMES_PACKS`` and re-execs) builds a fresh
    instance; there is no online mutation.

    Stored values are the **already-instantiated** Protocol objects
    the loader produced from ``"module:Class"`` imports. The registry
    keeps no reference to the source module; once registered, the
    object's behavior is the contract.
    """

    __slots__ = ("_ontology", "_prompts", "_ui", "_scorers")

    def __init__(self) -> None:
        self._ontology: List[OntologyPack] = []
        self._prompts: List[PromptPack] = []
        # Keyed by (pack_id, panel_id) so accidental double-mount is
        # caught at registration. Value is the UIPanel instance.
        self._ui: Dict[Tuple[str, str], UIPanel] = {}
        # Keyed by scorer pack_id for v0.3. PR after C3 will widen
        # this to (slot_id, pack_id) once a second scorer-providing
        # pack exists; the conflict policy stays "loud".
        self._scorers: Dict[str, Scorer] = {}

    # ─── ontology ───────────────────────────────────────────────────

    def register_ontology(self, pack: OntologyPack) -> None:
        if not isinstance(pack, OntologyPack):
            raise PluginLoadError(
                f"ontology slot rejected: object does not satisfy "
                f"OntologyPack protocol; got "
                f"{type(pack).__name__}"
            )
        self._ontology.append(pack)

    def ontology_packs(self) -> Tuple[OntologyPack, ...]:
        """All registered ontology packs in registration order."""
        return tuple(self._ontology)

    # ─── prompts ────────────────────────────────────────────────────

    def register_prompts(self, pack: PromptPack) -> None:
        if not isinstance(pack, PromptPack):
            raise PluginLoadError(
                f"prompts slot rejected: object does not satisfy "
                f"PromptPack protocol; got {type(pack).__name__}"
            )
        self._prompts.append(pack)

    def prompt_packs(self) -> Tuple[PromptPack, ...]:
        """All registered prompt packs in registration order.

        Resolution policy lives in the consumer
        (``core/reasoning/modes/``) — registry only stores. Default
        consumer policy is last-registered-first, falling through to
        the built-in default when every pack returns ``""``.
        """
        return tuple(self._prompts)

    # ─── ui panels ──────────────────────────────────────────────────

    def register_ui_panel(self, panel: UIPanel) -> None:
        if not isinstance(panel, UIPanel):
            raise PluginLoadError(
                f"ui slot rejected: object does not satisfy UIPanel "
                f"protocol; got {type(panel).__name__}"
            )
        key = (panel.pack_id, panel.panel_id)
        if key in self._ui:
            raise PluginLoadError(
                f"ui panel {key} already registered; the same "
                f"(pack_id, panel_id) pair cannot be mounted twice"
            )
        self._ui[key] = panel

    def ui_panels(self) -> Tuple[UIPanel, ...]:
        """All registered UI panels. Iteration order is insertion order."""
        return tuple(self._ui.values())

    # ─── scorers ────────────────────────────────────────────────────

    def register_scorer(self, scorer: Scorer) -> None:
        if not isinstance(scorer, Scorer):
            raise PluginLoadError(
                f"scorers slot rejected: object does not satisfy "
                f"Scorer protocol; got {type(scorer).__name__}"
            )
        pack_id = scorer.pack_id
        if pack_id in self._scorers:
            raise PluginLoadError(
                f"scorer for pack_id={pack_id!r} already registered; "
                f"two scorers in the same slot is an unresolved "
                f"conflict (declare in only one pack)"
            )
        self._scorers[pack_id] = scorer

    def scorers(self) -> Tuple[Scorer, ...]:
        """All registered scorers."""
        return tuple(self._scorers.values())

    # ─── diagnostics ────────────────────────────────────────────────

    def slot_counts(self) -> Dict[str, int]:
        """Quick startup-log line: how many implementations per slot."""
        return {
            "ontology": len(self._ontology),
            "prompts": len(self._prompts),
            "ui": len(self._ui),
            "scorers": len(self._scorers),
        }


# ─── Process-wide singleton ────────────────────────────────────────
#
# Populated by ``core/plugins/loader.load_packs_from_env()``. Consumers
# import this name; replacing it (e.g. in a test) goes through the
# loader.

_REGISTRY: PluginRegistry = PluginRegistry()


def get_registry() -> PluginRegistry:
    """Return the process-wide registry."""
    return _REGISTRY


def _set_registry_for_testing(new: PluginRegistry) -> None:
    """Replace the process-wide registry. Tests only.

    Production code never calls this — the registry is built once at
    startup by the loader and never swapped. Tests use this to inject
    a fresh registry per case without depending on import-time state.
    """
    global _REGISTRY
    _REGISTRY = new


__all__ = [
    "PluginRegistry",
    "get_registry",
    "_set_registry_for_testing",
]


# Annotation-only import to keep mypy happy about Any-typed locals
# inside the slot methods. Not used at runtime; here to keep the
# linter from flagging "unused import" while making the type
# surface explicit.
_ = Any  # noqa: F841
