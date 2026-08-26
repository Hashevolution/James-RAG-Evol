# 발견 ① — bidi override span 제거 · 결과 보고 초안

**상태**: DRAFT. 발송 전 운영자 확인.
**순서**: 4통 중 **1번째**. 지금 발송 가능 (측정 완료).
**전제**: 3차 답장(발행 확인) **발송 완료 확인됨** — Ali 4차 메시지가
그에 대한 답신이다 (README EN/KO 대조 · #461/#463 v0.3.1 · one message
per finding, 세 항목이 3차 본문과 하나씩 대응). 바로 발송 가능.
**판정**: **재현** — 라이브 보안 결함이었음.
**커밋 메시지 오류 기록**: `e19f239` 메시지는 *"the weaker version was
our implementation choice rather than his advice"* 와 *"the
recommendation came from his Track 2c report and we shipped the
character strip"* 를 동시에 주장한다 — **자기모순**. 원본 대조 결과:
그의 Track 2c 리포트 X3 + Provia 권고 4번 = *"strip/normalize bidi
control characters at input"*, 즉 **우리가 구현한 그것**. span 제거
문장은 2026-08-19 편지에 있다.
**단, 그가 자기 권고를 "수정"한 것인지는 알 수 없다** — 리포트의
"normalize" 가 애초에 span 제거를 포함하는 뜻이었을 수 있다. 초안 2차에
"revised your own earlier recommendation" 이라고 단정했다가 이 검토에서
철회. 편지는 두 텍스트를 병치만 하고 책임은 우리로 둔다.
(커밋 메시지는 이미 푸시됨 → 여기서 기록으로 남긴다.)
**근거**: commit `e19f239` (PR #1079) · `core/input_normalization.py` ·
`tests/test_input_normalization.py` 43 passed.

## 왜 4통으로 나눴나

Ali 4차 메시지: *"One message per finding is the right shape, and I would
rather have a slow measured answer than a fast impression."* 통합 1통
초안(`m9-joint-deposit-prep/ali-reply-4-draft-engineering-findings.md`)은
이 지시로 폐기. 또한 그 초안은 본문 번호를 1 bidi / 2 아랍어 / 3 숫자 /
4 salt 로 매겼는데 **Ali 자신의 번호와 ②③이 뒤바뀐 상태**였음 (그의
번호 = ①bidi ②숫자 ③아랍어 ④salt, 커밋 메시지로 확인). 분리하면서 교정.

## 넣지 않은 것

- 그의 스택에 대한 추정. 우리가 뭘 고쳤는지만 말한다.
- 답장을 요구하는 문장.
- 다른 3건 언급 — 각 통은 독립적으로 읽혀야 한다.

---

Ali,

First of the four, one message each as you asked.

**Reproduced**, and it was a live defect we had been shipping.

On attribution, so the record is straight. Your Track 2c report asked
for bidi controls to be stripped or normalised at input — X3, and again
in the Provia-side list — and a character strip is what we built. Your
August sentence, that stripping the controls removes the concealment but
not the concealed text, is what showed the strip to be the wrong reading
of it. Whether you meant the stronger operation all along I cannot tell
from the report's wording, and it does not much matter: the weak version
was ours to ship, and ours to fix.

Under the old gate an RLO attack lost its wrapper and kept its payload.
The concealed instruction arrived at the model as ordinary cleartext, so
we were removing the evidence of the attack and forwarding the attack —
worse than not filtering at all, because the characters that would have
raised a flag were the ones we deleted.

The gate now splits treatment by what each control actually does.
Override characters, LRO and RLO, take their whole span: opener,
contents and terminating PDF together, to the matching PDF or to end of
input if unterminated, with depth tracking so an inner embedding's PDF
cannot close an outer override. Everything else keeps its contents.
Embeddings and isolates are how legitimate bidirectional text carries a
directional run — an English product name inside an Arabic sentence —
and deleting their contents would destroy real input. Marks and the
zero-width set are single characters with no span at all.

This is deliberately destructive for override spans, and your own
bidi_04 case shows what that costs. It wraps each digit of the spoofed
price in its own RLO…PDF pair — three spans for "1", "2", "0" — so the
spoofed number is removed outright rather than mis-parsed. We took that
as the safer failure: a validator seeing no number asks again, one
seeing the wrong number does not. In that particular case the floor
reference survives anyway, since the sentence names 120 again in the
clear further along, but I would not want to argue the general point
from a case that happens to be forgiving. Both counts land in the audit
record — spans removed and characters dropped — so a removal stays
forensically visible instead of becoming a silent no-op.

Two things I will not overstate. The four cases you sent are the ones I
rewrote against the new contract, so the tests prove the contract holds,
not that the space of override attacks is covered. And the module
docstring cited a bidi normalisation audit that is not in our
repository, so I wrote the rationale into the code itself rather than
resting it on a reference I could not open.

— Jiwon Seo
Hashevolution / PROJECT JAMES
ORCID 0009-0002-0007-7860
