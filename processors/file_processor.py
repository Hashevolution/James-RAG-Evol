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
           - 영상 (현재 stub, 향후 ASR+vision)       → ("asr",    "low")
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

from config import UPLOAD_FOLDER, POPPLER_PATH, TESSERACT_PATH
from core.gemma_client import GemmaClient
from core.policy_engine import TrustedContent
from utils.metadata import MetadataGenerator


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
        w, h  = img.size
        img   = img.resize((w * 2, h * 2), Image.LANCZOS)
        img_np = np.array(img.convert("L"))
        binary = cv2.adaptiveThreshold(img_np, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                        cv2.THRESH_BINARY, 11, 2)
        return Image.fromarray(binary)

    def _extract_with_tesseract(self, img):
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
        processed = self._preprocess_image(img)
        return pytesseract.image_to_string(processed, lang="kor+eng", config="--psm 6")

    def _extract_with_easyocr(self, filepath):
        reader = self.get_easyocr_reader()
        if not reader:
            return ""
        results = reader.readtext(filepath, detail=0, paragraph=True)
        return "\n".join(results)

    def _extract_with_vision_tiling(self, filepath):
        try:
            filename = os.path.basename(filepath)
            res = self.gemma_client.call_gemma_vision(
                "이 이미지의 모든 텍스트를 마크다운으로 추출해. 표가 있다면 형식을 유지해.",
                filepath
            )
            if res.count('|') >= 3:
                res = f"\n\n> **[ORIGINAL_IMAGE_REFERENCE_REQUIRED: {filename}]**\n" + res
            return res
        except Exception as e:
            print(f"[DEBUG] Vision 오류: {e}")
            return ""

    def extract_image(self, filepath) -> TrustedContent:
        # 이미지에서 추출된 모든 텍스트는 low-trust (적대적 픽셀 가능).
        # vision tiling 성공 시 source="vision", OCR fallback 시 source="ocr".
        text   = self._extract_with_vision_tiling(filepath)
        source = "vision"
        if len(text) < 10:
            text   = self._extract_with_easyocr(filepath)
            source = "ocr"
        if len(text) < 10:
            text   = self._extract_with_tesseract(Image.open(filepath))
            source = "ocr"
        return TrustedContent(
            text=f"[이미지 분석 결과]\n{text}",
            source=source,
            trust="low",
        )

    def extract_audio(self, filepath) -> TrustedContent:
        model = self.get_whisper_model()
        res   = model.transcribe(filepath, language="ko")
        return TrustedContent(
            text=f"[음성 변환]\n{res.get('text', '')}",
            source="asr",
            trust="low",
        )

    # [video-reject 2026-05-10] extract_video 는 W1 진단 §3-C 권고에 따라
    # 제거됨. 이전 stub 은 silent failure 를 만들어 ChromaDB 에 노이즈
    # 인덱스를 추가했음. 영상 파일은 server_llmwiki.py /upload/ 단계에서
    # 422 로 거부되며, defense-in-depth 로 process_file 도 unsupported
    # placeholder 를 돌려준다 (아래 dispatch 참조).
    # 후속 video-asr PR 에서 ffmpeg + Whisper + frame caption 합성을 추가.

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
            elif ext in ["mp4", "avi", "mov", "mkv"]:
                # [video-reject 2026-05-10] 정상 경로는 server_llmwiki.py
                # /upload/ 가 422 거부하지만, 직접 process_file 호출에 대한
                # defense-in-depth — silent stub 대신 명시적 unsupported.
                print(f"[WARN] 영상 파일 미지원 (현재 stub 제거됨): {ext}")
                inner = TrustedContent(
                    text="[지원하지 않는 형식 — 영상 파일은 음성으로 변환 후 업로드]",
                    source="doc", trust="medium",
                )
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
