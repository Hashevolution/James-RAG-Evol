"""
PROJECT JAMES - Patch Generator (Phase 6)

사람 승인 전제. 자동 적용 절대 없음.

흐름:
  1. LLM → diff 형식 Patch 제안 생성
  2. status = "PENDING_APPROVAL"
  3. James가 검토
  4. 승인 시만 PatchValidator → 적용

절대 금지:
  ❌ 자동 적용
  ❌ PROTECTED_FILES 대상 Patch 생성
  ❌ security_layer / memory_loom / ontology 수정 제안
"""

import re
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

from tools.code.sandbox import policy_validate_path
from tools.router import _is_protected

PATCH_LOG_PATH = "james_patch_log.jsonl"
PATCH_STORE    = "./workspace/patches"   # Patch 저장 위치

# Patch 생성 자체를 막을 파일 (더 보수적)
PATCH_FORBIDDEN = [
    "security_layer", "memory_loom", "ontology",
    "auth.py", "graph_engine", "reasoning_engine",
]


def _log_patch(event: str, patch_id: str, detail: str):
    entry = {
        "time":     datetime.now().isoformat(),
        "event":    event,
        "patch_id": patch_id,
        "detail":   detail[:200],
        "layer":    "patch_generator",
    }
    try:
        with open(PATCH_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def generate_patch(
    request:  str,
    target:   str,
    user_role: str = "admin",
) -> dict:
    """
    LLM을 통해 Patch 제안 생성.
    status는 항상 PENDING_APPROVAL — 자동 적용 없음.

    Args:
        request:   개선 요청 내용
        target:    대상 파일 경로
        user_role: 요청자 role

    Returns:
        {
          "patch_id":   str,
          "diff":       str,
          "target":     str,
          "confidence": float,
          "status":     "PENDING_APPROVAL",
          "created_at": str,
        }
    """
    patch_id = hashlib.md5(
        f"{target}{request}{datetime.now().isoformat()}".encode()
    ).hexdigest()[:12]

    # 1. PROTECTED_FILES 차단 (Patch 생성 자체 거부)
    if _is_protected(target):
        _log_patch("BLOCKED_PROTECTED", patch_id, f"target={target}")
        return {
            "patch_id": patch_id, "status": "BLOCKED",
            "error": f"PROTECTED: {target}",
        }

    # 2. 절대 금지 파일 차단
    for forbidden in PATCH_FORBIDDEN:
        if forbidden in target:
            _log_patch("BLOCKED_FORBIDDEN", patch_id, f"target={target}")
            return {
                "patch_id": patch_id, "status": "BLOCKED",
                "error": f"FORBIDDEN: {target} (보안/핵심 파일)",
            }

    # 3. PolicyEngine + 경로 검증 (#44 phase 3-3) — fs.write (admin only)
    path_ok, reason = policy_validate_path(target, user_role, "fs.write")
    if not path_ok:
        _log_patch("BLOCKED_PATH", patch_id, reason)
        return {"patch_id": patch_id, "status": "BLOCKED", "error": reason}

    # 4. 현재 파일 읽기
    p = Path(target)
    original_code = ""
    if p.exists():
        try:
            original_code = p.read_text(encoding="utf-8")[:3000]
        except Exception:
            pass

    # 5. LLM으로 Patch diff 생성
    diff = _generate_diff_via_llm(request, target, original_code)

    # 6. confidence 계산
    confidence = _estimate_confidence(diff, original_code)

    patch = {
        "patch_id":   patch_id,
        "target":     target,
        "request":    request[:200],
        "diff":       diff,
        "confidence": confidence,
        "status":     "PENDING_APPROVAL",   # 자동 적용 금지
        "created_at": datetime.now().isoformat(),
        "created_by": user_role,
    }

    # 7. Patch 저장
    Path(PATCH_STORE).mkdir(parents=True, exist_ok=True)
    patch_file = Path(PATCH_STORE) / f"{patch_id}.json"
    try:
        patch_file.write_text(
            json.dumps(patch, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception:
        pass

    _log_patch("GENERATED", patch_id,
               f"target={target} confidence={confidence:.2f}")
    print(f"[PATCH] ✅ 생성: {patch_id} | {target} | status=PENDING_APPROVAL")
    return patch


def _generate_diff_via_llm(request: str, target: str, original: str) -> str:
    """LLM 통해 unified diff 형식 Patch 생성."""
    try:
        from llm.router import route
        llm = route(request, task_type="coding")

        prompt_messages = [{
            "role": "user",
            "content": (
                f"다음 파일을 수정하는 unified diff를 생성해줘.\n\n"
                f"파일: {target}\n\n"
                f"요청: {request}\n\n"
                f"현재 코드:\n```python\n{original[:2000]}\n```\n\n"
                "규칙:\n"
                "1. unified diff 형식으로만 출력 (--- +++ @@ 형태)\n"
                "2. 최소한의 변경만\n"
                "3. 설명 없이 diff만\n"
            )
        }]

        diff = llm.generate(prompt_messages, timeout=60)

        # diff 형식 정제
        if "---" not in diff and "+++" not in diff:
            diff = _make_simple_diff(target, request)

        return diff[:3000]

    except Exception as e:
        print(f"[PATCH] LLM 실패 → 템플릿 diff: {e}")
        return _make_simple_diff(target, request)


def _make_simple_diff(target: str, request: str) -> str:
    """LLM 실패 시 템플릿 diff 반환."""
    return (
        f"--- a/{target}\n"
        f"+++ b/{target}\n"
        f"@@ -1,1 +1,2 @@\n"
        f" # [PATCH] 자동 생성 diff\n"
        f"+# 요청: {request[:100]}\n"
        f" # 위 diff를 검토 후 수동 적용하세요\n"
    )


def _estimate_confidence(diff: str, original: str) -> float:
    """Patch 신뢰도 간단 추정."""
    if not diff or len(diff) < 20:
        return 0.1

    # unified diff 형식 여부
    has_format = "---" in diff and "+++" in diff and "@@" in diff
    if not has_format:
        return 0.3

    # 변경 라인 수 기반 (변경이 적을수록 신뢰도 높음)
    added   = diff.count("\n+")
    removed = diff.count("\n-")
    total   = added + removed

    if total <= 5:   return 0.9
    if total <= 15:  return 0.7
    if total <= 30:  return 0.5
    return 0.3


def load_patch(patch_id: str) -> Optional[dict]:
    """저장된 Patch 불러오기."""
    patch_file = Path(PATCH_STORE) / f"{patch_id}.json"
    if not patch_file.exists():
        return None
    try:
        return json.loads(patch_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_patches(status: str = "PENDING_APPROVAL") -> list:
    """상태별 Patch 목록 조회."""
    store = Path(PATCH_STORE)
    if not store.exists():
        return []
    patches = []
    for f in store.glob("*.json"):
        try:
            p = json.loads(f.read_text(encoding="utf-8"))
            if status == "all" or p.get("status") == status:
                patches.append({
                    "patch_id":   p.get("patch_id"),
                    "target":     p.get("target"),
                    "status":     p.get("status"),
                    "confidence": p.get("confidence"),
                    "created_at": p.get("created_at"),
                })
        except Exception:
            pass
    return sorted(patches, key=lambda x: x.get("created_at",""), reverse=True)


if __name__ == "__main__":
    print("=== Patch Generator 자가 테스트 ===\n")

    # 정상 케이스
    patch = generate_patch(
        request="함수에 docstring 추가",
        target="./workspace/sample.py",
        user_role="admin",
    )
    print(f"  상태: {patch.get('status')} | confidence={patch.get('confidence')}")

    # PROTECTED 차단
    blocked = generate_patch(
        request="보안 우회 시도",
        target="core/security_layer.py",
        user_role="admin",
    )
    print(f"  PROTECTED 차단: {blocked.get('status')=='BLOCKED'}")

    # FORBIDDEN 차단
    forbidden = generate_patch(
        request="메모리 수정",
        target="core/memory_loom.py",
        user_role="admin",
    )
    print(f"  FORBIDDEN 차단: {forbidden.get('status')=='BLOCKED'}")
