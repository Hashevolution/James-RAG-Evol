"""GemmaClient — main LLM client class.

Extracted from the legacy single-file ``core/gemma_client.py``
during the v0.6 oversize-module split (CLAUDE.md rule #5). Behaviour
is byte-identical to the pre-split file; only the location moved.

The class encapsulates:
  * The Ollama HTTP call (``call_gemma``)
  * The Vision call (``call_gemma_vision``)
  * The bounded LRU response cache (with error-response rejection)
  * Cache statistics (hits / misses / errors / total)
  * The D6 follow-up ``_last_done_reason`` stash that
    ``OllamaClient.generate_meta`` reads to forward Ollama's native
    truncation signal upward.
"""
from __future__ import annotations

import base64
import hashlib
import time
from collections import OrderedDict
from typing import Optional

import requests

from config import GEMMA_MODEL, MULTIMODAL_MODEL, OLLAMA_API_URL, VISION_NUM_CTX
from core.gemma_client.config import _resolve_max_prompt_len
from core.gemma_client.errors import (
    is_cacheable_response,
    log_system_event,
)
from core.gemma_client.response_parser import (
    recover_think_block,
    recover_vision_response,
)


class GemmaClient:
    def __init__(self, cache_max_size: int = 100, cache_ttl: int = 600):
        self.cache            = OrderedDict()
        self.cache_timestamps = {}
        self.cache_max_size   = cache_max_size
        self.cache_ttl        = cache_ttl

        # [CACHE-STAT] 통계 카운터
        self._cache_hits   = 0
        self._cache_misses = 0
        self._cache_errors = 0   # 에러 응답 캐시 거부 횟수
        self._total_calls  = 0

        # D6 follow-up (2026-05-25) — native Ollama `done_reason`
        # stashed by the most recent uncached `call_gemma` invocation.
        # Read by `OllamaClient.generate_meta` so the
        # `ollama_local` backend can replace the length+terminator
        # heuristic with Ollama's native signal.
        #
        # Empty string when:
        #   - call_gemma hit a cached response (no fresh ollama call)
        #   - the upstream response did not include `done_reason`
        #     (Ollama < 0.1.30)
        #   - the call errored before reaching the response
        self._last_done_reason: str = ""

    # ─── 캐시 메서드 ─────────────────────────────────────────

    def _generate_cache_key(self, content: str) -> str:
        return hashlib.sha256(str(content).strip().lower().encode()).hexdigest()

    def _get_from_cache(self, cache_key: str):
        """[CACHE-BUG-FIX] 조회 시점에도 에러 응답 재검증.
        이전 실행에서 잘못 저장된 에러 응답 자동 제거.
        """
        if cache_key in self.cache:
            age = time.time() - self.cache_timestamps.get(cache_key, 0)
            if age < self.cache_ttl:
                value = self.cache[cache_key]

                # 기존에 저장된 에러 응답 감지 → 제거 후 None 반환
                if not is_cacheable_response(value):
                    print(f"[CACHE] 🧹 오래된 에러 응답 제거: '{value[:40]}'")
                    self.cache.pop(cache_key, None)
                    self.cache_timestamps.pop(cache_key, None)
                    self._cache_errors += 1
                    return None

                self.cache.move_to_end(cache_key)
                return value
            else:
                # TTL 만료 제거
                self.cache.pop(cache_key, None)
                self.cache_timestamps.pop(cache_key, None)
        return None

    def _set_cache(self, cache_key: str, value: str):
        """[CACHE-BUG-FIX] 정상 응답만 캐시 저장"""
        if not is_cacheable_response(value):
            self._cache_errors += 1
            print(f"[CACHE] 에러 응답 저장 거부: '{value[:40]}'")
            return

        while len(self.cache) >= self.cache_max_size:
            oldest_key, _ = self.cache.popitem(last=False)
            self.cache_timestamps.pop(oldest_key, None)

        self.cache[cache_key] = value
        self.cache.move_to_end(cache_key)
        self.cache_timestamps[cache_key] = time.time()

    # ─── [CACHE-STAT] 통계 ───────────────────────────────────

    def get_cache_stats(self) -> dict:
        total    = self._cache_hits + self._cache_misses
        hit_rate = self._cache_hits / total if total > 0 else 0.0
        return {
            "hits":       self._cache_hits,
            "misses":     self._cache_misses,
            "errors":     self._cache_errors,
            "total":      self._total_calls,
            "hit_rate":   round(hit_rate, 3),
            "hit_rate_%": f"{hit_rate * 100:.1f}%",
            "cache_size": len(self.cache),
            "ttl":        self.cache_ttl,
        }

    def reset_stats(self):
        self._cache_hits = self._cache_misses = self._cache_errors = self._total_calls = 0

    # ─── 메인 LLM 호출 ───────────────────────────────────────

    def call_gemma(
        self,
        prompt: str,
        timeout: int = 90,
        use_cache: bool = True,
        max_tokens: int = 0,
        model: str = None,
        temperature: float = None,
        think: Optional[bool] = None,
    ) -> str:
        """Gemma 모델 호출.

        [CACHE-BUG-FIX] 에러 응답 캐시 금지
        [C2-FIX]        <think> 블록 3단계 복구 (delegated to
                        ``response_parser.recover_think_block``)
        [CACHE-STAT]    hit/miss 카운터 업데이트
        [#15]           model override (None이면 config.GEMMA_MODEL 기본)
        [PR plan-1, 2026-05-09] model=None일 때 core.model_resolver로
            폴백. 운영자 PC에 config의 default 모델이 설치돼 있으면
            그것을 그대로 사용 (behavior unchanged). 미설치면 preference
            list에서 첫 설치된 것으로 자동 fallback. 결정은 [MODEL_RESOLVE]
            print로 로깅돼 운영자가 보임. 하나도 설치 안 된 경우 명확한
            "ollama pull X" 안내 메시지로 RuntimeError 발생.
        """
        # D6 follow-up (2026-05-25) — reset stale done_reason from
        # prior call before *anything else* (including model resolve
        # that may raise RuntimeError when no models are installed).
        # If reset happened after resolve, a failed resolve would
        # leave the previous truncation signal stashed and leak
        # upward through OllamaClient.generate_meta on the next
        # successful call. Reset-at-entry guarantees the invariant
        # "stash is empty unless the most recent uncached
        # resp.json() populated it."
        self._last_done_reason = ""

        if model:
            # Caller specified a tag — verify it's installed before
            # hitting Ollama. If not installed, the resolver falls
            # through to the preference list (defense for picker
            # selecting a not-yet-pulled model).
            # [PR plan-4, 2026-05-09] gracefully handles "user picked
            # gemma3:12b in dropdown but only gemma3:4b is installed".
            from core.model_resolver import installed_models, resolve_for_mode
            if model in installed_models():
                actual_model = model
            else:
                resolved = resolve_for_mode("chat", requested=model)
                if not resolved.tag:
                    raise RuntimeError(resolved.warning)
                actual_model = resolved.tag
                if resolved.warning:
                    print(f"[MODEL_RESOLVE] {resolved.warning}")
        else:
            from core.model_resolver import resolve_chat
            resolved = resolve_chat()
            if not resolved.tag:
                # No models at all in Ollama — surface the install
                # command rather than 404'ing through call_ollama.
                raise RuntimeError(resolved.warning)
            actual_model = resolved.tag
            if resolved.warning:
                print(f"[MODEL_RESOLVE] {resolved.warning}")
        self._total_calls += 1
        # A2 — think-mode is part of the request shape (§16.2: think=False
        # produces a different (shorter, no-trace) response than the
        # default). The cache key must vary with it, otherwise the first
        # think=ON answer would be returned to a later think=OFF caller
        # (silent staleness). Model also varies the response, so include
        # both in the key salt — keeps backward compat when think=None
        # and actual_model is the historical default.
        from core.reasoning.think_policy import is_thinking_capable
        emit_think = think is not None and is_thinking_capable(actual_model)
        cache_salt = f"|model={actual_model}|think={think if emit_think else 'default'}"
        cache_key = self._generate_cache_key(prompt + cache_salt)

        # 긴 프롬프트 캐시 금지
        if len(prompt) > 2000:
            use_cache = False

        # 캐시 조회
        if use_cache:
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                self._cache_hits += 1
                print(f"🔥 GEMMA CACHE HIT (hits={self._cache_hits})")
                age = time.time() - self.cache_timestamps.get(cache_key, 0)
                print(f"[DEBUG] cache age={age:.1f}s / TTL={self.cache_ttl}s")
                # _last_done_reason stays "" — caller treats absence
                # as "no truncation signal observed" (heuristic fallback
                # applies if caller uses ollama_local heuristic).
                return cached
            else:
                self._cache_misses += 1
                print(f"❌ GEMMA CACHE MISS (misses={self._cache_misses})")

        # 프롬프트 길이 제한 (env-configurable since cycle γ Phase B
        # smoke 2026-06-08; default 4000 = byte-identical pre-fix
        # behaviour for any caller that does not set the env var).
        MAX_PROMPT_LEN = _resolve_max_prompt_len()
        if len(prompt) > MAX_PROMPT_LEN:
            print(f"[GEMMA] 프롬프트 {len(prompt)}자 → {MAX_PROMPT_LEN}자 축약")
            prompt = prompt[:MAX_PROMPT_LEN]

        # 실제 모델 호출
        last_err = ""
        t_call   = time.time()
        for _ in range(1):   # 재시도 1회 고정 (이중 timeout 방지)
            try:
                # A2 — emit `think` field only when (caller specified)
                # AND (model is thinking-capable). Non-thinking models
                # reject `think:true` with HTTP 400 (§16.7); we omit the
                # field entirely to keep their request body byte-identical
                # to pre-A2. think=False on gemma4:e4b collapses eval_count
                # from ~400 to ~45 with the same visible answer (§16.2).
                body: dict = {
                    "model":  actual_model,
                    "prompt": prompt,
                    "stream": False,
                }
                if emit_think:
                    body["think"] = bool(think)
                body["options"] = {
                            # [#A8-5 2026-05-09] num_predict 기본값 2000 → 8192.
                            # 사용자 보고: "대화 글자수가 중간에 짤리지 않고
                            # 최대한 다 나올수 있도록". 이전 2000 토큰 ≈ 한국어
                            # 1500자 — 보고서 양식 답변 잘림. 8192는 gemma 8K
                            # 컨텍스트도 안전, 더 큰 모델은 자체 컨텍스트로
                            # 더 길게 가능. -1 (무제한)도 옵션이지만 runaway
                            # LLM 방어 위해 hard ceiling 유지.
                            "num_predict": max_tokens if max_tokens > 0 else 8192,
                            # [Track 1 PR-C, 2026-05-19] caller-supplied
                            # temperature wins; otherwise config.LLM_TEMPERATURE
                            # (default 0.2 — preserves v0.3.0 byte-identical
                            # determinism). Reserved kwarg per the Provider
                            # contract §R4 — also the 3×3 experiment's
                            # swept variable.
                            "temperature": (
                                temperature
                                if temperature is not None
                                else __import__("config").LLM_TEMPERATURE
                            ),
                            # [#A8-5] 4096 → 8192 (긴 답변 토큰까지 수용).
                            # JAMES_NUM_CTX env override (default 8192 =
                            # production byte-identical). Benchmark eval may
                            # raise it (e.g. 16384) so large retrieval
                            # evidence + a full CoT answer both fit without
                            # truncating the answer — gemma4:e4b supports
                            # up to 131072. Measurement-only; production
                            # unchanged when the env is unset.
                            "num_ctx": int(
                                __import__("os").environ.get(
                                    "JAMES_NUM_CTX", "8192"
                                )
                            ),
                        }
                resp = requests.post(
                    OLLAMA_API_URL,
                    json=body,
                    timeout=timeout,
                )
                resp.raise_for_status()
                resp_json = resp.json()
                output = resp_json.get("response", "").strip()
                # D6 follow-up — stash native done_reason for
                # OllamaClient.generate_meta to forward upward.
                # Ollama 0.1.30+ returns "stop" / "length" / "load";
                # older versions omit the field → "" left in place.
                self._last_done_reason = resp_json.get("done_reason", "") or ""
                elapsed_llm = time.time() - t_call
                print(f"[GEMMA] 응답 수신 ({elapsed_llm:.1f}s) | {len(output)}자")

                # [C2-FIX] <think> 블록 3단계 복구 — delegated to
                # ``response_parser.recover_think_block`` (split out
                # of this method for the v0.6 oversize-module split,
                # behaviour byte-identical).
                if not output:
                    result = "[Gemma 응답 없음]"
                    log_system_event(
                        "gemma.empty_response",
                        f"timeout={timeout}s elapsed={elapsed_llm:.1f}s",
                        level="WARN",
                    )
                else:
                    result = recover_think_block(output)

                # [CACHE-BUG-FIX] 정상 응답만 캐시 저장
                if use_cache:
                    self._set_cache(cache_key, result)

                return result

            except requests.exceptions.Timeout:
                last_err = f"응답 시간 초과 ({timeout}s)"
                print(f"[DEBUG] Gemma timeout ({timeout}s)")
                log_system_event("gemma.timeout", last_err, level="WARN")

            except Exception as e:
                last_err = str(e)
                print(f"[DEBUG] Gemma 오류: {e}")
                log_system_event("gemma.call_error", last_err)

        error_result = f"[Gemma 오류] {last_err}"
        # 에러 결과 → _set_cache 내부에서 자동 거부됨
        if use_cache:
            self._set_cache(cache_key, error_result)
        return error_result

    # ─── Vision 호출 ─────────────────────────────────────────

    def call_gemma_vision(self, prompt: str, image_path: str, timeout: int = 600) -> str:
        try:
            with open(image_path, "rb") as f:
                image_b64 = base64.b64encode(f.read()).decode("utf-8")

            resp = requests.post(
                OLLAMA_API_URL,
                json={
                    # MUST be a vision-capable model. GEMMA_MODEL (text)
                    # ignored the image → "no image attached" replies, so
                    # uploaded images produced no entities. See
                    # config.MULTIMODAL_MODEL.
                    "model":  MULTIMODAL_MODEL,
                    "prompt": prompt,
                    "images": [image_b64],
                    "stream": False,
                    # A high-res image's vision tokens + the prompt overflow
                    # the default 4096 context → HTTP 400 and zero text read.
                    # See config.VISION_NUM_CTX.
                    "options": {"num_ctx": VISION_NUM_CTX},
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            output = resp.json().get("response", "").strip()

            return recover_vision_response(output)

        except requests.exceptions.Timeout:
            return "[Gemma Vision 오류] 응답 시간 초과"
        except Exception as e:
            log_system_event("gemma_vision.error", str(e))
            return f"[Gemma Vision 오류] {str(e)}"

    # ─── 캐시 정리 ───────────────────────────────────────────

    def clear_expired_cache(self):
        current_time = time.time()
        expired = [k for k, t in self.cache_timestamps.items()
                   if current_time - t >= self.cache_ttl]
        for key in expired:
            self.cache.pop(key, None)
            self.cache_timestamps.pop(key, None)
        if expired:
            print(f"[CACHE] 만료 {len(expired)}개 제거")


__all__ = [
    "GemmaClient",
]
