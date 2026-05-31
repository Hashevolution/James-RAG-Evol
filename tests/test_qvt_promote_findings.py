"""Contract tests for scripts/qvt_promote_findings.py.

These exercise the parser and the promote filter on a synthetic
findings.md to keep the script honest as the findings log format
evolves.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "qvt_promote_findings.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("qvt_promote_findings", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["qvt_promote_findings"] = mod
    spec.loader.exec_module(mod)
    return mod


qpf = _load_module()


SYNTHETIC = """\
# Header

Preamble text.

## How to add a finding

Some boilerplate.

## Findings

<!-- comment -->

### 2026-05-31 — alpha-finding-a

- **bucket**: (b) LLM model capability — small tier ceiling
- **pattern**: 3/3 M_S cells show abstention F1 collapse
- **observation**: M_S abstains 80% on truth=present temporal queries
- **surprise**: gemma3:4b under-commits when temporal anchoring conflicts
- **data pointer**: `reports/x.json`
- **follow-up tag**: `mechanism-candidate`
- **probe ideas**: more sampling on temporal subset

### 2026-05-31 — beta-finding-b

- **bucket**: (d) measurement artifact
- **observation**: bench dropped sources
- **follow-up tag**: `data-quality`
- **data pointer**: `reports/y.json`

### 2026-05-31 — gamma-finding-c → RESOLVED (#999)

- **bucket**: (a) Architecture
- **observation**: layer wires duplicate retrieval
- **follow-up tag**: `universal-law` + `anti-pattern`

### 2026-05-31 — delta-finding-d

- **bucket**: (c) feature gap
- **observation**: no abstention judge
- **follow-up tag**: `operational`

---

## Promoted to memory

| Date | Finding slug | Memory file | Confirmed by |
|---|---|---|---|

(none)

## Carry-over from prior tracks

- some-other-thing — should NOT be parsed as a finding.
"""


def test_parse_findings_count_and_slugs():
    findings = qpf.parse_findings(SYNTHETIC)
    slugs = [f.slug for f in findings]
    assert slugs == [
        "alpha-finding-a",
        "beta-finding-b",
        "gamma-finding-c",  # resolution suffix stripped
        "delta-finding-d",
    ]


def test_parse_findings_extracts_bucket():
    findings = qpf.parse_findings(SYNTHETIC)
    buckets = {f.slug: f.bucket for f in findings}
    assert buckets == {
        "alpha-finding-a": "b",
        "beta-finding-b": "d",
        "gamma-finding-c": "a",
        "delta-finding-d": "c",
    }


def test_parse_findings_strips_backticks_from_tags():
    findings = qpf.parse_findings(SYNTHETIC)
    tags = {f.slug: f.tags for f in findings}
    assert tags["alpha-finding-a"] == {"mechanism-candidate"}
    assert tags["beta-finding-b"] == {"data-quality"}
    assert tags["gamma-finding-c"] == {"universal-law", "anti-pattern"}
    assert tags["delta-finding-d"] == {"operational"}


def test_carry_over_section_not_parsed_as_finding():
    findings = qpf.parse_findings(SYNTHETIC)
    assert "some-other-thing" not in [f.slug for f in findings]


def test_filename_uses_snake_case():
    findings = qpf.parse_findings(SYNTHETIC)
    by_slug = {f.slug: f for f in findings}
    assert by_slug["alpha-finding-a"].memory_filename == "finding_alpha_finding_a.md"


def test_render_draft_contains_frontmatter_and_body():
    findings = qpf.parse_findings(SYNTHETIC)
    f = findings[0]  # alpha
    out = qpf.render_draft(f)
    assert out.startswith("---\n")
    assert "name: finding-alpha-finding-a" in out
    assert "type: project" in out
    assert "## Source entry" in out
    assert "**Bucket**: (b)" in out
    assert "mechanism-candidate" in out


def test_promotion_filter_default_keeps_mechanism_and_universal():
    findings = qpf.parse_findings(SYNTHETIC)
    promoted = [f for f in findings if f.tags & qpf.PROMOTE_TAGS_DEFAULT]
    slugs = sorted(f.slug for f in promoted)
    assert slugs == ["alpha-finding-a", "gamma-finding-c"]


def test_promotion_filter_with_anti_pattern_keeps_three():
    findings = qpf.parse_findings(SYNTHETIC)
    promoted = [f for f in findings if f.tags & qpf.PROMOTE_TAGS_WITH_ANTI]
    slugs = sorted(f.slug for f in promoted)
    # alpha (mechanism), gamma (universal-law + anti-pattern)
    # beta has only data-quality, delta has only operational → not promoted
    assert slugs == ["alpha-finding-a", "gamma-finding-c"]


def test_data_quality_and_operational_not_promoted_by_default():
    findings = qpf.parse_findings(SYNTHETIC)
    promoted_default = {f.slug for f in findings if f.tags & qpf.PROMOTE_TAGS_DEFAULT}
    assert "beta-finding-b" not in promoted_default
    assert "delta-finding-d" not in promoted_default


def test_one_line_description_includes_date_and_bucket():
    findings = qpf.parse_findings(SYNTHETIC)
    f = findings[0]
    desc = qpf._one_line_description(f)
    assert desc.startswith("[2026-05-31, bucket-(b)]")


def test_empty_findings_section_returns_empty():
    text = "# Header\n\nNo findings section here.\n"
    assert qpf.parse_findings(text) == []
