"""
PROJECT JAMES - Video Analyzer (Phase 7)

영상 분석 3단계:
  Step 1. 프레임 추출 (opencv, 10초마다 1장)
  Step 2. 음성 추출 → Whisper 텍스트 변환
  Step 3. 프레임별 이미지 분석 (llava)

보안:
  프레임 임시파일 → 분석 후 즉시 삭제
  VRAM: llava 로드 전 gemma 언로드 권장

저장 구조:
  wiki/media/prod/videos/YYYY-MM/video_name.md
"""

import os
import json
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

SUPPORTED_EXTS  = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv"}
FRAME_INTERVAL  = 10      # 초마다 프레임 1장 추출
MAX_FRAMES      = 20      # 최대 프레임 수 (VRAM + 시간 절약)
RESULT_LOG      = "james_multimodal_log.jsonl"


def _log(event: str, path: str, detail: str):
    try:
        entry = {"time": datetime.now().isoformat(), "event": event,
                 "path": path, "detail": detail[:200], "layer": "video_analyzer"}
        with open(RESULT_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ─── Step 1: 프레임 추출 ─────────────────────────────────────

def extract_keyframes(
    video_path: str,
    interval_sec: int   = FRAME_INTERVAL,
    max_frames:   int   = MAX_FRAMES,
    output_dir:   Optional[str] = None,
) -> list:
    """
    opencv로 키프레임 추출.
    interval_sec마다 1장, 최대 max_frames장.

    Returns:
        [(frame_path, timestamp_sec), ...]
    """
    try:
        import cv2
    except ImportError:
        print("[VIDEO] opencv 미설치 → pip install opencv-python")
        return []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[VIDEO] 영상 열기 실패: {video_path}")
        return []

    fps        = cap.get(cv2.CAP_PROP_FPS) or 30
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration   = total_frames / fps

    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="james_frames_")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    frames   = []
    frame_idx = 0
    extracted = 0
    interval_frames = int(fps * interval_sec)

    print(f"[VIDEO] 프레임 추출: {duration:.1f}초 영상 / {interval_sec}초 간격")

    while cap.isOpened() and extracted < max_frames:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % interval_frames == 0:
            timestamp_sec = int(frame_idx / fps)
            frame_path    = os.path.join(output_dir, f"frame_{timestamp_sec:04d}.jpg")
            cv2.imwrite(frame_path, frame)
            frames.append((frame_path, timestamp_sec))
            extracted += 1

        frame_idx += 1

    cap.release()
    print(f"[VIDEO] {extracted}개 프레임 추출 완료")
    return frames


# ─── Step 2: 음성 추출 + Whisper 변환 ───────────────────────

