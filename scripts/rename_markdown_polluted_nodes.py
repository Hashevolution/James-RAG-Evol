"""Rename wiki entities whose name carries markdown emphasis tokens.

## Why this script exists

Before PR #452's forward fix, `WikiFrontmatterMixin.create_entity_file`
accepted `entity["name"]` verbatim from the LLM extractor. When the
LLM (Gemma / Gemini, especially on web-learning paths) wrapped a name
in markdown bold (`**…**`), italic (`*…*`), code (`` `…` ``), or
strike (`~~…~~`), those markers leaked all the way through:

- frontmatter `name`         — `**경쟁사 대비 AMD 기술적 우위**`
- frontmatter `normalized_name` — `___경쟁사_대비_amd_기술적_우위__`
  (the `*` collapses to `_` via the non-word substitution in
  `_normalize_name`)
- filename                   — `___경쟁사_대비_amd_기술적_우위__.md`
- `entity_id`                — `e_document_<hash>` keyed off the dirty
  normalized name, so the same logical entity gets a different id
  depending on whether the LLM bolded it on that pass

PR #452 fixes the *forward* path so new ingests can't produce this
state. This script patches the *backlog*: it walks the production
wiki, detects stale nodes by the `*` / `` ` `` / `~` markers in
`name`, computes a clean id/name/filename, and migrates every
cross-reference so the graph stays connected.

Current corpus (snapshot 2026-05-24): 6 stale nodes (~2.1% of 283).
The most-referenced one (`e_document_baffd813` — `web_general_**추
장치 옵션 검토:**`) is the target of 11 other entities'
`relations[].target_id`, so the cross-ref step is load-bearing.

## What it changes

Two passes:

**Pass 1 — build the rename map.** Scan every `wiki/entity/**/*.md`,
read frontmatter, and flag entries whose `name` contains `*` / `` ` ``
/ `~`. For each flagged entry, compute:

- `clean_name`       = the same emphasis-token strip + .strip() that
                       PR #452 applies on the forward path
- `clean_normalized` = same `_normalize_name` normalization (non-word
                       and non-Hangul chars collapse to `_`)
- `clean_entity_id`  = `e_{type}_{sha256(clean_normalized + "_" +
                       entity_type + "_JAMES_SECURE_V1")[:8]}` —
                       must mirror `_generate_entity_id` exactly so
                       a re-ingested doc lands on the same id
- `clean_filename`   = `{clean_normalized}.md`, or for `event`
                       entities the existing `_{8hex}` suffix
                       convention is preserved

Skips if `clean_name` is empty (e.g. name was literally `***`) — that
shape would have hit the `"unknown"` fallback in PR #452, and a
batch-rename to "unknown" would collide with every other empty entry.
Skips if a destination file already exists (name collision with a
clean sibling — extremely rare; logged as a warning for manual
resolution).

**Pass 2 — apply the rename.** For every wiki entity file:

1. If it's the stale entity itself: rewrite frontmatter
   (`name`, `normalized_name`, `entity_id`, `aliases`), rewrite the
   body's `## 관계` lines to use `clean_name` for the entity's own
   name in any backlinks, then rename the file on disk.
2. If it references a stale id in `relations[].target_id`: rewrite
   that field to `clean_entity_id`.
3. If it references the stale name in `relations[].target`: rewrite
   to `clean_name`.
4. Rewrite the body's `## 관계` lines so any `- 관련: <stale_name>`
   entries pick up the clean name (the wiki_generator template uses
   `target` text in that section, not `target_id`).

## Safety

- Dry-run by default. Prints every file that would change with the
  old → new mapping.
- `--apply` writes files in place and renames stale entity files.
  Run on a clean working tree so `git diff` + `git status` show
  exactly what moved.
- Refuses to write if the destination path already exists (would
  silently overwrite a sibling entity).
- Refuses to rename if `clean_name` resolves to empty after strip.
- Idempotent: a second `--apply` pass on an already-clean wiki finds
  0 stale nodes and writes nothing.

## Usage

    python scripts/rename_markdown_polluted_nodes.py             # dry-run
    python scripts/rename_markdown_polluted_nodes.py --apply     # write + rename
    python scripts/rename_markdown_polluted_nodes.py --apply --verbose
    python scripts/rename_markdown_polluted_nodes.py --root path/to/wiki/entity

## Out of scope

- Nodes with `**` *only* in `aliases` (not in `name`) — none observed
  in the current corpus; add if a future audit surfaces one.
- Nodes whose `normalized_name` carries `__` runs from legitimate
  punctuation in `name` (e.g. `Tesla, Inc. (TSLA)` →
  `tesla__inc___tsla_`). The double-underscore there is not markdown
  pollution, it's the normal output of normalizing `, `, ` (`, `) `.
  PR #452's strip would not touch it on the forward path either.
  Cleaning those up is a separate normalization-policy decision.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

# Path bootstrap — match scripts/recover_gemma_empty_summary.py convention.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

WIKI_ROOT = Path(__file__).resolve().parent.parent / "wiki" / "entity"

# Mirror the constants in core/wiki_generator/_frontmatter.py so this
# script can recompute the canonical id without importing the wiki
# generator (which would drag in chromadb / torch on first use).
_SALT = "JAMES_SECURE_V1"
_MARKDOWN_TOKEN_RE = re.compile(r"[\*`~]+")
_NORMALIZE_RE      = re.compile(r"[^\w가-힣]")


def _split_frontmatter(raw: str) -> Tuple[dict, str]:
    """Parse `---\\n…\\n---\\n<body>`. Returns ({}, raw) on any parse
    failure so a malformed file is just skipped, not crashed on."""
    if not raw.startswith("---\n"):
        return {}, raw
    rest = raw[4:]
    end = rest.find("\n---\n")
    if end < 0:
        return {}, raw
    fm_text = rest[:end]
    body    = rest[end + 5:]
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        return {}, raw
    if not isinstance(fm, dict):
        return {}, raw
    return fm, body


def _join_frontmatter(fm: dict, body: str) -> str:
    fm_text = yaml.dump(
        fm, allow_unicode=True, default_flow_style=False, sort_keys=True,
    )
    sep = "" if body.startswith("\n") else "\n"
    return f"---\n{fm_text}---{sep}{body}"


def _clean_name(name: str) -> str:
    """Same strip PR #452 applies on the forward path. Centralised here
    so script + test verify the script matches the forward behavior."""
    if not isinstance(name, str):
        return ""
    return _MARKDOWN_TOKEN_RE.sub("", name).strip()


def _normalize(name: str) -> str:
    return _NORMALIZE_RE.sub("_", name.strip().lower())


def _generate_entity_id(name: str, entity_type: str) -> str:
    normalized = _normalize(name)
    raw = f"{normalized}_{entity_type}_{_SALT}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:8]
    return f"e_{entity_type}_{h}"


def _is_markdown_polluted(name) -> bool:
    """A node is in scope if its `name` carries markdown emphasis
    tokens. We check `name`, not `normalized_name` or the filename,
    because `_normalize_name` collapses `*` → `_` so the polluted
    runs show up as `__` / `___` which is ambiguous (legitimate
    punctuation like `, ` also produces `__`)."""
    return isinstance(name, str) and bool(_MARKDOWN_TOKEN_RE.search(name))


@dataclass(frozen=True)
class _RenamePlan:
    old_path:     Path
    new_path:     Path
    old_name:     str
    new_name:     str
    old_id:       str
    new_id:       str
    old_norm:     str
    new_norm:     str
    entity_type:  str


def _build_rename_plan(
    fm: dict, path: Path, wiki_root: Path,
) -> Optional[_RenamePlan]:
    """Compute the migration mapping for one stale entity. Returns
    None if the entity is clean or if the planned rename is unsafe
    (empty clean name, destination collision)."""
    name = fm.get("name")
    if not _is_markdown_polluted(name):
        return None

    clean_name = _clean_name(name)
    if not clean_name:
        # Would have fallen back to "unknown" on the forward path,
        # but batch-renaming N entities to "unknown" would collide.
        return None

    entity_type = fm.get("entity_type") or fm.get("type") or "concept"
    old_id      = fm.get("entity_id") or _generate_entity_id(name, entity_type)
    new_id      = _generate_entity_id(clean_name, entity_type)
    old_norm    = fm.get("normalized_name") or _normalize(name)
    new_norm    = _normalize(clean_name)

    # Preserve the event-id `_{8hex}` suffix on filenames.
    suffix = ""
    if entity_type == "event" and path.stem.endswith(old_id[-8:]):
        suffix = f"_{new_id[-8:]}"
    new_filename = f"{new_norm}{suffix}.md"
    new_path = path.with_name(new_filename)

    return _RenamePlan(
        old_path     = path,
        new_path     = new_path,
        old_name     = str(name),
        new_name     = clean_name,
        old_id       = old_id,
        new_id       = new_id,
        old_norm     = str(old_norm),
        new_norm     = new_norm,
        entity_type  = entity_type,
    )


def _scan(wiki_root: Path) -> Tuple[List[_RenamePlan], List[str]]:
    """Pass 1 — walk every wiki entity file, collect rename plans.
    Returns (plans, warnings). A plan is None-filtered for clean nodes,
    so the list length == count of stale nodes."""
    plans:    List[_RenamePlan] = []
    warnings: List[str]         = []
    seen_new_paths: Dict[Path, _RenamePlan] = {}

    for md_path in sorted(wiki_root.rglob("*.md")):
        try:
            raw = md_path.read_text(encoding="utf-8")
        except OSError as e:
            warnings.append(f"read error: {md_path}: {e}")
            continue
        fm, _body = _split_frontmatter(raw)
        if not fm:
            continue
        plan = _build_rename_plan(fm, md_path, wiki_root)
        if plan is None:
            continue
        # Same-pass collision: two stale entities cleaning to the same
        # destination. Flag for manual resolution.
        prior = seen_new_paths.get(plan.new_path)
        if prior is not None:
            warnings.append(
                f"collision: {plan.old_path.name} and {prior.old_path.name} "
                f"both clean to {plan.new_path.name}"
            )
            continue
        # Cross-pass collision: destination already exists as a clean
        # sibling. Skip — the operator must merge by hand.
        if plan.new_path != plan.old_path and plan.new_path.exists():
            warnings.append(
                f"destination exists: {plan.old_path.name} → "
                f"{plan.new_path.name} (would overwrite a sibling)"
            )
            continue
        plans.append(plan)
        seen_new_paths[plan.new_path] = plan
    return plans, warnings


def _apply_xref_to_fm(fm: dict, id_map: Dict[str, str], name_map: Dict[str, str]) -> bool:
    """Rewrite `relations[].target_id` and `relations[].target` in
    place. Returns True if anything changed."""
    rels = fm.get("relations")
    if not isinstance(rels, list):
        return False
    changed = False
    for rel in rels:
        if not isinstance(rel, dict):
            continue
        old_tid = rel.get("target_id")
        if isinstance(old_tid, str) and old_tid in id_map:
            rel["target_id"] = id_map[old_tid]
            changed = True
        old_tname = rel.get("target")
        if isinstance(old_tname, str) and old_tname in name_map:
            rel["target"] = name_map[old_tname]
            changed = True
    return changed


def _apply_xref_to_body(body: str, name_map: Dict[str, str]) -> Tuple[str, bool]:
    """Rewrite `## 관계` section lines that mention a stale name
    verbatim. The wiki_generator template emits `- 관련: <name>
    (conf=…)`, so we do a literal name swap inside `관련:` lines only
    to avoid touching free-text that happens to contain the name."""
    changed = False
    out_lines = []
    for line in body.splitlines(keepends=True):
        # Cheap prefix check before the expensive substring loop.
        stripped = line.lstrip()
        if stripped.startswith("- ") and ": " in stripped:
            new_line = line
            for old, new in name_map.items():
                if old and old in new_line:
                    new_line = new_line.replace(old, new)
            if new_line != line:
                changed = True
                out_lines.append(new_line)
                continue
        out_lines.append(line)
    return "".join(out_lines), changed


def _apply_self_rewrite(
    fm: dict, body: str, plan: _RenamePlan,
) -> Tuple[dict, str]:
    """Rewrite the stale entity's own frontmatter (and any self-name
    occurrences in the body). Caller is responsible for the disk write
    + rename."""
    new_fm = dict(fm)
    new_fm["name"]            = plan.new_name
    new_fm["normalized_name"] = plan.new_norm
    new_fm["entity_id"]       = plan.new_id
    # Aliases: strip the old verbatim name if present, prepend clean.
    aliases = list(new_fm.get("aliases") or [])
    aliases = [a for a in aliases if a != plan.old_name]
    if plan.new_name not in aliases:
        aliases.insert(0, plan.new_name)
    new_fm["aliases"] = aliases
    # Body may reference the entity's own old name in backlink lines
    # (rare but observed in cross-citations). Swap them.
    new_body, _ = _apply_xref_to_body(body, {plan.old_name: plan.new_name})
    return new_fm, new_body


def _process_xref_only(
    fm: dict, body: str, id_map: Dict[str, str], name_map: Dict[str, str],
) -> Tuple[dict, str, bool]:
    """For files that aren't being renamed themselves but reference a
    stale node, rewrite their cross-refs. Returns (new_fm, new_body,
    changed)."""
    new_fm = dict(fm)
    fm_changed = _apply_xref_to_fm(new_fm, id_map, name_map)
    new_body, body_changed = _apply_xref_to_body(body, name_map)
    return new_fm, new_body, (fm_changed or body_changed)


def run(wiki_root: Path, apply: bool, verbose: bool) -> int:
    plans, warnings = _scan(wiki_root)
    for w in warnings:
        print(f"WARN  {w}")
    if not plans:
        print(f"OK    no markdown-polluted nodes under {wiki_root}")
        return 0

    print(f"SCAN  {len(plans)} stale node(s) found under {wiki_root}")
    id_map:   Dict[str, str] = {p.old_id:   p.new_id   for p in plans}
    name_map: Dict[str, str] = {p.old_name: p.new_name for p in plans}
    rename_paths = {p.old_path: p for p in plans}

    # Pass 2 — walk every file, rewrite xrefs, rewrite self for stale.
    n_xref   = 0
    n_self   = 0
    for md_path in sorted(wiki_root.rglob("*.md")):
        try:
            raw = md_path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"SKIP  {md_path}: read error: {e}")
            continue
        fm, body = _split_frontmatter(raw)
        if not fm:
            continue

        plan = rename_paths.get(md_path)
        if plan is not None:
            new_fm, new_body = _apply_self_rewrite(fm, body, plan)
            # Cross-refs in this same file (rare — e.g. a stale node
            # whose `relations[]` points to another stale node).
            _apply_xref_to_fm(new_fm, id_map, name_map)
            new_body, _ = _apply_xref_to_body(new_body, name_map)
            n_self += 1
            tag_action = "rename + self-rewrite"
            if apply:
                out = _join_frontmatter(new_fm, new_body)
                plan.new_path.write_text(out, encoding="utf-8")
                if plan.new_path != plan.old_path:
                    plan.old_path.unlink()
            print(
                f"{'WROTE' if apply else 'WOULD'} "
                f"{plan.old_path.name} → {plan.new_path.name}  "
                f"({tag_action}; id {plan.old_id} → {plan.new_id})"
            )
            continue

        new_fm, new_body, changed = _process_xref_only(
            fm, body, id_map, name_map,
        )
        if not changed:
            if verbose:
                print(f"OK    {md_path.name}: no xref to update")
            continue
        n_xref += 1
        if apply:
            out = _join_frontmatter(new_fm, new_body)
            md_path.write_text(out, encoding="utf-8")
        print(
            f"{'WROTE' if apply else 'WOULD'} "
            f"{md_path.name}: xref(s) updated"
        )

    print(
        f"DONE  {'applied' if apply else 'would apply'}: "
        f"{n_self} renamed, {n_xref} cross-ref'd"
    )
    return 0


def main() -> int:
    # UTF-8 stdout for Korean entity names on Windows cp949 consoles.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--apply", action="store_true",
        help="actually rewrite + rename (default: dry-run)",
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

    if not args.root.exists():
        print(f"FAIL  wiki root not found: {args.root}", file=sys.stderr)
        return 2
    return run(args.root, apply=args.apply, verbose=args.verbose)


if __name__ == "__main__":
    sys.exit(main())
