# 비전 모델 기본값 두 갈래 — 발견 기록

**날짜**: 2026-08-28
**계기**: `test_vision_mode` 2건이 `'qwen2.5vl:7b' != 'llava:13b'` 로
실패. 테스트만 스테일한 줄 알았는데, 소스를 따라가 보니 **경로마다
기본값이 다릅니다.**
**상태**: 기록만. **코드 변경 없음** — 어느 쪽이 옳은지는 운영자 판단.

## 사실

`core/reasoning/modes/vision.py::_resolve_vision_model` 은 세 단계다:

| 우선순위 | 경로 | 기본값 | 출처 |
|---|---|---|---|
| 1 | 사용자 명시 선택 | — | 호출자 |
| 2 | kill-switch (`JAMES_DISABLE_MODE_AWARE_ROUTING`) | **`qwen2.5vl:7b`** | `config.py:204` `MULTIMODAL_MODEL` |
| 3 | 정상 경로 `resolve_for_mode("vision")` | **`llava:13b`** | `core/model_resolver.py:152` |

별도로 UI 설정에도 하나 더 있다:

| `core/llm_settings.py:51` | `vision_model` | **`llava:13b`** |

## 왜 갈렸나

PR #1070 `feat(v0.6.1): default vision model llava:13b → qwen2.5vl:7b
(proven OCR win) + filter floor fix` 이 **`config.py` 만** 바꿨다.
`model_resolver.py` 의 `"vision": ["llava:13b"]` 목록과
`llm_settings.py` 의 기본값은 그대로다.

## 함의 — 확인이 필요한 지점

kill-switch 는 **꺼져 있는 것이 정상 운영 상태**다. 즉 평상시 비전
요청은 3번 경로를 타고 `llava:13b` 로 간다. PR #1070 이 근거로 든
"proven OCR win" 이 실제로는 **kill-switch 를 켠 경우에만 적용**되고
있을 가능성이 있다.

세 가지 중 하나일 것이다:

1. **누락** — `model_resolver.py:152` 도 `qwen2.5vl:7b` 로 갔어야 했다.
   그렇다면 OCR 개선이 지금 대부분의 트래픽에 적용되지 않고 있다.
2. **의도** — 정상 경로는 설치 확인 + graceful fallback 이 있어
   보수적으로 두고, config 는 레거시 경로용이다.
3. **부분 이행** — 롤아웃 중간 단계.

**본 세션에서 판단하지 않았다.** 비전 모델 선택을 바꾸는 것은 동작
변경이고, 여기서는 Ollama 도 실제 이미지도 없어 OCR 품질을 측정할 수
없다. 근거 없이 목록을 바꾸는 것은 PR #1070 이 근거를 들어 한 결정을
근거 없이 확대하는 셈이다.

## 테스트 쪽에서 한 것

`tests/test_vision_mode.py` 의 두 assertion 이 `llava:13b` 를
하드코딩하고 있었다. 둘 다 **kill-switch 경로**를 검사하므로
`config.MULTIMODAL_MODEL` 을 읽도록 바꿨다 — 기본값이 또 바뀌어도
테스트를 고칠 필요가 없다. 3번 경로를 검사하는 테스트(96 / 104 행)는
`llava:13b` 를 그대로 두었다. **그것이 현재 사실이기 때문이다.**

즉 테스트는 이제 두 값이 다르다는 사실을 그대로 반영한다. 위 1/2/3 중
무엇인지 정해지면 그때 한쪽으로 모으면 된다.
