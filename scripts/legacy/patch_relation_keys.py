"""
PROJECT JAMES - Relation Key 통일 스크립트
[REL-1] wiki 파일 내 relation key 혼재 문제 일괄 수정

문제:
  wiki entity 파일의 relations 목록에서
  'label' 키와 'type' 키가 혼재됨.
  graph_rag_engine.py에서 _get_rel_type()으로 런타임 처리하지만
  데이터 레벨에서 통일이 근본 해결책.

전략:
  - 기준 키: 'type' (표준 키로 통일)
  - label만 있는 경우 → ontology.normalize_relation()으로 표준 type 파생 후 'type' 키 추가
  - type만 있는 경우 → 정상 (변경 없음)
  - 둘 다 있는 경우 → type 우선, label 제거
  - 둘 다 없는 경우 → type: "RELATED_TO" 기본값 추가

실행:
  python patch_relation_keys.py            # dry-run (변경 없음)
  python patch_relation_keys.py --apply    # 실제 적용
  python patch_relation_keys.py --report   # 현황 리포트만

출력:
  patch_relation_keys_report.json
"""

import sys
import re
import json
from pathlib import Path
from datetime import datetime

# 런타임 sys.path 설정 (프로젝트 루트에서 실행 가정)
sys.path.insert(0, str(Path(__file__).parent))

APPLY  = "--apply"  in sys.argv
REPORT = "--report" in sys.argv

# ─────────────────────────────────────
# 설정
# ─────────────────────────────────────

try:
    from config import WIKI_DIR
    WIKI_PATH = Path(WIKI_DIR)
except ImportError:
    WIKI_PATH = Path("wiki")
    print(f"[WARNING] config.py 로드 실패 → wiki 경로 기본값: {WIKI_PATH}")

try:
    from core.ontology import normalize_relation
except ImportError:
    def normalize_relation(label: str) -> str:
        return "RELATED_TO"
    print("[WARNING] ontology.py 로드 실패 → normalize_relation 기본값 사용")

REPORT_PATH = "patch_relation_keys_report.json"

# ─────────────────────────────────────
# YAML frontmatter 파서 (경량)
# ─────────────────────────────────────

def _read_frontmatter_raw(filepath: Path):
    """frontmatter 블록을 (raw_text, body) 로 분리"""
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        return None, None, str(e)

    if not content.startswith("---"):
        return None, content, None

    end_idx = content.find("---", 3)
    if end_idx < 0:
        return None, content, "frontmatter 닫힘 없음"

    fm_text = content[3:end_idx].strip()
    body    = content[end_idx + 3:].strip()
    return fm_text, body, None


def _write_frontmatter(filepath: Path, fm_text: str, body: str):
    """frontmatter + body를 파일에 저장"""
    new_content = f"---\n{fm_text}\n---\n\n{body}\n"
    filepath.write_text(new_content, encoding="utf-8")


# ─────────────────────────────────────
# relation key 분석
# ─────────────────────────────────────

def analyze_relation(rel_text: str) -> dict:
    """
    relations 블록 내 단일 항목의 키 현황 분석.
    반환: {"has_type": bool, "has_label": bool, "case": str}
    """
    has_type  = bool(re.search(r"^\s*type\s*:", rel_text, re.MULTILINE))
    has_label = bool(re.search(r"^\s*label\s*:", rel_text, re.MULTILINE))

    if has_type and has_label:
        case = "both"       # 중복 → type 우선, label 제거
    elif has_type:
        case = "type_only"  # 정상
    elif has_label:
        case = "label_only" # type 파생 필요
    else:
        case = "neither"    # 기본값 추가 필요

    return {"has_type": has_type, "has_label": has_label, "case": case}


# ─────────────────────────────────────
# 단일 파일 처리
# ─────────────────────────────────────

