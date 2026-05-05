"""
PROJECT JAMES - File Processor Module

수정 사항:
  Fix 1. 순환 임포트 제거 (RAGEngine import 삭제)
         → 저장 책임을 server_llmwiki.py로 이전
  Fix 2. process_file() → str만 반환 (tuple 제거)
         → 메타데이터 생성은 별도 메서드로 분리
  Fix 3. sensitivity 강제 override (사용자 입력 신뢰 금지)
  Fix 4. 컨텐츠 기반 자동 sensitivity 상향
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

    def extract_text(self, filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            data = f.read()
        print(f"[DEBUG] 텍스트 읽기 완료 ({len(data)}자)")
        return data

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

    def extract_pdf(self, filepath):
        text = self._extract_with_markitdown(filepath)
        if not text or len(text) < 100:
            text = self._extract_scanned_pdf(filepath)
        return text

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

    def extract_office(self, filepath):
        text = self._extract_with_markitdown(filepath)
        return text if text else "[문서 변환 실패]"

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

    def extract_image(self, filepath):
        text = self._extract_with_vision_tiling(filepath)
        if len(text) < 10:
            text = self._extract_with_easyocr(filepath)
        if len(text) < 10:
            text = self._extract_with_tesseract(Image.open(filepath))
        return f"[이미지 분석 결과]\n{text}"

    def extract_audio(self, filepath):
        model = self.get_whisper_model()
        res   = model.transcribe(filepath, language="ko")
        return f"[음성 변환]\n{res.get('text', '')}"

    def extract_video(self, filepath):
        return "[영상 분석 결과 - 샘플링 기반]"

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

    def process_file(self, filepath: str, original_filename: str) -> str:
        """
        파일 → 텍스트 추출만 담당 (저장 X)
        Fix 2: str 반환 (tuple 제거)
        저장은 server_llmwiki.py의 rag_engine.save_to_wiki()에서 수행
        """
        filename = os.path.basename(filepath)
        ext      = filename.lower().rsplit(".", 1)[-1]

        print(f"\n{'='*50}")
        print(f"[SYSTEM] 파일 처리: {filename}")
        print(f"{'='*50}")

        content = f"# 파일: {original_filename}\n\n"

        try:
            if ext in ["txt", "md"]:
                content += self.extract_text(filepath)
            elif ext == "pdf":
                content += self.extract_pdf(filepath)
            elif ext in ["png", "jpg", "jpeg", "bmp", "tiff", "webp"]:
                content += self.extract_image(filepath)
            elif ext in ["mp3", "wav", "m4a", "ogg"]:
                content += self.extract_audio(filepath)
            elif ext in ["mp4", "avi", "mov", "mkv"]:
                content += self.extract_video(filepath)
            elif ext in ["docx", "doc", "xlsx", "xls", "pptx", "ppt", "hwp", "hwpx"]:
                content += self.extract_office(filepath)
            else:
                print(f"[WARN] 지원하지 않는 형식: {ext}")
                content += "[지원하지 않는 형식]"
        except Exception as e:
            print(f"[ERROR] 파일 처리 오류: {e}")
            content += f"[처리 오류] {str(e)}"

        print(f"[DEBUG] 텍스트 추출 완료 ({len(content)}자)")
        return content

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
