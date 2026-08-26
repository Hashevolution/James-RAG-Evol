# Ali Afana 엔지니어링 4건 — 결과 보고 (건당 1통)

**성격**: 1차 답장에서 약속하고 Ali 4차 메시지(2026-08-21)가 형식을
지정한 후속 보고. 공동 기탁 arc 와 **별개 실**이다 — 기탁은
DOI `10.5281/zenodo.22030935` 로 종결됐고, 그 준비 폴더
(`docs/collab/m9-joint-deposit-prep/`)는 CLOSED 상태로 둔다.

## Ali 4차 메시지가 지정한 형식

> *One message per finding is the right shape, and I would rather have a
> slow measured answer than a fast impression. Please send the
> non-reproductions with the same weight as the reproductions... Track 2c
> under salted run identities is the one I am most uncertain about on my
> own numbers, so whatever it says, it tells me something.*

세 가지 지시가 들어 있다 — (1) 건당 1통, (2) 비재현도 같은 무게로,
(3) 서두르지 말 것. 통합 1통 초안
(`m9-joint-deposit-prep/ali-reply-4-draft-engineering-findings.md`, commit
`16a638e`)은 이 지시로 **폐기**했다. git 이력에 남아 있으므로 필요하면
꺼낼 수 있고, 작업 트리에 두면 다음 세션이 잘못된 쪽을 보낼 위험이 있어
지웠다.

## 번호 체계

**Ali 자신의 번호**를 따른다. 당시 브랜치 커밋 메시지가 그의 번호를
인용하고 있어 그것으로 확인했다 (해당 커밋들은 PR #1079 squash 병합으로
소멸 — 전부 `6d6a079` 안에 있다):

| | 발견 | 그의 표현 | 판정 |
|---|---|---|---|
| ① | bidi override span 제거 | "first correction" | **재현** |
| ② | JS `\d` ASCII 전용 | "second engineering finding" | **재현** (최소 규모) |
| ③ | 아랍어 표기 변형 | "third finding" | **분할** — 보안 게이트 비재현 / 정규화·스코어러 재현 |
| ④ | salted run identity | "fourth finding" | 메커니즘 재현 / **수치 미측정** |

> 폐기된 통합 초안은 본문 번호를 1 bidi / 2 아랍어 / 3 숫자 / 4 salt 로
> 매겨 **②③이 Ali 번호와 뒤바뀐** 상태였다. 분리하면서 교정했다.

## 발송 순서와 상태

> **통합 발송본**: 운영자가 ①②③을 한 통으로 보내기로 선택 →
> `COMBINED-findings-1-2-3.md`. 내용은 아래 세 통과 동일하며 연결부만
> 다르다. ④는 그대로 단독 발송.

| 순서 | 파일 | 상태 |
|---|---|---|
| 1 | `finding-1-bidi-span-removal.md` | ✅ 발송 가능 |
| 2 | `finding-2-unicode-digits.md` | ✅ 발송 가능 |
| 3 | `finding-3-arabic-normalisation.md` | ✅ 발송 가능 |
| 4 | `finding-4-run-identity-salt.md` | ⛔ **차단** — Track 2c 재측정 필요 |

**3차 답장(발행 확인)은 발송 완료** — Ali 4차 메시지가 그에 대한
답신이다 (README EN/KO 대조 · #461/#463 v0.3.1 · one message per
finding, 세 항목이 3차 본문과 하나씩 대응). 선행 조건 충족.

**①②③은 ④를 기다리지 않는다** — 그게 건당 1통으로 나눈 실익이다.
순서: ① → ② → ③ 발송 → Track 2c 재측정 → ④ 발송.

## ④의 차단 해제 조건 — 한 명령으로 준비됨

라이브 JAMES 서버 + Ollama 가 있는 **운영자 머신**에서:

```bash
python scripts/research/track2c_remeasure.py --preflight-only  # 환경 점검, 무변경
python scripts/research/track2c_remeasure.py --evidence-only   # 증거 캡처, 무변경
python scripts/research/track2c_remeasure.py --yes             # 실측
```

`--yes` 가 [5]단계에서 **편지에 그대로 붙일 텍스트**를 출력한다.

**설계가 바뀐 이유** (2026-08-25): 원래 계획은 "재실행 후 옛 표와 diff"
였는데 **작동하지 않는다.** 표는 2026-06-23 이고 그 뒤 `core/` 19 커밋 /
전체 73 커밋이 들어갔다 — 판정 변화가 salt 때문인지 drift 때문인지 구분
불가이고, ③ 스코어러 수정이 또 겹친다. 대신 **같은 빌드에서 paired**:

| arm | 세션 키 | 의미 |
|---|---|---|
| A | 전 케이스 공유 (`--shared-session-key`) | 수정 전 동작 재현 |
| B | 케이스별 salt | 수정 후 |

drift · 스코어러 수정 · 언어 오분류가 **양쪽에 동일하게 존재해 상쇄**
된다. 남는 A↔B 차이가 오염 효과다.

