# Ali 엔지니어링 4건 — 건당 1통 답신 세트

**생성**: 2026-08-21
**대체 대상**: `../ali-reply-4-draft-engineering-findings.md` (통합 1통판,
커밋 `16a638e`). 이 폴더가 그 초안을 대체하며, 원 초안은 삭제한다.
**상태**: ①②③ 발송 가능 / ④ 운영자 게이트로 보류.

---

## 왜 4통인가

세 개의 근거가 같은 방향을 가리킨다.

1. **우리가 먼저 그렇게 약속했다.** 1차 답장(발송 완료)의 마지막 문장 —
   *"I will come back with what each one did or did not reproduce, **in
   its own message**, once there is something measured to report."*
   3차 답장도 같은 표현을 반복한다. 통합 1통은 우리 자신의 약속과
   어긋난다.
2. **Ali 4차 메시지가 같은 형식을 명시했다** — *"One message per finding
   is the right shape, and I would rather have a slow measured answer
   than a fast impression"*, 앞에 *"take the time they need"*. 우리
   문장의 메아리일 가능성이 있으나, 두 독법 모두 4통으로 수렴한다.
3. **④가 ①②③을 인질로 잡는다.** ④는 라이브 서버 + Ollama 재측정
   대기이고 해제 시점을 우리가 통제하지 못한다. 묶어 보내면 이미 끝난
   세 건이 무기한 대기한다. 분해하면 ①②③이 지금 나간다.

## 파일

| 파일 | Ali 번호 | 재현 여부 | 발송 |
|---|---|---|---|
| `finding-1-bidi-span.md` | ① | 재현 (라이브 보안 결함) | **지금** |
| `finding-2-ascii-digits.md` | ② | 절반 비재현 (Python) / 재현 (JS 렌더러) | **지금** |
| `finding-3-arabic-orthography.md` | ③ | 절반 비재현 (아랍어 게이트 부재) / 재현 (런타임 정규화 · 스코어러) | **지금** |
| `finding-4-run-identity-salt.md` | ④ | 메커니즘 재현, **측정 미완** | **보류** |

