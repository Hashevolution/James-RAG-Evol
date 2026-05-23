"""Recover wiki entities whose summary is a Gemma error sentinel.

## Why this script exists

Before PR #447's forward fix, the web-learn path in `server_llmwiki.py`
checked only `len(knowledge.strip()) < 10` before falling back to a
snippet-based summary. The Gemma error sentinels — `[Gemma 응답 없음]`,
`[Gemma 오류] ...`, etc. — are 13+ characters, so they sailed past the
gate and got persisted to `attributes.summary` on disk. The graph node
detail panel then renders that sentinel as the entity's summary, which
is what the operator sees on the `/graph` page.

Current corpus: 15 entity files match (all
`learn_method: web_search` documents).

PR #447 fixes the *forward* path so new web-learn ingests can't
produce this state. This script patches the *backlog*: it rewrites
each stale node's summary in place using only the metadata that's
already on the file (no LLM call — Gemma may still be unhealthy on
the operator's machine).

## What it changes

For each `wiki/entity/**/*.md` whose `summary` or `attributes.summary`
starts with one of the Gemma `ERROR_PREFIXES`:

1. Synthesize a deterministic fallback summary from the file's own
   metadata, in this priority order:
   - `attributes.original_query` (the question the operator asked —
     usually the most descriptive)
   - `attributes.keywords`        (extracted topic tokens)
   - `name`                       (sanitized entity name)
2. Cap at 300 chars.
3. Rewrite frontmatter:
   - top-level `summary` (canonical, per PR #445)
   - `attributes.summary` (legacy field, kept in sync)
4. Rewrite the body's `## 요약` section via the shared helper
   `core.wiki_generator.sync_summary_body`.

## Safety

- Dry-run by default. Prints diff-style per-file output.
- `--apply` writes files in place. Run on a clean working tree so
  `git diff` shows the recovery delta.
- Skips files whose summary is already clean.
- Skips files that don't parse as wiki entities.

## Usage

    python scripts/recover_gemma_empty_summary.py             # dry-run
    python scripts/recover_gemma_empty_summary.py --apply     # write
    python scripts/recover_gemma_empty_summary.py --apply --verbose
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Tuple

import yaml

# Path bootstrap — match scripts/resync_wiki_summary_body.py convention.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.gemma_client import ERROR_PREFIXES  # noqa: E402
from core.wiki_generator import sync_summary_body  # noqa: E402


WIKI_ROOT = Path(__file__).resolve().parent.parent / "wiki" / "entity"
_SUMMARY_CAP = 300


def _split_frontmatter(raw: str) -> Tuple[dict, str]:
    if not raw.startswith("---\n"):
        return {}, raw
    rest = raw[4:]
    end = rest.find("\n---\n")
    if end < 0:
        return {}, raw
    fm_text = rest[:end]
    body = rest[end + 5 :]
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        return {}, raw
    if not isinstance(fm, dict):
        return {}, raw
    return fm, body


def _is_error_sentinel(s) -> bool:
    if not isinstance(s, str):
        return False
    stripped = s.strip()
    return bool(stripped) and stripped.startswith(ERROR_PREFIXES)


def _node_needs_recovery(fm: dict) -> bool:
    """A node needs recovery if either the top-level `summary` or
    `attributes.summary` is a Gemma error sentinel. We treat the two
    independently because (per PR #445) the two fields are sometimes
    out of sync on legacy data."""
    if _is_error_sentinel(fm.get("summary")):
        return True
    attrs = fm.get("attributes") or {}
    if isinstance(attrs, dict) and _is_error_sentinel(attrs.get("summary")):
        return True
    return False


def _fallback_summary(fm: dict) -> str:
    """Synthesize a deterministic summary from metadata that's already
    on the file. Priority: original_query > keywords > name. Always
    returns a non-empty string for nodes that need recovery (every
    web-learn entity carries at least a `name`)."""
    attrs = fm.get("attributes") or {}
    if isinstance(attrs, dict):
        oq = attrs.get("original_query")
        if isinstance(oq, str) and oq.strip():
            return oq.strip()[:_SUMMARY_CAP]
        kw = attrs.get("keywords")
        if isinstance(kw, str) and kw.strip():
            return kw.strip()[:_SUMMARY_CAP]
    name = fm.get("name")
    if isinstance(name, str) and name.strip():
        # Strip the `web_business_` prefix and the trailing
        # `_<timestamp>` suffix so the synthesized summary reads as the
        # original question, not the auto-generated entity id.
        n = name.strip()
        if n.startswith("web_business_"):
            n = n[len("web_business_") :]
        # Trim a trailing `_<digits>` if present (entity name suffix).
        import re
        n = re.sub(r"_\d{7,}$", "", n)
        return n.replace("_", " ")[:_SUMMARY_CAP]
    return "(웹 검색 자료 — 자동 요약 실패)"


def process_file(path: Path, apply: bool, verbose: bool) -> Tuple[bool, str]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        return False, f"SKIP {path}: read error: {e}"

    fm, body = _split_frontmatter(raw)
    if not fm:
        return False, ""
    if "entity_id" not in fm or "entity_type" not in fm:
        return False, ""
    if not _node_needs_recovery(fm):
        if verbose:
            return False, f"OK   {path}: summary clean"
        return False, ""

    fallback = _fallback_summary(fm)
    new_fm = dict(fm)
    new_fm["summary"] = fallback
    # Keep attributes.summary mirrored so legacy readers see the same value.
    attrs = dict(new_fm.get("attributes") or {})
    attrs["summary"] = fallback
    new_fm["attributes"] = attrs

    new_body, _body_changed = sync_summary_body(body, fallback)

    if apply:
        new_fm_text = yaml.dump(
            new_fm, allow_unicode=True, default_flow_style=False, sort_keys=True
        )
        out = f"---\n{new_fm_text}---\n{new_body}" if not new_body.startswith("\n") else f"---\n{new_fm_text}---{new_body}"
        path.write_text(out, encoding="utf-8")
        tag = "WROTE"
    else:
        tag = "WOULD"
    return True, f"{tag} {path}: -> {fallback[:60]!r}"


def main() -> int:
    # UTF-8 stdout for Korean output on Windows cp949 consoles.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--apply", action="store_true",
        help="actually rewrite files (default: dry-run)",
    )
    ap.add_argument(
        "--verbose", action="store_true",
        help="print every file (including no-op skips)",
    )
    ap.add_argument(
        "--root", type=Path, default=WIKI_ROOT,
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
    for f in files:
        ch, msg = process_file(f, apply=args.apply, verbose=args.verbose)
        if ch:
            changed += 1
            print(msg)
        elif msg and args.verbose:
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
