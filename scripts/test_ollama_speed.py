"""
PROJECT JAMES - Ollama/Gemma 성능 진단
실제 Gemma 응답 속도 측정
"""
import time
import requests

try:
    from config import OLLAMA_API_URL, GEMMA_MODEL
except ImportError:
    OLLAMA_API_URL = "http://127.0.0.1:11434/api/generate"
    GEMMA_MODEL    = "gemma4:e4b"


def test_ollama():
    print("=" * 55)
    print(f"  Ollama 진단 — 모델: {GEMMA_MODEL}")
    print("=" * 55)

    # 1. 서버 연결 확인
    try:
        r = requests.get("http://127.0.0.1:11434", timeout=5)
        print("  ✅ Ollama 서버 연결 OK")
    except Exception as e:
        print(f"  ❌ Ollama 연결 실패: {e}")
        return

    # 2. 짧은 프롬프트 테스트
    prompts = [
        ("짧은 프롬프트 (10자)",     "안녕"),
        ("중간 프롬프트 (100자)",    "다음 질문에 답하세요: 경제학은 무엇인가? 간단히 답해주세요."),
        ("긴 프롬프트 (1500자)",     "A" * 1500 + "\n위 내용 요약해주세요."),
    ]

    for label, prompt in prompts:
        print(f"\n  [{label}]")
        start = time.time()
        try:
            resp = requests.post(
                OLLAMA_API_URL,
                json={
                    "model":  GEMMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": 100, "temperature": 0.3},
                },
                timeout=120
            )
            elapsed = time.time() - start
            if resp.status_code == 200:
                output = resp.json().get("response", "")[:100]
                print(f"     ✅ {elapsed:.1f}s")
                print(f"        응답: {output[:80]}")
            else:
                print(f"     ❌ status={resp.status_code}")
        except requests.exceptions.Timeout:
            elapsed = time.time() - start
            print(f"     ⏱  TIMEOUT at {elapsed:.1f}s")
        except Exception as e:
            print(f"     ❌ 오류: {e}")

    # 3. 모델 로드 상태 확인
    print("\n  [모델 로드 확인]")
    try:
        r = requests.get("http://127.0.0.1:11434/api/tags", timeout=5)
        if r.status_code == 200:
            models = r.json().get("models", [])
            names  = [m.get("name") for m in models]
            print(f"     설치된 모델: {names}")
            if GEMMA_MODEL in names or any(GEMMA_MODEL in n for n in names):
                print(f"     ✅ {GEMMA_MODEL} 존재")
            else:
                print(f"     ❌ {GEMMA_MODEL} 없음")
    except Exception as e:
        print(f"     ❌ {e}")

    print()
    print("=" * 55)
    print("  판정")
    print("=" * 55)
    print("""
  짧은 프롬프트가 30초 이상 걸리면:
    → Ollama/Gemma 자체가 느림 (하드웨어 or 모델 이슈)
    → 더 작은 모델 고려: ollama pull gemma2:2b
    → GPU 가속 확인

  짧은 < 10초, 긴 > 60초라면:
    → 프롬프트 길이가 원인
    → context 더 축소 필요

  모두 timeout이면:
    → Ollama 서버 재시작 필요
    → ollama serve 로그 확인
    """)


if __name__ == "__main__":
    test_ollama()
