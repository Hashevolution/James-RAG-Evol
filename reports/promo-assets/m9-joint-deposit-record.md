# M9 — three-author convergence record (PUBLISHED)

**DOI**: [`10.5281/zenodo.22030935`](https://doi.org/10.5281/zenodo.22030935)
**Published**: 2026-08-19 · report · CC-BY-4.0 · English · v1.0.0
**Authors** (alphabetical, non-political): Afana, Ali (Provia) ·
Converse, Robin (Triava Labs) · Seo, Jiwon (Hashevolution)
**Submitted by**: Ali Afana, on two OKs (Converse, Seo).

This is the read-only outcome record that
`docs/collab/m9-joint-deposit-prep/README.md` §"What changes after
publish" calls for. The prep folder stays in place as the historical
audit trail; nothing there is authoritative any more.

---

## What the record archives

Three independently built systems converging on the same architectural
split — substitution calls (stateless, short, structured) separated from
synthesis calls (contextual, long-form) — on three measured axes:

| Axis | Owner | Stack |
|---|---|---|
| Mode split, byte-identical substitution, cap-invariance | Converse | sovereign Ollama, gemma4:26b MoE |
| **Workload gradient — 7-tier natural stop, 62 → 1681 tokens, 27×** | **Seo** | **JAMES middleware, gemma4:e4b** |
| Production runtime under shipped prompts + instruction-removed arm | Afana | hosted gpt-4o-mini sales router |

**The JAMES leg** is the V3′ Direction 1 closure — PRs
[#461](https://github.com/Hashevolution/James-RAG-Evol/pull/461) /
[#463](https://github.com/Hashevolution/James-RAG-Evol/pull/463),
archived as v0.3.1, DOI `10.5281/zenodo.20363998`. The earlier two-mode /
three-workload split is PR
[#440](https://github.com/Hashevolution/James-RAG-Evol/pull/440);
Converse's cross-stack numbers are issue
[#448](https://github.com/Hashevolution/James-RAG-Evol/issues/448).

## What JAMES contributed beyond its axis

**Citation corrections.** The record's first draft cited the seven-tier
gradient as "PR #440, Issue #448". #440 is the three-level precursor and
predates Direction 1; #448 is Converse's leg. The mislabel originated in
our own prep folder, which had never been updated after v0.3.1 upgraded
the axis from a binary split to seven tiers. Fixed here and in the
record (see PR #1077).

**Honest-framing caveat, carried verbatim.** The seven-tier figure is
total completion tokens (`eval_count`), which on gemma4:e4b includes a
hidden reasoning trace: 5 of 7 tiers are 82–98% trace. The record says
so, and names the substitution baseline (2%) and `reflect` (61%, 580
visible tokens) as the tiers carrying unambiguous workload signal.

**Two precision fixes in the final text.**

1. *The instruction effect.* The production leg dismissed a 127 → 138.5
   token shift as "smaller than within-cell spread". Within-cell spread
   is per-call dispersion; a shift in centres clears the error on the
   centre (~3 tokens for the difference of two 80-call medians), so
   +11.5 is roughly four times it, and all four cap cells moved the same
   way with the two median sets disjoint. Restated as: removing the
   instruction lengthens the reply by about 9% — a contributor, not the
   binding constraint.
2. *The no-trace explanation.* "A hosted model with no reasoning trace
   floors near its visible answer" read as established, but the
   reasoning axis was never varied on that stack and every trace-side
   number in the record comes from e4b. The body now matches the
   record's own claim-scope section.

**Identifier verification.** The three v0.3.x DOIs
(`20363998` / `20372649` / `20374227`) and the four repository pointers
(#461, #463, #440, #448) were checked against source before submission.
No concept DOI is cited — it resolves to the latest version of the
chain, the wrong artifact for a v0.3.x citation.

**The stitch clause.** The forward-pointer sentence now on all three
surfaces was drafted on the JAMES side; Ali's README already resolves to
the live DOI with the production clause, and this repository carries the
middleware clause in README §Papers & Reproducibility.

## Attribution note — Vadym Arnaut

The record went out three-author. Vadym Arnaut appears in
`docs/collab/m9-joint-deposit-prep/four-way-attribution-catalog.md` §3 as
the source of "each variant has its own tax", flagged by Converse during
Phase R6. **That phrasing does not appear in the published text**, so
this record carries no attribution defect, and the 3-vs-4-author question
it was gating is moot for it. The catalog entry stands for any future
deposit that does use the phrase.

## Ali's forward-pointer trail

Per his 2026-08-19 message: his README pointer resolves to the live DOI,
the issue #448 note goes up the same day, and the template is free for
each stack to place on its own surfaces.

## What is still open

- **Four engineering findings** from Ali's 2026-08-19 letter — bidi span
  removal, Arabic NFKC/tatweel normalisation, salted run identities plus
  a Track 2c re-measurement, and unicode digit parsing in the JS
  renderer. The first reply promised a separate message once measured;
  three are confirmed live defects here, one (`\d` ASCII-only) does not
  reproduce in the Python scorer but does in the browser renderer.
- **arXiv assembly** — Ali's next thread, opening once a draft exists.

## Trail

| Artifact | Role |
|---|---|
| `docs/collab/m9-joint-deposit-prep/` | historical drafts + publish gates (superseded) |
| `docs/collab/m9-joint-deposit-prep/ali-reply-draft-2026-08-19.md` | first reply — axis correction, DOIs, engineering findings (SENT) |
| `docs/collab/m9-joint-deposit-prep/ali-reply-2-draft-2026-08-19.md` | second reply — conditional OK + the two precision fixes (SENT) |
| PR #1077 | repository-side citation + DOI-lineage corrections |
