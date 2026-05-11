"""
PROJECT JAMES - Patch Extractor (Phase 7)

대화에서 코드 블록을 추출하여 Patch 후보로 변환.
trigger 키워드 없으면 추출 안 함.

흐름:
  대화 → 트리거 감지 → 코드 블록 추출 → Patch 후보 반환
  반환된 후보는 반드시 patch_validator.py 4-Gate 통과 후에만 적용.
"""

import re
import json
from datetime import datetime
from typing import Optional

PATCH_LOG_PATH = "james_patch_log.jsonl"

CODE_TRIGGER = [
    "코드 추가", "수정해줘", "구현해줘", "함수 만들어",
    "업데이트", "리팩토링", "개선해줘", "추가해줘",
    "fix ", "update ", "refactor ", "implement ",
]

SUPPORTED_LANGS = {
    "python": ".py", "py": ".py",
    "javascript": ".js", "js": ".js",
    "typescript": ".ts", "ts": ".ts",
    "bash": ".sh", "shell": ".sh",
    "sql": ".sql", "json": ".json",
    "": ".py",  # 언어 미지정 → Python 기본
}


def _log(event: str, detail: str):
    try:
        entry = {"time": datetime.now().isoformat(), "event": event,
                 "detail": detail[:200], "layer": "patch_extractor"}
        with open(PATCH_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def extract_from_chat(
    query:    str,
    response: str,
    target:   Optional[str] = None,   # 대상 파일 경로 (없으면 임시)
) -> Optional[dict]:
    """
    대화에서 코드 블록 추출 → Patch 후보 반환.

    Args:
        query:    사용자 질문
        response: LLM 응답
        target:   적용할 파일 경로 (없으면 workspace/patch_temp.py)

    Returns:
        Patch 후보 dict or None (트리거 없거나 코드 없음)
    """
    # 1. 트리거 키워드 확인
    q_lower = query.lower()
    triggered = any(t in q_lower for t in CODE_TRIGGER)
    if not triggered:
        return None

    # 2. 코드 블록 추출 (```lang ... ``` 형식)
    # 언어 명시 또는 미명시 모두 허용
    blocks = re.findall(r"```(\w*)\n?(.*?)```", response, re.DOTALL)

    if not blocks:
        # 인라인 코드만 있어도 추출 시도
        inline = re.findall(r"`([^`]+)`", response)
        if inline and len(inline[0]) > 20:
            blocks = [("", inline[0])]
        else:
            _log("NO_CODE_BLOCK", f"query={query[:50]}")
            return None

    # 3. 가장 긴 코드 블록 선택
    lang, code = max(blocks, key=lambda x: len(x[1]))
    code = code.strip()

    if len(code) < 10:
        return None

    # 4. 대상 파일 결정
    ext = SUPPORTED_LANGS.get(lang.lower(), ".py")
    if not target:
        target = f"./workspace/patch_temp{ext}"

    # 5. Patch 후보 구성
    patch = {
        "source":     "chat",
        "query":      query[:200],
        "code":       code,
        "language":   lang or "python",
        "target":     target,
        "confidence": 0.0,     # Validator가 채움
        "status":     "PENDING_VALIDATION",
        "created_at": datetime.now().isoformat(),
    }

    _log("EXTRACTED", f"target={target} lang={lang} len={len(code)}")
    print(f"[EXTRACTOR] 코드 추출: {len(code)}자 ({lang or 'python'}) → {target}")
    return patch


def extract_target_from_query(query: str) -> Optional[str]:
    """
    질문에서 대상 파일 경로 추출.
    예: "app.py 수정해줘" → "app.py"
    """
    patterns = [
        r"([\w/\\]+\.py)",
        r"([\w/\\]+\.js)",
        r"([\w/\\]+\.ts)",
    ]
    for pattern in patterns:
        m = re.search(pattern, query)
        if m:
            path = m.group(1)
            # workspace 내 경로로 보정
            if not path.startswith("./") and not path.startswith("/"):
                path = f"./workspace/{path}"
            return path
    return None


if __name__ == "__main__":
    print("=== Patch Extractor 자가 테스트 ===\n")

    cases = [
        # (query, response, expect_patch)
        (
            "hello 함수 만들어줘",
            '```python\ndef hello():\n    print("Hello, JAMES!")\n```',
            True,
        ),
        (
            "오늘 날씨 어때?",  # 트리거 없음
            "맑습니다.",
            False,
        ),
        (
            "이 코드 수정해줘",
            "코드 블록 없는 응답입니다.",  # 코드 없음
            False,
        ),
        (
            "app.py 업데이트해줘",
            '```py\nx = 1\nprint(x)\n```',
            True,
        ),
    ]

    passed = 0
    for query, response, expect in cases:
        result = extract_from_chat(query, response)
        ok = (result is not None) == expect
        passed += int(ok)
        has_patch = result is not None
        print(f"  {'✅' if ok else '❌'} '{query[:25]}' → patch={'있음' if has_patch else '없음'} (기대={'있음' if expect else '없음'})")
        if result:
            print(f"       code={result['code'][:40]} target={result['target']}")

    print(f"\n  결과: {passed}/{len(cases)} PASS")
