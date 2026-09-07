"""[PR plan-2, 2026-05-09] Central LLM model registry — single source of truth.

Before this module, model metadata lived in two places:
  - tools/system/hardware_inspector.LLM_CATALOG (10 entries, hardware
    feasibility evaluation)
  - core/model_catalog._model_catalog (mode → candidate list, chat
    picker; uses config.GEMMA_MODEL to fold in operator's default)

Adding a new model meant editing both. Worse, the two lists could
drift — the chat picker and the hardware recommendation could
disagree on whether a given tag is "supported".

This module is now the single registry. Both sites read from here:
  - core.model_catalog.model_catalog() builds per-mode lists by
    purpose-filtering CATALOG and sorting by weight class
  - tools.system.hardware_inspector reads via the LLM_CATALOG alias
    + get_llm_recommendations delegates to recommend_for_hardware
  - core.model_resolver could derive its preference lists from here
    (deferred — preference order is opinionated about Korean quality
    and doesn't fit cleanly in the metadata schema)

Schema per entry:
  tag          : Ollama tag exactly as `ollama pull` expects
  weight       : "light" | "medium" | "heavy" — UI weight icon group
  purpose      : list of {chat, retrieval, coding, multimodal, general}
  min_vram_gb  : minimum VRAM to run with reasonable speed
  min_ram_gb   : minimum system RAM
  size_gb      : approximate download size
  description  : Korean operator-facing one-liner
  language     : optional list — primary languages the model handles
                  well ("ko", "en", "zh", "general")
"""
from __future__ import annotations

from typing import List, Optional


CATALOG: List[dict] = [
    # ─── Gemma 3 family — primary chat recommendations ──────────────
    {
        "tag":         "gemma3:1b",
        "weight":      "light",
        "purpose":     ["chat"],
        "min_vram_gb": 0, "min_ram_gb": 4,    # CPU-only OK (with patience)
        "size_gb":     1.0,
        "description": "초경량 일상 대화 (8GB RAM, GPU 없어도 OK)",
        "language":    ["en", "ko"],
    },
    {
        "tag":         "gemma3:4b",
        "weight":      "light",
        "purpose":     ["chat", "retrieval", "general"],
        "min_vram_gb": 0, "min_ram_gb": 8,    # CPU-only feasible, GPU 가속 권장
        "size_gb":     3.0,
        "description": "권장 일상 대화 (16GB RAM)",
        "language":    ["en", "ko"],
    },
    {
        "tag":         "gemma3:12b",
        "weight":      "medium",
        "purpose":     ["chat", "retrieval"],
        "min_vram_gb": 8, "min_ram_gb": 16,
        "size_gb":     7.5,
        "description": "균형형 고성능 추론",
        "language":    ["en", "ko"],
    },
    {
        "tag":         "gemma3:27b",
        "weight":      "heavy",
        "purpose":     ["chat", "retrieval"],
        "min_vram_gb": 16, "min_ram_gb": 32,
        "size_gb":     16.0,
        "description": "최고 품질 추론",
        "language":    ["en", "ko"],
    },

    # ─── Gemma 4 — operator's existing default ─────────────────────
    {
        "tag":         "gemma4:e4b",
        "weight":      "light",
        "purpose":     ["chat", "retrieval", "general"],
        "min_vram_gb": 4, "min_ram_gb": 8,
        "size_gb":     4.0,
        "description": "운영자 default (gemma 4 family)",
        "language":    ["en", "ko"],
    },

    # ─── Gemma 2 (older, legacy fallback) ───────────────────────────
    {
        "tag":         "gemma2:2b",
        "weight":      "light",
        "purpose":     ["chat"],
        "min_vram_gb": 0, "min_ram_gb": 4,    # CPU-only OK
        "size_gb":     1.6,
        "description": "구버전이지만 가벼움 (legacy fallback)",
        "language":    ["en"],
    },

    # ─── Qwen family — Korean/Chinese strong, coder series ──────────
    {
        "tag":         "qwen2.5:14b",
        "weight":      "medium",
        "purpose":     ["chat", "retrieval"],
        "min_vram_gb": 10, "min_ram_gb": 16,
        "size_gb":     9.0,
        "description": "한국어+중국어 강화 14B",
        "language":    ["ko", "zh", "en"],
    },
    {
        "tag":         "qwen2.5-coder:7b",
        "weight":      "light",
        "purpose":     ["coding"],
        "min_vram_gb": 4, "min_ram_gb": 8,
        "size_gb":     4.5,
        "description": "코딩 특화 경량",
        "language":    ["en"],
    },
    {
        "tag":         "qwen2.5-coder:14b",
        "weight":      "medium",
        "purpose":     ["coding"],
        "min_vram_gb": 10, "min_ram_gb": 16,
        "size_gb":     9.0,
        "description": "코딩 특화 균형형",
        "language":    ["en"],
    },
    {
        "tag":         "qwen2.5-coder:32b",
        "weight":      "heavy",
        "purpose":     ["coding"],
        "min_vram_gb": 16, "min_ram_gb": 32,
        "size_gb":     19.0,
        "description": "코딩 특화 최고성능",
        "language":    ["en"],
    },

    # ─── DeepSeek coder (alternative coding family) ─────────────────
    {
        "tag":         "deepseek-coder:6.7b",
        "weight":      "light",
        "purpose":     ["coding"],
        "min_vram_gb": 4, "min_ram_gb": 8,
        "size_gb":     4.1,
        "description": "코딩 특화 경량 (대안)",
        "language":    ["en"],
    },
    {
        "tag":         "deepseek-coder:33b",
        "weight":      "heavy",
        "purpose":     ["coding"],
        "min_vram_gb": 16, "min_ram_gb": 32,
        "size_gb":     19.0,
        "description": "코딩 특화 최고성능 (대안)",
        "language":    ["en"],
    },

    # ─── Multimodal vision ─────────────────────────────────────────
    {
        # v0.6.1 default MULTIMODAL_MODEL (config.py, PR #1070 A/B —
        # reads dense Korean document photos llava:13b cannot).
        # Catalog entry added 2026-07-01 to close the drift between
        # config default and this catalog (hardware recommender +
        # admin picker read this list).
        "tag":         "qwen2.5vl:7b",
        "weight":      "light",
        "purpose":     ["multimodal"],
        "min_vram_gb": 6, "min_ram_gb": 16,
        "size_gb":     6.0,
        "description": "이미지+텍스트 분석 (문서 사진 OCR 강함, 기본값)",
        "language":    ["multi", "ko", "en"],
    },
    {
        "tag":         "llava:13b",
        "weight":      "medium",
        "purpose":     ["multimodal"],
        "min_vram_gb": 8, "min_ram_gb": 16,
        "size_gb":     8.0,
        "description": "이미지+텍스트 분석",
        "language":    ["en"],
    },
    {
        "tag":         "llava:34b",
        "weight":      "heavy",
        "purpose":     ["multimodal"],
        "min_vram_gb": 16, "min_ram_gb": 32,
        "size_gb":     20.0,
        "description": "고성능 멀티모달",
        "language":    ["en"],
    },

    # ─── General-purpose alternatives ──────────────────────────────
    {
        "tag":         "llama3.2:3b",
        "weight":      "light",
        "purpose":     ["chat"],
        "min_vram_gb": 2, "min_ram_gb": 8,
        "size_gb":     2.5,
        "description": "Meta Llama 3.2 (영어 강함)",
        "language":    ["en"],
    },
    {
        "tag":         "mistral:7b",
        "weight":      "light",
        "purpose":     ["chat"],
        "min_vram_gb": 4, "min_ram_gb": 8,
        "size_gb":     4.1,
        "description": "유럽어 지원 빠른 모델",
        "language":    ["en"],
    },
    {
        "tag":         "phi4:14b",
        "weight":      "medium",
        "purpose":     ["chat", "coding"],
        "min_vram_gb": 8, "min_ram_gb": 16,
        "size_gb":     8.5,
        "description": "Microsoft 소형 고성능",
        "language":    ["en"],
    },
]


