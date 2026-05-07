"""PolicyEngine — single source of role/sensitivity decisions (#44, Axis 4 phase 1).

Phase 1 scope: skeleton only. Every decision method delegates to the
existing `core/security_layer.py` primitives, preserving behavior bit for
bit. Subsequent migration PRs will:

  Phase 2 — move call sites off direct `check_access` imports onto
            `PolicyEngine.can_retrieve / can_walk / can_emit` (one PR per
            consumer: retrieval, graph, output).
  Phase 3 — sandbox migration to capability tokens (`can_call_tool`).
  Phase 4 — multimodal extractor outputs wrapped in `TrustedContent`,
            funneled through `quarantine()` before joining LLM context.

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

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


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

        Phase 1: admin-only. The capability-token model arrives in the
        sandbox migration PR (#44 phase 3). Until then, callers may
        bypass this method; the existing admin checks in
        `tools/router.py::execute_tool` and `tools/code/sandbox.py`
        remain authoritative.

        Args:
          role:  caller role.
          tool:  tool name (e.g. "read_file", "execute_command").
          args:  reserved for capability-token scope match in phase 3
                 (currently ignored).
        """
        ok = (role == "admin")
        return Decision(
            allowed=ok,
            reason="role.is_admin" if ok else "role.not_admin",
            applied_rule="policy.tool.admin_only",
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

    def quarantine(self, content: TrustedContent) -> Tuple[str, Decision]:
        """[#44 phase 4] Single chokepoint for content entering LLM context.

        Low-trust sources (web search results, OCR text, ASR transcripts,
        vision captions) carry adversarial risk: a poisoned page or image
        can embed prompt-injection strings ("ignore previous instructions
        and ...") that piggyback on the requester's role. The reasoning
        pipeline must funnel every such string through this method
        before joining it into the LLM context.

        Behavior:
          - trust == "low":   route through `extract_data_only()`, which
                              neutralizes injection patterns in place.
                              Returns the cleaned text + a Decision whose
                              reason carries `modified={bool}` for audit
                              correlation.
          - trust == "medium" / "high": pass through unchanged. The
                              "user" source (direct query) is the canonical
                              high-trust case; "doc" (internal corpus) is
                              already sanitized at ingestion via
                              `sanitize_document_content`.

        Returns:
          (sanitized_text, decision). Always allowed in phase 4 — the
          method is a sanitization chokepoint, not a deny gate. Future
          phases may escalate to deny on critical patterns.
        """
        if content.trust == "low":
            from core.security_layer import extract_data_only
            clean, modified = extract_data_only(content.text)
            return clean, Decision(
                allowed=True,
                reason=f"quarantine.low_trust.modified={modified}",
                applied_rule="policy.quarantine.low_trust",
            )

        return content.text, Decision(
            allowed=True,
            reason=f"quarantine.passthrough.trust_{content.trust}",
            applied_rule="policy.quarantine.passthrough",
        )


# Module-level convenience singleton.
# Phase-2 migration: call sites prefer `from core.policy_engine import default_engine`
# over instantiating their own. The engine is stateless, so a singleton is fine.
default_engine = PolicyEngine()