def process_file(filepath: Path, apply: bool) -> dict:
    """
    단일 wiki 파일의 relation key 통일 처리.

    Returns:
        {
          "path":     str,
          "issues":   list[str],   # 발견된 문제
          "fixed":    list[str],   # 수정된 내용 (apply=True 시)
          "changed":  bool,
        }
    """
    fm_text, body, err = _read_frontmatter_raw(filepath)

    # 실제 파일 읽기 오류 (권한, 인코딩 등)
    if err is not None:
        return {"path": str(filepath), "issues": [f"파싱 오류: {err}"],
                "fixed": [], "changed": False}

    # frontmatter 없는 파일 (index.md 등 일반 마크다운) → 정상 skip
    if fm_text is None:
        return {"path": str(filepath), "issues": [], "fixed": [], "changed": False,
                "skipped": "frontmatter 없음 (일반 마크다운)"}

    issues  = []
    fixed   = []
    changed = False

    # relations 블록 찾기 (YAML 리스트 항목)
    # 패턴: relations 아래의 - 로 시작하는 블록
    relations_match = re.search(
        r"(^relations\s*:\s*\n)((?:[ \t]+-[ \t]*\n(?:[ \t]+\S.*\n)*)*)",
        fm_text,
        re.MULTILINE,
    )
    if not relations_match:
        return {"path": str(filepath), "issues": [], "fixed": [], "changed": False}

    rel_block_start = relations_match.start(2)
    rel_block_end   = relations_match.end(2)
    rel_block_text  = relations_match.group(2)

    if not rel_block_text.strip():
        return {"path": str(filepath), "issues": [], "fixed": [], "changed": False}

    # 각 relation 항목 처리
    new_rel_lines = []
    # 항목 분리: "  - \n  key: val\n  key2: val2\n  - \n..."
    items = re.split(r"(?=[ \t]+-[ \t]*\n)", rel_block_text)

    for item in items:
        if not item.strip():
            new_rel_lines.append(item)
            continue

        info = analyze_relation(item)

        if info["case"] == "type_only":
            new_rel_lines.append(item)

        elif info["case"] == "both":
            # label 제거
            issues.append("type+label 동시 존재 → label 제거")
            fixed_item  = re.sub(r"[ \t]+label\s*:.*\n", "", item)
            new_rel_lines.append(fixed_item)
            fixed.append("label 키 제거")
            changed = True

        elif info["case"] == "label_only":
            # label 값 추출 → normalize → type 추가
            label_match = re.search(r"label\s*:\s*(.+)", item)
            label_val   = label_match.group(1).strip().strip('"\'') if label_match else "RELATED_TO"
            std_type    = normalize_relation(label_val)
            issues.append(f"label only ('{label_val}') → type: {std_type} 추가")

            # type 줄 추가 (label 바로 앞에)
            indent      = re.match(r"([ \t]+)", item)
            indent_str  = indent.group(1) + "  " if indent else "    "
            fixed_item  = re.sub(
                r"([ \t]+label\s*:)",
                f"{indent_str}type: {std_type}\n\\1",
                item,
                count=1,
            )
            new_rel_lines.append(fixed_item)
            fixed.append(f"type: {std_type} 추가 (from label: {label_val})")
            changed = True

        else:  # neither
            # type: RELATED_TO 기본값 추가
            issues.append("type/label 모두 없음 → type: RELATED_TO 기본값 추가")
            indent     = re.match(r"([ \t]+-[ \t]*\n)", item)
            if indent:
                insert_after = indent.end()
                ind_str      = re.match(r"([ \t]+)", item)
                ind          = ind_str.group(1) + "  " if ind_str else "    "
                fixed_item   = item[:insert_after] + f"{ind}type: RELATED_TO\n" + item[insert_after:]
            else:
                fixed_item = item
            new_rel_lines.append(fixed_item)
            fixed.append("type: RELATED_TO 기본값 추가")
            changed = True

    if changed and apply:
        new_rel_block = "".join(new_rel_lines)
        new_fm_text   = (
            fm_text[:rel_block_start]
            + new_rel_block
            + fm_text[rel_block_end:]
        )
        try:
            _write_frontmatter(filepath, new_fm_text, body)
        except Exception as e:
            return {"path": str(filepath), "issues": issues,
                    "fixed": [], "changed": False, "error": str(e)}

    return {
        "path":    str(filepath),
        "issues":  issues,
        "fixed":   fixed if (changed and apply) else [],
        "changed": changed,
    }


