"""Direction α ① — local vs cloud reasoning measurement (v2, reasoning-isolated).

Answers the §4.1 closure question: on MultiHop-RAG hard cases, does a strong
cloud model reason better than the local model, and which pre-reasoning
signals (question_type, hop count) predict it?

v2 fixes the v1 confounds found in the smoke run:
  - EVIDENCE SUFFICIENCY: Ollama default num_ctx=2048 silently truncated the
    6-7.5k-char gold articles. v2 sets num_ctx=8192 and feeds full articles.
  - METRIC: the fixture's gold_signals are fragments ('Yes','really','2021')
    for comparison/temporal — keyword graded is invalid here (same artifact
    family as the α-cycle oracle). v2 scores with an LLM-judge (Claude) that
    marks each answer CORRECT / INCORRECT / ABSTAINED against the FULL gold
    evidence, with answers BLINDED (A/B, order randomized per query) to blunt
    self-preference. Raw answers are dumped for human verification.

CAVEAT: the judge is Claude and one candidate is Claude — self-preference is
possible. Mitigated by blinding + evidence-grounded grading + raw dump; treat
the auto-score as a SIGNAL, confirm against the printed answers.

Design = REASONING-ISOLATED: both models get the SAME full gold evidence, so
we measure reasoning, not retrieval. Cloud = Max-plan `claude -p` (free
research stand-in). Local = Ollama. A full-retrieval-pipeline version is a
follow-up.

Run:  python scripts/research/local_vs_cloud_multihop.py [--n-per-type 2]
"""
from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

WS = ROOT / "workspaces" / "hotpot_eval"
FIXTURE = WS / "eval" / "multihop_rag_queries.json"
RAW = WS / "raw"
LOCAL_MODEL = "gemma3:4b"
OLLAMA = "http://127.0.0.1:11434/api/generate"
ANSWERABLE = ("inference_query", "comparison_query", "temporal_query")
MAX_ART_CHARS = 7500
MAX_CTX_CHARS = 16000
NUM_CTX = 8192


# ─── evidence: map expected_path titles → raw article bodies ──────────

def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


_RAW_IDX = [(_norm(re.sub(r"^multihop_\d+_", "", p.stem)), p)
            for p in RAW.glob("multihop_*.txt")]


def _article_for_title(title: str):
    nt = _norm(title)
    best, best_len = None, 0
    for nslug, path in _RAW_IDX:
        if nt.startswith(nslug) and len(nslug) > best_len:
            best, best_len = path, len(nslug)
    return best


def build_evidence(query: dict):
    nodes = (query.get("expected_path") or {}).get("nodes") or []
    parts, resolved = [], 0
    for title in nodes:
        path = _article_for_title(title)
        if not path:
            continue
        resolved += 1
        body = path.read_text(encoding="utf-8", errors="ignore").strip()
        parts.append(f"[Article] {title}\n{body[:MAX_ART_CHARS]}")
    return "\n\n".join(parts)[:MAX_CTX_CHARS], len(nodes), resolved


# ─── model calls ──────────────────────────────────────────────────────

def _answer_prompt(context: str, question: str) -> str:
    return (
        "Answer the question using ONLY the provided context. Be specific and "
        "complete. If the answer truly is not in the context, reply exactly "
        "\"I don't know\".\n\n"
        f"Context:\n{context}\n\nQuestion: {question}\n\nAnswer:"
    )


def call_local(prompt: str, timeout: int = 180) -> str:
    req = urllib.request.Request(
        OLLAMA,
        data=json.dumps({
            "model": LOCAL_MODEL, "prompt": prompt, "stream": False,
            "options": {"num_predict": 400, "temperature": 0.0, "num_ctx": NUM_CTX},
        }).encode(),
        headers={"Content-Type": "application/json"},
    )
    r = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    return (r.get("response") or "").strip()


