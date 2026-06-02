"""A3 — think-mode quality boundary experiment (5 cognitive stages × hard/easy fixtures).

Closes §17.5.3 of `reports/research-runs/v3prime-cross-family-final-2026-05-29.md`:

    "think-mode quality boundary — when does the default reasoning trace actually
     improve the answer vs waste budget? Measured-null on easy fixtures (§16
     Part C); unmeasured on hard multi-step prompts. Deferred to a JAMES-
     operations follow-up (relates to the §16.5 task)."

This driver runs the deferred hard-fixture leg. For each of the 5 cognitive
stages (planner / reflect / verify / synthesis / query_rewriter) it pairs the
existing easy fixture with a newly designed hard one and runs both think=True
and think=False, capturing budget cost + deterministic quality signals. The
output is a per-stage verdict feeding A2 (gemma4:e4b operational think-policy).

Hard-fixture design principles (per stage):
- planner_hard:  3-hop conditional query (subtasks + dependency + branching)
- reflect_hard:  draft with 3 planted defects (contradiction, missing-side, ambiguity)
- verify_hard:   answer with 3 fabricated claims vs context that supports only 1
- synth_hard:    3-document comparison with 1 internal contradiction
- rewriter_hard: F7-style multi-hop entity (concept anchor required)

Deterministic graders (no LLM-judge, by design — keeps the boundary
measurement self-contained; LLM-judge upgrade is a v2 if results are ambiguous).

Method:
- /api/generate (matches JAMES production path) with explicit think field.
  gemma4:e4b is the only panel model that honours think; the toggle was
  validated in §16.2 (eval_count 400 → 45 with identical visible answer on easy).
- temp=0.2, cap=4096 (A5 production cap), n=5 per cell by default → 100 calls.
- Per cell: eval_count, visible chars, stage-specific quality signals.
- Verdict per (stage × fixture): think=OFF safe / think=ON needed / ambiguous.

Output: JSON dump + markdown report. cp949-safe stdout.

Internal-only: this measures JAMES's own default model on JAMES's own cognitive
stages; no collaboration axis (Robin 26b / Ali Gemini) is touched.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[2]
RESEARCH = REPO / "scripts" / "research"
REPORTS = REPO / "reports" / "research-runs"
GEN_URL = "http://127.0.0.1:11434/api/generate"
DEFAULT_MODEL = "gemma4:e4b"
DEFAULT_TEMP = 0.2
DEFAULT_CAP = 4096
DEFAULT_N = 5
DEFAULT_TIMEOUT = 180.0

# ────────────────────────────────────────────────────────────────────
# Easy fixtures — load from existing per-stage drivers so the easy
# baseline is byte-identical to the §16 Part C measurement.
# ────────────────────────────────────────────────────────────────────


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, RESEARCH / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_EASY_QUERY = "BlackRock 과 Vanguard 의 ETF 전략 차이를 비교해줘"


def build_easy_prompts() -> dict[str, str]:
    pl = _load("v3prime_planner")
    rf = _load("v3prime_reflect")
    vf = _load("v3prime_verify")
    qr = _load("v3prime_query_rewriter")
    ems = _load("v3prime_e_mode_split")
    return {
        "planner": pl.PLAN_PROMPT_KO.format(query=_EASY_QUERY),
        "reflect": rf.CRITIQUE_PROMPT_KO.format(
            query=_EASY_QUERY, draft=rf.FIXTURE_DRAFT_KO
        ),
        "verify": vf.FACT_CHECK_PROMPT_KO.format(
            query=_EASY_QUERY,
            answer=vf.FIXTURE_ANSWER_KO,
            context=vf.FIXTURE_CONTEXT_KO,
        ),
        "synthesis": ems.SYNTHESIS_PROMPT.format(context=ems.CONTEXT_FIXTURE),
        "query_rewriter": qr.REWRITE_PROMPT_KO.format(query=_EASY_QUERY),
    }


# ────────────────────────────────────────────────────────────────────
# Hard fixtures — newly designed for A3. Each is deliberately built so
# a non-reasoning answer can be detected by a deterministic grader.
# ────────────────────────────────────────────────────────────────────

# planner — 3-hop conditional. A correct decomposition must (a) decompose
# into ≥3 subtasks, (b) reference the conditional (인플레이션 시나리오),
# (c) reference the dependency (먼저 자산군 결정 → 그 안에서 ETF 선택).
PLANNER_HARD_QUERY = (
    "2026 년 미국 인플레이션이 5% 이상으로 유지되는 시나리오와 2% 수준으로 "
    "안정되는 시나리오 각각에서, 유리한 자산군을 결정한 뒤 그 자산군 내에서 "
    "expense ratio 가 가장 낮은 ETF 3 개를 추려 비교 보고서를 작성하라."
)

# reflect — draft with 3 planted defects:
#   (1) contradiction: BlackRock fee says "0.10~0.30%" in para 1 but
#       "0.40~0.60%" in para 2.
#   (2) missing-side: Vanguard side completely absent (query asks for
#       comparison; draft only describes BlackRock).
#   (3) ambiguity: timeframe "최근" with no concrete period.
REFLECT_HARD_QUERY = _EASY_QUERY
REFLECT_HARD_DRAFT = (
    "BlackRock 의 iShares 시리즈는 시장 점유율 1 위로, 테마형 ETF "
    "라인업이 넓다. 운용 보수는 평균 0.10~0.30% 수준이다.\n\n"
    "최근 BlackRock 은 비트코인 spot ETF (IBIT) 출시에 적극적이며, "
    "테마형 ETF 의 운용 보수는 평균 0.40~0.60% 수준으로 알려져 있다.\n\n"
    "정리하면 BlackRock 은 폭넓은 상품 다양성 + 신규 시장 선점으로 "
    "요약된다."
)

# verify — answer fabricates claims unsupported by the provided context:
#   (1) "BlackRock 의 AUM 은 글로벌 GDP 의 12% 다" — not in context.
#   (2) "Vanguard 의 VOO expense ratio 는 0.01% 다" — context says 0.03~0.05%.
#   (3) "Vanguard 가 2024 년 spot 비트코인 ETF 를 출시했다" — context says
#       Vanguard 신청 보류.
# Only (4) "BlackRock 의 iShares 는 AUM 1 위" is grounded.
# Expected: grounded=false, unsupported list ≥ 2 items.
VERIFY_HARD_QUERY = _EASY_QUERY
VERIFY_HARD_ANSWER = (
    "BlackRock 의 iShares 는 AUM 글로벌 1 위로, BlackRock 의 전체 AUM "
    "은 글로벌 GDP 의 12% 를 차지한다.\n\n"
    "Vanguard 의 VOO 는 expense ratio 0.01% 로 업계 최저이며, Vanguard "
    "는 2024 년 spot 비트코인 ETF 를 출시해 디지털 자산 시장에 진입했다."
)
# Reuse the same FIXTURE_CONTEXT_KO from v3prime_verify so the
# adversarial signals (real fee bands, real Vanguard 신청 보류 line) are
# the same as the existing easy fixture's context.

# synthesis — 3-item ETF comparison with one internal contradiction.
# The hard prompt asks for a multi-row comparison; the context contains
# a contradiction (VOO fee listed as 0.03% in one passage, 0.05% in
# another). A reasoning model should produce a coherent table; a non-
# reasoning fallback may emit the contradiction verbatim or pick one.
SYNTHESIS_HARD_CONTEXT = (
    "[문서 A — 미국 대표 인덱스 ETF 비교, 2026 Q1]\n"
    "Vanguard VOO (S&P 500) — expense ratio 0.03%, AUM 1.2T USD.\n"
    "BlackRock IVV (S&P 500) — expense ratio 0.03%, AUM 0.5T USD.\n"
    "State Street SPY (S&P 500) — expense ratio 0.0945%, AUM 0.5T USD.\n\n"
    "[문서 B — Vanguard 비용 공시 메모, 2026 Q1]\n"
    "VOO 의 expense ratio 는 2026 Q1 부로 0.05% 로 상향 조정 검토 중. "
    "현재 공식 expense ratio 는 여전히 0.03%.\n\n"
    "[문서 C — ETF 시장 보고서, 2025 Q4]\n"
    "S&P 500 인덱스 ETF 중 거래량 1 위는 SPY, AUM 1 위는 VOO. "
    "IVV 는 BlackRock 의 코어 인덱스 ETF 로 분류된다."
)
SYNTHESIS_HARD_PROMPT = (
    "Compare the three S&P 500 ETFs (VOO, IVV, SPY) using the documents "
    "below. Produce a comparison covering (1) expense ratio, (2) AUM, "
    "(3) issuer. If the documents contain conflicting numbers for any "
    "field, flag the conflict explicitly.\n\n[Documents]\n"
    "{context}\n\nComparison:"
).format(context=SYNTHESIS_HARD_CONTEXT)

# query_rewriter — F7/F9 multi-hop entity. A non-reasoning rewrite
# echoes the surface form; a reasoning rewrite adds the concept anchor
# "Model Context Protocol" or the originator entity, both of which the
# F7 finding identified as required for retrieval.
REWRITER_HARD_QUERY = "MCP 설계자가 최근에 다른 회사로 이직한다는 발표"


def build_hard_prompts() -> dict[str, str]:
    pl = _load("v3prime_planner")
    rf = _load("v3prime_reflect")
    vf = _load("v3prime_verify")
    qr = _load("v3prime_query_rewriter")
    return {
        "planner": pl.PLAN_PROMPT_KO.format(query=PLANNER_HARD_QUERY),
        "reflect": rf.CRITIQUE_PROMPT_KO.format(
            query=REFLECT_HARD_QUERY, draft=REFLECT_HARD_DRAFT
        ),
        "verify": vf.FACT_CHECK_PROMPT_KO.format(
            query=VERIFY_HARD_QUERY,
            answer=VERIFY_HARD_ANSWER,
            context=vf.FIXTURE_CONTEXT_KO,
        ),
        "synthesis": SYNTHESIS_HARD_PROMPT,
        "query_rewriter": qr.REWRITE_PROMPT_KO.format(query=REWRITER_HARD_QUERY),
    }


# ────────────────────────────────────────────────────────────────────
# Ollama call — explicit think field. cap=4096 so the thinking trace
# never truncates the visible answer (we measure quality, not floor).
# ────────────────────────────────────────────────────────────────────


def call_ollama(
    prompt: str, *, think: bool, model: str, cap: int, temp: float,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict:
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "think": think,
        "options": {"num_predict": cap, "temperature": temp},
    }).encode("utf-8")
    req = request.Request(
        GEN_URL, data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    t0 = time.monotonic()
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as e:
        return {"_error": f"HTTPError {e.code}",
                "elapsed_s": round(time.monotonic() - t0, 2)}
    except error.URLError as e:
        return {"_error": f"URLError {e.reason}",
                "elapsed_s": round(time.monotonic() - t0, 2)}
    elapsed = time.monotonic() - t0
    raw = payload.get("response", "")
    return {
        "elapsed_s": round(elapsed, 2),
        "response": raw,
        "response_chars": len(raw),
        "eval_count": payload.get("eval_count") or 0,
        "done_reason": payload.get("done_reason", "?"),
        "non_empty": bool(raw.strip()),
    }


# ────────────────────────────────────────────────────────────────────
# Per-stage deterministic graders. Each returns a dict of named signals
# the report can compare across (think_on, think_off).
# ────────────────────────────────────────────────────────────────────


def _strip_json_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t)
    return t.strip()


def grade_planner(response: str) -> dict:
    """planner: subtasks-JSON shape + conditional/dependency signals."""
    parsed: dict | None = None
    try:
        parsed = json.loads(_strip_json_fence(response))
    except (json.JSONDecodeError, ValueError):
        parsed = None
    subtasks = parsed.get("subtasks", []) if isinstance(parsed, dict) else []
    n_subtasks = len(subtasks) if isinstance(subtasks, list) else 0
    text_lower = response
    conditional_keywords = ("시나리오", "경우", "이면", "조건", "5%", "2%")
    dependency_keywords = ("결정한 뒤", "다음", "이후", "추린", "선정한", "선택한")
    return {
        "valid_json": parsed is not None and "subtasks" in (parsed or {}),
        "n_subtasks": n_subtasks,
        "has_conditional": any(k in text_lower for k in conditional_keywords),
        "has_dependency": any(k in text_lower for k in dependency_keywords),
    }


def grade_reflect(response: str, *, expect_issues: bool) -> dict:
    """reflect: 3-dim coverage + NO_ISSUES decision correctness.

    Hard fixture has 3 planted defects; expected output is a critique
    touching all 3 dimensions (모순/누락/모호), NOT NO_ISSUES.
    Easy fixture's draft is clean; either NO_ISSUES or a soft critique
    is acceptable — we score on detection coverage and decision agreement.
    """
    text = response.strip()
    no_issues = text.upper().startswith("NO_ISSUES")
    contradiction = "모순" in text
    missing = "누락" in text
    ambiguous = "모호" in text
    coverage = sum([contradiction, missing, ambiguous])
    # Decision-correctness: hard => should NOT say NO_ISSUES; easy => may.
    decision_correct = (not no_issues) if expect_issues else True
    return {
        "no_issues": no_issues,
        "dim_contradiction": contradiction,
        "dim_missing": missing,
        "dim_ambiguous": ambiguous,
        "dim_coverage": coverage,
        "decision_correct": decision_correct,
    }


def grade_verify(response: str, *, expect_grounded: bool, expect_unsupported_min: int) -> dict:
    """verify: JSON validity + grounded judgment + unsupported list size."""
    parsed: dict | None = None
    try:
        parsed = json.loads(_strip_json_fence(response))
    except (json.JSONDecodeError, ValueError):
        parsed = None
    valid_json = isinstance(parsed, dict) and "grounded" in parsed and "unsupported" in parsed
    grounded = parsed.get("grounded") if valid_json else None
    unsupported = parsed.get("unsupported", []) if valid_json else []
    n_unsupported = len(unsupported) if isinstance(unsupported, list) else 0
    judgment_correct = (grounded == expect_grounded) if valid_json else False
    list_adequate = n_unsupported >= expect_unsupported_min
    return {
        "valid_json": valid_json,
        "grounded": grounded,
        "n_unsupported": n_unsupported,
        "judgment_correct": judgment_correct,
        "list_adequate": list_adequate,
    }


def grade_synthesis_easy(response: str) -> dict:
    """synthesis easy: existing §16 measurement — visible chars + decision presence."""
    text = response
    return {
        "response_chars": len(text),
        "has_decision": any(k in text for k in (
            "Recommend", "Accept", "Reject", "Eligible", "Apply",
            "권장", "거부", "수용", "거절",
        )),
    }


def grade_synthesis_hard(response: str) -> dict:
    """synthesis hard: 3-entity coverage + conflict flagging.

    Hard fixture asks for a 3-way ETF comparison and includes one
    internal conflict (VOO 0.03% vs 0.05%). A reasoning answer should
    (a) mention all three ETFs, (b) flag the conflict.
    """
    text = response
    ents = ("VOO", "IVV", "SPY")
    coverage = sum(1 for e in ents if e in text)
    conflict_keywords = (
        "conflict", "conflicting", "contradict", "discrepan",
        "충돌", "상충", "모순", "차이", "vs", "vs.",
    )
    has_conflict_flag = any(k in text for k in conflict_keywords)
    has_both_fees = ("0.03" in text and "0.05" in text)
    return {
        "response_chars": len(text),
        "n_entity_coverage": coverage,
        "all_entities_covered": coverage == len(ents),
        "has_conflict_flag": has_conflict_flag,
        "has_both_fee_numbers": has_both_fees,
    }


def grade_rewriter(response: str, *, hard: bool) -> dict:
    """query_rewriter: JSON validity + (hard) concept-anchor presence."""
    parsed: dict | None = None
    try:
        parsed = json.loads(_strip_json_fence(response))
    except (json.JSONDecodeError, ValueError):
        parsed = None
    valid_json = isinstance(parsed, dict) and "rewritten" in parsed
    rewritten = parsed.get("rewritten", "") if valid_json else ""
    out = {
        "valid_json": valid_json,
        "rewritten_chars": len(rewritten) if isinstance(rewritten, str) else 0,
    }
    if hard:
        # F7 finding: "MCP" alone does not match the chroma chunks; the
        # concept anchor "Model Context Protocol" (or originator entity)
        # is required. A reasoning rewrite should add at least one.
        anchor_keywords = (
            "Model Context Protocol", "model context protocol",
            "프로토콜", "Anthropic", "anthropic",
        )
        out["has_concept_anchor"] = (
            isinstance(rewritten, str)
            and any(k in rewritten for k in anchor_keywords)
        )
    return out


GRADERS: dict[str, dict] = {
    "planner": {
        "easy": lambda r: grade_planner(r),
        "hard": lambda r: grade_planner(r),
    },
    "reflect": {
        "easy": lambda r: grade_reflect(r, expect_issues=False),
        "hard": lambda r: grade_reflect(r, expect_issues=True),
    },
    "verify": {
        "easy": lambda r: grade_verify(r, expect_grounded=True, expect_unsupported_min=0),
        "hard": lambda r: grade_verify(r, expect_grounded=False, expect_unsupported_min=2),
    },
    "synthesis": {
        "easy": grade_synthesis_easy,
        "hard": grade_synthesis_hard,
    },
    "query_rewriter": {
        "easy": lambda r: grade_rewriter(r, hard=False),
        "hard": lambda r: grade_rewriter(r, hard=True),
    },
}


# ────────────────────────────────────────────────────────────────────
# Driver
# ────────────────────────────────────────────────────────────────────


def run_cell(prompt: str, *, think: bool, n: int, stage: str, fixture: str,
             grader, model: str, cap: int, temp: float) -> list[dict]:
    rows: list[dict] = []
    for i in range(n):
        print(f"  [{stage}/{fixture}/think={think}/{i+1}/{n}] ... ",
              end="", flush=True)
        r = call_ollama(prompt, think=think, model=model, cap=cap, temp=temp)
        if "_error" in r:
            print(f"ERROR {r['_error']}")
            rows.append({"_error": r["_error"], "run_idx": i + 1})
            continue
        signals = grader(r["response"])
        row = {
            "run_idx": i + 1,
            "elapsed_s": r["elapsed_s"],
            "eval_count": r["eval_count"],
            "response_chars": r["response_chars"],
            "done_reason": r["done_reason"],
            "non_empty": r["non_empty"],
            **signals,
        }
        rows.append(row)
        print(
            f"{r['elapsed_s']:.1f}s eval={r['eval_count']} "
            f"chars={r['response_chars']}"
        )
    return rows


def _mean(values: list) -> float | None:
    nums = [v for v in values if isinstance(v, (int, float))]
    return round(statistics.mean(nums), 2) if nums else None


def _frac_true(values: list) -> float | None:
    bools = [v for v in values if isinstance(v, bool)]
    return round(sum(bools) / len(bools), 2) if bools else None


def summarise(rows: list[dict]) -> dict:
    """Aggregate per-cell: budget stats + grader signal means/fractions."""
    ok = [r for r in rows if "_error" not in r]
    if not ok:
        return {"n_ok": 0, "errors": len(rows)}
    keys = sorted({k for r in ok for k in r.keys()})
    out: dict = {"n_ok": len(ok), "errors": len(rows) - len(ok)}
    for k in keys:
        if k in ("run_idx", "done_reason"):
            continue
        vals = [r.get(k) for r in ok]
        if all(isinstance(v, bool) for v in vals):
            out[k + "_frac"] = _frac_true(vals)
        elif all(isinstance(v, (int, float)) for v in vals if v is not None):
            out[k + "_mean"] = _mean(vals)
        else:
            # Mixed (e.g. grounded may be True/False/None).
            tvals = [v for v in vals if isinstance(v, bool)]
            if tvals:
                out[k + "_true_frac"] = round(sum(tvals) / len(vals), 2)
    return out


def verdict(stage: str, fixture: str, on: dict, off: dict) -> tuple[str, str]:
    """Per-cell think-policy verdict + one-line rationale.

    Heuristic: compare the stage's dominant quality metric think=True
    vs think=False, plus the budget reclaim (eval_count).
    """
    if on.get("n_ok", 0) == 0 or off.get("n_ok", 0) == 0:
        return "ERROR", "no successful runs on one side"
    reclaim = (on.get("eval_count_mean") or 0) - (off.get("eval_count_mean") or 0)
    # Choose the stage's primary quality metric.
    if stage == "planner":
        m_on = on.get("valid_json_frac", 0) + (on.get("n_subtasks_mean") or 0) / 5
        m_off = off.get("valid_json_frac", 0) + (off.get("n_subtasks_mean") or 0) / 5
        if fixture == "hard":
            m_on += on.get("has_conditional_frac", 0) + on.get("has_dependency_frac", 0)
            m_off += off.get("has_conditional_frac", 0) + off.get("has_dependency_frac", 0)
    elif stage == "reflect":
        m_on = (on.get("dim_coverage_mean") or 0) / 3 + on.get("decision_correct_frac", 0)
        m_off = (off.get("dim_coverage_mean") or 0) / 3 + off.get("decision_correct_frac", 0)
    elif stage == "verify":
        m_on = on.get("valid_json_frac", 0) + on.get("judgment_correct_frac", 0) + on.get("list_adequate_frac", 0)
        m_off = off.get("valid_json_frac", 0) + off.get("judgment_correct_frac", 0) + off.get("list_adequate_frac", 0)
    elif stage == "synthesis":
        if fixture == "hard":
            m_on = (on.get("n_entity_coverage_mean") or 0) / 3 + on.get("has_conflict_flag_frac", 0)
            m_off = (off.get("n_entity_coverage_mean") or 0) / 3 + off.get("has_conflict_flag_frac", 0)
        else:
            m_on = on.get("has_decision_frac", 0)
            m_off = off.get("has_decision_frac", 0)
    elif stage == "query_rewriter":
        m_on = on.get("valid_json_frac", 0)
        m_off = off.get("valid_json_frac", 0)
        if fixture == "hard":
            m_on += on.get("has_concept_anchor_frac", 0)
            m_off += off.get("has_concept_anchor_frac", 0)
    else:
        return "?", "no policy for stage"
    delta = m_on - m_off
    if abs(delta) < 0.15:
        return "think=OFF safe", (
            f"quality tie (Δ={delta:+.2f}); budget reclaim "
            f"{reclaim:.0f} tok"
        )
    if delta > 0:
        return "think=ON needed", (
            f"quality drops {delta:+.2f} without thinking; reclaim "
            f"{reclaim:.0f} tok not worth it"
        )
    return "think=OFF wins", (
        f"think=OFF higher quality by {-delta:+.2f}; reclaim "
        f"{reclaim:.0f} tok bonus"
    )


def render_report(results: dict) -> str:
    meta = results["metadata"]
    lines: list[str] = [
        "# A3 — think-mode quality boundary (gemma4:e4b, 5 cognitive stages)",
        "",
        f"**Date**: {meta['started_utc']}",
        f"**Model**: {meta['model']}  **Cap**: {meta['cap']}  "
        f"**Temp**: {meta['temperature']}  **n/cell**: {meta['n']}",
        "**Closes**: §17.5.3 of v3prime-cross-family-final-2026-05-29.md",
        "",
        "## Per-stage verdicts (feeds A2 per-stage think policy)",
        "",
        "| Stage | Fixture | think=ON eval | think=OFF eval | reclaim | "
        "primary quality (ON / OFF) | verdict | rationale |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for stage in meta["stages"]:
        for fixture in meta["fixtures"]:
            cell = results["cells"][stage][fixture]
            on = cell["think_on"]["summary"]
            off = cell["think_off"]["summary"]
            on_eval = on.get("eval_count_mean") or 0
            off_eval = off.get("eval_count_mean") or 0
            reclaim = on_eval - off_eval
            v, why = verdict(stage, fixture, on, off)
            # Pick a concise quality signal per stage for the table.
            if stage == "planner":
                q_on = f"sub={on.get('n_subtasks_mean')}/json={on.get('valid_json_frac')}"
                q_off = f"sub={off.get('n_subtasks_mean')}/json={off.get('valid_json_frac')}"
            elif stage == "reflect":
                q_on = f"cov={on.get('dim_coverage_mean')}/dec={on.get('decision_correct_frac')}"
                q_off = f"cov={off.get('dim_coverage_mean')}/dec={off.get('decision_correct_frac')}"
            elif stage == "verify":
                q_on = (f"json={on.get('valid_json_frac')}/jdg="
                        f"{on.get('judgment_correct_frac')}/uns="
                        f"{on.get('n_unsupported_mean')}")
                q_off = (f"json={off.get('valid_json_frac')}/jdg="
                         f"{off.get('judgment_correct_frac')}/uns="
                         f"{off.get('n_unsupported_mean')}")
            elif stage == "synthesis":
                if fixture == "hard":
                    q_on = (f"ent={on.get('n_entity_coverage_mean')}/3,"
                            f"conf={on.get('has_conflict_flag_frac')}")
                    q_off = (f"ent={off.get('n_entity_coverage_mean')}/3,"
                             f"conf={off.get('has_conflict_flag_frac')}")
                else:
                    q_on = (f"dec={on.get('has_decision_frac')},"
                            f"chars={on.get('response_chars_mean')}")
                    q_off = (f"dec={off.get('has_decision_frac')},"
                             f"chars={off.get('response_chars_mean')}")
            else:  # query_rewriter
                q_on = f"json={on.get('valid_json_frac')}"
                q_off = f"json={off.get('valid_json_frac')}"
                if fixture == "hard":
                    q_on += f"/anchor={on.get('has_concept_anchor_frac')}"
                    q_off += f"/anchor={off.get('has_concept_anchor_frac')}"
            lines.append(
                f"| {stage} | {fixture} | {on_eval:.0f} | {off_eval:.0f} | "
                f"-{reclaim:.0f} | {q_on} / {q_off} | **{v}** | {why} |"
            )
    lines += [
        "",
        "## Reading",
        "",
        "- `eval` = `eval_count` mean across n samples. think=ON includes the",
        "  default-on hidden thinking trace (§16); think=OFF disables it.",
        "- `reclaim` = budget recovered if we flip the stage to think=OFF.",
        "- Primary quality signal differs per stage (see grader docstrings",
        "  in the driver). Verdict heuristic: |Δquality| < 0.15 → OFF safe.",
        "- Hard fixtures planted explicit reasoning targets so a non-",
        "  reasoning answer is detectable (multi-hop conditional, planted",
        "  defects, hallucinated claims, 3-way comparison with conflict,",
        "  multi-hop entity anchor). Easy fixtures are the §16 baseline.",
        "",
        "## A2 feed-through",
        "",
        "Stages with **think=OFF safe** verdict on hard fixture are",
        "candidates for A2 to force `think=false` in the call site",
        "(reclaims ~85% of budget per call on e4b). Stages with",
        "**think=ON needed** should keep the default (and the per-stage",
        "cap must stay ≥ ~500 to leave the thinking trace room).",
        "",
        "Artifact: this driver is self-contained, deterministic graders",
        "only. No LLM-judge dependency. v2 (LLM-judge with gemma3:12b as",
        "tie-breaker) is a follow-up if any cell lands in `ambiguous`.",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="A3 think-mode quality boundary")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--cap", type=int, default=DEFAULT_CAP)
    ap.add_argument("--temp", type=float, default=DEFAULT_TEMP)
    ap.add_argument("--n", type=int, default=DEFAULT_N,
                    help="samples per (stage × fixture × think) cell")
    ap.add_argument("--stages", default="planner,reflect,verify,synthesis,query_rewriter")
    ap.add_argument("--fixtures", default="easy,hard")
    args = ap.parse_args()

    stages = [s.strip() for s in args.stages.split(",") if s.strip()]
    fixtures = [f.strip() for f in args.fixtures.split(",") if f.strip()]

    easy = build_easy_prompts()
    hard = build_hard_prompts()
    prompts: dict[str, dict[str, str]] = {
        s: {"easy": easy[s], "hard": hard[s]} for s in stages
    }

    started = datetime.now(timezone.utc).isoformat()
    results: dict = {
        "metadata": {
            "started_utc": started,
            "driver": "v3prime_a3_think_quality_boundary.py",
            "model": args.model,
            "cap": args.cap,
            "temperature": args.temp,
            "n": args.n,
            "stages": stages,
            "fixtures": fixtures,
            "closes": "§17.5.3 v3prime-cross-family-final-2026-05-29.md",
        },
        "cells": {},
    }

    n_cells = len(stages) * len(fixtures) * 2
    print(f"A3 — {n_cells} cells × n={args.n} = {n_cells * args.n} calls\n")
    for stage in stages:
        results["cells"][stage] = {}
        for fixture in fixtures:
            grader = GRADERS[stage][fixture]
            prompt = prompts[stage][fixture]
            results["cells"][stage][fixture] = {}
            for label, think in (("think_on", True), ("think_off", False)):
                rows = run_cell(
                    prompt, think=think, n=args.n, stage=stage,
                    fixture=fixture, grader=grader,
                    model=args.model, cap=args.cap, temp=args.temp,
                )
                results["cells"][stage][fixture][label] = {
                    "rows": rows,
                    "summary": summarise(rows),
                }

    results["metadata"]["finished_utc"] = datetime.now(timezone.utc).isoformat()

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    REPORTS.mkdir(parents=True, exist_ok=True)
    json_path = REPORTS / f"v3prime-a3-think-quality-boundary-{ts}.json"
    md_path = REPORTS / f"v3prime-a3-think-quality-boundary-{ts}.md"
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    md = render_report(results)
    md_path.write_text(md, encoding="utf-8")
    print(f"\nJSON: {json_path}")
    print(f"MD:   {md_path}\n")
    print(md)


if __name__ == "__main__":
    main()
