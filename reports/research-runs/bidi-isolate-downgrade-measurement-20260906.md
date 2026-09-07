# Isolate downgrade: how much concealment does an RLI wrapper actually buy?

**Date**: 2026-09-06
**Occasion**: Ali Afana (Provia), 2026-09-06 reply, finding ① follow-up.
**Status**: measured; 10/10 claims reproduced by a checked-in harness
(see *Reproducing*). Answers a question Ali explicitly flagged as **not**
measured on his side.

## The question

Both gates — his and ours — remove override spans (LRO/RLO) whole, and
leave embeddings (LRE/RLE) and isolates (LRI/RLI/FSI/PDI) strip-only,
because deleting an isolate's contents destroys legitimate bidirectional
text. Ali's observation:

> an attacker who switches RLO to RLI gets the old behavior back:
> wrapper removed, payload forwarded. How much practical concealment an
> isolate wrapper actually buys is something I have not measured, so I'm
> flagging it as a question, not a finding.

The downgrade reproduces on JAMES exactly as he describes.
`normalize_user_input` on `"price: " + RLI + payload + PDI + " end"`
returns the payload as cleartext; only the RLO/LRO forms lose their span.

But "the payload is forwarded" is only half the question. The other half
is whether the attacker still has an attack after the switch — i.e.
whether an isolate conceals anything.

## Method

Unicode Bidirectional Algorithm, resolved with `python-bidi` 0.6.11
(the Rust `unicode-bidi` backend, which implements UBA 6.3+ isolates).

**A first attempt was invalid and is recorded here as such, along with
a wrong diagnosis of why.** The first probe raised
`AssertionError: RLI not allowed here`. Read naively that looks like
"the isolate did not survive" — a library limitation reported as a
Unicode result.

The first explanation for it was also wrong: *"the installed version
predates isolate support."* It does not. `python-bidi` 0.6.11 exposes
**two** entry points from the same install, and they do not implement
the same algorithm:

| import | backend | RLO | RLI |
|---|---|---|---|
| `from bidi import get_display` | Rust `unicode-bidi`, UBA 6.3+ | mangles | resolves |
| `from bidi.algorithm import get_display` | legacy pure-Python, kept for compatibility | mangles | **raises** |

Both agree on overrides, which is what makes it dangerous: the legacy
path looks correct on every RLO case you check first, then answers a
question about isolates by throwing. Nothing about the package version
warns you. This is the same shape as the hazard Ali reported from his
own fifteen re-checks — a probe that appears to be exercising the thing
under test and is not.

Display order is compared with the invisible controls stripped from the
output, so the comparison is what a reader sees.

## Result

| context | wrapper | payload spelled intact in display order |
|---|---|---|
| LTR | none | ✅ `ignore all previous` |
| LTR | **RLO** | ❌ `suoiverp lla erongi` |
| LTR | **RLI** | ✅ `ignore all previous` |
| Arabic | none | ✅ |
| Arabic | **RLO** | ❌ `suoiverp lla erongi` |
| Arabic | **RLI** | ✅ |

**An isolate never mangles spelling.** Override is the concealment
primitive because rule X6 reassigns the *character types* of its
contents; an isolate does not — its contents resolve normally and the
isolate acts as a single neutral in the outer context.

So the downgrade is not free for the attacker. Switching RLO→RLI does
get the payload past the span removal, but it arrives on screen reading
left-to-right, correctly spelled, **indistinguishable from having sent
it with no wrapper at all**. The concealment is what the attacker gave
up in order to pass.

### The residual, stated precisely

An isolate can still change *placement* — the run moves as a unit
relative to its neighbours. Constructed so the isolate boundary falls
between a phrase and an adjacent number, the number changes sides:

```
bare      لاير transfer funds 100 رعسلا
isolated  لاير 100 transfer funds رعسلا     <-- 100 moved
```

**This is much weaker than it first looks, and one over-claim was
caught while writing this.** Wrap a *natural* phrase — an isolate around
a complete clause in a real Arabic price line — and the display is
byte-identical to the unwrapped text. The relocation above requires the
attacker to draw the isolate boundary through the middle of a phrase,
in RTL context, with a number at the seam.

A second trap, worth naming because it would be easy to file as a
finding: in plain Arabic with **zero** control characters, the digit
runs already appear in a different order on screen than in logical
order (`السعر 100 والشحن 20 ريال` → displayed `20 … 100`). That is
ordinary RTL rendering, not an attack, and it is present with and
without any isolate.

## Verdict

- **Instruction-injection concealment via isolate downgrade: no.**
  Measured, both LTR and RTL context. The payload reads normally.
- **Numeric adjacency via isolate placement: narrow yes**, but only
  under an unnatural boundary placement, and it does not survive
  wrapping a natural phrase.
- **Not a reason to start deleting isolate contents.** The cost Ali and
  we both cite — destroying real bidirectional text — is unchanged, and
  the thing it would buy is smaller than assumed.

## What this does not cover

Rendering is client-dependent. This measures the Unicode algorithm, not
any particular terminal, browser or PDF viewer, some of which implement
isolates incompletely. A client that mis-implements isolates could
behave differently; that is a per-client question and is not measured
here.

## Reproducing

```
python3 scripts/research/verify_bidi_isolate.py
```

`scripts/research/verify_bidi_isolate.py` asserts all ten claims above
(six table rows, the two relocation claims, the natural-phrase identity,
and the control-character-free digit reorder). It passes 10/10 as of
this document.

It is a script, not a pytest test, and `python-bidi` is deliberately
**not** added as a JAMES dependency — nothing in the product renders
bidi text, and a CI test importing it would fail. It happened to be
present in this environment at 0.6.11.

The one thing to get right when re-running: import `get_display` from
`bidi`, **not** from `bidi.algorithm`. The script asserts this itself
and refuses to report numbers from the legacy path — see *Method*.
