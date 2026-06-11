"""S5 — `JAMES_FORCE_CLOUD` synth wiring tests.

Locks the contract added in `core/reasoning/trace_helpers.py`:

  • flag OFF                  → byte-identical to pre-S5 (direct backend.complete)
  • flag ON  + cloud backend  → routes through core.abstraction.run_cloud_egress
                                (abstraction audit fires, restored text returned)
  • flag ON  + local backend  → logs + falls through (no abstraction wrap;
                                wrapping local would be a confusing no-op)
  • flag ON  + abstraction import explodes → caught + falls through to
                                backend.complete (synth path stays alive)

Entities kwarg parity: passing `entities=[]` is the same as omitting
(default `None` → `()` → empty mask), and passing real entities exercises
the mask. Caller-site PRs (S7 etc.) opt in by passing entities; existing
callers stay unchanged.
"""
from __future__ import annotations

import sqlite3
import json
from typing import List, Tuple

import pytest

from core.reasoning.backends import (
    BackendCapability,
    CompletionResult,
    _clear_for_tests,
    register_backend,
)
from core.reasoning.trace_helpers import trace_synth_call


# ─── Stub backends ─────────────────────────────────────────────────


class _CloudBackend:
    """Records what reached complete + canned reply.

    `tier="large", provider="cloud"` — the capability that
    `force_cloud_enabled()` looks for in trace_synth_call's wrap branch.
    """

    backend_id = "stub_cloud"
    capability = BackendCapability(tier="large", provider="cloud")

    def __init__(self, reply: str = "ok") -> None:
        self.reply = reply
        self.calls: List[Tuple[str, str, dict]] = []

    def complete(self, prompt, *, system="", max_tokens=1024,
                 timeout=60.0, **opts) -> CompletionResult:
        self.calls.append((prompt, system, dict(opts)))
        return CompletionResult(
            text=self.reply, backend_id=self.backend_id,
            model="claude-stub", latency_ms=42, error="",
        )


class _LocalBackend:
    """Local-tier stub. force_cloud=on with this backend resolved
    must NOT wrap (mismatch → fall through)."""

    backend_id = "stub_local"
    capability = BackendCapability(tier="small", provider="local")

    def __init__(self, reply: str = "ok") -> None:
        self.reply = reply
        self.calls: List[Tuple[str, str, dict]] = []

    def complete(self, prompt, *, system="", max_tokens=1024,
                 timeout=60.0, **opts) -> CompletionResult:
        self.calls.append((prompt, system, dict(opts)))
        return CompletionResult(
            text=self.reply, backend_id=self.backend_id,
            model="local-stub", latency_ms=10, error="",
        )


# ─── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def isolate_registry():
    """Each test starts with a clean backend registry to avoid
    cross-test bleed from the autoregistered ollama_local."""
    _clear_for_tests()
    yield
    _clear_for_tests()


def _init_audit_schema(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT, user_role TEXT, endpoint TEXT,
                query TEXT, answer TEXT, graph_paths TEXT,
                blocked INTEGER, security_event TEXT,
                elapsed_sec REAL, ip_address TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def audit_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_audit.db")
    _init_audit_schema(db_path)
    monkeypatch.setattr("core.audit_bridge._DEFAULT_AUDIT_DB", db_path)
    yield db_path


def _read_egress_endpoints(db_path: str) -> List[str]:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            "SELECT endpoint FROM audit_log WHERE endpoint='reason:egress'"
        )
        return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def _read_egress_payloads(db_path: str) -> List[str]:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            "SELECT answer FROM audit_log WHERE endpoint='reason:egress'"
        )
        out = []
        for (packed,) in cur.fetchall():
            blob = json.loads(packed) if packed else {}
            out.append(blob.get("answer", ""))
        return out
    finally:
        conn.close()


# ─── Flag OFF — byte-identical (regression guard) ──────────────────


