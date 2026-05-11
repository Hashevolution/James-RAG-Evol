"""
PROJECT JAMES - Entity 필드 일괄 패치 (Phase 4.5)

Phase 4.5 변경:
  [P4.5-PATCH-1] source_type 추가
                 기존 entity 'internal' → 'prod' 마이그레이션
  [P4.5-PATCH-2] prod/test 폴더 구조 스캔
  [P4.5-PATCH-3] verified: false 추가
  [P4.5-PATCH-4] sensitivity + owner 누락 시 추가 (기존 기능 유지)

실행:
  python patch_abac_fields.py              # 전체 패치
  python patch_abac_fields.py --dry-run   # 미리보기 (파일 변경 없음)
  python patch_abac_fields.py --prod      # prod 폴더만
  python patch_abac_fields.py --test      # test 폴더만
"""

import sys
import yaml
from pathlib import Path
from datetime import datetime

SENSITIVITY_MAP = {
    "person":   "confidential",
    "org":      "internal",
    "document": "confidential",
    "concept":  "public",
}
ENTITY_TYPES = ["person", "concept", "org", "document"]


def patch(wiki_dir: str, dry_run: bool = False, target_source: str = "all"):
    entity_base = Path(wiki_dir) / "entity"
    mode_label  = "[DRY-RUN] " if dry_run else ""

    # 스캔 경로 수집
    scan_paths = []

    if target_source in ("prod", "all"):
        p = entity_base / "prod"
        if p.exists(): scan_paths.append(("prod", p))

    if target_source in ("test", "all"):
        p = entity_base / "test"
        if p.exists(): scan_paths.append(("test", p))

    # 레거시: /entity/{type}/ 직접 구조 (Phase 4.5 이전 생성분)
    if not scan_paths or target_source == "all":
        for etype in ENTITY_TYPES:
            if (entity_base / etype).exists():
                scan_paths.append(("prod", entity_base))
                break

    if not scan_paths:
        print(f"[PATCH] entity 폴더 없음: {entity_base}")
        return {"patched": 0, "skipped": 0, "errors": 0, "fields_added": {}}

    patched = skipped = errors = 0
    fields_added: dict = {}

    for source_type, base_path in scan_paths:
        for etype in ENTITY_TYPES:
            d = base_path / etype
            if not d.exists():
                continue

            for f in sorted(d.glob("*.md")):
                try:
                    content = f.read_text(encoding="utf-8")
                    if not content.startswith("---"):
                        skipped += 1; continue

                    end = content.find("---", 3)
                    if end < 0:
                        skipped += 1; continue

                    fm   = yaml.safe_load(content[3:end]) or {}
                    body = content[end + 4:]

                    added     = []
                    changed   = False

                    # sensitivity [ABAC]
                    if "sensitivity" not in fm:
                        fm["sensitivity"] = SENSITIVITY_MAP.get(etype, "internal")
                        added.append("sensitivity"); changed = True

                    # owner [ABAC]
                    if "owner" not in fm:
                        fm["owner"] = "system"
                        added.append("owner"); changed = True

                    # source_type [P4.5-PATCH-1]
                    if "source_type" not in fm:
                        fm["source_type"] = source_type
                        added.append("source_type"); changed = True
                    elif fm.get("source_type") == "internal":
                        # 구버전 'internal' → 'prod' 마이그레이션
                        fm["source_type"] = "prod"
                        added.append("source_type(internal→prod)"); changed = True

                    # verified [P4.5-PATCH-3]
                    if "verified" not in fm:
                        fm["verified"] = False
                        added.append("verified"); changed = True

                    if not changed:
                        skipped += 1; continue

                    fm["updated_at"] = datetime.now().isoformat()

                    for field in added:
                        fields_added[field] = fields_added.get(field, 0) + 1

                    new_content = (
                        "---\n"
                        + yaml.dump(fm, allow_unicode=True,
                                    default_flow_style=False).strip()
                        + "\n---\n\n"
                        + body
                    )

                    if not dry_run:
                        f.write_text(new_content, encoding="utf-8")

                    patched += 1
                    print(f"  {mode_label}✅ {etype}/{f.name} +{added}")

                except Exception as e:
                    errors += 1
                    print(f"  ❌ {f.name}: {e}")

    return {"patched": patched, "skipped": skipped, "errors": errors,
            "fields_added": fields_added}


def print_result(result: dict, dry_run: bool):
    mode = "DRY-RUN 결과" if dry_run else "패치 완료"
    print(f"\n{'='*50}")
    print(f"  {mode}")
    print(f"  패치: {result['patched']}개 | 스킵: {result['skipped']}개 | 오류: {result['errors']}개")
    if result["fields_added"]:
        print("\n  추가 필드 통계:")
        for field, count in sorted(result["fields_added"].items()):
            print(f"    {field:30s}: {count}개")
    if dry_run:
        print("\n  ※ 실제 적용: python patch_abac_fields.py")
    print(f"{'='*50}")


if __name__ == "__main__":
    args          = sys.argv[1:]
    dry_run       = "--dry-run" in args or "--dry" in args
    target_source = "all"
    if "--prod"   in args: target_source = "prod"
    if "--test"   in args: target_source = "test"
    if "--legacy" in args: target_source = "legacy"

    try:
        from config import WIKI_DIR
    except ImportError:
        # config import 실패 시 — 현재 스크립트 위치 기준
        import os as _os
        WIKI_DIR = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "wiki")

    mode = "DRY-RUN" if dry_run else "실제 패치"
    print(f"\n[PATCH] Entity 필드 일괄 패치 ({mode}, target={target_source})")
    print(f"[PATCH] WIKI_DIR: {WIKI_DIR}\n")

    result = patch(WIKI_DIR, dry_run=dry_run, target_source=target_source)
    print_result(result, dry_run)
