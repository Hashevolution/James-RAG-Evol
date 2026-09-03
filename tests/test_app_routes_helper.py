"""Guards for tests/_app_routes.py — the router-inclusion unwrapper.

Built on a throwaway FastAPI app rather than the real server, so these
run in milliseconds and do not need the embedding model.
"""
from __future__ import annotations

from fastapi import APIRouter, FastAPI

from tests._app_routes import route_paths


def _app_with_router(prefix: str = "") -> FastAPI:
    app = FastAPI()

    @app.get("/direct")
    def _direct():                      # pragma: no cover - never called
        return {}

    r = APIRouter()

    @r.get("/included")
    def _included():                    # pragma: no cover - never called
        return {}

    @r.post("/included/sub")
    def _sub():                         # pragma: no cover - never called
        return {}

    app.include_router(r, prefix=prefix)
    return app


def test_finds_paths_declared_directly_on_the_app():
    assert "/direct" in route_paths(_app_with_router())


def test_finds_paths_behind_include_router():
    """The regression this helper exists for: before it, an included
    route was invisible because the wrapper carries no `path`."""
    paths = route_paths(_app_with_router())
    assert "/included" in paths
    assert "/included/sub" in paths


def test_accepts_a_routes_list_as_well_as_an_app():
    app = _app_with_router()
    assert route_paths(app.routes) == route_paths(app)


def test_unwraps_a_router_included_into_a_router():
    app = FastAPI()
    inner = APIRouter()

    @inner.get("/deep")
    def _deep():                        # pragma: no cover - never called
        return {}

    outer = APIRouter()
    outer.include_router(inner)
    app.include_router(outer)
    assert "/deep" in route_paths(app)


def test_prefix_assumption_is_explicit():
    """route_paths does not compose a prefix.

    The server includes every router without one, so this is correct
    today. Pinned as a known limit: if this ever fails, FastAPI began
    exposing prefixed paths through the wrapper and route_paths should
    be revisited rather than the assertion loosened.
    """
    paths = route_paths(_app_with_router(prefix="/api"))
    assert "/api/included" not in paths, (
        "include_router(prefix=...) now surfaces composed paths — "
        "update tests/_app_routes.py::route_paths to compose prefixes"
    )
    assert "/included" in paths
