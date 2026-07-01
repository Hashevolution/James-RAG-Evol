"""Mode + model routing for ``ReasoningEngine._query_impl``.

Extracted from ``core/reasoning/engine.py`` during the 2026-07-01
module-size split (CLAUDE.md rule #5 — engine.py crossed the 20 KB cap
when the v0.6.1 model_used reporting landed). Behaviour is
byte-identical to the pre-split file; only the location moved.

The function owns the four routing decisions that sat between
``build_memory_context`` and the mode dispatch:

  1. Query-mode resolution — client ``mode_override`` (role-gated) or
     ``QueryRouter`` auto-routing, with the ``force_web_search`` and
     attached-image overrides.
  2. ``selected_model`` validation — the user's picker choice is
     untrusted; anything not in the catalog for the resolved mode is
     rejected (silent fallback to mode default).
  3. Measured-preference auto-routing (v18.7 Phase 2c/3c/wiki_edit-c)
     for chat / retrieval / wiki_edit when no explicit pick was made.
  4. ``engine._last_routed_model`` bookkeeping so ``query()`` can report
     the model that actually answered (v0.6.1).
"""
from __future__ import annotations

from typing import Any, Dict, Tuple


def resolve_mode_and_model(
    engine,
    safe_query: str,
    user_role: str,
    mode_override: str,
    selected_model: str,
    kwargs: Dict[str, Any],
) -> Tuple[str, str]:
    """Resolve (mode, picked_model) for this query.

    ``engine`` is the calling ``ReasoningEngine`` — used for ``_log``
    and the ``_last_routed_model`` marker. ``kwargs`` is the query's
    kwargs dict (read-only here: ``force_web_search`` / ``image_path``).
    """
    # ── Query Router (STEP 0.5a) ─────────────────────────
    # pre_check 통과 후에만 진입. 보안 순서 유지.
    # item #6: mode_override가 있으면 router 건너뛰고 그 모드 사용
    # (클라이언트가 챗 페이지 dropdown으로 명시한 경우). 단,
    # role-allowed 체크는 그대로 적용해서 권한 우회 방지.
    from core.intent_classifier import ROLE_ALLOWED
    VALID_OVERRIDES = {"chat", "retrieval", "meta", "coding",
                       "wiki_edit", "self_evolve", "vision"}
    mode = ""
    override = (mode_override or "").strip().lower()
    if override and override in VALID_OVERRIDES:
        allowed = ROLE_ALLOWED.get(user_role, {"chat", "retrieval"})
        if override in allowed:
            mode = override
            print(f"[ROUTER] mode={mode} (client override) | query='{safe_query[:40]}'")
        else:
            # 권한 없는 모드 override → router 정상 사용
            print(f"[ROUTER] override {override!r} 권한 없음 (role={user_role}) → 자동 라우팅")
            override = ""

    if not override or override not in VALID_OVERRIDES:
        try:
            from core.query_router import QueryRouter
            mode = QueryRouter().route(safe_query, user_role=user_role)
            print(f"[ROUTER] mode={mode} | query='{safe_query[:40]}'")
        except Exception as e:
            engine._log("query_router", e, user_role)
            mode = "retrieval"   # fallback → 기존 Loop

    # ── [Bug fix, 2026-05-09] force_web_search forces retrieval ──
    # The chip click sends force_web_search=True. Only the retrieval
    # pipeline (run_retrieval_pipeline) honors this flag — chat /
    # meta / wiki_edit / etc. silently drop it, which surfaces as:
    # user clicks the "🌐 웹으로 더 조사" chip → server takes the
    # chat path again → memory_context (prior turns including the
    # last inference-only answer) is mixed back into the prompt →
    # new answer looks identical to the previous → user concludes
    # "the search must be based on James's earlier answer".
    #
    # Reality: no web search ran. Force-route to retrieval so the
    # web search actually fires with the original user question.
    if kwargs.get("force_web_search") and mode != "retrieval":
        print(f"[ROUTER] force_web_search=True overrides mode "
              f"{mode!r} → retrieval (web search needs the "
              f"retrieval pipeline)")
        mode = "retrieval"

    # ── Image attached → vision mode (v18.7 vision-wire) ─────
    # An image_path in kwargs forces vision regardless of what the
    # text router produced — the query is *about* the image. Gated
    # by ROLE_ALLOWED so external (chat-only) can't reach it.
    if kwargs.get("image_path") and "vision" in ROLE_ALLOWED.get(
            user_role, {"chat", "retrieval"}):
        print(f"[ROUTER] image attached → mode=vision (was {mode!r})")
        mode = "vision"

    # ── [#A2 phase 2] selected_model validation ────────────
    # The user's secondary-picker choice arrives untrusted. Reject
    # anything not in the catalog for the resolved mode — silent
    # fallback to mode default, never echo arbitrary tags to Ollama.
    from core.model_catalog import resolve_model
    picked_model = resolve_model(mode, (selected_model or "").strip()) or ""
    if selected_model and not picked_model:
        print(f"[MODEL] '{selected_model}' rejected for mode={mode} → mode default")
    elif picked_model:
        print(f"[MODEL] mode={mode} using user-selected '{picked_model}'")

    # ── v18.7 Phase 2c/3c/wiki_edit-c — measured-preference routing ──
    # When the user did NOT pick a model, these modes auto-route via
    # resolve_for_mode(mode, requested="") to the preference-list top
    # (requested="" bypasses config.GEMMA_MODEL). All three are
    # measurement-backed → gemma3:12b; see docs/reference/
    # routing-matrix.md for the per-mode QDC + ranking. Kill-switch
    # JAMES_DISABLE_MODE_AWARE_ROUTING=1 reverts all to GEMMA_MODEL.
    # meta/self_evolve stay legacy; vision resolves its own
    # single-candidate model inside handle_vision (no text catalog).
    if mode in ("chat", "retrieval", "wiki_edit") and not picked_model:
        import os
        if not os.environ.get("JAMES_DISABLE_MODE_AWARE_ROUTING"):
            from core.model_resolver import resolve_for_mode
            _rm = resolve_for_mode(mode, requested="")
            if _rm.tag:
                picked_model = _rm.tag
                print(f"[MODEL] mode={mode} auto-routed → '{_rm.tag}' "
                      f"(source={_rm.source}; measured pref)")
                if _rm.warning:
                    print(f"[MODEL] {_rm.warning}")

    # v0.6.1 — remember the model actually chosen for this query so
    # query() can report it. picked_model holds the user pick OR the
    # auto-routed tag; fall back to the legacy default for the LLM
    # modes when neither applied, so the header is right in the common
    # cases (coding resolves CODING_MODEL downstream; meta uses no LLM).
    _eff_model = picked_model
    if not _eff_model and mode in ("chat", "retrieval", "wiki_edit"):
        try:
            from config import GEMMA_MODEL as _GM
            _eff_model = _GM
        except Exception:
            _eff_model = ""
    engine._last_routed_model = _eff_model or ""

    return mode, picked_model


__all__ = ["resolve_mode_and_model"]
