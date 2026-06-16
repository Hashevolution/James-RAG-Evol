"""Gold-signal grounded recheck — v18.7 Phase 3b local tier ladder.

4-cell multihop measurement (gemma3:4b / gemma4:e4b / gemma3:12b /
gemma3:27b), reasoning-isolated (gold evidence injected). The judge
(Claude) verdict alone said 4b=12b=gemma4=1.0 > 27b=0.704, which would
have (and briefly did) concluded "complexity escalation is pointless".
The deterministic gold_signals recheck below REVERSED that: 27b is the
only cell at gold-grounded 1.000, and the judge UNDER-credited it by
-0.296 because 27b answers verbosely and the judge tripped on the
elaboration. This is the v18.6 judge-reliability rule catching a
premature judge-only conclusion (project_d5_complexity_routing_negative
self-correction).

Run from repo root:
    python reports/research-runs/v18.7-phase3b-tier-ladder/gold_grounded_recheck.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
FIXTURE_PATH = REPO_ROOT / "workspaces" / "hotpot_eval" / "eval" / "multihop_rag_queries.json"
RESULTS_DIR = REPO_ROOT / "reports" / "research-runs" / "v18.7-phase3b-tier-ladder"

CELLS = [
    ("gemma3:4b",  "cell_light_4b.json",     "light"),
    ("gemma4:e4b", "cell_gemma4_e4b.json",   "(current default)"),
    ("gemma3:12b", "cell_standard_12b.json", "standard"),
    ("gemma3:27b", "cell_deep_27b.json",     "deep"),
]


def _gold_index() -> Dict[int, list]:
    fx = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return {q["id"]: q.get("gold_signals", []) for q in fx["queries"]}


def check_gold(answer: str, sigs: list) -> bool:
    a = (answer or "").lower()
    for s in sigs:
        terms = [s.get("term", "")] + list(s.get("aliases", []))
        if any(t and t.lower().strip() in a for t in terms):
            return True
    return False


def recheck(model: str, fname: str, rung: str,
            gold: Dict[int, list]) -> dict:
    path = RESULTS_DIR / fname
    rows = json.loads(path.read_text(encoding="utf-8"))["rows"]
    rows = [r for r in rows if gold.get(r["id"])]
    n = len(rows)
    j = sum(1 for r in rows if r["local_verdict"] == "CORRECT")
    g = sum(1 for r in rows if check_gold(r.get("local_answer", ""), gold[r["id"]]))
    elaps = [r["elapsed_sec"] for r in rows]
    return {
        "model": model, "rung": rung, "n": n,
        "judge_correct": round(j / n, 3) if n else 0,
        "gold_correct": round(g / n, 3) if n else 0,
        "judge_bias": round((j - g) / n, 3) if n else 0,
        "pair_latency_sec": round(sum(elaps) / len(elaps), 1) if elaps else 0,
    }


def main() -> int:
    gold = _gold_index()
    out = [recheck(m, f, r, gold) for m, f, r in CELLS
           if (RESULTS_DIR / f).exists()]

    print("\n=== v18.7 Phase 3b gold-grounded recheck (multihop, n=27/cell) ===\n")
    hdr = (f'{"model":<12} | {"rung":<18} | {"judge":>6} | '
           f'{"gold":>6} | {"bias":>7} | {"pair s":>7}')
    print(hdr)
    print("-" * len(hdr))
    for s in sorted(out, key=lambda x: -x["gold_correct"]):
        print(f'{s["model"]:<12} | {s["rung"]:<18} | '
              f'{s["judge_correct"]:>6.3f} | {s["gold_correct"]:>6.3f} | '
              f'{s["judge_bias"]:>+7.3f} | {s["pair_latency_sec"]:>7.1f}')
    print()
    print("KEY: gold-grounded REVERSES the judge-only ranking. 27b is the")
    print("only cell at gold 1.000 (judge under-credited it -0.296 due to")
    print("verbose answers). Escalation has a basis but it is modest")
    print("(+0.111 over 12b) and costs 2.3x latency + verbosity.")

    (RESULTS_DIR / "gold_grounded_summary.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nsaved → {(RESULTS_DIR / 'gold_grounded_summary.json').relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
