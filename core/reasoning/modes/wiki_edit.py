"""``handle_wiki_edit`` — admin-only wiki entity CRUD via natural language.

Extracted from the monolithic ``core/reasoning/modes.py`` in the
v0.3.x rule-#5 split. Body is byte-identical to the pre-split version.
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict

from core.reasoning.trace_helpers import trace_synth_call


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
            ' "entity_type": "person|org|concept|document'
            '|event|date|location|quantity|project"}\n\n'
            "JSON만 출력:"
        )
        raw = trace_synth_call(
            parse_prompt,
            applied_rule="reasoning.synth.wiki_edit_parse",
            user_role=user_role,
            timeout=30,
            use_cache=False,
            model=selected_model or None,
        )

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
                new_content = trace_synth_call(
                    new_prompt,
                    applied_rule="reasoning.synth.wiki_edit_update",
                    user_role=user_role,
                    timeout=90,
                    use_cache=False,
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


__all__ = ["handle_wiki_edit"]
