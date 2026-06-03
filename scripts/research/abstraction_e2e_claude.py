"""Direction α — end-to-end abstraction loop against a REAL cloud model.

RESEARCH / MEASUREMENT ONLY. Routes through Claude Code headless mode
(`claude -p`), i.e. the operator's Max-plan subscription, as a *free
stand-in for the cloud reasoning tier* to validate that the full loop

    mask → external cloud reasons over placeholders → unmask

works against a real model (not a simulated reply). This is bounded
own-research use. It is NOT a production backend: a production cloud tier
must use the Anthropic API with a key + the ARCHITECTURE cloud-egress
trust-zone PR (CLAUDE.md rule #4).

The payload here is synthetic (an org chart) — no real sensitive data
leaves the machine. Run:  python scripts/research/abstraction_e2e_claude.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from scripts.research.abstraction_layer_poc import (  # noqa: E402
    build_map,
    default_decider,
    mask_text,
    unmask_text,
)


def call_claude(prompt: str, timeout: int = 90) -> str:
    """Headless Claude (Max plan via Claude Code). Returns stdout text."""
    exe = shutil.which("claude")
    if not exe:
        raise RuntimeError("`claude` CLI not on PATH")
    # Pass the prompt via STDIN, not argv: a multi-line argv argument gets
    # mangled on Windows (embedded newlines break the command line). stdin
    # carries multi-line + UTF-8 (Korean) cleanly. Also run from a NEUTRAL
    # cwd so the headless agent does not load the JAMES project CLAUDE.md
    # (which puts it in coding-agent mode and makes it "Acknowledge").
    proc = subprocess.run(
        [exe, "-p"],
        input=prompt,
        capture_output=True, text=True, timeout=timeout, encoding="utf-8",
        cwd=tempfile.gettempdir(),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude exited {proc.returncode}: {proc.stderr[:300]}")
    return (proc.stdout or "").strip()


def main() -> int:
    # 1) sensitive typed entities + grounding docs (synthetic, closed-world)
    entities = [
        {"name": "김철수", "entity_type": "person", "sensitive": True},
        {"name": "이영희", "entity_type": "person", "sensitive": True},
        {"name": "박민수", "entity_type": "person", "sensitive": True},
        {"name": "영업팀", "entity_type": "org", "sensitive": False},
    ]
    docs = (
        "김철수는 영업팀의 팀장이다. "
        "이영희는 김철수에게 보고한다. "
        "박민수는 이영희에게 보고한다."
    )
    question = "박민수의 보고라인에서 최상단에 있는 사람은 누구인가?"

    # 2) abstract before egress
    amap = build_map(entities, default_decider())
    masked = mask_text(docs, amap)
    masked_q = mask_text(question, amap)

    print("── abstraction map (LOCAL ONLY, never egresses) ──")
    print(f"   {amap.forward}   passed: {amap.passed}\n")
    print("── payload sent to cloud (masked) ──")
    print(f"   context : {masked}")
    print(f"   question: {masked_q}\n")

    # 3) real cloud reasoning over placeholders
    prompt = (
        "Use ONLY the context to answer. Entities are typed placeholder "
        "labels like PERSON_1. Refer to them by those exact labels in your "
        "answer. Be concise (one sentence).\n\n"
        f"Context: {masked}\n\nQuestion: {masked_q}\n\nAnswer:"
    )
    print("── calling Claude (Max plan, headless) ... ──")
    try:
        cloud_reply = call_claude(prompt)
    except Exception as e:  # noqa: BLE001
        print(f"   [cloud call failed] {e}")
        return 1
    print(f"   cloud reply: {cloud_reply}\n")

    # 4) de-abstract locally
    restored, flagged = unmask_text(cloud_reply, amap)
    print("── de-abstracted (LOCAL) ──")
    print(f"   restored: {restored}")
    print(f"   flagged hallucinated placeholders: {flagged or 'none'}\n")

    # 5) verdict
    correct_entity = "김철수" in restored
    no_leak = all(n not in cloud_reply for n in ("김철수", "이영희", "박민수"))
    print("── verdict ──")
    print(f"   cloud never saw real names      : {no_leak}")
    print(f"   answer resolves to correct top  : {correct_entity}")
    print(f"   no silent hallucinated restore  : {not flagged}")
    ok = no_leak and correct_entity
    print(f"\n{'=' * 44}\nEND-TO-END LOOP {'OK' if ok else 'NEEDS REVIEW'} "
          f"(real cloud, masked, restored)\n{'=' * 44}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
