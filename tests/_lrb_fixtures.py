"""On-demand builder for the LRB scenario fixtures.

``eval/external/_fixtures/`` is gitignored (.gitignore:82), so the LRB
scenario JSONs are never checked in. Every LRB test therefore died with
``FileNotFoundError`` in CI — 12 of the 101 standing failures as of
2026-08-19 — and had in fact *never* run there since the suite landed
(PR #1027, 2026-06-23).

The builders under ``scripts/research/build_lrb_scenario_s*.py`` are
deterministic and stdlib-only (hardcoded vocabulary, no network, no
model), so the honest fix is to build the fixture on demand rather than
to skip the tests or add them to the workflow's ignore list. Building
S1 + S2 takes well under a second.

Usage from a test module::

    from tests._lrb_fixtures import ensure_scenario
    FIXTURE_S2 = ensure_scenario("S2")
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_FIXTURE_DIR = ROOT / "eval" / "external" / "_fixtures" / "lrb"

# scenario key -> (fixture filename, builder script)
_SCENARIOS = {
    "S1": ("scenario_S1_quarterly.json", "build_lrb_scenario_s1.py"),
    "S2": ("scenario_S2_yearly_timetravel.json", "build_lrb_scenario_s2.py"),
    "S3": ("scenario_S3_publication_scale.json", "build_lrb_scenario_s3.py"),
}


def ensure_scenario(key: str) -> Path:
    """Return the fixture path, building it first if it is absent."""
    try:
        filename, builder = _SCENARIOS[key]
    except KeyError:                                   # pragma: no cover
        raise ValueError(f"unknown LRB scenario {key!r}") from None

    path = _FIXTURE_DIR / filename
    if path.exists():
        return path

    script = ROOT / "scripts" / "research" / builder
    if not script.exists():                            # pragma: no cover
        raise FileNotFoundError(
            f"LRB {key} fixture is missing and its builder {script} does "
            f"not exist — cannot reconstruct the scenario"
        )

    # The builders print a short summary to stdout; keep it out of the
    # test report but let a real failure propagate.
    _FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    stdout, sys.stdout = sys.stdout, open("/dev/null", "w")
    try:
        runpy.run_path(str(script), run_name="__main__")
    finally:
        sys.stdout.close()
        sys.stdout = stdout

    if not path.exists():                              # pragma: no cover
        raise FileNotFoundError(
            f"{builder} ran but did not produce {path}"
        )
    return path
