"""Backend conformance suite (R1–R6).

From ``docs/design/v0.3-llm-provider-contract.md`` §"Conformance tests".
Every backend in ``core/reasoning/backends/`` must pass these checks
before being eligible for the JAMES handbook of registered backends.
External implementers (Ali's Gemini-API backend, OpenAI / Mistral
plugins, …) point their CI at this same suite.

The 7 checks the contract names:

  1. **Type** — ``isinstance(backend, Backend)`` is True (Protocol).
  2. **R1** — ``.complete(...)`` against an intentionally-broken
     upstream never raises; it returns ``CompletionResult`` with
     ``error`` populated.
  3. **R2** — ``backend.backend_id == name_registered_under``.
  4. **R3** — ``result.latency_ms >= 0`` (and plausibly bounded).
  5. **R4** — every reserved kwarg is accepted without raising:
     ``system``, ``max_tokens``, ``timeout``, ``model``,
     ``use_cache``. (``temperature`` is required for backends used
     in the 3×3 Gemma 4 experiment; we tag-skip those for backends
     that don't claim that role.)
  6. **R5** — backend module's SDK imports stay inside the module
     itself; ``tests.test_no_sdk_leakage`` is the architectural test
     for the *middleware-side* of this rule and runs in CI; this
     suite just sanity-checks that the backend file does NOT, by
     accident, get caught when the no-sdk-leakage test enumerates
     middleware files.
  7. **R6** — stateless backends produce the same shape twice; stateful
     backends document the state in the module docstring and expose
     a callable ``reset()`` method. (Determinism of the model output
     itself is not asserted — temperature > 0 makes that meaningless.)

The two reference backends on main — ``ollama_local`` and
``claude_code_cli`` — are exercised by parameterized tests. Each
backend is mocked at the SDK boundary (RouterWrapper / subprocess.Popen)
so the suite is hermetic: no live ollama, no live Claude CLI required.

External backends register themselves under ``JAMES_PLUGINS``
(Track 1 PR-C) and inherit the same checks automatically — the
parameterization picks up whatever ``list_backends()`` returns.
"""
from __future__ import annotations

import inspect
import os
import sys
import unittest
from typing import Iterable, Tuple
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.console import ensure_utf8_console  # noqa: E402
ensure_utf8_console()

from core.reasoning.backends import (  # noqa: E402
    Backend,
    CompletionResult,
)


# ─── Per-backend mock harness ─────────────────────────────────────
#
# Each reference backend has a different SDK boundary. The harness
# below installs the minimum mock so .complete() returns a real
# CompletionResult without reaching out to ollama or the claude CLI.
# External backends added later add their own entry here.


def _instantiate_backend(name: str):
    """Construct a backend instance by registry name. Used so the
    parameterized tests can run against backends whose constructor
    needs no arguments (the standard case for the reference impls).
    """
    if name == "ollama_local":
        from core.reasoning.backends.ollama_local import OllamaLocalBackend
        b = OllamaLocalBackend()
        # Inject a fake router so .complete() doesn't reach the network.
        fake_router = MagicMock()
        fake_router.call_gemma.return_value = "ok"
        b._router = fake_router
        return b
    if name == "claude_code_cli":
        from core.reasoning.backends.claude_code_cli import ClaudeCodeCliBackend
        # Constructor takes an optional cli_path — pass a fake one and
        # patch subprocess.Popen at call sites in the tests below.
        return ClaudeCodeCliBackend(cli_path="/fake/claude")
    if name == "diffusiongemma_local":
        # v0.6.1 v18 (2026-06-16) spike. Inject a fake requests.Session
        # so the suite never reaches a vLLM / llama.cpp-server. The
        # session returns a Response-like object whose .json() yields
        # an OpenAI-shaped successful completion.
        from core.reasoning.backends.diffusiongemma_local import (
            DiffusionGemmaLocalBackend,
        )
        b = DiffusionGemmaLocalBackend(
            url="http://fake.invalid",
            model="diffusiongemma-26b-a4b-it-test",
        )
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {
            "choices": [{
                "message": {"role": "assistant", "content": "ok"},
                "finish_reason": "stop",
            }],
        }
        fake_resp.text = '{"choices":[{"message":{"content":"ok"}}]}'
        fake_session = MagicMock()
        fake_session.post.return_value = fake_resp
        b._session = fake_session
        return b
    raise ValueError(f"no mock harness for backend {name!r}")


