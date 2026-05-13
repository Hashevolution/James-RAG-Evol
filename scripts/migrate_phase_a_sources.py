"""Knowledge Cascade Phase A — sources 필드 마이그레이션.

docs/design/v0.3-knowledge-cascade.md §3 / §8 / §9 — Phase A.

이 스크립트는 기존 wiki entity 파일들의 frontmatter `relations:` 항목에
``sources`` 필드를 back-fill 한다. confidence 는 손대지 않는다 — 새로
추가되는 sources 1개의 weight 가 기존 confidence 와 같아서 모든 후속
파생 계산이 byte-identical 결과를 낸다.

행동:
  1. ``wiki/`` 전체를 ``wiki.pre-v03-migration/`` 로 미러 복사 (rollback 용)
  2. ``wiki/entity/prod/**/*.md`` 순회
  3. 각 relation 에 ``sources`` 가 없으면 build_legacy_source() 결과 1개
     를 부착. 이미 있으면 skip (멱등)
  4. 통계 출력: scanned / mutated / relations_back_filled / errors

옵션:
  --dry-run         실제 쓰지 않고 영향 범위만 보고
  --root <path>     wiki 루트 (기본: 현재 디렉토리의 wiki/)
  --no-snapshot     스냅샷 건너뛰기 (CI 등에서 이미 백업한 경우)
  --force           ``wiki.pre-v03-migration/`` 가 이미 있어도 덮어쓰기

권장 사용 순서 (운영자):
  1. 서버 중단
  2. python scripts/migrate_phase_a_sources.py --dry-run
     → 영향 범위 확인
  3. python scripts/migrate_phase_a_sources.py
     → 실제 마이그레이션
  4. python scripts/bench.py --suite=step7 --check
     → STEP 7 byte-identical 검증
  5. 서버 재시작

문제 발생 시:
  python scripts/rollback_phase_a_sources.py
"""
from __future__ import annotations

import argparse
import datetime as _dt
import os
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

# Project root 가 sys.path 에 있어야 core.* import 가 동작.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.relations_schema import build_legacy_source

DEFAULT_WIKI_ROOT = Path("wiki")
SNAPSHOT_SUFFIX   = "pre-v03-migration"


# ───────────────────────────────────────────────────────────────
# Snapshot
# ───────────────────────────────────────────────────────────────

def snapshot_wiki(wiki_root: Path, force: bool = False) -> Path:
    """wiki/ → wiki.pre-v03-migration/ 미러 복사. 반환: snapshot 경로.

    이미 존재하면 force=True 일 때만 덮어쓰기. 사용자가 이전 마이그레이션
    의 snapshot 을 실수로 날리는 것 방지.
    """
    snap = wiki_root.with_name(f"{wiki_root.name}.{SNAPSHOT_SUFFIX}")
    if snap.exists():
        if not force:
            raise FileExistsError(
                f"snapshot already exists: {snap}\n"
                f"  → pass --force to overwrite, or remove it manually\n"
                f"     (rollback 시 잃을 수 있으니 신중히)"
            )
        shutil.rmtree(snap)
    print(f"[PHASE_A] snapshot {wiki_root} → {snap}")
    shutil.copytree(wiki_root, snap)
    return snap


# ───────────────────────────────────────────────────────────────
# Migration core
# ───────────────────────────────────────────────────────────────

def _split_frontmatter(text: str) -> tuple[dict | None, str]:
    """frontmatter dict 와 body 를 분리. frontmatter 가 없으면 (None, text)."""
    if not text.startswith("---"):
        return None, text
    end = text.find("---", 3)
    if end < 0:
        return None, text
    try:
        fm = yaml.safe_load(text[3:end]) or {}
    except Exception:
        return None, text
    body_tail = text[end + 3:]
    return fm, body_tail


def _serialize_frontmatter(fm: dict, body_tail: str) -> str:
    return (
        "---\n"
        + yaml.dump(
            fm,
            allow_unicode      = True,
            default_flow_style = False,
            sort_keys          = True,
        )
        + "---"
        + body_tail
    )


