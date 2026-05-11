"""
PROJECT JAMES - Media Store (Phase 7)

사진/영상/오디오 원본 파일을 날짜별 폴더에 보관.
챗 지시로 폴더/인물/태그 지정 가능.

자동 분류:
  wiki/media/prod/images/2024-03/photo.jpg
  wiki/media/prod/videos/2024-03/video.mp4
  wiki/media/prod/audio/2024-03/record.mp3

챗 지시 커스텀:
  wiki/media/prod/persons/김철수/2024-03-15_photo.jpg
  wiki/media/prod/places/제주도/2024-03-15_video.mp4
  wiki/media/prod/custom/가족여행/2024-03-15_audio.mp3

날짜 우선순위:
  1. EXIF 촬영일
  2. 파일 수정일
  3. 오늘 날짜
"""

import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"}
VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".wma"}

try:
    from config import WIKI_DIR, BASE_DIR as _BASE_DIR
    # 절대 경로 강제 — 상대 경로면 BASE_DIR 기준으로 변환
    if os.path.isabs(WIKI_DIR):
        MEDIA_BASE = os.path.join(WIKI_DIR, "media")
    else:
        MEDIA_BASE = os.path.join(os.path.abspath(_BASE_DIR), "wiki", "media")
except ImportError:
    MEDIA_BASE = os.path.join(os.path.abspath("."), "wiki", "media")

print(f"[MEDIA_STORE] MEDIA_BASE: {MEDIA_BASE}")


# ─── 날짜 결정 ───────────────────────────────────────────────

def _resolve_date(file_path: str, exif_date: str = "") -> str:
    """Returns 'YYYY-MM' — 자동 분류 폴더용."""
    if exif_date:
        try:
            return datetime.strptime(exif_date[:10], "%Y-%m-%d").strftime("%Y-%m")
        except Exception:
            pass
    try:
        mtime = os.path.getmtime(file_path)
        return datetime.fromtimestamp(mtime).strftime("%Y-%m")
    except Exception:
        pass
    return datetime.now().strftime("%Y-%m")


