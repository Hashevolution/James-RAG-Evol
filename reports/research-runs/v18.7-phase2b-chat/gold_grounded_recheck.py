"""Gold-signal grounded recheck of v18.7 Phase 2b chat-mode 3-cell.

Operator catch v18.6 (project_judge_reliability_gold_grounded_v18_6):
"Claude 가 판정 기준이었잖아. Claude 가 낸 답이 확실히 맞는지도 점검 가능?"

Same protocol as the v18.5 Path A multihop recheck, applied to the
chat-mode fixture's factual_chat sub-class (the only sub-class that
carries gold_signals — see CAVEAT_BLOCK['chat_mode_lenient_judge']).
The other 3 sub-classes (small_talk / open_question / multi_turn)
have no deterministic ground truth so judge-only verdicts stand.

Outputs:
  - stdout table — judge vs gold agreement per cell, factual_chat only
  - gold_grounded_summary.json — machine-readable per-cell dict

Run from repo root:

    python reports/research-runs/v18.7-phase2b-chat/gold_grounded_recheck.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
FIXTURE_PATH = REPO_ROOT / "eval" / "chat_mode_queries.json"
RESULTS_DIR = REPO_ROOT / "reports" / "research-runs" / "v18.7-phase2b-chat"

CELLS = [
    ("A", "cellA.json", "gemma4:e4b OFF cap=400"),
    ("B", "cellB.json", "gemma3:4b cap=400"),
    ("C", "cellC.json", "gemma3:12b cap=400"),
]


def _load_gold_index() -> Dict[int, list]:
    """Return question_id → gold_signals[] for factual_chat queries only."""
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return {
        q["id"]: q.get("gold_signals", [])
        for q in data["queries"]
        if q.get("question_type") == "factual_chat"
    }


def check_gold(answer: str, gold_signals: list) -> Tuple[bool, int]:
    """Substring check — case-insensitive — for term OR any alias.
    Single-hit threshold (any gold_signal counted once)."""
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
                break
    return hits >= 1, hits


def recheck_cell(label: str, path: Path, model_desc: str,
                 gold_by_id: Dict[int, list]) -> dict:
    """Per-cell judge vs gold agreement on factual_chat rows only."""
    rows = json.loads(path.read_text(encoding="utf-8"))["rows"]
    rows = [r for r in rows if r["id"] in gold_by_id]   # factual_chat
    n = len(rows)
    lj = cj = 0
    lg = cg = 0
    lj_agree = cj_agree = 0
    over_local: List[dict] = []
    under_local: List[dict] = []
    for r in rows:
        gold = gold_by_id[r["id"]]
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
        if ljv == "CORRECT" and not lg_present:
            over_local.append({"id": r["id"], "run": r.get("run"),
                               "answer_head": r.get("local_answer", "")[:120]})
        if ljv != "CORRECT" and lg_present:
            under_local.append({"id": r["id"], "run": r.get("run"),
                                "judge_verdict": ljv,
                                "answer_head": r.get("local_answer", "")[:120]})
    return {
        "cell": label,
        "model_desc": model_desc,
        "scope": "factual_chat only",
        "n_trials": n,
        "local_judge_correct":     round(lj / n, 3) if n else 0,
        "local_gold_correct":      round(lg / n, 3) if n else 0,
        "local_agreement":         round(lj_agree / n, 3) if n else 0,
        "local_over_credits":      len(over_local),
        "local_under_credits":     len(under_local),
        "cloud_judge_correct":     round(cj / n, 3) if n else 0,
        "cloud_gold_correct":      round(cg / n, 3) if n else 0,
        "cloud_agreement":         round(cj_agree / n, 3) if n else 0,
        "over_credit_examples":    over_local[:5],
        "under_credit_examples":   under_local[:5],
    }


def main() -> int:
    gold_by_id = _load_gold_index()
    print(f"\nfactual_chat queries with gold_signals: "
          f"{sorted(gold_by_id.keys())}\n")

    summaries = []
    for label, fname, desc in CELLS:
        path = RESULTS_DIR / fname
        if not path.exists():
            print(f"[WARN] missing {path}", file=sys.stderr)
            continue
        s = recheck_cell(label, path, desc, gold_by_id)
        summaries.append(s)

    print("=== gold-signal grounded recheck — factual_chat ===\n")
    header = (
        f'{"Cell":<5} | {"model":<28} | '
        f'{"LOCAL judge":>11} | {"LOCAL gold":>10} | {"agree":>5}'
        f' | {"over+":>5} | {"under-":>6}'
        f' || {"CLOUD judge":>11} | {"CLOUD gold":>10}'
    )
    print(header)
    print("-" * len(header))
    for s in summaries:
        print(
            f'{s["cell"]:<5} | {s["model_desc"]:<28} | '
            f'{s["local_judge_correct"]:>11.2f} | '
            f'{s["local_gold_correct"]:>10.2f} | {s["local_agreement"]:>5.2f}'
            f' | {s["local_over_credits"]:>5} | {s["local_under_credits"]:>6}'
            f' || {s["cloud_judge_correct"]:>11.2f} | '
            f'{s["cloud_gold_correct"]:>10.2f}'
        )
    print()

    # Judge-bias delta table.
    print("=== judge bias (local) — judge says CORRECT but gold absent ===")
    for s in summaries:
        bias = round(s["local_judge_correct"] - s["local_gold_correct"], 3)
        sign = "+" if bias >= 0 else ""
        print(f"  Cell {s['cell']} {s['model_desc']:<28} bias = {sign}{bias}")
    print()

    out_path = RESULTS_DIR / "gold_grounded_summary.json"
    out_path.write_text(
        json.dumps(summaries, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"saved → {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":   # pragma: no cover
    sys.exit(main())
