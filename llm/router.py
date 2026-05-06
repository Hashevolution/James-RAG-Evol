"""
PROJECT JAMES - LLM Router (Phase 6)

GPU 업그레이드 후 실제 Multi-LLM 분기 구현.

분기 기준:
  task_type == "coding"  → qwen2.5-coder:32b  (QwenCoderClient)
  task_type == "vision"  → llava:13b           (Phase 6 후반)
  그 외                  → gemma4:e4b          (기본)

VRAM 주의:
  동시에 2개 모델 로드 시 VRAM 초과 가능
  한 번에 하나씩만 (lazy init + 교체 방식)
"""

import json
from datetime import datetime
from typing import Optional, Dict

from llm.base import BaseLLM

SYSTEM_LOG_PATH = "james_system_log.jsonl"

# ─── lazy init 캐시 ─────────────────────────────────────────

_llm_instances: Dict[str, BaseLLM] = {}


def _log(step: str, detail: str):
    try:
        entry = {"time": datetime.now().isoformat(), "level": "INFO",
                 "step": f"llm_router.{step}", "detail": detail[:200]}
        with open(SYSTEM_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _get_llm(model_key: str) -> Optional[BaseLLM]:
    """lazy init — 요청 시점에만 로드 (VRAM 절약)"""
    if model_key in _llm_instances:
        return _llm_instances[model_key]

    try:
        if model_key == "coding":
            from llm.providers.deepseek_client import QwenCoderClient
            inst = QwenCoderClient()   # qwen2.5-coder:32b
        elif model_key == "vision":
            from llm.providers.llava_client import LlavaClient
            inst = LlavaClient()       # llava:13b (Phase 6 후반)
        else:
            from llm.providers.ollama_client import OllamaClient
            inst = OllamaClient()      # gemma4:e4b 기본

        _llm_instances[model_key] = inst
        _log("load", f"모델 로드: {model_key} ({inst.name})")
        return inst

    except ImportError as e:
        _log("load_fail", f"{model_key}: {e}")
        return None


# ─── 공개 API ────────────────────────────────────────────────

def get_llm(task_type: str = "general") -> BaseLLM:
    """
    task_type 기반 LLM 선택.
    실패 시 기본 모델로 fallback.
    """
    model_key = {"coding": "coding", "vision": "vision"}.get(task_type, "default")

    llm = _get_llm(model_key)
    if llm is None or not llm.is_available():
        _log("fallback", f"task={task_type} → default fallback")
        llm = _get_llm("default")

    return llm


def classify_task(query: str) -> str:
    """
    쿼리 기반 task_type 자동 분류.
    LLM 호출 없이 키워드 기반으로만 판단.
    """
    q = query.lower()

    coding_keywords = [
        "코드", "함수", "클래스", "버그", "디버그", "리팩토링", "구현",
        "python", "javascript", "java", "def ", "class ", "import ",
        "algorithm", "code", "function", "error", "traceback", "syntax",
    ]
    if any(kw in q for kw in coding_keywords):
        return "coding"

    vision_keywords = ["이미지", "사진", "그림", "image", "photo", "picture", "vision"]
    if any(kw in q for kw in vision_keywords):
        return "vision"

    return "general"


def route(query: str, task_type: Optional[str] = None) -> BaseLLM:
    """
    쿼리 또는 명시적 task_type으로 LLM 라우팅.

    Args:
        query:     사용자 쿼리 (task_type 미지정 시 자동 분류)
        task_type: 명시적 지정

    Returns:
        선택된 LLM 인스턴스
    """
    if task_type is None:
        task_type = classify_task(query)

    llm = get_llm(task_type)
    _log("route", f"task={task_type} → {llm.name if llm else 'None'}")
    print(f"[LLM_ROUTER] task={task_type} → {llm.name if llm else 'fallback'}")
    return llm


def list_available() -> Dict[str, bool]:
    """현재 사용 가능한 LLM 목록"""
    result = {}
    for key in ["default", "coding", "vision"]:
        llm = _get_llm(key)
        result[key] = llm.is_available() if llm else False
    return result


# ─── 호환 helper (Issue #13) ──────────────────────────────────
#
# 기존 호출 site들은 GemmaClient.call_gemma(prompt, timeout, use_cache, max_tokens)
# 형태로 직접 호출하고 있다. Router의 BaseLLM.generate는 messages 형식이라
# 시그니처가 달라 substitution이 안 된다.
#
# call_router는 동일한 단일 prompt 인터페이스를 유지하면서 내부적으로
# router.route()를 거쳐 task-aware 모델로 전달한다. 결과적으로 각 호출
# site는 GemmaClient를 import하지 않고 task_type을 명시하는 형태로
# 1줄 마이그레이션이 가능해진다.
#
# 현재 모든 task_type이 결국 default(GemmaClient/gemma4:e4b)로 떨어지지만,
# Issue #15(어드민 모델 선택 persistence)가 들어오면 이 함수가 task별로
# 다른 모델을 자동 사용하게 된다.

def call_router(
    prompt:    str,
    task_type: Optional[str] = None,
    **kwargs,
) -> str:
    """call_gemma 호환 인터페이스. router를 거쳐 적절한 LLM에 prompt 전달."""
    llm = route(prompt, task_type=task_type)
    if llm is None:
        # Hard fallback: router가 모두 실패하면 GemmaClient 직접
        from core.gemma_client import GemmaClient
        return GemmaClient().call_gemma(prompt, **kwargs)
    messages = [{"role": "user", "content": prompt}]
    return llm.generate(messages, **kwargs)


class RouterWrapper:
    """GemmaClient.call_gemma 호환 인스턴스 wrapper (Issue #13 Phase 2).

    호출 site의 ``self.llm = GemmaClient()`` 패턴을
    ``self.llm = RouterWrapper("general")`` 로 1줄 교체하면 그 클래스의
    모든 ``.call_gemma(...)`` 호출이 자동으로 router를 거쳐
    task-aware 모델로 전달된다.

    task_type은 인스턴스 default를 가지고 가되, 호출 시점에 ``task_type=``
    kwarg로 override 가능. ``call_gemma_vision`` 은 현재 LLaVA wrapper가
    아직 multimodal generate를 지원하지 않아 GemmaClient에 직접 위임 —
    vision routing은 별도 작업.
    """

    def __init__(self, default_task: str = "general"):
        self.default_task = default_task
        self.name         = f"router_wrapper:{default_task}"

    def call_gemma(self, prompt: str, **kwargs) -> str:
        task = kwargs.pop("task_type", self.default_task)
        return call_router(prompt, task_type=task, **kwargs)

    def call_gemma_vision(self, prompt: str, image_path: str, **kwargs) -> str:
        from core.gemma_client import GemmaClient
        return GemmaClient().call_gemma_vision(prompt, image_path, **kwargs)

    def get_cache_stats(self) -> dict:
        """GemmaClient.get_cache_stats 호환 schema 반환.

        v0.1.3.1 hotfix — `core/reasoning_engine.py:920` 의 호출이 PR #18의
        ``self.llm`` 인스턴스 교체(GemmaClient → RouterWrapper) 이후
        AttributeError를 발생시켜 query 응답이 500으로 깨지는 회귀 fix.

        실제 cache는 OllamaClient가 호출 시점에 새 GemmaClient를 만드는
        구조라 누적되지 않는다. 정확한 cache 통계는 별도 후속 (router
        레벨 캐시 통합 — #15와 합본 후보). 여기서는 schema 일관성만
        지킨다 — reasoning_engine print에서 KeyError 안 나게.
        """
        try:
            from core.gemma_client import GemmaClient
            return GemmaClient().get_cache_stats()
        except Exception:
            return {
                "hits":       0,
                "misses":     0,
                "errors":     0,
                "total":      0,
                "hit_rate":   0.0,
                "hit_rate_%": "0.0%",
                "cache_size": 0,
                "ttl":        0,
            }

    def is_available(self) -> bool:
        return True


# ─── 자가 테스트 ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=== LLM Router 자가 테스트 ===\n")

    cases = [
        ("파이썬 함수 작성해줘", "coding"),
        ("코드 버그 찾아줘",     "coding"),
        ("경제학이란 무엇인가?", "general"),
        ("이 이미지를 분석해줘", "vision"),
        ("서울대학교 위치는?",   "general"),
    ]
    passed = 0
    for query, expected in cases:
        result = classify_task(query)
        ok = result == expected
        passed += int(ok)
        print(f"  {'✅' if ok else '❌'} '{query}' → {result} (기대={expected})")

    print(f"\n  결과: {passed}/{len(cases)} PASS")
