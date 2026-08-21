# Ali 엔지니어링 4건 — ②/4 ASCII-only `\d`

**상태**: DRAFT. 발송 전 운영자 확인.
**성격**: 건당 1통 이행분 2/4.
**Ali 번호**: 그의 두 번째 항목 (커밋 `a9d96f4`).
**발송 가능**: **지금.** 재현 · 수정 · node v22 실동작 검증 완료.

## 이 초안의 순서 원칙

**비재현을 먼저.** 그가 찾은 자리(숫자 추출)에서는 우리 쪽이 재현되지
않는다 — Python `re` 의 `\d` 는 기본이 유니코드라 `١٢٠` 을 정상 추출하고
`int()` 도 120 으로 읽는다 (`scripts/adversarial_sweep.py:181,200` 확인,
실행 검증함). 같은 클래스의 결함은 **JS 렌더러**에서 났다. 그의 요청
*"send the non-reproductions with the same weight as the reproductions"*
에 맞춘 순서.

## 넣지 않은 것

- 나머지 3건.
- 사전 미존재 테스트 1건 red (`test_cluster_header_emits_when_
  suggestions_exist`): 무관한 기존 실패, 우리 집안일.

---

Ali,

**Your second finding — ASCII-only `\d`. Reproduced, but not where you
found it.**

The non-reproduction first, since it is the more useful half. On our
side the number extraction is Python, and Python's `re` matches Unicode
decimal digits under `\d` by default, so a price written in
Arabic-Indic digits is extracted correctly and `int()` reads it as the
same value. I ran it rather than assuming it: the scorer that pulls
figures out of a reply returns 120 for both spellings. So the specific
failure you hit — the price gate blind to the digits the customer
actually typed — does not exist in our measurement path, and it is the
language, not our care, that prevented it.

The class of defect is live here all the same, one layer further out.
Our chat renderer is JavaScript, where `\d` really is `[0-9]`, and four
model-output-facing patterns were blind to a reply enumerated in
Arabic-Indic or extended Arabic-Indic digits: truncation detection, two
enumerated-list parsers, and the markdown ordered-list rendering. The
visible effect is that a correct Arabic answer renders as an unbroken
block and its numbered items are not offered as follow-ups — a quality
failure rather than a safety one, but the same root cause you named.

All four now carry an explicit class covering ASCII, Arabic-Indic and
extended Arabic-Indic. Not `\p{Nd}`, which would have been the cleaner
spelling: one of our tests lifts those regex literals out of the
JavaScript and recompiles them in Python, which rejects `\p`. Our own
internal markers stay ASCII-only on purpose — we emit those ourselves
and they never come from a model.

Verified behaviourally on node rather than by reading the diff: all six
extraction cases, truncation detection, and ordered-list rendering, in
both digit systems, ASCII unchanged.

— Jiwon Seo
Hashevolution / PROJECT JAMES
ORCID 0009-0002-0007-7860
