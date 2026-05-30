"""V3'.e — is D1's 7-tier budget gradient workload, or gemma4:e4b thinking?

INTERNAL-UPGRADE experiment (not a joint-piece artifact). D1's headline
"7-tier monotonic natural-stop gradient" (62 -> 1681 tokens, 27x range) was
measured on `gemma4:e4b` ONLY. §16 showed that ~85% of e4b's *synthesis*
token budget is a hidden thinking trace, not output. This probe asks the
operational question that follows:

    For each of the 7 tiers D1's budget signal routes on, how much of
    gemma4:e4b's per-tier budget is the thinking trace vs visible output?

Why JAMES cares (internal upgrade, not publication):
  - D1 `core/reasoning/budget.py` routes per-stage caps off this gradient.
  - D5 / LEO routing consume the same per-call budget signal.
  - A5 (planner/reflect/verify hold cap=4096) is sized to clear this budget.
  If a tier's budget is mostly thinking trace, the budget signal is routing
  on reasoning-mode cost, not task workload — which changes how A5/D4/D5
  should size and interpret it. think=false reclaims it where reasoning is
  not needed.

Method: stream gemma4:e4b on each of the 7 tier prompts (cap=4096, T=0.2),
count visible `response` tokens vs `eval_count` (the gap = hidden thinking
trace, language-independent — important since the cognitive tiers are
Korean and chars/token heuristics do not transfer). Then re-run each tier
with think=false to show the reclaimable budget.

Collaboration note: this measures JAMES's own default model on JAMES's own
D1 axis. It does not touch the Robin 26b-scale anchor or the Ali managed-
Gemini axis, and it does not restate the public 27x figure — it
*recontextualises it internally* (the number stands; the interpretation
gains a thinking-trace caveat). Internal-land only; any external framing
revision folds into the joint piece at the rendezvous.

The 7 tiers (D1 ordering): substitution / light-synthesis / heavy-synthesis
(English e-commerce) + query_rewrite / planner / reflect / verify (Korean
cognitive, prompts pinned from core/reasoning/*).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from urllib import request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[2]
RESEARCH = REPO / "scripts" / "research"
GEN_URL = "http://127.0.0.1:11434/api/generate"
CHAT_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "gemma4:e4b"
QUERY = "BlackRock 과 Vanguard 의 ETF 전략 차이를 비교해줘"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, RESEARCH / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_tiers() -> list[tuple[str, str]]:
    ems = _load("v3prime_e_mode_split")
    cx = _load("v3prime_e_mode_split_complex")
    pl = _load("v3prime_planner")
    rf = _load("v3prime_reflect")
    vf = _load("v3prime_verify")
    qr = _load("v3prime_query_rewriter")
    return [
        ("1.substitution", ems.SUBSTITUTION_PROMPT.format(context=ems.CONTEXT_FIXTURE)),
        ("2.light_synth", ems.SYNTHESIS_PROMPT.format(context=ems.CONTEXT_FIXTURE)),
        ("3.heavy_synth", cx.SYNTHESIS_PROMPT.format(context=cx.CONTEXT_FIXTURE)),
        ("4.query_rewrite", qr.REWRITE_PROMPT_KO.format(query=QUERY)),
        ("5.planner", pl.PLAN_PROMPT_KO.format(query=QUERY)),
        ("6.reflect", rf.CRITIQUE_PROMPT_KO.format(query=QUERY, draft=rf.FIXTURE_DRAFT_KO)),
        ("7.verify", vf.FACT_CHECK_PROMPT_KO.format(
            query=QUERY, answer=vf.FIXTURE_ANSWER_KO, context=vf.FIXTURE_CONTEXT_KO)),
    ]


def stream_visible(prompt: str, cap: int = 4096) -> dict:
    body = json.dumps({
        "model": MODEL, "prompt": prompt, "stream": True,
        "options": {"num_predict": cap, "temperature": 0.2},
    }).encode("utf-8")
    req = request.Request(GEN_URL, data=body, method="POST",
                          headers={"Content-Type": "application/json"})
    visible = 0
    final: dict = {}
    with request.urlopen(req, timeout=300) as resp:
        for line in resp:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("response"):
                visible += 1
            if obj.get("done"):
                final = obj
    ec = final.get("eval_count") or 0
    return {"visible": visible, "eval": ec, "hidden": ec - visible,
            "hidden_pct": (100 * (ec - visible) / ec) if ec else 0.0,
            "done": final.get("done_reason")}


def think_false_eval(prompt: str, cap: int = 4096) -> int:
    body = json.dumps({
        "model": MODEL, "prompt": prompt, "stream": False, "think": False,
        "options": {"num_predict": cap, "temperature": 0.2},
    }).encode("utf-8")
    req = request.Request(GEN_URL, data=body, method="POST",
                          headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode()).get("eval_count") or 0


def main() -> None:
    print("# gemma4:e4b 7-tier budget — thinking-trace decomposition (INTERNAL)\n")
    print("Question: is D1's 7-tier budget gradient workload, or thinking trace?\n")
    print(f"| Tier | visible tok | eval_count (think ON) | hidden | hidden % | "
          f"eval (think OFF) | reclaim |")
    print(f"|---|---|---|---|---|---|---|")
    rows = []
    for tier, prompt in build_tiers():
        on = stream_visible(prompt)
        off = think_false_eval(prompt)
        reclaim = on["eval"] - off
        rows.append((tier, on, off, reclaim))
        print(f"| {tier} | {on['visible']} | {on['eval']} | {on['hidden']} | "
              f"{on['hidden_pct']:.0f}% | {off} | -{reclaim} |")
    print(
        "\nReading:\n"
        "- `hidden %` = share of the tier's budget that is the thinking trace "
        "(consumed by num_predict, stripped from response).\n"
        "- `eval (think OFF)` = budget when reasoning is disabled — the "
        "workload-only cost.\n"
        "- High hidden% tiers: D1's budget signal there is routing on "
        "reasoning-mode cost, not task workload. think=false reclaims it where "
        "the stage does not need reasoning (A5/D4/D5 implication).\n"
    )
    visible_grad = [r[1]["visible"] for r in rows]
    off_grad = [r[2] for r in rows]
    on_grad = [r[1]["eval"] for r in rows]
    def span(g):
        g = [x for x in g if x]
        return f"{min(g)}->{max(g)} ({max(g)/max(min(g),1):.0f}x)" if g else "—"
    print(f"Gradient span — think ON (eval_count): {span(on_grad)}  "
          f"<- the public D1 '27x' figure is this column")
    print(f"Gradient span — think OFF (workload-only): {span(off_grad)}")
    print(f"Gradient span — visible output only:       {span(visible_grad)}")
    print(
        "\nIf the think-OFF / visible spans are much flatter than the think-ON "
        "span, the 27x gradient is substantially a thinking-trace gradient on "
        "e4b, not a pure workload gradient. Recontextualise internally; do NOT "
        "restate the public figure unilaterally."
    )


if __name__ == "__main__":
    main()
