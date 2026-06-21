"""
PROJECT JAMES - LLaVA Client (Phase 6 멀티모달)

이미지 → 날짜/장소/인물 태깅 첫 단계.
Ollama llava:13b 통해 로컬 실행.

사용:
  ollama pull llava:13b
"""

import base64
import re
import json
from pathlib import Path

from llm.base import BaseLLM


class LlavaClient(BaseLLM):
    name = "llava"

    def __init__(self, model: str = ""):
        try:
            from config import MULTIMODAL_MODEL, OLLAMA_API_URL
            default_model = MULTIMODAL_MODEL   # llava:13b
            self.api_url  = OLLAMA_API_URL
        except ImportError:
            default_model = "llava:13b"
            self.api_url  = "http://127.0.0.1:11434/api/generate"
        # An explicit (resolved) tag wins — e.g. handle_vision passes the
        # ``resolve_for_mode("vision")`` result. Empty keeps the legacy
        # config/hardcoded default so existing callers are byte-identical.
        self.model = (model or "").strip() or default_model

    def generate(self, messages: list, **kwargs) -> str:
        """텍스트 전용 — 이미지 없을 때 fallback"""
        import requests
        prompt  = "\n".join(m.get("content","") for m in messages if m.get("content"))
        timeout = kwargs.get("timeout", 60)
        try:
            resp = requests.post(
                self.api_url,
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=timeout,
            )
            return resp.json().get("response","").strip()
        except Exception as e:
            return f"[LLaVA 오류] {e}"

    def analyze_image(
        self,
        image_path: str,
        prompt: str = "이 이미지에서 날짜, 장소, 인물을 찾아서 JSON으로 반환해줘.",
        timeout: int = 120,
    ) -> dict:
        """
        이미지 분석 → 날짜/장소/인물 태깅.

        Returns:
            {"date": str, "location": str, "persons": list, "description": str}
        """
        import requests

        # 이미지 → base64
        p = Path(image_path)
        if not p.exists():
            return {"error": f"파일 없음: {image_path}"}

        suffix = p.suffix.lower()
        mime_map = {".jpg":"image/jpeg",".jpeg":"image/jpeg",
                    ".png":"image/png",".gif":"image/gif",".webp":"image/webp"}
        if suffix not in mime_map:
            return {"error": f"지원하지 않는 형식: {suffix}"}

        try:
            image_data = base64.b64encode(p.read_bytes()).decode("utf-8")
        except Exception as e:
            return {"error": f"이미지 읽기 실패: {e}"}

        # LLaVA 호출
        try:
            resp = requests.post(
                self.api_url,
                json={
                    "model":  self.model,
                    "prompt": prompt,
                    "images": [image_data],
                    "stream": False,
                    "options": {"temperature": 0, "num_predict": 500},
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "").strip()
        except Exception as e:
            return {"error": f"LLaVA 호출 실패: {e}"}

        # JSON 파싱 시도
        return self._parse_result(raw, image_path)

    @staticmethod
    def _parse_result(raw: str, image_path: str) -> dict:
        """응답에서 JSON 추출, 실패 시 텍스트 그대로"""
        result = {
            "image":       image_path,
            "date":        "",
            "location":    "",
            "persons":     [],
            "description": raw[:300],
        }
        # JSON 블록 추출 시도
        m = re.search(r"\{.*?\}", raw, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(0))
                result.update({k: v for k, v in parsed.items()
                               if k in ("date","location","persons","description")})
                return result
            except Exception:
                pass
        # 텍스트 기반 파싱
        if re.search(r"\d{4}[-./]\d{2}[-./]\d{2}", raw):
            dates = re.findall(r"\d{4}[-./]\d{2}[-./]\d{2}", raw)
            if dates: result["date"] = dates[0]
        return result

    def is_available(self) -> bool:
        try:
            import requests
            resp = requests.get("http://127.0.0.1:11434/api/tags", timeout=5)
            models = [m.get("name","") for m in resp.json().get("models",[])]
            return any("llava" in m for m in models)
        except Exception:
            return False


if __name__ == "__main__":
    client = LlavaClient()
    available = client.is_available()
    print(f"LLaVA 사용 가능: {available}")
    if not available:
        print("설치: ollama pull llava:13b")
