"""
PROJECT JAMES — 실제 데이터 투입 전 리셋 스크립트
=====================================================

실행:  python reset_for_production.py
확인:  python reset_for_production.py --dry-run   (삭제 없이 대상만 확인)

리셋 대상:
  [1] wiki/entity/prod/  — 테스트 entity 파일 전체
  [2] wiki/entity/test/  — 테스트용 파일 전체
  [3] chroma_db/         — 벡터 인덱스 전체
  [4] uploads/           — 업로드된 테스트 파일
  [5] memory/james_memory.db — 대화 기록, 선호도, 피드백 (선택)
  [6] james_attack_log.jsonl — 보안 이벤트 로그 (선택)

리셋 제외 (운영 데이터 유지):
  james_users.db    — 사용자 계정 (admin 계정 날아감)
  james_audit.db    — 감사 로그 (기록 보존 목적)
  모든 .py 파일     — 코드
  models/           — 임베딩 모델
"""

import os
import sys
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime

# Issue #2: cp949 콘솔에서 box-drawing 문자 크래시 방지.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from utils.console import ensure_utf8_console
    ensure_utf8_console()
except ImportError:
    pass

# ── 경로 설정 ──────────────────────────────────────────────────
try:
    from config import BASE_DIR, WIKI_DIR, CHROMA_DIR, UPLOAD_DIR
except ImportError:
    BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
    WIKI_DIR   = os.path.join(BASE_DIR, "wiki")
    CHROMA_DIR = os.path.join(BASE_DIR, "chroma_db")
    UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")

MEMORY_DB   = os.path.join(BASE_DIR, "memory", "james_memory.db")
ATTACK_LOG  = os.path.join(BASE_DIR, "james_attack_log.jsonl")

DRY_RUN = "--dry-run" in sys.argv

# ── 유틸 ───────────────────────────────────────────────────────
def log(msg: str, level: str = ""):
    prefix = {"WARN": "⚠️ ", "OK": "✅ ", "SKIP": "⏭️ ", "DEL": "🗑️ "}.get(level, "   ")
    print(f"  {prefix}{msg}")

def count_files(path: str) -> int:
    p = Path(path)
    if p.is_dir():
        return len(list(p.rglob("*")))
    return 1 if p.exists() else 0

def delete_dir_contents(path: str, label: str):
    p = Path(path)
    if not p.exists():
        log(f"{label} — 폴더 없음 (스킵)", "SKIP")
        return 0
    files = list(p.rglob("*"))
    n = len([f for f in files if f.is_file()])
    if DRY_RUN:
        log(f"{label} — {n}개 파일 삭제 예정 (dry-run)", "WARN")
        for f in sorted(files)[:5]:
            print(f"     {f.relative_to(Path(path).parent)}")
        if n > 5:
            print(f"     ... 외 {n-5}개")
    else:
        shutil.rmtree(path)
        Path(path).mkdir(parents=True, exist_ok=True)
        log(f"{label} — {n}개 파일 삭제 완료", "DEL")
    return n

def delete_file(path: str, label: str):
    p = Path(path)
    if not p.exists():
        log(f"{label} — 없음 (스킵)", "SKIP")
        return
    if DRY_RUN:
        size = p.stat().st_size // 1024
        log(f"{label} — {size}KB 삭제 예정 (dry-run)", "WARN")
    else:
        p.unlink()
        log(f"{label} — 삭제 완료", "DEL")

def reset_memory_db(path: str):
    """메모리 DB — 대화/피드백/지식레벨만 초기화, 페르소나/사용자 유지."""
    if not Path(path).exists():
        log("james_memory.db — 없음 (스킵)", "SKIP")
        return
    if DRY_RUN:
        log("james_memory.db — 대화/피드백/지식레벨 초기화 예정", "WARN")
        return
    try:
        conn = sqlite3.connect(path)
        # 대화 기록 전체 삭제
        conn.execute("DELETE FROM conversation_history")
        # 피드백/지식레벨/패턴 삭제 (선호도/페르소나는 유지)
        conn.execute(
            "DELETE FROM preferences WHERE key LIKE 'domain:%'"        # 지식 레벨
        )
        conn.execute(
            "DELETE FROM preferences WHERE key LIKE 'feedback_%'"      # 피드백
        )
        conn.execute(
            "DELETE FROM preferences WHERE key LIKE 'session_%'"       # 세션 이름/요약
        )
        conn.execute("DELETE FROM patterns")                            # 반복 패턴
        conn.commit()
        conn.close()
        log("james_memory.db — 대화/피드백/지식레벨 초기화 (페르소나/설정 유지)", "OK")
    except Exception as e:
        log(f"james_memory.db 초기화 실패: {e}", "WARN")


