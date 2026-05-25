"""V3'.a — query_rewriter cap-budget single-variable replication.

Tests whether raising ``num_predict`` from the JAMES default (200) to
4096 recovers the empty-response rate seen on the ``query_rewrite``
stage in the 2026-05-18 cognitive-stages eval.

References
----------
- ``reports/promo-assets/gemma4-e4b-cognitive-stages-eval.md`` —
  the original eval (5/6 cognitive stages returned empty on
  ``gemma4:e4b``; ``query_rewrite`` was one of them at ~2.1 s / 0 chars)
- ``docs/research/gemma4-experiment-validation-plan.md`` §4.3 —
  V3' design + decision tree this script implements
- External cross-validation: Ali Afana (2026-05-21 dev.to walk-back)
  12/12 recovery on Gemini Dense + 26B MoE with ``max_tokens``
  400 → 4096. JAMES per-stage default sits at 200 for query_rewrite,
  even tighter than Ali's failing cap.

Method
------
Single-variable isolation per Ali's walk-back protocol:

    Held constant: model, prompt template, query, temperature, server
    Variable:      num_predict ∈ {200, 4096}

The prompt template is pinned verbatim from
``core/retrieval/query_rewriter.py:53`` (``REWRITE_PROMPT_KO``) so the
research record is reproducible even if the JAMES module evolves.

Usage
-----
::

    python scripts/research/v3prime_query_rewriter.py
    python scripts/research/v3prime_query_rewriter.py --n 20
    python scripts/research/v3prime_query_rewriter.py --model gemma4:e4b --temperature 0.0

Outputs ``reports/research-runs/v3prime-query-rewriter-<UTC>.json``
plus a stdout summary table with a decision-tree interpretation.

Decision rule (validation plan §4.3)
------------------------------------
* ≥ 9/10 success at ``num_predict=4096`` AND ≤ 3/10 at 200
  → hypothesis B-budget CONFIRMED for query_rewrite
  → run V3'.b / .c / .d (planner / reflect.critique / verify.fact_check)
  → eventual PR bumps the four ``DEFAULT_MAX_TOKENS`` constants,
    pastes STEP 7 numbers per CLAUDE.md rule #2
* Similar rates at both caps
  → cap is not the variable for this stage
  → next: V8 (``<think>``-strip bypass) becomes first follow-up
* Anything in between → examine per-run telemetry for sub-mode mix
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
# Prompt — pinned from core/retrieval/query_rewriter.py:53.
# DO NOT auto-sync. If the JAMES module changes, this script's results
# describe the OLD prompt at the commit it was run against; that is
# the correct behaviour for a research replication record.
# ────────────────────────────────────────────────────────────────────
REWRITE_PROMPT_KO = (
    "다음 검색 질의를 retrieval 시스템에 최적화된 형태로 다시 작성하라.\n"
    "원본 질의: {query}\n\n"
    "규칙:\n"
    "- 의미는 그대로 유지\n"
    "- 핵심 키워드는 강화 (동의어 1-2개 병기 가능)\n"
    "- 대명사 (이것/그것/위/그분 등) 는 구체적인 명사로 치환\n"
    "- 부연 설명 없이 한 문장으로\n\n"
    "JSON 으로만 응답하라:\n"
    '{{"rewritten": "<재작성된 질의>"}}'
)

# Same Korean retrieval query as the 2026-05-18 cognitive-stages eval.
DEFAULT_QUERY = "BlackRock 과 Vanguard 의 ETF 전략 차이를 비교해줘"

DEFAULT_MODEL = "gemma4:e4b"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
DEFAULT_TEMPERATURE = 0.2  # matches config.LLM_TEMPERATURE default
DEFAULT_N = 10

CAP_DEFAULT = 200   # current core/retrieval/query_rewriter.py:46 (DEFAULT_MAX_TOKENS)
CAP_LIFTED = 4096   # Ali's working cap


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
        "looks_like_rewritten_json": '"rewritten"' in raw_response,
    }


def run_sweep(args: argparse.Namespace) -> dict:
    """Run ``args.n`` calls at each of (default, lifted) cap, aggregate."""
    prompt = REWRITE_PROMPT_KO.format(query=args.query)
    results = {
        "metadata": {
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "driver": "v3prime_query_rewriter.py",
            "stage": "query_rewrite",
            "model": args.model,
            "temperature": args.temperature,
            "n_per_cap": args.n,
            "query": args.query,
            "caps_tested": [CAP_DEFAULT, CAP_LIFTED],
            "ollama_url": args.url,
            "prompt_template_pinned_from":
                "core/retrieval/query_rewriter.py:53 (REWRITE_PROMPT_KO)",
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
    print(" V3'.a — query_rewrite cap-budget sweep — SUMMARY")
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
        json_ok = sum(1 for r in runs if r.get("looks_like_rewritten_json"))
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

    print(" Decision-tree interpretation (per validation plan §4.3):")
    if n == 0:
        print("   (no runs completed — nothing to interpret)")
    elif success_lifted >= int(0.9 * n) and success_default <= int(0.3 * n):
        print("   → hypothesis B-budget CONFIRMED for query_rewrite")
        print("   → next: V3'.b/.c/.d (planner / reflect.critique / verify.fact_check)")
        print("   → eventual PR: bump the four DEFAULT_MAX_TOKENS constants,")
        print("     paste STEP 7 numbers per CLAUDE.md rule #2")
    elif abs(success_lifted - success_default) <= max(1, n // 5):
        print("   → cap appears NOT to be the variable for this stage")
        print("   → next: V8 (`<think>`-strip bypass) becomes first follow-up")
    else:
        print("   → partial signal — examine per-run telemetry for sub-mode mix")
        print(f"     (Δsuccess = {success_lifted - success_default} / {n}; "
              f"empty-immediate vs partial-truncate split worth a manual look)")
    print()


def save_results(results: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = (
        results["metadata"]["started_utc"]
        .replace(":", "")
        .replace("-", "")
        .split(".")[0]
    )
    out_path = out_dir / f"v3prime-query-rewriter-{ts}.json"
    out_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="V3'.a — query_rewriter cap-budget replication driver",
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
        f"V3'.a sweep: model={args.model}  temperature={args.temperature}  "
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
