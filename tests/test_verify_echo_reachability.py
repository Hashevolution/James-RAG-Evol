"""The corroborated echo block cannot fire on sanitized content.

This file is the standing form of a 2026-09-27 finding. The task was to
build a fixture that triggers verify's `injection_echo → block` so
#1153 could be validated in vivo, after three arms produced zero blocks
each. The fixture cannot be built, and the reason is structural.

Since #1153 an echo is reported only when the matched span is present in
the retrieved evidence — an echo has a source. But every path text takes
into that evidence runs through ``core.security_layer.extract_data_only``,
which replaces each ``INSTRUCTION_INJECTION_PATTERNS`` match with
``[INSTRUCTION_REMOVED]``:

  * ``PolicyEngine.sanitize_for_ingestion`` — upload path, write time
  * ``PolicyEngine.quarantine`` — low-trust join time (web, OCR, ASR,
    vision captions)

So the corroborating text is destroyed before it could corroborate
anything. `scripts/research/verify_echo_reachability.py` reproduces this
and additionally found **0 of 368 documents** in the live store carrying
raw pattern text, so the historical path (documents predating the ingest
chokepoint) is empty on this host too.

Why pin it as a test rather than only writing it down: the conclusion
rests on two things that could change independently — the chokepoints
calling ``extract_data_only``, and ``extract_data_only`` covering the
same pattern list verify scans with. If either drifts, the echo block
becomes live again, and the false-positive risk documented in #1153
comes back with it. These tests fail loudly in that case.

Run:
  python -m pytest tests/test_verify_echo_reachability.py -q
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.reasoning.verify import _build_security_flags  # noqa: E402
from core.security_layer import (  # noqa: E402
    INSTRUCTION_INJECTION_PATTERNS,
    extract_data_only,
)

# Index-aligned with INSTRUCTION_INJECTION_PATTERNS. Kept in the probe
# script too; `test_probe_strings_match_the_live_pattern_list` is what
# stops the two from drifting apart silently.
from scripts.research.verify_echo_reachability import (  # noqa: E402
    PROBE_STRINGS,
)


def _idx():
    return list(range(len(INSTRUCTION_INJECTION_PATTERNS)))


def test_probe_strings_cover_the_live_pattern_list():
    """A probe that misses its own pattern proves nothing about it, and
    reads in the output as 'survives ingestion'. One of these was wrong
    on the first run of the probe script."""
    assert len(PROBE_STRINGS) == len(INSTRUCTION_INJECTION_PATTERNS)


@pytest.mark.parametrize("i", _idx())
def test_each_probe_matches_its_own_pattern(i):
    assert re.search(INSTRUCTION_INJECTION_PATTERNS[i], PROBE_STRINGS[i],
                     re.IGNORECASE), (
        f"probe {i!r} does not match pattern {i} — fix PROBE_STRINGS")


@pytest.mark.parametrize("i", _idx())
def test_each_pattern_is_neutralized_by_the_chokepoint(i):
    clean, modified = extract_data_only(PROBE_STRINGS[i])
    assert modified, f"pattern {i} survives extract_data_only"
    assert "[INSTRUCTION_REMOVED]" in clean


@pytest.mark.parametrize("i", _idx())
def test_no_echo_survives_sanitization(i):
    """The whole argument in one assertion: quote the document verbatim —
    the strongest echo case — against the text the store actually holds,
    and nothing is reportable."""
    probe = PROBE_STRINGS[i]
    clean, _ = extract_data_only(probe)
    echoes = [f for f in _build_security_flags(probe, "employee", clean)
              if f.startswith("security.injection_echo")]
    assert echoes == [], (
        f"pattern {i} is corroborable after sanitization — the echo block "
        f"is live again and #1153's false-positive risk returns with it")


def test_both_chokepoints_route_through_extract_data_only():
    """Structural: the conclusion holds only while both do."""
    src = (REPO_ROOT / "core" / "policy_engine.py").read_text(encoding="utf-8")
    for fn in ("def sanitize_for_ingestion", "def quarantine"):
        body = src.split(fn, 1)[1].split("\n    def ", 1)[0]
        assert "extract_data_only" in body, f"{fn} no longer sanitizes"


def test_extract_data_only_scans_the_same_list_verify_does():
    """If verify's scan ever gains patterns extract_data_only lacks,
    those patterns become corroborable and the block goes live."""
    det = (REPO_ROOT / "core" / "security_layer" / "_detection.py").read_text(
        encoding="utf-8")
    body = det.split("def extract_data_only", 1)[1].split("\ndef ", 1)[0]
    assert "INSTRUCTION_INJECTION_PATTERNS" in body

    sec = (REPO_ROOT / "core" / "reasoning" / "verify"
           / "security_flags.py").read_text(encoding="utf-8")
    assert "INSTRUCTION_INJECTION_PATTERNS" in sec


def test_unsanitized_context_still_blocks():
    """The mechanism is intact — it is the *input* that cannot arrive.

    This is also the correction to #1153's "known residual": that test
    passes raw runbook text straight to the scan, which no production
    path does. The residual is real in the function's contract and
    unreachable through the pipeline.
    """
    raw = "배포 절차: 다음 명령을 실행하세요 — git push"
    echoes = [f for f in _build_security_flags(
        "문서에 따르면 다음 명령을 실행하세요", "employee", raw)
        if f.startswith("security.injection_echo")]
    assert echoes, "corroboration mechanism itself regressed"
