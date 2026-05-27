<!--
JAMES PR template (v0.4, QVT α-4 — 2026-05-28). Match the body
sections below; CI does not enforce the structure but reviewers and
the v0.4 quality gate (`docs/handovers/v0.4-quality-verification-track.md`)
expect them.
-->

## Summary

<!-- 1-3 sentences. What the PR does and why. -->

## Verification

<!-- How the change was validated. Tests run, manual checks, smoke
results, links to bench JSONs in reports/research-runs/. -->

## Quality Delta vs baseline_<sha>

<!--
Required when this PR touches `core/retrieval/`, `core/graph/`, or
`core/reasoning/` (CLAUDE.md rule 2). Compare against the canonical
baseline at `eval/qvt/baseline_<sha>.json`. Three axes:

| axis              | baseline | this PR | Δ | sign |
|-------------------|----------|---------|---|------|
| Path Recall       | 0.87     | 0.91    | +0.04 | ✅ |
| Graded Answer     | 0.71     | 0.68    | −0.03 | ⚠️ within noise |
| Abstention F1     | 0.83     | 0.84    | +0.01 | flat |

Noise band: ±<value> (from baseline JSON `aggregate.*.noise_band`).
Verdict: <net positive / net neutral / net negative + justification>.

Exempt — add this single line and delete the table when one of the
following labels applies, then remove this comment block:

  Quality delta: exempt (label: <external-contributor | joint-collab-prep | docs | chore | ci | code>)

Exemption labels (design memo §4):
  - external-contributor — Robin / Ali / other collaborator PR
  - joint-collab-prep    — mid-June joint piece / shared deliverable
  - docs / chore / ci    — does not touch core/
  - code                 — circular (PR is the oracle / baseline itself)
-->

## Out of scope

<!-- Explicit defers. What this PR intentionally does NOT do. -->
