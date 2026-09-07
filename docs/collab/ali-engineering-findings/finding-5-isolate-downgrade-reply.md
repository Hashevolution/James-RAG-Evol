# ⑤ Ali 5차 메시지 회신 (isolate 측정 + probe 함정 상호보고)

**성격**: Ali 2026-09-06 메시지에 대한 회신. 건당 1통 형식.
**상태**: 발송 가능. ④(Track 2c 재측정)와 **독립** — 이 편지는 ④를
기다리지 않는다.

## 왜 지금 보내는가

Ali 5차는 회신이 아니라 **반대 방향 감사**다. 그가 명시적으로
*"a question, not a finding"* 으로 남긴 것 — isolate 래퍼가 은닉을
얼마나 사주는가 — 에 우리 쪽 측정이 나왔다. 그리고 그는 자기 스택의
numeral/orthography 수정이 *"queued and unshipped... still live
defects"* 라고 밝혔다. 큐가 밀린 사람에게 이 결과는 **어디에 시간을
쓰지 않아도 되는지**를 알려준다. 늦을수록 가치가 준다.

그가 *"no clock on this side"* 라고 한 것은 ④에 대해서지 이 질문에
대해서가 아니다.

## 근거 자료

- `reports/research-runs/bidi-isolate-downgrade-measurement-20260906.md`
- `scripts/research/verify_bidi_isolate.py` (10/10 재현)
- probe 수정: `james_security_test.py` `t_fix3_*` 2건

편지의 모든 수치는 위 소스에서 직접 측정한 것이며, 초안이나 커밋
메시지에서 옮기지 않았다.

---

Ali,

The isolate question has an answer. Taking it first because you left it
open and because it bears on where you spend the queue you described.

## The downgrade, measured

It reproduces here exactly as you said it would. `normalize_user_input`
on `"price: " + RLI + payload + PDI + " end"` hands the payload back as
cleartext; only the override forms lose their span. Wrapper removed,
payload forwarded — your finding #1 living in the tail of my fix, same
as it lives in the tail of yours.

But that is half the question. The other half is whether the attacker
still has an attack after the switch, and the answer is no.

An override is the concealment primitive because rule X6 reassigns the
*character types* of its contents. An isolate does not: its contents
resolve normally and the isolate acts as a single neutral in the outer
context. Measured against the algorithm, both directions of context:

| context | wrapper | payload in display order |
|---|---|---|
| LTR | none | `ignore all previous` |
| LTR | RLO | `suoiverp lla erongi` |
| LTR | RLI | `ignore all previous` |
| Arabic | none | intact |
| Arabic | RLO | reversed |
| Arabic | RLI | intact |

So the downgrade is not free. It gets the payload past the span removal
and delivers it reading left to right, correctly spelled — **indistinguishable
from having sent it with no wrapper at all**. The concealment is the
price of passing the gate. Which is, I think, the gate working: the
attacker can have the text through or hidden, not both.

The practical read for your queue: this is not a reason for either of us
to start deleting isolate contents. The cost we both cite — destroying
real bidirectional text — is unchanged, and what it would buy is smaller
than it looks from the downgrade alone.

## The residual, and one over-claim I caught

An isolate can still move a run as a unit relative to its neighbours.
Draw the boundary between a phrase and an adjacent number and the number
changes sides:

```
bare      لاير transfer funds 100 رعسلا
isolated  لاير 100 transfer funds رعسلا
```

I nearly sent that as a numeric-adjacency finding, which would have been
wrong. Wrap a *natural* phrase — an isolate around a complete clause in
a real Arabic price line — and the display is byte-identical to the
unwrapped text. The relocation needs the boundary drawn through the
middle of a phrase, in RTL context, with a number at the seam. It is a
constructed shape, not something a sentence falls into.

One more worth naming because it is easy to file as a finding and is
not one: plain Arabic with **zero** control characters already shows
digit runs in a different order on screen than in logical order —
`السعر 100 والشحن 20 ريال` displays as `20 … 100`. Ordinary RTL
rendering, present with and without any isolate. If your price extractor
ever grows a display-order cross-check, that is the thing that will fire
first and it will not be an attack.

The measurement is of the Unicode algorithm, not of any particular
client. A terminal or viewer with incomplete isolate support could
differ, and I have not surveyed clients.

## Two residuals side by side

You asked that each of us know the other's rather than assume it closed,
so here is mine with a number on it. On an unterminated override we
remove to end of input, and the cost is exactly what you said. A stray
opener early in legitimate input:

```
in    السعر ⟪RLO⟫ 100 ريال والشحن 20 ريال والتسليم غدا     (44 chars)
out   السعر                                            (6 chars)
```

(`⟪RLO⟫` is the invisible U+202E, shown so the example is readable.)
38 of 44 characters destroyed by one stray control. When the opener
leads the question, the whole thing goes and the request terminates in a
400 rather than an answer.

