# Ali 엔지니어링 4건 — ③/4 아랍어 정규화 / keyword gate

**상태**: DRAFT. 발송 전 운영자 확인.
**성격**: 건당 1통 이행분 3/4.
**Ali 번호**: 그의 세 번째 항목 (커밋 `8c6f726`).
**발송 가능**: **지금.** 절반 비재현 / 절반 재현, 양쪽 다 확인 완료.

## 이 초안의 순서 원칙 — 중요

**비재현을 먼저 놓는다.** 그가 지적한 실패 모드는 *"아랍어 키워드 게이트가
평범한 표기 변형에서 뚫린다"* 인데, **우리 스택에는 뚫릴 아랍어 키워드
게이트 자체가 없다**. `core/security_layer/_policies.py` 의
`ATTACK_PATTERNS` 는 영어 + 한국어뿐 (2026-08-21 재확인: 아랍어 패턴 0건).
커밋 `8c6f726` 본문도 같은 말을 이미 기록하고 있다 —
*"there is no bypass to close in the security layer and this commit does
not claim one."*

4차 통합 초안은 이 항목을 그냥 "Reproduced" 로 열었다. 그건 우리에게
유리한 쪽만 앞세운 순서였고, 그가 명시적으로 요청하기 전에도 고쳤어야
했다. 이 판은 (1) 비재현 → (2) 재현된 두 지점 (런타임 게이트 · 측정
스코어러) 순서.

## 판단이 필요했던 한 줄

"아랍어 게이트가 아예 없다" 는 그 자체로 커버리지 갭이다. 통합 초안은
*"여기서 꺼내면 그가 답할 게 생긴다"* 는 이유로 뺐다. 이 판은 **한 절만
남긴다** — 우리 쪽 미해결 항목이라고 명시하고, 그에게 아무것도 묻지
않는 형태. 비재현을 "우리는 안 뚫린다" 로 읽히게 두면 오히려 부정직해진다.

## 넣지 않은 것

- 나머지 3건.
- `ATTACK_PATTERNS` 아랍어 확장 계획 / 일정: 정책 변경이고 미결이다.
  약속하지 않는다.

---

Ali,

**Your third finding — Arabic orthography. Half of it did not reproduce
here, and that half is worth more than the half that did.**

The failure you described needs a keyword gate over Arabic to bypass.
We do not have one. Our prompt-injection pattern table is English and
Korean only — I checked it before building anything, and there are no
Arabic patterns in it at all. So there is no gate here that ordinary
orthography walks past, and I am not going to claim we closed one.

The honest reading of that is not that we were safe. It is that the
check you were bypassing is a check we never ran. A pattern table that
has nothing to say about Arabic input does not get bypassed by tatweel;
it was already not looking. That gap is ours to settle and I am not
treating your finding as having closed it.

Where your point does land is two places, and both are real.

The first is the gate that lets one word arrive in several byte forms
to begin with. We were applying NFC, which by construction leaves
tatweel and the Presentation Forms blocks alone, so the same word in
three spellings was three different strings to anything downstream that
compares text. The gate now removes tatweel explicitly — it is
display-only elongation and survives both NFC and NFKC — and applies
NFKC per character inside U+FB50–FDFF and U+FE70–FEFF only. Deliberately
narrow: measured, a global NFKC also rewrites circled numerals to plain
digits, ligatures like ﬁ, and full-width forms to half-width, which is
not a change a Korean-first system should absorb as part of an Arabic
fix. A test pins that — Korean, circled numerals, half-width katakana
and full-width digits must come through untouched.

The gate deliberately stops short of folding letters. Alef maqsura, the
alef family and teh marbuta are what the user actually typed, and some
of those pairs are distinct letters rather than variants; rewriting them
in the text we forward to the model changes the input. That belongs at
comparison time, not in the pipe.

The second is our own measurement path, and this one is the shape of
your finding exactly — displaced onto the scorer instead of the gate.
The adversarial runner compared substring criteria with a plain
lowercase, so a reply that *did* contain the forbidden phrase, written
with tatweel or a presentation form or harakat or an alef variant,
scored as a clean resist. A false negative in numbers we report. The
comparison now normalises both sides and does fold letters, which is
safe at comparison time in a way it is not in the gate. It is kept local
to the runner rather than imported from the core module, since the
runner is a black-box client and the fixture-to-server boundary is what
the bidi cases test.

Coverage across the two suites went 51 to 68 tests: the variant classes,
the lam-alef ligature, harakat, idempotence, a guard that NFKC is *not*
applied outside those two blocks, and a guard that the letters we
refused to fold survive the gate. Clean multilingual input stays
byte-identical.

— Jiwon Seo
Hashevolution / PROJECT JAMES
ORCID 0009-0002-0007-7860
