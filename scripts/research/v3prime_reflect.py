"""V3'.c — reflect.critique cap-budget single-variable replication.

Tests whether raising ``num_predict`` from the JAMES pre-#399 default
(400) to 4096 recovers the empty-response rate seen on the
``reflect.critique`` stage in the 2026-05-18 cognitive-stages eval.

Companion to V3'.a (query_rewriter, 200 → 4096, 0/10 → 10/10
confirmed) and V3'.b (planner, 400 → 4096, 0/10 → 10/10 confirmed).
V3'.c provides the in-house **post-merge validation** that PR #399's
bump of ``DEFAULT_CRITIQUE_MAX_TOKENS`` (400 → 4096) is what fixed
the empty-response pattern at this stage — by re-measuring at the
pre-bump default and comparing to the lifted cap.

References
----------
- ``reports/promo-assets/gemma4-e4b-cognitive-stages-eval.md`` —
  2026-05-18 eval; reflect.critique returned 0 chars at 4.2s on
  ``gemma4:e4b`` (control ``gemma3:12b`` passed at 7.98s with a
  coherent meta-critique)
- ``docs/research/gemma4-experiment-validation-plan.md`` §4.3 —
  V3' design
- ``scripts/research/v3prime_query_rewriter.py`` (V3'.a) +
  ``scripts/research/v3prime_planner.py`` (V3'.b) — companion drivers
- PR #399 — reasoning cap defaults bumped above the ~500-token
  reasoning floor (current ``DEFAULT_CRITIQUE_MAX_TOKENS = 4096`` at
  ``core/reasoning/reflect.py:58``)

Method
------
Single-variable isolation:

    Held constant: model, prompt template, query, draft, temperature, server
    Variable:      num_predict ∈ {400, 4096}

Prompt template pinned verbatim from
``core/reasoning/reflect.py:66`` (``CRITIQUE_PROMPT_KO``).

Draft fixture
-------------
``reflect.critique`` requires a draft answer as input. To preserve
reproducibility (and avoid two-stage variance), we use a static
fixture draft — a compressed real Korean prose answer in the same
shape as the 2026-05-18 eval's successful ``synth.rag`` output
(2 690 chars). The fixture is short enough to fit comfortably in
the model's context but rich enough to expose the meta-reasoning
the critique stage actually performs.

Usage
-----
::

    python scripts/research/v3prime_reflect.py
    python scripts/research/v3prime_reflect.py --n 20

Outputs ``reports/research-runs/v3prime-reflect-<UTC>.json`` plus a
stdout summary with a decision-tree interpretation.

Decision rule
-------------
* ≥ 9/10 success at ``num_predict=4096`` AND ≤ 3/10 at 400
  → hypothesis B-budget confirmed for reflect.critique — replicates
    V3'.a/.b. PR #399's cap bump is validated for this stage.
* Similar rates at both caps
  → cap is not the variable for reflect.critique — different mechanism
    (revisit before the 4-stage PR description)
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
# Prompt — pinned from core/reasoning/reflect.py:66.
# DO NOT auto-sync. If the JAMES module changes, this script's
# results describe the prompt at the commit it was run against.
# ────────────────────────────────────────────────────────────────────
CRITIQUE_PROMPT_KO = (
    "아래 답변을 비판적으로 검토하라. 검토 목적은 사용자가 받기 전에 "
    "결함을 잡아내는 것이다.\n\n"
    "[원본 질문]\n{query}\n\n"
    "[답변 초안]\n{draft}\n\n"
    "다음 3 가지 측면만 점검 (각 1-2 줄):\n"
    "1. 모순/사실 오류 — 답변 안에서 서로 어긋나는 부분이나 명백히 틀린 사실\n"
    "2. 누락된 핵심 — 질문에 직접 답하지 않은 부분 또는 빠진 핵심 정보\n"
    "3. 모호함 — 사용자가 오해할 가능성이 있는 표현\n\n"
    "문제가 없으면 'NO_ISSUES' 한 줄만 출력.\n\n"
    "검토:"
)

# Same Korean retrieval query as the 2026-05-18 eval + V3'.a/.b.
DEFAULT_QUERY = "BlackRock 과 Vanguard 의 ETF 전략 차이를 비교해줘"

# Fixture draft — compressed real Korean prose in the shape of the
# 2026-05-18 eval's successful synth.rag output. Pre-baked so the
# critique stage receives a stable input and we measure the critique
# step in isolation.
FIXTURE_DRAFT_KO = (
    "BlackRock 과 Vanguard 의 ETF 전략은 자산 규모와 운용 철학에서 "
    "구분된다. BlackRock 의 iShares 시리즈는 시장 점유율 1 위로, "
    "테마형·섹터형·국제형 ETF 라인업이 넓고, 비트코인 spot ETF "
    "(IBIT) 등 신규 자산군 진입에 적극적이다. 운용 보수는 평균 "
    "0.10~0.30% 수준이다.\n\n"
    "Vanguard 는 인덱스 펀드 창시자 답게 광범위 시장 노출 + 초저비용 "
    "전략을 유지한다. VOO (S&P 500), VTI (Total US Market) 등 "
    "core ETF 의 운용 보수가 0.03~0.05% 로 업계 최저 수준이다. "
    "테마·암호자산 등 niche 영역 진입은 상대적으로 보수적이며, "
    "장기 buy-and-hold 투자자 layer 가 주된 사용자다.\n\n"
    "정리하면 BlackRock 은 폭넓은 상품 다양성 + 신규 시장 선점, "
    "Vanguard 는 비용 최소화 + 광범위 인덱스로 요약된다."
)

DEFAULT_MODEL = "gemma4:e4b"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_N = 10

# Pre-#399 default vs lifted. Current code default is already 4096
# (see core/reasoning/reflect.py:58 DEFAULT_CRITIQUE_MAX_TOKENS).
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
        # The critique stage outputs either "NO_ISSUES" (draft is fine)
        # or a multi-line review touching the 3 dimensions
        # (contradiction / missing core / ambiguity). Both shapes are
        # "success" — what defines failure is the empty-byte pathology.
        "no_issues_signal": raw_response.strip().upper().startswith("NO_ISSUES"),
        "has_critique_dimension": any(
            kw in raw_response for kw in ("모순", "누락", "모호")
        ),
    }


def run_sweep(args: argparse.Namespace) -> dict:
    """Run ``args.n`` calls at each of (default, lifted) cap, aggregate."""
    prompt = CRITIQUE_PROMPT_KO.format(query=args.query, draft=FIXTURE_DRAFT_KO)
    results = {
        "metadata": {
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "driver": "v3prime_reflect.py",
            "stage": "reflect.critique",
            "model": args.model,
            "temperature": args.temperature,
            "n_per_cap": args.n,
            "query": args.query,
            "fixture_draft_chars": len(FIXTURE_DRAFT_KO),
            "caps_tested": [CAP_DEFAULT, CAP_LIFTED],
            "ollama_url": args.url,
            "prompt_template_pinned_from":
                "core/reasoning/reflect.py:66 (CRITIQUE_PROMPT_KO)",
            "validation_role":
                "post-merge validation of PR #399 cap bump "
                "(DEFAULT_CRITIQUE_MAX_TOKENS 400 → 4096)",
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
            print(
                f"  {r['elapsed_s']:>5.1f}s  {status:<5}  "
                f"done={r['ollama_done_reason']}  bytes={r['response_bytes']}"
            )
    results["metadata"]["completed_utc"] = datetime.now(timezone.utc).isoformat()
    return results


def summarize(results: dict) -> None:
    """Print summary table + decision-tree interpretation to stdout."""
    print()
    print("━" * 70)
    print(" V3'.c — reflect.critique cap-budget sweep — SUMMARY")
    print("━" * 70)
    print(f" Model:        {results['metadata']['model']}")
    print(f" Temperature:  {results['metadata']['temperature']}")
    print(f" N per cap:    {results['metadata']['n_per_cap']}")
    print(f" Query:        {results['metadata']['query']}")
    print(f" Draft:        {results['metadata']['fixture_draft_chars']} chars "
          "(fixture, see FIXTURE_DRAFT_KO)")
    print()
    print(f" {'Cap':>6} | {'Success':>10} | {'Avg lat':>10} | {'NO_ISSUES':>10} | {'Dim. hit':>10}")
    print(f" {'─' * 6}-+-{'─' * 10}-+-{'─' * 10}-+-{'─' * 10}-+-{'─' * 10}")
    for cap_key in sorted(results["runs"].keys(), key=int):
        runs = results["runs"][cap_key]
        n = len(runs)
        non_empty = sum(1 for r in runs if r.get("non_empty"))
        avg_lat = sum(r.get("elapsed_s", 0) for r in runs) / max(n, 1)
        no_issues = sum(1 for r in runs if r.get("no_issues_signal"))
        dim_hit = sum(1 for r in runs if r.get("has_critique_dimension"))
        print(
            f" {cap_key:>6} | {non_empty:>5}/{n:<4} | {avg_lat:>7.1f}s   | "
            f"{no_issues:>5}/{n:<4} | {dim_hit:>5}/{n:<4}"
        )
    print()

    runs_default = results["runs"][str(CAP_DEFAULT)]
    runs_lifted = results["runs"][str(CAP_LIFTED)]
    n = len(runs_default)
    success_default = sum(1 for r in runs_default if r.get("non_empty"))
    success_lifted = sum(1 for r in runs_lifted if r.get("non_empty"))

    print(" Decision-tree interpretation:")
    if n == 0:
        print("   (no runs completed — nothing to interpret)")
    elif success_lifted >= int(0.9 * n) and success_default <= int(0.3 * n):
        print("   → hypothesis B-budget CONFIRMED for reflect.critique")
        print("   → replicates V3'.a/.b pattern at the same ~500-token floor")
        print("   → PR #399 cap bump (400 → 4096) validated for this stage")
        print("   → V3'.d (verify.fact_check) next for the final stage")
    elif abs(success_lifted - success_default) <= max(1, n // 5):
        print("   → cap appears NOT to be the variable for reflect.critique")
        print("   → revisit before the 4-stage PR description — different")
        print("     mechanism may be at play here")
    else:
        print("   → partial signal — examine per-run telemetry for sub-mode mix")
        print(f"     (Δsuccess = {success_lifted - success_default} / {n})")
    print()


def save_results(results: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = (
        results["metadata"]["started_utc"]
        .replace(":", "")
        .replace("-", "")
        .split(".")[0]
    )
    out_path = out_dir / f"v3prime-reflect-{ts}.json"
    out_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="V3'.c — reflect.critique cap-budget replication driver",
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
        f"V3'.c sweep: model={args.model}  temperature={args.temperature}  "
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
