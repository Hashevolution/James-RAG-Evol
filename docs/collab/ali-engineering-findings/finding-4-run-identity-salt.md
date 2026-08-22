# 발견 ④ — salted run identity · 결과 보고 초안

**상태**: DRAFT — **아직 발송 불가.**
**순서**: 4통 중 **4번째, 마지막**.
**차단 사유**: Track 2c 재측정 미실행. 라이브 JAMES 서버 + Ollama 필요
= 운영자 게이트. 본문의 `[측정 결과]` 슬롯이 비어 있는 채로는 보내지
않는다 — 1차 답장이 "측정된 것만 말한다"고 약속했고, Ali 4차가
*"a slow measured answer over a fast impression"* 으로 재확인했다.
**판정(현재)**: 메커니즘 **재현**, 수치 **미측정**.
**근거**: commit `dace68f` (PR #1079) ·
`reports/research-runs/track-2c-run-identity-contamination-20260819.md` ·
`tests/test_sweep_run_identity.py` 11 passed.

## 발송 전 실행해야 할 것 (운영자)

```bash
# 1. 이력 초기화 — 오염의 원인이 누적된 대화이므로 반드시 선행
sqlite3 memory/james_memory.db "DELETE FROM conversation_history;"
# 2. salt 적용된 스윕 재실행
python scripts/adversarial_sweep.py --fixture eval/adversarial/ar_ecommerce-v1.1-james.yaml
# 3. eval/adversarial/ar_ecommerce-cross-stack-comparison.md §2 표와 대조
```

추가로, 보낸 수치가 실제로 오염됐는지 판정하는 단일 질의:

```bash
sqlite3 memory/james_memory.db \
  "SELECT session_id, COUNT(*) turns FROM conversation_history
    GROUP BY session_id HAVING turns > 2 ORDER BY turns DESC LIMIT 40;"
```

`default` 행이 크면 Track 2c 스윕이 거기 누적된 것. 2턴 초과 행이 없으면
노출은 잠재적이었고 수정은 순수 예방.

## 이 통의 설계

- Ali 가 **가장 불확실해하는 항목**이라고 명시했고 *"whatever it says,
  it tells me something"* 이라고 선약했다. → 결과가 우리에게 불리해도
  그대로 보낸다. 유리한 결과만 보내면 그 선약을 배신하는 것.
- ③의 스코어러 위양성과 **같은 재실행이 둘 다 해소**한다. 재실행 결과는
  두 원인이 섞여 있으므로, 변화가 관측되면 **어느 쪽 탓인지 분리해서
  쓸 수 없다** — 그 한계도 본문에 적었다.

## 넣지 않은 것

- 재측정 전 Track 2c 표 수치의 재확인. 절대 금지.
- `bench.py` salt 여부 = 운영자 결정. 결정 사실만 적고 권고하지 않는다.

---

Ali,

Last of the four, and the one you said you were least certain about on
your own numbers.

**The mechanism reproduced. The measurement it invalidates has now been
re-run, and here is what it said.**
> ⚠️ 위 문장은 **재실행이 실제로 끝난 뒤에만** 참이다. 아래 블록과 함께
> 확정할 것.

> ⚠️ **[측정 결과 — 재실행 후 이 블록을 채우고 위 문장을 확정할 것]**
> - 재실행 일시 / 이력 초기화 여부
> - 케이스별 판정 변화: 변화 없음 / N건 변화 (어느 케이스, 어느 방향)
> - `bidi_02` 의 슬립이 재현되는가
> - `sqlite3` 점검 결과 = 과거 실행이 실제로 누적됐는지
>
> 변화가 **없으면** 그렇게 쓴다. 우리에게 불리한 결과여도 그대로 쓴다.
> 이 블록이 비어 있는 채로 발송 금지.

Three lines make a shared conversation key harmful here. Our query route
defaults a missing session id to the literal string `default`. The
reasoning engine injects that session's last five turns into the prompt.
Every answered turn is written back. And the memory build runs before
the mode dispatch, so this reaches the retrieval path too, not just
chat. Our own code comment already described the outcome in as many
words — *"prior turns mixed back into the prompt → new answer looks
identical to the previous"* — which is the part I find least comfortable:
the failure was documented in our source and still shipped.

Our eighteen-case sweep sent no session key at all, so it ran as
eighteen turns of one conversation, each case answered with the five
before it sitting in its prompt. The runner now mints a per-case key
salted with a random value drawn once per process, so a re-run cannot
rejoin an earlier one, and the key is recorded in the run JSON so it can
be traced against the audit log. There is a test that demonstrates the
bleed directly against a temporary store rather than only asserting that
the keys differ.

Surveying the rest turned your finding out wider than the one suite.
Three other measurement paths use exactly the shape you described —
stable, human-readable keys that silently rejoin across runs. One of
them is the bench that gates every change to our retrieval and reasoning
code. Salting it changes the conditions under which future numbers are
produced, so they stop being comparable to the baselines they are
measured against; that is a re-baselining decision and I have left it as
one rather than making it quietly.

One limit on the re-run above, which I would rather state than have you
infer. The third finding independently broke the same scorer — a
forbidden phrase in variant Arabic spelling scored as a clean resist —
and it is fixed in the same branch. So the re-run clears both faults at
once, and if a verdict moves I cannot attribute the movement to
contamination rather than to scoring. Separating them would need a run
with one fix and not the other. I have not done that, and my own read is
that it does not earn the cycles unless the re-run actually moves a
verdict — but you are welcome to think otherwise.

The one thing worth taking back to your stack: it was not the missing
key that hurt, it was the key being *found* rather than *created*. A
stack that silently find-or-creates on a readable name does this to
anyone who labels their runs the way a human would — which is to say, to
anyone doing it carefully.

That is all four. The first was a real security defect we had been
shipping, the third was half a non-reproduction, and this one cost us a
table. Thank you for all of them.

— Jiwon Seo
Hashevolution / PROJECT JAMES
ORCID 0009-0002-0007-7860
