"""V3' Direction 1 (cognitive-stages extension) — Adaptive Budget A/B
on the 4 cognitive middleware stages.

Sibling of `v3prime_direction1_adaptive_budget.py`. That driver tested
the substitution / light / heavy task-weight tiers on direct Ollama
calls; this one tests the **4 cognitive stages** (query_rewriter,
planner, reflect, verify) using their *actual production prompt
templates* sourced from `core/retrieval/query_rewriter.py`,
`core/reasoning/planner.py`, `core/reasoning/reflect.py`,
`core/reasoning/verify.py`.

Goal: validate whether the cap-invariance finding from Direction 1's
3-prompt sweep (cap reduction → 0 token change because model stops
naturally below cap) also holds for the 4 cognitive stages, OR
whether the cognitive prompts have natural-stop lengths closer to the
cap budgets that would benefit from dynamic budget more meaningfully.

V3'.a/.b/.c/.d (PR #407) measured these same prompts on a Korean ETF
fixture with caps 200/400/400/400 → all 0/10, lifted to 4096 → all
10/10. This driver runs the same prompts on the **English e-commerce
refund-policy fixture** (matching V3'.e + Direction 1) with the new
A/B shape:

    arms        : baseline (cap=4096) vs treatment (cap = TaskBudget)
    stages      : query_rewriter, planner, reflect, verify
    N per cell  : 20 (matches Direction 1's main sweep)

= 4 stages × 2 arms × 20 = 160 calls.

The TaskBudget heuristic resolves each cognitive prompt independently;
the resolved cap is recorded per-cell in metadata so the result doc
can distinguish "cap=800 because no heavy marker" from "cap=4096
because the prompt happened to contain a marker".

Pre-registered expectations (from Direction 1's 3-prompt sweep
result, 2026-05-24):

  • All cognitive prompts will resolve to either CAP_LIGHT (800) or
    CAP_HEAVY (4096) — none are substitution patterns.
  • If natural-stop length is ≪ 800 across stages → no token-cut
    expected (same finding as 3-prompt sweep).
  • If any stage has natural-stop length 800-4096 on this fixture
    → baseline=4096 vs treatment=800 will reveal `done_reason=length`
    truncations in the treatment arm → confirms a *real* cap-cost
    on that stage, and the dynamic budget would help.
  • If any stage gets escalated to CAP_HEAVY (4096) by the heuristic,
    its baseline and treatment caps are identical → 0 delta expected.

The 4-cell decision table:

  cap-invariant + no truncation         → confirms 3-prompt finding;
                                          dynamic budget is safety-only
                                          for this stage.
  cap-invariant + truncation @ 800      → would not happen
                                          (truncation means cap-dependent).
  cap-dependent + truncation @ 800      → CAP_LIGHT=800 too tight for
                                          this stage; bump heuristic.
  cap-dependent + no truncation         → cap-dependent reduction win;
                                          this stage benefits from D1.

Pre-condition: `core/reasoning/budget.py` and the 4 stage modules are
importable. Driver does NOT toggle JAMES_ADAPTIVE_BUDGET — it calls
TaskBudget.assess() directly. The wiring (PR #461 D1.B) is untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request

# Resolve repo-rooted imports regardless of cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core.reasoning.budget import (  # noqa: E402
    CAP_HEAVY,
    CAP_LIGHT,
    CAP_SUBSTITUTION,
    TaskBudget,
)

# Reuse production prompt templates so the driver tests the *actual*
# strings the stages send to Ollama in live use. If those modules
# change their prompts, this driver picks up the change automatically.
from core.retrieval.query_rewriter import REWRITE_PROMPT_EN  # noqa: E402
from core.reasoning.planner import PLAN_PROMPT_EN  # noqa: E402
from core.reasoning.reflect import CRITIQUE_PROMPT_EN  # noqa: E402
from core.reasoning.verify import FACT_CHECK_PROMPT_EN  # noqa: E402


# ────────────────────────────────────────────────────────────────────
# Fixture — same e-commerce refund policy context as V3'.e + D1 3-tier
# sweep, so cross-experiment deltas are directly comparable.
# ────────────────────────────────────────────────────────────────────
CONTEXT_FIXTURE = (
    "Refund Policy\n"
    "-------------\n"
    "Items may be returned within 30 days of delivery for a full "
    "refund, provided they are unworn, unwashed, and have all "
    "original tags attached. Linen, silk, and cashmere garments are "
    "final sale once washed — refunds are not issued for washed "
    "items in these fabrics.\n\n"
    "Damaged Items\n"
    "-------------\n"
    "Damaged or defective items are eligible for replacement or "
    "full refund regardless of the 30-day window, including washed "
    "specialty fabrics, when accompanied by clear photographs of "
    "the defect.\n\n"
    "Exchanges\n"
    "---------\n"
    "Standard items may be exchanged for a different size or color "
    "within 14 days. Specialty fabrics are exchange-only when "
    "unworn and tagged."
)

USER_QUERY = (
    "How do I get a refund for a silk dress I bought 10 days ago, "
    "wore once, and now want to return?"
)

# Driver-supplied dummy draft for the reflect (critique) stage.
# In production this comes from the synth.rag pipeline; here we hand-
# craft a deliberately imperfect draft to ensure the critique stage
# has substantive material to critique.
DUMMY_DRAFT = (
    "You can return the silk dress within 30 days of delivery for a "
    "full refund as long as it is unworn and has original tags. "
    "Since you wore it once, this might not qualify under the "
    "standard policy. If there is any damage, take photos and "
    "submit them for a damaged-item refund."
)

# Driver-supplied dummy answer for the verify (fact-check) stage.
# Slight fact-error embedded ("60 days" vs actual "30 days") so the
# verify stage has a non-trivial fact-check task.
DUMMY_ANSWER = (
    "Items may be returned within 60 days of delivery for a full "
    "refund if unworn, unwashed, and tagged. Silk garments worn "
    "once are still eligible since they have not been washed. "
    "Exchanges are available within 14 days."
)


def _build_stage_prompts() -> dict[str, str]:
    """Resolve the 4 cognitive-stage prompts on the fixture."""
    return {
        "query_rewriter": REWRITE_PROMPT_EN.format(query=USER_QUERY),
        "planner": PLAN_PROMPT_EN.format(query=USER_QUERY),
        "reflect": CRITIQUE_PROMPT_EN.format(
            query=USER_QUERY, draft=DUMMY_DRAFT,
        ),
        "verify": FACT_CHECK_PROMPT_EN.format(
            query=USER_QUERY, answer=DUMMY_ANSWER, context=CONTEXT_FIXTURE,
        ),
    }


STAGE_TYPES = ("query_rewriter", "planner", "reflect", "verify")
ARMS = ("baseline", "treatment")

DEFAULT_MODEL = "gemma4:e4b"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_N = 20
BASELINE_CAP = 4096

# Quality signals — substring checks against the canonical context.
HAS_POLICY = ("30 days", "silk", "linen", "cashmere", "fabrics", "damaged")
HAS_DECISION = (
    "refund", "exchange", "replacement", "30", "14",
    "eligible", "qualif",
)


def call_ollama(
    url: str, model: str, prompt: str,
    num_predict: int, temperature: float,
    timeout: float = 60.0,
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
        return {"_error": f"HTTPError {e.code}",
                "elapsed_s": round(time.monotonic() - t0, 2)}
    except error.URLError as e:
        return {"_error": f"URLError {e.reason}",
                "elapsed_s": round(time.monotonic() - t0, 2)}
    elapsed = time.monotonic() - t0
    raw_response = payload.get("response", "")
    response_lower = raw_response.lower()
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
        "raw_response_text": raw_response,
        "non_empty": bool(raw_response.strip()),
        "has_policy_keyword": any(kw in response_lower for kw in HAS_POLICY),
        "has_decision_keyword": any(kw in response_lower for kw in HAS_DECISION),
    }


def _resolve_treatment_cap(stage: str, prompt: str) -> tuple[int, str]:
    tb = TaskBudget()
    cap = tb.assess(stage, prompt)
    if cap == CAP_SUBSTITUTION:
        reason = "substitution_pattern"
    elif cap == CAP_HEAVY:
        reason = "heavy_marker"
    elif cap == CAP_LIGHT:
        reason = "default_light"
    else:
        reason = f"unknown_cap_{cap}"
    return cap, reason


def run_sweep(args: argparse.Namespace) -> dict:
    prompts = _build_stage_prompts()
    treatment = {
        stage: _resolve_treatment_cap(stage, prompts[stage])
        for stage in STAGE_TYPES
    }

    results: dict = {
        "metadata": {
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "driver": "v3prime_direction1_cognitive_stages.py",
            "stage": "direction1_cognitive_stages_adaptive_budget",
            "hypothesis": (
                "TaskBudget.assess() applied to the 4 cognitive stages "
                "(query_rewriter / planner / reflect / verify) reveals "
                "whether the cap-invariance finding from D1's 3-prompt "
                "sweep also holds here, OR whether the cognitive prompts "
                "have natural-stop lengths in the band where "
                "cap=800 truncates and cap=4096 does not."
            ),
            "model": args.model,
            "temperature": args.temperature,
            "n_per_cell": args.n,
            "context_chars": len(CONTEXT_FIXTURE),
            "user_query": USER_QUERY,
            "baseline_cap": BASELINE_CAP,
            "stages_tested": list(STAGE_TYPES),
            "arms": list(ARMS),
            "ollama_url": args.url,
            "resolved_treatment_cap": {
                s: {"cap": treatment[s][0], "reason": treatment[s][1]}
                for s in STAGE_TYPES
            },
            "schema_version": "v3prime-protocol-v1-additive",
            "schema_additions": [
                "adaptive_cap_requested",
                "adaptive_decision_reason",
            ],
            "cross_experiment_anchors": {
                "v3prime_a_d_pr407": (
                    "V3'.a~d (PR #407) measured these same prompts on "
                    "Korean ETF fixture; cap=200/400/400/400 → 0/10, "
                    "cap=4096 → 10/10. This driver re-tests with English "
                    "e-commerce fixture + cap=800 treatment to isolate "
                    "fixture sensitivity from cap dependence."
                ),
                "direction1_3prompt_sweep": (
                    "v3prime_direction1_adaptive_budget.py (sibling) "
                    "showed cap-invariance on substitution / light / "
                    "heavy free-form prompts. This driver tests the "
                    "same hypothesis on structured-JSON cognitive prompts."
                ),
            },
        },
        "fixtures": {
            "context": CONTEXT_FIXTURE,
            "user_query": USER_QUERY,
            "dummy_draft": DUMMY_DRAFT,
            "dummy_answer": DUMMY_ANSWER,
            "stage_prompts": prompts,
        },
        "runs": {
            arm: {stage: [] for stage in STAGE_TYPES}
            for arm in ARMS
        },
    }

    total = len(ARMS) * len(STAGE_TYPES) * args.n
    done = 0
    for arm in ARMS:
        for stage in STAGE_TYPES:
            prompt = prompts[stage]
            if arm == "baseline":
                cap = BASELINE_CAP
                reason = "baseline_4096"
            else:
                cap, reason = treatment[stage]
            for i in range(args.n):
                done += 1
                print(
                    f"  [{done:>3}/{total}] arm={arm:<9} stage={stage:<14} "
                    f"cap={cap:>4} run={i+1:>2}/{args.n}  ...",
                    end="", flush=True,
                )
                r = call_ollama(
                    args.url, args.model, prompt, cap, args.temperature,
                )
                r["run_idx"] = i + 1
                r["arm"] = arm
                r["stage"] = stage
                r["adaptive_cap_requested"] = cap
                r["adaptive_decision_reason"] = reason
                results["runs"][arm][stage].append(r)
                if "_error" in r:
                    print(f"  ERROR  {r['_error']}")
                    continue
                status = "OK" if r.get("non_empty") else "EMPTY"
                print(
                    f"  {r['elapsed_s']:>5.1f}s  {status:<5}  "
                    f"done={r['ollama_done_reason']}  "
                    f"eval={r.get('ollama_eval_count', '?')}"
                )

    results["metadata"]["completed_utc"] = (
        datetime.now(timezone.utc).isoformat()
    )
    return results


def _cell_stats(runs: list) -> dict:
    n = len(runs)
    if n == 0:
        return {"n": 0}
    non_empty = [r for r in runs if r.get("non_empty")]
    eval_counts = [
        r.get("ollama_eval_count")
        for r in runs if isinstance(r.get("ollama_eval_count"), int)
    ]
    latencies = [
        r.get("elapsed_s")
        for r in runs if isinstance(r.get("elapsed_s"), (int, float))
    ]
    done_lengths = sum(1 for r in runs if r.get("ollama_done_reason") == "length")
    done_stops = sum(1 for r in runs if r.get("ollama_done_reason") == "stop")
    decision_hits = sum(1 for r in runs if r.get("has_decision_keyword"))
    policy_hits = sum(1 for r in runs if r.get("has_policy_keyword"))
    unique_responses = len({r.get("raw_response_sha256") for r in runs})
    return {
        "n": n,
        "success": f"{len(non_empty)}/{n}",
        "avg_eval_count": (
            round(sum(eval_counts) / max(len(eval_counts), 1), 1)
            if eval_counts else None
        ),
        "min_eval_count": min(eval_counts) if eval_counts else None,
        "max_eval_count": max(eval_counts) if eval_counts else None,
        "avg_latency_s": (
            round(sum(latencies) / max(len(latencies), 1), 2)
            if latencies else None
        ),
        "done_length_count": done_lengths,
        "done_stop_count": done_stops,
        "decision_keyword_hits": f"{decision_hits}/{n}",
        "policy_keyword_hits": f"{policy_hits}/{n}",
        "unique_responses": f"{unique_responses}/{n}",
    }


def summarize(results: dict) -> None:
    print()
    print("━" * 86)
    print(" V3' Direction 1 — Cognitive Stages Adaptive Budget A/B — SUMMARY")
    print("━" * 86)
    md = results["metadata"]
    print(f" Model:        {md['model']}")
    print(f" Temperature:  {md['temperature']}")
    print(f" N per cell:   {md['n_per_cell']}   "
          f"(arms × stages = {len(ARMS) * len(STAGE_TYPES)} cells)")
    print(f" Baseline cap: {md['baseline_cap']}")
    print(" Treatment cap (resolved):")
    for s, d in md["resolved_treatment_cap"].items():
        print(f"   {s:<15} → cap={d['cap']:>4}  reason={d['reason']}")
    print()
    print(f" {'Arm':<10} | {'Stage':<14} | {'Cap':>5} | "
          f"{'Success':>9} | {'EvalCt avg':>10} | {'Range':<15} | "
          f"{'Latency':>8} | {'Length✗':>8}")
    print(f" {'─' * 10}-+-{'─' * 14}-+-{'─' * 5}-+-"
          f"{'─' * 9}-+-{'─' * 10}-+-{'─' * 15}-+-{'─' * 8}-+-{'─' * 8}")
    cells: dict = {}
    for arm in ARMS:
        for stage in STAGE_TYPES:
            runs = results["runs"][arm][stage]
            stats = _cell_stats(runs)
            cells[(arm, stage)] = stats
            cap = (BASELINE_CAP if arm == "baseline"
                   else md["resolved_treatment_cap"][stage]["cap"])
            mn = stats.get("min_eval_count", "-")
            mx = stats.get("max_eval_count", "-")
            print(
                f" {arm:<10} | {stage:<14} | {cap:>5} | "
                f"{stats.get('success', '-'):>9} | "
                f"{stats.get('avg_eval_count', '-'):>10} | "
                f"{str(mn) + '-' + str(mx):<15} | "
                f"{stats.get('avg_latency_s', '-'):>8} | "
                f"{stats.get('done_length_count', '-'):>8}"
            )

    print()
    print("━" * 86)
    print(" Per-stage outcome — token delta + truncation rate")
    print("━" * 86)
    for stage in STAGE_TYPES:
        b = cells[("baseline", stage)].get("avg_eval_count") or 0
        t = cells[("treatment", stage)].get("avg_eval_count") or 0
        t_cap = md["resolved_treatment_cap"][stage]["cap"]
        t_trunc = cells[("treatment", stage)].get("done_length_count", 0)
        if b and t:
            pct = (1 - t / b) * 100
        else:
            pct = 0
        if t_cap == BASELINE_CAP:
            verdict = "heavy-escalated (no delta possible)"
        elif t_trunc > 0:
            verdict = f"⚠️  cap-dependent — {t_trunc}/{md['n_per_cell']} truncations at cap={t_cap}"
        elif abs(pct) < 5:
            verdict = "cap-invariant (matches D1 3-prompt finding)"
        elif pct > 5:
            verdict = f"reduction win {pct:+.1f}% (stage benefits from D1)"
        else:
            verdict = f"unclear {pct:+.1f}% delta"
        print(f"   {stage:<15}  cap {BASELINE_CAP}→{t_cap:<4}  "
              f"{b:>6.1f}→{t:>6.1f}  Δ={pct:+5.1f}%  | {verdict}")

    print()
    print("━" * 86)
    print(" Quality regression check (decision-keyword hits)")
    print("━" * 86)
    for stage in STAGE_TYPES:
        b = cells[("baseline", stage)].get("decision_keyword_hits", "-")
        t = cells[("treatment", stage)].get("decision_keyword_hits", "-")
        print(f"   {stage:<15}  baseline {b:>6}  treatment {t:>6}")


def save_results(results: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    path = out_dir / f"v3prime-direction1-cognitive-stages-{ts}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    return path


def main() -> None:
    p = argparse.ArgumentParser(
        description=(
            "V3' Direction 1 (cognitive-stages extension) — "
            "Adaptive Budget A/B on the 4 cognitive middleware stages."
        ),
    )
    p.add_argument(
        "--n", type=int, default=DEFAULT_N,
        help=f"Calls per cell (default {DEFAULT_N}).",
    )
    p.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"Ollama model tag (default {DEFAULT_MODEL})",
    )
    p.add_argument(
        "--url", default=DEFAULT_OLLAMA_URL,
        help=f"Ollama /api/generate URL (default {DEFAULT_OLLAMA_URL})",
    )
    p.add_argument(
        "--temperature", type=float, default=DEFAULT_TEMPERATURE,
        help=f"Sampling temperature (default {DEFAULT_TEMPERATURE})",
    )
    p.add_argument(
        "--out-dir", default="reports/research-runs",
        help="Output directory for the JSON result (default %(default)s)",
    )
    args = p.parse_args()

    print("V3' Direction 1 (cognitive-stages extension)")
    print(f"  Model:       {args.model}")
    print(f"  N per cell:  {args.n}")
    print(f"  Stages:      {STAGE_TYPES}")
    print(f"  Total calls: {len(ARMS) * len(STAGE_TYPES) * args.n}")
    print()

    results = run_sweep(args)
    out_path = save_results(results, Path(args.out_dir))
    summarize(results)
    print()
    print(f"Raw JSON written to: {out_path}")


if __name__ == "__main__":   # pragma: no cover
    main()
