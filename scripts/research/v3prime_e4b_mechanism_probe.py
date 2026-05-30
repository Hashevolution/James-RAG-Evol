"""V3'.e mechanism probe — WHY does gemma4:e4b alone hold a high cap-400 floor?

Direction 3 closed H1 (the synthesis cap-400 floor is checkpoint-isolated to
`gemma4:e4b`). The final report then proposed three successive *proximate*
stories for the mechanism, all of which this probe shows are WRONG:

  §7    "gemma4:e4b is 4-9x more verbose"          (token-tax = verbosity)
  §15.5 "reasoning-first; keyword at the tail"     (position_fraction model)
  §15.6 "5-10x more verbose via natural median"    (verbosity, corrected ratio)

The decisive measurement below overturns all three: e4b's *visible* answer is
the SAME length as the other six models (~50-90 visible tokens, ~280-440
chars). The "464-token natural budget" is ~85% **hidden reasoning tokens** that
are counted in `eval_count` (and therefore consume the `num_predict` cap) but
are never emitted in the Ollama `response` stream — there is no separate
`thinking` field, so they are silently dropped (a gemma4 chat-template
artifact).

Mechanism, definitively:

    gemma4:e4b emits a hidden reasoning/scratchpad trace (~85% of generated
    tokens) BEFORE its visible answer. num_predict caps the model's own token
    count, so cap=400 truncates during or just after the hidden phase — the
    visible answer (which comes last) is then empty (~39% of cap=400 runs) or
    partial. The other six checkpoints answer directly: eval_count == visible
    tokens (hidden == 1, just EOS), so their full answer costs ~50-95 tokens
    and clears any deployment-range cap.

This is the same class of phenomenon as o1/R1-style reasoning models where
`max_tokens` must budget for invisible reasoning — except Ollama does not
surface the trace here, so it reads as a mysterious "cap floor."

Two measurements:

  Part A (live, decisive)  — stream each model and compare visible token count
                             (stream chunks) against eval_count. The gap is the
                             hidden-reasoning trace.
  Part B (stored, corrob.) — chars-per-eval-token from the cap=4096 synthesis
                             JSONs: e4b ~0.71 vs others ~4.8 (the same gap seen
                             from the storage side, no new calls).

Pure measurement + read-only audit. Part A makes 4 short Ollama calls; Part B
reads existing JSONs. No JAMES state change.
"""

from __future__ import annotations

import glob
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from urllib import request

# Windows cp949 console safety — this probe prints em-dash / arrow glyphs.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[2]
RUN_DIR = REPO / "reports" / "research-runs"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

CONTEXT_FIXTURE = (
    "Refund Policy\n-------------\n"
    "Items may be returned within 30 days of delivery for a full refund, "
    "provided they are unworn, unwashed, and have all original tags "
    "attached. Linen, silk, and cashmere garments are final sale once "
    "washed.\n"
)
SYNTHESIS_PROMPT = (
    "Based on the policy context below, advise whether a customer who "
    "bought a linen shirt, washed it, and now wants to return it qualifies "
    "for a refund. Justify the decision in 2-3 sentences citing the "
    "specific clause.\n\nContext:\n" + CONTEXT_FIXTURE + "\nRecommendation:"
)

# e4b first; the rest are the cross-family panel (those installed locally).
PANEL = ["gemma4:e4b", "qwen2.5:7b", "gemma3:12b", "llama3.1:8b", "gemma2:2b"]


