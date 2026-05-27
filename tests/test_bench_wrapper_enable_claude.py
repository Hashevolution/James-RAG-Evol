"""F3 (2026-05-27) — contract tests for bench_lc_scope_arms `--enable-claude`.

Pins the flag plumbing without spawning a server. The end-to-end
acceptance (claude_code_cli backend actually routes wide-tier
decisions) is the operator-run acceptance gate documented in the
result doc — runs against a live `claude` CLI + ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_module_toggle_default_off():
    """Default (`--enable-claude` not passed) keeps the legacy
    small-tier-only fleet behaviour. Backward-compat with the L.D
    F1/F4/F5 acceptance runs."""
    import importlib
    import scripts.bench_lc_scope_arms as wrap
    importlib.reload(wrap)
    assert wrap._ENABLE_CLAUDE_LARGE_TIER is False


def test_flag_plumbs_to_module_toggle(monkeypatch):
    """Simulate CLI invocation by setting sys.argv around `main()`
    parser setup. We can't run `main()` end-to-end (it spawns a
    server) so we patch _run_arm to no-op and verify the module
    toggle flips when --enable-claude is in argv."""
    import scripts.bench_lc_scope_arms as wrap

    monkeypatch.setattr(
        wrap, "_run_arm",
        lambda *_a, **_kw: None,  # short-circuit — main returns 1 on None
    )
    monkeypatch.setattr(sys, "argv", ["bench_lc_scope_arms.py", "--enable-claude"])
    wrap._ENABLE_CLAUDE_LARGE_TIER = False
    try:
        rc = wrap.main()
    except SystemExit as e:
        rc = e.code
    assert wrap._ENABLE_CLAUDE_LARGE_TIER is True, (
        "--enable-claude must propagate to the module-level toggle so "
        "_run_arm sees it before spawning the server"
    )
    assert rc in (None, 0, 1)


def test_flag_injects_env_into_server_spawn(monkeypatch):
    """When the toggle is on, _run_arm must add JAMES_ENABLE_CLAUDE_BACKEND=1
    to the env dict before spawning the server. We capture the env
    by patching _spawn_server."""
    import scripts.bench_lc_scope_arms as wrap

    captured_env = {}

    def fake_spawn(env):
        captured_env.update(env)
        return None  # short-circuit the rest of _run_arm

    monkeypatch.setattr(wrap, "_spawn_server", fake_spawn)
    wrap._ENABLE_CLAUDE_LARGE_TIER = True
    try:
        wrap._run_arm("test-arm", "1")
    finally:
        wrap._ENABLE_CLAUDE_LARGE_TIER = False
    assert captured_env.get("JAMES_ENABLE_CLAUDE_BACKEND") == "1"
    assert captured_env.get("JAMES_AUTO_ROUTER") == "1"
    assert captured_env.get("JAMES_SCOPE_ROUTING") == "1"


def test_flag_off_does_not_inject_claude_env(monkeypatch):
    """Default toggle = off → server_env must NOT contain
    JAMES_ENABLE_CLAUDE_BACKEND. Pins back-compat invariant."""
    import scripts.bench_lc_scope_arms as wrap

    captured_env = {}

    def fake_spawn(env):
        captured_env.update(env)
        return None

    monkeypatch.setattr(wrap, "_spawn_server", fake_spawn)
    # Make sure no inherited env leaks in
    monkeypatch.delenv("JAMES_ENABLE_CLAUDE_BACKEND", raising=False)
    wrap._ENABLE_CLAUDE_LARGE_TIER = False
    wrap._run_arm("test-arm", "0")
    assert "JAMES_ENABLE_CLAUDE_BACKEND" not in captured_env, (
        "default toggle must not register the claude backend — "
        "back-compat with L.D F1/F4/F5 small-tier-only fleet runs"
    )
