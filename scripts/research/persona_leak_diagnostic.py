"""Phase A persona leak diagnostic — dump the final system_prompt
that engine_memory.build_memory_context constructs for a terse-mode
English MultiHop-RAG query, without invoking the LLM.

Goal: identify which path(s) inject persona-shaped text into the
final system_prompt under response_style="terse" on the
production-minimum (advanced-OFF) path. The cycle-beta entry doc
predicts persona injection from `MemoryStore.get_system_prompt()`
("당신의 이름은 자메스입니다.") and the language directive
("Always respond in English...") survive even when
`inject_character_directives=False` collapses the 16-trait L1 path.

Usage (operator):
  JAMES_WORKSPACE=./workspaces/hotpot_eval \
  JAMES_RESPONSE_STYLE=terse \
  python scripts/research/persona_leak_diagnostic.py

Output: a structured report on stdout listing
  (1) DB persona dict
  (2) MemoryStore.get_system_prompt() raw return
  (3) CharacterProfile.get_prompt_modifiers() raw (info only —
      blocked by inject_character_directives=False in terse mode)
  (4) build_memory_context() final system_prompt for 3 sample
      English MultiHop-RAG queries
  (5) per-component leak attribution: which lines came from which
      injection path
"""
from __future__ import annotations

import io
import json
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)


SEPARATOR = "─" * 72


def banner(title: str) -> None:
    print()
    print(SEPARATOR)
    print(f"  {title}")
    print(SEPARATOR)


def section(title: str) -> None:
    print()
    print(f"── {title} " + "─" * (68 - len(title)))


class _MinimalEngineStub:
    """Smallest stub satisfying engine_memory.build_memory_context's
    `engine._log(category, exception, user_role)` contract.
    Captures errors instead of swallowing them silently so the
    diagnostic surfaces missing dependencies."""
    def __init__(self) -> None:
        self.errors: list[tuple[str, str]] = []

    def _log(self, category: str, exc: Exception, user_role: str = "") -> None:
        self.errors.append((category, f"{type(exc).__name__}: {exc}"))


def diagnose_db_persona() -> None:
    banner("(1) DB persona dict + raw get_system_prompt()")
    try:
        from core.memory import MemoryStore
        store = MemoryStore()
        persona = store.get_persona()
        sys_prompt_raw = store.get_system_prompt()

        section("get_persona() rows (sqlite persona table)")
        for k, v in persona.items():
            print(f"  {k:12s} = {v!r}")

        section("get_system_prompt() raw return")
        print(f"  [{len(sys_prompt_raw)} chars]")
        print(f"  {sys_prompt_raw!r}")
    except Exception as e:
        print(f"  [ERROR] {type(e).__name__}: {e}")


def diagnose_character_profile() -> None:
    banner("(2) CharacterProfile.get_prompt_modifiers() — terse-blocked")
    try:
        from core.character_profile import CharacterProfile
        cp = CharacterProfile()
        modifier = cp.get_prompt_modifiers()
        section("raw modifier (would be appended under NATURAL)")
        print(f"  [{len(modifier)} chars]")
        print(f"  {modifier!r}")
    except Exception as e:
        print(f"  [ERROR] {type(e).__name__}: {e}")


def diagnose_response_style() -> None:
    banner("(3) response_style.resolve_style() resolved preset (terse)")
    try:
        from core.response_style import resolve_style
        style = resolve_style("terse")
        section("preset fields")
        print(f"  name                        = {style.name!r}")
        print(f"  max_tokens                  = {style.max_tokens}")
        print(f"  force_two_sections          = {style.force_two_sections}")
        print(f"  inject_character_directives = {style.inject_character_directives}")
        print(f"  inject_sources_header       = {style.inject_sources_header}")
    except Exception as e:
        print(f"  [ERROR] {type(e).__name__}: {e}")


def diagnose_build_memory_context(queries: list[str]) -> None:
    banner("(4) build_memory_context() final system_prompt — terse + EN")
    try:
        from core.reasoning.engine_memory import build_memory_context
    except Exception as e:
        print(f"  [ERROR] import: {type(e).__name__}: {e}")
        return

    engine = _MinimalEngineStub()

    for idx, q in enumerate(queries, 1):
        section(f"query {idx}: {q[:60]!r}")
        kwargs: dict = {"session_id": f"persona-diag-q{idx}"}
        try:
            memory_context, system_prompt, hist_ctx = build_memory_context(
                engine,
                safe_query=q,
                user_role="admin",
                kwargs=kwargs,
                response_style="terse",
            )
        except Exception as e:
            print(f"  [ERROR] build_memory_context: {type(e).__name__}: {e}")
            continue

        print(f"  hist_ctx_len     = {len(hist_ctx)}")
        print(f"  memory_ctx_len   = {len(memory_context)}")
        print(f"  system_prompt    = [{len(system_prompt)} chars]")
        for line_no, line in enumerate(system_prompt.splitlines(), 1):
            print(f"    L{line_no}: {line!r}")

        # Per-line attribution heuristic. Identifies the most likely
        # injection path that produced each line. Used as the leak
        # attribution table in Phase A.5.
        section(f"query {idx}: attribution")
        attributed = attribute_lines(system_prompt.splitlines())
        for line_no, (line, src) in enumerate(attributed, 1):
            print(f"    L{line_no} [{src:18s}]: {line[:60]!r}")

    if engine.errors:
        section("captured engine._log errors (non-fatal)")
        for cat, msg in engine.errors:
            print(f"  {cat:24s} {msg}")


