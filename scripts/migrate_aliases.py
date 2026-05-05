"""Backfill `aliases` for existing wiki entities (Issue #7 fix).

For each entity .md under wiki/entity/{prod,test}, regenerate `aliases`
from `name` via wiki_generator._expand_alias_candidates and merge with
the existing list (dedup, preserve original order).

Why: STEP 7 found that LLM-extracted entity names ("RAG") miss matching
when the wiki entity is stored with a verbose name ("RAG (검색 증강
생성)") because aliases only contained the full form. The fix adds
short forms automatically — but pre-existing entities still need to
be backfilled.

Usage:
    python scripts/migrate_aliases.py              # dry run, prints diff
    python scripts/migrate_aliases.py --apply      # rewrite files

The script preserves the body (everything after the closing `---`).
Frontmatter is parsed with PyYAML and re-dumped with allow_unicode=True
and sort_keys=False so existing key order survives the round-trip.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.wiki_generator import _expand_alias_candidates  # noqa: E402

WIKI_BASE = ROOT / "wiki" / "entity"
FM_RE     = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)


def normalize_aliases(name: str, existing: object) -> list[str]:
    """Merge expanded alias candidates with existing list (dedup, ordered)."""
    if not isinstance(existing, list):
        existing = [str(existing)] if existing else []
    existing_str = [str(a).strip() for a in existing if a]
    expanded     = _expand_alias_candidates(name)
    seen: set[str] = set()
    merged: list[str] = []
    for a in [*existing_str, *expanded]:
        if a and a not in seen:
            seen.add(a)
            merged.append(a)
    return merged


def process_file(path: Path, apply: bool) -> tuple[bool, list[str]]:
    """Return (changed, added_aliases). Rewrites file if apply=True."""
    text = path.read_text(encoding="utf-8")
    m = FM_RE.match(text)
    if not m:
        return False, []
    fm_text = m.group(1)
    body    = m.group(2)
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        return False, []
    name = fm.get("name", "")
    if not name:
        return False, []
    existing = fm.get("aliases") or []
    new_list = normalize_aliases(name, existing)
    if new_list == ([str(a) for a in (existing or [])] if isinstance(existing, list) else [str(existing)]):
        return False, []
    added = [a for a in new_list if a not in (existing if isinstance(existing, list) else [])]
    fm["aliases"] = new_list
    if apply:
        new_fm = yaml.safe_dump(
            fm, allow_unicode=True, sort_keys=False, default_flow_style=False,
        ).rstrip()
        path.write_text(f"---\n{new_fm}\n---\n{body}", encoding="utf-8")
    return True, added


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="actually rewrite files (default: dry run)")
    args = ap.parse_args()

    files = sorted(WIKI_BASE.rglob("*.md"))
    print(f"Scanning {len(files)} entity files under {WIKI_BASE.relative_to(ROOT)}/")
    print(f"Mode: {'APPLY' if args.apply else 'DRY RUN'}\n")

    changed = 0
    total_added = 0
    for f in files:
        ok, added = process_file(f, apply=args.apply)
        if ok:
            changed += 1
            total_added += len(added)
            rel = f.relative_to(ROOT)
            label = ", ".join(repr(a) for a in added) if added else "(re-ordered)"
            print(f"  + {rel} -> {label}")

    print(f"\nresult: {changed}/{len(files)} files would be updated, "
          f"{total_added} aliases added")
    if not args.apply and changed > 0:
        print("Re-run with --apply to write changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
