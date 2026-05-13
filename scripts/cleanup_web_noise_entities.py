"""Cleanup web-learn noise concept entities (continuation of #252 + #253).

Pre-PR-#252, every web-search learning call routed through the buggy
``save_as_longterm`` that stamped the user's *raw question string* as a
single ``entity_type: concept`` node with ``relations: []``. The result:
``wiki/entity/prod/concept/`` is now polluted with rows like

    엔비디아와_조비와_관계_조사해봐.md
    엔비디아_대해_묻고_있데_.md
    gpu_최근_개발_연구_대해__.md

— each is a leaf node with zero edges, the summary is "[Gemma 응답 없음]",
and the surface form is a Korean sentence rather than an entity name.
These nodes inflate the wiki, pollute concept-type queries, and crowd
the inference graph with disconnected dots.

This one-shot script identifies and removes them.

## Detection heuristic

A concept entity is flagged as web-learn noise when **all** of the
following hold:

1. ``entity_type == "concept"``
2. ``attributes.learn_method == "web_search"``
3. ``len(relations) == 0``
4. The surface ``name`` looks like a question / command rather than an
   entity, judged by either:
   - whitespace count ≥ 2 in the name, OR
   - the name contains one of the Korean question / imperative endings
     (조사해봐 · 묻고 · 알려줘 · 뭐야 · 설명해 · 이뭐 · 대해 · 싶어 · 싶다 · ?)

Properly extracted concepts (e.g. ``비트코인``, ``RAG``, ``Claude
Sonnet 4.6``) fail criterion 4 — they're single tokens or compact
multi-word names without question/imperative markers.

## Usage

    python scripts/cleanup_web_noise_entities.py                # dry run
    python scripts/cleanup_web_noise_entities.py --apply        # delete
    python scripts/cleanup_web_noise_entities.py --apply --no-backup

By default the script is **dry-run** — it only prints the candidates.
``--apply`` performs:

  1. zip backup of ``wiki/entity/{source_type}/concept/`` to
     ``workspace/backups/concept_<source_type>_<UTC>.zip`` (skipped if
     ``--no-backup``)
  2. delete each candidate ``.md`` file
  3. call ``vector_store.delete_by_source(<entity_sources>)`` to drop
     the matching ChromaDB chunks (best-effort; missing collection is
     non-fatal)

## Safety

- Idempotent: re-running after ``--apply`` is a no-op (the candidate
  files no longer exist, so detection returns an empty list).
- Only touches ``concept/`` — ``person`` / ``org`` / ``document``
  entities are never inspected or deleted (they were not affected by
  the pre-#252 bug).
- Does not touch the document entities that the buggy
  ``save_as_longterm`` also created (``web_<domain>_..._<ts>.md``).
  Those carry ``entity_type: document`` and are left for a follow-up
  pass if needed — keeping the blast radius minimal.
- Does not modify any other entity's ``relations`` — by criterion #3
  the candidates have no inbound edges from their own ``relations``
  field, and a separate audit would be needed to confirm no other
  entity points *to* them (none observed in practice — they were
  always leaf-only).
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

import yaml

# Allow `python scripts/cleanup_web_noise_entities.py` from repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Heuristic ────────────────────────────────────────────────────────

_QUESTION_PATTERNS = re.compile(
    r"(조사해|묻고|묻나|알려줘|뭐야|뭐냐|설명해|이뭐|대해|싶어|싶다|\?)",
)


def _is_question_like(name: str) -> bool:
    """Surface form looks like a user question rather than an entity name."""
    if name.count(" ") >= 2:
        return True
    return bool(_QUESTION_PATTERNS.search(name))


@dataclass(frozen=True)
class NoiseCandidate:
    path:      Path
    entity_id: str
    name:      str
    sources:   List[str]


def identify_noise_entities(concept_dir: Path) -> List[NoiseCandidate]:
    """Return every concept .md under *concept_dir* that matches the
    pre-#252 web-learn noise pattern.
    """
    if not concept_dir.exists():
        return []

    out: List[NoiseCandidate] = []
    for f in sorted(concept_dir.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue
        end = text.find("---", 3)
        if end < 0:
            continue
        try:
            fm = yaml.safe_load(text[3:end]) or {}
        except Exception:
            continue

        if fm.get("entity_type") != "concept":
            continue
        attrs = fm.get("attributes") or {}
        if not isinstance(attrs, dict):
            continue
        if attrs.get("learn_method") != "web_search":
            continue
        relations = fm.get("relations") or []
        if relations:  # 비어있지 않으면 청소 대상 아님 (분해됐을 가능성)
            continue
        name = (fm.get("name") or "").strip()
        if not name or not _is_question_like(name):
            continue

        out.append(NoiseCandidate(
            path      = f,
            entity_id = fm.get("entity_id") or "",
            name      = name,
            sources   = list(fm.get("sources") or []),
        ))
    return out


# ── Apply ────────────────────────────────────────────────────────────

def _zip_backup(concept_dir: Path, backup_root: Path, source_type: str) -> Path:
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = backup_root / f"concept_{source_type}_{stamp}"
    shutil.make_archive(str(out), "zip", root_dir=str(concept_dir))
    return out.with_suffix(".zip")


def _drop_vector_chunks(sources: Iterable[str]) -> int:
    """Best-effort ChromaDB cleanup. Returns the number of source keys
    that were attempted (not necessarily found)."""
    if not sources:
        return 0
    try:
        from core.vector_store import VectorStore
    except Exception as e:
        print(f"[CLEANUP] VectorStore import 실패 (ChromaDB 정리 건너뜀): {e}")
        return 0
    vs = VectorStore()
    n = 0
    for s in sources:
        if not s:
            continue
        try:
            vs.delete_by_source(s)
        except Exception as e:
            print(f"[CLEANUP] delete_by_source({s}) 실패 (무시): {e}")
        n += 1
    return n


def cleanup_entities(
    candidates:  List[NoiseCandidate],
    *,
    apply:       bool,
    backup_root: Optional[Path],
    source_type: str,
    concept_dir: Path,
) -> dict:
    """Delete each candidate's .md plus its ChromaDB chunks when
    *apply* is True. Otherwise no-op (returns the plan only)."""
    plan = {
        "candidate_count": len(candidates),
        "applied":         False,
        "backup_zip":      None,
        "deleted_files":   [],
        "vector_drops":    0,
    }
    if not candidates:
        return plan
    if not apply:
        return plan

    if backup_root is not None:
        plan["backup_zip"] = str(_zip_backup(concept_dir, backup_root, source_type))

    for c in candidates:
        try:
            c.path.unlink()
            plan["deleted_files"].append(str(c.path))
        except Exception as e:
            print(f"[CLEANUP] delete fail {c.path}: {e}")

    plan["vector_drops"] = _drop_vector_chunks(
        s for c in candidates for s in c.sources
    )
    plan["applied"] = True
    return plan


# ── CLI ──────────────────────────────────────────────────────────────

def _default_wiki_dir() -> Path:
    return Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) / "wiki"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    ap.add_argument("--apply", action="store_true",
                    help="실제 삭제 수행 (기본은 dry-run).")
    ap.add_argument("--no-backup", action="store_true",
                    help="--apply 와 함께 사용 시 zip 백업 생략 (권장하지 않음).")
    ap.add_argument("--source-type", choices=("prod", "test"), default="prod")
    ap.add_argument("--wiki-dir", type=Path, default=_default_wiki_dir(),
                    help="wiki 루트 경로 override (테스트용).")
    args = ap.parse_args(argv)

    concept_dir = args.wiki_dir / "entity" / args.source_type / "concept"
    backup_root = (args.wiki_dir.parent / "workspace" / "backups"
                   if not args.no_backup else None)

    candidates = identify_noise_entities(concept_dir)
    print(f"[CLEANUP] {len(candidates)} 후보 발견 "
          f"({args.source_type}/concept 디렉토리)")
    for c in candidates:
        print(f"  - {c.path.name}  |  name={c.name!r}")

    plan = cleanup_entities(
        candidates,
        apply       = args.apply,
        backup_root = backup_root,
        source_type = args.source_type,
        concept_dir = concept_dir,
    )

    if args.apply:
        print(f"[CLEANUP] 백업: {plan['backup_zip']}")
        print(f"[CLEANUP] 삭제: {len(plan['deleted_files'])} 파일")
        print(f"[CLEANUP] vector_store delete_by_source: "
              f"{plan['vector_drops']} 호출")
    else:
        print("[CLEANUP] dry-run 모드. 실제 삭제하려면 --apply 추가.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
