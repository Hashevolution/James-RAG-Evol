# An axis for verify's warnings — and what it found on its first run (2026-09-28)

> **Why**: the 2026-09-27 n=3 contrast found the cognitive stages flat on
> every quality axis while costing 62% of query latency, and could not
> conclude from that — **none of the five axes scores verify's output**.
> With the stages off verify produced zero annotations; with them on,
> 3 / 7 / 4 per 18 queries. Whether those warnings were *right* was
> invisible.
>
> **What**: `eval/qvt/annotation_axis.py` scores each `annotate` as a
> claim ("this answer is not supported") against fixture labels that
> existed before verify was touched. `scripts/research/score_annotations.py`
> reads any audit-log window and applies it. Read-only; no server.
>
> Not a sixth canonical axis — `score_five_axis` and the
> `baseline_<sha>.json` schema are untouched. Reported alongside.

## 1. Design — no new gold

Scoring a component with a yardstick built for the purpose is
`feedback_self_evaluation_trap`. So correctness comes only from what the
fixture already carried, through the oracle's own unchanged functions
(`detect_abstention`, `score_graded_answer`):

| truth | system | correctness |
|---|---|---|
| absent | answered | **wrong** |
| absent | refused | **right** |
| present | refused | **wrong** |
| present | answered | *unscored* (strict) · right if graded = 1.0 (graded mode) |

`wrong + annotated` = true alarm · `wrong + silent` = miss ·
`right + annotated` = false alarm · `right + silent` = correct silence.

Classification runs on the answer **with verify's note stripped**, so
verify's own output cannot change the verdict it is scored against.
Measured before building it: across 22 step7 bench files, 11 answers had
a note inside the oracle's 300-character preview and **0** flipped the
abstention verdict — but the axis does not rely on that staying zero,
and a test pins the case where it would.

## 2. First run, and the design defect it exposed

Applied to the 2026-09-27 n=3 arms and the bare-claim sample:

| window | mode | annotated | P | R | TA | FA | miss |
|---|---|---:|---:|---:|---:|---:|---:|
| ON (3 runs, 54 ep.) | graded | 14 | 0.30 | 0.33 | 3 | **7** | 6 |
| ON | **strict** | 14 | **1.00** | 0.33 | 3 | 0 | 6 |
| OFF (3 runs, 54 ep.) | either | 0 | — | **0.00** | 0 | 0 | 8 |
| bare-claim (30 ep.) | either | 4 | 1.00 | 0.50 | 4 | 0 | 4 |

Graded mode said **70% of verify's warnings were false alarms**. That
was not taken at face value; every one of those warnings was read, with
the claims verify actually listed pulled from its fact-check row.

They split into two kinds.

**Correct warnings the axis mis-scored** — verify flagged claims the
evidence does not carry, bolted onto an otherwise correct answer:

- "RAG가 무엇인가?" ×2 — unrequested access-control and attack-surface
  advice: *"검색 단계에서 사용자 권한 기반의 접근 제어 메커니즘을
  구현해야 합니다"*
- BlackRock ×1 — editorial: *"… 핵심적인 '구조적 다리(Structural
  Bridge)' 역할을 한다는 점이 가장 중요합니다"*

The answers hit every gold signal, so graded = 1.0 and the axis called
them *right*. **graded = 1.0 means "contains the answer", not "contains
nothing else."** That is the blind spot, and it cannot be closed without
claim-level gold, which the axis refuses to invent.

**Genuine false alarms** — verify flagged the *correct core answer*:

- "BTC와 비트코인은 같은 것인가?" ×3 — *"BTC와 비트코인은 같은 디지털
  자산을 지칭한다"*, *"BTC는 … 표준 약어(Ticker Symbol)이다"*
- "Anthropic과 Claude의 관계" ×2 — *"Anthropic … develops, owns, and
  provides the Claude AI models"*

The user receives a correct answer with *"(검증: 다음 주장이 자료에 직접
지지되지 않음: BTC와 비트코인은 같은 디지털 자산을 지칭한다)"* attached.

**Hence two modes.** Strict (the default) decides correctness by
abstention alone and never consults graded; it is reliable where it
scores, and blind to the genuine false alarms above because those sit on
answered truth=present queries. Graded sees them and also mis-scores the
embellishment catches. Neither alone is the truth, and the report of
either should say which it is.

## 3. What the axis does establish

**verify has a measurable effect the five axes could not see.** Both
modes agree:

- **ON flags 3 of 9 wrong answers. OFF flags 0 of 8.** That is the
  contribution the n=3 contrast reported as "flat".
- **Where correctness is unambiguous, verify raised no false alarm**
  (strict P = 1.00, across 11 + 10 scored episodes).
- On the bare-entity shape it is precise but catches half (P 1.00,
  R 0.50) — consistent with 2026-09-27's four correct "Alex Karp"
  flags.

## 4. A product defect this surfaced

`FACT_CHECK_PROMPT_*` already states the rule:

> General common knowledge (e.g., 'AI is a technology') passes even
> without data support

The fact-check model is not applying it. "BTC = Bitcoin" and "Anthropic
develops Claude" are the textbook case, and both were flagged as
unsupported, 5 times across 3 runs. A correct answer carrying a note
that says its central claim is unsupported is worse than no note: it
teaches the user to distrust verify's warnings, including the correct
ones.

This is a finding, not a fix — the fix touches `core/reasoning/verify`,
needs rule #2 measurement, and would be judged on exactly this axis.

## 5. What this licenses — and what it does not

**Licensed**

- verify contributes something measurable: 3 of 9 wrong answers
  flagged with the stages on, 0 with them off.
- verify's fact-check produces false alarms on common-knowledge core
  answers despite its own prompt rule (§4).
- The axis, used in strict mode, gives a reliable lower-bound read of
  verify's precision; graded mode gives a noisy upper bound on false
  alarms. Neither is the true precision.

**Not licensed**

- ❌ "verify's precision is 1.00" — strict mode only scores 11 of 54
  episodes, and the genuine false alarms are in the other 43.
- ❌ "verify's precision is 0.30" — 3 of those 7 "false alarms" were
  correct warnings.
- ❌ Folding this into `score_five_axis` or any baseline. That changes
  what every stored baseline means.
- ❌ A recall claim from n = 9 wrong answers. It says "not zero", not
  "one third".

## 6. Follow-ups

1. **Fix the fact-check's common-knowledge exemption** (§4) — measured
   on this axis, graded mode, where the false alarms are visible.
2. **Claim-level gold for a small set** would close the graded blind
   spot. Only if built by someone other than the author of verify's
   changes, or it re-enters the self-evaluation trap.
3. The reflect-off n=3 is scored with this axis in
   `reflect-off-n3-20260928.md` §4 — verify kept its precision with
   reflect off (strict P = 1.00 in both arms) and lost some recall
   (5/9 → 3/10, small counts).