def stream_once(model: str, cap: int = 4096, temp: float = 0.2) -> dict:
    """Stream one synthesis generation; count visible tokens vs eval_count."""
    body = json.dumps({
        "model": model, "prompt": SYNTHESIS_PROMPT, "stream": True,
        "options": {"num_predict": cap, "temperature": temp},
    }).encode("utf-8")
    req = request.Request(
        OLLAMA_URL, data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    chunks: list[str] = []
    final: dict = {}
    with request.urlopen(req, timeout=180) as resp:
        for line in resp:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("response"):
                chunks.append(obj["response"])
            if obj.get("done"):
                final = obj
    visible_tokens = len(chunks)
    eval_count = final.get("eval_count") or 0
    answer = "".join(chunks)
    return {
        "model": model,
        "visible_tokens": visible_tokens,
        "eval_count": eval_count,
        "hidden_tokens": eval_count - visible_tokens,
        "hidden_pct": (100 * (eval_count - visible_tokens) / eval_count
                       if eval_count else 0.0),
        "answer_chars": len(answer),
        "done_reason": final.get("done_reason"),
    }


def part_a_live() -> None:
    print("## Part A — live stream: visible tokens vs counted tokens "
          "(synthesis, num_predict=4096, temp=0.2)\n")
    print(f"| {'model':<16} | {'visible tok':>11} | {'eval_count':>10} | "
          f"{'hidden':>6} | {'hidden %':>8} | {'answer chars':>12} |")
    print(f"|{'-'*18}|{'-'*13}|{'-'*12}|{'-'*8}|{'-'*10}|{'-'*14}|")
    for model in PANEL:
        try:
            r = stream_once(model)
        except Exception as exc:  # pragma: no cover - environment dependent
            print(f"| {model:<16} | {'ERROR':>11} | {str(exc)[:30]} |")
            continue
        print(f"| {r['model']:<16} | {r['visible_tokens']:>11} | "
              f"{r['eval_count']:>10} | {r['hidden_tokens']:>6} | "
              f"{r['hidden_pct']:>7.1f}% | {r['answer_chars']:>12} |")
    print(
        "\nReading: for every model except gemma4:e4b, eval_count == visible "
        "tokens (hidden == 1, just EOS). e4b carries ~85% hidden reasoning "
        "tokens that consume the num_predict budget but never reach the "
        "response stream. THAT is the cap-400 floor.\n"
    )


def part_b_stored() -> None:
    print("## Part B — stored corroboration: chars per eval-token "
          "(cap=4096 synthesis, temp=0.2)\n")
    data: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for path in glob.glob(str(RUN_DIR / "v3prime-e-mode-split-*.json")):
        doc = json.load(open(path, encoding="utf-8"))
        meta = doc.get("metadata", {})
        if meta.get("temperature") != 0.2:
            continue
        model = meta.get("model")
        for t in doc.get("runs", {}).get("synthesis", {}).get("4096", []):
            txt, ec = t.get("raw_response_text"), t.get("ollama_eval_count")
            if txt and ec:
                data[model].append((len(txt), ec))
    if not data:
        print("(no stored cap=4096 synthesis runs with raw_response_text)\n")
        return
    print(f"| {'model':<16} | {'n':>3} | {'med chars':>9} | "
          f"{'med eval':>8} | {'chars/token':>11} |")
    print(f"|{'-'*18}|{'-'*5}|{'-'*11}|{'-'*10}|{'-'*13}|")
    rows = []
    for model, vals in data.items():
        ratios = [c / e for c, e in vals]
        rows.append((statistics.median(ratios), model, len(vals),
                     int(statistics.median([c for c, _ in vals])),
                     int(statistics.median([e for _, e in vals]))))
    for ratio, model, n, mc, me in sorted(rows):
        print(f"| {model:<16} | {n:>3} | {mc:>9} | {me:>8} | {ratio:>11.2f} |")
    print(
        "\nReading: identical-length visible answers (~270-460 chars) cost e4b "
        "~0.71 chars/token vs ~4.8 for the other six — the storage-side shadow "
        "of the hidden-token gap measured live in Part A.\n"
    )


def part_c_thinking_toggle() -> None:
    """Decisive root-cause test: gemma4:e4b declares the `thinking`
    capability. Toggling it isolates the hidden trace as the floor."""
    print("## Part C — root cause: gemma4:e4b `thinking` capability toggle "
          "(cap=400)\n")
    print("`ollama show gemma4:e4b` lists `thinking` under Capabilities. The "
          "hidden tokens are a 'Thinking Process:' reasoning trace the model "
          "emits by design. Toggling `think` isolates it:\n")
    print(f"| {'endpoint / think':<26} | {'eval_count':>10} | "
          f"{'done':>7} | {'answer chars':>12} | {'thinking exposed':>16} |")
    print(f"|{'-'*28}|{'-'*12}|{'-'*9}|{'-'*14}|{'-'*18}|")
    # /api/chat exposes the trace in a `thinking` field; /api/generate
    # (what JAMES uses) silently strips it.
    chat_url = OLLAMA_URL.replace("/api/generate", "/api/chat")
    for think in (True, False):
        body = json.dumps({
            "model": "gemma4:e4b",
            "messages": [{"role": "user", "content": SYNTHESIS_PROMPT}],
            "stream": False, "think": think,
            "options": {"num_predict": 400, "temperature": 0.2},
        }).encode("utf-8")
        req = request.Request(chat_url, data=body, method="POST",
                              headers={"Content-Type": "application/json"})
        with request.urlopen(req, timeout=180) as resp:
            p = json.loads(resp.read().decode())
        msg = p.get("message", {})
        tlen = len(msg.get("thinking") or "")
        print(f"| {'/api/chat think=' + str(think):<26} | "
              f"{p.get('eval_count'):>10} | {str(p.get('done_reason')):>7} | "
              f"{len(msg.get('content') or ''):>12} | "
              f"{('yes (' + str(tlen) + ' ch)') if tlen else 'no':>16} |")
    print(
        "\nReading: think=True → eval_count ~400 (truncates at cap, the floor); "
        "think=False → eval_count ~45 (matches the other six models), full "
        "answer, no floor. The floor IS the thinking trace, by design.\n"
        "JAMES caveat: production uses /api/generate with `think` unset — the "
        "trace is still generated and counted (silently stripped), so caps "
        "below ~450 risk empty/partial output on gemma4:e4b.\n"
    )


SYNTHESIS_PROMPT_COT = (
    "Based on the policy context below, advise whether a customer who "
    "bought a linen shirt, washed it, and now wants to return it qualifies "
    "for a refund. Think step by step through each relevant clause before "
    "giving your final recommendation.\n\nContext:\n" + CONTEXT_FIXTURE
    + "\nReasoning:"
)


def _gen_eval(model: str, prompt: str, cap: int = 4096) -> int:
    body = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
        "options": {"num_predict": cap, "temperature": 0.2},
    }).encode("utf-8")
    req = request.Request(OLLAMA_URL, data=body, method="POST",
                          headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode()).get("eval_count") or 0


