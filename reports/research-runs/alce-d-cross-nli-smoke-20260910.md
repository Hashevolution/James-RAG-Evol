# D-alce — research-tier cross-NLI smoke, both legs (2026-09-10)

Pre-registration: `docs/research/cycle-gamma-d-alce-research-tier-nli-preregistration-2026-06-12.md`
(config unchanged since; no re-prereg needed per its §2 last row).
Runner: `scripts/research/alce_smoke_run.py --n 20 --model gemma4:e4b
--verifier {roberta-mnli,deberta-v3-anli}`. Fixture ASQA dev, front-slice
n=20 (deterministic), top-5 ALCE-published passages, producer
`ALCEClosedCorpusProducer` on Ollama gemma4:e4b.

The RoBERTa leg had been run on 2026-06-21 / 06-22; the DeBERTa leg had
never been run, so the prereg's verdict — which is a *pair* comparison —
was still open. Both legs were run **today, back to back, same
producer config**, so the pair is same-day.

## 1. Results

| Verifier | citation_precision | citation_recall | verifier_grade | honest tier |
|---|---|---|---|---|
| string-containment (fallback, 2026-06-11) | 0.8168 | 0.9067 | fallback-string-containment | ⭐ infra-only |
| RoBERTa-large-MNLI (2026-06-21) | 0.6239 | 0.7344 | research-tier-roberta-mnli | ⭐ research-tier |
| RoBERTa-large-MNLI (2026-06-22) | 0.5849 | 0.6825 | research-tier-roberta-mnli | ⭐ research-tier |
| **RoBERTa-large-MNLI (2026-09-10)** | **0.5670** | **0.6981** | research-tier-roberta-mnli | ⭐ research-tier |
| **DeBERTa-v3 (mnli-fever-anli-ling-wanli) (2026-09-10)** | **0.7938** | **0.8727** | research-tier-deberta-v3-anli | ⭐ research-tier |
| T5-XXL TRUE NLI (ALCE-official) | — | — | — | DEFERRED, NOT RUN |

Both same-day result files carry the prereg §3 fields (`verifier_grade`,
`honest_tier`, `fixture_sha` = `d72737ce…`, n=20, errors 0/20):
`reports/external/alce/asqa-smoke-20260910T064312Z.result.json` (RoBERTa),
`…20260910T064201Z.result.json` (DeBERTa).

## 2. Pre-registered verdict

Same-day Δ (DeBERTa − RoBERTa): **precision +0.227, recall +0.175** — both
above the prereg's 0.10 disagreement threshold.

| Prereg §2 row | Fires? |
|---|---|
| RoBERTa = DeBERTa, both LOWER than string-containment | no — DeBERTa is not lower than RoBERTa |
| **RoBERTa ≠ DeBERTa (Δ > 0.10) → cross-NLI disagreement** | **yes** |
| RoBERTa = DeBERTa = string-containment (Δ < 0.05) | no |
| a leg failed to load / 0 evaluations | no — 20/20 both legs |

**Verdict (pre-registered wording): ⭐ research-tier infra validated +
cross-NLI sensitivity finding.** Consequence, also pre-registered: the
T5-XXL TRUE NLI cycle is the prerequisite before any research-tier ALCE
number goes into the paper on its own — "without cross-checkpoint
agreement, robustness is insufficient". Per §4, research-tier scores are
only ever cited **as a pair**, never one verifier alone.

## 3. What the disagreement looks like per query

| Axis | DeBERTa higher (>0.05) | lower | tie | \|Δ\| ≥ 0.5 |
|---|---|---|---|---|
| citation_precision | 12 / 20 | 2 | 6 | 7 |
| citation_recall | 8 / 20 | 1 | 11 | 4 |

It is a systematic direction, not noise: DeBERTa returns ENTAILMENT for
citation ⟹ sentence pairs that RoBERTa calls neutral/contradiction, on a
third of the queries by half a point or more. The adapter treats both
verifiers identically (`argmax == ENTAILMENT` → cited-and-supported;
`eval/external/alce_nli_adapter.py:38`), so this is the checkpoints
disagreeing, not a mapping difference. Note the ordering: DeBERTa
(0.79 / 0.87) lands close to the string-containment fallback
(0.82 / 0.91), RoBERTa far below it — which of the two is "right" is
exactly what the ALCE-official T5-XXL verifier is for.

Consistent with HR v0.2.4 (`lrb-v024-hr-n100-cross-nli-20260621.md`),
where DeBERTa was also the more lenient checkpoint and the *ordering*
across SUTs survived while absolute levels did not.

## 4. Producer drift, bounded

The June RoBERTa legs used answers generated in June; today's legs used
answers generated today (the producer is an LLM; it is not cached). Same
verifier, different day: aggregate moved **0.585 → 0.567 / 0.683 → 0.698**
(≈ 0.02), while per-query |Δ| averaged 0.15 / 0.18. So the producer is
noisy per query and stable in aggregate, and the 0.23 / 0.18 verifier gap
is an order of magnitude larger than the day-to-day producer gap. The
pair comparison stands on its own day regardless.

## 5. What this does and does not license

- Licensed: the sentence in a paper *methods* table that string-containment
  is a lenient upper bound and that two research-tier NLI checkpoints
  disagree by ~0.2 on ASQA citation support at n=20 — with both numbers
  shown, per prereg §4.
- Not licensed: any ALCE citation score for JAMES as a result claim. Not
  ALCE-grade (T5-XXL deferred, GPU-only), not publication-N (n=20; F-alce
  full N=300–1000 is gated behind this verdict per prereg §6 and is now
  explicitly a T5-XXL-first decision).
- E-alce (RAB preprint v1.4 "ALCE outer validation" section) is an
  operator step after arXiv submission; the paired numbers above are what
  it would cite.

## 6. Wall clock

DeBERTa leg 387 s (34 s producer + ~350 s CPU NLI, ~200 pairs); RoBERTa leg
53 s. Both checkpoints were already in the HF cache from HR v0.2.4.

## One line

The two research-tier NLI checkpoints disagree by ~0.2 on ASQA citation
support (RoBERTa 0.57 / 0.70, DeBERTa 0.79 / 0.87, same day, same answers);
the pre-registered verdict is *infra validated + cross-NLI sensitivity*,
and it moves T5-XXL from "deferred" to "prerequisite".