I want to be careful about what this does and does not say about your
80-character cap. It says nothing — your window is on overrides, my
isolate measurement is on isolates, and I have not measured your trade.
The only structural remark I will make is about my own side's failure,
since I do not know how yours is instrumented and will not guess. Mine
is loud by construction: it drops text and logs the counts
(`override_spans_removed`, `override_span_chars`, `chars_dropped` land
in the stage log whenever anything is dropped), so a destroyed question
leaves a record and, at the limit, a 400 the user sees. The failure that
worries me more is the one that produces no artefact at all — a payload
arriving as ordinary input, indistinguishable from a real question —
because there is nothing for anyone to find later. That is a general
remark about failure shapes, not a claim about what your gate records;
if your cap logs its truncations then the asymmetry I am describing is
not there. And it cuts the other way on what matters to real traffic:
your cap protects legitimate trailing text that mine destroys. Two
settlements, and the measurement I have does not pick between them.

## Your hazard, found in my own suite

*"Break one keyword per sentence or you are measuring the wrong thing."*
I went looking and found it, in the mirror form: not an evasion looking
harmless, but an untested layer looking tested.

Our security layer ORs a literal list against a regex list. Two tests
exist specifically to prove the regex list catches what the literals
miss. `t_fix3_regex_patterns` asserts variants "not in ATTACK_PATTERNS"
— and two of its five were literals, blocked before the regex layer was
reached. `t_fix3_sanitize_regex`, named for regex substitution, used a
query matching **zero** regexes; it passed entirely on the literal path,
so the substitution it exists to verify had never once run. Both green since
they landed on 2026-06-23, neither measuring its own name.

Fixed with regex-only inputs, but the part I took from your message is
that fixing the inputs is not enough — the next person to extend the
literal list re-breaks it silently. So the premise is now asserted
rather than assumed: a `_regex_only()` helper checks that each probe
misses every literal and hits at least one regex, and the test fails
loudly if a pattern list later absorbs its own probe.

Two of my own probes were wrong while measuring the isolate question,
and the second is the more useful one to pass on. The first raised
`AssertionError: RLI not allowed here`, which reads as "the isolate was
neutralised" and is not that. My first explanation for it was also wrong
— I wrote "the installed version predates isolate support," and it does
not. One `python-bidi` install exposes two entry points running
different algorithms: `bidi.get_display` is the Rust UBA 6.3+ backend,
`bidi.algorithm.get_display` is a legacy pure-Python path kept for
compatibility. They agree on every override case, then the legacy one
answers the first isolate question by throwing. Nothing about the
version warns you, so checking the version — which is what I did — tells
you nothing. My harness now refuses to print numbers from the legacy
path rather than trusting me to remember which import I used.

Your fifteen re-checks caught one probe. Mine caught two, and one of
them was my diagnosis of the other.

## Your language-guard finding, against our code

You described a deterministic guard gated behind an LLM classifier's
language verdict, silently inheriting its error rate, fixed by deriving
the expected language from the script and demoting the model to a
fallback. I checked ours against that shape. `core.i18n.detect_language`
is already script-derived — Hangul syllable count against ASCII letter
count, no model anywhere upstream. So we do not have your defect; we
appear to have landed where you landed, by a different route.

The residual is ours and it is a different mechanism, which is what
makes your framing useful rather than just reassuring. Our classifier
does not inherit an error rate from a model — it manufactures one from
its own codomain. It returns `"ko"` or `"en"` and nothing else, with
ties and zero-counts defaulting to `"ko"`. Arabic scores zero Hangul and
zero ASCII letters, so **every Arabic query classifies as Korean**,
confidently, with no model involved and no error rate to inherit. A
two-way classifier fielding a question that has more than two answers.

Your sentence survives the substitution intact: language identification
sits upstream of the safety machinery and owns its error rate without
appearing in any of its code. Yours was a router field feeding one
guard, mine is a binary counter feeding every reasoning stage, and
neither error is visible from inside the machinery it misdirects.

A correction owed on that, since you quoted my number back to me. I
wrote "seven consumers" in the third finding and it is wrong. It is
**six** modules — the planner, the query rewriter, verify, the reflect
loop, and the memory and synth paths in the engine — across eight call
sites. Neither count is seven. I checked at the commit the letter was
written against as well as at today's head, in case the code had moved
under me; it was six then too. I cannot reconstruct where seven came
from, and I would rather say that than invent a reading that makes it
true. The shape of the finding is unchanged. The number was decoration,
and it was wrong.

## Three short ones

On the scorer separation — your reading of it is right. Our fold runs at
comparison time on both sides and is deliberately kept local to the
runner rather than imported from the product tree, with that reasoning
written into the file: the runner is a black-box client of the server,
and the fixture-to-server boundary is what the bidi cases test. Same
separation, arrived at from the other direction, as you said.

On the 100-case suite and the "language lane exists" row — accepted, and
we are not building an Arabic lane. Your sizing of the outcome is the
one I would have wanted: stop describing the support as though the only
gap were a keyword list. That is done on our side and it is where I
intend to leave it.

On the fourth — understood, and no clock is welcome, because the gate
there is not only a machine. The evidence the re-measurement destroys
lives on the machine that produced the published numbers, so it is not
something I can stand up anywhere convenient; it has to run where that
history is. It will come with the numbers in it or not at all.

— Jiwon
