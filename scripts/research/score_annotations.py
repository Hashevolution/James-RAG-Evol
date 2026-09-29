"""Score verify's annotations over audit-log windows.

Reads each window's query episodes out of ``james_audit.db`` — the full
final answer (note included) and verify's recommendation — joins them to
the step7 fixture **by question text** (not by position, so a skipped or
blocked query cannot shift every row after it), and scores them with
``eval.qvt.annotation_axis``.

Windows can be grouped under a label so n runs of one arm aggregate:

    python scripts/research/score_annotations.py \\
        --window ON=2026-09-27T11:02:59,2026-09-27T11:37:20 \\
        --window ON=2026-09-27T11:59:54,2026-09-27T12:23:25 \\
        --window OFF=2026-09-27T11:37:20,2026-09-27T11:59:54

Read-only against the audit database.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass

from eval.qvt.annotation_axis import score_annotations  # noqa: E402

DB = ROOT / "james_audit.db"
FIXTURE = ROOT / "eval" / "regression" / "step7_queries.json"


def load_episodes(since: str, until: str, fixture: Dict[str, Any],
                  db: Path = DB) -> Dict[str, Any]:
    """Episodes in [since, until] joined to fixture ids by question text."""
    by_text = {q["text"].strip(): int(q["id"]) for q in fixture["queries"]}
    con = sqlite3.connect("file:{}?mode=ro".format(db.as_posix()), uri=True)
    try:
        rows = list(con.execute(
            "select endpoint, query, answer, blocked from audit_log "
            "where timestamp between ? and ? order by id", (since, until)))
    finally:
        con.close()

    episodes: List[Dict[str, Any]] = []
    unmatched: List[str] = []
    cur: List[tuple] = []
    for r in rows:
        cur.append(r)
        if r[0] != "/query/":
            continue
        rec = "accept"
        for ep in cur:
            s = str(ep[2] or "")
            if ep[0] == "reason:verify" and "rec=" in s:
                rec = s.split("rec=")[1].split()[0].strip('",')
        question = str(r[1] or "").strip()
        qid = by_text.get(question)
        if r[3]:
            pass  # security-blocked: nothing for verify to have annotated
        elif qid is None:
            unmatched.append(question[:40])
        else:
            episodes.append({"id": qid, "final_answer": str(r[2] or ""),
                             "annotated": rec == "annotate",
                             "recommendation": rec})
        cur = []
    return {"episodes": episodes, "unmatched": unmatched}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--window", action="append", required=True,
                    help="LABEL=SINCE,UNTIL (repeatable; same label aggregates)")
    ap.add_argument("--fixture", type=str, default=str(FIXTURE),
                    help="fixture the windows' questions are joined to "
                         "(default: step7). Use the workspace fixture for "
                         "external suites, e.g. workspaces/hotpot_eval/eval/"
                         "multihop_rag_queries.json — joined against the "
                         "wrong fixture every question is 'unmatched' and "
                         "the run exits non-zero rather than scoring nothing")
    ap.add_argument("--graded", action="store_true",
                    help="graded mode: also score answered truth=present "
                         "queries, treating graded==1.0 as right. Has a "
                         "known blind spot — see annotation_axis docs")
    ap.add_argument("--json", action="store_true",
                    help="emit per-label axis dicts as JSON")
    args = ap.parse_args(argv)

    fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    groups: "OrderedDict[str, List[Dict[str, Any]]]" = OrderedDict()
    problems: List[str] = []
    for spec in args.window:
        label, _, span = spec.partition("=")
        since, _, until = span.partition(",")
        if not (label and since and until):
            sys.exit(f"[score-annotations] bad --window {spec!r}")
        got = load_episodes(since.strip(), until.strip(), fixture)
        if not got["episodes"]:
            # Same rule as the bare-claim probe: an empty window is not a
            # finding, it is a mistyped timestamp.
            problems.append(f"{label} {since}..{until}: 0 episodes")
        if got["unmatched"]:
            problems.append(f"{label}: {len(got['unmatched'])} unmatched "
                            f"questions, e.g. {got['unmatched'][:2]}")
        groups.setdefault(label, []).extend(got["episodes"])

    out = {}
    for label, eps in groups.items():
        axis = score_annotations(eps, fixture, strict=not args.graded)
        out[label] = axis
        if not args.json:
            print(f"[{label}] episodes={len(eps)} annotated={axis.n_annotated} "
                  f"scored={axis.n_scored} | {axis.summary()}")
    if args.json:
        print(json.dumps({k: v.to_dict() for k, v in out.items()},
                         ensure_ascii=False, indent=2))
    for p in problems:
        print(f"[warn] {p}", file=sys.stderr)
    # An all-unmatched window is the wrong-fixture case: episodes exist
    # but none joined. Same rule as an empty window — refuse, don't score.
    unjoined = [p for p in problems if "unmatched" in p]
    if any("0 episodes" in p for p in problems) or (
            unjoined and not any(groups.values())):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
