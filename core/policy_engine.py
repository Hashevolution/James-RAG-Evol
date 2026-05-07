"""PolicyEngine — single source of role/sensitivity decisions (#44, Axis 4 phase 1).

Phase 1 scope: skeleton only. Every decision method delegates to the
existing `core/security_layer.py` primitives, preserving behavior bit for
bit. Subsequent migration PRs will:

  Phase 2 — move call sites off direct `check_access` imports onto
            `PolicyEngine.can_retrieve / can_walk / can_emit` (one PR per
            consumer: retrieval, graph, output).
  Phase 3 — sandbox migration to capability tokens (`can_call_tool`).
  Phase 4 — multimodal extractor outputs wrapped in `TrustedContent`.

After all four phases, direct `check_access` imports outside of
`security_layer.py` (the implementation backend) and `policy_engine.py`
(this file) become a regression — the v0.2 ROADMAP Axis 4 "done when"
criterion in the issue says removing this file should break ≥ 4 modules
on import.

Design notes:
  - `Decision` is frozen + carries `applied_rule` for audit-log correlation.
  - Methods take primitives (role + dict), no engine state. Trivially
    mockable in tests, stateless in production.
  - `can_call_tool` is intentionally restrictive in phase 1 (admin-only)
    until the capability-token model lands. Existing `tools/router.py`
    admin gates remain authoritative — call sites MAY bypass this method
    during phases 1-2.
  - `TrustedContent` is defined now so its identity stays stable across
    the migration PRs that will start returning it from extractors.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class Decision:
    """Result of a policy check.

    Attributes:
      allowed: binary verdict.
      reason: short human-readable string for logs / operator UI.
      applied_rule: canonical rule id for audit-log correlation,
                    e.g. "policy.retrieve.abac" or "policy.tool.admin_only".
    """
    allowed: bool
    reason: str
    applied_rule: str


@dataclass(frozen=True)
class TrustedContent:
    """Wrapper for content with a known provenance + trust level.

    Phase 4 of #44: every multimodal extractor returns one of these
    instead of a raw string. The reasoning pipeline then runs
    `extract_data_only()` against `low`-trust content before joining it
    into the LLM context.
    """
    text:   str
    source: str    # "user" | "doc" | "ocr" | "asr" | "vision" | "web"
    trust:  str    # "high" | "medium" | "low"


@dataclass(frozen=True)
class Capability:
    """Short-lived authorization token issued by PolicyEngine.

    Phase 3 of #44 — replaces ad-hoc string allowlists in
    `tools/code/sandbox.py` and `tools/router.py` with capability tokens
    carrying an explicit (role, action, scope, ttl) tuple.

    Tokens are in-process only; cryptographic signing/binding is out of
    scope per #44 (deferred to v1.0 hardening). The `token_id` exists
    for audit-log correlation, not authentication.
    """
    role:       str    # caller role at issue time, e.g. "admin"
    action:     str    # e.g. "fs.read", "fs.write", "shell.exec"
    scope:      str    # path-prefix scope, or "*" for unbounded
    issued_at:  float  # time.time() at issue
    expires_at: float  # issued_at + ttl_seconds
    token_id:   str    # uuid4 hex; goes in audit logs

    def is_expired(self, now: Optional[float] = None) -> bool:
        """True if `now` (default: time.time()) is at-or-past expiry."""
        return (now if now is not None else time.time()) >= self.expires_at


def _scope_contains(cap_scope: str, requested: str) -> bool:
    """True if a capability with `cap_scope` covers a `requested` path.

    Rules (phase 3 — deliberately simple, structured globs deferred):
      - "*" covers anything.
      - exact string match covers itself.
      - `cap_scope` ending in "/" (or normalized to) is a directory
        prefix; `requested` must start with that prefix to match.

    Trailing-slash normalization avoids the `./workspace` vs
    `./workspaceextra` partial-match bug.
    """
    if cap_scope == "*":
        return True
    if cap_scope == requested:
        return True
    cap_norm = cap_scope if cap_scope.endswith(("/", "\\")) else cap_scope + "/"
    return requested.startswith(cap_norm)


class PolicyEngine:
    """Single point of role/sensitivity policy decisions.

    Phase 1: every method delegates to `core.security_layer` functions,
    preserving exact existing behavior. The intent of this PR is the
    *call-site contract* — future policy changes should touch one file
    instead of the whole codebase.
    """

    def can_retrieve(self, role: str, doc_meta: Dict[str, Any]) -> Decision:
        """Vector retrieval: may this role see this document?

        Delegates to `security_layer.check_access(role, meta)`. The
        sensitivity field is read from `doc_meta.sensitivity` (default
        "public") and compared against `ROLE_LEVEL[role]`.
        """
        from core.security_layer import check_access
        ok = bool(check_access(role, doc_meta or {}))
        return Decision(
            allowed=ok,
            reason="abac.role_ge_sensitivity" if ok else "abac.role_lt_sensitivity",
            applied_rule="policy.retrieve.abac",
        )

    def can_walk(self, role: str, entity: Dict[str, Any]) -> Decision:
        """Graph DFS: may this role traverse to this entity?

        Same ABAC primitive as `can_retrieve`. Kept as a separate method
        because phase-2 graph migration will likely add traversal-depth
        and relation-type guards distinct from retrieval policy.
        """
        from core.security_layer import check_access
        ok = bool(check_access(role, entity or {}))
        return Decision(
            allowed=ok,
            reason="abac.role_ge_sensitivity" if ok else "abac.role_lt_sensitivity",
            applied_rule="policy.walk.abac",
        )

    def can_call_tool(
        self,
        role:  str,
        tool:  str,
        args:  Optional[Dict[str, Any]] = None,
    ) -> Decision:
        """Tool execution: may this role invoke this tool with these args?

        Phase 1/3-1: admin-only — preserved bit-for-bit so the
        `issue_capability()` issuance gate keeps the same surface as the
        legacy `tools/router.py::execute_tool` admin gate. Per-action
        relaxation (e.g. fs.read for employees) is deferred to phase 3-2
        when router migrates onto this method; today no production caller
        depends on it.

        Args:
          role:  caller role.
          tool:  tool name (e.g. "read_file", "execute_command", or
                 capability-action like "fs.write").
          args:  reserved for capability-token scope match in phase 3-2+
                 (currently ignored).
        """
        ok = (role == "admin")
        return Decision(
            allowed=ok,
            reason="role.is_admin" if ok else "role.not_admin",
            applied_rule="policy.tool.admin_only",
        )

    def issue_capability(
        self,
        role:        str,
        action:      str,
        scope:       str,
        ttl_seconds: int = 60,
    ) -> Optional[Capability]:
        """Issue a short-lived capability for a (role, action, scope) request.

        Phase 3 of #44 — the issuance gate is `can_call_tool(role, action)`.
        If the policy denies issuance, returns None and the caller MUST
        treat that as a hard refusal (do not fall back to legacy gates).

        Phase 3-1: routers/sandboxes do not yet require capability tokens —
        the existing admin/path checks remain authoritative. This method
        exists so phase 3-2 can flip the contract atomically.

        Args:
          role:         caller role.
          action:       canonical action id (e.g. "fs.read", "fs.write",
                        "shell.exec"). Free-form for now; phase 3-2 may
                        formalize the namespace.
          scope:        path-prefix or "*"; see `_scope_contains`.
          ttl_seconds:  token lifetime; default 60s matches issue
                        recommendation in #44.

        Returns:
          A `Capability` on success, or None if issuance is denied.
        """
        if ttl_seconds <= 0:
            return None
        decision = self.can_call_tool(role, action, args={"scope": scope})
        if not decision.allowed:
            return None
        now = time.time()
        return Capability(
            role=role,
            action=action,
            scope=scope,
            issued_at=now,
            expires_at=now + ttl_seconds,
            token_id=uuid.uuid4().hex,
        )

    def verify_capability(
        self,
        cap:    Optional[Capability],
        action: str,
        scope:  str,
        now:    Optional[float] = None,
    ) -> Decision:
        """Verify `cap` authorizes `(action, scope)` and is not expired.

        Phase 3 of #44 — sandbox/router will call this immediately before
        executing a privileged action. `now` is injectable for tests.

        Decision rules (in order):
          1. `cap is None`              → missing
          2. expired                    → expired
          3. action mismatch            → action_mismatch
          4. scope not contained        → scope_out_of_bounds
          5. otherwise                  → allowed
        """
        if cap is None:
            return Decision(
                allowed=False,
                reason="capability.missing",
                applied_rule="policy.cap.missing",
            )
        if cap.is_expired(now):
            return Decision(
                allowed=False,
                reason="capability.expired",
                applied_rule="policy.cap.expired",
            )
        if cap.action != action:
            return Decision(
                allowed=False,
                reason=f"capability.action_mismatch[{cap.action}!={action}]",
                applied_rule="policy.cap.action_mismatch",
            )
        if not _scope_contains(cap.scope, scope):
            return Decision(
                allowed=False,
                reason=f"capability.scope_out_of_bounds[{scope} not in {cap.scope}]",
                applied_rule="policy.cap.scope_mismatch",
            )
        return Decision(
            allowed=True,
            reason="capability.valid",
            applied_rule="policy.cap.allow",
        )

    def can_emit(self, role: str, content: str) -> Decision:
        """Output gate: may this role receive this content?

        Phase 1: always allow. `security_layer.filter_answer_by_role()`
        already mutates content per role (PII masking, person-name
        redaction); the binary emit/no-emit decision is therefore a
        no-op today. Phase 2+ may promote real secret/keyword leak
        post-checks into this method.
        """
        return Decision(
            allowed=True,
            reason="policy.emit.always_allow_v1",
            applied_rule="policy.emit.passthrough",
        )


# Module-level convenience singleton.
# Phase-2 migration: call sites prefer `from core.policy_engine import default_engine`
# over instantiating their own. The engine is stateless, so a singleton is fine.
default_engine = PolicyEngine()
