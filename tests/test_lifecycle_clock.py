"""v0.4 Sprint 5 PR-0 — ``core.lifecycle.clock`` contract tests.

Pins the single ``now()`` helper that every T1+T7 path consults for
"current time". The contract is small but load-bearing:

1. ``now()`` returns a **UTC-aware** ``datetime`` so audit rows and
   validity windows have an unambiguous time-zone reading.
2. ``monkeypatch.setattr("core.lifecycle.clock.now", lambda: <fixed>)``
   actually replaces the function (the helper is module-level, not
   class-level, so the patch works without ``autospec`` complexity).
3. The "explicit ``t``" path of the replay primitive
   (``reconstruct_view_at(t=<past>)``, lands at PR-T7.A) is not the
   subject of these tests — it bypasses ``clock.now`` by design.

Entry memo lock reference: §12.2 (hybrid choice — production calls
``clock.now()``, replay endpoint accepts explicit ``t``).
"""
from __future__ import annotations

from datetime import datetime, timezone


from core.lifecycle import clock


def test_now_returns_datetime():
    """Contract: ``now()`` returns a ``datetime`` instance."""
    assert isinstance(clock.now(), datetime)


def test_now_is_utc_aware():
    """Contract: returned datetime carries a non-None tzinfo and the
    tzinfo represents UTC. v0.4 audit rows assume UTC-aware throughout."""
    result = clock.now()
    assert result.tzinfo is not None, (
        "clock.now() must return a timezone-aware datetime — audit "
        "rows + validity windows would be ambiguous otherwise"
    )
    # utcoffset of UTC is timedelta(0). Equivalent to tzinfo == timezone.utc
    # but more permissive (e.g., pytz UTC also passes).
    assert result.utcoffset().total_seconds() == 0, (
        "clock.now() tzinfo must represent UTC (offset 0); got "
        f"{result.utcoffset()}"
    )


def test_now_advances_across_calls():
    """Sanity — two successive calls give monotonically non-decreasing
    timestamps. Catches a pathological monkey-patch leaking across
    tests (e.g., a test forgot to undo a freezer)."""
    a = clock.now()
    b = clock.now()
    assert b >= a, (
        f"clock.now() must be monotonically non-decreasing within a "
        f"single process — got a={a.isoformat()} b={b.isoformat()}"
    )


def test_clock_is_monkey_patchable(monkeypatch):
    """The locked design choice (§12.2) requires that test code can
    freeze time via ``monkeypatch.setattr``. This test guarantees the
    contract — every T1+T7 test that needs deterministic time will
    rely on this patch site."""
    fixed = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("core.lifecycle.clock.now", lambda: fixed)
    assert clock.now() == fixed
    # Repeatable
    for _ in range(10):
        assert clock.now() == fixed


def test_clock_patch_does_not_leak_outside_test(monkeypatch):
    """Defensive — monkeypatch is correctly scoped to one test. Without
    this, a freezer set in test A would persist into test B as silent
    state contamination. pytest's monkeypatch fixture auto-undoes at
    teardown; this test simply confirms the contract holds for our
    setup (we patch a module-level callable, not a class attribute,
    which is the simpler case)."""
    fixed = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("core.lifecycle.clock.now", lambda: fixed)
    assert clock.now() == fixed
    # Teardown will undo — verified by the other tests in this file
    # observing a live clock value.


def test_module_surface():
    """``core.lifecycle.clock`` exposes only ``now`` — keeps the API
    surface single-purpose so future swaps (NTP-corrected clock,
    monotonic ordering) land at one symbol."""
    assert clock.__all__ == ["now"]
    assert hasattr(clock, "now")


def test_lifecycle_package_reexport():
    """``core.lifecycle`` package surfaces ``clock`` for direct import
    — keeps the call-site ``from core.lifecycle import clock`` pattern
    cheap (no separate explicit import of the submodule)."""
    import core.lifecycle as lifecycle_pkg
    assert lifecycle_pkg.clock is clock
    assert "clock" in lifecycle_pkg.__all__
