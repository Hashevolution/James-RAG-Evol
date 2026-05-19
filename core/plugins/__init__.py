"""Plugin contract layer — Track C of the v0.3 Platform Skeleton.

This package will eventually contain:

  - ``base.py``      — Protocol types for the 4 plugin slots
  - ``errors.py``    — PluginLoadError / PluginVersionError
  - ``loader.py``    — JAMES_PACKS env-driven dynamic loader (PR-C3)
  - ``manifest.py``  — pack.yaml schema + license: field (PR-C3)
  - ``registry.py``  — in-memory slot registry (PR-C3)

PR-C2 (this PR) ships ``base.py`` + ``errors.py`` only. The loader,
manifest parser, and registry land in PR-C3.

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

__all__ = [
    "OntologyPack",
    "PromptPack",
    "UIPanel",
    "Scorer",
    "PanelContext",
    "KNOWN_MODES",
    "PluginLoadError",
    "PluginVersionError",
]
