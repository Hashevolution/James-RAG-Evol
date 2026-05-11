"""
PROJECT JAMES - Patch Applier (Phase 7)

4-Gate Validator 통과 후에만 적용.
백업 → 적용 → 감사 로그 순서 강제.

절대 금지:
  ❌ Validator 통과 없이 적용
  ❌ PROTECTED_FILES 적용
  ❌ 백업 없이 수정
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Tuple

from tools.router import _is_protected

PATCH_LOG_PATH = "james_patch_log.jsonl"
BACKUP_DIR     = "./workspace/.backups"
APPLY_LOG      = "james_apply_log.jsonl"


def _log(event: str, patch_id: str, detail: str, success: bool = True):
    entry = {
        "time":     datetime.now().isoformat(),
        "event":    event,
        "patch_id": patch_id,
        "detail":   detail[:200],
        "success":  success,
        "layer":    "patch_applier",
    }
    for path in [PATCH_LOG_PATH, APPLY_LOG]:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass


def apply(patch: dict, validated: bool = False) -> Tuple[bool, str]:
    """
    Patch 적용.

    Args:
        patch:     Patch dict (patch_generator 또는 extractor 결과)
        validated: True여야만 적용 (Validator 통과 확인)

    Returns:
        (success, message)
    """
    patch_id = patch.get("patch_id", patch.get("source","unknown") + "_" +
                          datetime.now().strftime("%H%M%S"))
    target   = patch.get("target", "")
    code     = patch.get("code", patch.get("diff", ""))

    # ── 0. Validator 통과 확인 ───────────────────────────────
    if not validated:
        reason = "Validator 미통과 — 적용 거부"
        _log("APPLY_REJECTED", patch_id, reason, success=False)
        print(f"[APPLIER] ❌ {reason}")
        return False, reason

    # ── 1. PROTECTED_FILES 재확인 (이중 안전장치) ───────────
    if _is_protected(target):
        reason = f"PROTECTED 파일 — 적용 거부: {target}"
        _log("APPLY_PROTECTED", patch_id, reason, success=False)
        print(f"[APPLIER] ❌ {reason}")
        return False, reason

    # ── 2. 대상 경로 검증 ────────────────────────────────────
    # Sandbox guard: target must be a relative-ish path starting with
    # "." (typically "./workspace/..."). We check the RAW string, not
    # str(Path(...)) — on Windows Path normalization strips the leading
    # "./", which would silently reject every legitimate sandbox patch.
    p = Path(target)
    if not target or not target.startswith("."):
        reason = f"잘못된 경로: {target}"
        _log("APPLY_BAD_PATH", patch_id, reason, success=False)
        return False, reason

    # ── 3. 백업 (기존 파일 있을 때) ─────────────────────────
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    if p.exists():
        timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = Path(BACKUP_DIR) / f"{p.name}.{timestamp}.bak"
        try:
            shutil.copy2(target, backup_path)
            print(f"[APPLIER] 백업: {backup_path.name}")
        except Exception as e:
            reason = f"백업 실패: {e}"
            _log("APPLY_BACKUP_FAIL", patch_id, reason, success=False)
            return False, reason

    # ── 4. 적용 ──────────────────────────────────────────────
    try:
        p.parent.mkdir(parents=True, exist_ok=True)

        # diff 형식이면 patch 처리, 아니면 전체 쓰기
        if code.startswith("---") and "+++" in code:
            ok, msg = _apply_diff(p, code)
            if not ok:
                return False, msg
        else:
            # 코드 블록 직접 쓰기
            p.read_text(encoding="utf-8") if p.exists() else ""
            p.write_text(code, encoding="utf-8")

    except Exception as e:
        reason = f"적용 실패: {e}"
        _log("APPLY_FAIL", patch_id, reason, success=False)
        return False, reason

    # ── 5. 감사 로그 ─────────────────────────────────────────
    _log("APPLY_SUCCESS", patch_id,
         f"target={target} len={len(code)}", success=True)
    print(f"[APPLIER] ✅ 적용 완료: {target} ({len(code)}자)")
    return True, f"적용 완료: {target}"


def _apply_diff(target_path: Path, diff_text: str) -> Tuple[bool, str]:
    """
    unified diff 형식 적용.
    단순 +/- 라인 기반으로 처리.
    """
    try:
        lines = diff_text.split("\n")
        new_lines = []
        for line in lines:
            if line.startswith("+") and not line.startswith("+++"):
                new_lines.append(line[1:])
            elif line.startswith("-") or line.startswith("---") or line.startswith("+++"):
                continue
            elif line.startswith("@@"):
                continue
            else:
                new_lines.append(line)
        target_path.write_text("\n".join(new_lines), encoding="utf-8")
        return True, ""
    except Exception as e:
        return False, f"diff 적용 실패: {e}"


def restore_latest(target: str) -> Tuple[bool, str]:
    """가장 최근 백업으로 롤백."""
    p    = Path(target)
    bdir = Path(BACKUP_DIR)
    backups = sorted(bdir.glob(f"{p.name}.*.bak"), reverse=True)
    if not backups:
        return False, f"백업 없음: {target}"
    try:
        shutil.copy2(backups[0], target)
        print(f"[APPLIER] 롤백: {target} ← {backups[0].name}")
        return True, f"롤백 완료: {backups[0].name}"
    except Exception as e:
        return False, f"롤백 실패: {e}"


if __name__ == "__main__":
    import os
    os.makedirs("./workspace", exist_ok=True)

    print("=== Patch Applier 자가 테스트 ===\n")

    # 정상 적용
    patch = {
        "patch_id": "test_01",
        "target":   "./workspace/_applier_test.py",
        "code":     "# 자동 적용 테스트\nprint('JAMES Patch Applied')\n",
    }
    ok, msg = apply(patch, validated=True)
    print(f"  {'✅' if ok else '❌'} 정상 적용: {msg[:50]}")

    # Validator 미통과 → 거부
    ok2, msg2 = apply(patch, validated=False)
    print(f"  {'✅' if not ok2 else '❌'} validated=False 거부: {msg2[:50]}")

    # PROTECTED 파일 → 거부
    patch3 = {"patch_id":"test_02","target":"core/security_layer.py",
              "code":"hack","diff":""}
    ok3, msg3 = apply(patch3, validated=True)
    print(f"  {'✅' if not ok3 else '❌'} PROTECTED 거부: {msg3[:50]}")

    # 롤백
    ok4, msg4 = restore_latest("./workspace/_applier_test.py")
    print(f"  {'✅' if ok4 else '❌'} 롤백: {msg4[:50]}")

    try:
        os.remove("./workspace/_applier_test.py")
    except Exception:
        pass
