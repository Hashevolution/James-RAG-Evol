"""A3 v2 — LLM-judge confirmation on the 3 surprising A3 cells.

A3 (PR #608) used deterministic graders only. v2 is the reserved-trigger
LLM-judge upgrade gated to the 3 cells most worth a second opinion:

  - verify EASY    — A3 grader said think=ON judgment_correct=0.6 (3/5
                     wrong) vs think=OFF=1.0. Biggest "overthinking
                     hurts" signal — is it real, or did the grader
                     mis-parse 3 perfectly fine answers?
  - synthesis HARD — A3 grader said think=ON conflict_flag=0.4 (2/5)
                     vs think=OFF=1.0 (5/5). Biggest "think=OFF wins"
                     signal — is the OFF answer actually clearer about
                     the planted VOO 0.03% vs 0.05% conflict, or did
                     the keyword grader miss nuanced ON answers?
  - planner HARD   — A3 grader said Δ=+0.04 (essentially tie). Middle
                     case: sanity check that judge agrees "tie" rather
                     than "ON micro-wins" (which would flag the grader
                     as too coarse).

Method
------
1. **Regenerate** the n=5 paired outputs per cell (A3 stored only
   signals, not raw text). Same fixture, model (gemma4:e4b), cap=4096,
   temp=0.2, n=5, with full response captured this time.
2. **Paired judge** on gemma3:12b (local, no external API). For each
   of the 5 pairs, judge twice with the A/B positions swapped — this
   controls for position bias (a known LLM-judge failure mode).
3. **Per-pair verdict**: A_wins / B_wins / tie. A pair is "agreement"
   only when both positional runs yield the same winner OR both say
   tie. Disagreement (position-dependent verdict) → mark "position-
   biased" and exclude from the cell verdict.
4. **Cell verdict**: aggregate winners across the n=5 agreed pairs.
   Compare to A3 grader's direction.

Output: JSON dump + markdown report. cp949-safe.

If judge agrees with A3 on all 3 cells → A3 grader strengthened →
A2 default-flip plan stays on schedule. If judge disagrees on any
cell → flag it, walk back the default-flip plan for that stage,
keep the opt-in shipping behaviour.

Cost: ~30 e4b generation calls (~10s each, ~5 min) + 30 judge calls
(~15s each on gemma3:12b, ~7-8 min) = ~12-13 min total.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
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
GEN_MODEL = "gemma4:e4b"
JUDGE_MODEL = "gemma3:12b"
DEFAULT_TEMP = 0.2
DEFAULT_CAP = 4096
DEFAULT_N = 5
GEN_TIMEOUT = 180.0
JUDGE_TIMEOUT = 240.0


# Reuse the A3 driver's fixture builders so the prompts are byte-identical.
def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, RESEARCH / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


a3 = _load("v3prime_a3_think_quality_boundary")
EASY = a3.build_easy_prompts()
HARD = a3.build_hard_prompts()


# ────────────────────────────────────────────────────────────────────
# Cell selection — the 3 surprising A3 cells worth a judge.
# ────────────────────────────────────────────────────────────────────


CELLS: list[dict] = [
    {
        "stage": "verify",
        "fixture": "easy",
        "prompt": EASY["verify"],
        "a3_verdict": "OFF wins (judgment_correct 0.6 ON vs 1.0 OFF)",
        # Judge criterion phrased for verify: which answer's grounded/
        # unsupported judgment is more accurate against the provided context?
        "criterion_ko": (
            "각 답변은 [질문]/[답변]/[내부 자료] 묶음에 대한 검증 결과 (grounded 여부 "
            "+ unsupported 주장 리스트) 를 JSON 으로 반환한다. 더 정확한 판단을 "
            "한 쪽을 고르라: (a) grounded 값이 자료 지지/모순 상태와 일치하는가, "
            "(b) unsupported 리스트가 실제 자료에 없는/모순되는 주장만 정확히 "
            "잡았는가. 두 판단이 동등하게 정확하면 'tie'."
        ),
    },
    {
        "stage": "synthesis",
        "fixture": "hard",
        "prompt": HARD["synthesis"],
        "a3_verdict": "OFF wins (conflict_flag 0.4 ON vs 1.0 OFF)",
        "criterion_ko": (
            "각 답변은 VOO / IVV / SPY 세 ETF 의 (expense ratio, AUM, issuer) "
            "비교를 작성한다. 문서 안에 VOO 의 expense ratio 가 0.03% vs 0.05% "
            "두 값으로 충돌한다 — 좋은 답변은 이 충돌을 명시적으로 지적해야 "
            "한다. 더 나은 답변을 고르라: (a) 세 ETF 모두 다루는가, (b) "
            "fee 충돌을 명시했는가, (c) 비교가 명료한가. 동등하면 'tie'."
        ),
    },
    {
        "stage": "planner",
        "fixture": "hard",
        "prompt": HARD["planner"],
        "a3_verdict": "tie (Δ=+0.04, sanity check)",
        "criterion_ko": (
            "각 답변은 다단계 조건부 질문을 subtasks JSON 으로 분해한다. 더 "
            "나은 분해를 고르라: (a) 인플레이션 시나리오 분기를 포함했는가, "
            "(b) '자산군 결정 → ETF 추리기' 의존성 순서가 자연스러운가, "
            "(c) subtask 가 짧고 명령형인가. 동등하면 'tie'."
        ),
    },
]


# ────────────────────────────────────────────────────────────────────
# Ollama call (gen + judge)
# ────────────────────────────────────────────────────────────────────


def gen_call(prompt: str, *, think: bool, model: str = GEN_MODEL,
             cap: int = DEFAULT_CAP, temp: float = DEFAULT_TEMP,
             timeout: float = GEN_TIMEOUT) -> dict:
    body = json.dumps({
        "model": model, "prompt": prompt, "stream": False, "think": think,
        "options": {"num_predict": cap, "temperature": temp},
    }).encode("utf-8")
    req = request.Request(GEN_URL, data=body, method="POST",
                          headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (error.HTTPError, error.URLError) as e:
        return {"_error": str(e), "elapsed_s": round(time.monotonic() - t0, 2)}
    return {
        "elapsed_s": round(time.monotonic() - t0, 2),
        "response": payload.get("response", "") or "",
        "eval_count": payload.get("eval_count") or 0,
        "done_reason": payload.get("done_reason", "?"),
    }


JUDGE_PROMPT_KO = (
    "당신은 답변 품질 평가 심판입니다. 같은 입력에 대한 두 답변 (A, B) 중 어느 "
    "쪽이 평가 기준을 더 잘 만족하는지 판단하세요. **편향 방지를 위해 답변 길이 "
    "/ 형식 / 순서에 영향받지 말고, 평가 기준에만 집중하세요.**\n\n"
    "[입력]\n{prompt}\n\n"
    "[답변 A]\n{a}\n\n"
    "[답변 B]\n{b}\n\n"
    "[평가 기준]\n{criterion}\n\n"
    "JSON 으로만 응답:\n"
    '{{"verdict": "A_wins" | "B_wins" | "tie", "rationale": "한 줄 이유 (50자 이내)"}}'
)


def judge_call(prompt: str, a: str, b: str, criterion: str, *,
               model: str = JUDGE_MODEL, temp: float = DEFAULT_TEMP,
               timeout: float = JUDGE_TIMEOUT) -> dict:
    full = JUDGE_PROMPT_KO.format(prompt=prompt, a=a, b=b, criterion=criterion)
    body = json.dumps({
        "model": model, "prompt": full, "stream": False,
        "options": {"num_predict": 512, "temperature": temp},
    }).encode("utf-8")
    req = request.Request(GEN_URL, data=body, method="POST",
                          headers={"Content-Type": "application/json"})
    t0 = time.monotonic()
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (error.HTTPError, error.URLError) as e:
        return {"_error": str(e), "elapsed_s": round(time.monotonic() - t0, 2)}
    raw = payload.get("response", "") or ""
    parsed = _parse_judge(raw)
    return {
        "elapsed_s": round(time.monotonic() - t0, 2),
        "raw": raw,
        "verdict": parsed.get("verdict"),
        "rationale": parsed.get("rationale", ""),
        "eval_count": payload.get("eval_count") or 0,
    }


_JUDGE_JSON_RE = re.compile(r'\{[^{}]*"verdict"\s*:\s*"(A_wins|B_wins|tie)"', re.DOTALL)


def _parse_judge(text: str) -> dict:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t)
    try:
        blob = json.loads(t)
        if isinstance(blob, dict) and blob.get("verdict") in ("A_wins", "B_wins", "tie"):
            return {"verdict": blob["verdict"],
                    "rationale": (blob.get("rationale", "") or "")[:200]}
    except (json.JSONDecodeError, ValueError):
        pass
    m = _JUDGE_JSON_RE.search(text)
    if m:
        return {"verdict": m.group(1), "rationale": ""}
    return {"verdict": None, "rationale": ""}


# ────────────────────────────────────────────────────────────────────
# Per-cell run: generate n pairs (think on/off), then judge each pair
# in both positions (bias control).
# ────────────────────────────────────────────────────────────────────


def run_cell(cell: dict, *, n: int) -> dict:
    stage = cell["stage"]
    fixture = cell["fixture"]
    prompt = cell["prompt"]
    crit = cell["criterion_ko"]

    print(f"\n=== {stage}/{fixture} — A3 verdict: {cell['a3_verdict']} ===")
    print(f"Generating {n} pairs (think on/off) on {GEN_MODEL}...")
    pairs: list[dict] = []
    for i in range(n):
        on = gen_call(prompt, think=True)
        off = gen_call(prompt, think=False)
        pairs.append({"idx": i + 1, "on": on, "off": off})
        on_chars = len(on.get("response", ""))
        off_chars = len(off.get("response", ""))
        print(f"  pair {i+1}: ON eval={on.get('eval_count')} chars={on_chars} "
              f"| OFF eval={off.get('eval_count')} chars={off_chars}")

    print(f"Judging {2 * n} judgments ({JUDGE_MODEL}, both positions per pair)...")
    judgements: list[dict] = []
    for p in pairs:
        on_text = p["on"].get("response", "")
        off_text = p["off"].get("response", "")
        # Position 1: A=ON, B=OFF
        j1 = judge_call(prompt, on_text, off_text, crit)
        # Position 2: A=OFF, B=ON (swap)
        j2 = judge_call(prompt, off_text, on_text, crit)

        # Translate raw verdicts back to think-mode (so A/B position is
        # neutralised). pos1: A_wins → ON wins ; B_wins → OFF wins.
        # pos2: A_wins → OFF wins ; B_wins → ON wins.
        def _to_mode(verdict: str | None, swapped: bool) -> str | None:
            if verdict == "tie":
                return "tie"
            if verdict == "A_wins":
                return "OFF" if swapped else "ON"
            if verdict == "B_wins":
                return "ON" if swapped else "OFF"
            return None

        mode_pos1 = _to_mode(j1.get("verdict"), swapped=False)
        mode_pos2 = _to_mode(j2.get("verdict"), swapped=True)

        if mode_pos1 is None or mode_pos2 is None:
            agreement = "judge_parse_fail"
            agreed_mode = None
        elif mode_pos1 == mode_pos2:
            agreement = "agreed"
            agreed_mode = mode_pos1
        else:
            agreement = "position_biased"
            agreed_mode = None

        judgements.append({
            "pair_idx": p["idx"],
            "pos1": {"verdict": j1.get("verdict"), "mode": mode_pos1,
                     "rationale": j1.get("rationale")},
            "pos2": {"verdict": j2.get("verdict"), "mode": mode_pos2,
                     "rationale": j2.get("rationale")},
            "agreement": agreement,
            "agreed_mode": agreed_mode,
        })
        print(f"  pair {p['idx']}: pos1={mode_pos1} pos2={mode_pos2} -> "
              f"{agreement}/{agreed_mode}")

    # Cell aggregate
    agreed = [j for j in judgements if j["agreement"] == "agreed"]
    n_on = sum(1 for j in agreed if j["agreed_mode"] == "ON")
    n_off = sum(1 for j in agreed if j["agreed_mode"] == "OFF")
    n_tie = sum(1 for j in agreed if j["agreed_mode"] == "tie")
    n_biased = sum(1 for j in judgements if j["agreement"] == "position_biased")
    n_fail = sum(1 for j in judgements if j["agreement"] == "judge_parse_fail")

    if n_off > n_on:
        judge_direction = "OFF wins"
    elif n_on > n_off:
        judge_direction = "ON wins"
    else:
        judge_direction = "tie"
    return {
        "stage": stage,
        "fixture": fixture,
        "a3_verdict": cell["a3_verdict"],
        "pairs": pairs,
        "judgements": judgements,
        "tally": {
            "agreed": len(agreed),
            "ON_wins": n_on,
            "OFF_wins": n_off,
            "tie": n_tie,
            "position_biased": n_biased,
            "judge_parse_fail": n_fail,
        },
        "judge_direction": judge_direction,
    }


def render_report(results: dict) -> str:
    meta = results["metadata"]
    out: list[str] = [
        "# A3 v2 — LLM-judge confirmation on 3 surprising A3 cells",
        "",
        f"**Date**: {meta['started_utc']}",
        f"**Generator**: {GEN_MODEL}  **Judge**: {JUDGE_MODEL}  "
        f"**Cap**: {meta['cap']}  **Temp**: {meta['temperature']}  "
        f"**n pairs/cell**: {meta['n']}",
        "**Closes**: A3 (#608) LLM-judge reservation gate; feeds A2 (#609) "
        "default-flip follow-up decision.",
        "",
        "## Verdicts",
        "",
        "| Cell | A3 (det. grader) | judge tally (ON/OFF/tie/biased/fail) | "
        "judge direction | agreement w/ A3 |",
        "|---|---|---|---|---|",
    ]
    for cell in results["cells"]:
        t = cell["tally"]
        tally_str = (f"{t['ON_wins']}/{t['OFF_wins']}/{t['tie']}/"
                     f"{t['position_biased']}/{t['judge_parse_fail']}")
        a3_dir = "OFF" if "OFF wins" in cell["a3_verdict"] else (
            "tie" if "tie" in cell["a3_verdict"] else "?"
        )
        jd = cell["judge_direction"]
        if a3_dir == "OFF" and jd == "OFF wins":
            agree = "AGREE"
        elif a3_dir == "tie" and jd == "tie":
            agree = "AGREE"
        elif a3_dir == "tie" and jd in ("OFF wins", "ON wins"):
            # tie in grader but judge picks one — grader was too coarse
            agree = f"weaker tie (judge: {jd})"
        elif a3_dir == "OFF" and jd == "tie":
            agree = "WEAKER (judge: tie)"
        elif a3_dir == "OFF" and jd == "ON wins":
            agree = "DISAGREE (judge: ON wins)"
        else:
            agree = f"check ({a3_dir} vs {jd})"
        out.append(f"| {cell['stage']}/{cell['fixture']} | {cell['a3_verdict']} "
                   f"| {tally_str} | **{jd}** | {agree} |")
    out += [
        "",
        "Tally column order: **ON_wins / OFF_wins / tie / position_biased / judge_parse_fail** "
        "(`n_pairs={n}` so the first four sum to ≤ n_pairs).".format(n=meta["n"]),
        "",
        "## Reading",
        "",
        "- **Agreement methodology**: each pair is judged TWICE with A/B "
        "positions swapped. A pair counts as 'agreed' only if both positions "
        "yield the same winner (or both say tie); else 'position_biased' and "
        "excluded from the tally.",
        "- **Cell verdict**: aggregate of agreed pairs only. A judge_direction "
        "of 'OFF wins' / 'ON wins' / 'tie' is reported by majority among "
        "agreed pairs.",
        "- **A2 default-flip gate**: 3 AGREE → A3 strengthened → next gate "
        "is 1-week real-query dogfood + Quality Delta Card. Any DISAGREE → "
        "stage walks back from the A2 safe-list (opt-in still ships).",
        "",
        "## Per-pair rationales (sampling)",
        "",
    ]
    for cell in results["cells"]:
        out.append(f"### {cell['stage']}/{cell['fixture']}")
        for j in cell["judgements"]:
            out.append(
                f"- pair {j['pair_idx']}: pos1={j['pos1']['mode']} "
                f"({j['pos1']['rationale'][:60]!r}), pos2={j['pos2']['mode']} "
                f"({j['pos2']['rationale'][:60]!r}) → {j['agreement']}"
                f"/{j['agreed_mode']}"
            )
        out.append("")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=DEFAULT_N)
    ap.add_argument("--cap", type=int, default=DEFAULT_CAP)
    ap.add_argument("--temp", type=float, default=DEFAULT_TEMP)
    args = ap.parse_args()

    started = datetime.now(timezone.utc).isoformat()
    results: dict = {
        "metadata": {
            "started_utc": started,
            "driver": "v3prime_a3_v2_llm_judge.py",
            "generator_model": GEN_MODEL,
            "judge_model": JUDGE_MODEL,
            "cap": args.cap,
            "temperature": args.temp,
            "n": args.n,
            "cells_selected": [(c["stage"], c["fixture"]) for c in CELLS],
            "closes": "A3 LLM-judge reservation gate (PR #608 §reservation)",
        },
        "cells": [],
    }
    print(f"A3 v2 — {len(CELLS)} cells × n={args.n} pairs × 2 judge positions "
          f"= {len(CELLS) * args.n} gen-pair + {len(CELLS) * args.n * 2} judge calls\n")

    for cell in CELLS:
        cell_result = run_cell(cell, n=args.n)
        results["cells"].append(cell_result)

    results["metadata"]["finished_utc"] = datetime.now(timezone.utc).isoformat()
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    REPORTS.mkdir(parents=True, exist_ok=True)
    json_path = REPORTS / f"v3prime-a3-v2-llm-judge-{ts}.json"
    md_path = REPORTS / f"v3prime-a3-v2-llm-judge-{ts}.md"
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    md = render_report(results)
    md_path.write_text(md, encoding="utf-8")
    print(f"\nJSON: {json_path}\nMD:   {md_path}\n")
    print(md)


if __name__ == "__main__":
    main()
