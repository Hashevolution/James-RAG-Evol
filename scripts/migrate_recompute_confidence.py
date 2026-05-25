"""Knowledge Cascade hotfix -- confidence noisy-OR 재계산.

docs/design/v0.3-knowledge-cascade.md §3 -- Phase A → E 가 머지될 때
``compute_confidence_from_sources`` 가 clamped sum 으로 구현되어 있던
defect 를 noisy-OR (`P = 1 - Π(1 - w_i)`) 로 정정.

이 스크립트는 기존 wiki entity 파일들을 순회하면서 **2개 이상의
source 를 가진 relation 의 confidence 만** 다시 derive 한다. 단일
source relation 은 두 공식이 동일값을 돌려주므로 건드리지 않는다.

행동:
  1. ``wiki/`` 전체를 ``wiki.pre-noisy-or-fix/`` 로 미러 복사 (rollback)
  2. ``wiki/entity/prod/**/*.md`` 순회
  3. 각 relation 의 ``sources`` 가 2개 이상이면 ``confidence`` 를
     noisy-OR 결과로 재기록. 차이가 0 (이미 정합) 이면 mutated 안 함.
  4. 통계 출력: scanned / multi_source_relations / confidence_updated /
     max_delta / errors

옵션:
  --dry-run         실제 쓰지 않고 영향 범위만 보고
  --root <path>     wiki 루트 (기본: 현재 디렉토리의 wiki/)
  --no-snapshot     스냅샷 건너뛰기 (CI 등에서 이미 백업한 경우)
  --force           snapshot 디렉토리가 이미 있어도 덮어쓰기

권장 사용 순서 (운영자):
  1. 서버 중단
  2. python scripts/migrate_recompute_confidence.py --dry-run
     → 영향 범위 + max_delta 확인
  3. python scripts/migrate_recompute_confidence.py
     → 실제 재계산
  4. python scripts/bench.py --suite=step7
     → STEP 7 graph_paths 회귀 측정 (multi-source relation 이 retrieval
        score 에 미치는 영향)
  5. 서버 재시작

문제 발생 시:
  rmdir /S /Q wiki && move wiki.pre-noisy-or-fix wiki
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.relations_schema import compute_confidence_from_sources

DEFAULT_WIKI_ROOT = Path("wiki")
SNAPSHOT_SUFFIX   = "pre-noisy-or-fix"


def snapshot_wiki(wiki_root: Path, force: bool = False) -> Path:
    snap = wiki_root.with_name(f"{wiki_root.name}.{SNAPSHOT_SUFFIX}")
    if snap.exists():
        if not force:
            raise FileExistsError(
                f"snapshot already exists: {snap}\n"
                f"  → pass --force to overwrite, or remove it manually"
            )
        shutil.rmtree(snap)
    print(f"[NOISY_OR_FIX] snapshot {wiki_root} → {snap}")
    shutil.copytree(wiki_root, snap)
    return snap


def split_frontmatter(text: str) -> tuple[dict, str] | tuple[None, str]:
    """`---`\\n...`---` 형식의 markdown frontmatter 분리."""
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 4)
    if end < 0:
        return None, text
    fm_raw = text[4:end].lstrip("\n")
    body   = text[end + 4:].lstrip("\n")
    try:
        fm = yaml.safe_load(fm_raw) or {}
    except yaml.YAMLError:
        return None, text
    if not isinstance(fm, dict):
        return None, text
    return fm, body


def join_frontmatter(fm: dict, body: str) -> str:
    return (
        "---\n"
        + yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).rstrip()
        + "\n---\n\n"
        + body
    )


def recompute_file(path: Path, dry_run: bool) -> dict:
    """한 entity .md 의 multi-source relation confidence 재계산.

    반환: {"multi_source": N, "updated": M, "max_delta": float}
    """
    text = path.read_text(encoding="utf-8")
    fm, body = split_frontmatter(text)
    if fm is None:
        return {"multi_source": 0, "updated": 0, "max_delta": 0.0}

    relations = fm.get("relations")
    if not isinstance(relations, list):
        return {"multi_source": 0, "updated": 0, "max_delta": 0.0}

    multi_source = 0
    updated      = 0
    max_delta    = 0.0
    mutated      = False

    for rel in relations:
        if not isinstance(rel, dict):
            continue
        sources = rel.get("sources")
        if not isinstance(sources, list) or len(sources) < 2:
            continue
        multi_source += 1
        new_conf = compute_confidence_from_sources(sources)
        old_conf = rel.get("confidence")
        if not isinstance(old_conf, (int, float)):
            continue
        delta = abs(float(old_conf) - new_conf)
        if delta < 1e-4:
            continue
        max_delta = max(max_delta, delta)
        updated += 1
        rel["confidence"] = new_conf
        mutated = True

    if mutated and not dry_run:
        path.write_text(join_frontmatter(fm, body), encoding="utf-8")

    return {
        "multi_source": multi_source,
        "updated":      updated,
        "max_delta":    max_delta,
    }


def migrate_wiki(wiki_root: Path, dry_run: bool) -> dict:
    entity_root = wiki_root / "entity" / "prod"
    if not entity_root.exists():
        print(f"[NOISY_OR_FIX] no entity root at {entity_root} -- nothing to do")
        return {"files_scanned": 0, "multi_source": 0,
                "updated": 0, "max_delta": 0.0, "errors": 0}

    totals = {"files_scanned": 0, "multi_source": 0,
              "updated": 0, "max_delta": 0.0, "errors": 0}

    for md in sorted(entity_root.rglob("*.md")):
        totals["files_scanned"] += 1
        try:
            stats = recompute_file(md, dry_run=dry_run)
        except Exception as e:
            totals["errors"] += 1
            print(f"[NOISY_OR_FIX] ERROR {md}: {e}")
            continue
        totals["multi_source"] += stats["multi_source"]
        totals["updated"]      += stats["updated"]
        totals["max_delta"]     = max(totals["max_delta"], stats["max_delta"])

    return totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run",     action="store_true")
    parser.add_argument("--no-snapshot", action="store_true")
    parser.add_argument("--force",       action="store_true")
    parser.add_argument("--root", type=Path, default=DEFAULT_WIKI_ROOT)
    args = parser.parse_args()

    if not args.root.exists():
        print(f"[NOISY_OR_FIX] wiki root not found: {args.root}")
        sys.exit(2)

    if not args.dry_run and not args.no_snapshot:
        snapshot_wiki(args.root, force=args.force)
    elif args.dry_run:
        print("[NOISY_OR_FIX] dry-run -- no snapshot, no writes")

    totals = migrate_wiki(args.root, dry_run=args.dry_run)
    print("[NOISY_OR_FIX] result:")
    print(f"  files_scanned       = {totals['files_scanned']}")
    print(f"  multi_source_rels   = {totals['multi_source']}")
    print(f"  confidence_updated  = {totals['updated']}")
    print(f"  max_delta           = {totals['max_delta']:.4f}")
    print(f"  errors              = {totals['errors']}")
    if args.dry_run:
        print("[NOISY_OR_FIX] dry-run -- no files were modified")


if __name__ == "__main__":
    main()
