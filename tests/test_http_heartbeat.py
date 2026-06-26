"""v0.6.1 — stream_json_with_heartbeat keeps long responses alive.

Long /query/ and /upload/ requests over a mobile / Tailscale tunnel were
dropped while the server worked (idle connection → "Failed to fetch", and
the composer chip stuck because the upload XHR errored even though the
server finished). The fix runs the blocking work in a worker thread and
streams JSON-insignificant whitespace until it's done.

Covers:
  * whitespace heartbeats are streamed while slow work runs, then the
    final JSON — and the concatenated body parses (clients use r.json(),
    which ignores leading whitespace).
  * an exception in work is surfaced in the body (NOT a torn connection).
  * a contextvar set before the call propagates into the worker thread
    (so core.observability.current_trace_id keeps trace correlation).

Run:
  python -m unittest tests.test_http_heartbeat
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import unittest
from contextvars import ContextVar

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.http_heartbeat import stream_json_with_heartbeat


async def _drain(resp):
    out = []
    async for c in resp.body_iterator:
        out.append(c if isinstance(c, (bytes, bytearray)) else c.encode("utf-8"))
    return b"".join(out), out


class HeartbeatStream(unittest.TestCase):
    def test_heartbeats_then_parseable_json(self):
        def slow():
            time.sleep(0.5)
            return {"answer": "ok", "mode": "retrieval"}

        async def run():
            resp = await stream_json_with_heartbeat(slow, interval=0.1)
            return await _drain(resp)

        body, chunks = asyncio.run(run())
        # at least a couple of whitespace heartbeats during the 0.5s work
        hb = sum(1 for c in chunks if c.strip() == b"")
        self.assertGreaterEqual(hb, 2)
        self.assertTrue(body.lstrip().startswith(b"{"))
        # client-equivalent parse (leading whitespace ignored)
        self.assertEqual(json.loads(body)["answer"], "ok")

    def test_exception_surfaced_in_body_not_torn(self):
        def boom():
            raise ValueError("model load failed")

        async def run():
            resp = await stream_json_with_heartbeat(boom, interval=0.1)
            return await _drain(resp)

        body, _ = asyncio.run(run())
        parsed = json.loads(body)
        self.assertEqual(parsed["answer"], "")
        self.assertIn("model load failed", parsed["error"])

    def test_fast_work_no_required_heartbeat(self):
        async def run():
            resp = await stream_json_with_heartbeat(lambda: {"answer": "x"}, interval=5.0)
            return await _drain(resp)

        body, _ = asyncio.run(run())
        self.assertEqual(json.loads(body)["answer"], "x")

    def test_contextvar_propagates_into_worker_thread(self):
        cv: ContextVar[str] = ContextVar("cv", default="")

        def work():
            # must see the value set in the calling (async) context
            return {"seen": cv.get()}

        async def run():
            cv.set("trace-123")
            resp = await stream_json_with_heartbeat(work, interval=0.1)
            return await _drain(resp)

        body, _ = asyncio.run(run())
        self.assertEqual(json.loads(body)["seen"], "trace-123")


if __name__ == "__main__":
    unittest.main()
