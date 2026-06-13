"""``generate_answer`` — the post-context synth orchestrator.

Extracted from the legacy single-file ``core/reasoning/pipeline_synth.py``
during the v0.6 oversize-module split (CLAUDE.md rule #5). Behaviour
is byte-identical to the pre-split file; only the location moved.

The low-relevance branch (web search + fallback prompt), canonical
RAG (engine._generate_answer), the "no info" retry, the optional
reflection pass, and the optional verification pass — all four
phases of the synth flow live here. Trace wraps on the call_gemma
sites are preserved verbatim (same audit_log rows for the same
queries).
"""
from __future__ import annotations

import os
import time

from core.observability import log_stage
from core.reasoning.trace_helpers import trace_synth_call

from core.reasoning.pipeline_synth.result import AnswerBlock
from core.reasoning.pipeline_synth.softener import (
    _abstention_triggers,
    _build_retry_prompt,
)


def generate_answer(
    engine,
    safe_query: str,
    safe_context: str,
    system_prompt: str,
    user_role: str,
    unified_score: float,
    *,
    response_style: str = "",
    selected_model: str = "",
    force_web_search: bool = False,
) -> AnswerBlock:
    """The post-context synth path: low-relevance branch (web search +
    fallback prompt) or canonical RAG (engine._generate_answer), plus
    the "no info" retry. Emits 1-3 trace rows via trace_synth_call.

    Total of three LLM call sites preserved (L1 wraps intact):
      - reasoning.synth.web_summary
      - reasoning.synth.web_fallback
      - reasoning.synth.retry_no_info
    plus reasoning.synth.rag inside engine._generate_answer.
    """
    t_llm = time.time()
    out = AnswerBlock()
    answer = ""

    # Phase 2 PR-7 — optional planner decomposition.
    # When JAMES_ENABLE_PLANNER=1, decompose the query into 2-5
    # subtasks and prepend them to the system_prompt so the LLM
    # follows the plan. MVP scope is "처음엔 단순 표시" — the plan
    # informs synth phrasing, but does NOT yet drive retrieval / tool
    # routing (future PR-7 follow-up). Trivial plans (1 subtask) are
    # skipped to avoid prompt noise.
    #
    # 2026-06-05 §24 — terse mode skip. The plan prepend includes a
    # Korean directive ("위 계획에 따라 단계별로 답변하라" = "answer
    # step-by-step following the plan above") which structurally forces
    # the model to open with `### Step 1:`, `### 1. Analysis`, `Hello,
    # I am JAMES. I will follow the plan step-by-step`. PM-15 confirmed
    # this is the source of 23/28 unstrippable meta-mode answers under
    # cap=8000 (the "synth draft (c2)" branch of the reflect-revise
    # finding). For terse mode (single-answer measurement / UX) the
    # plan directive is structurally incompatible with the format
    # contract ("ANSWER: <one line>") — skip the prepend.
    # Non-terse paths preserve byte-identical behavior.
    try:
        from core.response_style import resolve_style as _resolve_style
        _style_is_terse = _resolve_style(response_style).name == "terse"
    except Exception:
        _style_is_terse = False
    if not _style_is_terse:
        try:
            from core.reasoning.planner import get_planner
            _plan = get_planner().plan(safe_query, user_role=user_role)
            if _plan and not _plan.is_trivial():
                _steps = "\n".join(
                    f"{i + 1}. {s}" for i, s in enumerate(_plan.subtasks)
                )
                system_prompt = (
                    f"[추론 계획]\n{_steps}\n\n위 계획에 따라 단계별로 답변하라.\n\n"
                    + system_prompt
                )
        except Exception as e:
            engine._log("planner", e, user_role)

    try:
        sys_prefix = f"{system_prompt}\n\n" if system_prompt else ""

        # [P7] retrieval 결과 품질에 따라 분기
        # [#A6-1 2026-05-08] threshold + role gate 동적 로드
        # [#A8-6 2026-05-09] force_web_search=True면 threshold 무시하고
        # 무조건 low_relevance 분기 진입 → 웹 검색 시도. 사용자가 chat
        # bubble의 "🌐 웹으로 더 조사" chip 클릭 시 True로 도착.
        from core.web_search_config import get_threshold, is_role_allowed
        low_relevance = (
            force_web_search
            or not safe_context
            or len(safe_context.strip()) < 50
            or unified_score < get_threshold()
        )

        if low_relevance:
            # ── [3-E 경로 A] 내부 자료 없음 → 웹 검색 시도 ──
            web_context = ""
            try:
                from tools.web.web_searcher import (
                    search_web, format_search_results,
                    record_search, update_knowledge_level,
                )
                # [#A6-1] admin-only hardcode → role allowlist (settings).
                if is_role_allowed(user_role):
                    print(f"[WEB] 내부 자료 부족 → 웹 검색: {safe_query[:40]}")
                    out.web_results = search_web(safe_query, max_results=4)
                    if out.web_results:
                        web_context = format_search_results(out.web_results)
                        search_count = record_search(safe_query)

                        # 단기 지식 레벨 +2
                        update_knowledge_level(safe_query, is_longterm=False)

                        # [#A8-7 2026-05-09] 모든 웹 검색 결과에 대해 proposal
                        # 생성 (이전에는 search_count ≥ 2 또는 명시 저장 명령
                        # 시에만). chat 페이지의 "📥 위키 저장" chip이 첫 검색
                        # 부터 즉시 사용 가능해야 하므로. should_promote /
                        # is_save_command가 true면 자동 임포턴스 표시 정도로
                        # 확장 가능하지만 현재 단순화 — admin이 chat 또는
                        # admin 페이지에서 명시 승인.
                        always_propose = True   # [#A8-7] 항상 만들기
                        if always_propose:
                            try:
                                summary_prompt = (
                                    f"아래 검색 결과를 한국어로 200자 이내 핵심 요약:\n"
                                    f"{web_context[:1000]}\n\n요약:"
                                )
                                # L1 wiring — one audit row per LLM round-trip
                                summary = trace_synth_call(
                                    summary_prompt,
                                    applied_rule="reasoning.synth.web_summary",
                                    user_role=user_role,
                                    timeout=30,
                                    use_cache=False,
                                    max_tokens=300,
                                )
                                if summary:
                                    from tools.self.evo_analyzer import (
                                        _make_proposal, save_proposal,
                                    )
                                    p = _make_proposal(
                                        prop_type   = "web_longterm_save",
                                        title       = f"[웹→Wiki] 장기 저장: {safe_query[:40]}",
                                        description = (
                                            f"웹 검색 누적 {search_count}회 (≥2 또는 명시 저장 요청). "
                                            f"승인 시 검색 결과를 wiki entity로 영구 저장 + vector "
                                            f"인덱싱. 거절하면 단기 저장만 유지."
                                        ),
                                        content     = (
                                            f"[요약]\n{summary}\n\n"
                                            f"[출처 ({len(out.web_results)}건)]\n"
                                            + "\n".join(
                                                f"- {r.get('title','')[:60]} ({r.get('url','')})"
                                                for r in out.web_results[:5]
                                            )
                                        ),
                                        metadata    = {
                                            "auto_action":  "web_longterm_save",
                                            "query":        safe_query,
                                            "summary":      summary,
                                            "web_results":  out.web_results,
                                            "user_role":    user_role,
                                            "search_count": search_count,
                                        },
                                    )
                                    save_proposal(p)
                                    out.pending_save_proposal_id = p['proposal_id']
                                    print(f"[WEB→WIKI] admin confirm proposal 생성: {p['proposal_id']}")
                            except Exception as we:
                                print(f"[WEB→WIKI] proposal 생성 실패: {we}")
            except Exception as we:
                print(f"[WEB] 검색 모듈 오류: {we}")

            # 웹 검색 결과 있으면 컨텍스트에 포함
            # #44 phase 4: web 결과는 low-trust → PolicyEngine.quarantine 통과
            # ("ignore previous instructions" 류 injection 패턴 중립화).
            # safe_context 는 이미 retrieval/graph 단계의 ABAC + 문서 ingestion 시
            # sanitize_document_content() 를 거친 high-trust 영역이므로 추가 처리 없음.
            if web_context:
                from core.policy_engine import default_engine, TrustedContent
                web_clean, _ = default_engine.quarantine(
                    TrustedContent(text=web_context, source="web", trust="low")
                )
                combined_context = web_clean + "\n\n" + safe_context
            else:
                combined_context = safe_context
            from core.response_style import resolve_style as _resolve_style
            _style = _resolve_style(response_style)
            # Pick the right-language flow guide for the no-context
            # web-fallback prompt below. Same heuristic as engine + chat.
            _korean = sum(1 for c in safe_query if "가" <= c <= "힣")
            _is_ko = _korean >= max(1, len(safe_query) * 0.2)
            _rule = _style.rule_text_ko if _is_ko else _style.rule_text_en
            # Two-arm decision: no internal context → direct LLM with the
            # web-fallback prompt; otherwise the canonical RAG path via
            # _generate_answer (which itself emits a trace row).
            if not combined_context.strip():
                _web_fallback_prompt = (
                    f"{sys_prefix}"
                    f"{'[웹 검색 결과 포함]' if web_context else ''}"
                    f"\n{_rule}\n질문: {safe_query}\n\n답변:"
                )
                answer_raw = trace_synth_call(
                    _web_fallback_prompt,
                    applied_rule="reasoning.synth.web_fallback",
                    user_role=user_role,
                    use_cache=(not web_context),
                    timeout=90,
                    max_tokens=_style.max_tokens,
                    model=selected_model or None,
                )
            else:
                answer_raw = engine._generate_answer(
                    safe_query, combined_context, system_prompt,
                    response_style=response_style,
                    selected_model=selected_model,
                )
            answer_raw = answer_raw if answer_raw else ""

            if answer_raw and not any(
                answer_raw.startswith(p) for p in engine._LLM_ERROR_PREFIXES
            ):
                print(f"[ROUTER] retrieval_fallback (score={unified_score:.3f}) → LLM 직접")
                answer = answer_raw
            else:
                answer = engine._generate_answer(safe_query, safe_context, system_prompt, response_style=response_style, selected_model=selected_model)
        else:
            # 관련 자료 있음 → System Prompt + RAG 컨텍스트 + LLM 답변
            answer = engine._generate_answer(safe_query, safe_context, system_prompt, response_style=response_style, selected_model=selected_model)

        # [P7] "자료 없음" 단독 응답(추론 없음)이면 system_prompt 포함 재시도
        # α-6 S5 sector ablation — `JAMES_DISABLE_ABSTENTION=1` skips the
        # retry-no-info pass so the LLM's first "자료에 없음" answer stands.
        # The cell measures JAMES *without* the abstention softener.
        #
        # cycle γ Phase D2 (2026-06-08) — softener was Korean-only since
        # introduction; English queries (e.g. RGB-en) never triggered the
        # softener because the LLM's English abstention output didn't
        # match any Korean trigger string. JAMES_SOFTENER_BILINGUAL=1 enables
        # English triggers + bilingual retry prompt. Default OFF preserves
        # byte-identical pre-Phase-D2 behaviour for Korean-only deployments.
        _bilingual = os.environ.get("JAMES_SOFTENER_BILINGUAL") == "1"
        _no_data = _abstention_triggers(bilingual=_bilingual)
        _s5_disabled = os.environ.get("JAMES_DISABLE_ABSTENTION") == "1"
        if not _s5_disabled and answer and any(answer.startswith(p) for p in _no_data):
            sys_prefix = f"{system_prompt}\n\n" if system_prompt else ""
            from core.response_style import resolve_style as _resolve_style
            _style_retry = _resolve_style(response_style)
            _korean_r = sum(1 for c in safe_query if "가" <= c <= "힣")
            _is_ko_r = _korean_r >= max(1, len(safe_query) * 0.2)
            _rule_r = _style_retry.rule_text_ko if _is_ko_r else _style_retry.rule_text_en
            _retry_prompt = _build_retry_prompt(
                sys_prefix=sys_prefix,
                rule_text=_rule_r,
                query=safe_query,
                is_korean=_is_ko_r,
                bilingual=_bilingual,
            )
            retry = trace_synth_call(
                _retry_prompt,
                applied_rule="reasoning.synth.retry_no_info",
                user_role=user_role,
                use_cache=False,
                timeout=60,
                max_tokens=_style_retry.max_tokens,
                model=selected_model or None,
            )
            if retry and not any(retry.startswith(p) for p in engine._LLM_ERROR_PREFIXES):
                print("[ROUTER] post_check → 재시도 (persona 포함)")
                answer = retry

    except Exception as e:
        engine._log("generate_answer", e, user_role)
        answer = "답변 생성 중 오류가 발생했습니다."
    engine._elapsed(t_llm, "LLM_generate")
    # [#47 phase 1] answer stage — model latency + size signals so a
    # diagnoser can tell "blank answer because LLM timed out" from
    # "blank answer because retrieval was empty".
    log_stage(
        "answer",
        latency_ms=int((time.time() - t_llm) * 1000),
        answer_len=len(answer or ""),
        answer_starts_with_error=any(
            (answer or "").startswith(p) for p in engine._LLM_ERROR_PREFIXES
        ),
    )

    # Phase 2 PR-5 — optional reflection pass.
    # ReflectionLoop is opt-in via JAMES_ENABLE_REFLECT=1; default OFF
    # so a stock JAMES install pays no extra LLM round-trip per query.
    # When enabled, the loop runs critique + revise on the final answer
    # and returns the revised text; any failure falls back to ``answer``
    # unchanged so the synth contract is preserved end-to-end.
    try:
        from core.reasoning.reflect import get_reflection_loop
        reflected = get_reflection_loop().reflect(
            safe_query, answer, user_role=user_role
        )
        if reflected and reflected != answer and not any(
            reflected.startswith(p) for p in engine._LLM_ERROR_PREFIXES
        ):
            answer = reflected
    except Exception as e:
        engine._log("reflect_loop", e, user_role)

    # Phase 2 PR-6 — optional verification pass.
    # Verifier runs a heuristic security scan (always, ~5ms) plus an
    # optional LLM fact-check (separate env JAMES_ENABLE_FACT_CHECK=1).
    # Both gated on JAMES_ENABLE_VERIFY=1; default OFF preserves the
    # v0.3.0+PR1+PR2+PR5 path byte-identical.
    # Verifier returns one of three recommendations:
    #   accept   → final_answer == answer (unchanged)
    #   annotate → answer + verification note (unsupported claims)
    #   block    → safe refusal (injection echo detected)
    try:
        from core.reasoning.verify import get_verifier
        v_result = get_verifier().verify(
            safe_query, answer, safe_context, user_role
        )
        if v_result.final_answer and v_result.final_answer != answer:
            answer = v_result.final_answer
    except Exception as e:
        engine._log("verify_loop", e, user_role)

    out.answer = answer
    return out


__all__ = ["generate_answer"]
