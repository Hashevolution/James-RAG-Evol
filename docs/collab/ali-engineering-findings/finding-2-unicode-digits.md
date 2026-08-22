# 발견 ② — JS `\d` ASCII 전용 · 결과 보고 초안

**상태**: DRAFT. 발송 전 운영자 확인.
**순서**: 4통 중 **2번째**. 지금 발송 가능 (측정 완료).
**판정**: **재현** — 단, 넷 중 가장 작고 안전성 결함이 아님.
**근거**: commit `a9d96f4` (PR #1079) · `frontend/static/chat.js`
4개소 6개 리터럴 (2095 / 2156-2158 / 2233 / 2970) ·
node v22 실동작 6케이스 + `tests/test_chat_ux_n4_n5.py`.

## 이 통의 설계

- **크기를 부풀리지 않는다.** 렌더링 결함이지 보안 결함이 아니다.
  Ali 는 "slow measured answer" 를 요구했다 — 작은 건 작다고 쓴다.
- ②는 JS 언어 차원 사실이라 유일하게 그의 스택에도 검증 가능한
  형태로 언급 가능. 그래도 단정하지 않고 확인 가능한 사실만 적는다.

## 넣지 않은 것

- 그의 렌더러가 같은 문제를 갖고 있으리라는 추정.
- 다른 3건 언급.

---

Ali,

Second of the four.

**Reproduced**, and it was exactly the language-level fact you named:
JavaScript's `\d` is `[0-9]` and nothing else. A reply enumerated in
Arabic-Indic digits was invisible to six regex literals across four
places in our chat renderer: the truncation heuristic, the three
enumerated forms our next-step chip extractor recognises, a fourth
pattern built as a string that strips an enumerated line out of the
answer body once it has been lifted into a chip, and the markdown
ordered-list renderer.

The reply itself was always fine; the interface simply could not see
that it had structure. Numbered steps rendered as one undifferentiated
block, and a reply that broke off mid-enumeration was never flagged as
cut off. The four had to move together — fixing the extractor alone
would have made every Arabic-Indic suggestion appear twice, once as a
chip and once still sitting in the prose, because the pass that removes
the duplicate recognises the same enumerator forms.

They now carry an explicit class covering ASCII, Arabic-Indic and
extended Arabic-Indic. Not `\p{Nd}`, which would have been the tidier
spelling: one of our tests lifts those regex literals out of the JS and
recompiles them in Python, and Python's `re` rejects `\p` outright. So
the class is written out, and both engines were checked against it
rather than assumed.

Our own internal markers stayed ASCII-only on purpose — we emit those
ourselves and they never come from a model, so widening them would only
create new ways for model output to collide with our sentinels.

I want to be accurate about the size of this one: it is a rendering
defect, not a safety one, and it is the smallest of the four. It is
still worth having, because a user reading a reply in their own digits
was getting a visibly worse interface than a user reading the same reply
in ASCII, and nothing in our tests would ever have said so.

— Jiwon Seo
Hashevolution / PROJECT JAMES
ORCID 0009-0002-0007-7860
