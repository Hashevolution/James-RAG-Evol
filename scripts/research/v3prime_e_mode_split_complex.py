"""V3'.e — substitution vs synthesis mode split (Robin Converse hypothesis).

Tests Robin Converse's 2026-05-22~24 LinkedIn finding ("two operating
modes, one model") at the same cap budgets the JAMES V3'.a/.b/.c/.d
sweep used. Her observation on 26B-MoE × e-commerce showed scenario 6
(return-policy retrieval) producing **byte-identical answers across
temperatures 0.3 / 0.7 / 1.0**, while the next-row under-specified
question produced 1,000+ reasoning tokens varying wildly. Her
interpretation:

  Mode               Behaviour                              Temperature
  ---                ---                                    ---
  Substitution       Canonical text retrieved + rendered.    no effect
                     No reasoning step.
  Synthesis          Model reasons, generates new content.   affects output

Ali Afana elevated the framing to "architectural primitive everyone
building agentic systems needs to internalize" (2026-05-24 comment).

V3'.e tests whether this split predicts the cap-pathology floor:

- If **substitution** mode clears cap=400 cleanly while **synthesis**
  mode hits the same ~500-token floor we measured in V3'.a/.b/.c/.d,
  Robin's split is independently confirmed and the cap pathology gets
  a sharper mechanism: it's the *synthesis-mode entry cost*. The
  V3'.a/.b/.c/.d sweep then reads as "all four stages happen to route
  through synthesis, just under different surface tasks."
- If **both modes** hit the floor at cap=400, the cap pathology is
  mode-independent — Robin's split is real (her data shows it) but is
  a separate mechanism from what we measured.

Method — single-variable isolation, same as V3'.a/.b/.c/.d:

    Held constant: model, server, temperature, context fixture, cap
    Variable:      prompt arm ∈ {substitution, synthesis}
                   × num_predict ∈ {400, 4096}
                   × run_idx ∈ {1..N}

References
----------
- Robin Converse's LinkedIn post (2026-05-22~24) — first publication
  of the substitution/synthesis split.
- Ali Afana's comment elevating it to architectural primitive.
- ``scripts/research/v3prime_reflect.py`` / ``v3prime_verify.py`` —
  sibling drivers (V3'.c / V3'.d) at the same protocol.
- ``reports/promo-assets/gemma4-e4b-cognitive-stages-eval.md`` (PR #407)
  — the 4-stage validation that V3'.e extends.
- ``docs/handovers/v0.3.x-ali-collaboration-track.md`` — Track 5
  joint-piece narrative this driver feeds into.

Usage
-----
::

    python scripts/research/v3prime_e_mode_split.py
    python scripts/research/v3prime_e_mode_split.py --n 20

Outputs ``reports/research-runs/v3prime-e-mode-split-<UTC>.json`` plus
a stdout summary with a pattern-S / pattern-N decision tree.
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
# Context fixture — e-commerce return policy (Robin's domain).
# English so the comparison to her 26B-MoE Ollama data is direct;
# JAMES production fixtures are Korean but V3'.e isn't measuring
# JAMES's prompts, it's measuring the substitution/synthesis split
# claim on gemma4:e4b.
# ────────────────────────────────────────────────────────────────────
CONTEXT_FIXTURE = (
    "Refund Policy\n"
    "-------------\n"
    "Items may be returned within 30 days of delivery for a full "
    "refund, provided they are unworn, unwashed, and have all "
    "original tags attached. Linen, silk, and cashmere garments are "
    "final sale once washed — refunds are not issued for washed "
    "items in these fabrics.\n\n"
    "Shipping Policy\n"
    "---------------\n"
    "Standard shipping is free for orders over $50. Express shipping "
    "is a flat $15 fee. Orders placed before 2pm EST ship the same "
    "business day. International orders may take 7-14 business days.\n\n"
    "Sizing\n"
    "------\n"
    "Our garments run true to size. Linen products may shrink up to "
    "3% on first wash; cold wash and lay flat to dry to minimize "
    "shrinkage. Size charts are available on each product page."
)


# ────────────────────────────────────────────────────────────────────
# Substitution-mode prompt — verbatim retrieval, no reasoning.
# Robin's scenario 6 shape: ask for the canonical text of one section.
# ────────────────────────────────────────────────────────────────────
SUBSTITUTION_PROMPT = (
    "Return verbatim the section titled 'Refund Policy' from the "
    "context below. Do not paraphrase. Do not add commentary. "
    "Do not include other sections.\n\n"
    "Context:\n{context}\n\n"
    "Refund Policy section (verbatim):"
)


# ────────────────────────────────────────────────────────────────────
# Synthesis-mode prompt — V3'.e-complex variant (B-orig, 2026-05-29).
# Multi-item, multi-clause reasoning to push the synthesis-mode cap
# boundary harder. The original V3'.e fixture (single linen item)
# yielded ~65-70% success at cap=400 on gemma4:e4b only; the other
# 6 cross-family models all cleared 10/10. This complex variant
# tests whether the boundary is fixture-complexity dependent (other
# models also hit floor) or checkpoint-specific (only gemma4:e4b
# stays at the boundary even with harder synthesis).
# ────────────────────────────────────────────────────────────────────
SYNTHESIS_PROMPT = (
    "The customer purchased TWO items: a linen shirt and a silk "
    "scarf. She washed both garments at home, and now wants to return "
    "both for a refund. Based on the policy context below, advise "
    "separately for each item whether the customer qualifies for a "
    "refund, citing the specific policy clause that determines the "
    "outcome for each. Provide both decisions and both citations.\n\n"
    "Context:\n{context}\n\n"
    "Two-item analysis:"
)


DEFAULT_MODEL = "gemma4:e4b"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_N = 10

# Pre-#399 default vs lifted — same caps as V3'.b/.c/.d so the cross-
# arm result is directly comparable to the 4-stage matrix.
CAP_DEFAULT = 400
CAP_LIFTED = 4096

ARMS = ("substitution", "synthesis")


def call_ollama(
    url: str, model: str, prompt: str,
    num_predict: int, temperature: float,
    timeout: float = 30.0,
) -> dict:
    """Single Ollama ``/api/generate`` call returning per-call telemetry.

    Identical signature/shape to V3'.b/.c/.d so the result JSON can be
    consumed by the same downstream tooling (e.g. a future
    swap_eval_report.py aggregator).
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
        # Full text retained so post-hoc analysis can compute
        # unique-response sets and inspect canonical text directly.
        # Robin Converse's 2026-05-23 issue #448 Finding 1 showed
        # 40/40 calls → 1 unique response on 26b substitution arm;
        # this field lets the JAMES side mirror that measurement
        # on e4b without re-running the sweep.
        "raw_response_text": raw_response,
        "non_empty": bool(raw_response.strip()),
        # Substitution-mode signal: the response should contain the
        # canonical clause about linen/silk/cashmere final sale once
        # washed. If the answer is verbatim retrieval the phrase is
        # present; if the model paraphrased we still catch the policy
        # via fabric mention.
        "has_linen_clause": "linen" in raw_response.lower(),
        # Synthesis-mode signal: the recommendation should include a
        # decision keyword (no refund / not eligible / refund / etc.)
        # AND cite the policy clause.
        "has_decision_keyword": any(
            kw in raw_response.lower()
            for kw in ("not eligible", "no refund", "refund",
                       "qualif", "denied", "ineligible")
        ),
    }


