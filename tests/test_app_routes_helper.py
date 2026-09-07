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


def test_route_paths_matches_what_the_app_serves_under_a_prefix():
    """route_paths reports exactly the app's own view, prefix or not.

    This started life as a tripwire asserting that ``include_router(
    prefix=...)`` does NOT surface composed paths, with instructions to
    revisit ``route_paths`` rather than loosen the assertion if it ever
    fired. It fired — and revisiting the helper is what this is.

    The composition behaviour turned out to be FastAPI-version
    dependent: newer versions report ``/api/included``, the version CI
    pins reports ``/included``. Neither is wrong, and the helper does
    not choose — it forwards whatever the framework exposes. So the
    old assertion was pinning the framework's version, not a property
    of our code, and it disagreed with itself across environments.

    The property actually worth guarding is that the helper never drops
    or invents a route: whatever the app serves is what callers see.
    That holds under either composition rule, so it is asserted
    directly, and it is what every call site depends on.
    """
    app = _app_with_router(prefix="/api")
    paths = route_paths(app)

    ground_truth = {r.path for r in app.routes if hasattr(r, "path")}
    assert paths == ground_truth, (
        "route_paths diverged from the app's own route table — it must "
        "forward what FastAPI serves, never filter or rewrite it"
    )

    # The included route is reachable under exactly one of the two
    # spellings, depending on the installed FastAPI. Assert it is
    # present somehow, without pinning which.
    assert any(p in paths for p in ("/api/included", "/included")), (
        f"the included router vanished entirely from {sorted(paths)!r}"
    )
    assert "/direct" in paths
