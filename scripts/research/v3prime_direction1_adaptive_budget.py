"""V3' Direction 1 — Adaptive Budget A/B experiment.

Measures the token-cost reduction of `core/reasoning/budget.py::TaskBudget`
against the V3'.e e-commerce refund-policy fixture. Two conditions on
the same fixture × the same model × the same temperature:

    baseline   — every call uses cap=4096 (PR #399 default)
    treatment  — cap is `TaskBudget.assess("query_rewriter", prompt)`

Three prompt types covering the full task-weight gradient:

    substitution  — "Return verbatim" → CAP_SUBSTITUTION (200)
    light         — single-question lookup → CAP_LIGHT (800)
    heavy         — multi-step compare/decompose → CAP_HEAVY (4096)

Cell layout: 2 arms × 3 prompt types × N runs/cell. Default N=20
(matches V3'.e and V3' Protocol v1 §statistical-floor recommendation).

What gets measured per call:

  * ollama_eval_count  — primary metric. The reduction we promised.
  * elapsed_s          — wall-clock latency.
  * ollama_done_reason — `length` flags caps that were too tight.
  * raw_response_text  — V3' Protocol v1 REQUIRED field. Lets a
                         downstream reader compute unique-output sets
                         and inspect canonical text directly.
  * raw_response_sha256 (16-char prefix) — additive vs v1; matches
                         Direction 4 schema.
  * adaptive_cap_requested — the `num_predict` actually passed to
                         Ollama for this call.
  * adaptive_decision_reason — for treatment arm, which heuristic
                         branch picked the cap. One of:
                         substitution_pattern / heavy_marker /
                         default_light. baseline arm: always
                         "baseline_4096".

Cross-stack JSON shape — `reports/research-runs/v3prime-direction1-
adaptive-budget-<timestamp>.json` mirrors the V3'.e shape with two
additive fields (adaptive_cap_requested, adaptive_decision_reason).
Any Robin/Ali downstream tool reading the V3'.e schema can read this
unchanged; the new fields show up where they expect them.

Default-off invariant: this driver does NOT toggle the
JAMES_ADAPTIVE_BUDGET env. The driver is the *experiment* that
decides whether the env should ever flip to ON in production. The
adaptive cap is computed *inside this script* via direct
`TaskBudget.assess()` and passed as `num_predict` to raw Ollama —
no dependence on QueryRewriter's runtime wiring at all.

How to run::

    python scripts/research/v3prime_direction1_adaptive_budget.py --n 20

With a smaller smoke run::

    python scripts/research/v3prime_direction1_adaptive_budget.py --n 5

References
----------
- ``core/reasoning/budget.py`` — the heuristic this experiment tests
- ``scripts/research/v3prime_e_mode_split.py`` — sibling driver
  (V3'.e) at the same protocol; shares the fixture
- ``docs/research/v3prime-protocol-v1.md`` — JSON schema spec
- ``docs/handovers/v0.3.x-measurement-framework-track.md §Stage 2.A`` —
  the Direction 1 plan this driver instruments
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


# ────────────────────────────────────────────────────────────────────
# Fixture — same e-commerce refund policy as V3'.e so cross-experiment
# token deltas are directly comparable.
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


# ────────────────────────────────────────────────────────────────────
# Prompts — three task-weight tiers. Each is designed to trigger one
# branch of the TaskBudget heuristic.
# ────────────────────────────────────────────────────────────────────
SUBSTITUTION_PROMPT = (
    "Return the section titled 'Refund Policy' from the context "
    "below verbatim. Do not paraphrase. Do not add commentary. "
    "Do not include other sections.\n\n"
    "Context:\n{context}\n\n"
    "Refund Policy section (verbatim):"
)

LIGHT_PROMPT = (
    "Based on the policy context below, answer in one sentence: "
    "what is the standard refund window for an unworn, tagged item?"
    "\n\nContext:\n{context}\n\nAnswer:"
)

HEAVY_PROMPT = (
    "Based on the policy context below, compare the refund handling "
    "across the three categories (standard items, specialty fabrics, "
    "damaged items) step by step. Then produce a 4-step decision "
    "tree a customer-support agent could follow to handle any "
    "incoming refund request.\n\n"
    "Context:\n{context}\n\n"
    "Step-by-step analysis:"
)

PROMPTS = {
    "substitution": SUBSTITUTION_PROMPT,
    "light": LIGHT_PROMPT,
    "heavy": HEAVY_PROMPT,
}

PROMPT_TYPES = ("substitution", "light", "heavy")
ARMS = ("baseline", "treatment")

# Predicted treatment cap per prompt type. The driver re-derives this
# via TaskBudget.assess() at run time, but we keep it here as the
# expected ground-truth so the summary table can flag mis-classifications.
PREDICTED_TREATMENT_CAP = {
    "substitution": CAP_SUBSTITUTION,
    "light": CAP_LIGHT,
    "heavy": CAP_HEAVY,
}

DEFAULT_MODEL = "gemma4:e4b"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_N = 20

# Baseline cap — PR #399 lifted-floor default. Same as V3'.e's CAP_LIFTED.
BASELINE_CAP = 4096


# Quality signals — substring checks matching the canonical context.
# Cross-checked against V3'.e to keep the substitution arm comparable.
HAS_LINEN = ("linen", "silk", "cashmere", "fabrics")  # appears in refund policy
HAS_DECISION = (
    "30 days", "thirty days", "14 days", "fourteen days",
    "refund", "replacement", "exchange", "specialty",
)


def call_ollama(
    url: str, model: str, prompt: str,
    num_predict: int, temperature: float,
    timeout: float = 60.0,
) -> dict:
    """Single Ollama ``/api/generate`` call returning per-call telemetry.

    Matches the V3'.e call_ollama signature so the output JSON cells
    drop straight into the same downstream tooling.
    """
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
        # Quality signals — does the answer reference the canonical text?
        # On the substitution arm, both should be present (verbatim
        # retrieval). On synthesis arms, at least decision-keyword
        # must be present for the answer to count as on-topic.
        "has_policy_keyword": any(kw in response_lower for kw in HAS_LINEN),
        "has_decision_keyword": any(kw in response_lower for kw in HAS_DECISION),
    }


def _resolve_treatment_cap(prompt: str) -> tuple[int, str]:
    """Run the TaskBudget heuristic against `prompt`, return (cap, reason)."""
    tb = TaskBudget()
    cap = tb.assess("query_rewriter", prompt)
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
    """Run `args.n` calls at each (arm × prompt_type) cell."""
    prompts = {
        pt: PROMPTS[pt].format(context=CONTEXT_FIXTURE)
        for pt in PROMPT_TYPES
    }

    # Treatment caps + classification reasons — derived once per prompt
    # type since prompt text is constant across runs in a cell.
    treatment = {
        pt: _resolve_treatment_cap(prompts[pt])
        for pt in PROMPT_TYPES
    }

    results: dict = {
        "metadata": {
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "driver": "v3prime_direction1_adaptive_budget.py",
            "stage": "direction1_adaptive_budget",
            "hypothesis": (
                "TaskBudget.assess() reduces ollama_eval_count by 60-80% on "
                "substitution+light prompts while preserving answer quality, "
                "and matches the baseline 4096 cap on heavy synthesis "
                "(no regression on the V3'.a~d cap budget)."
            ),
            "model": args.model,
            "temperature": args.temperature,
            "n_per_cell": args.n,
            "context_chars": len(CONTEXT_FIXTURE),
            "baseline_cap": BASELINE_CAP,
            "prompt_types": list(PROMPT_TYPES),
            "arms": list(ARMS),
            "ollama_url": args.url,
            "predicted_treatment_cap": PREDICTED_TREATMENT_CAP,
            "resolved_treatment_cap": {
                pt: {"cap": treatment[pt][0], "reason": treatment[pt][1]}
                for pt in PROMPT_TYPES
            },
            "schema_version": "v3prime-protocol-v1-additive",
            "schema_additions": [
                "adaptive_cap_requested",
                "adaptive_decision_reason",
            ],
        },
        "fixtures": {
            "context": CONTEXT_FIXTURE,
            "prompts": prompts,
        },
        "runs": {
            arm: {pt: [] for pt in PROMPT_TYPES}
            for arm in ARMS
        },
    }

    total = len(ARMS) * len(PROMPT_TYPES) * args.n
    done = 0
    for arm in ARMS:
        for pt in PROMPT_TYPES:
            prompt = prompts[pt]
            if arm == "baseline":
                cap = BASELINE_CAP
                reason = "baseline_4096"
            else:
                cap, reason = treatment[pt]
            for i in range(args.n):
                done += 1
                print(
                    f"  [{done:>3}/{total}] arm={arm:<9} type={pt:<12} "
                    f"cap={cap:>4} run={i+1:>2}/{args.n}  ...",
                    end="", flush=True,
                )
                r = call_ollama(
                    args.url, args.model, prompt, cap, args.temperature,
                )
                r["run_idx"] = i + 1
                r["arm"] = arm
                r["prompt_type"] = pt
                r["adaptive_cap_requested"] = cap
                r["adaptive_decision_reason"] = reason
                results["runs"][arm][pt].append(r)
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
    """Aggregate one cell of N runs."""
    n = len(runs)
    if n == 0:
        return {"n": 0}
    non_empty = [r for r in runs if r.get("non_empty")]
    success_rate = len(non_empty) / n
    eval_counts = [r.get("ollama_eval_count") for r in runs if isinstance(r.get("ollama_eval_count"), int)]
    latencies = [r.get("elapsed_s") for r in runs if isinstance(r.get("elapsed_s"), (int, float))]
    decision_hits = sum(1 for r in runs if r.get("has_decision_keyword"))
    policy_hits = sum(1 for r in runs if r.get("has_policy_keyword"))
    done_lengths = sum(1 for r in runs if r.get("ollama_done_reason") == "length")
    unique_responses = len({r.get("raw_response_sha256") for r in runs})
    return {
        "n": n,
        "success": f"{len(non_empty)}/{n}",
        "success_rate": round(success_rate, 3),
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
        "decision_keyword_hits": f"{decision_hits}/{n}",
        "policy_keyword_hits": f"{policy_hits}/{n}",
        "done_length_count": done_lengths,
        "unique_responses": f"{unique_responses}/{n}",
    }


def summarize(results: dict) -> None:
    """Print summary table + token-reduction quantification."""
    print()
    print("━" * 82)
    print(" V3' Direction 1 — Adaptive Budget A/B — SUMMARY")
    print("━" * 82)
    md = results["metadata"]
    print(f" Model:        {md['model']}")
    print(f" Temperature:  {md['temperature']}")
    print(f" N per cell:   {md['n_per_cell']}   "
          f"(arms × types matrix = {len(ARMS) * len(PROMPT_TYPES)} cells)")
    print(f" Baseline cap: {md['baseline_cap']}")
    print(" Treatment cap (resolved):")
    for pt, d in md["resolved_treatment_cap"].items():
        predicted = PREDICTED_TREATMENT_CAP[pt]
        ok = "✓" if d["cap"] == predicted else "✗"
        print(f"   {pt:<14} → cap={d['cap']:>4}  reason={d['reason']:<22} "
              f"(predicted {predicted}) {ok}")
    print()
    print(f" {'Arm':<10} | {'Type':<13} | {'Cap':>5} | "
          f"{'Success':>9} | {'EvalCt avg':>10} | "
          f"{'Latency':>8} | {'Length✗':>8}")
    print(f" {'─' * 10}-+-{'─' * 13}-+-{'─' * 5}-+-"
          f"{'─' * 9}-+-{'─' * 10}-+-{'─' * 8}-+-{'─' * 8}")
    cells: dict = {}
    for arm in ARMS:
        for pt in PROMPT_TYPES:
            runs = results["runs"][arm][pt]
            stats = _cell_stats(runs)
            cells[(arm, pt)] = stats
            cap = (BASELINE_CAP if arm == "baseline"
                   else md["resolved_treatment_cap"][pt]["cap"])
            print(
                f" {arm:<10} | {pt:<13} | {cap:>5} | "
                f"{stats.get('success', '-'):>9} | "
                f"{stats.get('avg_eval_count', '-'):>10} | "
                f"{stats.get('avg_latency_s', '-'):>8} | "
                f"{stats.get('done_length_count', '-'):>8}"
            )

    print()
    print("━" * 82)
    print(" Token reduction (eval_count: baseline → treatment)")
    print("━" * 82)
    for pt in PROMPT_TYPES:
        b = cells[("baseline", pt)].get("avg_eval_count") or 0
        t = cells[("treatment", pt)].get("avg_eval_count") or 0
        if b and t:
            pct = (1 - t / b) * 100
            print(f"   {pt:<14}  {b:>7.1f}  →  {t:>6.1f}   "
                  f"Δ={pct:>+6.1f}%")
        else:
            print(f"   {pt:<14}  baseline={b}  treatment={t}  "
                  f"(insufficient data for delta)")

    print()
    print("━" * 82)
    print(" Quality regression check")
    print("━" * 82)
    for pt in PROMPT_TYPES:
        b = cells[("baseline", pt)]
        t = cells[("treatment", pt)]
        print(f"   {pt:<14}")
        print(f"     decision-keyword hits  baseline={b.get('decision_keyword_hits', '-'):>6}  "
              f"treatment={t.get('decision_keyword_hits', '-'):>6}")
        print(f"     policy-keyword hits    baseline={b.get('policy_keyword_hits', '-'):>6}  "
              f"treatment={t.get('policy_keyword_hits', '-'):>6}")
        print(f"     unique responses       baseline={b.get('unique_responses', '-'):>6}  "
              f"treatment={t.get('unique_responses', '-'):>6}")

    print()
    print("━" * 82)
    print(" Direction 1 result classification")
    print("━" * 82)
    # Decision logic — Direction 1 pass criteria.
    sub_b = cells[("baseline", "substitution")].get("avg_eval_count") or 0
    sub_t = cells[("treatment", "substitution")].get("avg_eval_count") or 0
    light_b = cells[("baseline", "light")].get("avg_eval_count") or 0
    light_t = cells[("treatment", "light")].get("avg_eval_count") or 0
    heavy_b = cells[("baseline", "heavy")].get("avg_eval_count") or 0
    heavy_t = cells[("treatment", "heavy")].get("avg_eval_count") or 0
    sub_qual_b = cells[("baseline", "substitution")].get("policy_keyword_hits", "0/0")
    sub_qual_t = cells[("treatment", "substitution")].get("policy_keyword_hits", "0/0")
    light_qual_b = cells[("baseline", "light")].get("decision_keyword_hits", "0/0")
    light_qual_t = cells[("treatment", "light")].get("decision_keyword_hits", "0/0")
    heavy_qual_b = cells[("baseline", "heavy")].get("decision_keyword_hits", "0/0")
    heavy_qual_t = cells[("treatment", "heavy")].get("decision_keyword_hits", "0/0")
    print(f"   substitution token reduction: "
          f"{(1 - sub_t/sub_b)*100:>+6.1f}%  "
          f"(target ≥ +60%; needs zero quality regression)")
    print(f"   light token reduction:        "
          f"{(1 - light_t/light_b)*100:>+6.1f}%  "
          f"(target ≥ +60%; needs zero quality regression)")
    print(f"   heavy token delta:            "
          f"{(1 - heavy_t/heavy_b)*100:>+6.1f}%  "
          f"(target ≈ 0%; the treatment heuristic correctly escalates)")
    print(f"   quality check (substitution policy hits): "
          f"baseline {sub_qual_b} → treatment {sub_qual_t}")
    print(f"   quality check (light decision hits):      "
          f"baseline {light_qual_b} → treatment {light_qual_t}")
    print(f"   quality check (heavy decision hits):      "
          f"baseline {heavy_qual_b} → treatment {heavy_qual_t}")


def save_results(results: dict, out_dir: Path) -> Path:
    """Persist JSON + return the path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    path = out_dir / f"v3prime-direction1-adaptive-budget-{ts}.json"
    with path.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    return path


def main() -> None:
    p = argparse.ArgumentParser(
        description="V3' Direction 1 — Adaptive Budget A/B experiment",
    )
    p.add_argument(
        "--n", type=int, default=DEFAULT_N,
        help=f"Calls per cell (default {DEFAULT_N}). "
             "Each (arm × prompt_type) is one cell.",
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

    print("V3' Direction 1 — Adaptive Budget A/B")
    print(f"  Model:       {args.model}")
    print(f"  N per cell:  {args.n}")
    print(f"  Cells:       {len(ARMS) * len(PROMPT_TYPES)}  "
          f"(arms={ARMS}, types={PROMPT_TYPES})")
    print(f"  Total calls: {len(ARMS) * len(PROMPT_TYPES) * args.n}")
    print()

    results = run_sweep(args)
    out_path = save_results(results, Path(args.out_dir))
    summarize(results)
    print()
    print(f"Raw JSON written to: {out_path}")


if __name__ == "__main__":   # pragma: no cover
    main()