def run_sweep(args: argparse.Namespace) -> dict:
    """Run ``args.n`` calls at each (arm × cap), aggregate."""
    prompts = {
        "substitution": SUBSTITUTION_PROMPT.format(context=CONTEXT_FIXTURE),
        "synthesis":    SYNTHESIS_PROMPT.format(context=CONTEXT_FIXTURE),
    }
    results: dict = {
        "metadata": {
            "started_utc": datetime.now(timezone.utc).isoformat(),
            "driver": "v3prime_e_mode_split.py",
            "stage": "mode_split",
            "hypothesis": (
                "Robin Converse substitution/synthesis split "
                "(LinkedIn 2026-05-22~24); Ali Afana elevated to "
                "architectural primitive 2026-05-24."
            ),
            "model": args.model,
            "temperature": args.temperature,
            "n_per_cap_per_arm": args.n,
            "context_chars": len(CONTEXT_FIXTURE),
            "caps_tested": [CAP_DEFAULT, CAP_LIFTED],
            "arms": list(ARMS),
            "ollama_url": args.url,
            "prompt_templates": {
                "substitution": (
                    "verbatim retrieval — no reasoning, render canonical text"
                ),
                "synthesis": (
                    "new recommendation — reason over clauses, generate text"
                ),
            },
            "context_fixture_role": (
                "Sibling shape to Robin's e-commerce policy fixture; "
                "English by design so the cross-replication is direct."
            ),
        },
        "fixtures": {
            "context":             CONTEXT_FIXTURE,
            "substitution_prompt": prompts["substitution"],
            "synthesis_prompt":    prompts["synthesis"],
        },
        "runs": {
            arm: {str(CAP_DEFAULT): [], str(CAP_LIFTED): []}
            for arm in ARMS
        },
    }
    total = 2 * 2 * args.n
    done = 0
    for arm in ARMS:
        prompt = prompts[arm]
        for cap in (CAP_DEFAULT, CAP_LIFTED):
            for i in range(args.n):
                done += 1
                print(
                    f"  [{done:>2}/{total}] arm={arm:<12} cap={cap:>4} "
                    f"run={i+1:>2}/{args.n}  ...",
                    end="", flush=True,
                )
                r = call_ollama(
                    args.url, args.model, prompt, cap, args.temperature,
                )
                r["run_idx"] = i + 1
                r["num_predict"] = cap
                r["arm"] = arm
                results["runs"][arm][str(cap)].append(r)
                if "_error" in r:
                    print(f"  ERROR  {r['_error']}")
                    continue
                status = "OK" if r.get("non_empty") else "EMPTY"
                print(
                    f"  {r['elapsed_s']:>5.1f}s  {status:<5}  "
                    f"done={r['ollama_done_reason']}  "
                    f"bytes={r['response_bytes']}"
                )
    results["metadata"]["completed_utc"] = (
        datetime.now(timezone.utc).isoformat()
    )
    return results


