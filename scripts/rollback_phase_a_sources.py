"""Knowledge Cascade Phase A — rollback to pre-migration state.

마이그레이션 결과가 잘못됐을 때 ``wiki.pre-v03-migration/`` snapshot
을 ``wiki/`` 자리로 되돌린다.

사용:
  python scripts/rollback_phase_a_sources.py
  python scripts/rollback_phase_a_sources.py --root path/to/wiki

안전 장치:
  - snapshot 이 없으면 거부 (실수로 wiki 삭제 방지)
  - 기본은 ``wiki/`` 도 ``wiki.rollback-trash/`` 로 옮긴 뒤 snapshot 을
    위치로 이동. --force 옵션으로 직접 삭제 가능.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

DEFAULT_WIKI_ROOT = Path("wiki")
SNAPSHOT_SUFFIX   = "pre-v03-migration"
TRASH_SUFFIX      = "rollback-trash"


def rollback(wiki_root: Path, force: bool = False) -> int:
    snap = wiki_root.with_name(f"{wiki_root.name}.{SNAPSHOT_SUFFIX}")
    if not snap.is_dir():
        print(f"[ROLLBACK] snapshot not found: {snap}", file=sys.stderr)
        print("           (migrate_phase_a_sources.py 가 --no-snapshot "
              "로 실행됐거나 이미 rollback 됐을 수 있음)", file=sys.stderr)
        return 2

    print(f"[ROLLBACK] stop the server before continuing.")
    if not wiki_root.exists():
        print(f"[ROLLBACK] {wiki_root} 가 없음 — snapshot 으로 바로 이동")
        snap.rename(wiki_root)
        print(f"[ROLLBACK] done: {wiki_root}")
        return 0

    trash = wiki_root.with_name(f"{wiki_root.name}.{TRASH_SUFFIX}")
    if trash.exists():
        if not force:
            print(f"[ROLLBACK] {trash} 가 이미 있음 — "
                  f"이전 rollback 시도 잔재일 수 있음. --force 로 삭제 "
                  f"가능하지만 그 안의 내용은 영구 손실됨.",
                  file=sys.stderr)
            return 3
        shutil.rmtree(trash)

    print(f"[ROLLBACK] move {wiki_root} → {trash}")
    wiki_root.rename(trash)
    print(f"[ROLLBACK] move {snap} → {wiki_root}")
    snap.rename(wiki_root)
    print(f"[ROLLBACK] done.")
    print(f"           trash kept at {trash} for manual inspection. "
          f"remove when confident.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="Restore wiki/ from the Phase A migration snapshot.",
    )
    p.add_argument("--root", type=Path, default=DEFAULT_WIKI_ROOT,
                   help="wiki root (default: ./wiki)")
    p.add_argument("--force", action="store_true",
                   help="overwrite existing wiki.rollback-trash/")
    args = p.parse_args()
    return rollback(args.root, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())
