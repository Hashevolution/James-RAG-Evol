"""
Audit e4b synthesis cap=4096 eval_count distribution across all D3 JSONs.

Goal: determine `gemma4:e4b` synthesis-mode natural completion budget upper bound.

For each trial:
- ollama_eval_count (token usage)
- ollama_done_reason ("stop" = natural; "length" = cap hit)
- has_linen_clause + has_decision_keyword (success markers)

Outputs distribution stats per (model, cap, temp) cell, focused on
the e4b synthesis cap=4096 cell — the natural-budget upper-bound question.

Pure read-only audit. No measurement run. No state change.
"""

from __future__ import annotations

import glob
import json
import statistics
from pathlib import Path
from collections import defaultdict

REPO = Path(__file__).resolve().parents[2]
RUN_DIR = REPO / "reports" / "research-runs"


def main() -> None:
    pattern = str(RUN_DIR / "v3prime-e-mode-split-20260529T*.json")
    files = sorted(glob.glob(pattern))

    # cell key = (model, temperature, cap)
    cells: dict[tuple[str, float, int], list[dict]] = defaultdict(list)

    for path in files:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        meta = doc.get("metadata", {})
        model = meta.get("model")
        temp = meta.get("temperature")
        if not model or temp is None:
            continue
        runs = doc.get("runs", {})
        syn = runs.get("synthesis", {})
        for cap_str, trials in syn.items():
            try:
                cap = int(cap_str)
            except ValueError:
                continue
            for t in trials:
                cells[(model, float(temp), cap)].append(t)

    print("# v3prime e4b cap=4096 natural-budget audit\n")
    print(f"Source files scanned: {len(files)}")
    print(f"Cells found: {len(cells)}\n")

    # Focus on e4b synthesis at every cap, both temperatures
    print("## gemma4:e4b synthesis - all (cap, temp) cells\n")
    print(
        "| temp | cap  | n  | success | done=stop | done=length | "
        "eval median | min | max | p75 |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|")
    e4b_cells = sorted(
        [k for k in cells if k[0] == "gemma4:e4b"],
        key=lambda k: (k[1], k[2]),
    )
    for key in e4b_cells:
        trials = cells[key]
        evals = [t["ollama_eval_count"] for t in trials]
        successes = sum(
            1
            for t in trials
            if t.get("has_linen_clause") and t.get("has_decision_keyword")
        )
        done_stop = sum(1 for t in trials if t.get("ollama_done_reason") == "stop")
        done_length = sum(
            1 for t in trials if t.get("ollama_done_reason") == "length"
        )
        _, temp, cap = key
        n = len(trials)
        med = int(statistics.median(evals))
        p75_pos = int(0.75 * (n - 1))
        p75 = sorted(evals)[p75_pos]
        print(
            f"| {temp} | {cap} | {n} | {successes}/{n} | "
            f"{done_stop} | {done_length} | {med} | "
            f"{min(evals)} | {max(evals)} | {p75} |"
        )

    # Headline question: cap=4096 e4b natural budget
    print("\n## Headline cell - gemma4:e4b synthesis, cap=4096, temp=0.2\n")
    target = ("gemma4:e4b", 0.2, 4096)
    trials = cells.get(target, [])
    if not trials:
        print("(no trials found)")
        return

    evals = [t["ollama_eval_count"] for t in trials]
    print(f"- N trials: {len(trials)}")
    print(f"- eval_count distribution (raw): {sorted(evals)}")
    print(f"- min: {min(evals)}")
    print(f"- median: {int(statistics.median(evals))}")
    print(f"- mean: {statistics.mean(evals):.1f}")
    print(f"- max: {max(evals)}")
    print(f"- stdev: {statistics.stdev(evals):.1f}" if len(evals) > 1 else "")

    cap_hits = sum(1 for e in evals if e >= 4090)
    nat_finish = sum(1 for e in evals if e < 4090)
    print(f"- cap-hit count (eval >= 4090): {cap_hits}/{len(trials)}")
    print(f"- natural finish (eval < 4090): {nat_finish}/{len(trials)}")

    done_stop = sum(1 for t in trials if t.get("ollama_done_reason") == "stop")
    done_length = sum(
        1 for t in trials if t.get("ollama_done_reason") == "length"
    )
    print(f"- done_reason='stop': {done_stop}/{len(trials)}")
    print(f"- done_reason='length': {done_length}/{len(trials)}")

    succ = sum(
        1
        for t in trials
        if t.get("has_linen_clause") and t.get("has_decision_keyword")
    )
    print(f"- success (has_linen + has_decision): {succ}/{len(trials)}")

    # Reference cell — temp=0.7
    print(
        "\n## Reference cell - gemma4:e4b synthesis, cap=4096, temp=0.7\n"
    )
    target2 = ("gemma4:e4b", 0.7, 4096)
    trials2 = cells.get(target2, [])
    if trials2:
        evals2 = [t["ollama_eval_count"] for t in trials2]
        print(f"- N: {len(trials2)}")
        print(f"- eval distribution (sorted): {sorted(evals2)}")
        print(f"- median: {int(statistics.median(evals2))}")
        print(f"- max: {max(evals2)}")
        cap_hits2 = sum(1 for e in evals2 if e >= 4090)
        print(f"- cap-hit (eval >= 4090): {cap_hits2}/{len(trials2)}")
        done_length2 = sum(
            1 for t in trials2 if t.get("ollama_done_reason") == "length"
        )
        print(f"- done_reason='length': {done_length2}/{len(trials2)}")


if __name__ == "__main__":
    main()
