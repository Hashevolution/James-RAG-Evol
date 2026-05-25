"""``packs/general/`` — the dogfood pack.

The first first-party pack and the v0.3 dogfood gate for the Plugin
contract. Loaded by default when ``JAMES_PACKS`` is unset (per the
loader contract in ``core/plugins/loader.py``).

**Scope of PR-C5a (this commit)**: declare the pack and expose the
two pack-level Protocol implementations (:class:`GeneralOntology` and
:class:`GeneralPrompts`) as **no-op overlays**. The existing JAMES
defaults in ``core/relations_schema.py`` and ``core/reasoning/modes/``
remain authoritative; the pack neither replaces nor mirrors them in
this PR. STEP 7 byte-identity is therefore trivially satisfied — no
behavioral change reaches the runtime.

**Out of scope (deferred to PR-C5b)**: wiring ``server_llmwiki.py``
startup to call :func:`core.plugins.loader.load_packs_from_env`. Once
that PR lands, this pack becomes the dogfood gate the rest of v0.3
depends on.

Per ``docs/design/v0.3-plugin-api.md`` PR sequence (PR-C5).
"""
from __future__ import annotations

from packs.general.ontology import GeneralOntology
from packs.general.prompts import GeneralPrompts

__all__ = ["GeneralOntology", "GeneralPrompts"]