def migrate_entity_file(path: Path) -> dict:
    """단일 entity .md 파일을 마이그레이션. 반환: 처리 통계 dict.

    멱등: relation 에 sources 가 이미 있으면 손대지 않는다.
    """
    stats = {
        "scanned":           1,
        "had_no_relations":  0,
        "mutated":           0,
        "relations_back_filled": 0,
        "relations_skipped_already_migrated": 0,
        "errors":            0,
    }
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"[PHASE_A] read fail {path}: {e}")
        stats["errors"] = 1
        return stats

    fm, body_tail = _split_frontmatter(text)
    if fm is None:
        # frontmatter 없는 파일 — 우리 entity 가 아님.
        return stats

    relations = fm.get("relations")
    if not isinstance(relations, list) or not relations:
        stats["had_no_relations"] = 1
        return stats

    # 파일 mtime → ts 추정.
    try:
        mtime_iso = _dt.datetime.fromtimestamp(
            path.stat().st_mtime
        ).isoformat()
    except Exception:
        mtime_iso = None

    file_changed = False
    for rel in relations:
        if not isinstance(rel, dict):
            continue
        if "sources" in rel and isinstance(rel.get("sources"), list):
            stats["relations_skipped_already_migrated"] += 1
            continue
        conf = rel.get("confidence")
        if not isinstance(conf, (int, float)):
            # confidence 없는 relation — synthetic source 만들 근거가 없음.
            # 그대로 두기 (read_relation_sources 가 빈 list 로 처리).
            continue
        rel["sources"] = [build_legacy_source(float(conf), mtime_iso)]
        stats["relations_back_filled"] += 1
        file_changed = True

    if file_changed:
        stats["mutated"] = 1
        # Atomic write: tempfile in same directory → fsync → rename.
        # 같은 dir 에 둬야 rename 이 atomic (cross-fs rename 은 copy 가 됨).
        new_text = _serialize_frontmatter(fm, body_tail)
        tmp_fd, tmp_path = tempfile.mkstemp(
            prefix=path.name + ".",
            suffix=".tmp",
            dir=str(path.parent),
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(new_text)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass  # Windows 일부 환경 — best effort
            os.replace(tmp_path, path)
        except Exception as e:
            print(f"[PHASE_A] write fail {path}: {e}")
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            stats["errors"] = 1
            stats["mutated"] = 0
    return stats


def migrate_wiki(wiki_root: Path, dry_run: bool = False) -> dict:
    """wiki_root/entity/**/**/*.md 를 모두 마이그레이션."""
    totals = {
        "scanned":           0,
        "had_no_relations":  0,
        "mutated":           0,
        "relations_back_filled": 0,
        "relations_skipped_already_migrated": 0,
        "errors":            0,
    }
    entity_root = wiki_root / "entity"
    if not entity_root.is_dir():
        print(f"[PHASE_A] no entity root: {entity_root} — nothing to do")
        return totals

    md_files = sorted(entity_root.rglob("*.md"))
    print(f"[PHASE_A] {len(md_files)} entity files found under {entity_root}")

    if dry_run:
        # Dry-run: read-only inspect.
        for path in md_files:
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                totals["errors"] += 1
                continue
            fm, _ = _split_frontmatter(text)
            if fm is None:
                continue
            relations = fm.get("relations")
            if not isinstance(relations, list) or not relations:
                totals["had_no_relations"] += 1
                continue
            totals["scanned"] += 1
            for rel in relations:
                if not isinstance(rel, dict):
                    continue
                if "sources" in rel and isinstance(rel.get("sources"), list):
                    totals["relations_skipped_already_migrated"] += 1
                else:
                    if isinstance(rel.get("confidence"), (int, float)):
                        totals["relations_back_filled"] += 1
        return totals

    for path in md_files:
        s = migrate_entity_file(path)
        for k in totals:
            totals[k] += s.get(k, 0)
    return totals


# ───────────────────────────────────────────────────────────────
# CLI
# ───────────────────────────────────────────────────────────────

def _format_stats(stats: dict, dry: bool) -> str:
    head = "[DRY-RUN]" if dry else "[APPLIED]"
    return (
        f"{head} scanned={stats['scanned']} "
        f"mutated={stats['mutated']} "
        f"relations_back_filled={stats['relations_back_filled']} "
        f"already_migrated={stats['relations_skipped_already_migrated']} "
        f"no_relations={stats['had_no_relations']} "
        f"errors={stats['errors']}"
    )


def main() -> int:
    p = argparse.ArgumentParser(
        description=(
            "Phase A: add sources field to wiki entity relations. "
            "Idempotent + reversible via the paired rollback script."
        ),
    )
    p.add_argument("--root", type=Path, default=DEFAULT_WIKI_ROOT,
                   help="wiki root (default: ./wiki)")
    p.add_argument("--dry-run", action="store_true",
                   help="report-only; no files written")
    p.add_argument("--no-snapshot", action="store_true",
                   help="skip snapshot (use only when you've backed up "
                        "externally)")
    p.add_argument("--force", action="store_true",
                   help="overwrite existing wiki.pre-v03-migration/ "
                        "snapshot")
    args = p.parse_args()

    wiki_root: Path = args.root
    if not wiki_root.is_dir():
        print(f"[PHASE_A] wiki root not found: {wiki_root}", file=sys.stderr)
        return 2

    if not args.dry_run:
        print(
            "[PHASE_A] WARNING: stop the server before running this. "
            "Concurrent ingest will race the migration."
        )

    if not args.dry_run and not args.no_snapshot:
        try:
            snapshot_wiki(wiki_root, force=args.force)
        except FileExistsError as e:
            print(f"[PHASE_A] {e}", file=sys.stderr)
            return 3

    stats = migrate_wiki(wiki_root, dry_run=args.dry_run)
    print(_format_stats(stats, args.dry_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
