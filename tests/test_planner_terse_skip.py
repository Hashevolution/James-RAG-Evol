"""§24 P-1 — terse 모드에서 planner plan-prepend skip (2026-06-05).

배경. `pipeline_synth.generate_answer` 는 `JAMES_ENABLE_PLANNER=1`
활성 시 매 query 마다 planner.plan() 호출 → sub-tasks 를 numbered
list 로 `[추론 계획]` 헤더와 함께 system_prompt 앞에 prepend +
`위 계획에 따라 단계별로 답변하라.` 한국어 directive 강제. 이
directive 가 모델에 step-by-step report 양식 ("### Step 1:" /
"### 1. Analysis" / "Hello, I am JAMES. I will follow the plan
step-by-step") 을 prior 로 활성화 → terse 모드의 단답 contract
와 정면 충돌.

PM-15 (e4b cap=8000 + per-query + stripper) 28/100 meta-mode 답
중 23/28 이 stripper 미스 — 그 23 의 답 lead 가 정확히 plan
directive 가 유도하는 양식. raw e4b (no JAMES stack) 는 100/100
중 0 → JAMES 측 prompt 가 원인 확정 → planner prepend 추적.

Fix (§24 P-1): terse 모드에서 plan prepend skip. response_style
이 terse 일 때만 차단, 나머지 (NATURAL / chat / 보고서 모드) 는
byte-identical 보존. cycle β 의 더 systemic 한 redesign (plan 을
retrieval routing 에만 사용, model prompt 비노출) 은 별도 PR.
"""
from __future__ import annotations

import importlib
import inspect
import re
from pathlib import Path


def _pipeline_synth_sources() -> dict[str, str]:
    """`{submodule name: source}` for the whole `pipeline_synth` package.

    [2026-08-21] `pipeline_synth` was a single module when these
    signature tests were written; it is now a package (`generator` /
    `softener` / `result`), split under the 20 KB module-size gate
    (CLAUDE.md rule 5). `inspect.getsource()` on a package returns only
    `__init__.py`, so every assertion here started reporting the P-1
    gate as missing when the code had simply moved. Read the package.
    """
    from core.reasoning import pipeline_synth
    out = {"__init__": inspect.getsource(pipeline_synth)}
    for path in sorted(Path(pipeline_synth.__file__).parent.glob("*.py")):
        if path.stem == "__init__":
            continue
        mod = importlib.import_module(
            f"core.reasoning.pipeline_synth.{path.stem}")
        out[path.stem] = inspect.getsource(mod)
    return out


def _read_pipeline_synth() -> str:
    return "\n".join(_pipeline_synth_sources().values())


def test_generate_answer_uses_resolve_style_for_terse_check():
    """generate_answer 가 resolve_style 을 호출해 terse 여부를 결정
    하는지 검증 (직접 환경변수 검사 아니라 공식 resolver 경유)."""
    src = _read_pipeline_synth()
    assert "resolve_style" in src, (
        "pipeline_synth must call resolve_style for the terse gate"
    )
    assert ".name == \"terse\"" in src or ".name == 'terse'" in src, (
        "terse decision should compare resolved style name to 'terse'"
    )


def test_planner_prepend_guarded_by_non_terse():
    """planner.plan() 호출 + `[추론 계획]` prepend 가 terse 가드
    뒤에 있어야 함. 가드 없이 무조건 prepend 면 P-1 회귀."""
    src = _read_pipeline_synth()
    # The planner block must sit inside a non-terse branch
    assert "if not _style_is_terse" in src, (
        "planner prepend must be inside `if not _style_is_terse` guard"
    )
    # And `[추론 계획]` literal must still be present (we didn't delete
    # the feature — just gated it)
    assert "[추론 계획]" in src, (
        "[추론 계획] header should remain for the non-terse path"
    )
    assert "위 계획에 따라 단계별로 답변하라" in src, (
        "step-by-step directive should remain for non-terse path"
    )


def test_terse_gate_precedes_planner_call():
    """terse 결정이 planner.plan() 호출 *이전*에 와야 — terse 면
    LLM round-trip 자체를 절약. planner 호출 후 prepend 만 skip
    하면 자원 낭비 + 의미상 모순."""
    # Ordering is only meaningful inside one file, so locate the
    # submodule that carries the planner call and check the order there.
    for name, src in _pipeline_synth_sources().items():
        plan_call_idx = src.find("get_planner().plan(safe_query")
        if plan_call_idx < 0:
            continue
        style_idx = src.find("_style_is_terse")
        assert 0 <= style_idx < plan_call_idx, (
            f"terse style check must come before get_planner().plan() "
            f"in pipeline_synth.{name}"
        )
        break
    else:
        raise AssertionError(
            "get_planner().plan(safe_query ...) not found anywhere in "
            "the pipeline_synth package — the P-1 planner path is gone"
        )


def test_resolve_style_fallback_to_non_terse_on_error():
    """resolve_style import / 호출 실패 시 _style_is_terse=False 로
    떨어져 기존 (non-terse) 동작 유지 — 안전 fallback."""
    src = _read_pipeline_synth()
    # The try / except around resolve_style must set _style_is_terse=False
    # in the except path (preserve byte-identical non-terse behavior on
    # any import failure).
    pattern = re.compile(
        r"try:\s*\n\s*from core\.response_style import resolve_style.*?"
        r"except Exception:\s*\n\s*_style_is_terse = False",
        re.DOTALL,
    )
    assert pattern.search(src), (
        "resolve_style import must fall back to _style_is_terse=False "
        "on any exception (byte-identical legacy behavior preserved)"
    )


def test_non_terse_path_byte_identical_to_legacy():
    """non-terse 분기 (NATURAL / brief / standard / detailed / 빈
    문자열) 는 기존 호출 패턴 (get_planner().plan() + Plan.is_trivial
    + [추론 계획] prepend) 그대로. 회귀 검출."""
    src = _read_pipeline_synth()
    # Original legacy sequence must still appear, gated only by the
    # non-terse branch.
    for needle in (
        "get_planner().plan(safe_query, user_role=user_role)",
        "not _plan.is_trivial()",
        "for i, s in enumerate(_plan.subtasks)",
        "[추론 계획]",
    ):
        assert needle in src, f"non-terse legacy path lost: {needle!r}"


def test_design_rationale_documented_in_source():
    """§24 P-1 design 의도가 source 주석에 살아 있어야 — 미래
    리팩토링이 'unused branch' 로 오해하고 지우지 않게."""
    src = _read_pipeline_synth()
    # Date + reason marker
    assert "2026-06-05" in src and "§24" in src, (
        "P-1 design comment must record date + section anchor"
    )
    # Cross-reference to PM-15 finding
    assert "PM-15" in src, (
        "P-1 design comment should reference PM-15 (the measurement "
        "that surfaced the planner-leak class of meta-mode answers)"
    )
