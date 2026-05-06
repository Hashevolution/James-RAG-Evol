"""
PROJECT JAMES — Deprecation shim for the JEPA-named query expander.

The module was renamed to ``core.query_expander`` in v0.2 (B3,
docs/handovers/v0.1.3.1-hotfix.md) because it never implemented JEPA
(Joint-Embedding Predictive Architecture). It is a keyword synonym
dictionary plus a Korean stopword filter — no embedding, no
predictor, no joint architecture.

This shim re-exports the new module so existing imports (`from
core.jepa_adapter import expand`) keep working through one minor.
Plan: remove in v0.3.

Update your imports:

    # before
    from core.jepa_adapter import expand, JEPA_TOKEN_HARD_LIMIT

    # after
    from core.query_expander import expand, TOKEN_HARD_LIMIT
"""

import warnings as _warnings

_warnings.warn(
    "core.jepa_adapter is deprecated and will be removed in v0.3. "
    "Use core.query_expander instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export everything from the new module so legacy imports keep working.
from core.query_expander import (   # noqa: F401, E402
    expand,
    TOKEN_HARD_LIMIT,
    TIMEOUT_SEC,
    JEPA_TOKEN_HARD_LIMIT,
    JEPA_TIMEOUT_SEC,
    SYSTEM_LOG_PATH,
    _SYNONYM_MAP,
    _STOPWORDS,
    _log,
    _tokenize_simple,
    _expand_keywords,
    _hard_truncate,
)
