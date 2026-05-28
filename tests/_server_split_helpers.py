"""Helpers for tests that scan server_llmwiki.py source after server-split.

v0.4.x cycle (docs/design/v0.4.x-server-split.md) moves many handlers
out of server_llmwiki.py into routes/<domain>.py modules. Tests that
do source-level assertions (``assertIn("@app.get('/llm/modes/')", src)``)
break when the handler is no longer in server_llmwiki.py.

``combined_server_source()`` returns the concatenated source across
server + every routes/<domain>.py module that exists, with ``@router.``
normalized back to ``@app.`` so existing assertions continue to match.

Adding a new routes/<domain>.py module via include_router (PR-C through
PR-H) requires no change here — they get picked up automatically.
"""
from __future__ import annotations

import importlib
import inspect


def combined_server_source() -> str:
    """Server + all routes/* sources, with @router. normalised to @app.

    The normalisation is correct because every router in routes/<domain>.py
    is registered to the same `app` via `app.include_router(<domain>_router)`
    — the URL surface is the same as if the decorators had stayed on `@app`.
    """
    import server_llmwiki  # noqa: F401  — surfaces import errors clearly
    parts: list[str] = [inspect.getsource(server_llmwiki)]

    # Probe known routes/* modules. Add new ones here as PR-H lands.
    for mod_name in (
        "routes.auth", "routes.llm", "routes.jobs", "routes.artifacts",
        "routes.evolution", "routes.coding", "routes.admin",
    ):
        try:
            mod = importlib.import_module(mod_name)
            parts.append(
                inspect.getsource(mod).replace("@router.", "@app.")
            )
        except ImportError:
            # Module not present yet — fine, just skip.
            continue
    return "\n".join(parts)
