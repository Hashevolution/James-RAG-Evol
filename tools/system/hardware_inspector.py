"""
PROJECT JAMES — Hardware Inspector (P3-1)

PC 하드웨어 성능을 자동 측정해서 "무기/장비" 형식으로 반환.

설계 철학:
  자메스 = 두뇌(지적 능력)
  하드웨어 = 무기/장비 (두뇌를 실행하는 물리 인프라)

  CPU  → ⚔️ 검  (연산 속도 = 공격력)
  RAM  → 🛡️ 방패 (메모리 = 방어력/지구력)
  GPU  → 🪄 마법봉 (병렬 추론 = 마법 능력)
  Disk → 🎒 가방 (저장 용량 = 지식 수납)
  NET  → 🌐 망토 (네트워크 = 이동 능력)
"""

import os
import platform
import sys
from typing import Dict, Any

# ─── 측정 함수 ─────────────────────────────────────────────────

def _get_cpu() -> Dict:
    """CPU 정보 측정."""
    info = {
        "name":  platform.processor() or "Unknown CPU",
        "arch":  platform.machine(),
        "cores": os.cpu_count() or 1,
        "freq_mhz": 0,
    }
    try:
        import psutil
        freq = psutil.cpu_freq()
        if freq:
            info["freq_mhz"] = int(freq.current)
        info["usage_pct"] = psutil.cpu_percent(interval=0.1)
    except ImportError:
        info["usage_pct"] = 0
    return info


def _get_ram() -> Dict:
    """RAM 정보 측정."""
    info = {"total_gb": 0, "used_gb": 0, "available_gb": 0, "pct": 0}
    try:
        import psutil
        mem = psutil.virtual_memory()
        info["total_gb"]     = round(mem.total / 1024**3, 1)
        info["used_gb"]      = round(mem.used  / 1024**3, 1)
        info["available_gb"] = round(mem.available / 1024**3, 1)
        info["pct"]          = mem.percent
    except ImportError:
        pass
    return info


