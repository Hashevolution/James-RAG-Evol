# Ali 4차 답장 초안 — 엔지니어링 4건 결과 보고

**상태**: DRAFT. 발송 전 운영자 확인.
**성격**: 1차 답장에서 약속한 "측정 끝나면 별도 메시지" 이행분.
**전제**: 3차 답장(발행 확인)이 이미 나갔다는 가정. 아직이면 3차 먼저.

## 이 초안의 설계 원칙

1. **재현 여부를 먼저, 수정 내용을 나중에.** 그가 준 건 발견이지 패치
   요청이 아니다. 각 항목은 "우리 쪽에서 재현됐다 / 안 됐다"로 연다.
2. **④는 정직하게 미완으로 둔다.** 메커니즘은 확인·시연했지만 Track 2c
   재측정은 라이브 서버 + Ollama 필요 → 운영자 게이트. 숫자를 재확인해
   주지 않는다. 1차 답장이 "측정된 것만 말한다"고 약속한 그 기준.
3. **그의 스택으로 일반화하지 않는다.** 우리가 뭘 고쳤는지만 말하고,
   그쪽에서도 그렇다는 추정은 하지 않는다. 단 ②의 `\d` 건은 JS 언어
   차원 사실이라 확인 가능한 형태로만 언급.
4. **새 의무를 만들지 않는다.** 답장을 요구하는 문장은 넣지 않는다.

## 발송 전 확인 사항

- PR #1079 머지 여부. 아직 열려 있으면 커밋 SHA 대신 PR 번호로만 지칭.
- ④의 `sqlite3` 점검(운영자 로컬 머신)을 돌렸다면, 그 결과를 마지막
  문단에 한 줄 반영할 수 있음. 안 돌렸으면 현행 문장 유지.

## 넣지 않은 것

- LRB-S2 재현 실패: 무관한 JAMES 내부 사안.
- `ATTACK_PATTERNS` 에 아랍어 패턴 없음: 진짜 갭이지만 정규화 수정이
  아니라 정책 변경. 여기서 꺼내면 그가 답할 게 생긴다.
- 남은 ~82 테스트 실패: 우리 집안일.

---

Ali,

Here is what your four findings did on our side. Three reproduced as
live defects. The fourth reproduced as a mechanism but the measurement
it invalidates has not been re-run yet, so I am reporting it as
unfinished rather than closed.

**1. The bidi gate.** Reproduced. Our input gate stripped the bidi
control characters and left the text they had reordered — so the
characters that raise the flag disappeared and the payload survived,
which is worse than not filtering at all. It now removes the whole
override span up to its matching PDF, with depth tracking so nested
embeddings inside an override do not terminate it early. Overrides
(LRO/RLO) are treated as spans; embeddings and isolates are not, since
those do not force a character-level reversal. The audit record gained
two counters — spans removed and characters dropped — so a stripped
attack stays visible in the log rather than becoming a silent no-op.

**2. Arabic orthographic variants.** Reproduced. We were applying NFC,
which by construction leaves tatweel and the Presentation Forms blocks
alone, so the same word in three spellings was three different strings
to the matcher. The gate now removes tatweel and applies NFKC to
U+FB50–FDFF and U+FE70–FEFF only. Deliberately narrow: global NFKC
would fold things we need to keep distinct, and we pinned that with a
test asserting NFKC is *not* applied outside those ranges, plus one
asserting letters are not folded into each other. Separately, the
scorer that decides whether a fixture's expected phrase appears in an
answer now does a tolerant fold of its own — harakat, the alef family,
alef maqsura, ta marbuta — because a correct answer spelled differently was
scoring as a miss, which is a measurement bug rather than a runtime one.

**3. Unicode digits in the renderer.** Reproduced, and it was exactly
the language-level fact you named: JavaScript's `\d` is ASCII-only, so
a reply enumerated in Arabic-Indic digits was invisible to four
patterns in our chat renderer — truncation detection, two enumerated
list parsers and the markdown ordered-list rendering. They now carry an
explicit class covering ASCII, Arabic-Indic and extended Arabic-Indic.
Not `\p{Nd}`: one of our tests lifts those regex literals out of the JS
and recompiles them in Python, which rejects `\p`. Our own internal
markers stayed ASCII-only on purpose — we emit those ourselves, they
never come from a model.

**4. Salted run identities.** The mechanism reproduced, the
re-measurement has not run. Three lines make it harmful here: our query
route defaults a missing session id to the literal string `default`,
the reasoning engine injects that session's last five turns into the
prompt, and every answered turn is written back. So our eighteen-case
sweep, which sent no session key at all, ran as eighteen turns of one
conversation — each case answered with the five cases before it sitting
in its prompt. The sweep
runner now mints a per-case key salted with a random value per process,
so a re-run cannot rejoin an earlier one, and the key is recorded in the
run JSON so it can be traced against the audit log. There is a test that
demonstrates the bleed directly against a temporary store rather than
just asserting the keys differ.

What I am *not* doing is re-confirming the Track 2c numbers I sent you.
That table reported one case where a verdict slipped between runs, and I
put it down to single-run noise at N=1. Order contamination is now a
live alternative explanation for it, and the honest position is that no
figure in that table is re-confirmed until the suite runs again from
clean history. That needs a live server plus a local model, so it is
queued rather than done.

Three other measurement paths in our repo have the same shape you
described — stable, human-readable keys that silently rejoin across
runs. One of them is the bench that gates every change to our retrieval
and reasoning code, so salting it means re-baselining, and I have left
that as a deliberate decision rather than a mechanical fix. Whether any
published number was actually affected depends on whether the machine
that produced it carried prior turns in its local store, which is a
single query against a database that is not in the repository.

The one thing worth taking back to your stack from this: it was not the
missing key that hurt, it was the key being *found* rather than
*created*. A stack that silently find-or-creates on a readable name will
do this to anyone who labels their runs the way a human would.

Thanks for all four. The first one was a real security defect and we had
been shipping it.

— Jiwon Seo
Hashevolution / PROJECT JAMES
ORCID 0009-0002-0007-7860
