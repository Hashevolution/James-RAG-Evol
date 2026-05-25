"""``GeneralOntology`` — no-op overlay for the dogfood pack.

This class satisfies the :class:`core.plugins.base.OntologyPack`
Protocol with **empty tuples / dict**. It does NOT mirror or replace
the existing JAMES default ontology in ``core/relations_schema.py``
— the existing schema remains authoritative at runtime.

The point of shipping this class in PR-C5a is to prove the slot
binding works end-to-end: the loader can read ``pack.yaml``, import
this class, verify it satisfies the Protocol, and register it. STEP 7
byte-identity follows trivially because nothing the runtime consults
has changed.

PR-C5b (separate PR, deferred) will wire ``server_llmwiki.py`` startup
to call :func:`core.plugins.loader.load_packs_from_env`, at which
point this class becomes live in the dogfood gate. PR-C5c (further
deferred) is where the existing default ontology — if it ever moves
out of ``core/relations_schema.py`` — would be expressed through this
overlay instead of staying hardcoded.
"""
from __future__ import annotations

from typing import Dict, Tuple


class GeneralOntology:
    """Pack-level ontology declaration. Empty in v0.3.

    The four attributes are checked at load time via
    ``isinstance(obj, OntologyPack)``. Empty values declare the pack
    contributes nothing structural — the existing ontology continues
    to drive the system.
    """

    pack_id: str = "general"
    entity_types: Tuple[str, ...] = ()
    relation_types: Tuple[str, ...] = ()
    hierarchies: Dict[str, Tuple[str, ...]] = {}


__all__ = ["GeneralOntology"]
