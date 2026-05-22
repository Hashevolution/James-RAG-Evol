"""Plugin contract layer — Track C of the v0.3 Platform Skeleton.

PR-C2 shipped ``base.py`` (4 Protocol types) + ``errors.py``.
PR-C3 (this commit) adds the loader / manifest / registry triad:

  - ``base.py``      — Protocol types for the 4 plugin slots
  - ``errors.py``    — PluginLoadError / PluginVersionError
  - ``loader.py``    — JAMES_PACKS env-driven dynamic loader
  - ``manifest.py``  — pack.yaml schema + license: field (closed enum)
  - ``registry.py``  — in-memory slot registry (process-wide singleton)

PR-C5 (next) extracts current JAMES default behavior into
``packs/general/`` — the dogfood gate that makes the loader live in
production startup. Until then, ``load_packs_from_env`` is a no-op
in the absence of a ``packs/`` directory.

Per ``docs/design/v0.3-plugin-api.md``.
"""
from __future__ import annotations

from core.plugins.base import (
    KNOWN_MODES,
    OntologyPack,
    PanelContext,
    PromptPack,
    Scorer,
    UIPanel,
)
from core.plugins.errors import PluginLoadError, PluginVersionError
from core.plugins.loader import (
    DEFAULT_PACK,
    JAMES_CORE_VERSION,
    load_packs_from_env,
)
from core.plugins.manifest import (
    ALLOWED_LICENSES,
    KNOWN_SLOTS,
    Manifest,
    check_semver,
    parse_manifest,
    read_manifest,
)
from core.plugins.registry import (
    PluginRegistry,
    get_registry,
)

__all__ = [
    # base
    "OntologyPack",
    "PromptPack",
    "UIPanel",
    "Scorer",
    "PanelContext",
    "KNOWN_MODES",
    # errors
    "PluginLoadError",
    "PluginVersionError",
    # manifest
    "ALLOWED_LICENSES",
    "KNOWN_SLOTS",
    "Manifest",
    "check_semver",
    "parse_manifest",
    "read_manifest",
    # registry
    "PluginRegistry",
    "get_registry",
    # loader
    "DEFAULT_PACK",
    "JAMES_CORE_VERSION",
    "load_packs_from_env",
]
