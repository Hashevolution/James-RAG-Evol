"""How often does a bare-entity query produce a bare claim? — option A.

Why this shape of measurement
-----------------------------
#1154 annotates when an answer is at or under ``BARE_CLAIM_ANSWER_CHARS``
(30) and the fact check reports an unsupported claim. The 2026-09-27
arms never fired it: short answers are ~1% of traffic (3 of 288 across 16
step7 runs) and the one candidate was 32 characters.

Three ways to get the path exercised were considered
(`reports/research-runs/verify-echo-reachability-20260927.md` §5 and the
2026-09-27 discussion). Forcing short answers with
``JAMES_RESPONSE_STYLE=terse`` was rejected: terse v4 deliberately
carries **no** length cap because v2's "MAXIMUM 30 words" was caught as
measurement-fitting (see the history block in
``core/response_style_presets.py``). Picking a knob so that a threshold
fires is the same move.

What is legitimate is **stratified sampling**. All three observed short
answers came from one query shape — a bare entity attribute — so this
probe repeats those queries at default settings and reports the
distribution. Nothing about the system is changed; only how often the
relevant stratum is sampled.

Queries (step7 fixture ids, verbatim):
  15  David Soria Parra가 누구야?        (abstention_truth: present)
  17  Anthropic의 CEO는 누구야?          (absent — the corpus holds
      Palantir's CEO, which is the trap that produced "Alex Karp")
  18  Tesla의 창립자는 누구야?           (present)

Server lifecycle and the pinned measurement env are **imported** from
``scripts/qvt_capture_baseline.py`` rather than copied — a third copy of
those helpers is the drift #1149 diagnosed.

Usage
-----
    python scripts/research/bare_claim_frequency.py --repeats 10
    python scripts/research/bare_claim_frequency.py --repeats 10 --md
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:
        pass

import qvt_capture_baseline as cap  # noqa: E402

DEFAULT_IDS = (15, 17, 18)
DB = ROOT / "james_audit.db"


def _fixture_queries(ids) -> List[Dict[str, Any]]:
    path = ROOT / "eval" / "regression" / "step7_queries.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    by_id = {q["id"]: q for q in data["queries"]}
    missing = [i for i in ids if i not in by_id]
    if missing:
        sys.exit(f"[bare-claim] fixture ids not found: {missing}")
    return [by_id[i] for i in ids]


def _ask(text: str, api_key: str, qid: int, bearer: Optional[str],
         timeout: int = 180) -> Optional[str]:
    """POST one query. Returns the answer text, or None on failure.

    Body shape mirrors ``scripts/bench.py`` exactly — `question` +
    `api_key`, not `query`. The first version of this probe guessed
    `{"query": ..., "mode": ...}` and every call came back 422.
    """
    body = json.dumps({
        "question": text,
        "api_key": api_key,
        "session_id": f"bareclaim_{qid}",
        "mode_override": "retrieval",
    }).encode("utf-8")
    req = urllib.request.Request(
        cap.SERVER_BASE_URL.rstrip("/") + "/query/",
        data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    if bearer:
        req.add_header("Authorization", f"Bearer {bearer}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        print(f"    [ask] {type(exc).__name__}: {exc}")
        return None
    for key in ("answer", "response", "result", "text"):
        if isinstance(payload.get(key), str):
            return payload[key]
    return json.dumps(payload, ensure_ascii=False)[:2000]


# `_format` appends this to the answer when the recommendation is
# annotate, so the `/query/` audit row holds answer + note — NOT the
# string `_decide` measured. Measuring the row directly reported every
# annotated bare claim as a ~130-character answer and concluded the path
# had not fired, when it had fired four times. Stripped back off here.
#
# The pattern itself lives in eval/qvt/annotation_axis.py since
# 2026-09-28, where tests/test_qvt_annotation_axis.py pins it against
# what Verifier._format actually emits. One definition, two readers —
# the #1149 lesson about copied guards applies to copied regexes too.
from eval.qvt.annotation_axis import strip_note as _pre_note  # noqa: E402


def _verify_rows(since: str, until: str) -> List[Dict[str, Any]]:
    """One record per query episode in the window: answer length and the
    verifier's recommendation, read from the audit log rather than
    inferred from the HTTP response."""
    con = sqlite3.connect("file:{}?mode=ro".format(DB.as_posix()), uri=True)
    try:
        rows = list(con.execute(
            "select endpoint, query, answer from audit_log "
            "where timestamp between ? and ? order by id",
            (since, until)))
    finally:
        con.close()

    episodes: List[Dict[str, Any]] = []
    cur: List[tuple] = []
    for r in rows:
        cur.append(r)
        if r[0] == "/query/":
            rec, unsupported = "accept", 0
            for ep_row in cur:
                summary = str(ep_row[2] or "")
                if ep_row[0] == "reason:verify" and "rec=" in summary:
                    rec = summary.split("rec=")[1].split()[0].strip('",')
                    if "unsupp=" in summary:
                        try:
                            unsupported = int(
                                summary.split("unsupp=")[1].split()[0].strip('",'))
                        except ValueError:
                            pass
            final = str(r[2] or "")
            pre = _pre_note(final)
            episodes.append({
                "query": str(r[1] or "")[:40],
                "final_chars": len(final.strip()),
                "answer_chars": len(pre),
                "recommendation": rec,
                "unsupported": unsupported,
            })
            cur = []
    return episodes


def render(eps: List[Dict[str, Any]], bare_chars: int, md: bool,
           attempted: int = 0, failed: int = 0) -> str:
    L: List[str] = []
    h, b = ("## ", "- ") if md else ("=== ", "  - ")
    total = len(eps)

    # The first run of this probe sent a malformed body, every call
    # returned 422, and the report concluded "the path did not fire" —
    # a negative finding drawn from zero data. Refuse to conclude
    # instead. Same shape as eval/qvt/capture_integrity.abort_reason.
    if failed or not total:
        L.append(f"{h}NO VERDICT — the run did not collect usable data")
        L.append("")
        L.append(f"{b}calls attempted: {attempted}")
        L.append(f"{b}calls failed: {failed}")
        L.append(f"{b}episodes recorded: {total}")
        L.append(f"{b}**Nothing is concluded from this run.** Fix the "
                 f"failures and re-run; an empty sample is not evidence "
                 f"that the path does not fire.")
        return "\n".join(L)

    bare = [e for e in eps if e["answer_chars"] <= bare_chars]
    fired = [e for e in bare if e["recommendation"] == "annotate"]
    # Self-check. `_decide` cannot annotate on a single unsupported claim
    # unless the answer was bare, so a row saying otherwise means the
    # length being measured is not the length the verifier saw — the bug
    # `_pre_note` fixes. Surfaced rather than silently tallied.
    impossible = [e for e in eps
                  if e["recommendation"] == "annotate"
                  and e["unsupported"] == 1
                  and e["answer_chars"] > bare_chars]

    L.append(f"{h}Distribution over {total} episodes "
             f"(BARE_CLAIM_ANSWER_CHARS = {bare_chars})")
    L.append("")
    if md:
        L.append("| query | answer chars | +note | rec | unsupported |")
        L.append("|---|---:|---:|---|---:|")
    for e in eps:
        mark = "  <-- BARE CLAIM FIRED" if (
            e in fired) else (" <= bare" if e in bare else "")
        if md:
            L.append("| {} | {} | {} | {} | {} |{}".format(
                e["query"], e["answer_chars"], e["final_chars"],
                e["recommendation"], e["unsupported"],
                " **fired**" if e in fired else ""))
        else:
            L.append("  {:40} {:5} (+note {:5}) {:9} unsupp={}{}".format(
                e["query"], e["answer_chars"], e["final_chars"],
                e["recommendation"], e["unsupported"], mark))
    lengths = sorted(e["answer_chars"] for e in eps)
    L.append("")
    if lengths:
        L.append("{}answer chars: min {} / median {} / max {}".format(
            b, lengths[0], lengths[len(lengths) // 2], lengths[-1]))
    L.append(f"{b}at or under {bare_chars} chars: {len(bare)}/{total}")
    L.append(f"{b}bare-claim annotations actually fired: {len(fired)}")
    near = [e for e in eps if bare_chars < e["answer_chars"] <= bare_chars + 10]
    L.append(f"{b}within 10 chars above the boundary (would fire if the "
             f"threshold were slightly higher): {len(near)}")
    if impossible:
        L.append(f"{b}🔴 **{len(impossible)} row(s) annotate on one "
                 f"unsupported claim with an answer over {bare_chars} "
                 f"chars.** `_decide` cannot do that, so the length being "
                 f"measured is not the length the verifier saw. Do not "
                 f"read the rest of this table.")
    elif fired:
        L.append(f"{b}**The path fired.** {len(fired)} bare claim(s) were "
                 f"annotated that the pre-#1154 code would have shipped "
                 f"unverified — the length gate skipped answers under "
                 f"{bare_chars} chars entirely, and the threshold of 2 "
                 f"would not have annotated a single claim.")
    elif not bare:
        L.append(f"{b}No answer landed at or under the threshold in this "
                 f"sample, so the path was not exercised. That is not "
                 f"evidence it never fires — see the boundary count above.")
    return "\n".join(L)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repeats", type=int, default=10,
                    help="repetitions per query (default 10)")
    ap.add_argument("--ids", type=str, default="",
                    help=f"comma-separated fixture ids (default {DEFAULT_IDS})")
    ap.add_argument("--md", action="store_true")
    args = ap.parse_args(argv)

    ids = ([int(x) for x in args.ids.split(",") if x.strip()]
           if args.ids else list(DEFAULT_IDS))
    queries = _fixture_queries(ids)

    from core.reasoning.verify import BARE_CLAIM_ANSWER_CHARS

    server_env = {**cap.os.environ, **cap._BASELINE_ENV}
    print(f"[bare-claim] {len(queries)} queries x {args.repeats} repeats "
          f"= {len(queries) * args.repeats} calls")
    print(f"[bare-claim] pinned env: "
          f"{ {k: server_env.get(k) for k in cap._BASELINE_ENV} }")

    api_key = cap._load_api_key() if hasattr(cap, "_load_api_key") else ""
    if not api_key:
        import bench  # noqa: WPS433 — same loader the bench uses
        api_key = bench._load_api_key()

    server = cap._spawn_server(server_env)
    if server is None:
        return 2
    since = cap.datetime.now().isoformat()
    attempted = failed = 0
    try:
        bearer = cap._mint_employee_jwt()
        for rep in range(args.repeats):
            for q in queries:
                t0 = time.time()
                attempted += 1
                ans = _ask(q["text"], api_key, q["id"], bearer)
                if ans is None:
                    failed += 1
                    # A malformed request fails identically every time;
                    # 30 identical 422s is 30 wasted minutes.
                    if failed >= 3 and not (attempted - failed):
                        print("  [abort] first 3 calls all failed — "
                              "stopping rather than repeating a broken "
                              "request 30 times")
                        break
                print("  rep {}/{} id={} {:.1f}s chars={}".format(
                    rep + 1, args.repeats, q["id"], time.time() - t0,
                    len(str(ans or "").strip())))
            else:
                continue
            break
    finally:
        cap._shutdown_server(server)
    until = cap.datetime.now().isoformat()

    eps = _verify_rows(since, until)
    print()
    print(render(eps, BARE_CLAIM_ANSWER_CHARS, args.md, attempted, failed))
    return 1 if (failed or not eps) else 0


if __name__ == "__main__":
    raise SystemExit(main())