# Weight-class ordering for stable sorts.
_WEIGHT_ORDER = {"light": 0, "medium": 1, "heavy": 2}


# ─── Lookups ──────────────────────────────────────────────────────
def by_tag(tag: str) -> Optional[dict]:
    """Lookup an entry by exact tag. None if not found."""
    if not tag:
        return None
    for entry in CATALOG:
        if entry["tag"] == tag:
            return entry
    return None


def by_purpose(purpose: str) -> List[dict]:
    """Return all entries whose `purpose` list contains `purpose`."""
    if not purpose:
        return []
    return [e for e in CATALOG if purpose in e.get("purpose", [])]


def all_tags() -> List[str]:
    """All tags in the catalog (dedup-safe)."""
    return [e["tag"] for e in CATALOG]


# ─── Hardware feasibility ─────────────────────────────────────────
def feasible_for_hardware(vram_gb: float, ram_gb: float) -> List[dict]:
    """Entries whose min_vram_gb + min_ram_gb fit within hardware specs."""
    out = []
    for e in CATALOG:
        if vram_gb >= e.get("min_vram_gb", 0) and ram_gb >= e.get("min_ram_gb", 0):
            out.append(e)
    return out


def recommend_for_hardware(specs: dict, top_n: int = 3) -> dict:
    """Top-N recommendations per purpose, given hardware specs.

    `specs` shape (from hardware_inspector.get_hardware_specs):
      {
        "gpu": {"found": bool, "vram_gb": int, "name": str, ...},
        "ram": {"total_gb": int, ...},
        ...
      }

    Returns: {chat: [...], coding: [...], multimodal: [...]}
      Each list contains up to `top_n` catalog entries that the
      hardware can run, sorted by size_gb descending (more-capable first
      within the feasibility envelope).

    The first-run wizard (PR plan-3) uses this to suggest the right
    install for the operator's machine.
    """
    gpu = specs.get("gpu", {}) or {}
    ram = specs.get("ram", {}) or {}
    vram = float(gpu.get("vram_gb", 0)) if gpu.get("found") else 0.0
    ram_gb = float(ram.get("total_gb", 0))

    feasible = feasible_for_hardware(vram, ram_gb)

    out: dict = {}
    for purpose in ("chat", "coding", "multimodal"):
        cands = [e for e in feasible if purpose in e.get("purpose", [])]
        # Most-capable first (largest size_gb that still fits).
        cands.sort(key=lambda e: (e.get("size_gb", 0), -_WEIGHT_ORDER.get(e.get("weight"), 99)),
                   reverse=True)
        out[purpose] = cands[:top_n]
    return out
