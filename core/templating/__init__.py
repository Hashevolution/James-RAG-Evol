"""core.templating — horizontal document-shaping engine (v0.6).

The operator supplies a template at runtime, pastes raw content, and
JAMES reshapes the content onto the template structure and returns a
downloadable file. **JAMES ships zero templates** — templates are user
data stored under the workspace (CLAUDE.md rule #1). See
``docs/design/v0.6-template-formatting-ui.md`` and ARCHITECTURE §5.7.14.

Public surface (re-exported here):
  * :mod:`core.templating.spec`     — ``parse_template`` / ``TemplateSpec``
  * :mod:`core.templating.store`    — workspace CRUD
  * :mod:`core.templating.ingest`   — input modes → raw template text
  * :mod:`core.templating.formatter`— LLM reshaping pass
  * :mod:`core.templating.render`   — formatted text → output bytes
"""
from __future__ import annotations

from core.templating.spec import (  # noqa: F401
    Section,
    TemplateSpec,
    parse_template,
)
from core.templating.store import (  # noqa: F401
    TemplateStoreError,
    VALID_MODES,
    create_template,
    delete_template,
    get_template,
    list_templates,
    new_output_id,
    output_dir,
)

__all__ = [
    "Section",
    "TemplateSpec",
    "parse_template",
    "TemplateStoreError",
    "VALID_MODES",
    "create_template",
    "delete_template",
    "get_template",
    "list_templates",
    "new_output_id",
    "output_dir",
]
