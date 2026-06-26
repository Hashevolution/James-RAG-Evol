"""Keep long HTTP responses alive over flaky mobile / Tailscale tunnels.

A request that holds an *idle* connection while the server does 30–90 s of
work (a full RAG query, an image ingest with vision OCR) gets dropped by a
mobile network or a Tailscale re-handshake — the browser surfaces it as
``Failed to fetch`` and the (server-side already-finished) result is lost.
The same blocking call inside an ``async def`` handler also pins the event
loop, so ``/trace/poll`` can't serve live reasoning stages during the
request.

``stream_json_with_heartbeat`` fixes both:

  * runs the blocking ``work()`` in a worker thread (frees the event loop →
    ``/trace/poll`` streams stages live), and
  * emits JSON-insignificant whitespace every few seconds while it runs, so
    bytes keep flowing and the tunnel stays up.

The heartbeat is leading whitespace; ``Response.json()`` / ``JSON.parse``
ignore it, so clients need **no change** — they still ``await r.json()``.

``contextvars`` (e.g. ``core.observability.current_trace_id``) propagate
into the worker thread because ``anyio.to_thread.run_sync`` copies the
current context — so trace correlation is preserved.

Usage — do the fast, status-bearing validation (auth, 400/413/403) BEFORE
calling this (the streamed response is always HTTP 200); put only the slow
work in ``work``::

    return await stream_json_with_heartbeat(_do_the_slow_work)
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

import anyio
from fastapi.responses import StreamingResponse

# Default gap between heartbeats. Kept short (5 s) so even an aggressive
# mobile-carrier / Tailscale idle-eviction window can't open between
# beats. The first beat is emitted IMMEDIATELY (see gen()) so there is no
# initial idle gap between the headers and the first body byte.
_HEARTBEAT_INTERVAL_SEC = 5.0

# Leading whitespace — ignored by any JSON parser, so the client reads the
# concatenated body as plain JSON.
_HEARTBEAT = b" "


async def stream_json_with_heartbeat(
    work: Callable[[], Any],
    *,
    interval: float = _HEARTBEAT_INTERVAL_SEC,
) -> StreamingResponse:
    """Stream ``json.dumps(work())`` while keeping the connection alive.

    ``work`` is a blocking, no-arg callable returning a JSON-serialisable
    object. It runs in a worker thread. On exception the error is streamed
    in the body (``{"answer": "", "error": ...}``) rather than tearing the
    connection — the HTTP status is already ``200`` once streaming starts,
    and the client's empty-answer handling still applies.
    """
    async def gen():
        task = asyncio.ensure_future(anyio.to_thread.run_sync(work))
        # Emit one byte immediately so the body starts flowing the moment
        # the headers go out — no initial idle gap for the tunnel to drop.
        yield _HEARTBEAT
        while not task.done():
            done, _ = await asyncio.wait({task}, timeout=interval)
            if not done:
                yield _HEARTBEAT
        try:
            result = task.result()
            yield json.dumps(result, ensure_ascii=False).encode("utf-8")
        except Exception as e:  # noqa: BLE001 — surface, don't tear the socket
            yield json.dumps(
                {"answer": "", "error": str(e)[:500]},
                ensure_ascii=False,
            ).encode("utf-8")

    # no-store: the whitespace-prefixed body must never be cached.
    return StreamingResponse(
        gen(),
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


__all__ = ("stream_json_with_heartbeat",)
