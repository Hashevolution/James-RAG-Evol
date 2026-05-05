"""
PROJECT JAMES - Metadata Utilities
메타데이터 생성 및 JSON 파싱
"""
import re
import json
from core.gemma_client import GemmaClient   # type/fallback retained
from llm.router import RouterWrapper

class MetadataGenerator:
    def __init__(self):
        self.gemma_client = RouterWrapper("extract")

    def safe_parse_json(self, text: str) -> dict:
        """JSON 파싱 (브라켓 카운팅 방식)"""
        if not isinstance(text, str):
            return {
                "keywords": [],
                "summary": "분석 실패",
                "category": "기타"
            }
            
        text = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', text).strip()

        try:
            return json.loads(text)
        except Exception:
            pass

        try:
            return json.loads(re.sub(r'\s+', ' ', text))
        except Exception:
            pass

        start_idx = text.find('{')
        if start_idx != -1:
            depth = 0
            for i, ch in enumerate(text[start_idx:], start=start_idx):
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        candidate = text[start_idx:i+1]
                        try:
                            return json.loads(candidate)
                        except Exception:
                            try:
                                cleaned = re.sub(r'\s+', ' ', candidate)
                                return json.loads(cleaned)
                            except Exception:
                                break

        for marker in ["...done thinking.", "done thinking.", "...done"]:
            thinking_end = text.find(marker)
            if thinking_end != -1:
                after = text[thinking_end + len(marker):]
                after_clean = re.sub(r'\s+', ' ', after).strip()
                start_idx = after_clean.find('{')
                if start_idx != -1:
                    depth = 0
                    for i, ch in enumerate(after_clean[start_idx:], start=start_idx):
                        if ch == '{':
                            depth += 1
                        elif ch == '}':
                            depth -= 1
                            if depth == 0:
                                candidate = after_clean[start_idx:i+1]
                                try:
                                    return json.loads(candidate)
                                except Exception:
                                    break
                break

        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass

        return {
            "keywords": [],
            "summary": text[:100] if text else "분석 실패",
            "category": "기타"
        }
    
    def generate_metadata(self, text: str) -> dict:
        """메타데이터 생성"""
        if not isinstance(text, str):
            text = str(text) if text else ""
            
        prompt = (
            "You must output ONLY a JSON object. "
            "No explanation, no thinking, no markdown. Just raw JSON.\n\n"
            "Output format:\n"
            '{"keywords": ["word1", "word2", "word3"], "summary": "한줄요약", "category": "기타"}\n\n'
            "Category must be one of: 경제, 법률, 기술, 의료, 영상분석, 음성, 기타\n\n"
            "Document:\n"
            + text[:2000]
            + "\n\nJSON:"
        )

        # 문서 기준으로 LLM 호출 (#13: router 경유, task_type=extract)
        from llm.router import call_router
        output = call_router(prompt, task_type="extract", use_cache=True)
        print(f"[DEBUG] generate_metadata raw output:\n{output}")
        meta = self.safe_parse_json(output)

        # ✅ ABAC 필드 추가 (없으면 기본값)
        # sensitivity: ABAC 접근 제어 등급
        # owner: 소유자 (서버 기본값, 외부 입력 신뢰 금지)
        if "sensitivity" not in meta:
            meta["sensitivity"] = "internal"
        if "owner" not in meta:
            meta["owner"] = "system"

        return meta
