"""Build the RAB pre-registration Zenodo deposit bundle.

This packages the Phase 3 (scenario-S2) pre-registration into a zip
artifact suitable for upload to Zenodo as a separate, citable record.

Why a separate deposit (not just the v0.4.3 release archive):
- The v0.4.3 Zenodo DOI ``10.5281/zenodo.20625533`` archives the
  software state at release time. The pre-registration's value is
  *temporal*: it locks the measurement protocol BEFORE the measurement
  exists. A standalone DOI is the strongest external timestamp for
  that priority claim.
- Reviewers can cite the pre-registration DOI without needing the
  whole software archive.

The bundle includes:
- the pre-registration doc itself (frozen at commit d21c680)
- the frozen SPEC v0.1 (which the pre-registration commits to test)
- this script (the build provenance witness)
- a README pointing to the source commit and the related identifiers

Run::

    python scripts/research/build_rab_prereg_deposit.py

Output::

    reports/zenodo/rab-prereg-phase-3-s2.zip
    reports/zenodo/rab-prereg-phase-3-s2.metadata.json

The metadata JSON is a recommendation; the operator pastes the fields
into the Zenodo web form (or uses the Zenodo REST API).
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = ROOT / "reports" / "zenodo"
OUT_ZIP = OUT_DIR / "rab-prereg-phase-3-s2.zip"
OUT_META = OUT_DIR / "rab-prereg-phase-3-s2.metadata.json"

PREREG_DOC = ROOT / "docs" / "research" / "r1-phase-3-scenario-s2-preregistration-2026-06-10.md"
SPEC_DOC   = ROOT / "eval" / "rab" / "SPEC-v0.1.md"
THIS       = Path(__file__).resolve()

# The pre-registration's locked-at commit (PR #774). Anyone can
# independently verify the bundle by running ``git show <SHA>``.
PREREG_COMMIT = "d21c680a51ba455f6712cca21db38af310b5868f"
PREREG_DATE   = "2026-06-10"

# Zenodo metadata (recommendation — operator confirms / edits on upload)
METADATA = {
    "metadata": {
        "title": (
            "Pre-Registration: Replayable-Audit Benchmark (RAB) Phase 3 — "
            "scenario-S2 'lifecycle-large'"
        ),
        "upload_type": "publication",
        "publication_type": "preprint",
        "publication_date": PREREG_DATE,
        "creators": [
            {"name": "Seo, Ji Won", "affiliation": "JAMES (Hashevolution)"},
        ],
        "description": (
            "<p>This deposit is the locked pre-registration for Phase 3 "
            "(scenario-S2) of the Replayable-Audit Benchmark (RAB). It "
            "specifies the scenario shape (400 ops; 110 INGEST / 40 UPDATE "
            "/ 30 SUPERSEDE / 20 DELETE / 200 QUERY; 40 checkpoints; "
            "supersede chain length avg &ge; 3, longest &ge; 5; "
            "cross-reference density &ge; 2.5), the four systems under "
            "test (Reference, JAMES, Baseline-0, Baseline-1), the "
            "RF-cost activation hypothesis, the honest-tier gate, and the "
            "result-reporting protocol &mdash; all committed BEFORE the "
            "scenario fixture is constructed and any measurement is "
            "executed. The frozen SPEC v0.1.1 that the pre-registration "
            "commits to test is included as evidence.</p>"
            "<p>Source repository: "
            "<a href='https://github.com/Hashevolution/James-RAG-Evol'>"
            "Hashevolution/James-RAG-Evol</a>. "
            f"Locking commit: <code>{PREREG_COMMIT}</code> "
            f"({PREREG_DATE}, PR #774). RAB software archive at locking "
            "time: <a href='https://doi.org/10.5281/zenodo.20625533'>"
            "10.5281/zenodo.20625533</a> (v0.4.3).</p>"
            "<p>This deposit is the priority-date anchor for any RAB "
            "Phase 3 result subsequently reported against scenario-S2.</p>"
        ),
        "keywords": [
            "RAB", "Replayable-Audit Benchmark", "pre-registration",
            "EU AI Act", "audit-log", "RAG", "provenance",
            "scenario-S2", "JAMES",
        ],
        "access_right": "open",
        "license": "cc-by-4.0",
        "related_identifiers": [
            {
                "identifier": "10.5281/zenodo.20625533",
                "relation": "isSupplementTo",
                "resource_type": "software",
                "scheme": "doi",
            },
            {
                "identifier": (
                    f"https://github.com/Hashevolution/James-RAG-Evol/commit/"
                    f"{PREREG_COMMIT}"
                ),
                "relation": "isDerivedFrom",
                "resource_type": "publication-other",
                "scheme": "url",
            },
        ],
        "notes": (
            "The locking commit hash is the in-git priority evidence; "
            "this Zenodo deposit is the external timestamped anchor. "
            "Any RAB scenario-S2 result that cites this DOI must report "
            "spec version, scenario sha, and re-verification artifacts "
            "per RAB SPEC v0.1.1 §4."
        ),
    }
}


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    files = [
        (PREREG_DOC, "r1-phase-3-scenario-s2-preregistration-2026-06-10.md"),
        (SPEC_DOC,   "RAB-SPEC-v0.1.md"),
        (THIS,       "build_rab_prereg_deposit.py"),
    ]
    for p, _ in files:
        if not p.exists():
            print(f"ERROR: missing input: {p}")
            return 2

    readme = (
        f"# RAB Phase 3 (scenario-S2) Pre-Registration — Zenodo Deposit\n\n"
        f"This zip packages the **locked** pre-registration of the\n"
        f"Replayable-Audit Benchmark (RAB) Phase 3 measurement\n"
        f"(scenario-S2 'lifecycle-large'), to be deposited on Zenodo as\n"
        f"a separate citable record from the v0.4.3 software archive.\n\n"
        f"## Contents\n\n"
        f"- `r1-phase-3-scenario-s2-preregistration-2026-06-10.md` —\n"
        f"  the pre-registration document, locked at commit\n"
        f"  `{PREREG_COMMIT}` (PR #774, {PREREG_DATE}).\n"
        f"- `RAB-SPEC-v0.1.md` — the SPEC v0.1.1 the pre-registration\n"
        f"  commits to test (frozen 2026-06-10).\n"
        f"- `build_rab_prereg_deposit.py` — the script that produced\n"
        f"  this bundle (reproducibility witness).\n\n"
        f"## Verification\n\n"
        f"Anyone can independently verify this bundle by running\n"
        f"`git show {PREREG_COMMIT}` against the source repository\n"
        f"(`Hashevolution/James-RAG-Evol`). The commit predates the\n"
        f"scenario-S2 fixture file (added in a later commit).\n\n"
        f"## Related identifiers\n\n"
        f"- RAB software archive at locking time: DOI\n"
        f"  10.5281/zenodo.20625533 (v0.4.3, 2026-06-10).\n"
        f"- Locking commit: GitHub `{PREREG_COMMIT}` (PR #774).\n\n"
        f"## Purpose\n\n"
        f"The locking commit hash is the in-git priority evidence;\n"
        f"this Zenodo deposit is the external timestamped anchor.\n"
        f"Any RAB scenario-S2 result that cites this DOI must report\n"
        f"spec version, scenario sha, and re-verification artifacts\n"
        f"per RAB SPEC v0.1.1 §4.\n"
    )

    with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.md", readme)
        for src, arcname in files:
            z.write(src, arcname=arcname)

    OUT_META.write_text(
        json.dumps(METADATA, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"wrote {OUT_ZIP}")
    print(f"wrote {OUT_META}")
    print(f"  files in bundle: {len(files) + 1} (incl. README.md)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
