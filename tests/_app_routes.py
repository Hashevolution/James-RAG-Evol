"""Collect an app's route paths across FastAPI's router-inclusion change.

Why this exists
---------------
Until recently ``FastAPI.include_router`` flattened a router's routes
into ``app.routes``, so a test could do::

    paths = {r.path for r in app.routes if hasattr(r, "path")}

and see every endpoint. Under the versions now installed (fastapi
0.141.1 / starlette 1.6.0) inclusion instead appends one
``fastapi.routing._IncludedRouter`` wrapper per ``include_router`` call.
The wrapper routes requests correctly but exposes no ``path``, so the
old comprehension silently drops every included endpoint — for this
server, 19 wrappers hiding ~137 paths, leaving only the handful declared
directly on the app.

That is what made seven suites fail with "'/query/' not found in
{...}" while the endpoint was working: verified with TestClient, where
``/query/`` answers 422, ``/workspace/info`` 401 and ``/templates/``
405 — all handler-reached, no 404 anywhere. The defect was in how the
tests looked, not in the app.

This module keeps that knowledge in one place instead of nine.
"""
from __future__ import annotations

from typing import Any, Iterable


def iter_routes(app_or_routes: Any) -> Iterable[Any]:
    """Yield every real route object, unwrapping included routers.

    Accepts an app or a routes list. Recurses, so a router included into
    a router is still reached.
    """
    routes = getattr(app_or_routes, "routes", app_or_routes)
    for route in routes:
        inner = getattr(route, "original_router", None)
        if inner is not None:
            yield from iter_routes(inner)
        else:
            yield route


def route_paths(app_or_routes: Any) -> set[str]:
    """The set of URL paths the app actually serves.

    Mirrors what the old ``{r.path for r in app.routes}`` returned before
    the inclusion change, so call sites keep their assertions.

    Note: this server calls ``include_router`` without ``prefix``
    everywhere, so a router's own paths are its final paths. If a prefix
    is ever introduced, this needs to compose it — there is a test for
    that assumption in tests/test_app_routes_helper.py.
    """
    return {p for p in (getattr(r, "path", None) for r in iter_routes(app_or_routes))
            if p is not None}


__all__ = ["iter_routes", "route_paths"]
