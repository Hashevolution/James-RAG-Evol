# Ali 엔지니어링 4건 — ①/4 bidi override span

**상태**: DRAFT. 발송 전 운영자 확인.
**성격**: 1차·3차 답장이 약속한 *"in its own message"* 이행분 1/4.
**전제**: 3차 답장(기탁 발행 확인)이 이미 나갔다는 가정.
**Ali 번호**: 그의 첫 번째 항목 (커밋 `e19f239` 이 인용한 원문 표현).
**발송 가능**: **지금.** 재현 · 수정 · 회귀 테스트 모두 끝남.

## 발송 전 확인

- PR #1079 머지 여부. 아직 열려 있으면 커밋 SHA 대신 PR 번호로만 지칭
  하거나, 코드 참조 없이 서술만 보낸다 (현행 초안은 코드 참조 없음).

## 넣지 않은 것

- 나머지 3건. 건당 1통 원칙 — ②③은 별도 파일, ④는 재측정 대기.
- 모듈 docstring 이 참조하는 `reports/research-runs/bidi-normalization-
  audit-20260602.md` 부재 건: 우리 집안일.

---

Ali,

Four messages, one per finding, in your numbering. The first three are
measured, and follow over the next three. The fourth reproduced as a
mechanism, but the measurement it invalidates has not been re-run yet,
so it comes when there is a number rather than now.

**Your first finding — the bidi gate. Reproduced.**

Our gate stripped the bidi control characters and left the text they had
reordered. So the characters that raise the flag disappeared and the
concealed instruction arrived at the model as ordinary cleartext: we
were removing the evidence of the attack and forwarding the attack,
which is worse than not filtering at all. Worth saying plainly that the
span-removal recommendation was already in your Track 2c report — the
weaker version was our implementation choice, not a gap in your advice.

The fix splits the treatment by what each control actually does. The
overrides, LRO and RLO, now take their whole span: opener, contents and
terminating PDF together, to the matching PDF or to end of input if
unterminated, with depth tracking so an inner embedding's PDF cannot
close an outer override. An override forces direction regardless of the
characters' own properties, which is the concealment primitive itself,
and it has no legitimate use inside a user's question. Everything else
keeps its contents: embeddings and isolates are how legitimate
bidirectional text carries a directional run — an English product name
inside an Arabic sentence — and deleting their contents would destroy
real input.

This is deliberately destructive, and your own bidi_04 case shows what
it costs. Three per-digit RLO spans mean the spoofed "120" is removed
rather than mis-parsed. I take that as the safer failure: a validator
that sees no number asks again, one that sees the wrong number does not.
Both counts land in the audit record — spans removed and characters
dropped — so a stripped attack stays visible in the log instead of
becoming a silent no-op, and the existing caller-side gate keeps firing
on the same field it always did.

Regression coverage went 29 to 35 tests. Your four cases are rewritten
against the new contract: bidi_01 and bidi_03 now assert the concealed
instruction is *absent*, which is the whole point of the change, and
bidi_02's LRE-wrapped digits still survive. Clean multilingual input is
byte-identical through the gate. The adversarial fixtures themselves are
untouched — the runner still must not normalise, since the
fixture-to-server boundary is what those cases exist to test.

This one was a live security defect and we had been shipping it.

— Jiwon Seo
Hashevolution / PROJECT JAMES
ORCID 0009-0002-0007-7860
