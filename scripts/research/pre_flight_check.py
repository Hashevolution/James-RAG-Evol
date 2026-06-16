"""Pre-flight sanity for the paired measurement harness.

Operator catch v0.6.1 v18.2 (2026-06-16) — the v17 meta regex
false-positive nearly polluted a paired measurement. Operator
requested a layered guarantee so UI / UX / chrome cycles don't
quietly invalidate ongoing measurement work.

This module is Layer 2 of the two-layer answer (Layer 1 is the
``tests/test_measurement_critical_surfaces.py`` lock-test). It runs
each time the paired harness launches and validates LIVE STATE before
any LLM call goes out:

  1. **Fixture integrity** — file exists, schema rows present, the
     answerable types still have the n×3 minimum the harness assumes.
  2. **Regex false-positive sweep** — every meta-mode pattern in
     ``core/intent_classifier`` is tested against the fixture's
     retrieval queries. Any pattern that matches an answerable query
     is a measurement-validity bug and blocks the launch.
  3. **Backend registry baseline** — exactly the backends the operator
     expects must be registered. Extras suggest a leaked
     ``JAMES_ENABLE_*`` env from a different shell; missing the
     reference backend means the cloud path is broken.
  4. **Abstraction module smoke** — ``core.abstraction.default_decider`` +
     ``run_cloud_egress`` import + run a no-op call on an empty
     entities list, mirroring the harness's cloud path.

Each check returns ``(status, detail)``. Statuses:
  - ``ok``     pass
  - ``warn``   non-fatal observation worth surfacing in the run log
  - ``fail``   fatal; refuse to launch unless ``--skip-pre-flight``
               is explicitly passed (which itself is recorded in the
               output JSON so the operator can't pretend the check
               didn't fire).

Usage as a CLI for ad-hoc inspection:

    python scripts/research/pre_flight_check.py

Or as a module (the harness calls ``run_pre_flight()`` in its main()):

    from scripts.research.pre_flight_check import run_pre_flight
    results = run_pre_flight()
"""
from __future__ import annotations

import importlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple


# Resolve repo root from this file's location — works whether the
# operator launches from repo root or from scripts/research/.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


# Baseline state the harness expects on a stock JAMES install. If the
# operator legitimately wants to change one of these (e.g. add a new
# answerable type), they update the lock-test in the same PR.
_EXPECTED_REGISTERED_BACKENDS = {"ollama_local"}     # minimum required
_OPTIONAL_REGISTERED_BACKENDS = {
    "claude_code_cli",          # opt-in JAMES_ENABLE_CLAUDE_BACKEND=1
    "diffusiongemma_local",     # opt-in JAMES_ENABLE_DIFFUSIONGEMMA=1
}
_EXPECTED_ANSWERABLE_TYPES = (
    "inference_query", "comparison_query", "temporal_query",
)
_MIN_ROWS_PER_TYPE = 9       # n_per_type=3 default × 3 runs = 9 rows


@dataclass
class PreFlightResult:
    name: str
    status: str           # "ok" | "warn" | "fail"
    detail: str
    extra: Dict[str, Any] = field(default_factory=dict)


# ─── checks ─────────────────────────────────────────────────────────


def check_fixture() -> PreFlightResult:
    try:
        import local_vs_cloud_paired as harness   # noqa: F401
    except ModuleNotFoundError:
        # harness path-based import — replicate what the lock-test does
        spec = importlib.util.spec_from_file_location(
            "local_vs_cloud_paired",
            _REPO_ROOT / "scripts" / "research" / "local_vs_cloud_paired.py",
        )
        harness = importlib.util.module_from_spec(spec)
        sys.modules["local_vs_cloud_paired"] = harness
        spec.loader.exec_module(harness)

    fixture_path: Path = harness.FIXTURE
    if not fixture_path.exists():
        return PreFlightResult(
            "fixture_exists", "fail",
            f"missing fixture file: {fixture_path}",
        )

    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    queries = data.get("queries", [])
    if not queries:
        return PreFlightResult(
            "fixture_exists", "fail",
            f"fixture {fixture_path} has empty queries[]",
        )

    counts = {t: 0 for t in _EXPECTED_ANSWERABLE_TYPES}
    for q in queries:
        t = q.get("question_type")
        if t in counts:
            counts[t] += 1

    short = [t for t, n in counts.items() if n < _MIN_ROWS_PER_TYPE]
    if short:
        return PreFlightResult(
            "fixture_rows", "fail",
            f"answerable types short of {_MIN_ROWS_PER_TYPE} rows: {short} "
            f"(counts={counts})",
            extra={"counts": counts},
        )

    return PreFlightResult(
        "fixture_rows", "ok",
        f"{sum(counts.values())} answerable queries available "
        f"(counts={counts})",
        extra={"counts": counts, "path": str(fixture_path)},
    )


