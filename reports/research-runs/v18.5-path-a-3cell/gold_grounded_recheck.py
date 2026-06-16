"""Gold-signal grounded recheck of v18.5 Path A 3-cell paired runs.

Operator catch 2026-06-16 v18.6: "Claude 가 판정 기준이었잖아.
Claude 가 낸 답이 확실히 맞는지도 점검 가능?".

This script answers the operator's question deterministically. It
walks the three cellX_*.json files, pulls each query's gold_signals
from the MultiHop-RAG fixture, and tests each local_answer +
cloud_answer for substring presence of the gold term or any
declared alias (case-insensitive). The result is reported alongside
the existing judge verdicts so judge-vs-gold agreement becomes
visible.

Why a separate script (not inline in the harness):
  - the v18.5 harness wrote the JSONs already; rerunning the cells
    just to add this column wastes ~45 min of paired LLM time
  - the deterministic check is hermetic — no LLM in the loop, so it
    runs in < 1 s per cell
  - operator-facing artifact: any reviewer can replay the same
    judgement from the committed raw JSONs without spinning up
    Claude or Ollama

Run from the repo root:

    python reports/research-runs/v18.5-path-a-3cell/gold_grounded_recheck.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
FIXTURE_PATH = REPO_ROOT / "workspaces" / "hotpot_eval" / "eval" / "multihop_rag_queries.json"
RESULTS_DIR = REPO_ROOT / "reports" / "research-runs" / "v18.5-path-a-3cell"

CELLS = [
    ("A", "cellA_gemma4_off_cap400.json"),
    ("B", "cellB_gemma4_on_cap2000.json"),
    ("C", "cellC_gemma3_12b_cap400.json"),
]


def _load_gold_index() -> Dict[int, list]:
    """Return question_id → gold_signals[]"""
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return {q["id"]: q.get("gold_signals", []) for q in data["queries"]}


def check_gold(answer: str, gold_signals: list) -> Tuple[bool, int]:
    """Substring check — case-insensitive — for term OR any alias.

    Returns (any_hit, hit_count). A query whose gold has three
    signals and the answer mentions one of them returns
    (True, 1) — single hit threshold is the operator-grade default
    used by the writeup. Stricter all-three thresholds are available
    via the all_present flag in the calling table but were not the
    headline metric.
    """
    if not answer:
        return False, 0
    ans = answer.lower()
    hits = 0
    for sig in gold_signals:
        terms = [sig.get("term", "")] + list(sig.get("aliases", []))
        for t in terms:
            t = (t or "").lower().strip()
            if t and t in ans:
                hits += 1
                break    # one term-or-alias per gold_signal counts once
    return hits >= 1, hits


def recheck_cell(label: str, path: Path, gold_by_id: Dict[int, list]) -> dict:
    """Compute judge vs gold agreement on a single cell's rows."""
    rows = json.loads(path.read_text(encoding="utf-8"))["rows"]
    n = len(rows)
    lj = cj = 0           # judge said CORRECT
    lg = cg = 0           # gold-signal present
    lj_agree = cj_agree = 0
    over_local: List[dict] = []      # judge CORRECT, gold absent
    under_local: List[dict] = []     # judge ABSTAINED/INCORRECT, gold present
    for r in rows:
        gold = gold_by_id.get(r["id"], [])
        if not gold:
            continue
        ljv = r["local_verdict"]
        cjv = r["cloud_verdict"]
        lg_present, _ = check_gold(r.get("local_answer", ""), gold)
        cg_present, _ = check_gold(r.get("cloud_answer", ""), gold)
        lj += (ljv == "CORRECT")
        cj += (cjv == "CORRECT")
        lg += lg_present
        cg += cg_present
        lj_agree += ((ljv == "CORRECT") == lg_present)
        cj_agree += ((cjv == "CORRECT") == cg_present)
        # categorize disagreements (LOCAL side — judge bias of interest)
        if ljv == "CORRECT" and not lg_present:
            over_local.append({"id": r["id"], "type": r.get("type"),
                               "run": r.get("run")})
        if ljv != "CORRECT" and lg_present:
            under_local.append({"id": r["id"], "type": r.get("type"),
                                "run": r.get("run"),
                                "judge_verdict": ljv})
    return {
        "cell": label,
        "n": n,
        "local_judge_correct":     round(lj / n, 3),
        "local_gold_correct":      round(lg / n, 3),
        "local_agreement":         round(lj_agree / n, 3),
        "local_over_credits":      len(over_local),
        "local_under_credits":     len(under_local),
        "cloud_judge_correct":     round(cj / n, 3),
        "cloud_gold_correct":      round(cg / n, 3),
        "cloud_agreement":         round(cj_agree / n, 3),
        "over_credit_examples":    over_local[:5],
        "under_credit_examples":   under_local[:5],
    }


def main() -> int:
    gold_by_id = _load_gold_index()
    summaries = []
    for label, fname in CELLS:
        path = RESULTS_DIR / fname
        if not path.exists():
            print(f"[WARN] missing {path}", file=sys.stderr)
            continue
        s = recheck_cell(label, path, gold_by_id)
        summaries.append(s)

    print(f"\n=== gold-signal grounded recheck (n=27 per cell) ===\n")
    header = (
        f'{"Cell":<5} | {"LOCAL judge":>11} | {"LOCAL gold":>10} | {"agree":>5}'
        f' | {"over+":>5} | {"under-":>6}'
        f' || {"CLOUD judge":>11} | {"CLOUD gold":>10} | {"agree":>5}'
    )
    print(header)
    print("-" * len(header))
    for s in summaries:
        print(
            f'{s["cell"]:<5} | {s["local_judge_correct"]:>11.2f} | '
            f'{s["local_gold_correct"]:>10.2f} | {s["local_agreement"]:>5.2f}'
            f' | {s["local_over_credits"]:>5} | {s["local_under_credits"]:>6}'
            f' || {s["cloud_judge_correct"]:>11.2f} | '
            f'{s["cloud_gold_correct"]:>10.2f} | {s["cloud_agreement"]:>5.2f}'
        )
    print()

    # JSON drop for downstream tooling.
    out_path = RESULTS_DIR / "gold_grounded_summary.json"
    out_path.write_text(
        json.dumps(summaries, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"saved → {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":   # pragma: no cover
    sys.exit(main())
