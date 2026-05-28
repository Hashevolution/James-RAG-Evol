"""HTTP route modules extracted from server_llmwiki.py.

Per docs/design/v0.4.x-server-split.md (Stage 0 design memo). The server-split
roadmap is an 8-PR sequence; this package surfaces as `from routes.<domain>
import router` per domain (auth / llm / jobs / artifacts / evolution /
coding / admin), each registered via `app.include_router(router)` in
server_llmwiki.py.

Invariants (all PRs in the cycle must satisfy):
  1. URL byte-identical (regression gate: scripts/audit_endpoint_paths.py)
  2. Middleware execution order unchanged
  3. _write_audit emit timing + fields unchanged
  4. /static mount path unchanged
  5. @app.on_event("startup") behaviour unchanged
  6. pytest tests/ — collected / passed / xfail delta == 0
"""