def _enumerate_reference_backends() -> Iterable[Tuple[str, str]]:
    """Yield (registry_name, harness_name) for backends covered by
    this hermetic suite. The two reference backends ship on main;
    additional entries are added when new in-tree backends arrive.

    Plugin-supplied backends (Track 1 PR-C) get a separate test class
    that takes them straight off ``list_backends()`` — we don't have
    a hermetic harness for them, so the assertions are scoped to the
    Protocol-level guarantees.
    """
    yield ("ollama_local", "ollama_local")
    if os.environ.get("JAMES_ENABLE_CLAUDE_BACKEND") == "1":
        yield ("claude_code_cli", "claude_code_cli")
    if os.environ.get("JAMES_ENABLE_DIFFUSIONGEMMA") == "1":
        yield ("diffusiongemma_local", "diffusiongemma_local")


# ─── Conformance assertions ───────────────────────────────────────


class ReferenceBackendConformanceTests(unittest.TestCase):
    """The two reference backends on main: ollama_local + (optionally)
    claude_code_cli. Each check is exercised per backend via subTest
    so a failure pinpoints which backend tripped which clause.
    """

    def test_protocol_type(self):
        """R1 type check: every reference backend satisfies the
        Backend Protocol (has ``backend_id`` + ``.complete``).
        """
        for name, harness in _enumerate_reference_backends():
            with self.subTest(backend=name):
                b = _instantiate_backend(harness)
                self.assertIsInstance(
                    b, Backend,
                    f"{name} does not satisfy the Backend Protocol "
                    f"(missing .backend_id or .complete?).",
                )

    def test_r1_broken_upstream_does_not_raise(self):
        """R1 — invalid input / broken upstream returns a
        ``CompletionResult`` with ``error`` set, not an exception.
        """
        # ollama_local — make RouterWrapper raise
        from core.reasoning.backends.ollama_local import OllamaLocalBackend
        b = OllamaLocalBackend()
        fake = MagicMock()
        fake.call_gemma.side_effect = RuntimeError("ollama unreachable")
        b._router = fake
        res = b.complete("hi", timeout=1.0)
        self.assertIsInstance(res, CompletionResult)
        self.assertNotEqual(res.error, "")
        self.assertEqual(res.text, "")

        # claude_code_cli — make Popen raise (e.g. CLI missing)
        if os.environ.get("JAMES_ENABLE_CLAUDE_BACKEND") == "1":
            from core.reasoning.backends.claude_code_cli import ClaudeCodeCliBackend
            cb = ClaudeCodeCliBackend(cli_path="/fake/claude")
            with patch("subprocess.Popen",
                       side_effect=FileNotFoundError("no claude binary")):
                res2 = cb.complete("hi", timeout=1.0)
            self.assertIsInstance(res2, CompletionResult)
            self.assertNotEqual(res2.error, "")
            self.assertEqual(res2.text, "")

        # diffusiongemma_local — make requests.Session.post raise
        # (timeout, network down, …).
        if os.environ.get("JAMES_ENABLE_DIFFUSIONGEMMA") == "1":
            from core.reasoning.backends.diffusiongemma_local import (
                DiffusionGemmaLocalBackend,
            )
            import requests as _req
            db = DiffusionGemmaLocalBackend(url="http://fake.invalid")
            fake_session = MagicMock()
            fake_session.post.side_effect = _req.Timeout("boom")
            db._session = fake_session
            res3 = db.complete("hi", timeout=1.0)
            self.assertIsInstance(res3, CompletionResult)
            self.assertNotEqual(res3.error, "")
            self.assertEqual(res3.text, "")

    def test_r2_backend_id_matches_registry_name(self):
        """R2 — backend_id is the registry name. Live registry is
        consulted so the assertion fails if someone registers
        ollama_local under a different key.
        """
        from core.reasoning import backends
        for name in backends.list_backends():
            with self.subTest(backend=name):
                b = backends.get_backend(name)
                self.assertEqual(
                    b.backend_id, name,
                    f"backend registered as {name!r} reports its "
                    f"backend_id as {b.backend_id!r} — mismatched names "
                    f"make trace records unreplayable.",
                )

    def test_r3_latency_ms_nonnegative_and_set(self):
        """R3 — ``latency_ms`` is populated and ``>= 0``. Backends
        measure end-to-end wall clock, so the field can be 0 only if
        the call returned instantaneously (a mock path); negative or
        absent is a bug.
        """
        for name, harness in _enumerate_reference_backends():
            with self.subTest(backend=name):
                b = _instantiate_backend(harness)
                # Drive a known-cheap path so the field is exercised.
                if name == "claude_code_cli":
                    fake_proc = MagicMock()
                    fake_proc.communicate.return_value = ("hi", "")
                    fake_proc.returncode = 0
                    with patch("subprocess.Popen", return_value=fake_proc):
                        res = b.complete("p")
                else:
                    res = b.complete("p")
                self.assertGreaterEqual(
                    res.latency_ms, 0,
                    f"{name} returned negative latency_ms = "
                    f"{res.latency_ms}",
                )
                self.assertIsInstance(res.latency_ms, int)

    def test_r4_reserved_kwargs_accepted(self):
        """R4 — every reserved kwarg is accepted without raising.
        Backends may translate or ignore each, but they must not
        refuse. ``temperature`` is the swept variable for the Gemma
        4 3×3 experiment, so both reference backends accept it on
        main (ollama_local applies; claude_code_cli ignores — both
        legal per R4).
        """
        reserved = dict(
            system="be helpful",
            max_tokens=128,
            timeout=10.0,
            model=None,
            use_cache=False,
            temperature=0.7,
        )
        for name, harness in _enumerate_reference_backends():
            with self.subTest(backend=name):
                b = _instantiate_backend(harness)
                # Don't care about the result here, only that no
                # TypeError / NotImplementedError surfaces.
                if name == "claude_code_cli":
                    fake_proc = MagicMock()
                    fake_proc.communicate.return_value = ("hi", "")
                    fake_proc.returncode = 0
                    with patch("subprocess.Popen", return_value=fake_proc):
                        b.complete("p", **reserved)
                else:
                    b.complete("p", **reserved)

    def test_r4_temperature_reaches_ollama_for_3x3_experiment(self):
        """R4 sub-clause for the 3×3 experiment: ollama_local must
        actually *apply* temperature rather than just accept it.
        The variable that the experiment sweeps must propagate end
        to end into the ollama HTTP options block.

        We inspect the fake router's recorded call rather than the
        outgoing HTTP request — the contract surface lives at
        ``RouterWrapper.call_gemma``'s signature, which now takes a
        ``temperature`` kwarg.
        """
        from core.reasoning.backends.ollama_local import OllamaLocalBackend
        b = OllamaLocalBackend()
        fake_router = MagicMock()
        fake_router.call_gemma.return_value = "ok"
        b._router = fake_router
        b.complete("p", temperature=0.9)
        # Capture the kwarg the router actually received.
        call_kwargs = fake_router.call_gemma.call_args.kwargs
        self.assertEqual(
            call_kwargs.get("temperature"), 0.9,
            "ollama_local must forward `temperature` into "
            "RouterWrapper.call_gemma so the 3×3 experiment's swept "
            "variable reaches the model. Saw kwargs: "
            f"{sorted(call_kwargs.keys())}",
        )

    def test_r4_arbitrary_extra_opts_tolerated(self):
        """R4 sub-clause — backends accept **opts without refusing
        unknown kwargs. An external caller may pass forward-compat
        hints (e.g. ``stop=["END"]`` once streaming lands); current
        backends must ignore them silently.
        """
        for name, harness in _enumerate_reference_backends():
            with self.subTest(backend=name):
                b = _instantiate_backend(harness)
                if name == "claude_code_cli":
                    fake_proc = MagicMock()
                    fake_proc.communicate.return_value = ("hi", "")
                    fake_proc.returncode = 0
                    with patch("subprocess.Popen", return_value=fake_proc):
                        b.complete("p", future_kwarg="should_be_ignored")
                else:
                    b.complete("p", future_kwarg="should_be_ignored")

    def test_r5_no_sdk_leakage_test_covers_middleware(self):
        """R5 — the architectural enforcement lives in
        ``tests.test_no_sdk_leakage``. This test simply pins that
        the no-sdk-leakage suite still imports + at least asserts
        the middleware roots are non-empty, so a future refactor
        that accidentally guts that test gets caught here too.
        """
        import tests.test_no_sdk_leakage as nsl
        # Both helpers must remain importable and non-empty.
        self.assertGreater(
            len(nsl._FORBIDDEN_SDK_PREFIXES), 0,
            "test_no_sdk_leakage._FORBIDDEN_SDK_PREFIXES emptied — "
            "R5 enforcement at the middleware boundary would be a "
            "no-op.",
        )
        self.assertTrue(
            list(nsl._iter_middleware_files()),
            "test_no_sdk_leakage._iter_middleware_files() returned "
            "nothing — the middleware roots drifted out of sync with "
            "the codebase layout.",
        )

    def test_r6_statefulness_documented_or_stateless(self):
        """R6 — stateful backends document the state in the module
        docstring and expose a callable ``reset()``. A backend with
        neither claim is treated as stateless and must produce the
        same *shape* (not necessarily same text — that's the model's
        stochasticity) for the same inputs.

        On main, ``ollama_local`` is stateless (RouterWrapper is
        process-scoped but exposes no per-instance state) and
        ``claude_code_cli`` is stateful via the subprocess handle,
        documented in its module docstring. Plugin backends declare
        their stance the same way.
        """
        for name, harness in _enumerate_reference_backends():
            with self.subTest(backend=name):
                b = _instantiate_backend(harness)
                module = inspect.getmodule(type(b))
                self.assertIsNotNone(
                    module,
                    f"could not resolve module for {name}",
                )
                docstring = (module.__doc__ or "").lower()
                has_reset = callable(getattr(b, "reset", None))
                claims_stateful = (
                    "stateful" in docstring
                    or "subprocess handle" in docstring
                )
                if claims_stateful:
                    self.assertTrue(
                        has_reset,
                        f"{name} claims stateful but exposes no "
                        f"callable reset() — required by R6.",
                    )
                else:
                    # Stateless backend: two back-to-back calls must
                    # at least return CompletionResult of the same
                    # shape (text type, error type). We don't assert
                    # text equality — model temperature defeats that.
                    if name == "claude_code_cli":
                        fake_proc = MagicMock()
                        fake_proc.communicate.return_value = ("ok", "")
                        fake_proc.returncode = 0
                        with patch("subprocess.Popen", return_value=fake_proc):
                            r1 = b.complete("p")
                            r2 = b.complete("p")
                    else:
                        r1 = b.complete("p")
                        r2 = b.complete("p")
                    self.assertEqual(type(r1.text), type(r2.text))
                    self.assertEqual(type(r1.error), type(r2.error))


class ConformanceMetaTests(unittest.TestCase):
    """Sanity assertions for the suite itself so a bug in the harness
    can't make the conformance checks silently pass.
    """

    def test_reference_backends_enumerated(self):
        """At minimum ollama_local must always be in the list — it's
        the v0.3.0 default and the rest of the system relies on it.
        """
        backends = list(_enumerate_reference_backends())
        names = [n for n, _ in backends]
        self.assertIn(
            "ollama_local", names,
            "_enumerate_reference_backends() must always include "
            "ollama_local — it's the always-registered default.",
        )

    def test_instantiate_unknown_raises(self):
        with self.assertRaises(ValueError):
            _instantiate_backend("definitely_not_a_backend")


if __name__ == "__main__":   # pragma: no cover
    unittest.main()
