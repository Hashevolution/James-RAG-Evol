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
) -> Dict[str, Any]:
    from core.response_style import resolve_style
    style = resolve_style(response_style)

    t_direct = time.time()
    try:
        # system_prompt + memory_context 주입
        sys_prefix = f"{system_prompt}\n\n" if system_prompt else ""
        mem_prefix = f"{memory_context}\n\n" if memory_context else ""
        raw_answer = engine.llm.call_gemma(
            f"{sys_prefix}{mem_prefix}질문: {safe_query}\n\n답변:",
            use_cache=True, timeout=60, max_tokens=style.max_tokens,
        )
        # [P7-FIX] 글자 사이 \n 제거 → 세로줄 방지
        if raw_answer:
            # \n\n 이상 → 단락 구분 (공백)
            answer = re.sub(r'\n{2,}', ' ', raw_answer)
            # 단일 \n → 완전 제거 (한국어 글자 사이 세로줄 방지)
            answer = re.sub(r'\n', '', answer).strip()
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
# wiki_edit — admin-only wiki entity CRUD
# ────────────────────────────────────────────────────────────────────
def handle_wiki_edit(
    engine,
    safe_query: str,
    system_prompt: str,
    user_role: str,
    t_start: float,
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
        raw = engine.llm.call_gemma(parse_prompt, timeout=30, use_cache=False)

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
                    new_prompt, timeout=90, use_cache=False
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
                f"❌ 편집 의도를 파악하지 못했습니다.\n"
                f"예시: '김철수 파일에 삼성전자 퇴직 추가해줘'"
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
) -> Dict[str, Any]:
    if user_role != "admin":
        return engine._blocked_result("자기 진화는 admin 권한만 가능합니다.")

    t_self = time.time()
    try:
        from tools.self.file_scanner import scan_and_report, get_file_content

        q_lower = safe_query.lower()

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
) -> Dict[str, Any]:
    t_code = time.time()
    answer = ""
    try:
        from llm.router import route as llm_route
        llm = llm_route(safe_query, task_type="coding")
        # [P7] System Prompt를 coding 지시에도 포함
        coding_prompt = (
            f"{system_prompt}\n\n" if system_prompt else ""
        ) + safe_query
        messages = [{"role": "user", "content": coding_prompt}]
        answer   = llm.generate(messages, timeout=120)
    except Exception as e:
        engine._log("coding_llm", e, user_role)
        try:
            sys_prefix = f"{system_prompt}\n\n" if system_prompt else ""
            answer = engine.llm.call_gemma(
                f"{sys_prefix}코딩 질문: {safe_query}\n\n답변:",
                use_cache=True, timeout=90,
            )
        except Exception:
            answer = "코딩 답변 생성 중 오류가 발생했습니다."

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
