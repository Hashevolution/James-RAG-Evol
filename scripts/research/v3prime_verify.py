"""V3'.d — verify.fact_check cap-budget single-variable replication.

Tests whether raising ``num_predict`` from the JAMES pre-#399 default
(400) to 4096 recovers the empty-response rate seen on the
``verify.fact_check`` stage in the 2026-05-18 cognitive-stages eval.

Companion to V3'.a (query_rewriter, 200 → 4096, 0/10 → 10/10
confirmed), V3'.b (planner, 400 → 4096, 0/10 → 10/10 confirmed),
and V3'.c (reflect.critique, 400 → 4096, pending). V3'.d closes the
4-stage cognitive cap-budget validation set and provides the
in-house **post-merge validation** that PR #399's bump of
``DEFAULT_FACT_CHECK_MAX_TOKENS`` (400 → 4096) is what fixed the
empty-response pattern at this stage.

References
----------
- ``reports/promo-assets/gemma4-e4b-cognitive-stages-eval.md`` —
  2026-05-18 eval; verify.fact_check returned 0 chars at 4.3s on
  ``gemma4:e4b`` (control ``gemma3:12b`` passed at 1.17s with
  ``{"grounded": true, "unsupported": []}`` valid JSON)
- ``docs/research/gemma4-experiment-validation-plan.md`` §4.3 —
  V3' design
- ``scripts/research/v3prime_query_rewriter.py`` (V3'.a) +
  ``scripts/research/v3prime_planner.py`` (V3'.b) +
  ``scripts/research/v3prime_reflect.py`` (V3'.c) — companion drivers
- PR #399 — reasoning cap defaults bumped above the ~500-token
  reasoning floor (current ``DEFAULT_FACT_CHECK_MAX_TOKENS = 4096``
  at ``core/reasoning/verify.py:73``)

Method
------
Single-variable isolation:

    Held constant: model, prompt template, query, answer, context,
                   temperature, server
    Variable:      num_predict ∈ {400, 4096}

Prompt template pinned verbatim from
``core/reasoning/verify.py:149`` (``FACT_CHECK_PROMPT_KO``).

Three fixtures
--------------
``verify.fact_check`` requires three inputs: ``query``, ``answer``,
and ``context`` (retrieved internal data). To preserve reproducibility
and avoid multi-stage variance, all three are static fixtures shaped
after the 2026-05-18 eval's measured inputs. The fixture answer
matches V3'.c's draft to keep cross-stage comparability.

Usage
-----
::

    python scripts/research/v3prime_verify.py
    python scripts/research/v3prime_verify.py --n 20

Outputs ``reports/research-runs/v3prime-verify-<UTC>.json`` plus a
stdout summary with a decision-tree interpretation.

Decision rule
-------------
* ≥ 9/10 success at ``num_predict=4096`` AND ≤ 3/10 at 400
  → hypothesis B-budget confirmed for verify.fact_check — completes
    the 4-stage replication set. PR #399's cap bump is fully validated
    across all four cognitive stages → 4-stage sweep PR (the
    "third deployment context" Ali described) ready to anchor with
    STEP 7 bench numbers in the body.
* Similar rates at both caps
  → cap is not the variable for verify.fact_check — different
    mechanism (revisit before the 4-stage PR description)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request

# ────────────────────────────────────────────────────────────────────
# Prompt — pinned from core/reasoning/verify.py:149.
# DO NOT auto-sync. If the JAMES module changes, this script's
# results describe the prompt at the commit it was run against.
# ────────────────────────────────────────────────────────────────────
FACT_CHECK_PROMPT_KO = (
    "아래 답변의 핵심 주장들이 제공된 [내부 자료] 에 의해 직접 지지되는지 "
    "검증하라.\n\n"
    "[질문]\n{query}\n\n"
    "[답변]\n{answer}\n\n"
    "[내부 자료]\n{context}\n\n"
    "검증 규칙:\n"
    "- 답변 안의 명시적 주장 (사실 / 수치 / 인용) 만 대상으로 함\n"
    "- 자료가 지지하는 주장은 통과; 자료에 없거나 모순되는 주장만 'unsupported'\n"
    "- 일반 상식 (예: 'AI 는 기술이다') 은 자료에 없어도 통과\n\n"
    "JSON 으로만 응답하라:\n"
    '{{"grounded": true|false, "unsupported": ["짧은 주장 1", "..."]}}'
)

DEFAULT_QUERY = "BlackRock 과 Vanguard 의 ETF 전략 차이를 비교해줘"

# Fixture answer — same compressed prose as V3'.c's draft for
# cross-stage comparability. fact_check evaluates explicit claims
# inside this answer against the context below.
FIXTURE_ANSWER_KO = (
    "BlackRock 의 iShares 시리즈는 시장 점유율 1 위로, 테마형·"
    "섹터형·국제형 ETF 라인업이 넓고, 비트코인 spot ETF (IBIT) 등 "
    "신규 자산군 진입에 적극적이다. 운용 보수는 평균 0.10~0.30% "
    "수준이다.\n\n"
    "Vanguard 는 인덱스 펀드 창시자 답게 광범위 시장 노출 + 초저비용 "
    "전략을 유지한다. VOO (S&P 500), VTI (Total US Market) 등 "
    "core ETF 의 운용 보수가 0.03~0.05% 로 업계 최저 수준이다."
)

# Fixture context — internal data passages the answer's claims must
# be checked against. Includes both supporting (IBIT, VOO/VTI) and
# adversarial (a contradictory boutique-fee figure) signals to give
# fact_check material to actually evaluate.
FIXTURE_CONTEXT_KO = (
    "[문서 A — BlackRock iShares 라인업 보고서, 2026 Q1]\n"
    "iShares 는 BlackRock 의 ETF 브랜드로, AUM 기준 글로벌 1 위. "
    "라인업은 광범위 시장 인덱스부터 섹터별·테마형 (반도체, AI 인프라, "
    "정정청정에너지) + 국제 시장 (EM, EAFE) 까지 포함. 2024 년 출시한 "
    "IBIT (iShares Bitcoin Trust) 가 spot 비트코인 ETF 카테고리 1 위. "
    "테마형 ETF 운용 보수는 0.20~0.40%, core 인덱스는 0.10% 이하.\n\n"
    "[문서 B — Vanguard ETF 비용 보고서, 2026 Q1]\n"
    "Vanguard 의 core ETF (VOO S&P500, VTI Total US Market, VXUS "
    "International) 의 expense ratio 는 0.03~0.05% 수준으로 업계 "
    "최저. mutual fund 출신 답게 broad-market index + buy-and-hold "
    "철학이 일관됨. 테마형·암호자산 ETF 진입은 보수적 — 2025 년 spot "
    "비트코인 ETF 신청 보류 결정.\n\n"
    "[문서 C — ETF 시장 점유율 분석, 2025 Q4]\n"
    "AUM 기준 BlackRock iShares 1 위, Vanguard 2 위. 두 운용사 합산 "
    "글로벌 ETF AUM 의 55% 차지. 신규 자산군 진입 속도는 BlackRock "
    "(iBIT, Ethereum ETF 등) > Vanguard (현재까지 디지털 자산 ETF "
    "출시 없음)."
)

DEFAULT_MODEL = "gemma4:e4b"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_N = 10

# Pre-#399 default vs lifted. Current code default is already 4096
# (see core/reasoning/verify.py:73 DEFAULT_FACT_CHECK_MAX_TOKENS).
# This driver measures the pre-bump default to validate the bump
# fix is what closed the empty-response pattern.
CAP_DEFAULT = 400   # pre-#399 default; PR #399 bumped to 4096
CAP_LIFTED = 4096


def call_ollama(
    url: str, model: str, prompt: str,
    num_predict: int, temperature: float,
    timeout: float = 30.0,
) -> dict:
    """Single Ollama ``/api/generate`` call returning per-call telemetry."""
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": num_predict,
            "temperature": temperature,
        },
    }).encode("utf-8")
    req = request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    t0 = time.monotonic()
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as e:
        return {"_error": f"HTTPError {e.code}", "elapsed_s": round(time.monotonic() - t0, 2)}
    except error.URLError as e:
        return {"_error": f"URLError {e.reason}", "elapsed_s": round(time.monotonic() - t0, 2)}
    elapsed = time.monotonic() - t0
    raw_response = payload.get("response", "")
    # Try to parse the JSON shape the prompt asks for. Tolerant of
    # leading/trailing whitespace and markdown fences. A run is
    # "valid_json" if the parsed object has both expected keys.
    valid_json = False
    try:
        text = raw_response.strip()
        if text.startswith("```"):
            # Strip ```json ... ``` fence.
            text = text.lstrip("`").lstrip("json").strip("`").strip()
        if text:
            parsed = json.loads(text)
            valid_json = (
                isinstance(parsed, dict)
                and "grounded" in parsed
                and "unsupported" in parsed
            )
    except (json.JSONDecodeError, ValueError):
        valid_json = False
    return {
        "elapsed_s": round(elapsed, 2),
        "response_bytes": len(raw_response.encode("utf-8")),
        "response_chars": len(raw_response),
        "ollama_done_reason": payload.get("done_reason", "?"),
        "ollama_total_duration_ms": (
            int(payload["total_duration"] / 1_000_000)
            if isinstance(payload.get("total_duration"), int) else None
        ),
        "ollama_eval_count": payload.get("eval_count"),
        "raw_response_sha256": hashlib.sha256(
            raw_response.encode("utf-8")
        ).hexdigest()[:16],
        "non_empty": bool(raw_response.strip()),
        "valid_json": valid_json,
        # Cheap surface check — does the response at least mention
        # the expected keys, even if not parseable.
        "mentions_grounded_key": '"grounded"' in raw_response,
    }


def run_sweep(args: argparse.Namespace) -> dict:
    """Run ``args.n`` calls at each of (default, lifted) cap, aggregate."""
    prompt = FACT_CHECK_PROMPT_KO.format(
        query=args.query,
        answer=FIXTURE_ANSWER_KO,
        context=FIXTURE_CONTEXT_KO,
    )
    results = {
        "metadata": {
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "driver": "v3prime_verify.py",
            "stage": "verify.fact_check",
            "model": args.model,
            "temperature": args.temperature,
            "n_per_cap": args.n,
            "query": args.query,
            "fixture_answer_chars": len(FIXTURE_ANSWER_KO),
            "fixture_context_chars": len(FIXTURE_CONTEXT_KO),
            "caps_tested": [CAP_DEFAULT, CAP_LIFTED],
            "ollama_url": args.url,
            "prompt_template_pinned_from":
                "core/reasoning/verify.py:149 (FACT_CHECK_PROMPT_KO)",
            "validation_role":
                "post-merge validation of PR #399 cap bump "
                "(DEFAULT_FACT_CHECK_MAX_TOKENS 400 → 4096); "
                "closes 4-stage cognitive cap-budget validation set",
        },
        "runs": {str(CAP_DEFAULT): [], str(CAP_LIFTED): []},
    }
    total = 2 * args.n
    done = 0
    for cap in (CAP_DEFAULT, CAP_LIFTED):
        for i in range(args.n):
            done += 1
            print(
                f"  [{done:>2}/{total}] cap={cap:>4}  run={i+1:>2}/{args.n}  ...",
                end="", flush=True,
            )
            r = call_ollama(args.url, args.model, prompt, cap, args.temperature)
            r["run_idx"] = i + 1
            r["num_predict"] = cap
            results["runs"][str(cap)].append(r)
            if "_error" in r:
                print(f"  ERROR  {r['_error']}")
                continue
            status = "OK" if r.get("non_empty") else "EMPTY"
            json_status = "JSON" if r.get("valid_json") else "    "
            print(
                f"  {r['elapsed_s']:>5.1f}s  {status:<5}  {json_status}  "
                f"done={r['ollama_done_reason']}  bytes={r['response_bytes']}"
            )
    results["metadata"]["completed_utc"] = datetime.now(timezone.utc).isoformat()
    return results


def summarize(results: dict) -> None:
    """Print summary table + decision-tree interpretation to stdout."""
    print()
    print("━" * 70)
    print(" V3'.d — verify.fact_check cap-budget sweep — SUMMARY")
    print("━" * 70)
    print(f" Model:        {results['metadata']['model']}")
    print(f" Temperature:  {results['metadata']['temperature']}")
    print(f" N per cap:    {results['metadata']['n_per_cap']}")
    print(f" Query:        {results['metadata']['query']}")
    print(
        f" Answer:       {results['metadata']['fixture_answer_chars']} chars "
        "(fixture, see FIXTURE_ANSWER_KO)"
    )
    print(
        f" Context:      {results['metadata']['fixture_context_chars']} chars "
        "(fixture, see FIXTURE_CONTEXT_KO)"
    )
    print()
    print(f" {'Cap':>6} | {'Success':>10} | {'Avg lat':>10} | {'Valid JSON':>11} | {'Key seen':>10}")
    print(f" {'─' * 6}-+-{'─' * 10}-+-{'─' * 10}-+-{'─' * 11}-+-{'─' * 10}")
    for cap_key in sorted(results["runs"].keys(), key=int):
        runs = results["runs"][cap_key]
        n = len(runs)
        non_empty = sum(1 for r in runs if r.get("non_empty"))
        avg_lat = sum(r.get("elapsed_s", 0) for r in runs) / max(n, 1)
        valid_json = sum(1 for r in runs if r.get("valid_json"))
        key_seen = sum(1 for r in runs if r.get("mentions_grounded_key"))
        print(
            f" {cap_key:>6} | {non_empty:>5}/{n:<4} | {avg_lat:>7.1f}s   | "
            f"{valid_json:>5}/{n:<5} | {key_seen:>5}/{n:<4}"
        )
    print()

    runs_default = results["runs"][str(CAP_DEFAULT)]
    runs_lifted = results["runs"][str(CAP_LIFTED)]
    n = len(runs_default)
    success_default = sum(1 for r in runs_default if r.get("non_empty"))
    success_lifted = sum(1 for r in runs_lifted if r.get("non_empty"))
    json_default = sum(1 for r in runs_default if r.get("valid_json"))
    json_lifted = sum(1 for r in runs_lifted if r.get("valid_json"))

    print(" Decision-tree interpretation:")
    if n == 0:
        print("   (no runs completed — nothing to interpret)")
    elif success_lifted >= int(0.9 * n) and success_default <= int(0.3 * n):
        print("   → hypothesis B-budget CONFIRMED for verify.fact_check")
        print("   → closes 4-stage replication set (V3'.a/.b/.c/.d all confirm)")
        print("   → PR #399 cap bump (400 → 4096) fully validated across the")
        print("     four cognitive stages")
        print("   → 4-stage sweep PR (the 'third deployment context' Ali described)")
        print("     ready to anchor with STEP 7 bench numbers in the body")
        if json_lifted >= int(0.7 * n):
            print(f"   → bonus: {json_lifted}/{n} runs at lifted cap produced "
                  "valid grounded/unsupported JSON — the prompt's structured")
            print("     output shape works at the lifted budget")
    elif abs(success_lifted - success_default) <= max(1, n // 5):
        print("   → cap appears NOT to be the variable for verify.fact_check")
        print("   → revisit before the 4-stage PR description — different")
        print("     mechanism may be at play here")
    else:
        print("   → partial signal — examine per-run telemetry for sub-mode mix")
        print(f"     (Δsuccess = {success_lifted - success_default} / {n}; "
              f"valid JSON δ = {json_lifted - json_default} / {n})")
    print()


def save_results(results: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = (
        results["metadata"]["started_utc"]
        .replace(":", "")
        .replace("-", "")
        .split(".")[0]
    )
    out_path = out_dir / f"v3prime-verify-{ts}.json"
    out_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="V3'.d — verify.fact_check cap-budget replication driver",
    )
    parser.add_argument(
        "--n", type=int, default=DEFAULT_N,
        help=f"Calls per cap (default {DEFAULT_N})",
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"Ollama model tag (default {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--url", default=DEFAULT_OLLAMA_URL,
        help=f"Ollama generate endpoint (default {DEFAULT_OLLAMA_URL})",
    )
    parser.add_argument(
        "--temperature", type=float, default=DEFAULT_TEMPERATURE,
        help=f"Sampling temperature (default {DEFAULT_TEMPERATURE})",
    )
    parser.add_argument(
        "--query", default=DEFAULT_QUERY,
        help="Korean retrieval query (default: 2026-05-18 eval query)",
    )
    parser.add_argument(
        "--out-dir", default="reports/research-runs",
        help="Output directory for results JSON",
    )
    args = parser.parse_args()

    print(
        f"V3'.d sweep: model={args.model}  temperature={args.temperature}  "
        f"n={args.n} per cap"
    )
    print(
        f"  caps tested: {CAP_DEFAULT} (pre-#399 default), "
        f"{CAP_LIFTED} (current default after #399)"
    )
    print()

    results = run_sweep(args)
    summarize(results)
    out = save_results(results, Path(args.out_dir))
    print(f" Results saved: {out}")


if __name__ == "__main__":
    main()
