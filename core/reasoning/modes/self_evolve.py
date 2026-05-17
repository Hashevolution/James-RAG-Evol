"""``handle_self_evolve`` — admin-only code introspection (folder / file / project scan).

Extracted from the monolithic ``core/reasoning/modes.py`` in the
v0.3.x rule-#5 split. Body is byte-identical to the pre-split version.
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict

from core.reasoning.trace_helpers import trace_synth_call


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
                _folder_prompt = (
                    f"{sys_prefix}다음 폴더 구조를 보고 각 파일의 역할과 "
                    f"전체 아키텍처를 설명해줘:\n\n{folder_report[:2000]}\n\n설명:"
                )
                analysis = trace_synth_call(
                    lambda: engine.llm.call_gemma(
                        _folder_prompt,
                        timeout=120, use_cache=False,
                        model=selected_model or None,
                    ),
                    _folder_prompt,
                    applied_rule="reasoning.synth.self_evolve_folder",
                    user_role=user_role,
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
            _file_prompt = (
                f"{sys_prefix}아래 코드를 분석하고 개선점을 제안해줘:\n\n"
                f"파일: {fname}\n```python\n{content[:2000]}\n```\n\n분석:"
            )
            analysis = trace_synth_call(
                lambda: engine.llm.call_gemma(
                    _file_prompt,
                    timeout=120, use_cache=False,
                    model=selected_model or None,
                ),
                _file_prompt,
                applied_rule="reasoning.synth.self_evolve_file",
                user_role=user_role,
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
                _improve_prompt = (
                    f"{sys_prefix}PROJECT JAMES의 현재 구조를 바탕으로, "
                    f"다음 관점에서 개선 제안을 해줘: {safe_query}\n\n제안:"
                )
                extra = trace_synth_call(
                    lambda: engine.llm.call_gemma(
                        _improve_prompt,
                        timeout=90, use_cache=False,
                        model=selected_model or None,
                    ),
                    _improve_prompt,
                    applied_rule="reasoning.synth.self_evolve_improve",
                    user_role=user_role,
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


__all__ = ["handle_self_evolve"]
