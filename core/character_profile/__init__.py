"""``core.character_profile`` — 자메스 성향 수치 관리 (16 traits, P1+W3b+P5c).

Originally a single 24 KB module; split in Stage C.3 (2026-05-24)
into a mixin-based package to respect CLAUDE.md rule #5 (< 20 KB
per file). The external surface is unchanged::

  from core.character_profile import CharacterProfile, get_profile, TRAITS

Re-exports for tests / direct callers:

- ``TRAITS``, ``CORRELATIONS`` — registries
- ``_CORR_INDEX``, ``_OPPONENTS``, ``_RIPPLE_DAMPING`` — private
  ripple-math state (test_character_traits_correlations.py +
  test_character_w3b.py import these directly)
- ``CharacterProfile`` — main class
- ``get_profile`` — module-level singleton accessor

Mixin map:

- ``_traits.py``    — registries + correlation graph (constants only)
- ``_profile.py``   — ``_ProfileCoreMixin``: state, get/set, ripple
                      math, ``_load`` / ``_save`` (preferences DB)
- ``_summary.py``   — ``_SummaryMixin``: ``build_summary`` (static) +
                      ``get_prompt_modifiers`` (uses ``self._values``
                      + ``self.build_summary``)
"""
from __future__ import annotations

from ._profile import _ProfileCoreMixin
from ._summary import _SummaryMixin
from ._traits import (
    _CORR_INDEX,
    _OPPONENTS,
    _RIPPLE_DAMPING,
    CORRELATIONS,
    TRAITS,
)


class CharacterProfile(_SummaryMixin, _ProfileCoreMixin):
    """16-trait character state + LLM prompt modifier projection.

    MRO: SummaryMixin → ProfileCoreMixin → object. No method-name
    collisions; order is documentation-driven (the read/projection
    layer sits above the state layer).

    See ``_profile.py`` for state + ripple math + persistence and
    ``_summary.py`` for the natural-language summary + LLM prompt
    directive generator.
    """
    pass


_profile = None


def get_profile() -> CharacterProfile:
    global _profile
    if _profile is None:
        _profile = CharacterProfile()
    return _profile


__all__ = [
    "CharacterProfile",
    "get_profile",
    "TRAITS",
    "CORRELATIONS",
    "_CORR_INDEX",
    "_OPPONENTS",
    "_RIPPLE_DAMPING",
]