또 하나 고친 것: 원래 런북은 **이력을 먼저 지우라고 했는데**, 그 삭제가
바로 "과거 수치가 실제로 오염됐는가" 의 증거를 없앤다. 스크립트는 증거를
**먼저** 캡처해 파일로 남기고, `--yes` 없이는 아무것도 지우지 않는다.

**결과가 불리해도 그대로 쓴다** — Ali 가 *"whatever it says, it tells me
something"* 으로 선약했다. 스크립트는 "아무 판정도 안 움직였다" 인 경우
그 문구까지 만들어 준다.

배경: `reports/research-runs/track-2c-run-identity-contamination-20260819.md`
(§6 런북은 위 스크립트로 supersede 됨)

## 검증 기록 — 왜 두 번 검토했나

초안 1차(4통 분해 직후)에서 정정 5건이 나왔고, 사용자가 *"왜 이렇게
잘못된 것이 많냐"* 고 물었다. **근본 원인은 근거 출처였다** — 소스가
아니라 이전 초안과 커밋 메시지를 근거로 썼고, ① 수정 커밋 메시지
자체가 자기모순이라 그 오류가 그대로 전파됐다.

2차 검토는 방식을 바꿨다: 편지의 **검증 가능한 주장을 전부 열거하고
각각을 명령으로 소스에 대조**했다. git 이력으로 수정 전 코드를 실제
실행해 보는 것 포함. 그 결과:

**2차에서 새로 찾은 실제 오류 2건**

| | 내용 |
|---|---|
| ④ | *"Our own code comment already described the outcome in as many words"* + 인용문. 그 주석(`engine.py:266-274`)은 **세션 키 오염과 무관한 다른 버그** — 2026-05-09 `force_web_search` 칩 클릭이 chat 경로를 타는 라우팅 문제다. 인용도 부정확했고 근거 자체가 오독. 편지에서 가장 자기비판적인 문장(*"documented in our source and still shipped"*)이 여기 얹혀 있었다. Ali 가 코드를 열어보면 바로 드러났을 것. **삭제.** |
| ① | *"your 2026-08-19 letter revised your own earlier recommendation"* — 그의 **의도를 단정**. 리포트의 "normalize" 가 애초에 span 제거를 포함하는 뜻이었을 수 있어 확인 불가. **두 텍스트 병치 + 책임은 우리로** 로 교체. |

**2차에서 강화 1건**: ③의 비재현 근거를 "두 리스트를 세어봤다" 에서
**`core/` 전역 스캔**으로 교체 — 트리 전체에서 아랍 문자가 있는 라인은
이번 수정으로 우리가 쓴 docstring 4줄이 전부다.

**2차에서 소스 대조로 확인된 주장** (변경 불필요): v1 이 실제로 컨트롤만
제거하고 페이로드를 평문으로 남겼다는 것(구 모듈을 직접 실행해 확인) ·
v1 이 NFC 적용이었다는 것 · bidi_04 의 RLO×3/PDF×3 per-digit span 구조와
평문 120 잔존 · 구 스코어러의 `.lower()` 부분문자열 비교 · 구 sweep 이
`{"question": text}` 만 POST 했다는 것 · truncation 함수의 `return true`
= "잘렸다" 의미 · 수정 전 tests/ 에 아랍-인도 숫자 커버리지 0건 ·
`\d` 를 담은 변경 라인이 정확히 6줄 4개소 · bench/ragas/q15 세 경로의
키 형태(리포트가 아니라 소스에서) · bidi_02 슬립 기록 · bidi_01~04
테스트 본문이 실제로 재작성됐다는 것(v1 은 컨트롤 부재만, v2 는 은닉
지시 부재를 단언).

## 세 통에 공통으로 적용한 규율

1. **재현 여부가 먼저, 수정 내용이 나중.** 그가 준 건 발견이지 패치
   요청이 아니다.
2. **그의 스택으로 일반화하지 않는다.** 우리가 뭘 고쳤는지만 말한다.
   ②의 `\d` 만 예외 — JS 언어 차원 사실이라 확인 가능한 형태로 적었다.
3. **크기를 부풀리지 않는다.** ②는 렌더링 결함이지 보안 결함이 아니라고
   본문에 명시했다.
4. **답장을 요구하는 문장을 넣지 않는다.** 4통 모두 상대에게 새 의무를
   만들지 않는다.

## 알려진 미해결 실 (여기서 다루지 않음)

- 아랍어 injection 이 어떤 철자로도 탐지되지 않는 커버리지 공백 —
  ③ 본문에 사실만 적고 확대하지 않았다. 탐지기 확장은 정책 변경.
- `bench.py` / `run_ragas.py` / `q15_repeat_audit.py` salt 여부 —
  운영자 결정. ④ 본문에 "결정으로 남겼다"고만 적었다.
- LRB-S2 재현 실패 — 무관한 JAMES 내부 사안. 4통 어디에도 없다.
