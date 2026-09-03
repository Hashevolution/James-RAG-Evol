"""Server-split boot smoke — invariants 2 + 4 + 5 (docs/design/v0.4.x-server-split.md).

Verifies that across every PR in the v0.4.x server-split cycle:
  - app boots without exception (module imports)
  - middleware stack order unchanged (rate_limit OUTER, no_cache_static INNER)
  - /static mount path present
  - @app.on_event("startup") hook registered
  - core route shape (auth + ops endpoints) intact

Does NOT exercise handler bodies — that is `pytest tests/` at large. This
file is the structural-snapshot test the design memo §6.2 sketches.

The audit_endpoint_paths.py script covers invariant 1 (URL byte-identical).
This file covers the rest of the bootstrap surface.
"""
from __future__ import annotations

from typing import Iterable


def _import_app():
    """Import server_llmwiki and return its FastAPI app.

    Wrapped in a function so import errors surface as a test failure rather
    than a collection-time crash that hides the line number.
    """
    import server_llmwiki  # noqa: F401  (side-effect import: DB init + state)
    return server_llmwiki.app


def _path_set(routes: Iterable) -> set[str]:
    # [2026-08-26] fastapi 0.141 / starlette 1.6 append one
    # _IncludedRouter wrapper per include_router instead of flattening
    # the router's routes into app.routes. The wrapper carries no
    # `path`, so the old comprehension dropped every included endpoint —
    # 19 wrappers hiding ~137 paths here. route_paths unwraps them.
    # The endpoints were never missing: TestClient gets 422 on /query/,
    # 401 on /workspace/info, 405 on /templates/ — no 404 anywhere.
    from tests._app_routes import route_paths
    return route_paths(routes)


def test_app_imports_cleanly():
    """Invariant: server_llmwiki imports without raising."""
    app = _import_app()
    assert app is not None
    assert app.title == "PROJECT JAMES - AI Knowledge Engine"


def test_static_mount_present():
    """Invariant 4: /static mount survives the split."""
    app = _import_app()
    # Starlette Mount objects expose .path; iterate looking for /static.
    mounts = [r for r in app.routes if type(r).__name__ == "Mount"]
    paths = {getattr(m, "path", None) for m in mounts}
    assert "/static" in paths, f"/static mount missing — found {paths}"


def test_middleware_stack_includes_rate_limit_and_no_cache():
    """Invariant 2: middleware stack carries the two HTTP middlewares.

    Starlette stores user-added middleware in `app.user_middleware` as a
    list, but `add_middleware` does `insert(0, ...)` — so the LAST one
    decorated lives at index 0 and becomes OUTERMOST at request time
    (Starlette wraps `for ... in reversed(middleware)` in
    `build_middleware_stack`).

    Concretely for the server pre-split:
      - `@app.middleware("http")` on no_cache_static (line 187) → added first
      - `@app.middleware("http")` on rate_limit_middleware (line 606) → added second
      - app.user_middleware = [rate_limit, no_cache_static]
      - At request time: rate_limit runs OUTER (can 429 short-circuit),
        no_cache_static runs INNER (adjusts response headers).

    We assert rate_limit at a LOWER index than no_cache_static so the
    short-circuit ordering survives every server-split PR.
    """
    app = _import_app()
    # `user_middleware` is the order user added them — last = outermost.
    names = []
    for mw in app.user_middleware:
        # Each is a Middleware(BaseHTTPMiddleware, dispatch=<fn>, ...).
        dispatch = mw.kwargs.get("dispatch") if hasattr(mw, "kwargs") else None
        if dispatch is None:
            # Older Starlette layouts store the func differently — fall
            # back to repr matching to keep this test stable across
            # Starlette upgrades (string-match the function name).
            dispatch = mw
        names.append(getattr(dispatch, "__name__", repr(dispatch)))

    haystack = "\n".join(names)
    assert "no_cache_static" in haystack, (
        f"no_cache_static missing from middleware stack:\n{haystack}"
    )
    assert "rate_limit_middleware" in haystack, (
        f"rate_limit_middleware missing from middleware stack:\n{haystack}"
    )
    # rate_limit_middleware was decorated LAST → insert(0) → ends up at
    # lower index than no_cache_static → outermost at request time.
    idx_no_cache = next(
        i for i, n in enumerate(names) if "no_cache_static" in n
    )
    idx_rate = next(
        i for i, n in enumerate(names) if "rate_limit_middleware" in n
    )
    assert idx_rate < idx_no_cache, (
        f"middleware order wrong — rate_limit_middleware must be at lower "
        f"index than no_cache_static (outermost at request time, can 429 "
        f"short-circuit). Got: {names}"
    )


def test_startup_event_registered():
    """Invariant 5: @app.on_event("startup") survives the split."""
    app = _import_app()
    handlers = app.router.on_startup
    # Should be non-empty; the named handler is `on_startup` from
    # server_llmwiki.py.
    assert handlers, "no startup event handlers registered"
    names = [getattr(h, "__name__", repr(h)) for h in handlers]
    assert any("on_startup" in n for n in names), (
        f"on_startup handler missing from startup hooks: {names}"
    )


def test_core_auth_and_ops_routes_present():
    """Anchor routes that every server-split PR (A → H) must keep alive.

    Picks a small, deliberately stable subset — the URL byte-identical
    invariant (scripts/audit_endpoint_paths.py) is the comprehensive
    check; this test exists so a smoke-test failure points at the
    likely-broken category fast.
    """
    app = _import_app()
    paths = _path_set(app.routes)

    anchor = {
        # Operations endpoints — always public.
        "/healthz",
        "/",
        # Auth surface.
        "/login/",
        "/signup/",
        # Upload + query — high-traffic auth-gated.
        "/upload/",
        "/query/",
        # API key management — present in routes/auth.py post-PR-A.1.
        "/api-keys/list",
        # Admin user mgmt.
        "/admin/users",
    }
    missing = anchor - paths
    assert not missing, f"anchor routes missing post-split: {sorted(missing)}"


def test_routes_deps_singletons_registered():
    """PR-A foundation: routes/_deps singletons populated at boot.

    set_rag_engine / set_file_processor / set_rate_limiter must be called
    before any include_router so extracted routers see real instances.
    This test imports the server (triggering boot) then asserts the
    routes/_deps getters return non-None.
    """
    _import_app()  # Triggers server boot + set_* calls.

    from routes._deps import (
        get_file_processor,
        get_rag_engine,
        get_rate_limiter,
    )
    assert get_rag_engine() is not None
    assert get_file_processor() is not None
    assert get_rate_limiter() is not None
