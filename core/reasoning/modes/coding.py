"""``handle_coding`` — coder LLM + automatic patch pipeline.

Extracted from the monolithic ``core/reasoning/modes.py`` in the
v0.3.x rule-#5 split. Body is byte-identical to the pre-split version.
"""
from __future__ import annotations

import time
from typing import Any, Dict

from core.reasoning.trace_helpers import trace_synth_call


# ────────────────────────────────────────────────────────────────────
# coding — coder LLM + auto-patch pipeline
# ────────────────────────────────────────────────────────────────────
def handle_coding(
    engine,
    safe_query: str,
    system_prompt: str,
    user_role: str,
    t_start: float,
    selected_model: str = "",   # [#A2 phase 2] catalog-validated user pick
) -> Dict[str, Any]:
    """Coding mode handler.

    Routes to qwen2.5-coder via `llm.router.route(task_type="coding")`.
    On any failure (model not installed / Ollama not responding /
    timeout), falls back to the default GEMMA_MODEL via call_gemma so
    the user still gets an answer. All errors are logged via
    log_stage so the operator can see what happened in /trace/poll/.

    Operator override: set JAMES_CODING_MODEL env to a lighter model
    (e.g. gemma4:e4b) if the 32B qwen-coder cold-start is hitting
    your tunnel / proxy timeout.

    [#A2 phase 2] When the user has explicitly picked a model tag from
    the secondary picker (selected_model non-empty after engine-level
    catalog validation), we BYPASS the smart router entirely and call
    that model directly via call_gemma. The whole point of the picker
    is "let me override" — if the user said "gemma4:e4b" we shouldn't
    silently re-route to qwen-coder.
    """
    from core.observability import log_stage
    t_code = time.time()
    answer = ""

    # [#A2 phase 2] User explicitly picked → bypass smart router and
    # call the chosen model directly. The patch pipeline below still
    # runs on the resulting `answer`.
    if selected_model:
        log_stage("coding_user_pick", model=selected_model,
                  query_len=len(safe_query))
        try:
            sys_prefix = f"{system_prompt}\n\n" if system_prompt else ""
            _coding_user_prompt = f"{sys_prefix}코딩 질문: {safe_query}\n\n답변:"
            answer = trace_synth_call(
                _coding_user_prompt,
                applied_rule="reasoning.synth.coding_user_pick",
                user_role=user_role,
                use_cache=True,
                timeout=120,
                model=selected_model,
            )
            log_stage("coding_user_pick_done",
                      latency_ms=int((time.time() - t_code) * 1000),
                      answer_len=len(answer or ""))
        except Exception as e:
            engine._log("coding_user_pick", e, user_role)
            log_stage("coding_user_pick_error",
                      error=f"{type(e).__name__}: {e}")
            answer = (f"선택한 모델 '{selected_model}' 호출 실패: "
                      f"{type(e).__name__}. 서버 콘솔 trace 확인.")
    else:
        # Stage logged so /trace/poll/ shows what's happening in real time.
        log_stage("coding_route", model="qwen-coder", query_len=len(safe_query))

        try:
            from llm.router import route as llm_route
            llm = llm_route(safe_query, task_type="coding")
            log_stage("coding_llm_pick", llm_name=getattr(llm, "name", "?"),
                      available=getattr(llm, "is_available", lambda: True)())

            sys_prefix = f"{system_prompt}\n\n" if system_prompt else ""
            coding_prompt = sys_prefix + safe_query
            messages = [{"role": "user", "content": coding_prompt}]
            answer = llm.generate(messages, timeout=120)
            log_stage("coding_done",
                      latency_ms=int((time.time() - t_code) * 1000),
                      answer_len=len(answer or ""))
        except Exception as e:
            engine._log("coding_llm", e, user_role)
            log_stage("coding_llm_error", error=f"{type(e).__name__}: {e}")
            # Fallback: default GEMMA_MODEL via the engine's RouterWrapper
            try:
                sys_prefix = f"{system_prompt}\n\n" if system_prompt else ""
                _coding_fallback_prompt = f"{sys_prefix}코딩 질문: {safe_query}\n\n답변:"
                answer = trace_synth_call(
                    _coding_fallback_prompt,
                    applied_rule="reasoning.synth.coding_fallback",
                    user_role=user_role,
                    use_cache=True,
                    timeout=90,
                )
                log_stage("coding_fallback_done",
                          latency_ms=int((time.time() - t_code) * 1000),
                          answer_len=len(answer or ""))
            except Exception as e2:
                log_stage("coding_fallback_error",
                          error=f"{type(e2).__name__}: {e2}")
                # Surface the actual error class to the user — silent generic
                # message hides the diagnostic. Real cause is now visible
                # both in the answer and the trace.
                answer = (
                    f"코딩 답변 생성 실패. 원인: {type(e).__name__} "
                    f"(LLM router → coder), 그 후 fallback도 실패: "
                    f"{type(e2).__name__}. 서버 콘솔에서 자세한 trace 확인."
                )

    # [P7] Patch Pipeline 자동 실행
    try:
        from tools.patch.patch_extractor import (
            extract_from_chat, extract_target_from_query,
        )
        from tools.patch.patch_validator import validate_patch
        from tools.patch.patch_applier   import apply as patch_apply

        target = extract_target_from_query(safe_query)
        patch  = extract_from_chat(safe_query, answer, target)

        if patch:
            passed, failures = validate_patch(patch)
            if passed:
                ok, msg = patch_apply(patch, validated=True)
                print(f"[P7-PATCH] 자동 적용: {msg[:50]}")
            else:
                print(f"[P7-PATCH] 검증 실패: {failures}")
    except Exception as e:
        engine._log("patch_pipeline", e, user_role)

    engine._elapsed(t_code, "CODING+PATCH")
    return {
        "answer":        answer or "답변을 생성할 수 없습니다.",
        "mode":          "coding",
        "graph_paths":   [],
        "graph_used":    0,
        "sources":       [],
        "blocked":       False,
        "timing_sec":    round(time.time() - t_start, 2),
        "unified_score": 0.0,
        "loop_count":    0,
    }


__all__ = ["handle_coding"]
