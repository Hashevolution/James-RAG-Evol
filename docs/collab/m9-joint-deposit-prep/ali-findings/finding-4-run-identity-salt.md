# Ali 엔지니어링 4건 — ④/4 salted run identity

**상태**: DRAFT — **발송 보류**. 운영자 게이트.
**성격**: 건당 1통 이행분 4/4.
**Ali 번호**: 그의 네 번째 항목 (커밋 `dace68f`, 리포트
`reports/research-runs/track-2c-run-identity-contamination-20260819.md`).
**발송 가능**: **아직 아니다.** 메커니즘은 재현·시연·테스트 완료지만,
그것이 무효화한 **Track 2c 18-case 재측정이 안 돌았다.**

## 발송 차단 조건 — 2건 (둘 다 운영자)

1. **Track 2c 재측정.** 라이브 JAMES 서버 + Ollama 필요.
   ```bash
   sqlite3 memory/james_memory.db "DELETE FROM conversation_history;"
   python scripts/adversarial_sweep.py \
     --fixture eval/adversarial/ar_ecommerce-v1.1-james.yaml
   # 결과를 ar_ecommerce-cross-stack-comparison.md §2 표와 대조
   ```
2. **`sqlite3` 노출 점검** (운영자 로컬 머신). 리포트 §5 의 단일 쿼리.
   돌렸으면 마지막 문단을 결과로 교체, 안 돌렸으면 현행 문장 유지.

Ali 가 이 항목을 *"the one I am most uncertain about on my own numbers"*
라고 했고 결과가 무엇이든 받겠다고 선약했다. 그래서 이 통은 **늦게 가는
게 맞다.** ①②③을 여기 묶어 인질로 잡지 않는다 — 그게 4통 분해의 이유다.

## 발송 시 갱신할 것

- 재측정 결과가 표를 바꿨으면: 바뀐 셀 + bidi_02 각주 정정 여부.
- 안 바꿨으면: "표는 서 있다" 를 **재측정 근거로** 말한다. 지금 말하면
  안 되는 이유가 그것이다.
- 아래 초안의 4문단("What I am *not* doing…")은 **재측정 전 판**이다.
  재측정 후에는 이 문단을 결과로 교체한다.

## 넣지 않은 것

- V3′ / Direction 1 드라이버는 Ollama `/api/generate` 직결이라 세션도
  히스토리도 없다 → 공동 기탁의 7-tier 숫자는 무관. 1차 답장이 이미
  말했으므로 반복하지 않는다. (필요해지면 한 줄 추가.)

---

Ali,

**Your fourth finding — salted run identities. The mechanism reproduced.
The measurement it invalidates has not been re-run, so this is a report
of something unfinished rather than closed.**

Three lines make it harmful here. Our query route defaults a missing
session id to the literal string `default`, the reasoning engine injects
that session's last five turns into the prompt, and every answered turn
is written back. The memory build runs before the mode dispatch, so this
reaches the retrieval path and not only chat. Our eighteen-case
adversarial sweep sent no session key at all, so it ran as eighteen
turns of a single conversation: each case was answered with the five
cases before it sitting in its prompt. Our own engine carries a comment
that describes this failure in as many words; nobody had read it as a
measurement problem.

The runner now mints a per-case key salted with a random value drawn
once per process, so a re-run cannot rejoin an earlier one, and the key
is recorded in the run JSON so it can be traced against the audit log.
There is a test that demonstrates the bleed itself against a temporary
store rather than merely asserting that the keys differ — I did not want
a fix whose evidence was that two strings were unequal.

Surveying the rest turned your finding out wider than the sweep. Four
things in our repository post to that route. The other three all use
stable, human-readable keys that silently rejoin across runs. One of
them is the bench that gates every change to our retrieval, graph and
reasoning code, so salting it changes the conditions under which future
numbers are produced and implies a re-baseline against the stored
references. I have left those three deliberately unchanged and written
down why, as a decision rather than a backlog item.

What I am *not* doing in this message is re-confirming the Track 2c
numbers I sent you. That table reported one case where a verdict slipped
between runs, and I put it down to single-run noise at N=1. Order
contamination is now a live alternative explanation for exactly that
slip, and the honest position is that no figure in the table is
re-confirmed until the suite runs again from clean history. That needs a
live server plus a local model, so it is queued rather than done. You
said this was the finding you were least certain about on your own
numbers; I would rather answer it late than answer it from the run that
is now in question.

Whether any published number was actually affected turns on whether the
machine that produced it carried prior turns in its local store. That is
a single query against a database which is not in the repository, so it
is one command on the machine and not something a code review settles.

The part worth taking back to your stack: it was not the missing key
that hurt, it was the key being *found* rather than *created*. A stack
that silently find-or-creates on a readable name will do this to anyone
who labels their runs the way a human would.

That is all four. Two of them changed code we had been shipping, one of
them changed how we score our own runs, and this one changed what I am
willing to claim about numbers I had already sent you. Thanks for
spending the time on someone else's repository.

— Jiwon Seo
Hashevolution / PROJECT JAMES
ORCID 0009-0002-0007-7860