def call_cloud(prompt: str, timeout: int = 180) -> str:
    exe = shutil.which("claude")
    proc = subprocess.run(
        [exe, "-p"], input=prompt, capture_output=True, text=True,
        timeout=timeout, encoding="utf-8", cwd=tempfile.gettempdir(),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude exit {proc.returncode}: {proc.stderr[:200]}")
    return (proc.stdout or "").strip()


_VERDICTS = ("CORRECT", "INCORRECT", "ABSTAINED")


def judge(question: str, evidence: str, ans_a: str, ans_b: str) -> tuple[str, str]:
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
    out = call_cloud(prompt)
    va = vb = "INCORRECT"
    for line in out.splitlines():
        u = line.upper()
        if u.strip().startswith("A:"):
            va = next((v for v in _VERDICTS if v in u), va)
        elif u.strip().startswith("B:"):
            vb = next((v for v in _VERDICTS if v in u), vb)
    return va, vb


def _is_abstain(ans: str) -> bool:
    a = ans.lower()
    return any(p in a for p in ("i don't know", "i dont know", "cannot determine",
                                "not in the context", "not provided in"))


# ─── run ──────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-per-type", type=int, default=2)
    args = ap.parse_args()

    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    by_type: dict = {}
    for q in fixture["queries"]:
        by_type.setdefault(q["question_type"], []).append(q)
    selected = []
    for t in ANSWERABLE:
        selected += by_type.get(t, [])[: args.n_per_type]

    print(f"local={LOCAL_MODEL} (num_ctx={NUM_CTX})  cloud=claude(Max)  "
          f"judge=claude(blinded)  queries={len(selected)}\n")

    rows = []
    for i, q in enumerate(selected, 1):
        ctx, n_nodes, n_res = build_evidence(q)
        prompt = _answer_prompt(ctx, q["text"])
        print(f"[{i}/{len(selected)}] id={q['id']} {q['question_type']} "
              f"hops={n_nodes}(res {n_res}) …", end="", flush=True)
        t0 = time.time()
        try:
            la = call_local(prompt)
        except Exception as e:  # noqa: BLE001
            la = f"[local error: {e}]"
        try:
            ca = call_cloud(prompt)
        except Exception as e:  # noqa: BLE001
            ca = f"[cloud error: {e}]"

        # blind A/B order per query (deterministic by id)
        a_is_local = random.Random(q["id"]).random() < 0.5
        ans_a, ans_b = (la, ca) if a_is_local else (ca, la)
        try:
            va, vb = judge(q["text"], ctx, ans_a, ans_b)
        except Exception as e:  # noqa: BLE001
            va = vb = f"[judge error: {e}]"
        local_verdict, cloud_verdict = (va, vb) if a_is_local else (vb, va)

        rows.append({
            "id": q["id"], "type": q["question_type"], "hops": n_nodes,
            "resolved": n_res,
            "local_verdict": local_verdict, "cloud_verdict": cloud_verdict,
            "local_abstain": _is_abstain(la), "cloud_abstain": _is_abstain(ca),
            "local_answer": la, "cloud_answer": ca,
        })
        print(f" local={local_verdict[:4]} cloud={cloud_verdict[:4]}  "
              f"({time.time()-t0:.0f}s)")

    # ── summary ──
    n = len(rows)

    def rate(key, val):
        return sum(1 for r in rows if r[key] == val) / n

    print(f"\n{'='*60}")
    print(f"{'':18s} CORRECT  INCORRECT  ABSTAINED")
    for who in ("local", "cloud"):
        k = f"{who}_verdict"
        c = sum(1 for r in rows if r[k] == "CORRECT")
        i_ = sum(1 for r in rows if r[k] == "INCORRECT")
        a = sum(1 for r in rows if r[k] == "ABSTAINED")
        print(f"{who:18s} {c:^7} {i_:^10} {a:^9}  (n={n})")
    print(f"\nCLOUD correct − LOCAL correct = "
          f"{rate('cloud_verdict','CORRECT')-rate('local_verdict','CORRECT'):+.2f}")

    print("\nby question_type:")
    for t in ANSWERABLE:
        tr = [r for r in rows if r["type"] == t]
        if not tr:
            continue
        lc = sum(1 for r in tr if r["local_verdict"] == "CORRECT")
        cc = sum(1 for r in tr if r["cloud_verdict"] == "CORRECT")
        print(f"  {t:18s} local_correct={lc}/{len(tr)} cloud_correct={cc}/{len(tr)}")

    print("\nby hop count (difficulty signal §4.1):")
    for h in sorted({r["hops"] for r in rows}):
        hr = [r for r in rows if r["hops"] == h]
        lc = sum(1 for r in hr if r["local_verdict"] == "CORRECT")
        cc = sum(1 for r in hr if r["cloud_verdict"] == "CORRECT")
        print(f"  hops={h}: local_correct={lc}/{len(hr)} cloud_correct={cc}/{len(hr)}")
    print("=" * 60)

    print("\n── RAW ANSWERS (human verification) ──")
    for r in rows:
        print(f"\nid={r['id']} {r['type']} | local={r['local_verdict']} "
              f"cloud={r['cloud_verdict']}")
        print(f"  LOCAL: {r['local_answer'][:200].replace(chr(10),' ')}")
        print(f"  CLOUD: {r['cloud_answer'][:200].replace(chr(10),' ')}")

    ts = time.strftime("%Y%m%dT%H%M%S")
    out = ROOT / "reports" / "research-runs" / f"local-vs-cloud-multihop-v2-{ts}.json"
    out.write_text(json.dumps({
        "local_model": LOCAL_MODEL, "num_ctx": NUM_CTX,
        "cloud": "claude-max-headless", "judge": "claude-blinded-AB",
        "design": "reasoning-isolated (full gold evidence, LLM-judge)",
        "caveat": "judge is Claude; self-preference possible — confirm vs raw answers",
        "rows": rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nsaved → {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