def test_flag_off_calls_backend_directly_no_egress_row(audit_db, monkeypatch):
    """Default state: JAMES_FORCE_CLOUD unset → trace_synth_call goes
    straight to backend.complete. No reason:egress row, no abstraction
    import overhead."""
    monkeypatch.delenv("JAMES_FORCE_CLOUD", raising=False)
    cloud = _CloudBackend(reply="local-style-answer")
    register_backend("ollama_local", cloud)  # fallback name resolve_backend uses

    out = trace_synth_call("hello", applied_rule="test.rule")

    assert out == "local-style-answer"
    assert len(cloud.calls) == 1
    sent_prompt, _, _ = cloud.calls[0]
    assert sent_prompt == "hello"  # NOT masked
    # No egress audit row
    assert _read_egress_endpoints(audit_db) == []


def test_flag_off_with_entities_kwarg_ignored(audit_db, monkeypatch):
    """Passing entities= when flag is OFF → entities are silently
    ignored (no mask, no audit). Forward-compatible signature; doesn't
    light up until the operator opts in."""
    monkeypatch.delenv("JAMES_FORCE_CLOUD", raising=False)
    cloud = _CloudBackend()
    register_backend("ollama_local", cloud)

    trace_synth_call(
        "김철수가 등장한다",
        applied_rule="test.rule",
        entities=[{"name": "김철수", "entity_type": "person", "sensitive": True}],
    )

    sent_prompt, _, _ = cloud.calls[0]
    assert "김철수" in sent_prompt  # unmasked — flag was off
    assert _read_egress_endpoints(audit_db) == []


# ─── Flag ON + cloud backend → wrapped through run_cloud_egress ────


def test_flag_on_cloud_backend_routes_through_abstraction(audit_db, monkeypatch):
    """JAMES_FORCE_CLOUD=1 + provider='cloud' backend → wrap fires.
    backend.complete still happens (the runner calls it) but the prompt
    has been masked first when entities are supplied, and a
    reason:egress audit row lands."""
    monkeypatch.setenv("JAMES_FORCE_CLOUD", "1")
    monkeypatch.setenv("JAMES_REASONING_BACKEND", "stub_cloud")
    cloud = _CloudBackend(reply="PERSON_1의 보고는 양호")
    register_backend("stub_cloud", cloud)

    out = trace_synth_call(
        "김철수의 보고는?",
        applied_rule="test.rule",
        entities=[{"name": "김철수", "entity_type": "person", "sensitive": True}],
    )

    # backend was called with the MASKED prompt
    assert len(cloud.calls) == 1
    sent_prompt, _, _ = cloud.calls[0]
    assert "김철수" not in sent_prompt
    assert "PERSON_1" in sent_prompt
    # returned text is UNMASKED
    assert out == "김철수의 보고는 양호"
    # audit row exists
    endpoints = _read_egress_endpoints(audit_db)
    assert endpoints == ["reason:egress"]
    payloads = _read_egress_payloads(audit_db)
    assert "backend=stub_cloud" in payloads[0]
    assert "PERSON:1" in payloads[0]  # type histogram


def test_flag_on_cloud_backend_no_entities_mask_is_noop(audit_db, monkeypatch):
    """Flag ON + cloud + no entities (or empty) → wrap still fires (audit
    row lands, backend gets prompt unchanged because empty mask). Proves
    operator can flip the flag and immediately see audit traces even
    before entity wiring lands at call sites."""
    monkeypatch.setenv("JAMES_FORCE_CLOUD", "1")
    monkeypatch.setenv("JAMES_REASONING_BACKEND", "stub_cloud")
    cloud = _CloudBackend(reply="cloud answer")
    register_backend("stub_cloud", cloud)

    out = trace_synth_call("hello", applied_rule="test.rule")

    assert out == "cloud answer"
    # mask was a no-op (empty entities)
    sent_prompt, _, _ = cloud.calls[0]
    assert sent_prompt == "hello"
    # audit row still lands → proves wrap fired
    assert _read_egress_endpoints(audit_db) == ["reason:egress"]


# ─── Flag ON + non-cloud backend → fallthrough + warning ──────────


def test_flag_on_local_backend_falls_through(audit_db, monkeypatch, capsys):
    """JAMES_FORCE_CLOUD=1 with a local backend resolved → log a
    warning + fall through to backend.complete. No abstraction wrap
    (wrapping local would be a confusing no-op). No egress audit row."""
    monkeypatch.setenv("JAMES_FORCE_CLOUD", "1")
    monkeypatch.setenv("JAMES_REASONING_BACKEND", "stub_local")
    local = _LocalBackend(reply="direct local")
    register_backend("stub_local", local)

    out = trace_synth_call("hello", applied_rule="test.rule")

    assert out == "direct local"
    # backend called directly, no mask
    assert len(local.calls) == 1
    sent_prompt, _, _ = local.calls[0]
    assert sent_prompt == "hello"
    # no abstraction audit row
    assert _read_egress_endpoints(audit_db) == []
    # warning printed
    captured = capsys.readouterr()
    assert "FORCE_CLOUD" in captured.out
    assert "stub_local" in captured.out