# ── 메인 ───────────────────────────────────────────────────────

def main():
    print()
    print("=" * 58)
    print("  🔄 PROJECT JAMES — 실제 데이터 투입 전 리셋")
    print(f"  {'[DRY-RUN 모드 — 실제 삭제 없음]' if DRY_RUN else '[실제 삭제 모드]'}")
    print("=" * 58)
    print(f"\n  BASE_DIR: {BASE_DIR}\n")

    # ── 사전 확인 ──────────────────────────────────────────────
    if not DRY_RUN:
        print("  ⚠️  다음 데이터가 삭제됩니다:")
        print("     - wiki/entity/ 전체 (테스트 entity)")
        print("     - chroma_db/    전체 (벡터 인덱스)")
        print("     - uploads/      전체 (업로드 파일)")
        print("     - 대화 기록 / 피드백 / 지식 레벨")
        print()
        ans = input("  계속 진행하시겠습니까? (yes 입력): ").strip().lower()
        if ans != "yes":
            print("\n  취소됨.\n")
            sys.exit(0)
        print()

    total_deleted = 0

    # [1] wiki entity — prod + test 전체
    print("  [1] Wiki Entity 초기화")
    wiki_prod = os.path.join(WIKI_DIR, "entity", "prod")
    wiki_test = os.path.join(WIKI_DIR, "entity", "test")
    total_deleted += delete_dir_contents(wiki_prod, "wiki/entity/prod/")
    total_deleted += delete_dir_contents(wiki_test, "wiki/entity/test/")

    # [2] ChromaDB 벡터 인덱스
    print("\n  [2] ChromaDB 벡터 인덱스 초기화")
    total_deleted += delete_dir_contents(CHROMA_DIR, "chroma_db/")

    # [3] 업로드 파일
    print("\n  [3] 업로드 파일 초기화")
    total_deleted += delete_dir_contents(UPLOAD_DIR, "uploads/")

    # [4] 메모리 DB (대화/피드백만, 페르소나 유지)
    print("\n  [4] 메모리 DB 부분 초기화")
    reset_memory_db(MEMORY_DB)

    # [5] 보안 로그 (선택)
    print("\n  [5] 보안 이벤트 로그")
    if Path(ATTACK_LOG).exists():
        size = Path(ATTACK_LOG).stat().st_size // 1024
        if DRY_RUN:
            log(f"james_attack_log.jsonl ({size}KB) — 삭제 예정", "WARN")
        else:
            ans2 = input(f"\n  james_attack_log.jsonl ({size}KB) 삭제? (y/n): ").strip().lower()
            if ans2 == 'y':
                delete_file(ATTACK_LOG, "james_attack_log.jsonl")
            else:
                log("james_attack_log.jsonl — 유지", "SKIP")
    else:
        log("james_attack_log.jsonl — 없음", "SKIP")

    # ── 결과 ───────────────────────────────────────────────────
    print()
    print("=" * 58)
    if DRY_RUN:
        print(f"  [DRY-RUN 완료] 실제 삭제된 것 없음")
        print(f"  실제 리셋: python reset_for_production.py")
    else:
        print(f"  ✅ 리셋 완료")
        print(f"  이제 실제 데이터를 투입할 수 있습니다.")
        print()
        print("  다음 단계:")
        print("  1. python server_llmwiki.py  (서버 재시작)")
        print("  2. 업로드 UI에서 실제 문서 업로드")
        print("  3. 어드민 → 자기학습 → 웹 검색 학습")
    print("=" * 58)
    print()


if __name__ == "__main__":
    main()
