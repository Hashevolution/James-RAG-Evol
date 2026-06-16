"""Direction α ① — local vs cloud paired measurement (v3, abstraction-wired).

Supersedes `local_vs_cloud_multihop.py` (v2). Three things change:

  1. **paired n=3** (vs v2's n=1). Per `feedback_n1_verdict_inflation_n3_caught`:
     a single-shot per question is below the noise band threshold for
     LLM-judge graded — n=1 conclusions have collapsed before. n=3 paired
     gives a per-question MAJORITY verdict + a per-mode variance signal.
  2. **cloud path goes through `core.abstraction.run_cloud_egress`**. The
     gold-evidence fixture has no PII, so the abstraction is a no-op
     (`entities=[]` → mask is empty), but the call path is exercised
     end-to-end against a real Claude backend — proves the §5.7.13
     module works on real workloads, not just stubs.
  3. **summary JSON includes the §4.1 caveat block explicitly**. v2's
     caveat was a one-line field; v3 promotes it to a structured block
     so any downstream reader (joint piece draft, ablation diff) cannot
     accidentally drop it.

CAVEAT (also embedded in output JSON — REQUIRED reading before citing):
  - judge is Claude; one candidate is Claude → self-preference is possible.
    Mitigated by blinding A/B + evidence-grounded grading + raw dump.
  - gold-evidence fixture = reasoning isolated; ≠ real noisy retrieval
    pipeline. A separate full-pipeline run is needed for the production
    Pareto claim.
  - small n; first answerable N per question_type from the public
    MultiHop-RAG slice — not a representative random sample.
  - lenient judge: ABSTAINED + INCORRECT counted separately, but two
    contradictory CORRECT answers can both land CORRECT (the judge
    grades each independently).
  - `gemma3:4b` is the local default — does NOT equate to `gemma4 e4b`
    (the production tier, which has the §α-cycle thinking-trace floor
    on multihop). Re-run with `--local-model gemma4:e4b` to compare
    against the production tier.

Design = REASONING-ISOLATED: both models get the SAME full gold evidence,
so we measure reasoning, not retrieval. Cloud = Max-plan `claude -p`
(free research stand-in); a production tier needs the Anthropic API +
trust-zone PR per CLAUDE.md rule #4 (see §5.7.12 / §5.7.13).

Operator setup:
  $env:JAMES_ENABLE_CLAUDE_BACKEND = "1"
  python scripts/research/local_vs_cloud_paired.py --n-per-type 3 --n-runs 3

Output:
  reports/research-runs/alpha-8-local-vs-cloud-paired-<ts>.json
  (per-question rows + n-run aggregate + paired Δ + caveat block)
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import statistics
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

WS = ROOT / "workspaces" / "hotpot_eval"
FIXTURE = WS / "eval" / "multihop_rag_queries.json"
RAW = WS / "raw"

DEFAULT_LOCAL_MODEL = "gemma3:4b"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

# Question types where the gold answer is actually derivable from the
# expected_path articles. The 4th type (`null_query`) is intentionally
# excluded — for null queries there is no positive evidence and the
# scoring would test abstention behavior, not reasoning quality. That
# is a separate hypothesis (see α-8 abstention work).
ANSWERABLE = ("inference_query", "comparison_query", "temporal_query")

# Evidence size guards (same as v2 — confirmed sufficient by the v2 smoke).
MAX_ART_CHARS = 7500
MAX_CTX_CHARS = 16000
NUM_CTX = 8192

_VERDICTS = ("CORRECT", "INCORRECT", "ABSTAINED")


# ─── evidence assembly ────────────────────────────────────────────────


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


_RAW_IDX: List[Tuple[str, Path]] = [
    (_norm(re.sub(r"^multihop_\d+_", "", p.stem)), p)
    for p in RAW.glob("multihop_*.txt")
] if RAW.exists() else []


def _article_for_title(title: str) -> Optional[Path]:
    """Find the raw article file whose filename slug matches the expected
    title (longest prefix match — disambiguates titles that share a
    prefix)."""
    nt = _norm(title)
    best: Optional[Path] = None
    best_len = 0
    for nslug, path in _RAW_IDX:
        if nt.startswith(nslug) and len(nslug) > best_len:
            best, best_len = path, len(nslug)
    return best


def build_evidence(query: dict) -> Tuple[str, int, int]:
    """Build the evidence block fed to BOTH models. Returns (text, n_nodes,
    n_resolved). When n_resolved < n_nodes some expected_path articles
    aren't on disk — the run still proceeds with what's available; the
    judge marks accordingly."""
    nodes = (query.get("expected_path") or {}).get("nodes") or []
    parts: List[str] = []
    resolved = 0
    for title in nodes:
        path = _article_for_title(title)
        if not path:
            continue
        resolved += 1
        body = path.read_text(encoding="utf-8", errors="ignore").strip()
        parts.append(f"[Article] {title}\n{body[:MAX_ART_CHARS]}")
    return "\n\n".join(parts)[:MAX_CTX_CHARS], len(nodes), resolved


def _answer_prompt(context: str, question: str) -> str:
    return (
        "Answer the question using ONLY the provided context. Be specific and "
        "complete. If the answer truly is not in the context, reply exactly "
        "\"I don't know\".\n\n"
        f"Context:\n{context}\n\nQuestion: {question}\n\nAnswer:"
    )


# ─── model calls ──────────────────────────────────────────────────────


def call_local(prompt: str, *, model: str, timeout: int = 180,
               local_backend: str = "ollama") -> str:
    """Direct local call. The matrix runner / pipeline isn't booted
    for measurement, so we hit the serving layer directly.

    Two backends supported (CLI flag ``--local-backend``):

      * ``ollama`` (default) — http://127.0.0.1:11434/api/generate.
        Same byte-identical shape v2 used; num_ctx explicit so the
        v1 silent truncation bug stays fixed.
      * ``diffusiongemma_local`` — v0.6.1 v18 (2026-06-16) spike.
        Goes through the registered backend
        (``core.reasoning.backends.diffusiongemma_local``) which speaks
        OpenAI-compatible /v1/chat/completions against vLLM or
        llama.cpp-server. Lets the operator paired-compare gemma4:e4b
        vs DiffusionGemma on the same fixture without rewriting the
        harness. ``model`` becomes the model tag the serving stack
        announced (e.g. ``google/diffusiongemma-26b-a4b-it``).

    v0.6.1 v18.4 (2026-06-16) — thinking-mode contract. The v18.3
    Path A baseline launched with gemma4:e4b and produced 27/27 empty
    LOCAL responses, then auto-classified them as ABSTAINED. Root
    cause was the d3_e4b_floor_mechanism_thinking_trace memory's
    finding (PR #602): the e4b model burns ~85% of num_predict on
    hidden thinking tokens that ``/api/generate`` strips from
    ``response``. cap=400 left zero room for user-facing answer.

    Fix: when the model is thinking-capable AND the operator's
    JAMES_GEMMA4_E4B_THINK_OFF=1 flag is set (default in `.env`
    since PR #609), forward ``think: false`` to the Ollama request.
    Honor the same contract production code uses — the harness was
    the last call site bypassing it.
    """
    if local_backend == "diffusiongemma_local":
        from core.reasoning.backends.diffusiongemma_local import (
            DiffusionGemmaLocalBackend,
        )
        # URL from env (JAMES_DIFFUSIONGEMMA_URL) is read by the
        # backend's constructor. Tests stay hermetic; measurement runs
        # honor whatever the operator pointed the env at.
        backend = DiffusionGemmaLocalBackend(model=model or None)
        result = backend.complete(
            prompt,
            max_tokens=400,
            timeout=float(timeout),
            temperature=0.0,
        )
        if result.error and not result.text:
            raise RuntimeError(f"diffusiongemma backend error: {result.error}")
        return (result.text or "").strip()

    # default: ollama. v18.4: thinking-aware body.
    body: Dict[str, Any] = {
        "model": model, "prompt": prompt, "stream": False,
        "options": {
            "num_predict": 400, "temperature": 0.0, "num_ctx": NUM_CTX,
        },
    }
    # Honor production's think_policy contract. is_thinking_capable
    # gates on the model family; _flag_active reads
    # JAMES_GEMMA4_E4B_THINK_OFF. When BOTH are true, ``think: false``
    # joins the Ollama body — matching the gemma_client.py path
    # production calls already take.
    try:
        from core.reasoning.think_policy import (
            is_thinking_capable, _flag_active,
        )
        if is_thinking_capable(model) and _flag_active():
            body["think"] = False
    except ImportError:
        # think_policy module gone (extreme refactor) — fall through
        # to the legacy direct call. Lock-test catches the loss.
        pass

    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    r = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    return (r.get("response") or "").strip()


def call_cloud_via_abstraction(prompt: str, *, timeout: int = 180) -> str:
    """Cloud call via `core.abstraction.run_cloud_egress` against the
    `ClaudeCodeCliBackend`. The fixture's gold-evidence has no PII so
    `entities=[]` makes the abstraction a no-op — but the full call
    chain (build_map → mask_text → backend.complete → unmask_text →
    emit_egress_event) is exercised end-to-end.

    Returns the raw text answer (errors propagate up so the per-run row
    records `[cloud error: ...]` in the caller's catch).
    """
    # Local imports — avoid loading the core stack at module import time
    # so `--help` / linting doesn't require the full env.
    from core.abstraction import default_decider, run_cloud_egress
    from core.reasoning.backends.claude_code_cli import ClaudeCodeCliBackend

    backend = ClaudeCodeCliBackend()
    result, flagged = run_cloud_egress(
        backend=backend,
        prompt=prompt,
        entities=[],         # gold evidence has no sensitive entities
        decider=default_decider(),
        stage="synth",
        timeout=float(timeout),
    )
    if result.error and not result.text:
        raise RuntimeError(f"cloud backend error: {result.error}")
    if flagged:
        # MUST surface per §5.7.13 caller obligation #3. For measurement
        # context: a flagged token in the reply means Claude invented a
        # placeholder shape — for gold-evidence fixtures with no real
        # masking this is vanishingly rare, but we don't strip it.
        print(f"  [flagged: {flagged}]", end="", flush=True)
    return result.text.strip()


# ─── judge ────────────────────────────────────────────────────────────


def judge(
    question: str, evidence: str, ans_a: str, ans_b: str,
    *, timeout: int = 180,
) -> Tuple[str, str]:
    """Blinded A/B judge — same shape as v2. Order is randomized per
    query (deterministic by query id) before this is called, so the
    judge has no positional cue."""
    from core.reasoning.backends.claude_code_cli import ClaudeCodeCliBackend

    prompt = (
        "You are grading two candidate answers to a question, using ONLY the "
        "evidence below as ground truth. Do not use outside knowledge.\n\n"
        f"Question: {question}\n\nEvidence:\n{evidence}\n\n"
        f"[Answer A]\n{ans_a}\n\n[Answer B]\n{ans_b}\n\n"
        "For EACH answer, grade strictly against the evidence:\n"
        "- CORRECT: accurately answers the question and is supported by evidence\n"
        "- INCORRECT: wrong, or asserts something the evidence does not support\n"
        "- ABSTAINED: declines to answer (e.g. \"I don't know\")\n\n"
        "Reply with EXACTLY two lines, nothing else:\n"
        "A: <CORRECT|INCORRECT|ABSTAINED>\n"
        "B: <CORRECT|INCORRECT|ABSTAINED>"
    )
    # Judge goes through the backend directly (no abstraction needed —
    # the judge prompt is constructed locally + no per-query entities).
    backend = ClaudeCodeCliBackend()
    result = backend.complete(prompt, timeout=float(timeout))
    if result.error and not result.text:
        raise RuntimeError(f"judge backend error: {result.error}")

    out = (result.text or "").strip()
    va = vb = "INCORRECT"
    for line in out.splitlines():
        u = line.upper().strip()
        if u.startswith("A:"):
            va = next((v for v in _VERDICTS if v in u), va)
        elif u.startswith("B:"):
            vb = next((v for v in _VERDICTS if v in u), vb)
    return va, vb


def _is_abstain(ans: str) -> bool:
    a = (ans or "").lower()
    return any(p in a for p in (
        "i don't know", "i dont know", "cannot determine",
        "not in the context", "not provided in",
    ))


def _majority(verdicts: List[str]) -> str:
    """Per-question majority across the n paired runs. Ties broken by
    preferring CORRECT > ABSTAINED > INCORRECT (the optimistic bias is
    documented in the caveat block — operator can override by reading
    the per-run dump)."""
    if not verdicts:
        return "INCORRECT"
    counts = {v: verdicts.count(v) for v in set(verdicts)}
    top = max(counts.values())
    tied = [v for v, c in counts.items() if c == top]
    for preferred in ("CORRECT", "ABSTAINED", "INCORRECT"):
        if preferred in tied:
            return preferred
    return tied[0]


# ─── run ──────────────────────────────────────────────────────────────


def select_queries(n_per_type: int) -> List[dict]:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    by_type: Dict[str, List[dict]] = {}
    for q in fixture["queries"]:
        by_type.setdefault(q["question_type"], []).append(q)
    selected: List[dict] = []
    for t in ANSWERABLE:
        selected += by_type.get(t, [])[:n_per_type]
    return selected


def run_one_query(
    query: dict, ctx: str, *,
    local_model: str, run_idx: int, timeout: int,
    local_backend: str = "ollama",
) -> Dict[str, Any]:
    """One paired (local + cloud + judge) trial. Returns a row dict."""
    prompt = _answer_prompt(ctx, query["text"])
    t0 = time.time()

    try:
        la = call_local(
            prompt, model=local_model, timeout=timeout,
            local_backend=local_backend,
        )
        la_err = ""
    except Exception as e:  # noqa: BLE001
        la, la_err = "", f"{type(e).__name__}: {e}"

    try:
        ca = call_cloud_via_abstraction(prompt, timeout=timeout)
        ca_err = ""
    except Exception as e:  # noqa: BLE001
        ca, ca_err = "", f"{type(e).__name__}: {e}"

    # Blind A/B order per (query, run) — deterministic from id+run so
    # operator can re-trace which model got which slot.
    a_is_local = random.Random(f"{query['id']}:{run_idx}").random() < 0.5
    ans_a, ans_b = (la, ca) if a_is_local else (ca, la)

    if not la_err and not ca_err:
        try:
            va, vb = judge(query["text"], ctx, ans_a, ans_b, timeout=timeout)
            j_err = ""
        except Exception as e:  # noqa: BLE001
            va = vb = "INCORRECT"
            j_err = f"{type(e).__name__}: {e}"
    else:
        # Skip judge when either side errored — verdict is INCORRECT for
        # the failed side, judge for the other would be one-sided
        va = vb = "INCORRECT"
        j_err = "skipped: candidate error"
    local_v, cloud_v = (va, vb) if a_is_local else (vb, va)

    return {
        "id": query["id"], "type": query["question_type"], "run": run_idx,
        "hops": len((query.get("expected_path") or {}).get("nodes") or []),
        "a_is_local": a_is_local,
        "local_verdict": local_v, "cloud_verdict": cloud_v,
        "local_abstain": _is_abstain(la), "cloud_abstain": _is_abstain(ca),
        "local_answer": la, "cloud_answer": ca,
        "local_error": la_err, "cloud_error": ca_err,
        "judge_error": j_err,
        "elapsed_sec": round(time.time() - t0, 2),
    }


def aggregate(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Per-question majority + n-run variance summary."""
    by_q: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        by_q.setdefault(r["id"], []).append(r)

    per_q: List[Dict[str, Any]] = []
    for qid, qrows in by_q.items():
        local_majority = _majority([r["local_verdict"] for r in qrows])
        cloud_majority = _majority([r["cloud_verdict"] for r in qrows])
        per_q.append({
            "id": qid,
            "type": qrows[0]["type"],
            "hops": qrows[0]["hops"],
            "n_runs": len(qrows),
            "local_majority": local_majority,
            "cloud_majority": cloud_majority,
            "local_verdicts": [r["local_verdict"] for r in qrows],
            "cloud_verdicts": [r["cloud_verdict"] for r in qrows],
            "local_stable": len(set(r["local_verdict"] for r in qrows)) == 1,
            "cloud_stable": len(set(r["cloud_verdict"] for r in qrows)) == 1,
            "elapsed_sec_mean": round(
                statistics.mean(r["elapsed_sec"] for r in qrows), 2
            ),
        })

    n_q = len(per_q)
    if n_q == 0:
        return {"per_question": [], "summary": {}}

    def rate(field: str, value: str) -> float:
        return sum(1 for q in per_q if q[field] == value) / n_q

    # n_runs_per_question: max(run_idx) + 1, since run_idx is 0-based.
    # Old form `rows[0].get("run", 0) and max(...) + 1` short-circuited
    # to 0 whenever run_idx=0 (every --n-runs=1 invocation), printing
    # `n_runs/q=0` in the summary header. Caught by S4 smoke 2026-06-03.
    summary = {
        "n_questions": n_q,
        "n_runs_per_question": max(r["run"] for r in rows) + 1,
        "local_correct_rate": round(rate("local_majority", "CORRECT"), 3),
        "cloud_correct_rate": round(rate("cloud_majority", "CORRECT"), 3),
        "local_abstain_rate": round(rate("local_majority", "ABSTAINED"), 3),
        "cloud_abstain_rate": round(rate("cloud_majority", "ABSTAINED"), 3),
        "delta_correct_cloud_minus_local": round(
            rate("cloud_majority", "CORRECT") - rate("local_majority", "CORRECT"),
            3,
        ),
        "local_stable_rate": round(
            sum(1 for q in per_q if q["local_stable"]) / n_q, 3
        ),
        "cloud_stable_rate": round(
            sum(1 for q in per_q if q["cloud_stable"]) / n_q, 3
        ),
    }

    by_type: Dict[str, Dict[str, int]] = {}
    for q in per_q:
        t = q["type"]
        d = by_type.setdefault(t, {"n": 0, "local_correct": 0, "cloud_correct": 0})
        d["n"] += 1
        if q["local_majority"] == "CORRECT":
            d["local_correct"] += 1
        if q["cloud_majority"] == "CORRECT":
            d["cloud_correct"] += 1
    summary["by_type"] = by_type

    return {"per_question": per_q, "summary": summary}


CAVEAT_BLOCK = {
    "judge_self_preference": (
        "judge is Claude; one candidate is Claude — self-preference is possible. "
        "Mitigated by blinding A/B + evidence-grounded grading + per-question raw "
        "dump. Treat the auto-score as a SIGNAL; confirm against raw answers."
    ),
    "gold_evidence_not_pipeline": (
        "Reasoning-isolated design: both models get the same full gold evidence. "
        "Does NOT measure the full retrieval pipeline. A production Pareto claim "
        "needs a separate full-pipeline run (with JAMES retrieval + abstention) "
        "before any operator-facing conclusion."
    ),
    "small_n": (
        "Sample is the first answerable N per question_type from MultiHop-RAG. "
        "Not representative. The verdict here is a §4.1 closure SIGNAL, not a "
        "publishable claim. n=3 paired (per feedback_n1_verdict_inflation_n3_caught) "
        "but n_questions is still small."
    ),
    "lenient_judge": (
        "ABSTAINED + INCORRECT are scored separately, but two contradictory "
        "CORRECT answers can both land CORRECT (judge grades each independently). "
        "Per α-8 closure: paired Δ near 0 + collapse to noise band on n=3 has been "
        "observed (n=1 inflation pattern)."
    ),
    "local_model_caveat": (
        "Default local-model is gemma3:4b. Does NOT equate to gemma4 e4b "
        "(production tier, has the α-cycle thinking-trace floor on multihop). "
        "Re-run with --local-model gemma4:e4b to compare against the production tier."
    ),
    "abstraction_no_op": (
        "Cloud path goes through core.abstraction.run_cloud_egress, but the gold-"
        "evidence fixture has no PII so entities=[] → mask is empty. The call "
        "path is exercised end-to-end (proves §5.7.13 module works against a real "
        "Claude backend) but the abstraction itself is a no-op for this fixture."
    ),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-per-type", type=int, default=3,
                    help="questions per question_type (default 3 → 9 total)")
    ap.add_argument("--n-runs", type=int, default=3,
                    help="paired runs per question (default 3)")
    ap.add_argument("--local-model", default=DEFAULT_LOCAL_MODEL,
                    help=f"Ollama / DiffusionGemma model tag (default {DEFAULT_LOCAL_MODEL})")
    ap.add_argument(
        "--local-backend",
        default="ollama",
        choices=["ollama", "diffusiongemma_local"],
        help=(
            "v0.6.1 v18 (2026-06-16) spike — pick which local backend "
            "drives the LOCAL side of the paired comparison. "
            "`ollama` (default) hits http://127.0.0.1:11434/api/generate. "
            "`diffusiongemma_local` hits the JAMES backend adapter "
            "(/v1/chat/completions on the URL given by "
            "JAMES_DIFFUSIONGEMMA_URL, default http://127.0.0.1:8001). "
            "Pair against the existing CLOUD (Claude) path to produce "
            "the 5-axis Quality Delta Card before promoting the spike."
        ),
    )
    ap.add_argument("--timeout", type=int, default=180,
                    help="per-call timeout in seconds")
    ap.add_argument("--output", default="",
                    help="output JSON path; auto-named when empty")
    # v0.6.1 v18.2 (2026-06-16) — measurement-validity guard.
    # Operator catch: UI / UX cycles silently rotate measurement
    # baselines (PR #962 — meta regex matched "News" / "New York"
    # substrings). Pre-flight runs the lock-test-aligned sanity
    # checks before any LLM call goes out. --skip-pre-flight is
    # recorded in the output JSON so an operator can't bypass the
    # guard invisibly.
    ap.add_argument("--skip-pre-flight", action="store_true",
                    help=(
                        "Bypass measurement-validity pre-flight checks "
                        "(fixture / regex sweep / backend registry / "
                        "abstraction smoke). The bypass IS recorded in "
                        "the output JSON so audit trail stays intact."
                    ))
    args = ap.parse_args()

    if os.environ.get("JAMES_ENABLE_CLAUDE_BACKEND") != "1":
        print("[FATAL] set JAMES_ENABLE_CLAUDE_BACKEND=1 before running — "
              "the claude_code_cli backend is opt-in (CLAUDE.md rule).",
              file=sys.stderr)
        return 2

    # v0.6.1 v18.2 — pre-flight gate.
    pre_flight_results: List[Dict[str, Any]] = []
    pre_flight_skipped = bool(args.skip_pre_flight)
    if not pre_flight_skipped:
        try:
            from scripts.research.pre_flight_check import (
                run_pre_flight, has_failures, format_results,
            )
        except ImportError:
            # Allow direct script invocation without the scripts/ prefix.
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from pre_flight_check import (    # type: ignore
                run_pre_flight, has_failures, format_results,
            )
        results = run_pre_flight()
        print("=== pre-flight check ===")
        print(format_results(results))
        # Preserve as plain dicts for the output JSON audit trail.
        pre_flight_results = [
            {"name": r.name, "status": r.status,
             "detail": r.detail, "extra": r.extra}
            for r in results
        ]
        if has_failures(results):
            print("\n[FATAL] pre-flight failed — paired run blocked. "
                  "Fix or re-launch with --skip-pre-flight (recorded).",
                  file=sys.stderr)
            return 3
        print()

    queries = select_queries(args.n_per_type)
    print(f"local={args.local_model} (num_ctx={NUM_CTX})  "
          f"cloud=claude-cli-abstraction-wired  judge=claude-blinded-AB  "
          f"queries={len(queries)}  n_runs={args.n_runs}")
    print("design=reasoning-isolated  fixture=multihop_rag\n")

    rows: List[Dict[str, Any]] = []
    for i, q in enumerate(queries, 1):
        ctx, n_nodes, n_res = build_evidence(q)
        if n_res == 0:
            print(f"[{i}/{len(queries)}] id={q['id']} SKIPPED "
                  f"(no resolved articles for {n_nodes} expected)")
            continue
        print(f"[{i}/{len(queries)}] id={q['id']} {q['question_type']} "
              f"hops={n_nodes}(res {n_res})")
        for run_idx in range(args.n_runs):
            print(f"  run {run_idx+1}/{args.n_runs} … ", end="", flush=True)
            row = run_one_query(
                q, ctx, local_model=args.local_model,
                run_idx=run_idx, timeout=args.timeout,
                local_backend=args.local_backend,
            )
            rows.append(row)
            print(f"local={row['local_verdict'][:4]} "
                  f"cloud={row['cloud_verdict'][:4]} "
                  f"({row['elapsed_sec']}s)")

    agg = aggregate(rows)

    print(f"\n{'='*60}")
    s = agg["summary"]
    print(f"n_questions={s.get('n_questions')}  "
          f"n_runs/q={s.get('n_runs_per_question')}")
    print(f"LOCAL  correct={s.get('local_correct_rate'):.2f}  "
          f"abstain={s.get('local_abstain_rate'):.2f}  "
          f"stable_across_runs={s.get('local_stable_rate'):.2f}")
    print(f"CLOUD  correct={s.get('cloud_correct_rate'):.2f}  "
          f"abstain={s.get('cloud_abstain_rate'):.2f}  "
          f"stable_across_runs={s.get('cloud_stable_rate'):.2f}")
    print(f"Δ (cloud − local) on correct rate = "
          f"{s.get('delta_correct_cloud_minus_local'):+.2f}")

    print("\nby question_type (majority verdict):")
    for t, d in (s.get("by_type") or {}).items():
        print(f"  {t:18s} local={d['local_correct']}/{d['n']}  "
              f"cloud={d['cloud_correct']}/{d['n']}")

    print(f"\n{'='*60}")
    print("CAVEAT — required reading before citing:")
    for k, v in CAVEAT_BLOCK.items():
        print(f"  • [{k}]\n      {v}")
    print("=" * 60)

    ts = time.strftime("%Y%m%dT%H%M%S")
    out_path = (Path(args.output) if args.output
                else ROOT / "reports" / "research-runs"
                / f"alpha-8-local-vs-cloud-paired-{ts}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "design": "reasoning-isolated; both models same full gold evidence",
        "local_model": args.local_model,
        "local_backend": args.local_backend,
        # v0.6.1 v18.2 — measurement-validity audit trail.
        "pre_flight": {
            "skipped": pre_flight_skipped,
            "results": pre_flight_results,
        },
        "num_ctx": NUM_CTX,
        "cloud_backend": "claude_code_cli (via core.abstraction.run_cloud_egress)",
        "judge": "claude-cli, blinded A/B per (query, run)",
        "n_per_type": args.n_per_type,
        "n_runs": args.n_runs,
        "caveat": CAVEAT_BLOCK,
        "rows": rows,
        "aggregate": agg,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nsaved → {out_path.relative_to(ROOT) if out_path.is_relative_to(ROOT) else out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
