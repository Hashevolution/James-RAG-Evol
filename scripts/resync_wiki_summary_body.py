"""Resync the `## 요약` body section of every wiki entity from its
frontmatter `summary` field.

## Why this script exists

Before B-2-A (PR #445), the ingest path stored the LLM description at
`attributes.summary` but the wiki body builder
(`core/wiki_generator/_frontmatter.py:create_entity_file`) read only
top-level `summary` / `description`. The result: every entity .md file
under `wiki/entity/**` was written with a blank `## 요약` section even
when `attributes.summary` carried a real description.

PR #445 fixes the *forward* path — new ingests now mirror the value to
top-level `summary` and the body builder picks it up. This script
patches the *backlog*: roughly 100s of entity files already on disk
whose bodies are stale.

It is intentionally a one-shot script (the same pattern as
`cleanup_web_noise_entities.py`), not a runtime hook — touching every
wiki file on every startup would be wasteful and would mask future
bugs in the forward path.

## What it changes

For each `wiki/entity/**/*.md`:

1. Parse the frontmatter (PyYAML).
2. Resolve the canonical summary:
   `fm.get("summary") or fm.get("attributes", {}).get("summary") or ""`
3. Find the `## 요약\\n` ... `\\n## 관계` window in the body and rewrite
   the content between them to the canonical summary.
4. If frontmatter top-level `summary` is missing but
   `attributes.summary` exists, also write top-level (canonical).

Files where the body is *already* in sync are left untouched.

## Usage

    python scripts/resync_wiki_summary_body.py              # dry-run
    python scripts/resync_wiki_summary_body.py --apply      # write
    python scripts/resync_wiki_summary_body.py --apply --verbose

## Safety

- Dry-run by default. Prints diff-style per-file output.
- `--apply` writes files in place. Run on a clean working tree so
  `git diff` shows the resync delta.
- Skips files that don't parse as wiki entities (no `entity_id` /
  `entity_type` in frontmatter).
- Skips files whose body already matches the canonical value (idempotent).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Tuple

import yaml

# Path bootstrap: scripts/ is run as a top-level script, so `core.*`
# imports need the repo root on sys.path. Match the convention used by
# scripts/cleanup_web_noise_entities.py.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.wiki_generator import sync_summary_body  # noqa: E402


WIKI_ROOT = Path(__file__).resolve().parent.parent / "wiki" / "entity"


def _split_frontmatter(raw: str) -> Tuple[dict, str, str]:
    """Return (frontmatter dict, raw frontmatter text, body text).

    Wiki files follow `---\\n<yaml>\\n---\\n\\n<body>`. If the format
    doesn't match, returns ({}, "", raw) so the caller can skip.
    """
    if not raw.startswith("---\n"):
        return {}, "", raw
    rest = raw[4:]
    end = rest.find("\n---\n")
    if end < 0:
        return {}, "", raw
    fm_text = rest[:end]
    body = rest[end + 5 :]
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        return {}, "", raw
    if not isinstance(fm, dict):
        return {}, "", raw
    return fm, fm_text, body


def _canonical_summary(fm: dict) -> str:
    """Top-level first, then `attributes.summary`, then empty."""
    top = fm.get("summary")
    if isinstance(top, str) and top.strip():
        return top.strip()
    attrs = fm.get("attributes") or {}
    if isinstance(attrs, dict):
        attr_sum = attrs.get("summary")
        if isinstance(attr_sum, str) and attr_sum.strip():
            return attr_sum.strip()
    return ""


def process_file(path: Path, apply: bool, verbose: bool) -> Tuple[bool, str]:
    """Return (changed, message).

    `changed` is True if the file would be rewritten (or was, when --apply).
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        return False, f"SKIP {path}: read error: {e}"

    fm, _fm_text, body = _split_frontmatter(raw)
    if not fm:
        return False, f"SKIP {path}: no parseable frontmatter"
    if "entity_id" not in fm or "entity_type" not in fm:
        return False, f"SKIP {path}: not a wiki entity (no entity_id/type)"

    summary = _canonical_summary(fm)
    if not summary:
        return False, f"SKIP {path}: no summary in frontmatter"

    new_body, body_changed = sync_summary_body(body, summary)
    fm_changed = False
    new_fm = dict(fm)
    if not isinstance(new_fm.get("summary"), str) or not new_fm["summary"].strip():
        new_fm["summary"] = summary
        fm_changed = True

    if not body_changed and not fm_changed:
        if verbose:
            return False, f"OK   {path}: already in sync"
        return False, ""

    if apply:
        new_fm_text = yaml.dump(
            new_fm, allow_unicode=True, default_flow_style=False, sort_keys=True
        )
        out = f"---\n{new_fm_text}---\n{new_body}" if not new_body.startswith("\n") else f"---\n{new_fm_text}---{new_body}"
        path.write_text(out, encoding="utf-8")
        tag = "WROTE"
    else:
        tag = "WOULD"

    parts = []
    if body_changed:
        parts.append("body")
    if fm_changed:
        parts.append("fm.summary")
    return True, f"{tag} {path}: {'+'.join(parts)} -> {summary[:60]!r}"


def main() -> int:
    # Korean summaries contain characters (en-dash, fullwidth punct) that
    # crash on Windows' default cp949 console. Force UTF-8 so dry-run
    # output is readable regardless of locale.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--apply",
        action="store_true",
        help="actually rewrite files (default: dry-run)",
    )
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="print every file (including no-op skips)",
    )
    ap.add_argument(
        "--root",
        type=Path,
        default=WIKI_ROOT,
        help=f"wiki entity root (default: {WIKI_ROOT})",
    )
    args = ap.parse_args()

    if not args.root.is_dir():
        print(f"ERROR: {args.root} is not a directory", file=sys.stderr)
        return 2

    files = sorted(args.root.rglob("*.md"))
    if not files:
        print(f"no .md files found under {args.root}")
        return 0

    changed = 0
    skipped = 0
    for f in files:
        ch, msg = process_file(f, apply=args.apply, verbose=args.verbose)
        if ch:
            changed += 1
            print(msg)
        elif msg:
            skipped += 1
            print(msg)

    mode = "APPLIED" if args.apply else "DRY-RUN"
    print()
    print(f"{mode}: {changed} file(s) {'rewritten' if args.apply else 'would change'}, "
          f"{len(files) - changed} unchanged.")
    if not args.apply and changed > 0:
        print("Rerun with --apply to write changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
