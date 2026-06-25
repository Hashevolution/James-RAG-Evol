"""
PROJECT JAMES — Configuration

All paths are relative to the project root (this file's location).
Sensitive values come from environment variables (.env file or system).
No hardcoded user paths — works on any machine after install.
"""

import logging
import os
import sys

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
        # `utf-8-sig` strips the BOM that Notepad / VS Code with default
        # settings adds when saving as "UTF-8". Without this, the FIRST
        # key parsed becomes '﻿JAMES_API_KEY' (instead of plain
        # 'JAMES_API_KEY'), every consumer reads back empty, and the
        # server fails fast with the unhelpful "must be set" error.
        # Confirmed on a real user's machine 2026-05-08.
        with open(_env_file, encoding="utf-8-sig") as _f:
            for _line in _f:
                _line = _line.strip()
                if not _line or _line.startswith("#") or "=" not in _line:
                    continue
                _k, _v = _line.split("=", 1)
                _k, _v = _k.strip(), _v.strip().strip('"').strip("'")
                # Defense-in-depth: also strip the BOM character per-key
                # in case some other tool emits it mid-file.
                _k = _k.lstrip("﻿")
                # Empty env values must NOT block .env loading. If a
                # parent process exported the var with empty string,
                # `_k in os.environ` is True but the value is "" — the
                # old check would skip the .env line and the empty env
                # value would propagate as the API key. We only respect
                # a pre-existing env value if it's non-empty.
                if _k and _v and not os.environ.get(_k):
                    os.environ[_k] = _v
        print(f"[CONFIG] .env loaded: {_env_file}")
    except Exception as _e:
        print(f"[CONFIG] .env load failed: {_e}")

# ────────────────────────────────────────────────────────────────
#  Base directories — auto-detected from this file's location
#  → Works regardless of folder name, OS, or user
#
#  Track C PR-C6.b: the four data directories (RAW_DIR / WIKI_DIR /
#  UPLOAD_DIR / CHROMA_DIR) honor JAMES_WORKSPACE via the resolver in
#  core.plugins.workspace. With the env unset the resolver returns
#  the project root, byte-identical to the pre-v0.3 behavior. With
#  JAMES_WORKSPACE=/some/dir the data dirs live under that workspace
#  while BASE_DIR (the project root, used for code/asset lookups)
#  stays anchored to this file's location.
# ────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))

from core.plugins.workspace import get_workspace_root  # noqa: E402

_WORKSPACE = str(get_workspace_root())
RAW_DIR    = os.path.join(_WORKSPACE, "raw")
WIKI_DIR   = os.path.join(_WORKSPACE, "wiki")
UPLOAD_DIR = os.path.join(_WORKSPACE, "uploads")
CHROMA_DIR = os.path.join(_WORKSPACE, "chroma_db")

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


def _llm_setting(key: str, env_name: str, default: str) -> str:
    """v0.6.1 — DB-first resolution via core.llm_settings, with the
    historical env name as fallback. Import is lazy + try/except so
    config.py stays importable even before the data DB exists (very
    early boot / test fixtures).

    Risk #1 mitigation (2026-06-15): if the operator set the env AND
    the DB has a different value, the DB silently wins. We print a
    one-time boot warning so the operator sees it before a long
    measurement run finishes with a tier-labelled-but-wrong-modeled
    result. Set ``JAMES_SETTINGS_USE_DB=0`` to disable the DB layer
    entirely (measurement runners do this)."""
    try:
        from core.llm_settings import get as _get, _use_db
        env_val = os.environ.get(env_name, "").strip()
        # Conflict detection: both env explicitly set AND DB row present
        # AND DB-mode active. Print to stderr once per boot per key.
        if env_val and _use_db():
            try:
                from core.llm_settings import _get_conn
                with _get_conn() as conn:
                    row = conn.execute(
                        "SELECT value FROM llm_settings WHERE key = ?",
                        (key,),
                    ).fetchone()
                if row and row[0] and row[0] != env_val:
                    import sys as _sys
                    _sys.stderr.write(
                        f"[CONFIG] WARN llm_settings conflict for {key!r}: "
                        f"{env_name}={env_val!r} but DB row={row[0]!r}. "
                        "DB wins. Set JAMES_SETTINGS_USE_DB=0 to use env.\n"
                    )
            except Exception:
                pass
        return _get(key, env_name, default)
    except Exception:
        return os.environ.get(env_name, default)


GEMMA_MODEL    = _llm_setting("default_model", "JAMES_LLM_MODEL", "gemma4:e4b")
# Coding-specialised model. Used by handle_coding via llm.router →
# QwenCoderClient. Operators can swap to a smaller/faster model
# (e.g. gemma4:e4b) if the 32B coder is too heavy for their tunnel
# / reverse proxy timeout.
CODING_MODEL   = _llm_setting("coding_model", "JAMES_CODING_MODEL", "qwen2.5-coder:32b")
# Vision / multimodal model. Used for image text-extraction + captioning
# during corpus ingest (processors/file_processor.extract_image →
# GemmaClient.call_gemma_vision) and the chat vision mode. MUST be a
# vision-capable model: sending images to a text-only model (the old bug —
# call_gemma_vision used GEMMA_MODEL) makes the LLM reply "no image
# attached", so uploaded images yielded no real text → no entities.
MULTIMODAL_MODEL = _llm_setting("multimodal_model", "JAMES_MULTIMODAL_MODEL", "qwen2.5vl:7b")
OLLAMA_API_URL = os.environ.get("OLLAMA_API_URL", "http://127.0.0.1:11434/api/generate")

