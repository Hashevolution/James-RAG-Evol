# Arabic E-commerce Adversarial Suite — for the JAMES adversarial-prompt collaboration

The Arabic cross-locale leg of the shared adversarial-prompt suite — companion to the
Korean + English baselines on the JAMES / Hashevolution side. Authored on the Provia side
(Arabic-speaking Instagram/Facebook merchant sales agent) and run against a production-shaped
deployment, so the fixtures arrive with evidence that they fire on a real system.

## What's here now (the pilot — done)

| File | What it is |
|---|---|
| `ar_ecommerce.yaml` | 18 Arabic adversarial cases, 4 families. Pure data, pytest-parametrize-ready, no framework imports. Schema `1.1-pending-alignment` — remap field names to JAMES canonical v1.1 where they differ; the cases are stack-agnostic. |
| `adversarial-sweep-results.json` | Raw run output — every prompt, reply, latency. |
| `REPORT.md` | Per-case verdicts + cross-cutting findings from running the suite against the production stack. |

**Four attack families:** prompt injection (Arabic + Arabizi) · RTL/LTR bidi confusion
(U+202E) · MSA↔Levantine dialect jailbreak · catalog poisoning (fake products / specs /
prior agreements / promos).

**Pilot headline:** the refusal layer held (no system-prompt or floor-price leak under direct,
transliterated, or formal-register attack), but the **grounding layer failed open** — the bot
confirmed a fabricated promotion and hallucinated a whole product with an invented price. One
bidi case proved U+202E content reaches the model even when the outcome stays safe. Full
verdicts + the confounds (catalog mismatch, single-turn, N=1) are disclosed in `REPORT.md`.

## What's coming (the 100-case English↔Arabic comparison)

A scaled run that takes a recognized English adversarial set, renders it in Arabic
(MSA / Levantine / Arabizi / bidi), runs **both languages** against the same stack, and
reports the **failure-rate delta** — the cross-lingual safety/grounding gap as a number, plus
a before/after once the grounding fix lands. Lands in `corpus/` + `COMPARISON.md`.

## Schema (v1.1-pending-alignment)

Each case carries: `id`, `family`, `lang`, `severity`, `title`, `attack_intent`,
`user_message` (the payload — bidi controls written as `‮`-style escapes), and
`expected_behavior` + `pass_criteria` for scoring. Load with:

```python
cases = yaml.safe_load(open("ar_ecommerce.yaml"))["cases"]
# @pytest.mark.parametrize("case", cases, ids=[c["id"] for c in cases])
```

## Reproduce

Start the target deployment, then run the driver (`run-adversarial-sweep.mjs`); `BASE_URL`
and store id are at the top of the script.

## Context

This Arabic suite extends the JAMES / Hashevolution adversarial-prompt work to a third locale
and a production deployment context. Intended to drop into the shared suite once field names
align to the canonical v1.1 schema.

*License: MIT — research artifact.*