def _resolve_full_date(file_path: str, exif_date: str = "") -> str:
    """Returns 'YYYY-MM-DD' — 파일명 prefix용."""
    if exif_date:
        try:
            return datetime.strptime(exif_date[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
        except Exception:
            pass
    try:
        mtime = os.path.getmtime(file_path)
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
    except Exception:
        pass
    return datetime.now().strftime("%Y-%m-%d")


# ─── 미디어 타입 ─────────────────────────────────────────────

def _media_type(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    if ext in IMAGE_EXTS: return "images"
    if ext in VIDEO_EXTS: return "videos"
    if ext in AUDIO_EXTS: return "audio"
    return None


# ─── 폴더 생성 ───────────────────────────────────────────────

def _make_dest_dir(media_type: str, year_month: str,
                   source_type: str = "prod") -> Path:
    dest = Path(MEDIA_BASE) / source_type / media_type / year_month
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def _make_custom_dir(folder_path: str, source_type: str = "prod") -> Path:
    dest = Path(MEDIA_BASE) / source_type / folder_path
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def _unique_path(dest_dir: Path, filename: str) -> Path:
    """중복 파일명 → _N 붙이기."""
    p = dest_dir / filename
    if not p.exists():
        return p
    stem, suffix = Path(filename).stem, Path(filename).suffix
    n = 1
    while p.exists():
        p = dest_dir / f"{stem}_{n}{suffix}"
        n += 1
    return p


# ─── 챗 지시 파서 ────────────────────────────────────────────

class InstructionParser:
    """
    챗 지시에서 폴더/인물/태그 파싱.

    예시:
      "김철수 폴더에 저장해줘"       → persons/김철수
      "제주도 여행 폴더로"           → places/제주도
      "가족여행 태그로 저장"         → custom/가족여행
      "회의록 폴더에 저장해줘"       → custom/회의록
      '"프로젝트A" 폴더에'           → custom/프로젝트A
    """

    PERSON_PATTERNS = [
        # 씨/님 명시 — 가장 확실한 인물 판별
        r"([가-힣]{2,5})\s*(씨|님)\s*폴더",
        # 폴더에 저장 — 단, 여행/장소/투어 단어 제외
        r"([가-힣]{2,4}(?<!여행)(?<!여행지)(?<!장소))\s*폴더[에로]?\s*저장",
        r"([A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\s*(?:folder|폴더)",
    ]
    PLACE_PATTERNS = [
        r"([가-힣]{2,8}여행)\s*(?:폴더|에|로)?",               # XX여행
        r"([가-힣]{2,6}(?:도|시|구|동|리|투어))\s*(?:폴더|에|로)?",
        r"(trip|travel)\s+(?:to\s+)?([a-zA-Z가-힣]+)",
    ]
    FOLDER_PATTERNS = [
        r'["\']([^"\']{1,30})["\']\s*폴더',                    # "폴더명" 폴더
        r'([가-힣a-zA-Z0-9_/\-]{2,20})\s*폴더[에로]?\s*저장',  # 폴더명 폴더에 저장
        r'([가-힣a-zA-Z0-9_/\-]{2,20})\s*[에로]\s*저장',       # 폴더명에 저장
        r'folder[:\s]+([a-zA-Z가-힣0-9_/\-]+)',                # folder: 폴더명
    ]
    TAG_PATTERNS = [
        r'#([가-힣a-zA-Z0-9_]+)',
        r'태그[:\s]+([가-힣a-zA-Z0-9_,\s]+)',
    ]

    def parse(self, instruction: str) -> dict:
        result = {
            "folder_type": "custom",
            "folder_name": "",
            "full_path":   "",
            "tags":        [],
            "persons":     [],
        }

        # 1. 인물명 (씨/님 명시된 경우만)
        for pattern in self.PERSON_PATTERNS:
            m = re.search(pattern, instruction)
            if m:
                name = m.group(1).strip()
                if len(name) >= 2:
                    result.update({"folder_type":"persons","folder_name":name})
                    result["persons"].append(name)
                    break

        # 2. 장소 (여행/도/시 등 명시)
        if not result["folder_name"]:
            for pattern in self.PLACE_PATTERNS:
                m = re.search(pattern, instruction)
                if m:
                    place = m.group(1).strip()
                    if len(place) >= 2:
                        result.update({"folder_type":"places","folder_name":place})
                        break

        # 3. 폴더 직접 지정 (따옴표 우선)
        if not result["folder_name"]:
            # 따옴표 폴더명 먼저
            m = re.search(self.FOLDER_PATTERNS[0], instruction)
            if m and len(m.group(1).strip()) >= 1:
                result.update({"folder_type":"custom",
                               "folder_name":m.group(1).strip()})
            else:
                for pattern in self.FOLDER_PATTERNS[1:]:
                    m = re.search(pattern, instruction)
                    if m:
                        folder = m.group(1).strip().strip("/\\")
                        if len(folder) >= 1:
                            result.update({"folder_type":"custom",
                                           "folder_name":folder})
                            break

        # 4. 태그
        for pattern in self.TAG_PATTERNS:
            for tag in re.findall(pattern, instruction):
                result["tags"].extend(
                    [t.strip() for t in tag.split(",") if t.strip()]
                )

        if result["folder_name"]:
            result["full_path"] = (
                f"{result['folder_type']}/{result['folder_name']}"
            )
        return result


# ─── 원본 보관 ───────────────────────────────────────────────

def store_original(
    src_path:    str,
    exif_date:   str  = "",
    source_type: str  = "prod",
    move:        bool = False,
) -> Tuple[bool, str]:
    """자동 분류 — YYYY-MM 폴더에 원본 보관."""
    p = Path(src_path)
    if not p.exists():
        return False, f"파일 없음: {src_path}"

    media_type = _media_type(src_path)
    if not media_type:
        return False, f"지원하지 않는 형식: {p.suffix}"

    year_month = _resolve_date(src_path, exif_date)
    dest_dir   = _make_dest_dir(media_type, year_month, source_type)
    dest_path  = _unique_path(dest_dir, p.name)

    try:
        if move:
            shutil.move(str(src_path), str(dest_path))
        else:
            shutil.copy2(str(src_path), str(dest_path))
        print(f"[MEDIA_STORE] {'이동' if move else '복사'}: {p.name} → "
              f"{year_month}/{dest_path.name}")
        return True, str(dest_path)
    except Exception as e:
        return False, f"보관 실패: {e}"


# ─── 분석 결과 MD 저장 ───────────────────────────────────────

def store_analysis_md(
    analysis:    dict,
    source_type: str          = "prod",
    custom_dir:  Optional[Path] = None,
) -> Tuple[bool, str]:
    """분석 결과 MD 저장 (원본과 같은 폴더)."""
    file_path  = analysis.get("path", "")
    p          = Path(file_path)
    media_type = _media_type(file_path) or "images"
    exif_date  = analysis.get("date", "")

    if custom_dir:
        dest_dir = custom_dir
    else:
        year_month = _resolve_date(file_path, exif_date)
        dest_dir   = _make_dest_dir(media_type, year_month, source_type)

    md_path = _unique_path(dest_dir, f"{p.stem}.md")
    md      = _make_md(analysis, media_type)
    try:
        md_path.write_text(md, encoding="utf-8")
        print(f"[MEDIA_STORE] MD 저장: {md_path.name}")
        return True, str(md_path)
    except Exception as e:
        return False, f"MD 저장 실패: {e}"


def _make_md(analysis: dict, media_type: str) -> str:
    p    = Path(analysis.get("path", ""))
    name = p.stem
    now  = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# {name}", "",
        "```yaml",
        f"entity_type: {media_type[:-1]}",
        f"name:        {name}",
        f"date:        {analysis.get('date', '')}",
        f"analyzed_at: {analysis.get('analyzed_at', now)}",
        "source_type: prod",
        "```", "", "## 분석 결과", "",
    ]
    if analysis.get("custom_folder"):
        lines.append(f"**분류:** {analysis['custom_folder']}")
    if media_type in ("images", "audio"):
        for key, label in [("location","장소"),("persons","인물"),
                            ("tags","태그"),("description","설명"),
                            ("camera","카메라")]:
            val = analysis.get(key)
            if val:
                v = ", ".join(val) if isinstance(val, list) else val
                lines.append(f"**{label}:** {v}")
    elif media_type == "videos":
        dur = analysis.get("duration_sec", 0)
        lines.append(f"**길이:** {int(dur//60)}분 {int(dur%60)}초")
        if analysis.get("summary"):
            lines += ["", "**요약:**", analysis["summary"]]
        if analysis.get("transcript"):
            lines += ["", "**음성:**",
                      f"> {analysis['transcript'][:300]}"]
    return "\n".join(lines) + "\n"


# ─── 통합 처리 ───────────────────────────────────────────────

def store_media(
    src_path:    str,
    analysis:    dict,
    source_type: str  = "prod",
    move:        bool = False,
) -> dict:
    """자동 분류 저장 (기존 동작 유지)."""
    exif_date  = analysis.get("date", "")
    year_month = _resolve_date(src_path, exif_date)

    ok1, orig_path = store_original(src_path, exif_date, source_type, move)
    if ok1:
        analysis["path"] = orig_path

    ok2, md_path = store_analysis_md(analysis, source_type)

    return {
        "original_path": orig_path if ok1 else "",   # 하위 호환
        "stored_path":   orig_path if ok1 else "",   # 통일된 키
        "md_path":       md_path   if ok2 else "",
        "year_month":    year_month,
        "success":       ok1,
    }


def store_with_instruction(
    src_path:    str,
    instruction: str,
    analysis:    dict = None,
    source_type: str  = "prod",
    move:        bool = False,
) -> dict:
    """
    챗 지시대로 커스텀 폴더에 날짜 prefix 파일명으로 보관.

    Args:
        src_path:    원본 파일 경로
        instruction: 챗 지시 ("김철수 폴더에 저장해줘" 등)
        analysis:    분석 결과 dict (날짜 정보 활용)
        source_type: 'prod' or 'test'
        move:        True=이동, False=복사

    Returns:
        {
          "success":     bool,
          "stored_path": str,   # 보관된 파일 경로
          "md_path":     str,   # MD 경로
          "folder":      str,   # 저장 폴더
          "date_prefix": str,   # 파일명 날짜 prefix
          "parsed":      dict,  # 파싱 결과
        }
    """
    result = {"success":False,"stored_path":"","md_path":"",
              "folder":"","date_prefix":"","parsed":{}}

    p = Path(src_path)
    if not p.exists():
        result["error"] = f"파일 없음: {src_path}"
        return result

    # 지시 파싱
    parsed = InstructionParser().parse(instruction)
    result["parsed"] = parsed

    if not parsed["full_path"]:
        # 폴더 지정 없으면 자동 분류 fallback
        print("[MEDIA_STORE] 폴더 미지정 — 자동 분류")
        return store_media(src_path, analysis or {}, source_type, move)

    # 날짜 prefix (YYYY-MM-DD_)
    exif_date   = (analysis or {}).get("date", "")
    date_prefix = _resolve_full_date(src_path, exif_date)
    result["date_prefix"] = date_prefix

    # 파일명: 2024-03-15_photo.jpg
    new_filename = f"{date_prefix}_{p.name}"
    dest_dir     = _make_custom_dir(parsed["full_path"], source_type)
    dest_path    = _unique_path(dest_dir, new_filename)
    result["folder"] = str(dest_dir)

    # 파일 보관
    try:
        if move:
            shutil.move(str(src_path), str(dest_path))
        else:
            shutil.copy2(str(src_path), str(dest_path))
        result["stored_path"] = str(dest_path)
        print(f"[MEDIA_STORE] ✅ {parsed['full_path']}/{dest_path.name}")
    except Exception as e:
        result["error"] = f"저장 실패: {e}"
        return result

    # 분석 MD 저장
    if analysis:
        analysis["path"]          = str(dest_path)
        analysis["custom_folder"] = parsed["full_path"]
        analysis["tags"]          = list(set(
            analysis.get("tags", []) + parsed["tags"]
        ))
        ok2, md_path = store_analysis_md(
            analysis, source_type, custom_dir=dest_dir
        )
        result["md_path"] = md_path if ok2 else ""

    result["success"] = True
    print(f"[MEDIA_STORE] 폴더={parsed['full_path']} 날짜={date_prefix}")
    return result


if __name__ == "__main__":
    import tempfile
    print("=== Media Store 자가 테스트 ===\n")

    parser = InstructionParser()
    cases = [
        ("김철수 폴더에 저장해줘",       "persons", "김철수"),
        ("제주도여행 폴더로 저장",        "places",  "제주도여행"),
        ("가족여행 태그로 저장해줘",      "custom",  "가족여행"),
        ('"회의록" 폴더에 저장',          "custom",  "회의록"),
        ("documents 폴더에 저장해줘",     "custom",  "documents"),
    ]

    passed = 0
    for instruction, exp_type, exp_name in cases:
        r  = parser.parse(instruction)
        ok = r["folder_type"] == exp_type and r["folder_name"] == exp_name
        passed += int(ok)
        icon = "✅" if ok else "❌"
        print(f"  {icon} '{instruction}' → {r['folder_type']}/{r['folder_name']}")

    print(f"\n  파싱: {passed}/{len(cases)} PASS")

    # store_with_instruction 실제 동작
    print()
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp.write(b"fake"); tmp.close()

    r = store_with_instruction(
        src_path    = tmp.name,
        instruction = "김철수 폴더에 저장해줘",
        analysis    = {"date":"2024-03-15","tags":[]},
        source_type = "test",
        move        = False,
    )
    print(f"  {'✅' if r['success'] else '❌'} 커스텀 저장: {r.get('stored_path','')}")
    print(f"  폴더: {r.get('folder','')}")
    print(f"  날짜prefix: {r.get('date_prefix','')}")

    os.unlink(tmp.name)
    if r.get("stored_path") and os.path.exists(r["stored_path"]):
        os.remove(r["stored_path"])
