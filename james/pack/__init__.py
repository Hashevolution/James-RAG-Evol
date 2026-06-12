"""JAMES Pack SDK — pack-author tooling.

This subpackage provides the CLI scaffolder + the
``OntologyPack`` re-export for pack authors. Runtime invocation:

    python -m james.pack init <pack_id>
    python -m james.pack init --output-dir <path> <pack_id>

See :doc:`docs/ONTOLOGY_PACK_AUTHORING.md` for the full author
guide.
"""
from core.ontology_packs import (
    CapabilityNotGrantedError,
    NameCollisionError,
    OntologyPack,
    SchemaError,
    register_pack,
    unmount_pack,
)

__all__ = (
    "OntologyPack",
    "register_pack",
    "unmount_pack",
    "CapabilityNotGrantedError",
    "NameCollisionError",
    "SchemaError",
)