def attribute_lines(lines: list[str]) -> list[tuple[str, str]]:
    """Heuristic attribution — what produced each line in the final
    system_prompt? Aligned with the engine_memory.build_memory_context
    construction order so it doubles as Phase A.5 evidence."""
    out: list[tuple[str, str]] = []
    for line in lines:
        if not line.strip():
            out.append((line, "blank"))
            continue
        if "Always respond in" in line and "highest priority" in line:
            out.append((line, "lang_directive_en"))
        elif "반드시 한국어로 답변" in line and "최우선" in line:
            out.append((line, "lang_directive_ko"))
        elif "이전 추론 흔적" in line or re.match(r"-\s*\[(plan|reflect|verify)\]", line):
            out.append((line, "episodic_block"))
        elif "당신의 이름은" in line:
            out.append((line, "store.persona_name"))
        elif "[캐릭터 페르소나]" in line or "[응답 지시]" in line:
            out.append((line, "character_profile"))
        elif re.match(r"^[가-힣].{0,20}하라\.?$", line) or re.match(r"^[가-힣].{0,20}하세요\.?$", line):
            out.append((line, "char_directive_line"))
        else:
            out.append((line, "OTHER"))
    return out


def diagnose_sample_answers(json_paths: list[str]) -> None:
    banner("(5) Recent bench JSON — leak-pattern scan in answers")
    leak_patterns = [
        ("JAMES", re.compile(r"\bJAMES\b")),
        ("자메스", re.compile(r"자메스")),
        ("As JAMES", re.compile(r"\bAs JAMES\b", re.IGNORECASE)),
        ("I have analyzed", re.compile(r"\bI have analyzed\b", re.IGNORECASE)),
        ("Hello, I am", re.compile(r"\bHello,? I am\b", re.IGNORECASE)),
        ("Revised Answer", re.compile(r"##\s*Revised Answer", re.IGNORECASE)),
        ("이 답변은", re.compile(r"^이 답변은", re.MULTILINE)),
    ]
    for path in json_paths:
        abs_path = os.path.join(ROOT, path) if not os.path.isabs(path) else path
        if not os.path.exists(abs_path):
            print(f"  [SKIP] not found: {path}")
            continue
        section(os.path.basename(path))
        try:
            data = json.loads(open(abs_path, encoding="utf-8").read())
        except Exception as e:
            print(f"  [ERROR] load: {e}")
            continue
        results = data.get("results", [])
        n = len(results)
        counts: dict[str, int] = {label: 0 for label, _ in leak_patterns}
        for r in results:
            ans = r.get("answer", "")
            for label, pat in leak_patterns:
                if pat.search(ans):
                    counts[label] += 1
        print(f"  n={n} answers")
        for label, _ in leak_patterns:
            c = counts[label]
            if c:
                print(f"    {label:18s} → {c:3d}/{n} ({c/max(1,n)*100:.1f}%)")
            else:
                print(f"    {label:18s} → 0")

        # Pick 3 representative answer samples (first non-empty)
        section("  → 3 answer samples")
        shown = 0
        for r in results:
            ans = r.get("answer", "")
            if not ans or ans.startswith("[ERROR]"):
                continue
            print(f"    qid={r.get('id','?')} ({r.get('question_type','?')}, "
                  f"sources={r.get('sources','?')}):")
            print(f"    {ans[:300]!r}")
            print()
            shown += 1
            if shown >= 3:
                break


SAMPLE_QUERIES = [
    "Does the article titled 'NVIDIA gears up for Q3 earnings as AI darling "
    "faces stiff competition' discuss any specific product or "
    "technology by NVIDIA?",
    "Which company is mentioned in both articles 'Trump's $100M New York "
    "Apartment Sale Reignites Debate' and 'FTX Trial: Sam Bankman-Fried "
    "Verdict Imminent'?",
    "What event involving Sam Altman is discussed across multiple articles?",
]

BENCH_JSON_CANDIDATES = [
    "reports/multihop_terse_gemma4-e4b_20260606_003028.json",
    "reports/multihop_terse_mixtral-8x7b_20260606_013018.json",
    "reports/multihop_raw_paper_gemma4-e4b_20260605_203024.json",
    "reports/multihop_raw_paper_mixtral-8x7b_20260605_200049.json",
]


def main() -> None:
    print("Phase A persona leak diagnostic")
    print(f"  cwd                  = {os.getcwd()}")
    print(f"  JAMES_WORKSPACE      = {os.environ.get('JAMES_WORKSPACE', '<unset>')!r}")
    print(f"  JAMES_RESPONSE_STYLE = {os.environ.get('JAMES_RESPONSE_STYLE', '<unset>')!r}")

    diagnose_db_persona()
    diagnose_character_profile()
    diagnose_response_style()
    diagnose_build_memory_context(SAMPLE_QUERIES)
    diagnose_sample_answers(BENCH_JSON_CANDIDATES)


if __name__ == "__main__":
    main()
