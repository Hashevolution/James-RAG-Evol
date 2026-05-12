"""Non-RAG mode handlers extracted from ReasoningEngine.query() (#29 phase 2/3).

Each handler is a free function that takes the engine instance plus the
specific closure variables it needs. They are pure refactor — every
expression and side effect matches the original in-method code byte-for-byte
where the language allows. The only change is `self.X` → `engine.X`.

Why free functions instead of methods on a Mixin:
- Composition is more explicit than inheritance for "engine plus side
  capabilities" semantics. The dispatch in query() reads as
  `return handle_chat(self, ...)` rather than `return self.handle_chat(...)`,
  making it visually obvious where the body lives.
- Method-resolution order, mocking, and `inspect.getsource()` all stay simple.

Permission gating (admin-only for wiki_edit / self_evolve) lives inside each
handler so the dispatch in query() stays uniform.
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict


# [Axis 6 user feedback, 2026-05-12] Prepended to the LLM prompt
# whenever previous-turn context exists. Suppresses the canned
# "안녕하세요. 자메스입니다." greeting that the model emits when it
# treats every turn as a cold start, and tells it how to resolve
# Korean / English anaphora against the immediately-preceding turn.
CONTINUITY_DIRECTIVE_KO = (
    "[연속 대화 규칙] 이전 대화가 이어지고 있다. "
    "'안녕하세요', '저는 자메스입니다' 같은 인사·자기소개는 생략하라. "
    "사용자가 '이것', '그것', '위', '위와 관련', '위에서' 같은 지시어를 "
    "사용하면 직전 턴의 답변·질문 내용을 참조하라."
)
CONTINUITY_DIRECTIVE_EN = (
    "[Continuity rule] This is a continuing conversation. "
    "Skip greetings and self-introductions like \"Hello\" or "
    "\"I'm JAMES\". When the user uses anaphora like \"this\", "
    "\"that\", \"the above\", \"as mentioned\", resolve it against "
    "the most recent turn in the conversation history above."
)


# ────────────────────────────────────────────────────────────────────
# chat — direct LLM, no retrieval
# ────────────────────────────────────────────────────────────────────
def handle_chat(
    engine,
    safe_query: str,
    system_prompt: str,
    memory_context: str,
    user_role: str,
    t_start: float,
    response_style: str = "",
    selected_model: str = "",   # [#A2 phase 2] catalog-validated user pick
) -> Dict[str, Any]:
    from core.response_style import resolve_style
    style = resolve_style(response_style)

    # Detect language by Korean character ratio to pick the
    # right-language flow guide. Same heuristic as engine._generate_answer.
    korean_chars = sum(1 for c in safe_query if "가" <= c <= "힣")
    is_ko = korean_chars >= max(1, len(safe_query) * 0.2)
    rule_txt = style.rule_text_ko if is_ko else style.rule_text_en

    t_direct = time.time()
    try:
        # system_prompt + memory_context + flow guide 주입
        sys_prefix = f"{system_prompt}\n\n" if system_prompt else ""
        # [Axis 6 user feedback, 2026-05-12] When prior turns exist
        # in memory_context, prepend a continuity directive so the
        # model (a) skips greeting / self-introduction preambles
        # and (b) resolves anaphora ("이것", "위와 관련", "그것")
        # against the most recent turn instead of starting fresh.
        # Empty memory_context ⇒ no directive ⇒ first-turn replies
        # keep their introductory tone.
        if memory_context:
            continuity_rule = CONTINUITY_DIRECTIVE_KO if is_ko else CONTINUITY_DIRECTIVE_EN
            mem_prefix = f"{continuity_rule}\n\n{memory_context}\n\n"
        else:
            mem_prefix = ""
        raw_answer = engine.llm.call_gemma(
            f"{sys_prefix}{mem_prefix}{rule_txt}\n질문: {safe_query}\n\n답변:",
            use_cache=True, timeout=60, max_tokens=style.max_tokens,
            model=selected_model or None,
        )
        # Preserve paragraph breaks (\n\n) — user feedback wants
        # natural 문단 separation, not a single block of text.
        # Collapse 3+ newlines to exactly 2 to keep things tidy.
        if raw_answer:
            answer = re.sub(r"\n{3,}", "\n\n", raw_answer).strip()
        else:
            answer = ""
        if not answer or any(answer.startswith(p) for p in engine._LLM_ERROR_PREFIXES):
            answer = "죄송합니다. 답변을 생성하지 못했습니다."
    except Exception as e:
        engine._log("direct_llm", e, user_role)
        answer = "죄송합니다. 답변 생성 중 오류가 발생했습니다."
    engine._elapsed(t_direct, "DIRECT_LLM(chat)")

    # Memory 추출 + 저장 (응답에 영향 없음)
    try:
        from core.memory import extract_memory, validate_memory
        from core.memory import MemoryStore
        candidate = extract_memory(safe_query, answer)
        if validate_memory(candidate):
            MemoryStore().save(candidate)
            print(f"[MEMORY] 저장: {candidate['type']}")
    except Exception as e:
        engine._log("memory_extract", e, user_role)

    return {
        "answer":        answer,
        "mode":          "chat",
        "graph_paths":   [],
        "graph_used":    0,
        "sources":       [],
        "blocked":       False,
        "timing_sec":    round(time.time() - t_start, 2),
        "unified_score": 0.0,
        "loop_count":    0,
    }


# ────────────────────────────────────────────────────────────────────
# meta — internal-data inventory ("what do you have?")
# ────────────────────────────────────────────────────────────────────
def handle_meta(
    engine,
    safe_query: str,
    system_prompt: str,
    user_role: str,
    t_start: float,
) -> Dict[str, Any]:
    """Inventory query handler — answers "what data do you have?" by
    listing wiki entity files directly via tools/wiki/list_entities.

    Pre-this-mode behavior: such queries fell into `retrieval` and
    returned hallucinated answers because the wiki file *list* lives in
    no vector chunk. Now we read the filesystem directly and format a
    grouped summary (top-level dirs first, then sample names).

    Output is intentionally compact (counts + sample, not full list) —
    a 200-entity wiki would otherwise blow the answer length even with
    response_style=brief. The user can drill in with a follow-up
    retrieval query (e.g. "person 카테고리에 어떤 인물 있어?").
    """
    t_meta = time.time()
    answer = ""
    try:
        from tools.wiki.wiki_editor import list_entities

        # Pull a generous slice — the formatter below dedupes by top-
        # level directory anyway. 500 covers any realistic v0.2 corpus.
        all_entities = list_entities(limit=500)
        total = len(all_entities)

        if total == 0:
            answer = "현재 보유한 wiki 자료가 없습니다."
        else:
            # Group by top-level dir under wiki/. The user wants to see
            # the structure ("entity/", "system/", "person/") not a
            # flat 200-row list.
            from collections import defaultdict
            buckets: dict[str, list[str]] = defaultdict(list)
            for e in all_entities:
                p = e.get("path", "")
                # First path segment as bucket; if no separator, use "(root)".
                head = p.split("/", 1)[0].split("\\", 1)[0] if p else "(root)"
                if "/" not in p and "\\" not in p:
                    head = "(root)"
                buckets[head].append(e.get("name", ""))

            lines = [f"📚 보유 wiki 자료: 총 {total}개"]
            for bucket in sorted(buckets.keys()):
                names = buckets[bucket]
                sample = ", ".join(names[:8])
                more = f" (+{len(names) - 8}개 더)" if len(names) > 8 else ""
                lines.append(f"  • {bucket}/  ({len(names)}개): {sample}{more}")
            lines.append("")
            lines.append(
                "특정 항목 자세히 보려면 구체적으로 질문하세요. "
                "예: '비트코인에 대해 알려줘'"
            )
            answer = "\n".join(lines)

    except Exception as e:
        engine._log("meta_inventory", e, user_role)
        answer = f"❌ 자료 목록 조회 실패: {e}"

    engine._elapsed(t_meta, "META_inventory")
    return {
        "answer":        answer,
        "mode":          "meta",
        "graph_paths":   [],
        "graph_used":    0,
        "sources":       [],
        "blocked":       False,
        "role_used":     user_role,
        "timing_sec":    round(time.time() - t_start, 2),
        "unified_score": 1.0,
        "loop_count":    0,
    }


# ────────────────────────────────────────────────────────────────────
# wiki_edit — admin-only wiki entity CRUD
# ────────────────────────────────────────────────────────────────────
def handle_wiki_edit(
    engine,
    safe_query: str,
    system_prompt: str,
    user_role: str,
    t_start: float,
    selected_model: str = "",   # [#A2 phase 2] catalog-validated user pick
) -> Dict[str, Any]:
    if user_role != "admin":
        return engine._blocked_result("wiki 편집은 admin 권한만 가능합니다.")

    t_wiki = time.time()
    answer = ""
    try:
        from tools.wiki.wiki_editor import (
            parse_edit_intent, read_entity,
            append_to_entity, update_entity,
            delete_entity, create_entity,
        )

        # 1. LLM으로 명령 파싱 (entity명, 액션, 내용 추출)
        sys_prefix = f"{system_prompt}\n\n" if system_prompt else ""
        parse_prompt = (
            f"{sys_prefix}"
            f"다음 명령에서 wiki 편집 정보를 JSON으로 추출하라.\n"
            f"명령: {safe_query}\n\n"
            "JSON 형식 (반드시 이 키만 사용):\n"
            '{"action": "append|update|delete|create|read",'
            ' "target": "entity이름",'
            ' "detail": "변경할 내용",'
            ' "entity_type": "person|org|concept|document"}\n\n'
            "JSON만 출력:"
        )
        raw = engine.llm.call_gemma(parse_prompt, timeout=30, use_cache=False,
                                    model=selected_model or None)

        # JSON 파싱
        import json as _json
        intent = {}
        try:
            m = re.search(r'\{.*\}', raw or "", re.DOTALL)
            if m:
                intent = _json.loads(m.group())
        except Exception:
            pass

        # LLM 파싱 실패 시 규칙 기반 fallback
        if not intent or not intent.get("target"):
            from tools.wiki.wiki_editor import parse_edit_intent
            intent = parse_edit_intent(safe_query)

        action      = intent.get("action", "unknown")
        target      = intent.get("target", "")
        detail      = intent.get("detail", "")
        entity_type = intent.get("entity_type", "concept")

        print(f"[WIKI_EDIT] action={action} target={target} detail={detail[:40]}")

        # 2. 액션 실행
        if action == "read":
            ok, content, msg = read_entity(target)
            answer = f"📄 {target} 파일 내용:\n\n{content[:800]}" if ok else f"❌ {msg}"

        elif action == "append":
            ok, msg = append_to_entity(target, detail, user_role)
            answer = msg if ok else f"❌ {msg}"

        elif action == "update":
            # update는 기존 내용 읽기 → LLM이 새 내용 생성 → 저장
            ok_r, old_content, _ = read_entity(target)
            if not ok_r:
                answer = f"❌ '{target}' 파일을 찾을 수 없습니다."
            else:
                new_prompt = (
                    f"{sys_prefix}"
                    f"아래 wiki 파일을 다음 지시에 맞게 수정하라.\n"
                    f"지시: {detail}\n\n"
                    f"[현재 내용]\n{old_content[:1200]}\n\n"
                    "수정된 전체 내용만 출력 (frontmatter 포함):"
                )
                new_content = engine.llm.call_gemma(
                    new_prompt, timeout=90, use_cache=False,
                    model=selected_model or None,
                )
                if new_content:
                    ok, msg = update_entity(target, new_content, user_role)
                    answer = msg if ok else f"❌ {msg}"
                else:
                    answer = "❌ 새 내용 생성 실패"

        elif action == "delete":
            ok, msg = delete_entity(target, user_role)
            answer = msg if ok else f"❌ {msg}"

        elif action == "create":
            ok, msg = create_entity(
                name=target, entity_type=entity_type,
                description=detail, user_role=user_role,
            )
            answer = msg if ok else f"❌ {msg}"

        else:
            answer = (
                "❌ 편집 의도를 파악하지 못했습니다.\n"
                "예시: '김철수 파일에 삼성전자 퇴직 추가해줘'"
            )

    except Exception as e:
        engine._log("wiki_edit", e, user_role)
        answer = f"❌ wiki 편집 중 오류: {e}"

    engine._elapsed(t_wiki, "WIKI_EDIT")
    return {
        "answer":        answer,
        "mode":          "wiki_edit",
        "graph_paths":   [],
        "graph_used":    0,
        "sources":       [],
        "blocked":       False,
        "role_used":     user_role,
        "timing_sec":    round(time.time() - t_start, 2),
        "unified_score": 1.0,
        "loop_count":    0,
    }


# ────────────────────────────────────────────────────────────────────
# self_evolve — admin-only code introspection
# ────────────────────────────────────────────────────────────────────
def handle_self_evolve(
    engine,
    safe_query: str,
    system_prompt: str,
    user_role: str,
    t_start: float,
    selected_model: str = "",   # [#A2 phase 2] catalog-validated user pick
) -> Dict[str, Any]:
    if user_role != "admin":
        return engine._blocked_result("자기 진화는 admin 권한만 가능합니다.")

    t_self = time.time()
    try:
        from tools.self.file_scanner import get_file_content

        safe_query.lower()

        # [P2-9] 폴더 지정 분석 (예: "tools 폴더", "core/ 폴더")
        folder_match = re.search(
            r'([\w/]+)\s*(?:폴더|디렉토리|folder|directory)', safe_query, re.IGNORECASE
        )

        # 특정 파일 내용 요청
        file_match = re.search(
            r'([\w./]+\.py)', safe_query, re.IGNORECASE
        )

        if folder_match:
            # [P2-9] 폴더 내 파일 목록 + 각 파일 요약
            folder_name = folder_match.group(1).strip()
            from tools.self.file_scanner import BASE_PATH
            folder_path = BASE_PATH / folder_name
            if not folder_path.exists():
                # 루트에서 재탐색
                for p in BASE_PATH.rglob(folder_name):
                    if p.is_dir():
                        folder_path = p
                        break

            if folder_path.exists() and folder_path.is_dir():
                py_files = list(folder_path.rglob("*.py"))
                md_files = list(folder_path.rglob("*.md"))

                # 각 파일 함수 목록 추출
                file_summaries = []
                for f in sorted(py_files)[:10]:  # 최대 10개
                    try:
                        src = f.read_text(encoding='utf-8', errors='replace')
                        fns = re.findall(r'^def (\w+)\(', src, re.MULTILINE)
                        classes = re.findall(r'^class (\w+)', src, re.MULTILINE)
                        size = len(src)
                        summary = f"  📄 {f.name} ({size//1024}KB)"
                        if classes: summary += f"\n     클래스: {', '.join(classes[:5])}"
                        if fns:    summary += f"\n     함수: {', '.join(fns[:8])}"
                        file_summaries.append(summary)
                    except Exception:
                        file_summaries.append(f"  📄 {f.name}")

                folder_report = (
                    f"📂 **{folder_name}/** 폴더 분석\n\n"
                    f"  Python 파일: {len(py_files)}개\n"
                    f"  Markdown:    {len(md_files)}개\n\n"
                    f"파일 목록:\n" + "\n".join(file_summaries)
                )

                # LLM에 세부 분석 요청
                sys_prefix = f"{system_prompt}\n\n" if system_prompt else ""
                analysis = engine.llm.call_gemma(
                    f"{sys_prefix}다음 폴더 구조를 보고 각 파일의 역할과 "
                    f"전체 아키텍처를 설명해줘:\n\n{folder_report[:2000]}\n\n설명:",
                    timeout=120, use_cache=False,
                    model=selected_model or None,
                )
                answer = folder_report
                if analysis:
                    answer += f"\n\n💡 **구조 분석:**\n{analysis}"
            else:
                answer = f"❌ '{folder_name}' 폴더를 찾을 수 없습니다."

        elif file_match:
            # 특정 파일 내용 요청
            fname   = file_match.group(1)
            content = get_file_content(fname)
            sys_prefix = f"{system_prompt}\n\n" if system_prompt else ""
            analysis = engine.llm.call_gemma(
                f"{sys_prefix}아래 코드를 분석하고 개선점을 제안해줘:\n\n"
                f"파일: {fname}\n```python\n{content[:2000]}\n```\n\n분석:",
                timeout=120, use_cache=False,
                model=selected_model or None,
            )
            answer = (
                f"📄 **{fname}** 분석\n\n"
                f"```python\n{content[:500]}...\n```\n\n"
                f"💡 **분석 결과:**\n{analysis or '분석 실패'}"
            )

        else:
            # 전체 구조 스캔
            from tools.self.file_scanner import (
                scan_project, build_wiki_content,
                save_to_wiki, index_to_vector
            )
            result  = scan_project(force=True)
            content = build_wiki_content(result)
            save_to_wiki(content)
            chunks = index_to_vector(
                content,
                vector_store=engine.retrieval.vector_store
            )

            answer = (
                f"✅ 코드 스캔 완료\n\n"
                f"📁 총 파일: {result['total']}개\n"
                f"🔄 갱신됨: {len(result['changed'])}개\n"
                f"📚 인덱싱: {chunks} chunks\n\n"
                f"📂 폴더 구조:\n{result['tree'][:800]}\n\n"
                f"💡 특정 폴더/파일 분석: 'tools 폴더 분석해줘' 또는 "
                f"'core/reasoning_engine.py 분석해줘'"
            )

            if safe_query and ("개선" in safe_query or "분석" in safe_query):
                sys_prefix = f"{system_prompt}\n\n" if system_prompt else ""
                extra = engine.llm.call_gemma(
                    f"{sys_prefix}PROJECT JAMES의 현재 구조를 바탕으로, "
                    f"다음 관점에서 개선 제안을 해줘: {safe_query}\n\n제안:",
                    timeout=90, use_cache=False,
                    model=selected_model or None,
                )
                if extra:
                    answer += f"\n\n💡 **개선 제안:**\n{extra}"

    except Exception as e:
        engine._log("self_evolve", e, user_role)
        answer = f"❌ 자기 분석 중 오류: {e}"

    engine._elapsed(t_self, "SELF_EVOLVE")
    return {
        "answer":        answer,
        "mode":          "self_evolve",
        "graph_paths":   [],
        "graph_used":    0,
        "sources":       [],
        "blocked":       False,
        "role_used":     user_role,
        "timing_sec":    round(time.time() - t_start, 2),
        "unified_score": 1.0,
        "loop_count":    0,
    }


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
            answer = engine.llm.call_gemma(
                f"{sys_prefix}코딩 질문: {safe_query}\n\n답변:",
                use_cache=True, timeout=120,
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
                answer = engine.llm.call_gemma(
                    f"{sys_prefix}코딩 질문: {safe_query}\n\n답변:",
                    use_cache=True, timeout=90,
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
