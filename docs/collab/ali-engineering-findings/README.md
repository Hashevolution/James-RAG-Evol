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

**Ali 자신의 번호**를 따른다. 커밋 메시지로 확인:

| | 발견 | 커밋 | 판정 |
|---|---|---|---|
| ① | bidi override span 제거 | `e19f239` "first correction" | **재현** |
| ② | JS `\d` ASCII 전용 | `a9d96f4` "second engineering finding" | **재현** (최소 규모) |
| ③ | 아랍어 표기 변형 | `8c6f726` "third finding" | **분할** — 보안 게이트 비재현 / 정규화·스코어러 재현 |
| ④ | salted run identity | `dace68f` "fourth finding" | 메커니즘 재현 / **수치 미측정** |

> 폐기된 통합 초안은 본문 번호를 1 bidi / 2 아랍어 / 3 숫자 / 4 salt 로
> 매겨 **②③이 Ali 번호와 뒤바뀐** 상태였다. 분리하면서 교정했다.

## 발송 순서와 상태

| 순서 | 파일 | 상태 |
|---|---|---|
| 1 | `finding-1-bidi-span-removal.md` | ✅ 발송 가능 |
| 2 | `finding-2-unicode-digits.md` | ✅ 발송 가능 |
| 3 | `finding-3-arabic-normalisation.md` | ✅ 발송 가능 |
| 4 | `finding-4-run-identity-salt.md` | ⛔ **차단** — Track 2c 재측정 필요 |

전제: 3차 답장(발행 확인)이 먼저 나가 있을 것.
①②③은 ④를 기다리지 않는다 — 그게 건당 1통으로 나눈 실익이다.

## ④의 차단 해제 조건

라이브 JAMES 서버 + Ollama 가 있는 운영자 머신에서:

```bash
sqlite3 memory/james_memory.db "DELETE FROM conversation_history;"
python scripts/adversarial_sweep.py --fixture eval/adversarial/ar_ecommerce-v1.1-james.yaml
```

결과를 `finding-4-...md` 의 `[측정 결과]` 블록에 채운 뒤 발송. **결과가
불리해도 그대로 쓴다** — Ali 가 *"whatever it says, it tells me
something"* 으로 선약했고, 유리한 결과만 보내면 그 선약을 배신한다.

전체 배경: `reports/research-runs/track-2c-run-identity-contamination-20260819.md`

## 검증 기록 — 왜 두 번 검토했나

초안 1차(4통 분해 직후)에서 정정 5건이 나왔고, 사용자가 *"왜 이렇게
잘못된 것이 많냐"* 고 물었다. **근본 원인은 근거 출처였다** — 소스가
아니라 이전 초안과 커밋 메시지를 근거로 썼고, 커밋 `e19f239` 메시지
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
