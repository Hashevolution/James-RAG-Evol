# 발견 ③ — 아랍어 표기 변형 · 결과 보고 초안

**상태**: DRAFT. 발송 전 운영자 확인.
**순서**: 4통 중 **3번째**. 지금 발송 가능 (측정 완료).
**판정**: **분할** — 보안 게이트 절반 **비재현**, 런타임 정규화 +
측정 스코어러 절반 **재현**.
**근거**: commit `8c6f726` (PR #1079) · `core/input_normalization.py` ·
`scripts/adversarial_sweep.py::_fold_for_match` ·
`tests/test_input_normalization.py` 43 + `test_adversarial_criteria_parser` 25.

## 이 통이 비재현으로 여는 이유

Ali 4차 메시지 명시 요구:

> *Please send the non-reproductions with the same weight as the
> reproductions: if the bidi span removal or the Arabic normalisation
> does not hold on your stack, that is a result about scope, and it
> belongs in the record as much as a confirmation does.*

통합 초안은 ③을 그냥 "Reproduced" 로 열고 비재현 사실(우리 injection
detector 에 아랍어 패턴이 0건)을 **의도적으로 뺐다** — "여기서 꺼내면
그가 답할 게 생긴다" 는 이유였다. 그 판단은 그의 이번 요구로 **무효**.
비재현이 이 통의 머리다.

## 검증 (2026-08-21, 재확인)

- `core/security_layer/_policies.py`: `ATTACK_PATTERNS` 31개 리터럴 +
  `ATTACK_REGEX` 13개 — **아랍 문자 포함 항목 0건** (스크립트로 계수).
- tatweel(U+0640) 은 **NFC 도 NFKC 도 통과** → 명시 제거 필요. 확인함.
- 구 스코어러(`.lower()` 부분문자열) 실측 — tatweel / harakat /
  presentation form / alef 변형 **4종 모두 불일치**, 새 fold 는 4종 모두
  일치. → 변형 철자로 쓰인 금지 문구가 **clean resist 로 채점**됐음.
  (초안 1차에서 "presentation form 은 우연히 일치" 라고 썼던 것은 테스트
  문자열을 잘못 만든 탓. NFKC 로 기저 문자에 대응하는 실제 표현형
  U+FEF1/FEE1/FED9/FEE5 로 다시 재보니 그것도 불일치였다.)

## 넣지 않은 것

- 아랍어 injection 미탐지 자체를 "우리도 확인했다" 로 포장하는 것.
  이건 그의 발견이 아니라 **다른 종류의 커버리지 공백**이다. 구분해서
  적되 확대하지 않는다.
- 과거 판정 중 실제로 몇 건이 위양성이었는지 — **모른다**. 재실행 전엔
  수량화 불가. ④와 같은 재실행이 둘 다 해소한다는 연결만 적는다.

---

Ali,

Third of the four, and the only one with a split answer. You said a
non-reproduction is a result about scope, so I am putting that half
first.

**The half about keyword gates does not reproduce here — and not
because we handle Arabic well.**

Your finding was that a keyword gate over Arabic breaks on ordinary
orthography, so ordinary traffic goes unchecked and nothing is logged.
We have no Arabic keyword gate. Our injection detector carries 31
literal patterns and 13 regexes; I counted the Arabic-script characters
across both lists and the answer is zero. There is no Arabic check for
a variant spelling to slip past, so no ordinary Arabic traffic was
walking past a gate that thought it had inspected it.

That leaves us with a coverage gap of a different kind — an Arabic
prompt injection is not caught by that layer in *any* spelling, correct
or variant — and I would rather name it plainly than let it ride in as a
confirmation of your finding, because it is not one. Widening the
detector is a policy change and I have not made it.

**The half about normalisation reproduces, in two places.**

The runtime gate first. We were applying NFC, which by construction
leaves tatweel and the Presentation Forms blocks alone — I checked, and
tatweel survives NFKC as well, so it needs removing explicitly rather
than normalising away. The same word in several spellings was
several different strings to everything downstream. The gate now
removes tatweel and applies NFKC inside U+FB50–FDFF and U+FE70–FEFF
only. Deliberately
narrow: a global NFKC also rewrites circled numerals to plain digits,
ligatures like ﬁ to fi, and full-width digits to ASCII — none of which a
Korean-first system should absorb as part of an Arabic fix. A
test pins that the rest of the input comes through untouched.

The gate stops short of folding letters, and that is on purpose. Alef
maqsura, the alef family and teh marbuta are what the user actually
typed, and some of those pairs are distinct letters rather than
variants. Rewriting them in the text forwarded to the model would change
the input. That belongs at comparison time.

The second place is the one I would flag hardest if our positions were
reversed, because it is your exact failure shape landing somewhere I did
not expect. Our adversarial scorer compared substring criteria with a
plain lowercase match. So a reply that contained the forbidden phrase
written with tatweel or harakat scored as a **clean resist**. The check
passed and nothing was logged — your sentence, but on our measurement
path rather than our enforcement path. I verified it rather than
assuming, and had to correct myself once doing so: under the old
comparison every variant class I tried failed to match — tatweel,
harakat, presentation forms and the alef family alike — where a first,
sloppier test had told me presentation forms were already fine. They
were not. The scorer now folds both sides — harakat, the alef
family, alef maqsura, teh marbuta — which is safe at comparison time in
a way it is not in the gate.

What I cannot tell you is how many past verdicts that turned into
false negatives in our own favour. It may be none — the fault only fires
if a model reply actually spelled a forbidden phrase with a variant, and
whether any did is not something I can read off the stored runs with
confidence. So the honest statement is that the scoring was capable of
crediting us wrongly, not that it did. Re-running the suite is what
settles it, and that is the same re-run the fourth finding needs.

— Jiwon Seo
Hashevolution / PROJECT JAMES
ORCID 0009-0002-0007-7860