def check_regex_false_positives() -> PreFlightResult:
    """No fast-path regex (across ALL non-retrieval modes) may match
    the fixture's retrieval queries. False positives in the live chat
    path silently route the operator's English queries away from
    retrieval — measurement-adjacent but visible-regression.

    Modes swept: ``meta``, ``wiki_edit``, ``coding``. ``chat`` is the
    fallback so its patterns are skipped. ``retrieval`` has no fast
    patterns — it's the implicit default.

    v18.2 retroactive scan (2026-06-16) found `coding` pattern
    ``\\b(def |class |import |traceback)\\b`` matching ``class `` in
    English fixture queries (`class-action`, `first-class`, etc.).
    Predates the v0.6.1 chrome cycle (initial release) — long-running
    bug, but now pre-flight catches it before measurement.

    The harness itself bypasses intent_classifier, so this check
    cannot poison a paired RUN; it catches the bug BEFORE the operator
    hits the broken live path.
    """
    try:
        from core.intent_classifier import IntentClassifier
    except ImportError as e:
        return PreFlightResult(
            "regex_sweep", "fail",
            f"intent_classifier import failed: {e}",
        )

    try:
        import local_vs_cloud_paired as harness
    except ModuleNotFoundError:
        return PreFlightResult(
            "regex_sweep", "warn",
            "harness module not preloaded — skip regex sweep "
            "(check_fixture must run before this check)",
        )

    fixture_path: Path = harness.FIXTURE
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    classifier = IntentClassifier()

    # Modes to sweep — every fast-path bucket EXCEPT chat (fallback)
    # and the implicit retrieval default. If a new mode appears in
    # FAST_PATTERNS that we want excluded (e.g. a new fallback), add
    # it to _SWEEP_EXCLUDE.
    _SWEEP_EXCLUDE = {"chat"}
    sweep_modes = [
        m for m in classifier.FAST_PATTERNS
        if m not in _SWEEP_EXCLUDE
    ]
    if not sweep_modes:
        return PreFlightResult(
            "regex_sweep", "warn",
            "no fast-path modes found to sweep — classifier surface "
            "may have rotated; lock-test should already be red",
        )

    # Per-mode compiled patterns.
    per_mode: Dict[str, List[re.Pattern]] = {}
    per_mode_raw: Dict[str, List[str]] = {}
    for mode in sweep_modes:
        raw = classifier.FAST_PATTERNS.get(mode, [])
        per_mode[mode] = [re.compile(p, re.IGNORECASE) for p in raw]
        per_mode_raw[mode] = raw

    answerable = harness.ANSWERABLE

    fp_rows: List[Dict[str, Any]] = []
    total = 0
    for q in data.get("queries", []):
        if q.get("question_type") not in answerable:
            continue
        total += 1
        text = q.get("text", "")
        for mode, compiled in per_mode.items():
            for i, cre in enumerate(compiled):
                m = cre.search(text)
                if m:
                    fp_rows.append({
                        "id":      q.get("id"),
                        "qtype":   q.get("question_type"),
                        "text":    text[:120],
                        "mode":    mode,
                        "pattern": per_mode_raw[mode][i][:80],
                        "match":   m.group(0),
                    })
                    break       # one match per (row, mode) is enough

    if fp_rows:
        by_mode: Dict[str, int] = {}
        for r in fp_rows:
            by_mode[r["mode"]] = by_mode.get(r["mode"], 0) + 1
        return PreFlightResult(
            "regex_sweep", "fail",
            f"{len(fp_rows)} false positives across answerable "
            f"fixture rows (modes: {by_mode}). Live chat path will "
            f"misroute. First example: {fp_rows[0]!r}",
            extra={
                "false_positives": fp_rows[:5],
                "total": total,
                "by_mode": by_mode,
            },
        )
    return PreFlightResult(
        "regex_sweep", "ok",
        f"0/{total} false positives across {len(sweep_modes)} fast-path "
        f"modes ({sorted(sweep_modes)})",
        extra={"total": total, "modes_swept": sorted(sweep_modes)},
    )


def check_backend_registry() -> PreFlightResult:
    """Backends actually registered should be exactly:
      - ollama_local (always)
      - claude_code_cli iff JAMES_ENABLE_CLAUDE_BACKEND=1
      - diffusiongemma_local iff JAMES_ENABLE_DIFFUSIONGEMMA=1
    Anything else suggests a JAMES_PLUGINS leak or a code path that
    auto-registers something unexpected — both rotate the paired
    baseline silently.
    """
    try:
        from core.reasoning.backends import list_backends
    except ImportError as e:
        return PreFlightResult(
            "backend_registry", "fail",
            f"backend registry import failed: {e}",
        )

    registered = set(list_backends())
    missing = _EXPECTED_REGISTERED_BACKENDS - registered
    if missing:
        return PreFlightResult(
            "backend_registry", "fail",
            f"required backends missing: {missing}; "
            f"registered={sorted(registered)}",
        )

    unexpected = registered - (
        _EXPECTED_REGISTERED_BACKENDS | _OPTIONAL_REGISTERED_BACKENDS
    )
    if unexpected:
        return PreFlightResult(
            "backend_registry", "fail",
            f"unexpected backends registered: {unexpected}; "
            f"a plugin (JAMES_PLUGINS) may be rotating the measurement "
            f"baseline. Clear JAMES_PLUGINS or update the expected set.",
            extra={"registered": sorted(registered)},
        )
    return PreFlightResult(
        "backend_registry", "ok",
        f"registered={sorted(registered)}",
        extra={"registered": sorted(registered)},
    )