def summarize(results: dict) -> None:
    """Print summary table + pattern-S/N decision tree to stdout."""
    print()
    print("━" * 78)
    print(" V3'.e — substitution vs synthesis mode split — SUMMARY")
    print("━" * 78)
    md = results["metadata"]
    print(f" Model:        {md['model']}")
    print(f" Temperature:  {md['temperature']}")
    print(f" N per cell:   {md['n_per_cap_per_arm']}   "
          f"(arm × cap matrix = 4 cells)")
    print(f" Context:      {md['context_chars']} chars (e-commerce policy)")
    print(" Hypothesis:   Robin Converse substitution/synthesis split")
    print()
    print(f" {'Arm':<14} | {'Cap':>5} | {'Success':>10} | "
          f"{'Avg lat':>9} | {'Domain hit':>11} | {'Unique':>7}")
    print(f" {'─' * 14}-+-{'─' * 5}-+-{'─' * 10}-+-{'─' * 9}-+-"
          f"{'─' * 11}-+-{'─' * 7}")
    cells: dict = {}
    for arm in ARMS:
        for cap_key in sorted(results["runs"][arm].keys(), key=int):
            runs = results["runs"][arm][cap_key]
            n = len(runs)
            non_empty = sum(1 for r in runs if r.get("non_empty"))
            avg_lat = sum(r.get("elapsed_s", 0) for r in runs) / max(n, 1)
            domain_key = ("has_linen_clause" if arm == "substitution"
                          else "has_decision_keyword")
            domain_hit = sum(1 for r in runs if r.get(domain_key))
            # Unique-response count per cell (Robin Finding 1
            # signature). On 26b substitution, 40/40 → 1. We compute
            # this from sha256-prefix (fast, 64-bit collision space)
            # and fall back to raw_response_text equality if the
            # earlier field isn't present (legacy JSON compatibility).
            unique = len({
                r.get("raw_response_sha256")
                or r.get("raw_response_text", "")
                for r in runs if r.get("non_empty")
            })
            cells[(arm, int(cap_key))] = {
                "n": n, "non_empty": non_empty,
                "avg_lat": avg_lat, "domain_hit": domain_hit,
                "unique_outputs": unique,
            }
            print(
                f" {arm:<14} | {cap_key:>5} | "
                f"{non_empty:>5}/{n:<4} | {avg_lat:>6.1f}s   | "
                f"{domain_hit:>5}/{n:<4} | {unique:>4}/{n:<2}"
            )
    print()

    # ── Decision tree ────────────────────────────────────────────────
    n_cell = next(iter(cells.values()))["n"] if cells else 0
    if n_cell == 0:
        print(" Decision tree: (no runs completed)")
        print()
        return
    hi = max(1, int(0.9 * n_cell))   # ≥ 9/10 default
    lo = max(0, int(0.3 * n_cell))   # ≤ 3/10 default

    sub_400  = cells[("substitution", CAP_DEFAULT)]["non_empty"]
    sub_4096 = cells[("substitution", CAP_LIFTED)]["non_empty"]
    syn_400  = cells[("synthesis",    CAP_DEFAULT)]["non_empty"]
    syn_4096 = cells[("synthesis",    CAP_LIFTED)]["non_empty"]

    print(" Decision tree:")
    if (sub_400 >= hi and syn_400 <= lo
            and sub_4096 >= hi and syn_4096 >= hi):
        print("   → Pattern S CONFIRMED — substitution/synthesis split")
        print("     replicates Robin's finding on gemma4:e4b at JAMES caps.")
        print("     Cap pathology reads as synthesis-mode entry cost; the")
        print("     V3'.a/.b/.c/.d 4-stage uniformity is consistent with")
        print("     all four stages routing through synthesis under their")
        print("     surface tasks. Promote to joint-piece headline (Track 5).")
    elif (sub_400 <= lo and syn_400 <= lo
          and sub_4096 >= hi and syn_4096 >= hi):
        print("   → Pattern N (cap-floor mode-independent)")
        print("     Both modes hit the ~500-token floor at cap=400.")
        print("     Robin's split is real in her data but is a separate")
        print("     mechanism from the cap pathology we measured. Joint")
        print("     piece carries TWO mechanisms, not one merged story.")
    elif (sub_400 >= hi and syn_400 >= hi
          and sub_4096 >= hi and syn_4096 >= hi):
        print("   → Pattern Z (no floor visible)")
        print("     Both modes clear cap=400; the floor in V3'.a~d may")
        print("     have been task-specific (cognitive prompts vs simple")
        print("     retrieval/recommendation). Worth a third arm closer")
        print("     to query_rewrite shape to disambiguate.")
    else:
        print("   → Partial signal — examine per-cell mix.")
        print(f"     substitution: {sub_400}/{n_cell} @ 400, "
              f"{sub_4096}/{n_cell} @ 4096")
        print(f"     synthesis:    {syn_400}/{n_cell} @ 400, "
              f"{syn_4096}/{n_cell} @ 4096")
    print()


