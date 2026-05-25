"""V3'.b — planner cap-budget single-variable replication.

Tests whether raising ``num_predict`` from the JAMES default (400) to
4096 recovers the empty-response rate seen on the ``plan.decompose``
stage in the 2026-05-18 cognitive-stages eval.

Companion to V3'.a (query_rewriter) which confirmed hypothesis
B-budget with mechanism: ~500-token hidden reasoning floor before
the first visible output token on gemma4:e4b. Planner defaults to
400, which sits just below that floor — strong prior this stage
replicates V3'.a's 0/10 → 10/10 pattern.

References
----------
- ``reports/promo-assets/gemma4-e4b-cognitive-stages-eval.md`` —
  2026-05-18 eval; planner returned empty at 1.33s on gemma4:e4b
  (control gemma3:12b passed at the same latency with 3 subtasks)
- ``docs/research/gemma4-experiment-validation-plan.md`` §4.3 —
  V3' design
- ``scripts/research/v3prime_query_rewriter.py`` — V3'.a driver
  (same protocol, query_rewrite stage)
- ``reports/research-runs/v3prime-query-rewriter-20260522T021221.json`` —
  V3'.a result (0/10 → 10/10 with mechanism)

Method
------
Single-variable isolation:

    Held constant: model, prompt template, query, temperature, server
    Variable:      num_predict ∈ {400, 4096}

Prompt template pinned verbatim from
``core/reasoning/planner.py:89`` (``PLAN_PROMPT_KO``).

Usage
-----
::

    python scripts/research/v3prime_planner.py
    python scripts/research/v3prime_planner.py --n 20

Outputs ``reports/research-runs/v3prime-planner-<UTC>.json``
plus a stdout summary table with a decision-tree interpretation.

Decision rule
-------------
* ≥ 9/10 success at ``num_predict=4096`` AND ≤ 3/10 at 400
  → hypothesis B-budget confirmed for planner — replicates V3'.a
  → run V3'.c / .d (reflect.critique / verify.fact_check) next
* Similar rates at both caps
  → cap is not the variable for planner — different mechanism
    (planner stage may have already been above the ~500 floor at 400)
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
# Prompt — pinned from core/reasoning/planner.py:89.
# Same locking policy as V3'.a: DO NOT auto-sync; this script's
# results describe the prompt at the commit it was run against.
# ────────────────────────────────────────────────────────────────────
PLAN_PROMPT_KO = (
    "아래 질문에 답하기 위해 필요한 하위 작업 (subtask) 들을 순서대로 "
    "2-5 개로 분해하라.\n\n"
    "[질문]\n{query}\n\n"
    "규칙:\n"
    "- 각 subtask 는 한 줄, 짧고 명령형 ('NVIDIA 의 GPU 라인업 조사')\n"
    "- 한 단계가 다음 단계의 입력이 되는 자연 순서\n"
    "- 질문이 단순하면 (1-2 단계로 충분) 그만큼만 출력\n"
    "- 의미를 보존하고 새 주제를 만들지 마라\n\n"
    "JSON 으로만 응답:\n"
    '{{"subtasks": ["...", "..."], "rationale": "한 줄 이유"}}'
)

DEFAULT_QUERY = "BlackRock 과 Vanguard 의 ETF 전략 차이를 비교해줘"

DEFAULT_MODEL = "gemma4:e4b"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_N = 10

CAP_DEFAULT = 400   # current core/reasoning/planner.py:43 (DEFAULT_MAX_TOKENS)
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
        "looks_like_subtasks_json": '"subtasks"' in raw_response,
    }


def run_sweep(args: argparse.Namespace) -> dict:
    prompt = PLAN_PROMPT_KO.format(query=args.query)
    results = {
        "metadata": {
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "driver": "v3prime_planner.py",
            "stage": "plan.decompose",
            "model": args.model,
            "temperature": args.temperature,
            "n_per_cap": args.n,
            "query": args.query,
            "caps_tested": [CAP_DEFAULT, CAP_LIFTED],
            "ollama_url": args.url,
            "prompt_template_pinned_from":
                "core/reasoning/planner.py:89 (PLAN_PROMPT_KO)",
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
    print()
    print("━" * 70)
    print(" V3'.b — plan.decompose cap-budget sweep — SUMMARY")
    print("━" * 70)
    print(f" Model:        {results['metadata']['model']}")
    print(f" Temperature:  {results['metadata']['temperature']}")
    print(f" N per cap:    {results['metadata']['n_per_cap']}")
    print(f" Query:        {results['metadata']['query']}")
    print()
    print(f" {'Cap':>6} | {'Success':>10} | {'Avg lat':>10} | {'JSON ok':>10}")
    print(f" {'─' * 6}-+-{'─' * 10}-+-{'─' * 10}-+-{'─' * 10}")
    for cap_key in sorted(results["runs"].keys(), key=int):
        runs = results["runs"][cap_key]
        n = len(runs)
        non_empty = sum(1 for r in runs if r.get("non_empty"))
        avg_lat = sum(r.get("elapsed_s", 0) for r in runs) / max(n, 1)
        json_ok = sum(1 for r in runs if r.get("looks_like_subtasks_json"))
        print(
            f" {cap_key:>6} | {non_empty:>5}/{n:<4} | {avg_lat:>7.1f}s   | "
            f"{json_ok:>5}/{n:<4}"
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
        print("   → hypothesis B-budget CONFIRMED for plan.decompose")
        print("   → matches V3'.a query_rewrite pattern (0/10 → 10/10 recovery)")
        print("   → next: V3'.c (reflect.critique) + V3'.d (verify.fact_check)")
    elif abs(success_lifted - success_default) <= max(1, n // 5):
        print("   → cap appears NOT to be the variable for plan.decompose")
        print("   → planner default (400) may already be above the ~500 floor")
        print("   → re-examine eval_count distribution to confirm")
    else:
        print("   → partial signal — examine per-run telemetry")
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
    out_path = out_dir / f"v3prime-planner-{ts}.json"
    out_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="V3'.b — planner cap-budget replication driver",
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
        f"V3'.b sweep: model={args.model}  temperature={args.temperature}  "
        f"n={args.n} per cap"
    )
    print(f"  caps tested: {CAP_DEFAULT} (current default), {CAP_LIFTED} (lifted)")
    print()

    results = run_sweep(args)
    summarize(results)
    out = save_results(results, Path(args.out_dir))
    print(f" Results saved: {out}")


if __name__ == "__main__":
    main()