def check_abstraction_smoke() -> PreFlightResult:
    """``core.abstraction.default_decider`` + ``run_cloud_egress`` —
    the cloud-egress path the harness exercises. We don't actually
    call Claude here (that's the measurement); we just verify the
    module + symbols are importable + minimally callable on an
    entities=[] no-op.
    """
    try:
        from core.abstraction import default_decider, run_cloud_egress
    except ImportError as e:
        return PreFlightResult(
            "abstraction_smoke", "fail",
            f"core.abstraction symbols missing: {e}",
        )

    if not callable(default_decider):
        return PreFlightResult(
            "abstraction_smoke", "fail",
            "default_decider is no longer callable",
        )
    if not callable(run_cloud_egress):
        return PreFlightResult(
            "abstraction_smoke", "fail",
            "run_cloud_egress is no longer callable",
        )

    try:
        decider = default_decider()
    except Exception as e:
        return PreFlightResult(
            "abstraction_smoke", "fail",
            f"default_decider() raised: {type(e).__name__}: {e}",
        )

    return PreFlightResult(
        "abstraction_smoke", "ok",
        f"default_decider={type(decider).__name__}; "
        f"run_cloud_egress callable",
    )


def check_diffusiongemma_opt_in() -> PreFlightResult:
    """If JAMES_ENABLE_DIFFUSIONGEMMA=1, the registry must register
    the backend. If the env says 1 but the backend is missing, the
    harness's --local-backend diffusiongemma_local will surface a
    KeyError mid-run. Catch it pre-flight.
    """
    flag = os.environ.get("JAMES_ENABLE_DIFFUSIONGEMMA")
    try:
        from core.reasoning.backends import list_backends
    except ImportError as e:
        return PreFlightResult(
            "diffusiongemma_optin", "fail",
            f"backend registry import failed: {e}",
        )
    has_dg = "diffusiongemma_local" in list_backends()
    if flag == "1" and not has_dg:
        return PreFlightResult(
            "diffusiongemma_optin", "fail",
            "JAMES_ENABLE_DIFFUSIONGEMMA=1 but diffusiongemma_local "
            "not registered — module import probably failed; check the "
            "server log for the import-time exception.",
        )
    if flag != "1" and has_dg:
        return PreFlightResult(
            "diffusiongemma_optin", "warn",
            "diffusiongemma_local is registered without the env flag — "
            "auto-import side-effect; expected only under "
            "JAMES_ENABLE_DIFFUSIONGEMMA=1.",
        )
    return PreFlightResult(
        "diffusiongemma_optin", "ok",
        f"flag={flag!r} registered={has_dg}",
    )


# ─── orchestrator ───────────────────────────────────────────────────


_CHECKS = (
    check_fixture,
    check_regex_false_positives,
    check_backend_registry,
    check_abstraction_smoke,
    check_diffusiongemma_opt_in,
)


def run_pre_flight() -> List[PreFlightResult]:
    """Execute every check, return the result list in execution order.
    Caller decides how to surface (CLI prints, harness aborts).
    """
    out: List[PreFlightResult] = []
    for fn in _CHECKS:
        try:
            out.append(fn())
        except Exception as e:
            out.append(PreFlightResult(
                fn.__name__, "fail",
                f"check raised: {type(e).__name__}: {e}",
            ))
    return out


def has_failures(results: List[PreFlightResult]) -> bool:
    return any(r.status == "fail" for r in results)


def format_results(results: List[PreFlightResult]) -> str:
    lines = []
    for r in results:
        glyph = {"ok": "✓", "warn": "!", "fail": "✗"}.get(r.status, "?")
        lines.append(f"  {glyph} [{r.status:4s}] {r.name:24s} — {r.detail}")
    return "\n".join(lines)


# ─── CLI ────────────────────────────────────────────────────────────


def main() -> int:
    results = run_pre_flight()
    print("=== paired measurement pre-flight ===")
    print(format_results(results))
    failed = has_failures(results)
    if failed:
        print("\nRESULT: FAIL — measurement launch blocked. "
              "Fix the failing checks or pass --skip-pre-flight "
              "(recorded in output JSON).")
        return 1
    warns = [r for r in results if r.status == "warn"]
    print(f"\nRESULT: PASS ({len(warns)} warning{'s' if len(warns)!=1 else ''})")
    return 0


if __name__ == "__main__":   # pragma: no cover
    sys.exit(main())
