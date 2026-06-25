"""
PROJECT JAMES - File Processor Module

수정 사항:
  Fix 1. 순환 임포트 제거 (RAGEngine import 삭제)
         → 저장 책임을 server_llmwiki.py로 이전
  Fix 2. process_file() → str만 반환 (tuple 제거)
         → 메타데이터 생성은 별도 메서드로 분리
  Fix 3. sensitivity 강제 override (사용자 입력 신뢰 금지)
  Fix 4. 컨텐츠 기반 자동 sensitivity 상향
  Fix 5. (#44 phase 4-B) 모든 extractor 가 TrustedContent 를 반환.
         source/trust 분류:
           - .txt/.md/.pdf-MarkItDown/.office       → ("doc",    "medium")
           - .pdf OCR fallback / 스캔 PDF           → ("ocr",    "low")
           - 이미지 vision tiling 성공              → ("vision", "low")
           - 이미지 EasyOCR / Tesseract             → ("ocr",    "low")
           - 음성 (Whisper ASR)                     → ("asr",    "low")
           - 영상 (ffmpeg → Whisper ASR; v0.3에 frame caption) → ("asr", "low")
           - 지원하지 않는 형식 / 처리 오류 placeholder → ("doc",    "medium")
         호출자(server_llmwiki.py 업로드 핸들러)는 `tc.text` 를 받아
         기존 sanitize_document_content 를 통해 ingestion-time 검역 유지.
         후속 phase 가 단일 quarantine chokepoint 로 통일 예정.
"""
import os
import re
import cv2
import numpy as np
from PIL import Image
import pytesseract
import whisper
from pdf2image import convert_from_path

from config import POPPLER_PATH, TESSERACT_PATH
from core.policy_engine import TrustedContent
from utils.metadata import MetadataGenerator

# Minimum per-word OCR confidence (Tesseract 0-100 scale; EasyOCR's 0-1
# scale is compared against this/100). Words below this are dropped — the
# key defence against OCR "noise" (a blurry photo can otherwise emit tens
# of thousands of low-confidence garbage tokens that would pollute the KG).
_OCR_MIN_CONF = 55

# Sentinel the vision model emits when it cannot read any text. Lets us
# distinguish "no transcription" from real text WITHOUT a fragile
# length/keyword heuristic, so the OCR fallback fires correctly.
_NO_TEXT = "<NO_TEXT>"


