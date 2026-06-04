"""Live proof: response_style override now collapses all 3 forcing
layers end-to-end (2026-06-04 platform-defect fix).

Runs the SAME query under default (NATURAL) and "terse" and prints
both answers + lengths. Terse should be markedly shorter, with no
"[관련 자료 목록]"/"Source files:" header and no character-persona
scaffolding ("보안 위험성", "다음 작업", report ## sections).
"""
from __future__ import annotations
import os, sys, io
# Force UTF-8 stdout so Windows cp949 console doesn't crash on ⚠ etc.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.reasoning.engine import ReasoningEngine

# Neutral retrieval query — no self_evolve/coding/wiki/meta trigger words.
Q = "재순위화(reranking)는 검색 결과 품질에 어떤 역할을 하는가?"
MODEL = os.environ.get("PROOF_MODEL", "qwen2.5:7b")


def run(style: str) -> str:
    eng = ReasoningEngine()
    out = eng.query(Q, user_role="admin", response_style=style,
                    selected_model=MODEL, session_id=f"proof-{style or 'def'}",
                    mode_override="retrieval")
    if isinstance(out, dict):
        return out.get("answer") or out.get("response") or str(out)
    return str(out)


def report(label: str, ans: str) -> None:
    print(f"\n===== {label} (len={len(ans)}) =====")
    print(ans[:1200])
    flags = {
        "관련자료헤더(L3)": ("[관련 자료" in ans) or ("Source files:" in ans) or ("관련 자료:" in ans),
        "보고서섹션(##)": "##" in ans,
        "다음작업(L2)": ("다음 작업" in ans) or ("Next actions" in ans),
        "ANSWER:라인": "ANSWER:" in ans,
    }
    print("  flags:", flags)


if __name__ == "__main__":
    print(f"model={MODEL}")
    nat = run("")          # default → NATURAL
    report("DEFAULT/NATURAL", nat)
    ter = run("terse")     # override → TERSE
    report("TERSE override", ter)
    print(f"\n>>> length ratio terse/natural = {len(ter)/max(1,len(nat)):.2f}")
