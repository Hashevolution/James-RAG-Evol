# 발견 ④ — salted run identity · 결과 보고 초안

**상태**: DRAFT — **아직 발송 불가.**
**순서**: 4통 중 **4번째, 마지막**.
**차단 사유**: Track 2c 재측정 미실행. 라이브 JAMES 서버 + Ollama 필요
= 운영자 게이트. 본문의 `[측정 결과]` 슬롯이 비어 있는 채로는 보내지
않는다 — 1차 답장이 "측정된 것만 말한다"고 약속했고, Ali 4차가
*"a slow measured answer over a fast impression"* 으로 재확인했다.
**판정(현재)**: 메커니즘 **재현**, 수치 **미측정**.
**근거**: PR #1079 (2026-08-26 main 병합, squash `6d6a079`) ·
`reports/research-runs/track-2c-run-identity-contamination-20260819.md` ·
`tests/test_sweep_run_identity.py` 11 passed ·
**표 해석 한계 = `reports/research-runs/arabic-pipeline-capability-audit-20260822.md` §7**.

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

> ⚠️ **미완성 — 이 블록이 남아 있는 채로 발송 금지.**
>
> 운영자 머신(라이브 서버 + Ollama)에서 **한 명령**:
> ```
> python scripts/research/track2c_remeasure.py --yes
> ```
> 스크립트가 [5]단계에서 여기 붙일 텍스트를 그대로 출력한다.
> 그 출력으로 이 블록을 교체하고 위 굵은 문장을 확정할 것.
>
> **옛 표와 비교하지 않는다.** 표는 2026-06-23 이고 그 뒤 `core/` 19
> 커밋이 들어갔다 — 판정 변화가 salt 때문인지 drift 때문인지 구분
> 불가. 스크립트는 대신 **같은 빌드에서 A(공유 키) / B(salt) 두 arm**
> 을 돌려 A↔B 차이를 측정한다. 그게 유일하게 깨끗한 비교다.
>
> 사전에 안전하게 볼 수 있는 것: `--preflight-only` (환경 점검),
> `--evidence-only` (**이력 삭제 전** 누적 증거 캡처, 아무것도 안 바꿈).
>
> **변화가 없으면 없다고 쓴다.** 스크립트가 그 문구를 만들어 준다.

Three lines make a shared conversation key harmful here. Our query route
defaults a missing session id to the literal string `default`. The
reasoning engine injects that session's last five turns into the prompt.
Every answered turn is written back. And the memory build runs ahead of
the mode dispatch, so this reaches the retrieval path too, not just
chat. None of that is wrong on its own — together it is a perfectly
reasonable chat feature — which is exactly why the consequence for
measurement went unnoticed as long as it did.

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

A word on how that re-run is built, because the obvious version of it
does not work.

The obvious version is: re-run the suite now and diff against the table
I sent you. It cannot answer the question. That table was written in
late June, and something like nineteen commits to our reasoning and
retrieval code have landed since. Any verdict that moved would be
confounded by two months of drift, and any verdict that held would
prove nothing either — and the third finding's scorer fix has landed in
the meantime, confounding it again.

So it runs paired instead, both arms on the same build: one arm where
every case shares a conversation key, which is the old behaviour
reproduced deliberately, and one arm with the salted per-case keys.
Same build, same fixture, same model, history wiped before each arm.
Everything that would otherwise confound — the drift, the scorer fix,
even our language misclassification — is present in both arms and
cancels. What is left between them is the contamination effect itself,
measured rather than argued. Whatever it says is what I will send you,
including "it moved nothing", which is a live possibility I would
rather name in advance than explain away afterwards.

The second is about what the table can be read for, and it is the one
that would change how you use it. As I said in the third message, our
pipeline has no Arabic classification: script that scores zero on both
of our counters falls through to the Korean branch, and a few Latin
characters flip it to English. I ran the eighteen cases through that
classifier to see what it actually did to them. Twelve came out Korean
and six English — and the split does not follow the fixture's own
language labels. Six `ar-LV` cases split five/one. Three `msa` cases
split two/one. So cases carrying the same language label were answered
under different prompt scaffolding, decided by how many Latin
characters happened to be in them.

For the re-run itself that is harmless: the text does not change, so the
classification does not change, and it cannot mask the salt effect —
it is a constant, not a variable. Where it does bite is comparison
*across* rows. A difference between two cases in that table may be a
difference in scaffolding rather than in anything either of us set out
to measure, and I would not want you drawing a language-family
conclusion from it. That is not a contamination I can fix by re-running;
it is a limit on what the table was ever measuring.

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