class FileProcessor:
    def __init__(self):
        # vision 호출은 RouterWrapper.call_gemma_vision이 GemmaClient에 위임
        from llm.router import RouterWrapper
        self.gemma_client = RouterWrapper("vision")
        self.metadata_gen = MetadataGenerator()
        # Fix 1: RAGEngine import 제거 → 순환 임포트 차단
        # 저장 책임은 server_llmwiki.py의 rag_engine.save_to_wiki()로 이전
        self._whisper_model  = None
        self._easyocr_reader = None

    def get_whisper_model(self):
        if self._whisper_model is None:
            print("[DEBUG] Whisper 모델 로드 중...")
            self._whisper_model = whisper.load_model("base")
            print("[DEBUG] Whisper 모델 로드 완료")
        return self._whisper_model

    def get_easyocr_reader(self):
        if self._easyocr_reader is None:
            try:
                import easyocr
                print("[DEBUG] EasyOCR Reader 초기화 중...")
                self._easyocr_reader = easyocr.Reader(['ko', 'en'], gpu=False)
                print("[DEBUG] EasyOCR Reader 초기화 완료")
            except ImportError:
                print("[DEBUG] EasyOCR 없음")
                self._easyocr_reader = None
        return self._easyocr_reader

    # ─────────────────────────────────────
    # 텍스트 추출 메서드들
    # ─────────────────────────────────────

    def extract_text(self, filepath) -> TrustedContent:
        with open(filepath, "r", encoding="utf-8") as f:
            data = f.read()
        print(f"[DEBUG] 텍스트 읽기 완료 ({len(data)}자)")
        return TrustedContent(text=data, source="doc", trust="medium")

    def _extract_with_markitdown(self, filepath: str) -> str:
        try:
            from markitdown import MarkItDown
            md   = MarkItDown()
            res  = md.convert(filepath)
            text = res.text_content.strip() if res else ""
            print(f"[DEBUG] MarkItDown 변환 성공 ({len(text)}자)")
            return text
        except Exception as e:
            print(f"[DEBUG] MarkItDown 실패: {e}")
            return ""

    def extract_pdf(self, filepath) -> TrustedContent:
        text = self._extract_with_markitdown(filepath)
        if not text or len(text) < 100:
            # OCR fallback — 스캔 PDF 는 이미지 기반이므로 low-trust ocr.
            text = self._extract_scanned_pdf(filepath)
            return TrustedContent(text=text, source="ocr", trust="low")
        return TrustedContent(text=text, source="doc", trust="medium")

    def _extract_scanned_pdf(self, filepath):
        try:
            images = convert_from_path(filepath, poppler_path=POPPLER_PATH)
            text   = ""
            for i, image in enumerate(images):
                img_np    = np.array(image.convert('L'))
                _, binary = cv2.threshold(img_np, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
                page_text  = pytesseract.image_to_string(Image.fromarray(binary), lang="kor+eng")
                text       += f"\n\n--- Page {i+1} ---\n{page_text}"
            return text
        except Exception as e:
            print(f"[DEBUG] 스캔 PDF OCR 실패: {e}")
            return "[PDF OCR 실패]"

    def extract_office(self, filepath) -> TrustedContent:
        text = self._extract_with_markitdown(filepath)
        return TrustedContent(
            text=text if text else "[문서 변환 실패]",
            source="doc",
            trust="medium",
        )

    def _preprocess_image(self, img):
        # NO hard binarization. Adaptive thresholding targets clean,
        # evenly-lit scans; on PHOTOS it freezes lighting gradients + JPEG
        # noise into black/white speckle that Tesseract reads as thousands
        # of phantom characters (measured on a blurry doc photo: this path
        # produced 296k garbage chars vs ~2k on the plain grayscale image —
        # a 136× amplification). Modern Tesseract-LSTM normalises internally
        # and reads grayscale better, so hand it grayscale and let it work.
        # A 2× upscale still helps small text, but only when the image is
        # small — upscaling an already-large photo just multiplies the noise.
        w, h = img.size
        if max(w, h) < 2000:
            img = img.resize((w * 2, h * 2), Image.LANCZOS)
        return img.convert("L")

    def _extract_with_tesseract(self, img):
        # Confidence-filtered: keep only words Tesseract is reasonably sure
        # about. A blurry / textless photo otherwise yields huge runs of
        # low-confidence gibberish (observed: 296k garbage chars) that would
        # be ingested as fake "text". image_to_data gives per-word conf.
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
        processed = self._preprocess_image(img)
        try:
            data = pytesseract.image_to_data(
                processed, lang="kor+eng", config="--psm 6",
                output_type=pytesseract.Output.DICT,
            )
        except Exception as e:
            print(f"[DEBUG] Tesseract 오류: {e}")
            return ""
        words = []
        for w, c in zip(data.get("text", []), data.get("conf", [])):
            try:
                conf = float(c)
            except (TypeError, ValueError):
                conf = -1.0
            if conf >= _OCR_MIN_CONF and w.strip():
                words.append(w.strip())
        return " ".join(words)

    def _extract_with_easyocr(self, filepath):
        reader = self.get_easyocr_reader()
        if not reader:
            return ""
        try:
            # detail=1 → (bbox, text, confidence); EasyOCR conf is 0-1.
            results = reader.readtext(filepath, detail=1, paragraph=False)
        except Exception as e:
            print(f"[DEBUG] EasyOCR 오류: {e}")
            return ""
        kept = [
            t for (_b, t, conf) in results
            if conf >= (_OCR_MIN_CONF / 100.0) and t and t.strip()
        ]
        return "\n".join(kept)

    @staticmethod
    def _looks_like_text(text: str) -> bool:
        """True iff ``text`` reads as real extracted text, not OCR noise.

        Three guards (confidence filtering already drops most low-conf
        noise upstream; this is the final gate before the KG):

          1. ≥10 word-characters total (reject near-empty).
          2. ≥50% of non-space chars are Hangul / Latin / digit (rejects
             block-char / symbol soup like EasyOCR's ▒█).
          3. NOT fragmented: a real document OCR yields multi-character
             "words", whereas an unreadable photo yields a stream of
             isolated 1-char tokens + symbols ("y | ® Fo 이 고 il Ki ...").
             Require ≥40% of whitespace tokens to be real words (≥2 word-
             chars) AND at least 3 such words. (The ≥40% ratio is the real
             discriminator — garbage runs ~0.3, real text ~1.0; the floor
             of 3 only rejects near-trivial output, kept low so short-but-
             real captions like a 4-word notice headline still pass —
             guard #1 already requires ≥10 word-chars.)
        """
        t = (text or "").strip()
        valid = len(re.findall(r"[가-힣A-Za-z0-9]", t))
        if valid < 10:
            return False
        nonspace = len(re.sub(r"\s", "", t)) or 1
        if (valid / nonspace) < 0.5:
            return False
        tokens = t.split()
        if not tokens:
            return False
        words = [w for w in tokens
                 if len(re.findall(r"[가-힣A-Za-z0-9]", w)) >= 2]
        return (len(words) / len(tokens)) >= 0.4 and len(words) >= 3

    def _extract_with_vision_tiling(self, filepath):
        # Verbatim-transcription prompt with a hard sentinel: the model
        # must emit `<NO_TEXT>: <short description>` when it cannot read
        # any text, instead of a verbose "the image is too blurry…"
        # paragraph. The old prompt's apology (> 10 chars) defeated the
        # length-based OCR fallback, so blurry document photos extracted
        # nothing AND never reached OCR.
        try:
            filename = os.path.basename(filepath)
            res = self.gemma_client.call_gemma_vision(
                "이 이미지에 보이는 모든 텍스트를 그대로(verbatim) 마크다운으로 옮겨 적어. "
                "표가 있으면 표 형식을 유지해. 설명·사과·번역·추측은 절대 하지 마. "
                "읽을 수 있는 텍스트가 전혀 없거나 흐려서 못 읽으면, 다른 말 없이 정확히 "
                f"`{_NO_TEXT}: ` 뒤에 이 이미지가 무엇인지 8단어 이내로만 적어 "
                f"(예: `{_NO_TEXT}: 흐릿한 한국어 공지 문서 사진`).",
                filepath,
            )
            res = res or ""
            if _NO_TEXT not in res and res.count('|') >= 3:
                res = f"\n\n> **[ORIGINAL_IMAGE_REFERENCE_REQUIRED: {filename}]**\n" + res
            return res
        except Exception as e:
            print(f"[DEBUG] Vision 오류: {e}")
            return ""

    def extract_image(self, filepath) -> TrustedContent:
        # 이미지에서 추출된 모든 텍스트는 low-trust (적대적 픽셀 가능).
        #
        # Flow (v0.6.1): vision transcription → if it emitted <NO_TEXT> (or
        # the result isn't real text) fall through to confidence-gated OCR
        # (Tesseract → EasyOCR). OCR output passes only `_looks_like_text`,
        # so garbage from an unreadable photo is discarded rather than
        # ingested. When nothing is readable we keep an honest, NON-garbage
        # marker (+ the model's short hint) so a document entity still has
        # minimal context without fabricated text.
        vtext   = self._extract_with_vision_tiling(filepath)
        no_text = _NO_TEXT in vtext

        desc = ""
        if no_text:
            m = re.search(rf"{re.escape(_NO_TEXT)}\s*:?\s*([^\n]*)", vtext)
            desc = (m.group(1).strip() if m else "")[:120]

        text, source = "", "vision"
        if not no_text and self._looks_like_text(vtext):
            text, source = vtext.strip(), "vision"
        else:
            # vision could not transcribe → confidence-gated OCR fallback.
            # EasyOCR (neural) goes first — it reads real-world / Korean
            # photos markedly better than Tesseract; Tesseract is the
            # cheaper last resort. (PaddleOCR would be a stronger #1 still,
            # but has no wheel for this Python — see the upgrade note.)
            source = "ocr"
            otext = self._extract_with_easyocr(filepath)
            if not self._looks_like_text(otext):
                otext = self._extract_with_tesseract(Image.open(filepath))
            text = otext.strip() if self._looks_like_text(otext) else ""

        if text:
            body = f"[이미지 텍스트]\n{text}"
        else:
            # Nothing readable by vision OR OCR — do NOT ingest noise.
            body   = f"[이미지 분석] {desc or '텍스트를 추출할 수 없는 이미지'}"
            source = "vision"

        return TrustedContent(text=body, source=source, trust="low")

    def extract_audio(self, filepath) -> TrustedContent:
        model = self.get_whisper_model()
        res   = model.transcribe(filepath, language="ko")
        return TrustedContent(
            text=f"[음성 변환]\n{res.get('text', '')}",
            source="asr",
            trust="low",
        )

    # [video-asr 2026-05-11] extract_video — ffmpeg 로 오디오 트랙
    # 추출 후 기존 Whisper 경로로 통과시킨다. ffmpeg 가 PATH 에 없으면
    # 명시적 RuntimeError — server_llmwiki.upload 가 그 메시지를
    # 422 detail 로 surface 한다 (silent failure 패턴 회피, W1 진단
    # §3-C 의 핵심 권고).
    #
    # frame caption 합성은 의도적으로 보류 (v0.3 multimodal 트랙) —
    # ASR 만으로 회의록·인터뷰·강의 영상 같은 일반 사례 cover.
    def extract_video(self, filepath: str) -> TrustedContent:
        import shutil as _shutil
        import subprocess as _sub
        import tempfile as _tmpfile
        import os as _os

        ffmpeg = _shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError(
                "ffmpeg 가 PATH 에 없습니다. 운영자가 사전 설치 필요 — "
                "Windows: winget install Gyan.FFmpeg / "
                "macOS: brew install ffmpeg / Linux: apt install ffmpeg"
            )

        # Audio 만 추출 → 임시 wav. 16kHz mono — Whisper 의 기본 입력.
        # -y overwrite, -vn disable video, -loglevel error 로 시끄러운
        # 진행 로그 차단 (subprocess.run 가 stderr 캡처).
        tmp = _tmpfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        try:
            cmd = [ffmpeg, "-y", "-i", filepath,
                   "-vn", "-acodec", "pcm_s16le",
                   "-ar", "16000", "-ac", "1",
                   "-loglevel", "error", tmp.name]
            r = _sub.run(cmd, capture_output=True, timeout=600)
            if r.returncode != 0:
                err = (r.stderr or b"").decode("utf-8", errors="replace")[:400]
                raise RuntimeError(f"ffmpeg 추출 실패: {err.strip() or 'unknown'}")
            if _os.path.getsize(tmp.name) < 1000:
                raise RuntimeError(
                    "영상에서 오디오 트랙을 찾지 못했거나 너무 짧습니다."
                )
            audio = self.extract_audio(tmp.name)
            return TrustedContent(
                text=f"[영상 음성 변환]\n{audio.text.removeprefix('[음성 변환]').lstrip()}",
                source="asr",
                trust="low",
            )
        finally:
            try: _os.unlink(tmp.name)
            except OSError: pass

    # ─────────────────────────────────────
    # Fix 3+4: sensitivity 강제 override
    # ─────────────────────────────────────

    @staticmethod
    def _determine_sensitivity(content: str) -> str:
        """
        컨텐츠 기반 자동 sensitivity 결정
        사용자 입력은 절대 신뢰하지 않음
        """
        CONFIDENTIAL_KEYWORDS = [
            "주민번호", "주민등록번호", "비밀번호", "password", "개인정보",
            "신용카드", "계좌번호", "confidential", "기밀", "top secret",
        ]
        INTERNAL_KEYWORDS = [
            "내부", "사내", "팀", "프로젝트", "internal", "회의록",
            "계획", "전략", "예산", "급여",
        ]
        content_lower = content.lower()

        if any(kw in content_lower for kw in CONFIDENTIAL_KEYWORDS):
            return "confidential"
        if any(kw in content_lower for kw in INTERNAL_KEYWORDS):
            return "internal"
        return "internal"  # 기본값: 업로드된 문서는 최소 internal

    # ─────────────────────────────────────
    # Fix 2: process_file → str만 반환
    # 메타데이터 생성은 generate_file_metadata()로 분리
    # ─────────────────────────────────────

    def process_file(self, filepath: str, original_filename: str) -> TrustedContent:
        """
        파일 → 텍스트 추출만 담당 (저장 X)
        Fix 2: str 반환 (tuple 제거)
        Fix 5 (#44 phase 4-B): TrustedContent 반환. 내부 extractor 의
              source/trust 를 상위로 전파 — 호출자가 PolicyEngine.quarantine
              으로 일원화할 수 있도록 provenance 보존.
        저장은 server_llmwiki.py의 rag_engine.save_to_wiki()에서 수행
        """
        filename = os.path.basename(filepath)
        ext      = filename.lower().rsplit(".", 1)[-1]

        print(f"\n{'='*50}")
        print(f"[SYSTEM] 파일 처리: {filename}")
        print(f"{'='*50}")

        try:
            if ext in ["txt", "md"]:
                inner = self.extract_text(filepath)
            elif ext == "pdf":
                inner = self.extract_pdf(filepath)
            elif ext in ["png", "jpg", "jpeg", "bmp", "tiff", "webp"]:
                inner = self.extract_image(filepath)
            elif ext in ["mp3", "wav", "m4a", "ogg"]:
                inner = self.extract_audio(filepath)
            elif ext in ["mp4", "avi", "mov", "mkv", "webm"]:
                # [video-asr 2026-05-11] ffmpeg → audio → Whisper.
                # Errors surface as RuntimeError from extract_video;
                # the outer try/except in this method catches them and
                # the upload returns 422 with a friendly message.
                inner = self.extract_video(filepath)
            elif ext in ["docx", "doc", "xlsx", "xls", "pptx", "ppt", "hwp", "hwpx"]:
                inner = self.extract_office(filepath)
            else:
                print(f"[WARN] 지원하지 않는 형식: {ext}")
                inner = TrustedContent(
                    text="[지원하지 않는 형식]", source="doc", trust="medium",
                )
        except Exception as e:
            print(f"[ERROR] 파일 처리 오류: {e}")
            inner = TrustedContent(
                text=f"[처리 오류] {e}", source="doc", trust="medium",
            )

        # 파일명 헤더는 서버 발 system 텍스트이므로 내부 extractor 의 trust 를 상속.
        composed_text = f"# 파일: {original_filename}\n\n{inner.text}"
        print(f"[DEBUG] 텍스트 추출 완료 ({len(composed_text)}자, "
              f"source={inner.source} trust={inner.trust})")
        return TrustedContent(
            text=composed_text,
            source=inner.source,
            trust=inner.trust,
        )

    def generate_file_metadata(self, content: str) -> dict:
        """
        메타데이터 생성 + sensitivity 강제 override
        Fix 3: 사용자 입력 sensitivity 무시, 서버에서 강제 지정
        """
        meta = self.metadata_gen.generate_metadata(content)

        # Fix 3: sensitivity는 항상 서버 판단 (사용자 입력 신뢰 금지)
        meta["sensitivity"] = self._determine_sensitivity(content)
        meta["owner"]       = "system"

        print(f"[SECURITY] metadata sensitivity: {meta['sensitivity']}")
        return meta