def extract_audio_transcript(video_path: str) -> str:
    """
    ffmpeg으로 음성 추출 → Whisper로 텍스트 변환.

    Returns:
        transcript str (실패 시 빈 문자열)
    """
    audio_path = video_path.replace(Path(video_path).suffix, "_audio.wav")

    # ffmpeg 음성 추출
    try:
        import subprocess
        result = subprocess.run(
            ["ffmpeg", "-i", video_path, "-vn", "-acodec", "pcm_s16le",
             "-ar", "16000", "-ac", "1", audio_path, "-y"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            print(f"[VIDEO] ffmpeg 실패: {result.stderr[:100]}")
            return ""
    except FileNotFoundError:
        print("[VIDEO] ffmpeg 미설치 — 음성 변환 건너뜀")
        return ""
    except Exception as e:
        print(f"[VIDEO] 음성 추출 실패: {e}")
        return ""

    # Whisper 변환
    transcript = ""
    try:
        import whisper
        print("[VIDEO] Whisper 음성 인식 중...")
        model      = whisper.load_model("base")   # base 모델 (빠름)
        result_wh  = model.transcribe(audio_path, language="ko")
        transcript = result_wh.get("text", "").strip()
        print(f"[VIDEO] 음성 변환 완료: {len(transcript)}자")
    except ImportError:
        print("[VIDEO] whisper 미설치 → pip install openai-whisper")
    except Exception as e:
        print(f"[VIDEO] Whisper 실패: {e}")
    finally:
        # 임시 음성 파일 삭제
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
        except Exception:
            pass

    return transcript


# ─── Step 3: 프레임 이미지 분석 ──────────────────────────────

def analyze_frames(frames: list) -> list:
    """
    프레임별 이미지 분석 (llava).

    Returns:
        [{"timestamp_sec": int, "description": str, "tags": list, ...}]
    """
    try:
        from tools.multimodal.image_analyzer import analyze_image
    except ImportError:
        print("[VIDEO] image_analyzer import 실패")
        return []

    results = []
    total   = len(frames)

    for i, (frame_path, timestamp_sec) in enumerate(frames):
        print(f"[VIDEO] 프레임 분석 {i+1}/{total}: {timestamp_sec}초")
        try:
            analysis = analyze_image(frame_path, role="admin")
            results.append({
                "timestamp_sec": timestamp_sec,
                "description":   analysis.get("description", ""),
                "location":      analysis.get("location", ""),
                "persons":       analysis.get("persons", []),
                "tags":          analysis.get("tags", []),
            })
        except Exception as e:
            print(f"[VIDEO] 프레임 분석 실패 ({timestamp_sec}초): {e}")
        finally:
            # ⚠️ 임시 프레임 파일 즉시 삭제 (개인정보 보호)
            try:
                if os.path.exists(frame_path):
                    os.remove(frame_path)
            except Exception:
                pass

    return results


# ─── 요약 생성 ───────────────────────────────────────────────

def _summarize(frames: list, transcript: str) -> str:
    """프레임 분석 + 음성 기반 영상 요약."""
    parts = []

    # 장소 수집
    locations = list({f["location"] for f in frames if f.get("location")})
    if locations:
        parts.append(f"장소: {', '.join(locations[:3])}")

    # 인물 수집
    persons = list({p for f in frames for p in f.get("persons", [])})
    if persons:
        parts.append(f"등장 인물: {', '.join(persons[:5])}")

    # 태그 수집
    tags = list({t for f in frames for t in f.get("tags", [])})
    if tags:
        parts.append(f"태그: {', '.join(tags[:8])}")

    # 음성 요약 (앞 200자)
    if transcript:
        parts.append(f"음성: {transcript[:200]}")

    return " | ".join(parts) if parts else "분석 정보 없음"


# ─── 메인 분석 함수 ──────────────────────────────────────────

def analyze_video(video_path: str, role: str = "admin") -> dict:
    """
    영상 종합 분석.

    Returns:
        {
          "path":          str,
          "duration_sec":  float,
          "transcript":    str,
          "frames":        list,
          "summary":       str,
          "analyzed_at":   str,
        }
    """
    p = Path(video_path)
    if not p.exists():
        return {"error": f"파일 없음: {video_path}"}
    if p.suffix.lower() not in SUPPORTED_EXTS:
        return {"error": f"지원하지 않는 형식: {p.suffix}"}

    print(f"\n[VIDEO] ▶ 분석 시작: {p.name}")
    tmp_dir = None

    try:
        # 영상 길이 확인
        duration = _get_duration(video_path)
        print(f"[VIDEO] 길이: {duration:.1f}초")

        # Step 1: 프레임 추출
        tmp_dir = tempfile.mkdtemp(prefix="james_frames_")
        frames  = extract_keyframes(video_path, FRAME_INTERVAL, MAX_FRAMES, tmp_dir)

        # Step 2: 음성 추출 + 변환
        transcript = extract_audio_transcript(video_path)

        # Step 3: 프레임 분석
        frame_results = analyze_frames(frames)

        # 요약
        summary = _summarize(frame_results, transcript)

        result = {
            "path":         video_path,
            "filename":     p.name,
            "duration_sec": duration,
            "transcript":   transcript,
            "frames":       frame_results,
            "summary":      summary,
            "analyzed_at":  datetime.now().isoformat(),
        }

        _log("ANALYZED", video_path,
             f"duration={duration:.0f}s frames={len(frame_results)}")
        print(f"[VIDEO] ✅ 분석 완료: {p.name} | {len(frame_results)}프레임 | {len(transcript)}자 음성")

        # ── 원본 보관 + MD 저장 ──────────────────────────────
        try:
            from tools.multimodal.media_store import store_media
            store_result = store_media(
                src_path    = video_path,
                analysis    = result,
                source_type = "prod",
                move        = False,    # 복사 (원본 유지)
            )
            if store_result["success"]:
                result["stored_path"] = store_result["original_path"]
                result["md_path"]     = store_result["md_path"]
        except Exception as e:
            print(f"[VIDEO] 보관 실패 (분석 결과는 유지): {e}")

        return result

    except Exception as e:
        _log("ANALYZE_ERROR", video_path, str(e))
        print(f"[VIDEO] ❌ 분석 실패: {e}")
        return {"error": str(e), "path": video_path}

    finally:
        # 임시 폴더 정리
        if tmp_dir and os.path.exists(tmp_dir):
            try:
                shutil.rmtree(tmp_dir)
                print("[VIDEO] 임시 파일 삭제 완료")
            except Exception:
                pass


def _get_duration(video_path: str) -> float:
    """영상 길이 (초) 반환."""
    try:
        import cv2
        cap = cv2.VideoCapture(video_path)
        fps    = cap.get(cv2.CAP_PROP_FPS) or 30
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        cap.release()
        return frames / fps
    except Exception:
        return 0.0


# ─── #44 phase 4-C: TrustedContent wrapper ──────────────────

def analyze_video_trusted(video_path: str, role: str = "admin"):
    """[#44 phase 4-C] 영상 분석 결과를 `TrustedContent` 로 wrap.

    LLM 컨텍스트로 합류 가능한 텍스트 — 요약, ASR transcript, 프레임별
    설명 — 을 결합하여 반환. 프레임 metadata (timestamp_sec) 는 텍스트
    경로에 노출하되 prompt-injection 위험은 frame 설명 본문에 한정된다.

    Trust 분류 (#44 §3):
      - source = "asr"   (영상에는 ASR transcript + vision 둘 다 있지만
                          더 위험한 lower-bound 인 ASR 로 분류 — 텍스트
                          음성에 prompt-injection 을 삽입한 공격이
                          프레임 vision 보다 단순)
      - trust  = "low"   (외부 영상 ingestion → 항상 low)

    호출자는 `default_engine.quarantine(tc)` 로 LLM 합류 직전 검역할 수
    있다. 분석이 실패하면 `text=""` 인 빈 TrustedContent 를 반환한다.

    `analyze_video()` (dict 반환) 는 HTTP 엔드포인트가 그대로 사용 중
    이므로 시그니처 변경 없이 유지한다.
    """
    from core.policy_engine import TrustedContent

    result = analyze_video(video_path, role)

    parts = []
    summary = result.get("summary", "") or ""
    if summary:
        parts.append(f"요약: {summary}")
    transcript = result.get("transcript", "") or ""
    if transcript:
        parts.append(f"음성: {transcript}")
    for f in (result.get("frames", []) or [])[:5]:   # 최대 5 프레임 미리보기
        desc = (f or {}).get("description", "") or ""
        if desc:
            ts = (f or {}).get("timestamp_sec", 0)
            parts.append(f"[{ts}초] {desc}")
    text = "\n".join(parts)

    return TrustedContent(text=text, source="asr", trust="low")


# ─── wiki 저장 구조 생성 ─────────────────────────────────────

def to_wiki_entity(analysis: dict) -> dict:
    """분석 결과 → wiki entity 구조 변환."""
    name = Path(analysis.get("path", "video")).stem
    return {
        "name":        name,
        "type":        "media_video",
        "entity_type": "media_video",
        "attributes": {
            "file_path":    analysis.get("path", ""),
            "duration_sec": analysis.get("duration_sec", 0),
            "summary":      analysis.get("summary", ""),
            "transcript":   analysis.get("transcript", "")[:500],
            "frame_count":  len(analysis.get("frames", [])),
        },
        "relations":   [],
        "sensitivity": "internal",
        "source_type": "prod",
    }


if __name__ == "__main__":
    print("=== Video Analyzer 자가 테스트 ===\n")

    # 의존성 확인
    checks = [
        ("cv2",     "import cv2; print('opencv ✅')"),
        ("whisper", "import whisper; print('whisper ✅')"),
        ("PIL",     "from PIL import Image; print('Pillow ✅')"),
    ]
    for name, cmd in checks:
        try:
            exec(cmd)
        except ImportError:
            print(f"  ❌ {name} 미설치")

    # llava 확인
    try:
        from llm.providers.llava_client import LlavaClient
        ok = LlavaClient().is_available()
        print(f"  {'✅' if ok else '❌'} llava:13b {'사용 가능' if ok else '미설치 (ollama pull llava:13b)'}")
    except Exception as e:
        print(f"  ❌ llava_client: {e}")
