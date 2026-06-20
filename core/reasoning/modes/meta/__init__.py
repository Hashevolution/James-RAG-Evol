"""``handle_meta`` — internal-data inventory ("what do you have?")
package facade.

v0.6.1 v18.7 (2026-06-20) module-size split (CLAUDE.md rule #5):
the single 31.6 KB ``modes/meta.py`` was split into four sibling
modules. The public surface — ``handle_meta`` — is re-exported here
so all existing imports (``from core.reasoning.modes import
handle_meta`` via ``modes/__init__.py``) continue working
byte-identically.

Module layout (private, not part of the public contract):
  - ``_parse.py``   — theme classifier + filter token tables +
                      ``_parse_meta_filter`` dispatcher
  - ``_degree.py``  — frontmatter relation scan + ``_build_degree_map``
  - ``_render.py``  — per-view markdown renderers (type / theme /
                      recent / LLM narrative)
  - ``_handler.py`` — ``handle_meta`` orchestrator (dispatcher)

The split keeps every file well under the 20 KB rule #5 ceiling and
makes each unit independently testable without touching the others.
"""
from __future__ import annotations

from core.reasoning.modes.meta._handler import handle_meta

__all__ = ["handle_meta"]