번호는 **Ali 자신의 번호**를 따른다 (커밋 `e19f239` / `a9d96f4` /
`8c6f726` / `dace68f` 본문이 각각 "first correction" / "second
engineering finding" / "third finding" / "fourth finding" 으로 인용).
통합 초안은 bidi → 아랍어 → 숫자 → salt 순으로 ②③을 뒤바꿔 놓았었다.

## 발송 순서

①  →  ②  →  ③  →  (재측정 후) ④.

①이 4통 예고를 담고 있으므로 반드시 먼저 나간다. ②③은 ①이 나간 뒤라면
같은 날 연달아 보내도 무방하다. ④는 §"발송 차단 조건" 두 건이 풀린 뒤.

## 통합 초안 대비 실질 변경 2건

1. **형식**: 1통 → 4통 (위 근거).
2. **③의 순서**: 통합 초안은 ③을 *"Reproduced"* 로 열었다. 실제로는
   그가 지목한 실패 모드(아랍어 키워드 게이트 우회)가 **우리 스택에서
   재현되지 않는다** — `core/security_layer/_policies.py` 의
   `ATTACK_PATTERNS` 는 영어 + 한국어뿐이라 뚫릴 게이트가 없다
   (2026-08-21 재확인, 아랍어 패턴 0건). 커밋 `8c6f726` 본문은 이미
   이걸 기록하고 있었는데 답신 초안만 유리한 절반을 앞세웠다. 새 판은
   비재현 → 재현 순서이고, "게이트가 아예 없다" 는 커버리지 갭도 한 절로
   명시한다 (그에게 묻지 않는 형태).

Ali 4차 메시지의 *"Please send the non-reproductions with the same
weight as the reproductions"* 가 이 두 번째 변경을 명시적 요구로
만들었지만, ③의 순서 문제는 그 요청 이전에도 정직성 문제였다.

## Ali 4차 원문 대조 (2026-08-21 검증)

그의 편지 4문단을 요구 단위로 쪼개고, 각각이 이 폴더의 어디서 충족되는지
대조한다. **미충족 0건.**

| Ali 원문 | 성격 | 충족 위치 |
|---|---|---|
| *"Confirmed on your side of the pointer ... the leg resolves to #461/#463 as v0.3.1 rather than to #440"* | 통보 (종결) | 요구 없음. README 포인터는 이미 서 있음 |
| *"they were right, and both were the same class of error — the text asserting a little more than the measurement supported"* | 통보 (종결) | 요구 없음. 우리 framing 을 그대로 받음 |
| *"take the time they need"* + *"I would rather have a slow measured answer than a fast impression"* | 허락 | `finding-4` 보류의 근거. ④를 미완으로 늦게 보내는 것이 이 문장에 정확히 기댄다 |
| *"One message per finding is the right shape"* | 형식 지시 | 이 폴더 전체 (4통 분해) |
| *"Please send the non-reproductions with the same weight as the reproductions"* | **실질 요구** | `finding-2` 비재현 선두 (Python `\d` 유니코드) · `finding-3` 비재현 선두 (아랍어 게이트 부재) |
| *"if the bidi span removal or the Arabic normalisation does not hold on your stack, that is a result about scope"* | **실질 요구 — bidi 명시** | `finding-3` 이 아랍어 쪽 scope 결과. bidi 는 **완전 재현**이므로 비재현이 없다 → `finding-1` 이 대신 **scope 경계 2건을 명시적으로** 보고한다 (override 한정 / bidi_04 숫자 소실). 그가 이름을 대고 물은 항목이라 "재현됨" 한 마디로 닫지 않는다 |
| *"Track 2c under salted run identities is the one I am most uncertain about on my own numbers, so whatever it says, it tells me something"* | 우선순위 신호 | `finding-4`. 재측정 우선순위 상승 + 수치 미재확인 원칙 유지의 근거. 그 문장을 본문에서 직접 되받는다 |
| *"no draft exists yet, so there is nothing to open ... you and Robin read it before it goes anywhere"* | 통보 (종결) | 요구 없음. 3차 답장이 이미 슬롯을 열어둠. **이 4통 어디에도 arXiv 언급 없음이 맞다** |

### 판단 보류 1건 — 운영자 확인 요망

*"it belongs in **the record** as much as a confirmation does."*

"the record" 의 범위가 두 갈래로 읽힌다:

- (A) 우리 둘 사이의 엔지니어링 교신 기록 — 사적. 이 4통이 곧 그 기록.
- (B) 공개 기록 (arXiv 원고 / 후속 기탁의 scope 절).

현 초안은 **(A) 로 가정**하고 쓰였다. (B) 라면 ②③의 비재현이 향후
공개물의 scope 절에 들어가야 하고, 그건 우리가 지금 약속할 수 있는
사안이 아니다 (arXiv 초안 자체가 아직 없음). **어느 쪽으로도 묻지
않는다** — 물으면 그에게 답할 게 생기고, 4통 전체의 "새 의무를 만들지
않는다" 원칙을 깬다. arXiv 초안이 실제로 열릴 때 자연스럽게 판정된다.

## 공통 설계 원칙 (4통 전부)

1. **재현 여부를 먼저, 수정 내용을 나중에.** 그가 준 건 발견이지 패치
   요청이 아니다.
2. **비재현을 재현과 같은 무게로.** ②③이 이에 해당. ①은 비재현이
   없으므로(완전 재현) 대신 **scope 경계**를 같은 무게로 보고한다 —
   그가 bidi 를 이름 대고 지목했기 때문.
3. **그의 스택으로 일반화하지 않는다.** 우리가 뭘 고쳤는지만 말한다.
   ②의 JS `\d` 는 언어 차원 사실이라 확인 가능한 형태로만 언급.
4. **새 의무를 만들지 않는다.** 답장을 요구하는 문장을 넣지 않는다.
5. **④ 전에는 Track 2c 수치를 어떤 형태로도 재확인해 주지 않는다.**

## 넣지 않은 것 (4통 공통)

- LRB-S2 재현 실패: 무관한 JAMES 내부 사안.
- 남은 테스트 실패: 우리 집안일.
- `ATTACK_PATTERNS` 아랍어 확장 계획/일정: 정책 변경이고 미결. ③이 갭의
  존재만 밝히고 약속은 하지 않는다.