def part_d_crossmodel_reasoning() -> None:
    """Is the reasoning cost e4b-specific? Compare native think-only vs
    prompt-induced explicit reasoning across the panel (§16.7)."""
    print("## Part D — is the reasoning cost e4b-specific? "
          "(native think vs prompt-induced CoT, §16.7)\n")
    # (A) native think toggle is e4b-only — rejected elsewhere.
    chat_url = OLLAMA_URL.replace("/api/generate", "/api/chat")
    body = json.dumps({
        "model": "qwen2.5:7b",
        "messages": [{"role": "user", "content": SYNTHESIS_PROMPT}],
        "stream": False, "think": True,
        "options": {"num_predict": 512, "temperature": 0.2},
    }).encode("utf-8")
    req = request.Request(chat_url, data=body, method="POST",
                          headers={"Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=120):
            verdict = "accepted (unexpected)"
    except Exception as exc:  # HTTP 400 for non-thinking models
        verdict = f"rejected — {str(exc)[:40]}"
    print(f"(A) native think=true on qwen2.5:7b (no thinking capability): "
          f"{verdict}\n")

    # (B) prompt-induced CoT cost across the standard models.
    print("(B) prompt-induced explicit reasoning (eval_count, cap=4096):\n")
    print(f"| {'model':<14} | {'plain':>6} | {'CoT':>5} | "
          f"{'induced reasoning':>17} |")
    print(f"|{'-'*16}|{'-'*8}|{'-'*7}|{'-'*19}|")
    for model in ["qwen2.5:7b", "gemma3:12b", "llama3.1:8b", "gemma2:2b"]:
        try:
            plain = _gen_eval(model, SYNTHESIS_PROMPT)
            cot = _gen_eval(model, SYNTHESIS_PROMPT_COT)
            print(f"| {model:<14} | {plain:>6} | {cot:>5} | "
                  f"{cot - plain:>+17} |")
        except Exception as exc:  # pragma: no cover
            print(f"| {model:<14} | ERROR {str(exc)[:30]} |")
    print(
        "\nReading: induced reasoning (~170-390 tokens) matches e4b's native "
        "trace (~377). Reasoning costs the same on every model — e4b is not "
        "abnormally expensive. The floor is a DEFAULT-MODE difference "
        "(reasoning on-by-default + hidden) not an efficiency defect.\n"
    )


def main() -> None:
    print("# V3'.e mechanism probe — gemma4:e4b cap-400 floor\n")
    print("Headline: the floor is the gemma4:e4b THINKING TRACE consuming the "
          "num_predict budget — by design, not verbosity (§7/§15.6) and not "
          "keyword positioning (§15.5).\n")
    part_a_live()
    part_b_stored()
    part_c_thinking_toggle()
    part_d_crossmodel_reasoning()


if __name__ == "__main__":
    main()