# [Track 1 PR-C, 2026-05-19] LLM_TEMPERATURE — default sampling
# temperature passed to the model. Reserved kwarg per the Provider
# contract (docs/design/v0.3-llm-provider-contract.md §R4). The
# Gemma 4 3×3 experiment sweeps this variable, so backends used
# in that experiment must accept it.
#
# Default 0.2 preserves the byte-identical v0.3.0 behavior — that
# was the hardcoded value inside RouterWrapper.call_gemma before
# this PR. Override via JAMES_LLM_TEMPERATURE.
try:
    LLM_TEMPERATURE = float(os.environ.get("JAMES_LLM_TEMPERATURE", "0.2"))
except ValueError:
    # An unparseable env value (e.g. "high") falls back to 0.2 with
    # a warning rather than a hard crash — same forgiving pattern as
    # the rest of config.py. The operator sees the print at startup.
    print(
        f"[CONFIG] JAMES_LLM_TEMPERATURE="
        f"{os.environ.get('JAMES_LLM_TEMPERATURE')!r} is not a float "
        f"→ falling back to 0.2"
    )
    LLM_TEMPERATURE = 0.2

# ────────────────────────────────────────────────────────────────
#  ChromaDB
# ────────────────────────────────────────────────────────────────
CHROMA_COLLECTION = "james_prototype"


# ────────────────────────────────────────────────────────────────
#  Embedding model — v0.4 Sprint 4 BL-9 prep
# ────────────────────────────────────────────────────────────────
#  Default stays at paraphrase-multilingual-MiniLM-L12-v2 so any
#  operator pulling alpha.2 sees zero behaviour change. Setting
#  JAMES_EMBEDDING_MODEL flips the default for the next ingestion +
#  swaps `chroma_db` to a per-model directory + downloads the new
#  model on first run.
#
#  Candidates the Sprint 4 swap PR will measure:
#    BAAI/bge-m3                       — 24 layers, 1024 dim
#    intfloat/multilingual-e5-large    — 24 layers, 1024 dim
#
#  The MiniLM default is a 384-dim 12-layer model. Switching to a
#  1024-dim model means the existing chroma collection is unusable
#  (cosine search requires matching dimensions), so the resolver in
#  core/vector_store.py picks a per-model chroma directory
#  (`chroma_db_<short>` instead of plain `chroma_db`). The default
#  path remains `chroma_db` when the env is unset or matches the
#  legacy MiniLM tag — backward-compat invariant.
EMBEDDING_MODEL = os.environ.get(
    "JAMES_EMBEDDING_MODEL",
    "paraphrase-multilingual-MiniLM-L12-v2",
)


def _embedding_short_name(model_id: str) -> str:
    """Filesystem-safe short slug for a HF embedding model id.

    Used to derive `models/<short>` (cached weights) and
    `chroma_db_<short>` (per-model vector DB) without conflicting
    with the legacy `models/miniLM` + `chroma_db` paths the v0.3.x
    cycle has been writing to.
    """
    return (model_id.split("/")[-1]
                    .replace("-", "_")
                    .replace(".", "_")
                    .lower())

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
#  Self-evolution gate (#48, Axis 5)
# ────────────────────────────────────────────────────────────────
# Default off. Operators must opt in by setting JAMES_ENABLE_EVOLUTION=1.
# `/admin/patch/approve` returns 403 unless this is true.
EVOLUTION_ENABLED = os.environ.get("JAMES_ENABLE_EVOLUTION", "0") == "1"

# Role required to approve patches. Defaults to "admin".
APPROVER_ROLE = os.environ.get("JAMES_EVOLUTION_APPROVER_ROLE", "admin").strip().lower()

# Auto-approval. Tests / dev only — both flags must be true AND
# JAMES_DEV_MODE must be 1, otherwise the server refuses to start.
# This is the "fail-closed in production" guarantee from #48.
AUTO_APPROVE = os.environ.get("JAMES_AUTO_APPROVE", "0") == "1"
_DEV_MODE_AT_IMPORT = os.environ.get("JAMES_DEV_MODE", "1") == "1"
if AUTO_APPROVE and not _DEV_MODE_AT_IMPORT:
    raise RuntimeError(
        "JAMES_AUTO_APPROVE=1 requires JAMES_DEV_MODE=1 — auto-approval is "
        "not allowed in non-dev environments. Either unset JAMES_AUTO_APPROVE "
        "or set JAMES_DEV_MODE=1 explicitly. Refusing to start."
    )

# ────────────────────────────────────────────────────────────────
#  Startup messages
# ────────────────────────────────────────────────────────────────
print("[CONFIG] PROJECT JAMES ready")
print(f"[CONFIG] BASE_DIR: {BASE_DIR}")
print("[CONFIG] API_KEY source: env:JAMES_API_KEY")

if TESSERACT_PATH:
    print(f"[CONFIG] Tesseract: {TESSERACT_PATH}")
else:
    print("[CONFIG] Tesseract: not found (OCR will fail until installed)")

if POPPLER_PATH:
    print(f"[CONFIG] Poppler: {POPPLER_PATH}")

if TAVILY_API_KEY:
    print(f"[CONFIG] Tavily search enabled (key: {TAVILY_API_KEY[:8]}...)")
else:
    print("[CONFIG] Tavily key not set → using DuckDuckGo fallback")

# Evolution-gate banner — operator must see this on boot.
if EVOLUTION_ENABLED:
    print(f"[CONFIG] ⚙️  Self-evolution ENABLED (approver role: {APPROVER_ROLE})"
          + (f" — AUTO_APPROVE on (DEV_MODE={_DEV_MODE_AT_IMPORT})" if AUTO_APPROVE else ""))
else:
    print("[CONFIG] Self-evolution disabled (set JAMES_ENABLE_EVOLUTION=1 to enable)")
