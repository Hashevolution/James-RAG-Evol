"""
PROJECT JAMES — Configuration

All paths are relative to the project root (this file's location).
Sensitive values come from environment variables (.env file or system).
No hardcoded user paths — works on any machine after install.
"""

import logging
import os
import sys
from pathlib import Path

# ────────────────────────────────────────────────────────────────
#  pdfminer 노이즈 차단
# ────────────────────────────────────────────────────────────────
# markitdown[pdf]가 의존하는 pdfminer는 폰트 메타데이터 누락 시
# 매 페이지 WARNING을 찍는다. e.g. "Could not get FontBBox from
# font descriptor". 텍스트 추출 자체는 성공하므로 무해하지만,
# 30개 PDF 일괄 업로드처럼 양이 많으면 콘솔이 도배된다.
# ERROR 이상만 살려서 진짜 문제만 보이게 한다.
for _noisy in ("pdfminer", "pdfminer.pdffont", "pdfminer.pdfinterp"):
    logging.getLogger(_noisy).setLevel(logging.ERROR)

# ────────────────────────────────────────────────────────────────
#  .env 파일 자동 로드 (프로젝트 루트에 .env가 있으면)
# ────────────────────────────────────────────────────────────────
_env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_file):
    try:
        with open(_env_file, encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if not _line or _line.startswith("#") or "=" not in _line:
                    continue
                _k, _v = _line.split("=", 1)
                _k, _v = _k.strip(), _v.strip().strip('"').strip("'")
                if _k and _v and _k not in os.environ:
                    os.environ[_k] = _v
        print(f"[CONFIG] .env loaded: {_env_file}")
    except Exception as _e:
        print(f"[CONFIG] .env load failed: {_e}")

# ────────────────────────────────────────────────────────────────
#  Base directories — auto-detected from this file's location
#  → Works regardless of folder name, OS, or user
# ────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
RAW_DIR    = os.path.join(BASE_DIR, "raw")
WIKI_DIR   = os.path.join(BASE_DIR, "wiki")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
CHROMA_DIR = os.path.join(BASE_DIR, "chroma_db")

# ────────────────────────────────────────────────────────────────
#  Tesseract OCR — auto-detect by OS, override via env var
# ────────────────────────────────────────────────────────────────
def _detect_tesseract():
    """Find Tesseract binary in common install locations."""
    # Priority 1: explicit env var
    env_path = os.environ.get("TESSERACT_PATH", "")
    if env_path and os.path.exists(env_path):
        return env_path

    # Priority 2: OS-specific common paths
    if sys.platform == "win32":
        candidates = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
        ]
    elif sys.platform == "darwin":  # macOS
        candidates = [
            "/opt/homebrew/bin/tesseract",
            "/usr/local/bin/tesseract",
        ]
    else:  # Linux
        candidates = [
            "/usr/bin/tesseract",
            "/usr/local/bin/tesseract",
        ]

    for path in candidates:
        if os.path.exists(path):
            return path
    return ""  # not found — pytesseract will raise on first use

TESSERACT_PATH = _detect_tesseract()
try:
    import pytesseract
    if TESSERACT_PATH:
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
except ImportError:
    pass  # OCR optional

# ────────────────────────────────────────────────────────────────
#  Poppler (for pdf2image) — auto-detect by OS, override via env
# ────────────────────────────────────────────────────────────────
def _detect_poppler():
    """Find Poppler bin directory."""
    env_path = os.environ.get("JAMES_POPPLER_PATH", "")
    if env_path and os.path.exists(env_path):
        return env_path

    if sys.platform == "win32":
        # Common Windows install patterns
        candidates = [
            r"C:\poppler\Library\bin",
            r"C:\Program Files\poppler\Library\bin",
            os.path.expandvars(r"%LOCALAPPDATA%\poppler\Library\bin"),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
    # On Mac/Linux, poppler is on PATH after `brew install poppler` / `apt install poppler-utils`
    return ""  # use system PATH

POPPLER_PATH = _detect_poppler()

# ────────────────────────────────────────────────────────────────
#  Ollama / LLM
# ────────────────────────────────────────────────────────────────
# Ollama runs as a service — usually no need to specify binary path.
# If you need to start it from JAMES, set OLLAMA_PATH env var.
OLLAMA_PATH    = os.environ.get("OLLAMA_PATH", "")  # blank = use system 'ollama' on PATH
GEMMA_MODEL    = os.environ.get("JAMES_LLM_MODEL", "gemma2:2b")
OLLAMA_API_URL = os.environ.get("OLLAMA_API_URL", "http://127.0.0.1:11434/api/generate")

# ────────────────────────────────────────────────────────────────
#  ChromaDB
# ────────────────────────────────────────────────────────────────
CHROMA_COLLECTION = "james_prototype"

# ────────────────────────────────────────────────────────────────
#  API Key — required for production, falls back for dev
# ────────────────────────────────────────────────────────────────
# Set via:
#   .env file:    JAMES_API_KEY=your_key
#   PowerShell:   $env:JAMES_API_KEY="your_key"
#   Bash/Zsh:     export JAMES_API_KEY=your_key
API_KEY = os.environ.get("JAMES_API_KEY", "")
if not API_KEY:
    # P0 보안 (v0.1.3.1 handover Item C) — fail-fast.
    # 이전엔 "dev_only_change_me" hardcode fallback. WARNING 한 줄만 출력하고
    # 그대로 운영 진입 가능했고, 그 secret으로 인증 통과한 client는 admin
    # 권한까지 받음. 더이상 silent.
    raise RuntimeError(
        "JAMES_API_KEY must be set in .env or environment before starting "
        "the server. Generate one with:\n"
        "    python -c \"import secrets; print(secrets.token_urlsafe(32))\""
    )

# ────────────────────────────────────────────────────────────────
#  Upload limits
# ────────────────────────────────────────────────────────────────
MAX_UPLOAD_MB    = int(os.environ.get("JAMES_MAX_UPLOAD_MB", "100"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
UPLOAD_FOLDER    = UPLOAD_DIR  # alias

# ────────────────────────────────────────────────────────────────
#  Web search (Tavily primary, DuckDuckGo fallback)
# ────────────────────────────────────────────────────────────────
# Tavily: https://tavily.com — free 1,000 req/month
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")

# ────────────────────────────────────────────────────────────────
#  Startup messages
# ────────────────────────────────────────────────────────────────
print(f"[CONFIG] PROJECT JAMES ready")
print(f"[CONFIG] BASE_DIR: {BASE_DIR}")
print("[CONFIG] API_KEY source: env:JAMES_API_KEY")

if TESSERACT_PATH:
    print(f"[CONFIG] Tesseract: {TESSERACT_PATH}")
else:
    print(f"[CONFIG] Tesseract: not found (OCR will fail until installed)")

if POPPLER_PATH:
    print(f"[CONFIG] Poppler: {POPPLER_PATH}")

if TAVILY_API_KEY:
    print(f"[CONFIG] Tavily search enabled (key: {TAVILY_API_KEY[:8]}...)")
else:
    print(f"[CONFIG] Tavily key not set → using DuckDuckGo fallback")
