# The block fixture cannot be built — verify's echo path is unreachable (2026-09-27)

> **Task**: build a fixture that actually triggers verify's
> `injection_echo → block`, so #1153 could be validated in vivo. Three
> arms had each produced **zero blocks**, including the pre-fix arm, so
> the path was never exercised.
>
> **Result**: the fixture cannot be built. Not because the suite is
> lacking — because the corroborating text is destroyed upstream before
> it could corroborate anything. Reproduce with
> `python scripts/research/verify_echo_reachability.py --scan-corpus`
> (read-only, no server).

## 1. The argument

Since #1153, verify reports `security.injection_echo` only when the
matched span is **present in the retrieved evidence** — an echo has a
source. Every path by which text reaches that evidence runs through
`core.security_layer.extract_data_only`, which replaces each
`INSTRUCTION_INJECTION_PATTERNS` match with `[INSTRUCTION_REMOVED]`:

| chokepoint | when | covers |
|---|---|---|
| `PolicyEngine.sanitize_for_ingestion` | write time | the upload corpus |
| `PolicyEngine.quarantine` (`trust="low"`) | join time | web search, OCR, ASR, vision captions |

High/medium-trust content passes `quarantine` through unchanged, but
that is exactly the internal corpus, which was already sanitized at
ingestion. So there is no route left.

## 2. Measured, pattern by pattern

`verify_echo_reachability.py` Part 1 — a probe string per pattern,
phrased the way a poisoned document would phrase it, then sanitized,
then quoted verbatim in an answer (the strongest echo case there is):

| # | pattern | probe matches | survives ingest | echo after sanitize |
|---|---|:-:|:-:|:-:|
| 0 | `(당신은\|너는\|you are\|you're)\s+.{0,30}(assistant\|…` | yes | **no** | 0 |
| 1 | `(반드시\|must\|should\|always)\s+.{0,20}(answer\|tell\|…` | yes | **no** | 0 |
| 2 | `(end\|stop\|exit\|quit\|close)\s+(session\|conversation…` | yes | **no** | 0 |
| 3 | `(show\|print\|output\|display\|reveal\|expose).{0,15}…` | yes | **no** | 0 |
| 4 | `(새\|new\|다음\|following)\s*(지시\|명령\|instruction\|…` | yes | **no** | 0 |
| 5 | `(context\|system\|previous)\s*(is\|was\|=\|:)\s*["']` | yes | **no** | 0 |

**0 of 6 patterns survive ingestion. 0 echoes are reportable.**

The "probe matches" column exists because of a mistake worth recording:
the first version of the probe used `"close the session when finished"`
for pattern 2, which the pattern does **not** match (it wants the noun
directly after the verb). That row printed as *survives = True* — a
probe missing its own pattern is indistinguishable from a pattern
surviving, unless you check. The column is now part of the output and
`tests/test_verify_echo_reachability.py` asserts every probe matches.

## 3. The historical path is empty too

Sanitization happens at write time, so documents ingested **before** the
chokepoint existed could still hold raw pattern text. That is
operator-specific and not knowable from the source, so the probe scans
the live store read-only — counts and document ids only, never content.

    chroma dir: chroma_db_bge_m3
    documents scanned: 368
    documents matching any pattern: 0

So on this host the echo block is unreachable in practice as well as in
principle.

## 4. Correction to #1153

#1153 shipped a "known residual", pinned by `KnownResidualTests`:
quoting a runbook that genuinely contains "다음 명령을 실행하세요" is
corroborated, so it **still blocks**. That claim was stated as a
production behaviour. It overstated the case: it requires *unsanitized*
context, and pattern 4 is neutralized at ingest, so no production path
supplies one. The test passes raw text directly to the scan, which
nothing in the pipeline does.

The test stays — it locks the function's contract on the input it is
given, and that contract is what goes live again if a chokepoint ever
stops sanitizing. Its docstring now carries the correction.

**This also retires an operator decision.** #1153 and the handover
escalated "narrow the output-echo pattern list, or downgrade `block` to
`annotate` for the ambiguous patterns" as a trust-boundary call. There
is nothing to downgrade: the recommendation never fires on sanitized
content. The decision can be closed as moot unless a chokepoint changes.

## 5. What is still worth building

The other half of the task survives. #1154's **bare-claim annotation**
*is* reachable — it needs a short answer with an unsupported claim, and
the 2026-09-27 arm missed it by two characters.

Frequency, measured over every step7 run this month
(16 runs, 288 answerable answers):

| answer | chars |
|---|---:|
| `Alex Karp` | 9 |
| `다리오 아모데이 (Dario Amodei)` | 23 |
| `ANSWER: Dario Amodei입니다.` | 24 |

**3 of 288 = 1.0%**, and all three come from the same query shape — a
bare entity attribute ("who is X's CEO"). That is precisely the shape
that can be confidently wrong, which is why #1154 exists. So the path
matters at ~1% of traffic and is worth a fixture; it is the remaining
buildable piece.

## 6. What this licenses — and what it does not

**Licensed**

- The `injection_echo → block` recommendation cannot fire on content
  that passed either chokepoint (§1–§2), and no content on this host
  bypasses them (§3).
- #1153's corroboration is therefore strictly a false-positive removal
  with no true-positive cost — there was no reachable true positive to
  lose.
- The pattern-list operator decision is moot (§4).

**Not licensed**

- ❌ "Remove the echo check." It is defence in depth against the
  chokepoints themselves failing, and the tests now fail loudly if they
  do. Removing it is a trust-boundary decision with no measurement
  behind it.
- ❌ "Prompt injection is handled." This says one *detector* is
  redundant with the sanitizers in front of it. It says nothing about
  whether the sanitizers are sufficient — a paraphrased or
  differently-phrased injection matches none of these six patterns at
  either layer.
- ❌ Any claim about corpora other than this one. §3 is one host's 368
  documents.