def save_results(results: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = (
        results["metadata"]["started_utc"]
        .replace(":", "")
        .replace("-", "")
        .split(".")[0]
    )
    out_path = out_dir / f"v3prime-e-mode-split-{ts}.json"
    out_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_path


def main():
    parser = argparse.ArgumentParser(
        description="V3'.e - substitution vs synthesis mode split.",
    )
    parser.add_argument(
        "--n", type=int, default=DEFAULT_N,
        help=f"Calls per cell (default {DEFAULT_N}). "
             f"Total trials = 4 × N (arm × cap matrix).",
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"Ollama model tag (default {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--url", default=DEFAULT_OLLAMA_URL,
        help=f"Ollama /api/generate URL (default {DEFAULT_OLLAMA_URL})",
    )
    parser.add_argument(
        "--temperature", type=float, default=DEFAULT_TEMPERATURE,
        help=f"Sampling temperature (default {DEFAULT_TEMPERATURE})",
    )
    parser.add_argument(
        "--out-dir", default="reports/research-runs",
        help="Output directory for the JSON result (default %(default)s)",
    )
    args = parser.parse_args()

    print()
    print("V3'.e — substitution vs synthesis mode split")
    print(f"  model={args.model}  temp={args.temperature}  n={args.n}")
    print(f"  caps={CAP_DEFAULT}, {CAP_LIFTED}   "
          f"total trials = {4 * args.n}")
    print()

    results = run_sweep(args)
    out_path = save_results(results, Path(args.out_dir))
    summarize(results)
    print(f" Saved: {out_path}")


if __name__ == "__main__":
    main()