# ─────────────────────────────────────
# 전체 실행
# ─────────────────────────────────────

def run():
    print("\n" + "="*60)
    print("  🔧 Relation Key 통일 스크립트[REL-1]")
    print(f"  모드: {'적용 (--apply)' if APPLY else '드라이런 (변경 없음)'}")
    print(f"  wiki 경로: {WIKI_PATH}")
    print("="*60)

    if not WIKI_PATH.exists():
        print(f"\n  ❌ wiki 경로 없음: {WIKI_PATH}")
        sys.exit(1)

    # 모든 .md 파일 수집
    md_files = list(WIKI_PATH.rglob("*.md"))
    print(f"\n  대상 파일: {len(md_files)}개\n")

    results       = []
    total_issues  = 0
    total_changed = 0
    total_skipped = 0   # frontmatter 없는 파일 (index.md 등)

    for filepath in md_files:
        result = process_file(filepath, apply=APPLY)
        results.append(result)

        # frontmatter 없는 파일은 집계에서 제외 (정상 skip)
        if result.get("skipped"):
            total_skipped += 1
            continue

        if result["issues"]:
            total_issues += len(result["issues"])
            if result["changed"]:
                total_changed += 1
                icon = "✅ 수정" if APPLY else "🔍 발견"
            else:
                icon = "⚠️  감지"
            print(f"  {icon} {Path(result['path']).name}")
            for issue in result["issues"][:3]:
                print(f"       └─ {issue}")

    entity_files = len(md_files) - total_skipped

    # 리포트
    print("\n" + "="*60)
    print("  📊 결과 요약")
    print(f"  전체 파일:   {len(md_files)}개")
    print(f"  entity 파일: {entity_files}개 (frontmatter 있음)")
    print(f"  skip 파일:   {total_skipped}개 (일반 마크다운, 정상)")
    print(f"  문제 발견:   {total_issues}개")
    print(f"  수정 {'완료' if APPLY else '예정'}:   {total_changed}개 파일")
    if total_issues == 0:
        print("\n  ✅ 모든 entity 파일의 relation key 정상")
    elif not APPLY and total_changed > 0:
        print("\n  💡 실제 적용: python patch_relation_keys.py --apply")
    print("="*60)

    report = {
        "timestamp":      datetime.now().isoformat(),
        "mode":           "apply" if APPLY else "dry-run",
        "wiki_path":      str(WIKI_PATH),
        "total_files":    len(md_files),
        "entity_files":   entity_files,
        "skipped_files":  total_skipped,
        "total_issues":   total_issues,
        "total_changed":  total_changed,
        "results":        [r for r in results if not r.get("skipped")],
    }
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  💾 리포트: {REPORT_PATH}")

    return total_issues == 0


# ─────────────────────────────────────
# 자가 테스트 (--test)
# ─────────────────────────────────────

def self_test():
    print("=== patch_relation_keys 단위 테스트 ===\n")
    cases = [
        ("type만",      "  type: STUDIES\n  confidence: 0.9",  "type_only"),
        ("label만",     "  label: 공부\n  confidence: 0.9",    "label_only"),
        ("type+label",  "  type: STUDIES\n  label: 공부\n",    "both"),
        ("둘 다 없음",  "  confidence: 0.9\n  target: X",       "neither"),
    ]
    passed = 0
    for name, text, expected in cases:
        result = analyze_relation(text)
        ok = result["case"] == expected
        passed += int(ok)
        print(f"  {'✅' if ok else '❌'} {name}: {result['case']} (기대={expected})")

    print(f"\n  결과: {passed}/{len(cases)} PASS")


if __name__ == "__main__":
    if "--test" in sys.argv:
        self_test()
    else:
        ok = run()
        sys.exit(0 if ok else 1)
