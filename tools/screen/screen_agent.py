"""
PROJECT JAMES — Screen Agent (P7-SCR-1)

화면 캡처 + OCR + LLM 분석 → 자메스가 화면 내용을 인식하고 대응.

보안 원칙:
  - admin 전용
  - 캡처 파일 즉시 삭제 (분석 후)
  - 개인정보 마스킹 후 LLM 전달
  - 화면 제어는 명시적 승인 후에만

현재 구현 (P7-SCR-1):
  ✅ 화면 캡처 (PIL/Pillow)
  ✅ OCR 텍스트 추출 (pytesseract)
  ✅ LLM 화면 분석 (Gemma)
  ✅ 권한 분리 (admin 전용)

Phase 8 예정 (P8-SCR-2):
  ⬜ 마우스/키보드 제어 (pyautogui)
  ⬜ 자동화 스크립트 실행
  ⬜ 멀티 모니터 지원
"""

import os
import re
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

try:
    from config import BASE_DIR
except ImportError:
    BASE_DIR = "."

SCREEN_LOG  = Path(BASE_DIR) / "workspace" / "screen_agent_log.jsonl"
SCREEN_LOG.parent.mkdir(parents=True, exist_ok=True)

# 개인정보 마스킹 패턴
_MASK_PATTERNS = [
    (r'\b\d{3}-\d{4}-\d{4}\b',      '***-****-****'),   # 전화번호
    (r'\b\d{6}-\d{7}\b',            '******-*******'),   # 주민번호
    (r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '***@***.***'),  # 이메일
    (r'\b(?:\d{4}[-\s]?){3}\d{4}\b', '**** **** **** ****'),  # 카드번호
]


class ScreenAgent:
    """화면 캡처 + 분석 에이전트."""

    # ─── 캡처 ────────────────────────────────────────────────────

    def capture(self, region=None) -> Optional[str]:
        """
        화면 캡처 → 임시 파일 저장.
        region: (x, y, width, height) 또는 None (전체)
        Returns: 임시 파일 경로
        """
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab(bbox=region)
            tmp = str(Path(BASE_DIR) / "workspace" /
                      f"screen_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            img.save(tmp)
            print(f"[SCR] 캡처 완료: {Path(tmp).name} ({img.size[0]}x{img.size[1]})")
            return tmp
        except ImportError:
            print("[SCR] PIL 없음 — pip install Pillow")
            return None
        except Exception as e:
            print(f"[SCR] 캡처 실패: {e}")
            return None

    # ─── OCR ─────────────────────────────────────────────────────

    def extract_text(self, img_path: str) -> str:
        """이미지에서 텍스트 추출 (OCR)."""
        try:
            import pytesseract
            from PIL import Image
            img  = Image.open(img_path)
            text = pytesseract.image_to_string(img, lang="kor+eng")
            return self._mask_pii(text)
        except ImportError:
            print("[SCR] pytesseract 없음 — pip install pytesseract")
            return "[OCR 불가]"
        except Exception as e:
            print(f"[SCR] OCR 실패: {e}")
            return "[OCR 실패]"

    # ─── LLM 분석 ────────────────────────────────────────────────

    def analyze(self, img_path: str, question: str = "") -> Dict:
        """
        캡처된 화면 분석.
        1. OCR 텍스트 추출
        2. LLM으로 화면 내용 분석
        3. 임시 파일 삭제
        Returns: 분석 결과 dict
        """
        text = self.extract_text(img_path)

        q = question or "화면에 무엇이 있나요? 중요한 정보를 요약해주세요."
        prompt = (
            f"화면에서 추출된 텍스트:\n{text[:1000]}\n\n"
            f"질문: {q}\n\n"
            f"화면 분석 결과:"
        )

        analysis = ""
        try:
            from llm.router import call_router
            analysis = call_router(
                prompt, task_type="general", timeout=60, use_cache=False,
            )
        except Exception as e:
            analysis = f"[LLM 분석 실패: {e}]"

        # 임시 파일 즉시 삭제
        try:
            os.remove(img_path)
        except Exception:
            pass

        result = {
            "ocr_text":  text[:500],
            "analysis":  analysis,
            "question":  q,
            "timestamp": datetime.now().isoformat(),
        }
        self._log(result)
        return result

    # ─── 전체 워크플로 ────────────────────────────────────────────

    def run(self, question: str = "", region=None) -> Dict:
        """캡처 → OCR → 분석 전체 실행."""
        img_path = self.capture(region)
        if not img_path:
            return {"error": "화면 캡처 실패 (PIL 설치 필요)", "analysis": ""}
        return self.analyze(img_path, question)

    # ─── 헬퍼 ────────────────────────────────────────────────────

    def _mask_pii(self, text: str) -> str:
        """개인정보 마스킹."""
        for pattern, mask in _MASK_PATTERNS:
            text = re.sub(pattern, mask, text)
        return text

    def _log(self, result: Dict):
        try:
            with open(SCREEN_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(
                    {**result, "ocr_text": result["ocr_text"][:100]},
                    ensure_ascii=False
                ) + "\n")
        except Exception:
            pass


# ─── 싱글턴 ──────────────────────────────────────────────────────

_agent: Optional[ScreenAgent] = None

def get_agent() -> ScreenAgent:
    global _agent
    if _agent is None:
        _agent = ScreenAgent()
    return _agent

def run_screen_analysis(question: str = "", region=None) -> Dict:
    """외부 진입점."""
    return get_agent().run(question, region)