# ─── Flag ON wrap explosion → graceful fallthrough ─────────────────


def test_flag_on_wrap_failure_falls_through(audit_db, monkeypatch):
    """If anything in the force_cloud wrap path raises (import error,
    capability lookup glitch, runner exception), the synth path stays
    alive — the helper logs + falls through to backend.complete.

    Simulated by monkeypatching `core.abstraction.run_cloud_egress` to
    raise. The user query must still get an answer (the normal backend
    path runs)."""
    monkeypatch.setenv("JAMES_FORCE_CLOUD", "1")
    monkeypatch.setenv("JAMES_REASONING_BACKEND", "stub_cloud")
    cloud = _CloudBackend(reply="fallback reply")
    register_backend("stub_cloud", cloud)

    def boom(*a, **kw):
        raise RuntimeError("abstraction explosion")

    monkeypatch.setattr("core.abstraction.run_cloud_egress", boom)

    out = trace_synth_call("hello", applied_rule="test.rule")

    assert out == "fallback reply"
    # backend called directly (fallthrough path)
    assert len(cloud.calls) == 1


# ─── Self-policing: capability missing → not wrapped ───────────────


class _NoCapBackend:
    """Backend without a capability attribute — `get_backend_capability`
    returns UNKNOWN. Flag ON should fall through (not wrap)."""

    backend_id = "stub_nocap"

    def __init__(self, reply: str = "ok") -> None:
        self.reply = reply
        self.calls: List[Tuple[str, str, dict]] = []

    def complete(self, prompt, *, system="", max_tokens=1024,
                 timeout=60.0, **opts) -> CompletionResult:
        self.calls.append((prompt, system, dict(opts)))
        return CompletionResult(
            text=self.reply, backend_id=self.backend_id, error="",
        )


def test_flag_on_unknown_capability_falls_through(audit_db, monkeypatch, capsys):
    """Backend without capability declared → cap.provider == 'unknown'
    → wrap does NOT fire (only `provider='cloud'` triggers it)."""
    monkeypatch.setenv("JAMES_FORCE_CLOUD", "1")
    monkeypatch.setenv("JAMES_REASONING_BACKEND", "stub_nocap")
    no_cap = _NoCapBackend(reply="direct")
    register_backend("stub_nocap", no_cap)

    out = trace_synth_call("hello", applied_rule="test.rule")

    assert out == "direct"
    assert len(no_cap.calls) == 1
    sent_prompt, _, _ = no_cap.calls[0]
    assert sent_prompt == "hello"
    assert _read_egress_endpoints(audit_db) == []
    captured = capsys.readouterr()
    assert "FORCE_CLOUD" in captured.out
    assert "unknown" in captured.out


# ─── Public function exposed correctly ─────────────────────────────


def test_force_cloud_enabled_public_callable():
    """`force_cloud_enabled` is unprefixed so external callers (planner,
    verify, reflect) can opt in symmetrically once synth proves the
    end-to-end shape."""
    from core.reasoning import router
    assert callable(router.force_cloud_enabled)


def test_force_cloud_enabled_reads_env(monkeypatch):
    from core.reasoning.router import force_cloud_enabled
    monkeypatch.delenv("JAMES_FORCE_CLOUD", raising=False)
    assert force_cloud_enabled() is False
    for truthy in ("1", "true", "yes", "on", "TRUE", "On"):
        monkeypatch.setenv("JAMES_FORCE_CLOUD", truthy)
        assert force_cloud_enabled() is True, f"truthy {truthy!r} not recognized"
    for falsy in ("0", "false", "no", "off", "", "  "):
        monkeypatch.setenv("JAMES_FORCE_CLOUD", falsy)
        assert force_cloud_enabled() is False, f"falsy {falsy!r} not recognized as off"