def _get_gpu() -> Dict:
    """GPU 정보 측정 (pynvml → nvidia-smi → wmic 3-단계 fallback).

    Each fallback's failure reason is recorded in `info["debug"]` so a
    "GPU Unknown 0GB" outcome can be diagnosed without re-running the
    whole stack. The user-facing fields (`name` / `vram_gb` / `found`)
    are unchanged. Set `JAMES_HW_DEBUG=1` to also print to stdout.
    """
    info = {"name": "Unknown", "vram_gb": 0, "found": False, "debug": []}

    def _trace(msg: str) -> None:
        info["debug"].append(msg)
        if os.environ.get("JAMES_HW_DEBUG", "").strip() in ("1", "true", "yes"):
            print(f"[HW_GPU] {msg}", flush=True)

    # 방법 1: pynvml
    try:
        import pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        name   = pynvml.nvmlDeviceGetName(handle)
        mem    = pynvml.nvmlDeviceGetMemoryInfo(handle)
        info["name"]    = name.decode() if isinstance(name, bytes) else name
        info["vram_gb"] = round(mem.total / 1024**3, 1)
        info["used_gb"] = round(mem.used  / 1024**3, 1)
        info["found"]   = True
        _trace(f"pynvml OK: {info['name']} {info['vram_gb']}GB")
        return info
    except ImportError as e:
        _trace(f"pynvml not installed ({e}); falling back to nvidia-smi")
    except Exception as e:
        _trace(f"pynvml failed ({type(e).__name__}: {e}); falling back to nvidia-smi")

    # 방법 2: nvidia-smi subprocess
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
            encoding="utf-8", errors="replace",
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            if lines and lines[0]:
                parts = lines[0].split(',')
                if len(parts) >= 2:
                    info["name"]    = parts[0].strip()
                    info["vram_gb"] = round(int(parts[1].strip()) / 1024, 1)
                    info["found"]   = True
                    _trace(f"nvidia-smi OK: {info['name']} {info['vram_gb']}GB")
                    return info
                _trace(f"nvidia-smi parse failed: parts={parts!r}")
            else:
                _trace(f"nvidia-smi returned empty stdout")
        else:
            _trace(f"nvidia-smi exit={result.returncode} "
                   f"stderr={(result.stderr or '')[:120]!r}")
    except FileNotFoundError:
        _trace("nvidia-smi not found in PATH; falling back to wmic")
    except subprocess.TimeoutExpired:
        _trace("nvidia-smi timeout (>5s); falling back to wmic")
    except Exception as e:
        _trace(f"nvidia-smi failed ({type(e).__name__}: {e}); falling back to wmic")

    # 방법 3: Windows WMI (GPU 이름만 — VRAM은 4GB 이상에서 부정확)
    try:
        import subprocess
        result = subprocess.run(
            ["wmic", "path", "win32_VideoController",
             "get", "name,AdapterRAM", "/format:csv"],
            capture_output=True, text=True, timeout=5,
            encoding="utf-8", errors="replace",
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                parts = line.strip().split(',')
                if len(parts) >= 3 and parts[2].strip():
                    name = parts[2].strip()
                    if name and name != "Name":
                        info["name"]  = name
                        info["found"] = True
                        try:
                            vram = int(parts[1].strip())
                            info["vram_gb"] = round(vram / 1024**3, 1)
                        except Exception:
                            pass
                        _trace(f"wmic OK: {info['name']} {info['vram_gb']}GB")
                        return info
            _trace(f"wmic returned no usable rows: stdout={result.stdout[:200]!r}")
        else:
            _trace(f"wmic exit={result.returncode}")
    except FileNotFoundError:
        _trace("wmic not found in PATH (Windows 11 24H2+ removed it)")
    except subprocess.TimeoutExpired:
        _trace("wmic timeout (>5s)")
    except Exception as e:
        _trace(f"wmic failed ({type(e).__name__}: {e})")

    _trace("ALL fallbacks exhausted; GPU info unavailable")
    return info


def _get_disk() -> Dict:
    """디스크 정보 측정."""
    info = {"total_gb": 0, "used_gb": 0, "free_gb": 0, "pct": 0}
    try:
        import psutil
        # 프로젝트 폴더의 디스크 사용량
        try:
            from config import BASE_DIR
            disk_path = BASE_DIR
        except ImportError:
            disk_path = os.path.abspath(".")
        usage = psutil.disk_usage(disk_path)
        info["total_gb"] = round(usage.total / 1024**3, 1)
        info["used_gb"]  = round(usage.used  / 1024**3, 1)
        info["free_gb"]  = round(usage.free  / 1024**3, 1)
        info["pct"]      = usage.percent
    except Exception:
        pass
    return info


# ─── 레벨 계산 ─────────────────────────────────────────────────

def _cpu_level(cores: int, freq_mhz: int) -> int:
    """CPU 성능 → 1~10 레벨."""
    score = 0
    score += min(5, cores // 2)         # 코어 수
    score += min(4, freq_mhz // 1000)   # 클럭
    return max(1, min(10, score))


def _ram_level(total_gb: float) -> int:
    """RAM 용량 → 1~10 레벨."""
    thresholds = [4, 8, 16, 32, 64, 128, 256]
    for i, t in enumerate(thresholds):
        if total_gb < t:
            return i + 1
    return 10


def _gpu_level(name: str, vram_gb: float) -> int:
    """GPU 성능 → 1~10 레벨."""
    if not name or name == "Unknown":
        return 0
    # NVIDIA RTX 시리즈 감지
    name_lower = name.lower()
    if "4090" in name_lower: return 10
    if "4080" in name_lower: return 9
    if "4070" in name_lower: return 8
    if "4060" in name_lower: return 7
    if "3090" in name_lower: return 8
    if "3080" in name_lower: return 7
    if "3070" in name_lower: return 6
    if "3060" in name_lower: return 5
    if "rtx" in name_lower:  return 5
    if "gtx" in name_lower:  return 4
    # VRAM 기반 fallback
    if vram_gb >= 24: return 9
    if vram_gb >= 16: return 8
    if vram_gb >= 12: return 7
    if vram_gb >= 8:  return 6
    if vram_gb >= 6:  return 5
    if vram_gb >= 4:  return 4
    if vram_gb > 0:   return 3
    return 1


def _disk_level(free_gb: float) -> int:
    """디스크 여유 공간 → 1~10 레벨."""
    thresholds = [10, 30, 60, 100, 200, 500, 1000]
    for i, t in enumerate(thresholds):
        if free_gb < t:
            return i + 1
    return 10


# ─── 무기 메타데이터 ─────────────────────────────────────────

def _weapon_meta(component: str, level: int) -> Dict:
    """컴포넌트 + 레벨 → 무기 정보."""
    weapons = {
        "cpu": {
            "icon": "⚔️",
            "name_map": {
                (1, 3): "Wooden Sword",
                (4, 5): "Iron Sword",
                (6, 7): "Silver Blade",
                (8, 9): "Magic Sword",
                (10, 10): "Legendary Holy Sword",
            },
            "role": "Computing Power",
            "desc_map": {
                (1, 3): "Basic computation",
                (4, 5): "General inference",
                (6, 7): "Fast parallel processing",
                (8, 9): "High-speed reasoning engine",
                (10, 10): "Peak performance computing",
            }
        },
        "ram": {
            "icon": "🛡️",
            "name_map": {
                (1, 3): "Leather Shield",
                (4, 5): "Iron Shield",
                (6, 7): "Reinforced Shield",
                (8, 9): "Magic Shield",
                (10, 10): "Immortal Shield",
            },
            "role": "Memory",
            "desc_map": {
                (1, 3): "Small context handling",
                (4, 5): "General session management",
                (6, 7): "Wide context retention",
                (8, 9): "Large-scale batch processing",
                (10, 10): "Unlimited memory operations",
            }
        },
        "gpu": {
            "icon": "🪄",
            "name_map": {
                (0, 0): "(none)",
                (1, 3): "Apprentice Staff",
                (4, 5): "Wizard Staff",
                (6, 7): "Sage Staff",
                (8, 9): "Grand Wizard Staff",
                (10, 10): "Divine Wand",
            },
            "role": "GPU Inference",
            "desc_map": {
                (0, 0): "CPU-only inference",
                (1, 3): "Basic GPU acceleration",
                (4, 5): "LLM inference capable",
                (6, 7): "Fast LLM processing",
                (8, 9): "Ultra-fast inference",
                (10, 10): "Maximum AI acceleration",
            }
        },
        "disk": {
            "icon": "🎒",
            "name_map": {
                (1, 3): "Small Pouch",
                (4, 5): "Travel Bag",
                (6, 7): "Large Backpack",
                (8, 9): "Magic Space Bag",
                (10, 10): "Infinite Warehouse",
            },
            "role": "Storage",
            "desc_map": {
                (1, 3): "Small-scale wiki storage",
                (4, 5): "Medium-scale data",
                (6, 7): "Large knowledge base",
                (8, 9): "Massive data management",
                (10, 10): "Unlimited knowledge storage",
            }
        },
    }

    meta = weapons.get(component, {})
    icon = meta.get("icon", "🔧")
    role = meta.get("role", component)

    def _lookup(d, lv):
        for (lo, hi), val in d.items():
            if lo <= lv <= hi:
                return val
        return list(d.values())[-1]

    name = _lookup(meta.get("name_map", {}), level)
    desc = _lookup(meta.get("desc_map", {}), level)

    return {"icon": icon, "name": name, "role": role, "desc": desc}


# ─── 메인 API ──────────────────────────────────────────────────

def get_hardware_specs() -> Dict[str, Any]:
    """
    PC 하드웨어 측정 + 무기/장비 메타데이터 반환.

    반환 예:
    {
      "cpu": {
        "name": "Intel Core i9-13900K",
        "cores": 24,
        "freq_mhz": 3000,
        "level": 8,
        "weapon": {"icon": "⚔️", "name": "마법 검", ...}
      },
      "ram": {...},
      "gpu": {...},
      "disk": {...},
      "overall_level": 8,
      "james_rank": "대마법사"
    }
    """
    cpu  = _get_cpu()
    ram  = _get_ram()
    gpu  = _get_gpu()
    disk = _get_disk()

    cpu_lv  = _cpu_level(cpu["cores"], cpu.get("freq_mhz", 0))
    ram_lv  = _ram_level(ram["total_gb"])
    gpu_lv  = _gpu_level(gpu["name"], gpu.get("vram_gb", 0))
    disk_lv = _disk_level(disk.get("free_gb", 0))

    overall = int(
        cpu_lv  * 0.30 +
        ram_lv  * 0.25 +
        gpu_lv  * 0.35 +
        disk_lv * 0.10
    )

    rank_map = [
        (9, "Legendary Wizard"),
        (7, "Grand Wizard"),
        (5, "Wizard"),
        (3, "Apprentice Wizard"),
        (0, "Trainee"),
    ]
    rank = next(r for (th, r) in rank_map if overall >= th)

    return {
        "cpu":  {**cpu,  "level": cpu_lv,
                 "weapon": _weapon_meta("cpu", cpu_lv)},
        "ram":  {**ram,  "level": ram_lv,
                 "weapon": _weapon_meta("ram", ram_lv)},
        "gpu":  {**gpu,  "level": gpu_lv,
                 "weapon": _weapon_meta("gpu", gpu_lv)},
        "disk": {**disk, "level": disk_lv,
                 "weapon": _weapon_meta("disk", disk_lv)},
        "overall_level": max(1, overall),
        "james_rank":    rank,
        "platform":      platform.platform(),
    }


if __name__ == "__main__":
    import json
    specs = get_hardware_specs()
    print("\n🧠 자메스 장비 현황\n" + "═" * 40)
    for comp in ["cpu", "ram", "gpu", "disk"]:
        d = specs[comp]
        w = d["weapon"]
        print(f"\n{w['icon']} {w['name']} (Lv.{d['level']})  ← {w['role']}")
        print(f"   {d.get('name','')}")
        print(f"   {w['desc']}")
    print(f"\n🏅 전체 등급: Lv.{specs['overall_level']} — {specs['james_rank']}")


# ── [4-B] 하드웨어 기반 LLM 추천 매트릭스 ─────────────────────

LLM_CATALOG = [
    # name, tag, min_vram_gb, min_ram_gb, desc, purpose, size_gb
    {"name":"gemma4:e4b",         "tag":"gemma4:e4b",         "min_vram":4,  "min_ram":8,
     "desc":"가장 빠른 일상 대화",     "purpose":["chat","general"],    "size_gb":4.0},
    {"name":"gemma3:12b",         "tag":"gemma3:12b",         "min_vram":8,  "min_ram":16,
     "desc":"균형형 고성능 추론",       "purpose":["chat","retrieval"],  "size_gb":7.5},
    {"name":"gemma3:27b",         "tag":"gemma3:27b",         "min_vram":16, "min_ram":32,
     "desc":"최고 품질 추론",          "purpose":["chat","retrieval"],  "size_gb":16.0},
    {"name":"deepseek-coder:6.7b","tag":"deepseek-coder:6.7b","min_vram":4,  "min_ram":8,
     "desc":"코딩 특화 경량",          "purpose":["coding"],            "size_gb":4.1},
    {"name":"deepseek-coder:33b", "tag":"deepseek-coder:33b", "min_vram":16, "min_ram":32,
     "desc":"코딩 특화 최고성능",       "purpose":["coding"],            "size_gb":19.0},
    {"name":"llava:13b",          "tag":"llava:13b",          "min_vram":8,  "min_ram":16,
     "desc":"이미지+텍스트 분석",       "purpose":["multimodal"],        "size_gb":8.0},
    {"name":"llava:34b",          "tag":"llava:34b",          "min_vram":16, "min_ram":32,
     "desc":"고성능 멀티모달",          "purpose":["multimodal"],        "size_gb":20.0},
    {"name":"mistral:7b",         "tag":"mistral:7b",         "min_vram":4,  "min_ram":8,
     "desc":"빠른 유럽어 지원",         "purpose":["chat"],              "size_gb":4.1},
    {"name":"qwen2.5:14b",        "tag":"qwen2.5:14b",        "min_vram":10, "min_ram":16,
     "desc":"한국어+중국어 강화",        "purpose":["chat","retrieval"],  "size_gb":9.0},
    {"name":"phi4:14b",           "tag":"phi4:14b",           "min_vram":8,  "min_ram":16,
     "desc":"Microsoft 소형 고성능",    "purpose":["chat","coding"],     "size_gb":8.5},
]


def get_llm_recommendations(specs: dict) -> list:
    """
    [4-B] 하드웨어 스펙 기반 LLM 모델 추천.
    반환: 설치 가능 모델 목록 + 추천 이유
    """
    gpu    = specs.get("gpu", {})
    ram    = specs.get("ram", {})
    vram   = gpu.get("vram_gb", 0) if gpu.get("found") else 0
    ram_gb = ram.get("total_gb", 0)

    recommended = []
    for m in LLM_CATALOG:
        if vram >= m["min_vram"] and ram_gb >= m["min_ram"]:
            rec = {**m}
            # 추천 이유
            reasons = []
            if vram >= m["min_vram"] * 1.5:
                reasons.append("VRAM 여유 충분")
            if "coding" in m["purpose"]:
                reasons.append("코딩 에이전트 용도")
            if "multimodal" in m["purpose"]:
                reasons.append("이미지 분석 용도")
            rec["reasons"] = reasons
            rec["feasible"] = True
            recommended.append(rec)
        else:
            m_copy = {**m, "feasible": False,
                      "reason_fail": f"VRAM {m['min_vram']}GB 필요 (현재 {vram:.0f}GB)"}
            recommended.append(m_copy)

    # 추천 순서: purpose별 best 먼저
    feasible = [m for m in recommended if m["feasible"]]
    infeasible = [m for m in recommended if not m["feasible"]]
    return feasible + infeasible
