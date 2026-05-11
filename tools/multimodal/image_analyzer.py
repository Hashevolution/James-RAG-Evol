"""
PROJECT JAMES - Image Analyzer (Phase 7)

이미지 → 날짜/장소/인물/태그 분석.

처리 순서:
  1. EXIF 메타데이터 추출 (날짜/GPS)
  2. llava:13b 시각 분석 (인물/장소/설명)
  3. 결과 통합 → wiki 저장 구조 반환

VRAM 주의:
  llava:13b (13GB) 로드 전 gemma 언로드 필요
  → is_gemma_loaded() 체크 후 교체
"""

import json
from datetime import datetime
from pathlib import Path

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff"}
RESULT_LOG     = "james_multimodal_log.jsonl"


def _log(event: str, path: str, detail: str):
    try:
        entry = {"time": datetime.now().isoformat(), "event": event,
                 "path": path, "detail": detail[:200], "layer": "image_analyzer"}
        with open(RESULT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ─── EXIF 추출 ───────────────────────────────────────────────

def extract_exif(image_path: str) -> dict:
    """EXIF 메타데이터 추출 (날짜, GPS)."""
    result = {"date": "", "gps_lat": None, "gps_lon": None, "camera": ""}
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS, GPSTAGS

        img  = Image.open(image_path)
        exif = img._getexif()
        if not exif:
            return result

        for tag_id, value in exif.items():
            tag = TAGS.get(tag_id, tag_id)

            if tag == "DateTimeOriginal":
                # "2024:01:15 14:30:00" → "2024-01-15"
                try:
                    dt = datetime.strptime(str(value)[:10], "%Y:%m:%d")
                    result["date"] = dt.strftime("%Y-%m-%d")
                except Exception:
                    result["date"] = str(value)[:10]

            elif tag == "Model":
                result["camera"] = str(value)

            elif tag == "GPSInfo":
                gps = {}
                for k, v in value.items():
                    gps[GPSTAGS.get(k, k)] = v
                # 위도
                if "GPSLatitude" in gps and "GPSLatitudeRef" in gps:
                    lat = _dms_to_decimal(gps["GPSLatitude"])
                    if gps["GPSLatitudeRef"] == "S":
                        lat = -lat
                    result["gps_lat"] = round(lat, 6)
                # 경도
                if "GPSLongitude" in gps and "GPSLongitudeRef" in gps:
                    lon = _dms_to_decimal(gps["GPSLongitude"])
                    if gps["GPSLongitudeRef"] == "W":
                        lon = -lon
                    result["gps_lon"] = round(lon, 6)

    except ImportError:
        print("[IMAGE] Pillow 미설치 — EXIF 건너뜀")
    except Exception as e:
        print(f"[IMAGE] EXIF 추출 실패: {e}")

    return result


def _dms_to_decimal(dms) -> float:
    """도/분/초 → 십진수 변환."""
    try:
        d, m, s = dms
        return float(d) + float(m) / 60 + float(s) / 3600
    except Exception:
        return 0.0


# ─── VRAM 모델 교체 ──────────────────────────────────────────

def _ensure_llava_loaded() -> bool:
    """
    llava 로드 전 gemma 언로드 확인.
    VRAM 16GB에서 둘 다 로드 불가.
    """
    try:
        import requests
        resp = requests.get("http://127.0.0.1:11434/api/ps", timeout=5)
        if resp.status_code != 200:
            return True   # 확인 불가 → 그냥 진행

        running = [m.get("name","") for m in resp.json().get("models", [])]
        gemma_running = any("gemma" in m.lower() for m in running)

        if gemma_running:
            print("[IMAGE] ⚠️ gemma 실행 중 — llava 로드 시 VRAM 초과 가능")
            print("[IMAGE] 팁: ollama stop gemma4:e4b 먼저 실행 권장")

        return True
    except Exception:
        return True


# ─── 메인 분석 함수 ──────────────────────────────────────────

def analyze_image(image_path: str, role: str = "admin") -> dict:
    """
    이미지 종합 분석.

    Returns:
        {
          "path":        str,
          "date":        str,      # EXIF 날짜 또는 llava 감지
          "location":    str,      # llava 감지 장소
          "persons":     list,     # llava 감지 인물
          "tags":        list,     # llava 태그
          "description": str,      # llava 전체 설명
          "camera":      str,      # EXIF 카메라 모델
          "gps_lat":     float,
          "gps_lon":     float,
          "analyzed_at": str,
        }
    """
    p = Path(image_path)

    # 파일 존재 + 형식 확인
    if not p.exists():
        return {"error": f"파일 없음: {image_path}"}
    if p.suffix.lower() not in SUPPORTED_EXTS:
        return {"error": f"지원하지 않는 형식: {p.suffix}"}

    result = {
        "path":        image_path,
        "date":        "",
        "location":    "",
        "persons":     [],
        "tags":        [],
        "description": "",
        "camera":      "",
        "gps_lat":     None,
        "gps_lon":     None,
        "analyzed_at": datetime.now().isoformat(),
    }

    # Step 1: EXIF 추출
    exif = extract_exif(image_path)
    result.update({k: v for k, v in exif.items() if v})
    print(f"[IMAGE] EXIF: date={exif.get('date')} gps={exif.get('gps_lat')}")

    # Step 2: llava 시각 분석
    _ensure_llava_loaded()
    try:
        from llm.providers.llava_client import LlavaClient
        client = LlavaClient()

        if not client.is_available():
            print("[IMAGE] llava 미설치 → EXIF 결과만 반환")
            print("[IMAGE] 설치: ollama pull llava:13b")
            _log("LLAVA_NOT_AVAILABLE", image_path, "llava:13b 미설치")
            return result

        prompt = (
            "이 이미지를 분석해서 다음 항목을 JSON으로 반환해줘:\n"
            "{\n"
            '  "date": "찍힌 날짜 (없으면 빈 문자열)",\n'
            '  "location": "장소 이름 (없으면 빈 문자열)",\n'
            '  "persons": ["인물1", "인물2"],\n'
            '  "tags": ["태그1", "태그2", "태그3"],\n'
            '  "description": "이미지 전체 설명 (한국어, 2문장 이내)"\n'
            "}\n"
            "JSON만 반환. 설명 없이."
        )

        llava_result = client.analyze_image(image_path, prompt=prompt)

        # llava 결과 병합 (EXIF 날짜 우선)
        if not result["date"] and llava_result.get("date"):
            result["date"] = llava_result["date"]
        if llava_result.get("location"):
            result["location"] = llava_result["location"]
        if llava_result.get("persons"):
            result["persons"] = llava_result["persons"]
        if llava_result.get("description"):
            result["description"] = llava_result["description"]
        # 태그 추출
        raw_desc = llava_result.get("description", "")
        result["tags"] = _extract_tags(raw_desc)

    except ImportError:
        print("[IMAGE] llava_client import 실패")
    except Exception as e:
        print(f"[IMAGE] llava 분석 실패: {e}")
        _log("LLAVA_ERROR", image_path, str(e))

    _log("ANALYZED", image_path,
         f"date={result['date']} location={result['location']}")
    print(f"[IMAGE] ✅ 분석 완료: {p.name} | date={result['date']}")

    # ── 원본 보관 + MD 저장 ──────────────────────────────────
    try:
        from tools.multimodal.media_store import store_media
        store_result = store_media(
            src_path    = image_path,
            analysis    = result,
            source_type = "prod",
            move        = False,    # 복사 (원본 유지)
        )
        if store_result["success"]:
            result["stored_path"] = store_result["original_path"]
            result["md_path"]     = store_result["md_path"]
    except Exception as e:
        print(f"[IMAGE] 보관 실패 (분석 결과는 유지): {e}")

    return result


def _extract_tags(text: str) -> list:
    """설명 텍스트에서 태그 자동 추출."""
    tag_map = {
        "실내": ["indoor"], "실외": ["outdoor"], "야외": ["outdoor"],
        "사람": ["people"], "인물": ["people"],
        "음식": ["food"], "건물": ["building"],
        "자연": ["nature"], "풍경": ["landscape"],
        "밤": ["night"], "낮": ["day"],
        "도시": ["city"], "해변": ["beach"],
    }
    tags = []
    for keyword, tag_list in tag_map.items():
        if keyword in text:
            tags.extend(tag_list)
    return list(set(tags))[:10]


# ─── #44 phase 4-C: TrustedContent wrapper ──────────────────

def analyze_image_trusted(image_path: str, role: str = "admin"):
    """[#44 phase 4-C] 이미지 분석 결과를 `TrustedContent` 로 wrap.

    LLM 컨텍스트로 합류 가능한 텍스트 부분 (description / location /
    persons / tags) 를 결합하여 반환. EXIF 메타데이터는 trust 와 무관
    하므로 텍스트에 합류시키지 않는다.

    Trust 분류 (#44 §3):
      - source = "vision" (llava 비전 모델 출력)
      - trust  = "low"    (모델 환각 + 이미지에 새겨진 prompt-injection
                           텍스트가 OCR-like 경로로 흡수될 수 있음)

    호출자는 `default_engine.quarantine(tc)` 로 LLM 합류 직전 검역할 수
    있다. 분석이 실패하면 `text=""` 인 빈 TrustedContent 를 반환하므로
    호출자는 별도 분기를 줄일 수 있다.

    `analyze_image()` (dict 반환) 는 HTTP 엔드포인트가 그대로 사용 중
    이므로 시그니처 변경 없이 유지한다.
    """
    from core.policy_engine import TrustedContent

    result = analyze_image(image_path, role)

    parts = []
    description = result.get("description", "") or ""
    if description:
        parts.append(description)
    location = result.get("location", "") or ""
    if location:
        parts.append(f"장소: {location}")
    persons = result.get("persons", []) or []
    if persons:
        parts.append(f"인물: {', '.join(str(p) for p in persons)}")
    tags = result.get("tags", []) or []
    if tags:
        parts.append(f"태그: {', '.join(str(t) for t in tags)}")
    text = "\n".join(parts)

    return TrustedContent(text=text, source="vision", trust="low")


# ─── wiki 저장 구조 생성 ─────────────────────────────────────

def to_wiki_entity(analysis: dict) -> dict:
    """분석 결과 → wiki entity 구조 변환."""
    name = Path(analysis.get("path","image")).stem
    return {
        "name":         name,
        "type":         "media_image",
        "entity_type":  "media_image",
        "attributes": {
            "file_path":  analysis.get("path",""),
            "date":       analysis.get("date",""),
            "location":   analysis.get("location",""),
            "persons":    analysis.get("persons",[]),
            "tags":       analysis.get("tags",[]),
            "description":analysis.get("description",""),
            "camera":     analysis.get("camera",""),
            "gps_lat":    analysis.get("gps_lat"),
            "gps_lon":    analysis.get("gps_lon"),
        },
        "relations":    [],
        "sensitivity":  "internal",
        "source_type":  "prod",
    }


if __name__ == "__main__":
    print("=== Image Analyzer 자가 테스트 ===\n")

    # EXIF 로직 검증 (이미지 없이)
    from llm.providers.llava_client import LlavaClient
    client = LlavaClient()
    available = client.is_available()
    print(f"  llava 사용 가능: {available}")
    if not available:
        print("  → ollama pull llava:13b 실행 필요")

    # DMS 변환 테스트
    lat = _dms_to_decimal((37, 33, 0))
    ok  = abs(lat - 37.55) < 0.1
    print(f"  {'✅' if ok else '❌'} DMS→decimal: {lat:.4f}")

    # 태그 추출 테스트
    tags = _extract_tags("실외 풍경 사진입니다. 사람들이 도시에서 음식을 먹고 있습니다.")
    ok2  = len(tags) > 0
    print(f"  {'✅' if ok2 else '❌'} 태그 추출: {tags}")
