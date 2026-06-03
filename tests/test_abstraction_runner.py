"""§5.7.13 runner — `run_cloud_egress` orchestrator tests.

Covers the runner-side contract:
  • happy path: mask → call → unmask → audit, returns restored text
  • caller obligation #3: `flagged` returned alongside, never stripped
  • caller obligation #2: one `reason:egress` audit row per run
  • caller obligation #4 (runner-side): keep_local name in prompt
    → REFUSED egress (cloud not called), audit row records refusal
  • backend error → unmask skipped, audit row records the error
  • system prompt is also masked (names there leak just as readily)
  • masked prompt is what reaches the backend (real names never sent)
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, List, Tuple

import pytest

from core.abstraction import (
    Decision,
    default_decider,
    run_cloud_egress,
)
from core.reasoning.backends import (
    BackendCapability,
    CompletionResult,
)


# ─── Stub backends ──────────────────────────────────────────────────


class _CaptureBackend:
    """Records what reached `complete` and returns a canned reply.

    Capture is necessary to prove §5.7.12 invariant: real entity names
    must NEVER reach the backend on the cloud route. A real-world cloud
    backend can't be inspected this way; the stub is the test surrogate.
    """

    backend_id = "stub_cloud"
    capability = BackendCapability(tier="large", provider="cloud")

    def __init__(self, reply_text: str = "ok", reply_error: str = "") -> None:
        self.reply_text = reply_text
        self.reply_error = reply_error
        self.calls: List[Tuple[str, str, dict]] = []

    def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        max_tokens: int = 1024,
        timeout: float = 60.0,
        **opts: Any,
    ) -> CompletionResult:
        self.calls.append((prompt, system, dict(opts)))
        return CompletionResult(
            text=self.reply_text,
            backend_id=self.backend_id,
            model="claude-stub",
            latency_ms=42,
            error=self.reply_error,
        )


# ─── Audit DB harness ──────────────────────────────────────────────


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


def _read_egress_rows(db_path: str) -> List[Tuple[str, str, str]]:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(
            "SELECT endpoint, answer FROM audit_log "
            "WHERE endpoint='reason:egress'"
        )
        out: List[Tuple[str, str, str]] = []
        for endpoint, packed in cur.fetchall():
            blob = json.loads(packed) if packed else {}
            out.append((endpoint, blob.get("query", ""), blob.get("answer", "")))
        return out
    finally:
        conn.close()


@pytest.fixture
def audit_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_audit.db")
    _init_audit_schema(db_path)
    monkeypatch.setattr("core.audit_bridge._DEFAULT_AUDIT_DB", db_path)
    yield db_path


# ─── Happy path ────────────────────────────────────────────────────


def test_happy_path_masks_calls_unmasks(audit_db):
    """Org-chart end-to-end: real names are masked before backend.complete,
    cloud reply (placeholders) is unmasked, restored text comes back."""
    entities = [
        {"name": "김철수", "entity_type": "person", "sensitive": True},
        {"name": "이영희", "entity_type": "person", "sensitive": True},
    ]
    prompt = "김철수와 이영희의 보고관계는?"
    backend = _CaptureBackend(reply_text="PERSON_1이 PERSON_2의 상사다.")

    result, flagged = run_cloud_egress(
        backend=backend,
        prompt=prompt,
        entities=entities,
        decider=default_decider(),
        stage="synth",
    )

    # 1. backend received the MASKED prompt — no real names
    assert len(backend.calls) == 1
    sent_prompt, sent_system, _ = backend.calls[0]
    assert "김철수" not in sent_prompt
    assert "이영희" not in sent_prompt
    assert "PERSON_1" in sent_prompt
    assert "PERSON_2" in sent_prompt

    # 2. result.text is UNMASKED — placeholders back to real names
    assert result.text == "김철수이 이영희의 상사다."
    assert result.backend_id == "stub_cloud"
    assert result.error == ""

    # 3. no hallucinated placeholders
    assert flagged == []

    # 4. one audit row landed
    rows = _read_egress_rows(audit_db)
    assert len(rows) == 1
    _, query, answer = rows[0]
    assert query == "synth"
    assert "backend=stub_cloud" in answer
    assert "PERSON:2" in answer  # type histogram


def test_system_prompt_also_masked(audit_db):
    """Names in `system` text are just as leaky as names in `prompt`.
    The runner must mask both."""
    entities = [
        {"name": "김철수", "entity_type": "person", "sensitive": True},
    ]
    backend = _CaptureBackend(reply_text="ok")

    run_cloud_egress(
        backend=backend,
        prompt="요약해줘",
        entities=entities,
        decider=default_decider(),
        system="당신은 김철수의 비서입니다.",
    )

    sent_prompt, sent_system, _ = backend.calls[0]
    assert "김철수" not in sent_system
    assert "PERSON_1" in sent_system


def test_passthrough_entities_appear_real_in_prompt(audit_db):
    """Non-sensitive entities (PASS) are sent as-is — by design."""
    entities = [
        {"name": "삼성전자", "entity_type": "org", "sensitive": False},
        {"name": "김철수", "entity_type": "person", "sensitive": True},
    ]
    backend = _CaptureBackend(reply_text="ok")

    run_cloud_egress(
        backend=backend,
        prompt="김철수는 삼성전자 직원이다",
        entities=entities,
        decider=default_decider(),
    )

    sent_prompt, _, _ = backend.calls[0]
    # 삼성전자 passes through
    assert "삼성전자" in sent_prompt
    # 김철수 is masked
    assert "김철수" not in sent_prompt
    assert "PERSON_1" in sent_prompt


# ─── Caller obligation #3: flagged returned, never stripped ─────────


def test_hallucinated_placeholder_in_reply_surfaced(audit_db):
    """Cloud invents PERSON_9 (not in map). Runner returns it in
    `flagged`; the restored text still contains the verbatim token
    (never silently de-abstracted — §5.7.13 invariant #4)."""
    entities = [
        {"name": "김철수", "entity_type": "person", "sensitive": True},
    ]
    backend = _CaptureBackend(reply_text="PERSON_1과 PERSON_9이 협력한다")

    result, flagged = run_cloud_egress(
        backend=backend,
        prompt="협업관계?",
        entities=entities,
        decider=default_decider(),
    )

    assert flagged == ["PERSON_9"]
    # PERSON_9 stays verbatim in the answer — operator surface, not silently dropped
    assert "PERSON_9" in result.text
    assert "김철수" in result.text  # real placeholder restored normally

    # audit row records the flagged token
    rows = _read_egress_rows(audit_db)
    assert len(rows) == 1
    _, _, answer = rows[0]
    assert "flagged=PERSON_9" in answer


# ─── Caller obligation #4 (runner-side): keep_local refusal ─────────


def test_keep_local_name_in_prompt_refuses_egress(audit_db):
    """Open-world sensitive entity name in the prompt → REFUSED egress.
    The cloud backend is NEVER called. Audit row records the refusal."""
    entities = [
        {"name": "와파린", "entity_type": "concept", "sensitive": True},
    ]
    backend = _CaptureBackend(reply_text="should never be called")
    decider = default_decider(open_world_types=["concept"])

    result, flagged = run_cloud_egress(
        backend=backend,
        prompt="와파린과 아스피린 병용은 안전한가?",
        entities=entities,
        decider=decider,
    )

    # backend NOT called
    assert len(backend.calls) == 0
    # explicit error reason
    assert result.text == ""
    assert "refused: keep_local" in result.error
    assert "와파린" in result.error
    assert flagged == []

    # audit row records the refusal (not a clean egress)
    rows = _read_egress_rows(audit_db)
    assert len(rows) == 1
    _, _, answer = rows[0]
    assert "refused_keep_local_in_prompt:와파린" in answer


def test_keep_local_name_in_system_refuses_egress(audit_db):
    """Same defense applies to the `system` text."""
    entities = [
        {"name": "와파린", "entity_type": "concept", "sensitive": True},
    ]
    backend = _CaptureBackend(reply_text="x")
    decider = default_decider(open_world_types=["concept"])

    result, _ = run_cloud_egress(
        backend=backend,
        prompt="약물 상호작용 일반론",
        entities=entities,
        decider=decider,
        system="당신은 와파린 전문가입니다.",
    )

    assert len(backend.calls) == 0
    assert "refused: keep_local" in result.error


def test_keep_local_not_in_prompt_proceeds(audit_db):
    """KEEP_LOCAL entity whose name is NOT in the prompt → egress
    proceeds (the safety check is about what's about to leak, not about
    the entity being mentioned)."""
    entities = [
        {"name": "와파린", "entity_type": "concept", "sensitive": True},
        {"name": "환자김", "entity_type": "person", "sensitive": True},
    ]
    backend = _CaptureBackend(reply_text="PERSON_1의 상태는 안정적")
    decider = default_decider(open_world_types=["concept"])

    # 와파린 not in prompt — only 환자김 (which is MASK)
    result, _ = run_cloud_egress(
        backend=backend,
        prompt="환자김의 차트 요약",
        entities=entities,
        decider=decider,
    )

    assert len(backend.calls) == 1
    sent_prompt, _, _ = backend.calls[0]
    assert "환자김" not in sent_prompt
    assert "PERSON_1" in sent_prompt
    assert result.text == "환자김의 상태는 안정적"


# ─── Backend error handling ─────────────────────────────────────────


def test_backend_error_returns_as_is_no_unmask(audit_db):
    """Backend reported `error` with empty text → runner returns the
    error CompletionResult and skips unmask. Audit row records the
    backend error in the reason field (egress did happen — we sent
    the masked prompt — but the cloud didn't reply cleanly)."""
    entities = [
        {"name": "김철수", "entity_type": "person", "sensitive": True},
    ]
    backend = _CaptureBackend(reply_text="", reply_error="timeout")

    result, flagged = run_cloud_egress(
        backend=backend,
        prompt="질문",
        entities=entities,
        decider=default_decider(),
    )

    assert result.text == ""
    assert result.error == "timeout"
    assert flagged == []

    rows = _read_egress_rows(audit_db)
    assert len(rows) == 1
    _, _, answer = rows[0]
    assert "backend_error:timeout" in answer


def test_backend_text_with_nonempty_error_still_unmasked(audit_db):
    """If backend returns BOTH text and a non-fatal error (output
    truncated, etc.), the text path still runs — unmask + audit happen
    normally. The runner preserves the error code on the returned
    CompletionResult."""
    entities = [
        {"name": "김철수", "entity_type": "person", "sensitive": True},
    ]
    backend = _CaptureBackend(reply_text="PERSON_1...", reply_error="output truncated")

    result, _ = run_cloud_egress(
        backend=backend,
        prompt="질문",
        entities=entities,
        decider=default_decider(),
    )

    assert result.text == "김철수..."
    assert result.error == "output truncated"


# ─── Egress safety: real names never reach the backend ──────────────


def test_real_names_never_reach_backend_for_sensitive_entities(audit_db):
    """The §5.7.12 boundary: every sensitive entity name in the prompt
    text MUST be masked by the time backend.complete is called.
    Iterate the catalog of MASK-class entity names + sweep the call
    surface to prove the boundary."""
    sensitive = [
        {"name": "김철수", "entity_type": "person", "sensitive": True},
        {"name": "이영희", "entity_type": "person", "sensitive": True},
        {"name": "삼성전자", "entity_type": "org", "sensitive": True},
        {"name": "30억", "entity_type": "quantity", "sensitive": True},
    ]
    backend = _CaptureBackend(reply_text="reply")

    run_cloud_egress(
        backend=backend,
        prompt="김철수는 삼성전자에서 30억을 받았고, 이영희에게 보고한다.",
        entities=sensitive,
        decider=default_decider(),
    )

    sent_prompt, sent_system, _ = backend.calls[0]
    for sensitive_name in ("김철수", "이영희", "삼성전자", "30억"):
        assert sensitive_name not in sent_prompt, (
            f"{sensitive_name!r} leaked into backend prompt"
        )
        assert sensitive_name not in sent_system, (
            f"{sensitive_name!r} leaked into backend system text"
        )


def test_no_entities_passes_prompt_unchanged(audit_db):
    """Edge: empty entity list → empty map → prompt unchanged. Still
    emits an audit row (egress happened, mask was a no-op)."""
    backend = _CaptureBackend(reply_text="reply")

    result, flagged = run_cloud_egress(
        backend=backend,
        prompt="hello world",
        entities=[],
        decider=default_decider(),
    )

    sent_prompt, _, _ = backend.calls[0]
    assert sent_prompt == "hello world"
    assert result.text == "reply"
    assert flagged == []

    rows = _read_egress_rows(audit_db)
    assert len(rows) == 1


def test_opts_pass_through_to_backend(audit_db):
    """Backend kwargs (model, temperature, custom opts) are forwarded.
    The runner is a transparent wrapper on the call surface."""
    backend = _CaptureBackend(reply_text="x")

    run_cloud_egress(
        backend=backend,
        prompt="p",
        entities=[],
        decider=default_decider(),
        model="claude-sonnet-4-6",
        temperature=0.7,
        use_cache=False,
    )

    _, _, opts = backend.calls[0]
    assert opts.get("model") == "claude-sonnet-4-6"
    assert opts.get("temperature") == 0.7
    assert opts.get("use_cache") is False
